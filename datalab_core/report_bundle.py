from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

from shared.archive_validation import (
    ArchiveMemberRule,
    ArchiveValidationError,
    ArchiveValidationPolicy,
    normalize_archive_member_name,
    validate_archive_members,
    validate_archive_payloads,
)
from shared.workspace_schema import sha256_bytes
from .recipe_provenance import RecipeProvenanceError, normalize_recipe_provenance

SCHEMA = "datalab.report_bundle.v1"
SCHEMA_VERSION = 1

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOTS = 100
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOTS_COMBINED_BYTES = 50 * 1024 * 1024
MAX_TABLES = 100
MAX_TABLE_BYTES = 10 * 1024 * 1024
MAX_TABLES_COMBINED_BYTES = 50 * 1024 * 1024
MAX_LATEX_REPORT_BYTES = 10 * 1024 * 1024
MAX_LATEX_SECTIONS = 100
MAX_LATEX_SECTION_BYTES = 2 * 1024 * 1024
MAX_LATEX_SECTIONS_COMBINED_BYTES = 20 * 1024 * 1024
MAX_PLOTS = 64
MAX_PLOT_BYTES = 20 * 1024 * 1024
MAX_PLOTS_COMBINED_BYTES = 128 * 1024 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_SOURCES = 8
MAX_SOURCE_BYTES = 25 * 1024 * 1024
MAX_SOURCES_COMBINED_BYTES = 100 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024

_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = 0o100644 << 16
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PDF_SIGNATURE = b"%PDF-"

_REPORT_BUNDLE_ARCHIVE_POLICY = ArchiveValidationPolicy(
    rules=(
        ArchiveMemberRule(
            exact_path="manifest.json",
            max_file_bytes=MAX_MANIFEST_BYTES,
            file_size_error="manifest exceeds size limit",
        ),
        ArchiveMemberRule(
            prefix="snapshots/",
            required_suffix=".json",
            max_count=MAX_SNAPSHOTS,
            max_file_bytes=MAX_SNAPSHOT_BYTES,
            max_combined_bytes=MAX_SNAPSHOTS_COMBINED_BYTES,
            count_error="too many semantic snapshots",
            file_size_error="semantic snapshot exceeds size limit: {name}",
            combined_size_error="semantic snapshots exceed combined size limit",
            suffix_error="semantic snapshot must be json: {name}",
        ),
        ArchiveMemberRule(
            prefix="tables/",
            required_suffix=".csv",
            max_count=MAX_TABLES,
            max_file_bytes=MAX_TABLE_BYTES,
            max_combined_bytes=MAX_TABLES_COMBINED_BYTES,
            count_error="too many CSV tables",
            file_size_error="CSV table exceeds size limit: {name}",
            combined_size_error="CSV tables exceed combined size limit",
            suffix_error="table attachment must be csv: {name}",
        ),
        ArchiveMemberRule(
            exact_path="latex/report.tex",
            max_file_bytes=MAX_LATEX_REPORT_BYTES,
            file_size_error="LaTeX report exceeds size limit",
        ),
        ArchiveMemberRule(
            prefix="latex/sections/",
            required_suffix=".tex",
            max_count=MAX_LATEX_SECTIONS,
            max_file_bytes=MAX_LATEX_SECTION_BYTES,
            max_combined_bytes=MAX_LATEX_SECTIONS_COMBINED_BYTES,
            count_error="too many LaTeX sections",
            file_size_error="LaTeX section exceeds size limit: {name}",
            combined_size_error="LaTeX sections exceed combined size limit",
            suffix_error="LaTeX section must be tex: {name}",
        ),
        ArchiveMemberRule(
            prefix="plots/",
            required_suffix=".png",
            max_count=MAX_PLOTS,
            max_file_bytes=MAX_PLOT_BYTES,
            max_combined_bytes=MAX_PLOTS_COMBINED_BYTES,
            count_error="too many plot attachments",
            file_size_error="plot attachment exceeds size limit: {name}",
            combined_size_error="plot attachments exceed combined size limit",
            suffix_error="plot attachment must be png: {name}",
        ),
        ArchiveMemberRule(
            exact_path="pdf/report.pdf",
            max_file_bytes=MAX_PDF_BYTES,
            file_size_error="PDF report exceeds size limit",
        ),
        ArchiveMemberRule(
            prefix="sources/",
            max_count=MAX_SOURCES,
            max_file_bytes=MAX_SOURCE_BYTES,
            max_combined_bytes=MAX_SOURCES_COMBINED_BYTES,
            count_error="too many source attachments",
            file_size_error="source attachment exceeds size limit: {name}",
            combined_size_error="source attachments exceed combined size limit",
        ),
    ),
    total_uncompressed_bytes=MAX_TOTAL_UNCOMPRESSED_BYTES,
    total_size_error="report bundle exceeds total uncompressed size limit",
)


class ReportBundleValidationError(ValueError):
    """Raised when a report bundle is malformed or violates bundle policy."""


@dataclass(frozen=True)
class ReportBundleReadResult:
    manifest: dict[str, Any]
    snapshots: dict[str, dict[str, Any]]
    tables: dict[str, str]
    latex_report: str
    latex_sections: dict[str, str]
    plots: dict[str, bytes]
    pdf: bytes | None
    sources: dict[str, bytes]
    attachments: dict[str, bytes]


@dataclass(frozen=True)
class _AttachmentSpec:
    attachment_id: str
    path: str
    data: bytes
    media_type: str
    purpose: str
    extra: Mapping[str, Any] | None = None

    def manifest_entry(self) -> dict[str, Any]:
        entry = {
            "id": self.attachment_id,
            "path": self.path,
            "size_bytes": len(self.data),
            "sha256": sha256_bytes(self.data),
            "media_type": self.media_type,
            "purpose": self.purpose,
        }
        if self.extra:
            entry.update(dict(self.extra))
        return entry


def write_report_bundle(
    path: str | Path,
    *,
    semantic_snapshots: Mapping[str, Mapping[str, Any]],
    tables: Mapping[str, str | bytes],
    latex_report: str | bytes,
    latex_sections: Mapping[str, str | bytes] | None = None,
    plots: Mapping[str, bytes] | None = None,
    pdf: bytes | None = None,
    sources: Mapping[str, bytes] | None = None,
    datalab_version: str = "unknown",
    created_at: str | None = None,
    language: str = "unknown",
    precision_settings: Mapping[str, Any] | None = None,
    display_settings: Mapping[str, Any] | None = None,
    recipe_provenance: Mapping[str, Any] | None = None,
    export_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a self-contained `datalab.report_bundle.v1` ZIP bundle.

    The returned manifest is the exact JSON object written to `manifest.json`.
    """

    manifest, attachments = build_report_bundle_manifest(
        semantic_snapshots=semantic_snapshots,
        tables=tables,
        latex_report=latex_report,
        latex_sections=latex_sections,
        plots=plots,
        pdf=pdf,
        sources=sources,
        datalab_version=datalab_version,
        created_at=created_at,
        language=language,
        precision_settings=precision_settings,
        display_settings=display_settings,
        recipe_provenance=recipe_provenance,
        export_options=export_options,
    )
    _write_archive(Path(path), manifest, attachments)
    return manifest


def build_report_bundle_manifest(
    *,
    semantic_snapshots: Mapping[str, Mapping[str, Any]],
    tables: Mapping[str, str | bytes],
    latex_report: str | bytes,
    latex_sections: Mapping[str, str | bytes] | None = None,
    plots: Mapping[str, bytes] | None = None,
    pdf: bytes | None = None,
    sources: Mapping[str, bytes] | None = None,
    datalab_version: str = "unknown",
    created_at: str | None = None,
    language: str = "unknown",
    precision_settings: Mapping[str, Any] | None = None,
    display_settings: Mapping[str, Any] | None = None,
    recipe_provenance: Mapping[str, Any] | None = None,
    export_options: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    snapshot_specs = [
        _AttachmentSpec(
            attachment_id=name,
            path=_path_with_suffix("snapshots", name, ".json"),
            data=_json_bytes(snapshot, path=f"semantic_snapshots.{name}"),
            media_type="application/vnd.datalab.semantic-snapshot+json",
            purpose="semantic_snapshot",
        )
        for name, snapshot in sorted(semantic_snapshots.items())
    ]
    table_specs = [
        _AttachmentSpec(
            attachment_id=name,
            path=_path_with_suffix("tables", name, ".csv"),
            data=_text_bytes(table, path=f"tables.{name}"),
            media_type="text/csv; charset=utf-8",
            purpose="csv_table",
        )
        for name, table in sorted(tables.items())
    ]
    section_specs = [
        _AttachmentSpec(
            attachment_id=name,
            path=_path_with_suffix("latex/sections", name, ".tex"),
            data=_text_bytes(section, path=f"latex_sections.{name}"),
            media_type="text/x-tex; charset=utf-8",
            purpose="latex_section",
        )
        for name, section in sorted((latex_sections or {}).items())
    ]
    plot_specs = [
        _AttachmentSpec(
            attachment_id=name,
            path=_path_with_suffix("plots", name, ".png"),
            data=_png_bytes(data, path=f"plots.{name}"),
            media_type="image/png",
            purpose="plot",
            extra={"format": "png"},
        )
        for name, data in sorted((plots or {}).items())
    ]
    source_specs = [
        _AttachmentSpec(
            attachment_id=name,
            path=f"sources/{_validated_name(name, path=f'sources.{name}')}",
            data=_raw_bytes(data, path=f"sources.{name}"),
            media_type="application/octet-stream",
            purpose="source_data",
        )
        for name, data in sorted((sources or {}).items())
    ]

    report_spec = _AttachmentSpec(
        attachment_id="latex-report",
        path="latex/report.tex",
        data=_text_bytes(latex_report, path="latex_report"),
        media_type="text/x-tex; charset=utf-8",
        purpose="latex_report",
    )
    pdf_spec = (
        _AttachmentSpec(
            attachment_id="pdf-report",
            path="pdf/report.pdf",
            data=_pdf_bytes(pdf, path="pdf"),
            media_type="application/pdf",
            purpose="pdf_report",
        )
        if pdf is not None
        else None
    )

    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "datalab_version": _required_text(datalab_version, "metadata.datalab_version"),
            "created_at": _created_at_text(created_at),
            "language": _required_text(language, "metadata.language"),
            "precision_settings": _json_object(precision_settings or {}, "metadata.precision_settings"),
            "display_settings": _json_object(display_settings or {}, "metadata.display_settings"),
        },
        "selected_snapshots": _selected_snapshot_entries(semantic_snapshots),
        "export_options": _export_options(
            export_options,
            include_pdf_default=pdf_spec is not None,
            include_plots_default=bool(plot_specs),
            include_sources_default=bool(source_specs),
        ),
        "attachments": {
            "semantic_snapshots": [spec.manifest_entry() for spec in snapshot_specs],
            "tables": [spec.manifest_entry() for spec in table_specs],
            "latex": {
                "report": report_spec.manifest_entry(),
                "sections": [spec.manifest_entry() for spec in section_specs],
            },
            "plots": [spec.manifest_entry() for spec in plot_specs],
            "pdf": pdf_spec.manifest_entry() if pdf_spec is not None else None,
            "sources": [spec.manifest_entry() for spec in source_specs],
        },
    }
    if recipe_provenance is not None:
        manifest["metadata"]["recipe_provenance"] = _recipe_provenance_metadata(recipe_provenance)
    attachments = {
        spec.path: spec.data
        for spec in (
            snapshot_specs
            + table_specs
            + [report_spec]
            + section_specs
            + plot_specs
            + ([pdf_spec] if pdf_spec is not None else [])
            + source_specs
        )
    }
    validate_report_manifest(manifest)
    validate_report_manifest_attachment_hashes(manifest, attachments)
    _validate_archive_payloads_for_write(manifest, attachments)
    return manifest, attachments


def read_report_bundle(path: str | Path) -> ReportBundleReadResult:
    return _load_and_validate(Path(path))


def validate_report_manifest(manifest: dict[str, Any]) -> None:
    _validate_no_json_float(manifest, path="manifest")
    if not isinstance(manifest, dict):
        raise ReportBundleValidationError("manifest must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise ReportBundleValidationError(f"schema must be {SCHEMA!r}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ReportBundleValidationError("schema_version must be 1")

    metadata = _metadata_object(manifest.get("metadata"))
    _required_text(metadata.get("datalab_version"), "metadata.datalab_version")
    _timestamp_text(metadata.get("created_at"), "metadata.created_at")
    _required_text(metadata.get("language"), "metadata.language")
    _json_object(metadata.get("precision_settings"), "metadata.precision_settings")
    _json_object(metadata.get("display_settings"), "metadata.display_settings")
    if "recipe_provenance" in metadata:
        try:
            normalize_recipe_provenance(metadata.get("recipe_provenance"))
        except RecipeProvenanceError as exc:
            raise ReportBundleValidationError(f"metadata.recipe_provenance is invalid: {exc}") from exc
    export_options = _export_options_object(manifest.get("export_options"))
    selected_snapshots = _selected_snapshots_list(manifest.get("selected_snapshots"))

    attachments = manifest.get("attachments")
    if not isinstance(attachments, dict):
        raise ReportBundleValidationError("attachments must be an object")

    snapshots = _entry_list(attachments, "semantic_snapshots")
    tables = _entry_list(attachments, "tables")
    latex = attachments.get("latex")
    if not isinstance(latex, dict):
        raise ReportBundleValidationError("attachments.latex must be an object")
    report = _entry_object(latex.get("report"), "attachments.latex.report")
    sections = _entry_list(latex, "sections", parent_path="attachments.latex")
    plots = _entry_list(attachments, "plots")
    pdf = attachments.get("pdf")
    if pdf is not None:
        _entry_object(pdf, "attachments.pdf")
    sources = _entry_list(attachments, "sources")

    snapshot_ids = {cast(str, entry["id"]) for entry in snapshots}
    selected_ids = {cast(str, entry["id"]) for entry in selected_snapshots}
    if snapshot_ids != selected_ids:
        raise ReportBundleValidationError("selected_snapshots must match semantic snapshot attachments")
    _validate_export_options_consistency(export_options, plots=plots, pdf=pdf, sources=sources)

    _validate_entries(
        snapshots,
        prefix="snapshots/",
        suffix=".json",
        expected_purpose="semantic_snapshot",
        max_count=MAX_SNAPSHOTS,
        max_file_bytes=MAX_SNAPSHOT_BYTES,
        max_combined_bytes=MAX_SNAPSHOTS_COMBINED_BYTES,
        label="semantic snapshots",
    )
    _validate_entries(
        tables,
        prefix="tables/",
        suffix=".csv",
        expected_purpose="csv_table",
        max_count=MAX_TABLES,
        max_file_bytes=MAX_TABLE_BYTES,
        max_combined_bytes=MAX_TABLES_COMBINED_BYTES,
        label="CSV tables",
    )
    _validate_entry(
        report,
        expected_path="latex/report.tex",
        expected_purpose="latex_report",
        max_file_bytes=MAX_LATEX_REPORT_BYTES,
    )
    _validate_entries(
        sections,
        prefix="latex/sections/",
        suffix=".tex",
        expected_purpose="latex_section",
        max_count=MAX_LATEX_SECTIONS,
        max_file_bytes=MAX_LATEX_SECTION_BYTES,
        max_combined_bytes=MAX_LATEX_SECTIONS_COMBINED_BYTES,
        label="LaTeX sections",
    )
    _validate_entries(
        plots,
        prefix="plots/",
        suffix=".png",
        expected_purpose="plot",
        max_count=MAX_PLOTS,
        max_file_bytes=MAX_PLOT_BYTES,
        max_combined_bytes=MAX_PLOTS_COMBINED_BYTES,
        label="plot attachments",
    )
    for plot in plots:
        if plot.get("format") != "png":
            raise ReportBundleValidationError(f"plot attachment must declare png format: {plot.get('path')}")
    if pdf is not None:
        _validate_entry(
            _entry_object(pdf, "attachments.pdf"),
            expected_path="pdf/report.pdf",
            expected_purpose="pdf_report",
            max_file_bytes=MAX_PDF_BYTES,
        )
    _validate_entries(
        sources,
        prefix="sources/",
        suffix=None,
        expected_purpose="source_data",
        max_count=MAX_SOURCES,
        max_file_bytes=MAX_SOURCE_BYTES,
        max_combined_bytes=MAX_SOURCES_COMBINED_BYTES,
        label="source attachments",
    )
    _validate_global_attachment_ids(manifest)


def collect_report_attachment_paths(manifest: dict[str, Any]) -> set[str]:
    validate_report_manifest(manifest)
    return {entry["path"] for entry in _all_manifest_entries(manifest)}


def validate_report_manifest_attachment_hashes(
    manifest: dict[str, Any],
    attachments: Mapping[str, bytes],
) -> None:
    validate_report_manifest(manifest)
    for entry in _all_manifest_entries(manifest):
        path = cast(str, entry["path"])
        if path not in attachments:
            raise ReportBundleValidationError(f"missing attachment: {path}")
        data = attachments[path]
        if not isinstance(data, bytes):
            raise ReportBundleValidationError(f"attachment must be bytes: {path}")
        expected_size = entry["size_bytes"]
        if len(data) != expected_size:
            raise ReportBundleValidationError(f"attachment size mismatch: {path}")
        expected_hash = entry["sha256"]
        if sha256_bytes(data) != expected_hash:
            raise ReportBundleValidationError(f"attachment hash mismatch: {path}")
    _validate_global_attachment_ids(manifest)


def _write_archive(target: Path, manifest: dict[str, Any], attachments: Mapping[str, bytes]) -> None:
    manifest_bytes = _manifest_bytes(manifest)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as raw:
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED) as zf:
                zf.writestr(_deterministic_zip_info("manifest.json"), manifest_bytes)
                for name in sorted(attachments):
                    zf.writestr(_deterministic_zip_info(name), attachments[name])
            raw.flush()
            os.fsync(raw.fileno())
        _load_and_validate(Path(tmp_name))
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _load_and_validate(path: Path) -> ReportBundleReadResult:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            members = _validate_zip_members(zf)
            manifest = _read_manifest(zf, members["manifest.json"])
            expected_paths = collect_report_attachment_paths(manifest)
            archive_paths = set(members).difference({"manifest.json"})
            extra_paths = archive_paths.difference(expected_paths)
            if extra_paths:
                raise ReportBundleValidationError(f"unlisted attachment: {sorted(extra_paths)[0]}")
            missing_paths = expected_paths.difference(archive_paths)
            if missing_paths:
                raise ReportBundleValidationError(f"missing attachment: {sorted(missing_paths)[0]}")
            attachments = {name: _read_zip_member(zf, members[name]) for name in sorted(expected_paths)}
            validate_archive_payloads(
                attachments,
                hash_hook=lambda payloads: validate_report_manifest_attachment_hashes(manifest, dict(payloads)),
            )
            return _read_result_from_payloads(manifest, attachments)
    except zipfile.BadZipFile as exc:
        raise ReportBundleValidationError("report bundle is not a valid ZIP file") from exc


def _validate_zip_members(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    try:
        normalized = validate_archive_members(zf, _REPORT_BUNDLE_ARCHIVE_POLICY)
    except ArchiveValidationError as exc:
        raise ReportBundleValidationError(str(exc)) from exc
    if "manifest.json" not in normalized:
        raise ReportBundleValidationError("report bundle must contain exactly one manifest.json")
    return cast(dict[str, zipfile.ZipInfo], normalized)


def _read_manifest(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict[str, Any]:
    data = _read_zip_member(zf, info)
    try:
        manifest = json.loads(data.decode("utf-8"), parse_float=_reject_json_number, parse_constant=_reject_json_number)
    except (UnicodeDecodeError, json.JSONDecodeError, ReportBundleValidationError) as exc:
        raise ReportBundleValidationError("manifest must be valid UTF-8 JSON without JSON floats") from exc
    if not isinstance(manifest, dict):
        raise ReportBundleValidationError("manifest must be a JSON object")
    validate_report_manifest(manifest)
    return manifest


def _read_result_from_payloads(manifest: dict[str, Any], attachments: Mapping[str, bytes]) -> ReportBundleReadResult:
    attachment_entries = _attachments_object(manifest)
    latex = cast(dict[str, Any], attachment_entries["latex"])
    pdf_entry = attachment_entries.get("pdf")
    snapshots = {
        cast(str, entry["id"]): _snapshot_from_bytes(attachments[cast(str, entry["path"])], cast(str, entry["path"]))
        for entry in cast(list[dict[str, Any]], attachment_entries["semantic_snapshots"])
    }
    _validate_selected_snapshot_payloads(manifest, snapshots)
    tables = {
        cast(str, entry["id"]): _utf8_text(attachments[cast(str, entry["path"])], cast(str, entry["path"]))
        for entry in cast(list[dict[str, Any]], attachment_entries["tables"])
    }
    sections = {
        cast(str, entry["id"]): _utf8_text(attachments[cast(str, entry["path"])], cast(str, entry["path"]))
        for entry in cast(list[dict[str, Any]], latex["sections"])
    }
    plots = {
        cast(str, entry["id"]): _validated_png_payload(attachments[cast(str, entry["path"])], cast(str, entry["path"]))
        for entry in cast(list[dict[str, Any]], attachment_entries["plots"])
    }
    sources = {
        cast(str, entry["id"]): attachments[cast(str, entry["path"])]
        for entry in cast(list[dict[str, Any]], attachment_entries["sources"])
    }
    pdf = None
    if pdf_entry is not None:
        pdf_path = cast(str, cast(dict[str, Any], pdf_entry)["path"])
        pdf = _validated_pdf_payload(attachments[pdf_path], pdf_path)
    return ReportBundleReadResult(
        manifest=manifest,
        snapshots=snapshots,
        tables=tables,
        latex_report=_utf8_text(attachments[cast(str, cast(dict[str, Any], latex["report"])["path"])], "latex/report.tex"),
        latex_sections=sections,
        plots=plots,
        pdf=pdf,
        sources=sources,
        attachments=dict(attachments),
    )


def _read_zip_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    try:
        return zf.read(info)
    except (RuntimeError, NotImplementedError, zipfile.BadZipFile, OSError, EOFError) as exc:
        raise ReportBundleValidationError(f"unreadable archive entry: {info.filename}") from exc


def _validate_archive_payloads_for_write(manifest: dict[str, Any], attachments: Mapping[str, bytes]) -> None:
    try:
        validate_archive_payloads(
            attachments,
            hash_hook=lambda payloads: validate_report_manifest_attachment_hashes(manifest, dict(payloads)),
        )
    except ArchiveValidationError as exc:
        raise ReportBundleValidationError(str(exc)) from exc


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    validate_report_manifest(manifest)
    data = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(data) > MAX_MANIFEST_BYTES:
        raise ReportBundleValidationError("manifest exceeds size limit")
    return data


def _json_bytes(value: Mapping[str, Any], *, path: str) -> bytes:
    if not isinstance(value, Mapping):
        raise ReportBundleValidationError(f"{path} must be a JSON object")
    _validate_no_json_float(value, path=path)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ReportBundleValidationError(f"semantic snapshot exceeds size limit: {path}")
    return data


def _snapshot_from_bytes(data: bytes, path: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), parse_float=_reject_json_number, parse_constant=_reject_json_number)
    except (UnicodeDecodeError, json.JSONDecodeError, ReportBundleValidationError) as exc:
        raise ReportBundleValidationError(f"semantic snapshot must be valid UTF-8 JSON without JSON floats: {path}") from exc
    if not isinstance(value, dict):
        raise ReportBundleValidationError(f"semantic snapshot must be a JSON object: {path}")
    _validate_no_json_float(value, path=path)
    return value


def _text_bytes(value: str | bytes, *, path: str) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        _utf8_text(value, path)
        return value
    raise ReportBundleValidationError(f"{path} must be text or bytes")


def _raw_bytes(value: bytes, *, path: str) -> bytes:
    if not isinstance(value, bytes):
        raise ReportBundleValidationError(f"{path} must be bytes")
    return value


def _png_bytes(value: bytes, *, path: str) -> bytes:
    return _validated_png_payload(_raw_bytes(value, path=path), path)


def _pdf_bytes(value: bytes, *, path: str) -> bytes:
    return _validated_pdf_payload(_raw_bytes(value, path=path), path)


def _validated_png_payload(data: bytes, path: str) -> bytes:
    if not data.startswith(_PNG_SIGNATURE):
        raise ReportBundleValidationError(f"plot attachment must be png: {path}")
    return data


def _validated_pdf_payload(data: bytes, path: str) -> bytes:
    if not data.startswith(_PDF_SIGNATURE):
        raise ReportBundleValidationError(f"PDF report must start with a PDF header: {path}")
    return data


def _utf8_text(data: bytes, path: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportBundleValidationError(f"attachment must be UTF-8 text: {path}") from exc


def _path_with_suffix(prefix: str, name: str, suffix: str) -> str:
    filename = _validated_name(name, path=f"{prefix}.{name}")
    if not filename.endswith(suffix):
        filename = f"{filename}{suffix}"
    return f"{prefix}/{filename}"


def _validated_name(name: str, *, path: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ReportBundleValidationError(f"{path} must be a simple file name")
    if name in {".", ".."}:
        raise ReportBundleValidationError(f"{path} must be a simple file name")
    return name


def _entry_list(container: Mapping[str, Any], key: str, *, parent_path: str = "attachments") -> list[dict[str, Any]]:
    raw = container.get(key)
    if not isinstance(raw, list):
        raise ReportBundleValidationError(f"{parent_path}.{key} must be a list")
    return [_entry_object(item, f"{parent_path}.{key}[{index}]") for index, item in enumerate(raw)]


def _entry_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportBundleValidationError(f"{path} must be an object")
    for key in ("id", "path", "size_bytes", "sha256", "media_type", "purpose"):
        if key not in value:
            raise ReportBundleValidationError(f"{path}.{key} is required")
    if not isinstance(value["id"], str) or not value["id"]:
        raise ReportBundleValidationError(f"{path}.id must be a non-empty string")
    _validated_name(value["id"], path=f"{path}.id")
    if not isinstance(value["path"], str) or not value["path"]:
        raise ReportBundleValidationError(f"{path}.path must be a non-empty string")
    if isinstance(value["size_bytes"], bool) or not isinstance(value["size_bytes"], int) or value["size_bytes"] < 0:
        raise ReportBundleValidationError(f"{path}.size_bytes must be a non-negative integer")
    if not _is_sha256(value["sha256"]):
        raise ReportBundleValidationError(f"{path}.sha256 must be a sha256 digest")
    if not isinstance(value["media_type"], str) or not value["media_type"]:
        raise ReportBundleValidationError(f"{path}.media_type must be a non-empty string")
    if not isinstance(value["purpose"], str) or not value["purpose"]:
        raise ReportBundleValidationError(f"{path}.purpose must be a non-empty string")
    _normalize_archive_name(value["path"])
    return value


def _validate_entries(
    entries: Sequence[Mapping[str, Any]],
    *,
    prefix: str,
    suffix: str | None,
    expected_purpose: str,
    max_count: int,
    max_file_bytes: int,
    max_combined_bytes: int,
    label: str,
) -> None:
    if len(entries) > max_count:
        raise ReportBundleValidationError(f"too many {label}")
    combined = 0
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in entries:
        attachment_id = cast(str, entry["id"])
        if attachment_id in seen_ids:
            raise ReportBundleValidationError(f"duplicate attachment id: {attachment_id}")
        seen_ids.add(attachment_id)
        _validate_entry(
            entry,
            expected_path=_expected_attachment_path(prefix=prefix, suffix=suffix, attachment_id=attachment_id),
            prefix=prefix,
            suffix=suffix,
            expected_purpose=expected_purpose,
            max_file_bytes=max_file_bytes,
        )
        path = cast(str, entry["path"])
        if path in seen_paths:
            raise ReportBundleValidationError(f"duplicate attachment path: {path}")
        seen_paths.add(path)
        combined += cast(int, entry["size_bytes"])
    if combined > max_combined_bytes:
        raise ReportBundleValidationError(f"{label} exceed combined size limit")


def _validate_entry(
    entry: Mapping[str, Any],
    *,
    expected_path: str | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
    expected_purpose: str | None = None,
    max_file_bytes: int,
) -> None:
    path = cast(str, entry["path"])
    if expected_path is not None and path != expected_path:
        raise ReportBundleValidationError(f"attachment path must be {expected_path}: {path}")
    if prefix is not None and not path.startswith(prefix):
        raise ReportBundleValidationError(f"attachment path must start with {prefix}: {path}")
    if suffix is not None and not path.endswith(suffix):
        raise ReportBundleValidationError(f"attachment path must end with {suffix}: {path}")
    if expected_purpose is not None and entry["purpose"] != expected_purpose:
        raise ReportBundleValidationError(f"attachment purpose must be {expected_purpose}: {path}")
    if cast(int, entry["size_bytes"]) > max_file_bytes:
        raise ReportBundleValidationError(f"attachment exceeds size limit: {path}")


def _expected_attachment_path(*, prefix: str, suffix: str | None, attachment_id: str) -> str:
    if suffix is None:
        return f"{prefix}{attachment_id}"
    return _path_with_suffix(prefix.removesuffix("/"), attachment_id, suffix)


def _all_manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = _attachments_object(manifest)
    latex = cast(dict[str, Any], attachments["latex"])
    entries = list(cast(list[dict[str, Any]], attachments["semantic_snapshots"]))
    entries.extend(cast(list[dict[str, Any]], attachments["tables"]))
    entries.append(cast(dict[str, Any], latex["report"]))
    entries.extend(cast(list[dict[str, Any]], latex["sections"]))
    entries.extend(cast(list[dict[str, Any]], attachments["plots"]))
    pdf = attachments.get("pdf")
    if pdf is not None:
        entries.append(cast(dict[str, Any], pdf))
    entries.extend(cast(list[dict[str, Any]], attachments["sources"]))
    return entries


def _validate_global_attachment_ids(manifest: dict[str, Any]) -> None:
    seen: set[str] = set()
    for entry in _all_manifest_entries(manifest):
        attachment_id = cast(str, entry["id"])
        if attachment_id in seen:
            raise ReportBundleValidationError(f"duplicate attachment id: {attachment_id}")
        seen.add(attachment_id)


def _validate_selected_snapshot_payloads(
    manifest: Mapping[str, Any],
    snapshots: Mapping[str, Mapping[str, Any]],
) -> None:
    selected = _selected_snapshots_list(manifest.get("selected_snapshots"))
    for entry in selected:
        snapshot_id = cast(str, entry["id"])
        snapshot = snapshots.get(snapshot_id)
        if snapshot is None:
            raise ReportBundleValidationError(f"missing selected snapshot payload: {snapshot_id}")
        family = snapshot.get("family")
        kind = snapshot.get("kind")
        if family != entry["family"] or kind != entry["kind"]:
            raise ReportBundleValidationError(f"selected snapshot metadata mismatch: {snapshot_id}")


def _attachments_object(manifest: Mapping[str, Any]) -> dict[str, Any]:
    attachments = manifest.get("attachments")
    if not isinstance(attachments, dict):
        raise ReportBundleValidationError("attachments must be an object")
    return attachments


def _metadata_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportBundleValidationError("metadata must be an object")
    return value


def _recipe_provenance_metadata(value: Any) -> dict[str, Any]:
    try:
        return normalize_recipe_provenance(value)
    except RecipeProvenanceError as exc:
        raise ReportBundleValidationError(f"metadata.recipe_provenance is invalid: {exc}") from exc


def _json_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReportBundleValidationError(f"{path} must be an object")
    result = dict(value)
    _validate_no_json_float(result, path=path)
    return result


def _created_at_text(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return _timestamp_text(value, "metadata.created_at")


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportBundleValidationError(f"{path} must be a non-empty string")
    return value


def _timestamp_text(value: Any, path: str) -> str:
    text = _required_text(value, path)
    parseable = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parseable)
    except ValueError as exc:
        raise ReportBundleValidationError(f"{path} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ReportBundleValidationError(f"{path} must include a timezone")
    return text


def _optional_text(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ReportBundleValidationError(f"{path} must be a non-empty string or null")
    return value


def _selected_snapshot_entries(snapshots: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for index, (snapshot_id, snapshot) in enumerate(sorted(snapshots.items())):
        _validated_name(snapshot_id, path=f"selected_snapshots[{index}].id")
        entries.append(
            {
                "id": snapshot_id,
                "family": _required_text(snapshot.get("family"), f"selected_snapshots[{index}].family"),
                "kind": _required_text(snapshot.get("kind"), f"selected_snapshots[{index}].kind"),
            }
        )
    return entries


def _selected_snapshots_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ReportBundleValidationError("selected_snapshots must be a list")
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ReportBundleValidationError(f"selected_snapshots[{index}] must be an object")
        allowed = {"id", "family", "kind"}
        extra = set(item).difference(allowed)
        if extra:
            raise ReportBundleValidationError(f"selected_snapshots[{index}] contains unsupported key: {sorted(extra)[0]}")
        snapshot_id = _required_text(item.get("id"), f"selected_snapshots[{index}].id")
        _validated_name(snapshot_id, path=f"selected_snapshots[{index}].id")
        if snapshot_id in seen:
            raise ReportBundleValidationError(f"duplicate selected snapshot id: {snapshot_id}")
        seen.add(snapshot_id)
        entries.append(
            {
                "id": snapshot_id,
                "family": _required_text(item.get("family"), f"selected_snapshots[{index}].family"),
                "kind": _required_text(item.get("kind"), f"selected_snapshots[{index}].kind"),
            }
        )
    return entries


def _export_options(
    value: Mapping[str, Any] | None,
    *,
    include_pdf_default: bool,
    include_plots_default: bool,
    include_sources_default: bool,
) -> dict[str, Any]:
    options = {
        "include_pdf": include_pdf_default,
        "include_plots": include_plots_default,
        "include_source_data": include_sources_default,
        "include_rendered_caches": include_pdf_default or include_plots_default,
        "latex_engine": None,
        "compile_status": "succeeded" if include_pdf_default else "not_requested",
    }
    if value:
        options.update(dict(value))
    return _export_options_object(options)


def _export_options_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportBundleValidationError("export_options must be an object")
    _validate_no_json_float(value, path="export_options")
    for key in ("include_pdf", "include_plots", "include_source_data", "include_rendered_caches"):
        if not isinstance(value.get(key), bool):
            raise ReportBundleValidationError(f"export_options.{key} must be a boolean")
    latex_engine = value.get("latex_engine")
    if latex_engine is not None and (not isinstance(latex_engine, str) or not latex_engine.strip()):
        raise ReportBundleValidationError("export_options.latex_engine must be a non-empty string or null")
    compile_status = value.get("compile_status")
    if compile_status not in {"not_requested", "succeeded", "failed", "unavailable"}:
        raise ReportBundleValidationError("export_options.compile_status is unsupported")
    compile_error = value.get("compile_error")
    if compile_error is not None and not isinstance(compile_error, str):
        raise ReportBundleValidationError("export_options.compile_error must be a string or null")
    return dict(value)


def _validate_export_options_consistency(
    options: Mapping[str, Any],
    *,
    plots: Sequence[Mapping[str, Any]],
    pdf: Mapping[str, Any] | None,
    sources: Sequence[Mapping[str, Any]],
) -> None:
    if options["include_plots"] is False and plots:
        raise ReportBundleValidationError("export_options.include_plots is false but plot attachments are present")
    if options["include_pdf"] is False and pdf is not None:
        raise ReportBundleValidationError("export_options.include_pdf is false but PDF attachment is present")
    if options["include_rendered_caches"] is False and (plots or pdf is not None):
        raise ReportBundleValidationError(
            "export_options.include_rendered_caches is false but rendered attachments are present"
        )
    if options["include_source_data"] is False and sources:
        raise ReportBundleValidationError("export_options.include_source_data is false but source attachments are present")
    if options["compile_status"] == "succeeded" and pdf is None:
        raise ReportBundleValidationError("export_options.compile_status is succeeded but no PDF attachment is present")
    if options["compile_status"] != "succeeded" and pdf is not None:
        raise ReportBundleValidationError(
            "export_options.compile_status must be succeeded when a PDF attachment is present"
        )


def _validate_no_json_float(value: Any, *, path: str) -> None:
    if isinstance(value, float):
        raise ReportBundleValidationError(f"JSON floats are not allowed at {path}; pass numeric values as strings.")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, float):
                raise ReportBundleValidationError(f"JSON floats are not allowed at {path}.<key>; pass keys as strings.")
            if not isinstance(key, str):
                raise ReportBundleValidationError(f"Only string mapping keys are allowed at {path}.<key>.")
            _validate_no_json_float(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, item in enumerate(value):
            _validate_no_json_float(item, path=f"{path}[{index}]")


def _reject_json_number(value: str) -> NoReturn:
    raise ReportBundleValidationError(f"JSON floats are not allowed: {value}")


def _normalize_archive_name(name: str) -> str:
    try:
        return cast(str, normalize_archive_member_name(name, _REPORT_BUNDLE_ARCHIVE_POLICY))
    except ArchiveValidationError as exc:
        raise ReportBundleValidationError(str(exc)) from exc


def _deterministic_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = _ZIP_FILE_MODE
    return info


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value.removeprefix("sha256:")
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


__all__ = [
    "MAX_LATEX_REPORT_BYTES",
    "MAX_LATEX_SECTION_BYTES",
    "MAX_LATEX_SECTIONS",
    "MAX_LATEX_SECTIONS_COMBINED_BYTES",
    "MAX_MANIFEST_BYTES",
    "MAX_PDF_BYTES",
    "MAX_PLOT_BYTES",
    "MAX_PLOTS",
    "MAX_PLOTS_COMBINED_BYTES",
    "MAX_SNAPSHOT_BYTES",
    "MAX_SNAPSHOTS",
    "MAX_SNAPSHOTS_COMBINED_BYTES",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCES",
    "MAX_SOURCES_COMBINED_BYTES",
    "MAX_TABLE_BYTES",
    "MAX_TABLES",
    "MAX_TABLES_COMBINED_BYTES",
    "MAX_TOTAL_UNCOMPRESSED_BYTES",
    "ReportBundleReadResult",
    "ReportBundleValidationError",
    "SCHEMA",
    "SCHEMA_VERSION",
    "build_report_bundle_manifest",
    "collect_report_attachment_paths",
    "read_report_bundle",
    "validate_report_manifest",
    "validate_report_manifest_attachment_hashes",
    "write_report_bundle",
]
