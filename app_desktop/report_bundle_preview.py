from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datalab_core.report_bundle import ReportBundleReadResult, read_report_bundle
from shared.workspace_io import read_workspace
from shared.workspace_schema import WorkspaceValidationError


@dataclass(frozen=True)
class ReportBundleMetadataRow:
    key: str
    value: str


@dataclass(frozen=True)
class ReportBundleTextPreview:
    attachment_id: str
    path: str
    text: str
    size_bytes: int


@dataclass(frozen=True)
class ReportBundleBinaryPreview:
    attachment_id: str
    path: str
    media_type: str
    size_bytes: int


@dataclass(frozen=True)
class ReportBundleSelectedSnapshotPreview:
    attachment_id: str
    family: str
    kind: str


@dataclass(frozen=True)
class ReportBundleWorkspaceSourcePreview:
    attachment_id: str
    path: str
    size_bytes: int
    valid: bool
    title: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ReportBundlePreview:
    path: Path
    metadata_rows: tuple[ReportBundleMetadataRow, ...]
    selected_snapshots: tuple[ReportBundleSelectedSnapshotPreview, ...]
    latex_report: ReportBundleTextPreview
    latex_sections: tuple[ReportBundleTextPreview, ...]
    tables: tuple[ReportBundleTextPreview, ...]
    plots: tuple[ReportBundleBinaryPreview, ...]
    pdf: ReportBundleBinaryPreview | None
    sources: tuple[ReportBundleBinaryPreview, ...]
    source_workspaces: tuple[ReportBundleWorkspaceSourcePreview, ...]

    @property
    def openable_source_workspace_ids(self) -> tuple[str, ...]:
        return tuple(source.attachment_id for source in self.source_workspaces if source.valid)


def load_report_bundle_preview(path: str | Path) -> ReportBundlePreview:
    """Load a validated report bundle into a read-only desktop preview model."""

    target = Path(path)
    loaded = read_report_bundle(target)
    attachments = loaded.manifest["attachments"]
    latex = attachments["latex"]
    report_entry = latex["report"]
    pdf_entry = attachments.get("pdf")

    return ReportBundlePreview(
        path=target,
        metadata_rows=_metadata_rows(loaded.manifest),
        selected_snapshots=_selected_snapshots(loaded.manifest),
        latex_report=_text_preview(report_entry, loaded.latex_report),
        latex_sections=tuple(
            _text_preview(entry, loaded.latex_sections[entry["id"]]) for entry in latex["sections"]
        ),
        tables=tuple(_text_preview(entry, loaded.tables[entry["id"]]) for entry in attachments["tables"]),
        plots=tuple(_binary_preview(entry) for entry in attachments["plots"]),
        pdf=_binary_preview(pdf_entry) if pdf_entry is not None else None,
        sources=tuple(_binary_preview(entry) for entry in attachments["sources"]),
        source_workspaces=_source_workspace_previews(loaded),
    )


def _metadata_rows(manifest: dict[str, Any]) -> tuple[ReportBundleMetadataRow, ...]:
    metadata = manifest["metadata"]
    export_options = manifest["export_options"]
    rows = [
        ("schema", manifest["schema"]),
        ("schema_version", str(manifest["schema_version"])),
        ("datalab_version", metadata["datalab_version"]),
        ("created_at", metadata["created_at"]),
        ("language", metadata["language"]),
        ("compile_status", export_options["compile_status"]),
        ("include_pdf", _bool_text(export_options["include_pdf"])),
        ("include_plots", _bool_text(export_options["include_plots"])),
        ("include_source_data", _bool_text(export_options["include_source_data"])),
    ]
    latex_engine = export_options.get("latex_engine")
    if latex_engine is not None:
        rows.append(("latex_engine", str(latex_engine)))
    return tuple(ReportBundleMetadataRow(key=key, value=value) for key, value in rows)


def _selected_snapshots(manifest: dict[str, Any]) -> tuple[ReportBundleSelectedSnapshotPreview, ...]:
    return tuple(
        ReportBundleSelectedSnapshotPreview(
            attachment_id=str(item["id"]),
            family=str(item["family"]),
            kind=str(item["kind"]),
        )
        for item in manifest["selected_snapshots"]
    )


def _text_preview(entry: dict[str, Any], text: str) -> ReportBundleTextPreview:
    return ReportBundleTextPreview(
        attachment_id=str(entry["id"]),
        path=str(entry["path"]),
        text=text,
        size_bytes=int(entry["size_bytes"]),
    )


def _binary_preview(entry: dict[str, Any]) -> ReportBundleBinaryPreview:
    return ReportBundleBinaryPreview(
        attachment_id=str(entry["id"]),
        path=str(entry["path"]),
        media_type=str(entry["media_type"]),
        size_bytes=int(entry["size_bytes"]),
    )


def _source_workspace_previews(loaded: ReportBundleReadResult) -> tuple[ReportBundleWorkspaceSourcePreview, ...]:
    source_entries = loaded.manifest["attachments"]["sources"]
    previews: list[ReportBundleWorkspaceSourcePreview] = []
    for entry in source_entries:
        attachment_id = str(entry["id"])
        path = str(entry["path"])
        if not _looks_like_workspace_source(path):
            continue
        data = loaded.sources[attachment_id]
        previews.append(_validate_workspace_source(attachment_id=attachment_id, path=path, data=data))
    return tuple(previews)


def _looks_like_workspace_source(path: str) -> bool:
    lowered = path.lower()
    return lowered.endswith(".datalab") or lowered.endswith(".datalab.zip")


def _validate_workspace_source(*, attachment_id: str, path: str, data: bytes) -> ReportBundleWorkspaceSourcePreview:
    with tempfile.TemporaryDirectory(prefix="datalab-report-source-") as tmp_dir:
        candidate = Path(tmp_dir) / Path(path).name
        candidate.write_bytes(data)
        try:
            workspace = read_workspace(candidate).manifest["workspace"]
        except WorkspaceValidationError as exc:
            return ReportBundleWorkspaceSourcePreview(
                attachment_id=attachment_id,
                path=path,
                size_bytes=len(data),
                valid=False,
                error=str(exc),
            )
    title = workspace.get("title")
    return ReportBundleWorkspaceSourcePreview(
        attachment_id=attachment_id,
        path=path,
        size_bytes=len(data),
        valid=True,
        title=str(title) if isinstance(title, str) and title else None,
    )


def _bool_text(value: object) -> str:
    return "true" if value is True else "false"


def preview_to_json(preview: ReportBundlePreview) -> str:
    """Serialize preview metadata for tests or future read-only dialogs."""

    payload = {
        "path": str(preview.path),
        "metadata_rows": [row.__dict__ for row in preview.metadata_rows],
        "selected_snapshots": [snapshot.__dict__ for snapshot in preview.selected_snapshots],
        "latex_report": preview.latex_report.__dict__,
        "latex_sections": [section.__dict__ for section in preview.latex_sections],
        "tables": [table.__dict__ for table in preview.tables],
        "plots": [plot.__dict__ for plot in preview.plots],
        "pdf": None if preview.pdf is None else preview.pdf.__dict__,
        "sources": [source.__dict__ for source in preview.sources],
        "source_workspaces": [source.__dict__ for source in preview.source_workspaces],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)


__all__ = [
    "ReportBundleBinaryPreview",
    "ReportBundleMetadataRow",
    "ReportBundlePreview",
    "ReportBundleSelectedSnapshotPreview",
    "ReportBundleTextPreview",
    "ReportBundleWorkspaceSourcePreview",
    "load_report_bundle_preview",
    "preview_to_json",
]
