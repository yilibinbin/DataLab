"""Desktop formatting helpers for history comparison payloads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from datalab_core.history import HistoryEntry
from datalab_core.history_compare import history_comparison_to_json

COMPARE_CSV_HEADERS = [
    "section",
    "source",
    "key",
    "label_key",
    "row_index",
    "method",
    "value",
    "uncertainty",
    "severity",
    "message",
    "message_key",
    "render_group",
]

_SUPPORTED_RESULT_SCHEMAS = {
    "statistics": "datalab.result_snapshot.statistics",
    "fitting_comparison": "datalab.result_snapshot.fitting_comparison",
    "root_solving": "datalab.result_snapshot.root_solving",
    "uncertainty": "datalab.result_snapshot.uncertainty",
}


@dataclass(frozen=True)
class HistoryComparisonDisplay:
    text: str
    csv_rows: list[dict[str, str]]
    csv_headers: list[str]
    suggestion: str = "history_comparison.csv"


def history_compare_selection_diagnostic(
    current: HistoryEntry | None,
    selected: HistoryEntry | None,
    *,
    selected_is_current: bool = False,
    language: str = "en",
) -> str | None:
    """Return a localized reason when the conservative desktop compare rule fails."""

    if selected is None:
        return _localized(
            language,
            zh="请先选择一条最近历史记录。",
            en="Select a recent history entry first.",
        )
    if current is None:
        return _localized(
            language,
            zh="当前历史结果不可用，无法比较。",
            en="No current history result is available to compare.",
        )
    if selected_is_current or selected.entry_id == current.entry_id:
        return _localized(
            language,
            zh="请选择一条最近历史记录；当前结果会自动作为比较对象。",
            en="Select a recent history entry; the current result is compared automatically.",
        )
    current_result = _result_snapshot(current)
    selected_result = _result_snapshot(selected)
    if current_result is None or selected_result is None:
        return _localized(
            language,
            zh="所选历史记录缺少语义快照，无法比较。",
            en="The selected history entry is missing a semantic snapshot and cannot be compared.",
        )
    if current.family != selected.family:
        return _localized(
            language,
            zh="只能比较同一分析类型的历史记录。",
            en="Only history entries from the same analysis family can be compared.",
        )
    expected_schema = _SUPPORTED_RESULT_SCHEMAS.get(current.family)
    if expected_schema is None:
        return _localized(
            language,
            zh="此分析类型尚不支持历史比较。",
            en="History comparison is not supported for this analysis family yet.",
        )
    if (
        current_result.get("schema") != expected_schema
        or selected_result.get("schema") != expected_schema
        or current_result.get("schema_version") != 1
        or selected_result.get("schema_version") != 1
    ):
        return _localized(
            language,
            zh="所选历史记录的语义快照版本不支持比较。",
            en="The selected history entry uses an unsupported semantic snapshot schema.",
        )
    return None


def is_displayable_history_comparison(payload: Mapping[str, Any]) -> bool:
    normalized = history_comparison_to_json(payload)
    return str(normalized.get("comparison_mode") or "") == "same_family"


def build_history_comparison_display(
    payload: Mapping[str, Any],
    *,
    language: str = "en",
) -> HistoryComparisonDisplay:
    normalized = history_comparison_to_json(payload)
    rows = _csv_rows(normalized)
    return HistoryComparisonDisplay(
        text=_markdown_text(normalized, rows, language=language),
        csv_rows=rows,
        csv_headers=list(COMPARE_CSV_HEADERS),
    )


def _result_snapshot(entry: HistoryEntry) -> Mapping[str, Any] | None:
    semantic = entry.semantic_snapshot
    result = semantic.get("result") if isinstance(semantic, Mapping) else None
    if not isinstance(result, Mapping) or not result:
        return None
    return result


def _csv_rows(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section, payload_key in (
        ("comparison", "rows"),
        ("metadata", "metadata_rows"),
        ("diagnostic", "diagnostics"),
        ("budget", "budget_rows"),
    ):
        section_rows = payload.get(payload_key)
        if not isinstance(section_rows, list):
            continue
        for item in section_rows:
            if not isinstance(item, Mapping):
                continue
            value = _cell(item.get("value"))
            message = _cell(item.get("message"))
            if not message and section == "diagnostic":
                message = value
            rows.append(
                {
                    "section": section,
                    "source": _cell(item.get("source")),
                    "key": _cell(item.get("key")),
                    "label_key": _cell(item.get("label_key")),
                    "row_index": _cell(item.get("row_index")),
                    "method": _cell(item.get("method")),
                    "value": value,
                    "uncertainty": _cell(item.get("uncertainty")),
                    "severity": _cell(item.get("severity") or "info"),
                    "message": message,
                    "message_key": _cell(item.get("message_key")),
                    "render_group": _cell(item.get("render_group")),
                }
            )
    return rows


def _markdown_text(payload: Mapping[str, Any], rows: list[dict[str, str]], *, language: str) -> str:
    source = _mapping_or_empty(payload.get("source"))
    left = _mapping_or_empty(source.get("left"))
    right = _mapping_or_empty(source.get("right"))
    title = _localized(language, zh="历史比较", en="History comparison")
    left_label = _cell(left.get("label") if isinstance(left, Mapping) else "")
    right_label = _cell(right.get("label") if isinstance(right, Mapping) else "")
    mode = _cell(payload.get("comparison_mode"))
    family = payload.get("family") if isinstance(payload.get("family"), Mapping) else {}
    family_text = _cell(family.get("right") if isinstance(family, Mapping) else "")
    lines = [
        f"# {title}",
        "",
        f"- {_localized(language, zh='基准', en='Baseline')}: {_escape_inline(left_label)}",
        f"- {_localized(language, zh='当前', en='Current')}: {_escape_inline(right_label)}",
        f"- {_localized(language, zh='类型', en='Family')}: {_escape_inline(family_text)}",
        f"- {_localized(language, zh='模式', en='Mode')}: {_escape_inline(mode)}",
        "",
    ]
    if not rows:
        lines.append(_localized(language, zh="没有可显示的比较行。", en="No comparison rows to display."))
        return "\n".join(lines)

    lines.extend(
        [
            "| Section | Key | Value | Uncertainty | Severity | Message |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        message = row["message"] or row["message_key"]
        lines.append(
            "| "
            + " | ".join(
                _escape_table_cell(row[field])
                for field in ("section", "key", "value", "uncertainty", "severity")
            )
            + f" | {_escape_table_cell(message)} |"
        )
    return "\n".join(lines)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _escape_inline(value: str) -> str:
    return value.replace("\n", " ").strip()


def _escape_table_cell(value: str) -> str:
    return _escape_inline(value).replace("|", "\\|")


def _localized(language: str, *, zh: str, en: str) -> str:
    return zh if language == "zh" else en
