from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from datalab_core.history import HistoryEntry
from datalab_core.report_bundle import write_report_bundle
from datalab_latex.report_bundle import build_report_bundle_latex_report, build_report_bundle_latex_section
from shared.update_checker import current_version

from app_desktop.workspace_controller import render_semantic_snapshot_outputs

_BUNDLE_SUFFIX = ".datalab-report.zip"
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_ATTACHMENT_ID_LENGTH = 128
_RESERVED_ATTACHMENT_IDS = {"latex-report", "pdf-report"}


def write_history_entry_report_bundle(
    path: str | Path,
    entry: HistoryEntry,
    *,
    owner: Any | None = None,
    language: str = "unknown",
) -> Path:
    """Write a report bundle for one history entry and return the final path."""

    target = _report_bundle_target(path)
    snapshot_id = _safe_attachment_id(entry.entry_id or entry.label)
    table_id = _prefixed_attachment_id("table", snapshot_id)
    section_id = _prefixed_attachment_id("section", snapshot_id)
    snapshot = entry.to_json()["semantic_snapshot"]
    result_snapshot = snapshot.get("result") if isinstance(snapshot.get("result"), Mapping) else None
    rendered = render_semantic_snapshot_outputs(result_snapshot) if result_snapshot is not None else None
    tables: dict[str, str] = {}
    table_path = ""
    if rendered is not None:
        _text, rows, headers = rendered
        if rows and headers:
            tables[table_id] = _csv_text(rows, headers)
            table_path = f"tables/{table_id}.csv"

    section = {
        "id": section_id,
        "label": entry.label,
        "family": entry.family,
        "kind": entry.kind,
        "created_at": entry.created_at,
        "snapshot_path": f"snapshots/{snapshot_id}.json",
        "table_path": table_path,
    }
    latex_sections = {section_id: build_report_bundle_latex_section(section)}
    latex_report = build_report_bundle_latex_report(sections=[section], title="DataLab Report Bundle")
    plots = _entry_plot_attachments(entry, owner)

    write_report_bundle(
        target,
        semantic_snapshots={snapshot_id: snapshot},
        tables=tables,
        latex_report=latex_report,
        latex_sections=latex_sections,
        plots=plots,
        datalab_version=current_version(),
        language=language,
        precision_settings=_precision_settings(owner),
        display_settings=_display_settings(owner, language=language),
    )
    return target


def default_report_bundle_filename(entry: HistoryEntry) -> str:
    return f"{_safe_attachment_id(entry.label or entry.entry_id)}{_BUNDLE_SUFFIX}"


def _report_bundle_target(path: str | Path) -> Path:
    target = Path(path)
    if target.name and not target.name.endswith(_BUNDLE_SUFFIX) and target.suffix.lower() != ".zip":
        target = target.with_name(f"{target.name}{_BUNDLE_SUFFIX}")
    return target


def _safe_attachment_id(value: str, *, max_length: int = _MAX_ATTACHMENT_ID_LENGTH) -> str:
    cleaned = _SAFE_ID_RE.sub("-", value.strip()).strip(".-_")
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"entry-{cleaned}" if cleaned else "entry"
    if cleaned in _RESERVED_ATTACHMENT_IDS:
        cleaned = f"entry-{cleaned}"
    return cleaned[:max_length]


def _prefixed_attachment_id(prefix: str, value: str) -> str:
    cleaned_prefix = _safe_attachment_id(prefix, max_length=32)
    suffix_length = _MAX_ATTACHMENT_ID_LENGTH - len(cleaned_prefix) - 1
    suffix = _safe_attachment_id(value, max_length=suffix_length)
    return f"{cleaned_prefix}-{suffix}"


def _csv_text(rows: Sequence[Mapping[str, object]], headers: Sequence[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(headers), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: "" if row.get(header) is None else str(row.get(header)) for header in headers})
    return buffer.getvalue()


def _entry_plot_attachments(entry: HistoryEntry, owner: Any | None) -> dict[str, bytes]:
    cache = entry.rendered_cache if isinstance(entry.rendered_cache, Mapping) else {}
    plots = cache.get("plots") if isinstance(cache, Mapping) else None
    if not isinstance(plots, Sequence) or isinstance(plots, (str, bytes, bytearray, memoryview)):
        return {}
    workspace_attachments = getattr(owner, "_workspace_attachments", {}) if owner is not None else {}
    attachment_map = workspace_attachments if isinstance(workspace_attachments, Mapping) else {}
    output: dict[str, bytes] = {}
    for index, plot in enumerate(plots, 1):
        if not isinstance(plot, Mapping):
            continue
        path = plot.get("path")
        if not isinstance(path, str):
            continue
        data = attachment_map.get(path)
        if not isinstance(data, bytes):
            continue
        attachment_id = _plot_attachment_id(entry, plot, index)
        output[attachment_id] = data
    return output


def _plot_attachment_id(entry: HistoryEntry, plot: Mapping[str, object], index: int) -> str:
    column = str(plot.get("column") or "").strip()
    plot_index = str(plot.get("plot_index") or "").strip()
    parts = ["plot", entry.entry_id or entry.label]
    if column:
        parts.append(column)
    if plot_index:
        parts.append(plot_index)
    else:
        parts.append(str(index))
    return _safe_attachment_id("-".join(parts))


def _precision_settings(owner: Any | None) -> dict[str, int]:
    if owner is None:
        return {}
    return {
        "numeric_digits": _spin_value(getattr(owner, "precision_spin", None)),
        "display_digits": _display_digits(owner),
        "uncertainty_digits": _spin_value(getattr(owner, "uncertainty_digits_spin", None)),
    }


def _display_settings(owner: Any | None, *, language: str) -> dict[str, object]:
    if owner is None:
        return {"language": language}
    return {
        "language": language,
        "latex_input_digits": _spin_value(getattr(owner, "latex_input_precision_spin", None)),
        "latex_group_size": _spin_value(getattr(owner, "latex_group_size_spin", None)),
        "latex_dcolumn": _checkbox_checked(getattr(owner, "dcolumn_checkbox", None)),
    }


def _spin_value(widget: Any) -> int:
    if widget is None or not hasattr(widget, "value"):
        return 0
    try:
        value = widget.value()
    except Exception:
        return 0
    return int(value) if isinstance(value, int | float) else 0


def _display_digits(owner: Any) -> int:
    getter = getattr(owner, "_display_digits_value", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            return 0
    return _spin_value(getattr(owner, "digits_spin", None))


def _checkbox_checked(widget: Any) -> bool:
    if widget is None or not hasattr(widget, "isChecked"):
        return False
    try:
        return bool(widget.isChecked())
    except Exception:
        return False


__all__ = ["default_report_bundle_filename", "write_history_entry_report_bundle"]
