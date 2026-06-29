from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

from datalab_core.report_bundle import (
    MAX_SNAPSHOT_BYTES,
    MAX_SNAPSHOTS,
    ReportBundleValidationError,
    build_report_bundle_manifest,
    read_report_bundle,
    validate_report_manifest,
    write_report_bundle,
)
from shared.workspace_schema import sha256_bytes

PNG_BYTES = b"\x89PNG\r\n\x1a\nplot bytes"
PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


def test_report_bundle_round_trips_snapshots_tables_latex_without_pdf(tmp_path: Path) -> None:
    target = tmp_path / "report.datalab-report.zip"

    manifest = write_report_bundle(
        target,
        semantic_snapshots={
            "statistics": {
                "family": "statistics",
                "kind": "statistics_single",
                "metric_rows": [{"key": "mean", "value": "1.25"}],
                "count": 2,
            }
        },
        tables={"summary": "metric,value\nmean,1.25\n"},
        latex_report="\\documentclass{article}\n\\begin{document}\nReport\n\\end{document}\n",
        latex_sections={"methods": "\\section{Methods}\n"},
    )

    loaded = read_report_bundle(target)

    assert manifest["schema"] == "datalab.report_bundle.v1"
    assert manifest["metadata"]["datalab_version"] == "unknown"
    assert manifest["metadata"]["language"] == "unknown"
    assert manifest["metadata"]["precision_settings"] == {}
    assert manifest["metadata"]["display_settings"] == {}
    assert manifest["selected_snapshots"] == [{"id": "statistics", "family": "statistics", "kind": "statistics_single"}]
    assert manifest["export_options"]["include_pdf"] is False
    assert manifest["export_options"]["include_plots"] is False
    assert manifest["export_options"]["include_source_data"] is False
    assert manifest["export_options"]["compile_status"] == "not_requested"
    assert loaded.manifest == manifest
    assert loaded.snapshots["statistics"]["metric_rows"][0]["value"] == "1.25"
    assert loaded.tables == {"summary": "metric,value\nmean,1.25\n"}
    assert loaded.latex_report.startswith("\\documentclass")
    assert loaded.latex_sections == {"methods": "\\section{Methods}\n"}
    assert loaded.pdf is None

    snapshot_entry = manifest["attachments"]["semantic_snapshots"][0]
    assert snapshot_entry["path"] == "snapshots/statistics.json"
    assert snapshot_entry["purpose"] == "semantic_snapshot"
    assert snapshot_entry["sha256"] == sha256_bytes(loaded.attachments["snapshots/statistics.json"])
    assert snapshot_entry["size_bytes"] == len(loaded.attachments["snapshots/statistics.json"])

    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        manifest_info = zf.getinfo("manifest.json")

    assert names == [
        "manifest.json",
        "latex/report.tex",
        "latex/sections/methods.tex",
        "snapshots/statistics.json",
        "tables/summary.csv",
    ]
    assert manifest_info.compress_type == zipfile.ZIP_STORED
    assert manifest_info.date_time == (2026, 1, 1, 0, 0, 0)


def test_report_bundle_preserves_unit_metadata_in_semantic_snapshot_attachment(tmp_path: Path) -> None:
    target = tmp_path / "unit-aware-report.datalab-report.zip"
    unit_snapshot = {
        "schema": "datalab.result_snapshot.uncertainty",
        "schema_version": 1,
        "family": "uncertainty",
        "kind": "error",
        "metric_rows": [{"key": "result_value.1", "value": "2.0", "uncertainty": "0.1"}],
        "units": {
            "schema": "datalab.units.annotations.v1",
            "schema_version": 1,
            "enabled": True,
            "mode": "display_only",
            "inputs": {"x": {"unit": "m"}},
            "constants": {},
            "parameters": {},
            "outputs": {"result": {"unit": "m"}},
        },
    }

    write_report_bundle(
        target,
        semantic_snapshots={"uncertainty": unit_snapshot},
        tables={"uncertainty-table": "value,uncertainty,output_unit\n2.0,0.1,m\n"},
        latex_report="report",
    )

    loaded = read_report_bundle(target)

    assert loaded.manifest["selected_snapshots"] == [{"id": "uncertainty", "family": "uncertainty", "kind": "error"}]
    assert loaded.snapshots["uncertainty"]["units"]["outputs"]["result"]["unit"] == "m"
    assert loaded.snapshots["uncertainty"]["units"]["inputs"]["x"]["unit"] == "m"
    assert loaded.tables["uncertainty-table"].endswith(",m\n")


def test_report_bundle_preserves_non_error_family_unit_metadata(tmp_path: Path) -> None:
    target = tmp_path / "non-error-units-report.datalab-report.zip"
    units = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"A": {"unit": "m"}},
        "constants": {},
        "parameters": {},
        "outputs": {"result": {"unit": "m"}},
    }

    write_report_bundle(
        target,
        semantic_snapshots={
            "statistics": {
                "schema": "datalab.result_snapshot.statistics",
                "schema_version": 1,
                "family": "statistics",
                "kind": "statistics_single",
                "metric_rows": [{"key": "mean", "value": "1.25"}],
                "units": units,
            },
            "root": {
                "schema": "datalab.result_snapshot.root_solving",
                "schema_version": 1,
                "family": "root_solving",
                "kind": "root_batch",
                "metric_rows": [{"key": "result", "value": "2"}],
                "units": units,
            },
            "fit": {
                "schema": "datalab.result_snapshot.fitting",
                "schema_version": 1,
                "family": "fitting",
                "kind": "fit_single",
                "parameters": [{"name": "a", "value": "2"}],
                "units": units,
            },
        },
        tables={"summary": "metric,value\nmean,1.25\n"},
        latex_report="report",
    )

    loaded = read_report_bundle(target)

    assert loaded.snapshots["statistics"]["units"]["outputs"]["result"]["unit"] == "m"
    assert loaded.snapshots["root"]["units"]["inputs"]["A"]["unit"] == "m"
    assert loaded.snapshots["fit"]["units"]["enabled"] is True


def test_report_bundle_round_trips_optional_pdf_plot_and_source(tmp_path: Path) -> None:
    target = tmp_path / "report-with-assets.zip"

    write_report_bundle(
        target,
        semantic_snapshots={"fit": {"family": "fitting", "kind": "fit_single", "parameters": [{"name": "a", "value": "2"}]}},
        tables={"fit-results": "parameter,value\na,2\n"},
        latex_report="\\input{sections/fit}\n",
        plots={"fit-overview": PNG_BYTES},
        pdf=PDF_BYTES,
        sources={"raw-data.csv": b"x,y\n1,2\n"},
        datalab_version="2.7.10",
        created_at="2026-06-21T00:00:00Z",
        language="zh",
        precision_settings={"numeric_digits": 32},
        display_settings={"uncertainty_digits": 2},
        export_options={"latex_engine": "tectonic"},
    )

    loaded = read_report_bundle(target)

    assert loaded.manifest["metadata"] == {
        "datalab_version": "2.7.10",
        "created_at": "2026-06-21T00:00:00Z",
        "language": "zh",
        "precision_settings": {"numeric_digits": 32},
        "display_settings": {"uncertainty_digits": 2},
    }
    assert loaded.manifest["selected_snapshots"] == [{"id": "fit", "family": "fitting", "kind": "fit_single"}]
    assert loaded.manifest["export_options"] == {
        "include_pdf": True,
        "include_plots": True,
        "include_source_data": True,
        "include_rendered_caches": True,
        "latex_engine": "tectonic",
        "compile_status": "succeeded",
    }
    assert loaded.plots == {"fit-overview": PNG_BYTES}
    assert loaded.pdf == PDF_BYTES
    assert loaded.sources == {"raw-data.csv": b"x,y\n1,2\n"}
    assert loaded.manifest["attachments"]["plots"][0]["format"] == "png"
    assert loaded.manifest["attachments"]["pdf"]["id"] == "pdf-report"
    assert loaded.manifest["attachments"]["pdf"]["path"] == "pdf/report.pdf"
    assert loaded.manifest["attachments"]["sources"][0]["path"] == "sources/raw-data.csv"


@pytest.mark.parametrize("bad_name", ["../evil", "nested/name", "/absolute", ""])
def test_report_bundle_writer_rejects_unsafe_supplied_names(tmp_path: Path, bad_name: str) -> None:
    with pytest.raises(ReportBundleValidationError, match="simple file name"):
        write_report_bundle(
            tmp_path / "bad.zip",
            semantic_snapshots={bad_name: {"family": "statistics"}},
            tables={},
            latex_report="report",
        )


def test_report_bundle_rejects_attachment_hash_mismatch(tmp_path: Path) -> None:
    manifest, attachments = build_report_bundle_manifest(
        semantic_snapshots={"statistics": {"family": "statistics", "kind": "statistics_single"}},
        tables={},
        latex_report="report",
    )
    original = attachments["snapshots/statistics.json"]
    attachments["snapshots/statistics.json"] = original.replace(b"statistics", b"tamperstat", 1)
    assert len(attachments["snapshots/statistics.json"]) == len(original)
    target = tmp_path / "tampered.zip"
    _write_archive(target, manifest, attachments)

    with pytest.raises(ReportBundleValidationError, match="attachment hash mismatch: snapshots/statistics.json"):
        read_report_bundle(target)


def test_report_bundle_rejects_attachment_size_mismatch(tmp_path: Path) -> None:
    manifest, attachments = build_report_bundle_manifest(
        semantic_snapshots={"statistics": {"family": "statistics", "kind": "statistics_single"}},
        tables={},
        latex_report="report",
    )
    manifest["attachments"]["semantic_snapshots"][0]["size_bytes"] += 1
    target = tmp_path / "bad-size.zip"
    _write_archive(target, manifest, attachments)

    with pytest.raises(ReportBundleValidationError, match="attachment size mismatch: snapshots/statistics.json"):
        read_report_bundle(target)


def test_report_bundle_rejects_too_many_snapshots(tmp_path: Path) -> None:
    snapshots = {f"s{i:03d}": {"family": "statistics", "kind": "statistics_single"} for i in range(MAX_SNAPSHOTS + 1)}

    with pytest.raises(ReportBundleValidationError, match="too many semantic snapshots"):
        write_report_bundle(
            tmp_path / "too-many.zip",
            semantic_snapshots=snapshots,
            tables={},
            latex_report="report",
        )


def test_report_bundle_rejects_oversized_snapshot_member(tmp_path: Path) -> None:
    payload = b'{"text":"' + (b"x" * MAX_SNAPSHOT_BYTES) + b'"}'
    manifest = _minimal_manifest(
        semantic_snapshots=[
            _entry(
                "big",
                "snapshots/big.json",
                payload,
                media_type="application/vnd.datalab.semantic-snapshot+json",
                purpose="semantic_snapshot",
            )
        ]
    )
    target = tmp_path / "oversized.zip"
    _write_archive(target, manifest, {"snapshots/big.json": payload, "latex/report.tex": b"report"})

    with pytest.raises(ReportBundleValidationError, match="semantic snapshot exceeds size limit"):
        read_report_bundle(target)


def test_report_bundle_rejects_json_floats_on_write_and_read(tmp_path: Path) -> None:
    with pytest.raises(ReportBundleValidationError, match="JSON floats are not allowed"):
        write_report_bundle(
            tmp_path / "float-write.zip",
            semantic_snapshots={"statistics": {"mean": 1.5}},
            tables={},
            latex_report="report",
        )

    snapshot = b'{"mean":1.5}'
    manifest = _minimal_manifest(
        semantic_snapshots=[
            _entry(
                "statistics",
                "snapshots/statistics.json",
                snapshot,
                media_type="application/vnd.datalab.semantic-snapshot+json",
                purpose="semantic_snapshot",
            )
        ]
    )
    target = tmp_path / "float-read.zip"
    _write_archive(target, manifest, {"snapshots/statistics.json": snapshot, "latex/report.tex": b"report"})

    with pytest.raises(ReportBundleValidationError, match="semantic snapshot must be valid UTF-8 JSON without JSON floats"):
        read_report_bundle(target)

    manifest["attachments"]["semantic_snapshots"][0]["confidence"] = 0.5
    with pytest.raises(ReportBundleValidationError, match="JSON floats are not allowed"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_incomplete_manifest_metadata() -> None:
    manifest = _minimal_manifest()
    del manifest["metadata"]

    with pytest.raises(ReportBundleValidationError, match="metadata must be an object"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_selected_snapshot_mismatch() -> None:
    manifest = _minimal_manifest(
        semantic_snapshots=[
            _entry(
                "statistics",
                "snapshots/statistics.json",
                b'{"family":"statistics"}',
                media_type="application/vnd.datalab.semantic-snapshot+json",
                purpose="semantic_snapshot",
            )
        ]
    )
    manifest["selected_snapshots"] = [{"id": "other", "family": "statistics", "kind": "statistics_single"}]

    with pytest.raises(ReportBundleValidationError, match="selected_snapshots must match semantic snapshot attachments"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_selected_snapshot_metadata_mismatch_on_read(tmp_path: Path) -> None:
    snapshot = b'{"family":"statistics","kind":"statistics_single"}'
    manifest = _minimal_manifest(
        semantic_snapshots=[
            _entry(
                "statistics",
                "snapshots/statistics.json",
                snapshot,
                media_type="application/vnd.datalab.semantic-snapshot+json",
                purpose="semantic_snapshot",
            )
        ]
    )
    manifest["selected_snapshots"] = [{"id": "statistics", "family": "root_solving", "kind": "root_solving"}]
    target = tmp_path / "mismatch.zip"
    _write_archive(target, manifest, {"snapshots/statistics.json": snapshot, "latex/report.tex": b"report"})

    with pytest.raises(ReportBundleValidationError, match="selected snapshot metadata mismatch"):
        read_report_bundle(target)


def test_report_bundle_rejects_export_options_inconsistent_with_attachments() -> None:
    manifest = _minimal_manifest()
    manifest["export_options"]["compile_status"] = "succeeded"

    with pytest.raises(ReportBundleValidationError, match="succeeded but no PDF attachment"):
        validate_report_manifest(manifest)


@pytest.mark.parametrize("compile_status", ["not_requested", "failed", "unavailable"])
def test_report_bundle_rejects_pdf_with_unsuccessful_compile_status(compile_status: str) -> None:
    manifest = _minimal_manifest()
    manifest["attachments"]["pdf"] = _entry(
        "pdf-report",
        "pdf/report.pdf",
        PDF_BYTES,
        media_type="application/pdf",
        purpose="pdf_report",
    )
    manifest["export_options"]["include_pdf"] = True
    manifest["export_options"]["include_rendered_caches"] = True
    manifest["export_options"]["compile_status"] = compile_status

    with pytest.raises(ReportBundleValidationError, match="must be succeeded when a PDF attachment is present"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_duplicate_attachment_ids() -> None:
    first = _entry(
        "same",
        "tables/same.csv",
        b"a\n",
        media_type="text/csv; charset=utf-8",
        purpose="csv_table",
    )
    second = _entry(
        "same",
        "tables/same-2.csv",
        b"b\n",
        media_type="text/csv; charset=utf-8",
        purpose="csv_table",
    )
    manifest = _minimal_manifest()
    manifest["attachments"]["tables"] = [first, second]

    with pytest.raises(ReportBundleValidationError, match="duplicate attachment id: same"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_global_duplicate_attachment_ids() -> None:
    manifest = _minimal_manifest()
    manifest["attachments"]["pdf"] = _entry(
        "latex-report",
        "pdf/report.pdf",
        PDF_BYTES,
        media_type="application/pdf",
        purpose="pdf_report",
    )
    manifest["export_options"]["include_pdf"] = True
    manifest["export_options"]["include_rendered_caches"] = True
    manifest["export_options"]["compile_status"] = "succeeded"

    with pytest.raises(ReportBundleValidationError, match="duplicate attachment id: latex-report"):
        validate_report_manifest(manifest)


@pytest.mark.parametrize(
    ("group_path", "entry_id", "path", "data", "media_type", "purpose", "message"),
    [
        (
            ("attachments", "semantic_snapshots"),
            "statistics",
            "snapshots/other.json",
            b"{}",
            "application/vnd.datalab.semantic-snapshot+json",
            "semantic_snapshot",
            "attachment path must be snapshots/statistics.json",
        ),
        (
            ("attachments", "tables"),
            "summary",
            "tables/other.csv",
            b"a\n",
            "text/csv; charset=utf-8",
            "csv_table",
            "attachment path must be tables/summary.csv",
        ),
        (
            ("attachments", "plots"),
            "plot",
            "plots/other.png",
            PNG_BYTES,
            "image/png",
            "plot",
            "attachment path must be plots/plot.png",
        ),
        (
            ("attachments", "sources"),
            "raw.csv",
            "sources/other.csv",
            b"x\n",
            "application/octet-stream",
            "source_data",
            "attachment path must be sources/raw.csv",
        ),
    ],
)
def test_report_bundle_rejects_attachment_paths_that_do_not_match_ids(
    group_path: tuple[str, str],
    entry_id: str,
    path: str,
    data: bytes,
    media_type: str,
    purpose: str,
    message: str,
) -> None:
    entry = _entry(entry_id, path, data, media_type=media_type, purpose=purpose)
    manifest = _minimal_manifest()
    manifest[group_path[0]][group_path[1]] = [entry]
    if group_path[1] == "semantic_snapshots":
        manifest["selected_snapshots"] = [{"id": entry["id"], "family": "statistics", "kind": "statistics_single"}]
    if group_path[1] == "plots":
        manifest["export_options"]["include_plots"] = True
        manifest["export_options"]["include_rendered_caches"] = True
    if group_path[1] == "sources":
        manifest["export_options"]["include_source_data"] = True

    with pytest.raises(ReportBundleValidationError, match=message):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_wrong_attachment_purpose() -> None:
    manifest = _minimal_manifest()
    manifest["attachments"]["tables"] = [
        _entry("summary", "tables/summary.csv", b"a\n", media_type="text/csv; charset=utf-8", purpose="source_data")
    ]

    with pytest.raises(ReportBundleValidationError, match="attachment purpose must be csv_table"):
        validate_report_manifest(manifest)

    manifest = _minimal_manifest()
    manifest["attachments"]["latex"]["report"]["purpose"] = "latex_section"
    with pytest.raises(ReportBundleValidationError, match="attachment purpose must be latex_report"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_invalid_created_timestamp() -> None:
    manifest = _minimal_manifest()
    manifest["metadata"]["created_at"] = "not-a-timestamp"

    with pytest.raises(ReportBundleValidationError, match="ISO-8601 timestamp"):
        validate_report_manifest(manifest)

    manifest["metadata"]["created_at"] = "2026-06-21T00:00:00"
    with pytest.raises(ReportBundleValidationError, match="must include a timezone"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_latex_section_limits_and_purpose() -> None:
    manifest = _minimal_manifest()
    manifest["attachments"]["latex"]["sections"] = [
        _entry("methods", "latex/sections/methods.tex", b"x", media_type="text/x-tex; charset=utf-8", purpose="source_data")
    ]

    with pytest.raises(ReportBundleValidationError, match="attachment purpose must be latex_section"):
        validate_report_manifest(manifest)


def test_report_bundle_rejects_pdf_purpose_and_path() -> None:
    manifest = _minimal_manifest()
    manifest["attachments"]["pdf"] = _entry(
        "report",
        "pdf/report.pdf",
        PDF_BYTES,
        media_type="application/pdf",
        purpose="source_data",
    )
    manifest["export_options"]["include_pdf"] = True
    manifest["export_options"]["include_rendered_caches"] = True
    manifest["export_options"]["compile_status"] = "succeeded"

    with pytest.raises(ReportBundleValidationError, match="attachment purpose must be pdf_report"):
        validate_report_manifest(manifest)


@pytest.mark.parametrize(
    ("extra_name", "message"),
    [
        ("../evil.json", "unsafe archive path"),
        ("unexpected/file.txt", "unsupported archive path"),
        ("plots/plot.gif", "plot attachment must be png"),
    ],
)
def test_report_bundle_rejects_hostile_or_unsupported_archive_paths(
    tmp_path: Path,
    extra_name: str,
    message: str,
) -> None:
    manifest = _minimal_manifest()
    target = tmp_path / "hostile.zip"
    _write_archive(target, manifest, {"latex/report.tex": b"report"}, extra_entries=[(extra_name, b"x")])

    with pytest.raises(ReportBundleValidationError, match=message):
        read_report_bundle(target)


def test_report_bundle_rejects_directory_and_symlink_members(tmp_path: Path) -> None:
    manifest = _minimal_manifest()
    directory_target = tmp_path / "directory.zip"
    _write_archive(directory_target, manifest, {"latex/report.tex": b"report"}, directories=["sources/"])

    with pytest.raises(ReportBundleValidationError, match="directory entries are not allowed"):
        read_report_bundle(directory_target)

    symlink_target = tmp_path / "symlink.zip"
    _write_archive(symlink_target, manifest, {"latex/report.tex": b"report"}, symlinks=["sources/link"])

    with pytest.raises(ReportBundleValidationError, match="symlink entries are not allowed"):
        read_report_bundle(symlink_target)


def test_report_bundle_rejects_malformed_zip(tmp_path: Path) -> None:
    target = tmp_path / "not-a-zip.zip"
    target.write_bytes(b"not a zip")

    with pytest.raises(ReportBundleValidationError, match="not a valid ZIP file"):
        read_report_bundle(target)


def _entry(
    attachment_id: str,
    path: str,
    data: bytes,
    *,
    media_type: str,
    purpose: str,
) -> dict[str, Any]:
    return {
        "id": attachment_id,
        "path": path,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
        "media_type": media_type,
        "purpose": purpose,
    }


def _minimal_manifest(
    *,
    semantic_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report_data = b"report"
    snapshots = semantic_snapshots or []
    return {
        "schema": "datalab.report_bundle.v1",
        "schema_version": 1,
        "metadata": {
            "datalab_version": "2.7.10",
            "created_at": "2026-06-21T00:00:00Z",
            "language": "zh",
            "precision_settings": {},
            "display_settings": {},
        },
        "selected_snapshots": [
            {"id": entry["id"], "family": "statistics", "kind": "statistics_single"} for entry in snapshots
        ],
        "export_options": {
            "include_pdf": False,
            "include_plots": False,
            "include_source_data": False,
            "include_rendered_caches": False,
            "latex_engine": None,
            "compile_status": "not_requested",
        },
        "attachments": {
            "semantic_snapshots": snapshots,
            "tables": [],
            "latex": {
                "report": _entry(
                    "latex-report",
                    "latex/report.tex",
                    report_data,
                    media_type="text/x-tex; charset=utf-8",
                    purpose="latex_report",
                ),
                "sections": [],
            },
            "plots": [],
            "pdf": None,
            "sources": [],
        },
    }


def _write_archive(
    target: Path,
    manifest: Mapping[str, Any],
    attachments: Mapping[str, bytes],
    *,
    extra_entries: Iterable[tuple[str, bytes]] = (),
    directories: Iterable[str] = (),
    symlinks: Iterable[str] = (),
) -> None:
    buffer = io.BytesIO()
    symlink_names = set(symlinks)
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        for name in directories:
            zf.writestr(name, b"")
        for name, payload in {**dict(attachments), **dict(extra_entries), **{name: b"target" for name in symlink_names}}.items():
            info = zipfile.ZipInfo(name)
            if name in symlink_names:
                info.create_system = 3
                info.external_attr = 0o120777 << 16
            zf.writestr(info, payload)
    target.write_bytes(buffer.getvalue())
