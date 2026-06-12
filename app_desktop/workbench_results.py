"""Adapters for the compact result overview in the workbench rail."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app_desktop.theme import result_overview_card_style

MAX_RESULT_OVERVIEW_ROWS = 50
MAX_RESULT_OVERVIEW_STATE_ROWS = 100

ResultOverviewKind = Literal["none", "running", "tabular", "plot", "text", "plot_text", "empty_success", "failed"]


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    label_zh: str
    label_en: str
    value_zh: str
    value_en: str


@dataclass(frozen=True, slots=True)
class ResultOutputPart:
    label_zh: str
    meta_en: str
    summary_en: str


@dataclass(frozen=True, slots=True)
class ResultOverviewState:
    kind: ResultOverviewKind
    preview_rows: tuple[dict[str, object], ...] = ()
    total_rows: int = 0
    headers: tuple[str, ...] = ()
    has_plot: bool = False
    has_text: bool = False
    export_artifacts: tuple[ExportArtifact, ...] = ()


def build_result_overview(owner: Any) -> QWidget:
    widget = QWidget()
    widget.setObjectName("workbench_result_overview_panel")
    widget.setStyleSheet(result_overview_card_style())
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(4)

    title_row = QWidget()
    title_row.setObjectName("workbench_result_overview_title_row")
    title_layout = QHBoxLayout(title_row)
    title_layout.setContentsMargins(0, 0, 0, 0)
    title_layout.setSpacing(6)

    owner.workbench_result_overview_title = QLabel(owner._tr("结果概览", "Result overview"))
    owner.workbench_result_overview_title.setObjectName("workbench_result_overview_title")
    title_layout.addWidget(owner.workbench_result_overview_title, 1)

    owner.workbench_result_status_badge = QLabel(owner._tr("等待", "Waiting"))
    owner.workbench_result_status_badge.setObjectName("workbench_result_status_badge")
    owner.workbench_result_status_badge.setProperty("datalab_result_status", "waiting")
    title_layout.addWidget(owner.workbench_result_status_badge, 0)
    layout.addWidget(title_row)

    owner.workbench_result_overview = QLabel(owner._tr("暂无结果", "No results"))
    owner.workbench_result_overview.setObjectName("workbench_result_overview")
    owner.workbench_result_overview.setWordWrap(True)
    owner.workbench_result_overview.setMinimumHeight(36)
    owner.workbench_result_overview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    layout.addWidget(owner.workbench_result_overview)

    owner.workbench_result_overview_meta = QLabel(owner._tr("等待计算", "Waiting for calculation"))
    owner.workbench_result_overview_meta.setObjectName("workbench_result_overview_meta")
    owner.workbench_result_overview_meta.setWordWrap(True)
    layout.addWidget(owner.workbench_result_overview_meta)

    summary_grid = QWidget()
    summary_grid.setObjectName("workbench_result_summary_grid")
    summary_layout = QGridLayout(summary_grid)
    summary_layout.setContentsMargins(8, 6, 8, 6)
    summary_layout.setHorizontalSpacing(10)
    summary_layout.setVerticalSpacing(2)
    owner.workbench_result_summary_rows_label = _summary_label(owner._tr("行数", "Rows"))
    owner.workbench_result_summary_rows_value = _summary_value("0")
    owner.workbench_result_summary_columns_label = _summary_label(owner._tr("列数", "Columns"))
    owner.workbench_result_summary_columns_value = _summary_value("0")
    owner.workbench_result_summary_outputs_label = _summary_label(owner._tr("输出", "Outputs"))
    owner.workbench_result_summary_outputs_value = _summary_value(owner._tr("无", "None"))
    summary_layout.addWidget(owner.workbench_result_summary_rows_label, 0, 0)
    summary_layout.addWidget(owner.workbench_result_summary_rows_value, 0, 1)
    summary_layout.addWidget(owner.workbench_result_summary_columns_label, 1, 0)
    summary_layout.addWidget(owner.workbench_result_summary_columns_value, 1, 1)
    summary_layout.addWidget(owner.workbench_result_summary_outputs_label, 2, 0)
    summary_layout.addWidget(owner.workbench_result_summary_outputs_value, 2, 1)
    summary_layout.setColumnStretch(1, 1)
    layout.addWidget(summary_grid)
    owner.workbench_result_summary_grid = summary_grid

    return widget


def _summary_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("datalab_result_summary_label", True)
    return label


def _summary_value(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("datalab_result_summary_value", True)
    label.setWordWrap(True)
    return label


def _has_plot_result(owner: Any) -> bool:
    if getattr(owner, "result_plot_bytes", None):
        return True
    if getattr(owner, "_result_plot_base_pixmap", None) is not None:
        return True
    for attr in ("current_fit_figures", "current_stats_figures", "current_error_figures", "current_extrap_figures"):
        if getattr(owner, attr, None):
            return True
    return False


def _has_text_result(owner: Any) -> bool:
    return bool(str(getattr(owner, "_last_result_rendered_text", "") or "").strip())


def _existing_file_path(value: object) -> Path | None:
    if value is None:
        return None
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return None
    if not path.name:
        return None
    try:
        return path if path.is_file() else None
    except OSError:
        return None


def _existing_figure_paths(owner: Any) -> tuple[Path, ...]:
    paths: list[Path] = []
    seen: set[str] = set()
    for attr in ("current_fit_figures", "current_stats_figures", "current_error_figures", "current_extrap_figures"):
        for value in getattr(owner, attr, None) or ():
            path = _existing_file_path(value)
            if path is None:
                continue
            try:
                key = str(path.resolve(strict=True))
            except OSError:
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
    return tuple(paths)


def _export_artifacts(owner: Any) -> tuple[ExportArtifact, ...]:
    artifacts: list[ExportArtifact] = []
    latex_path = _existing_file_path(getattr(owner, "current_latex_path", None))
    if latex_path is not None:
        artifacts.append(ExportArtifact("LaTeX", "LaTeX", latex_path.name, latex_path.name))
    pdf_path = _existing_file_path(getattr(owner, "last_pdf_path", None))
    if pdf_path is not None:
        artifacts.append(ExportArtifact("PDF", "PDF", pdf_path.name, pdf_path.name))
    figure_paths = _existing_figure_paths(owner)
    if len(figure_paths) == 1:
        artifacts.append(ExportArtifact("图片文件", "Image file", figure_paths[0].name, figure_paths[0].name))
    elif len(figure_paths) > 1:
        artifacts.append(ExportArtifact("图片文件", "Image files", f"{len(figure_paths)} 个", f"{len(figure_paths)} files"))
    return tuple(artifacts)


def _overview_state(owner: Any) -> ResultOverviewState:
    workbench_state = str(getattr(owner, "_workbench_result_state", "none") or "none")
    raw_rows = list(getattr(owner, "_csv_rows", []) or [])
    headers = tuple(str(header) for header in (getattr(owner, "_csv_headers", []) or []))
    has_plot = _has_plot_result(owner)
    has_text = _has_text_result(owner)
    export_artifacts = _export_artifacts(owner)

    if workbench_state == "failed":
        return ResultOverviewState("failed", has_plot=has_plot, has_text=has_text, export_artifacts=export_artifacts)
    if workbench_state == "running":
        return ResultOverviewState("running", has_plot=has_plot, has_text=has_text, export_artifacts=export_artifacts)
    if raw_rows or headers:
        preview_rows = tuple(dict(row) for row in raw_rows[:MAX_RESULT_OVERVIEW_STATE_ROWS] if isinstance(row, dict))
        return ResultOverviewState(
            "tabular",
            preview_rows=preview_rows,
            total_rows=len(raw_rows),
            headers=headers,
            has_plot=has_plot,
            has_text=has_text,
            export_artifacts=export_artifacts,
        )
    if has_plot and has_text:
        return ResultOverviewState("plot_text", has_plot=True, has_text=True, export_artifacts=export_artifacts)
    if has_plot:
        return ResultOverviewState("plot", has_plot=True, export_artifacts=export_artifacts)
    if has_text:
        return ResultOverviewState("text", has_text=True, export_artifacts=export_artifacts)
    if workbench_state == "complete":
        return ResultOverviewState("empty_success", export_artifacts=export_artifacts)
    return ResultOverviewState("none", export_artifacts=export_artifacts)


def _format_tabular_summary(owner: Any, total_rows: int, column_count: int, visible_count: int) -> str:
    extra_zh = f"（显示前 {visible_count} 行）" if visible_count < total_rows else ""
    row_word = "row" if total_rows == 1 else "rows"
    column_word = "column" if column_count == 1 else "columns"
    extra_en = f" (showing first {visible_count} {row_word})" if visible_count < total_rows else ""
    return owner._tr(
        f"结果数据：{total_rows} 行，{column_count} 列{extra_zh}",
        f"Result data: {total_rows} {row_word}, {column_count} {column_word}{extra_en}",
    )


def _format_result_meta(owner: Any, state: ResultOverviewState) -> str:
    if state.kind == "running":
        return owner._tr("正在计算", "In progress")
    if state.kind == "failed":
        return owner._tr("请检查日志", "Check the log")
    if state.kind == "empty_success":
        return owner._tr("已完成，无表格、图片或文本结果", "Complete with no table, plot, or text result")
    if state.kind == "none":
        return owner._tr("等待计算", "Waiting for calculation")

    parts = _artifact_parts(state)
    zh_text = "包含：" + " / ".join(part.label_zh for part in parts)
    en_text = "Includes: " + " / ".join(part.meta_en for part in parts)
    artifact_zh, artifact_en = _format_export_artifacts(state)
    if artifact_zh:
        zh_text += "；产物：" + artifact_zh
        en_text += "; Artifacts: " + artifact_en
    return owner._tr(zh_text, en_text)


def _format_export_artifacts(state: ResultOverviewState) -> tuple[str, str]:
    if not state.export_artifacts:
        return "", ""
    zh = " / ".join(f"{artifact.label_zh}：{artifact.value_zh}" for artifact in state.export_artifacts)
    en = " / ".join(f"{artifact.label_en}: {artifact.value_en}" for artifact in state.export_artifacts)
    return zh, en


def _artifact_parts(state: ResultOverviewState) -> list[ResultOutputPart]:
    parts: list[ResultOutputPart] = []
    if state.kind == "tabular":
        parts.append(ResultOutputPart("表格", "table", "Table"))
    if state.has_plot:
        parts.append(ResultOutputPart("图片", "plot", "Plot"))
    if state.has_text:
        parts.append(ResultOutputPart("文本", "text", "Text"))
    return parts


def _format_outputs_summary(owner: Any, state: ResultOverviewState) -> str:
    parts = _artifact_parts(state)
    if parts:
        return owner._tr(
            " / ".join(part.label_zh for part in parts),
            " / ".join(part.summary_en for part in parts),
        )
    if state.kind == "running":
        return owner._tr("待生成", "Pending")
    if state.kind == "failed":
        return owner._tr("未生成", "Not generated")
    return owner._tr("无", "None")


def _status_badge(owner: Any, state: ResultOverviewState) -> tuple[str, str]:
    if state.kind == "running":
        return "running", owner._tr("计算中", "Running")
    if state.kind == "failed":
        return "failed", owner._tr("失败", "Failed")
    if state.kind == "empty_success":
        return "complete", owner._tr("完成", "Complete")
    if state.kind == "none":
        return "waiting", owner._tr("等待", "Waiting")
    return "ready", owner._tr("已就绪", "Ready")


def _refresh_status_badge(owner: Any, state: ResultOverviewState) -> None:
    badge = getattr(owner, "workbench_result_status_badge", None)
    if badge is None:
        return
    status, label = _status_badge(owner, state)
    badge.setText(label)
    badge.setProperty("datalab_result_status", status)
    badge.style().unpolish(badge)
    badge.style().polish(badge)


def refresh_result_overview(owner: Any) -> None:
    state = _overview_state(owner)
    rows = list(state.preview_rows)
    headers = list(state.headers)
    visible_count = min(len(rows), MAX_RESULT_OVERVIEW_ROWS)
    if state.kind == "tabular":
        summary = _format_tabular_summary(owner, state.total_rows, len(headers), visible_count)
        if state.has_plot and state.has_text:
            owner.workbench_result_overview.setText(
                summary + owner._tr("；另有图片和文本", "; plot and text also available")
            )
        elif state.has_plot:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有图片", "; plot also available"))
        elif state.has_text:
            owner.workbench_result_overview.setText(summary + owner._tr("；另有文本", "; text also available"))
        else:
            owner.workbench_result_overview.setText(summary)
    elif state.kind == "plot_text":
        owner.workbench_result_overview.setText(
            owner._tr("结果已生成；有图片和文本；无表格数据", "Result ready; plot and text available; no tabular data")
        )
    elif state.kind == "plot":
        owner.workbench_result_overview.setText(owner._tr("结果已生成；无表格数据", "Result ready; no tabular data"))
    elif state.kind == "text":
        owner.workbench_result_overview.setText(owner._tr("文本结果已生成；无表格数据", "Text result ready; no tabular data"))
    elif state.kind == "failed":
        owner.workbench_result_overview.setText(owner._tr("计算失败", "Calculation failed"))
    elif state.kind == "running":
        owner.workbench_result_overview.setText(owner._tr("计算中", "Running"))
    elif state.kind == "empty_success":
        owner.workbench_result_overview.setText(owner._tr("计算完成；无可显示结果", "Calculation complete; no displayable result"))
    else:
        owner.workbench_result_overview.setText(owner._tr("暂无结果", "No results"))
    title = getattr(owner, "workbench_result_overview_title", None)
    if title is not None:
        title.setText(owner._tr("结果概览", "Result overview"))
    _refresh_status_badge(owner, state)
    meta = getattr(owner, "workbench_result_overview_meta", None)
    if meta is not None:
        meta.setText(_format_result_meta(owner, state))
    _refresh_summary_grid(owner, state)
    _refresh_result_details_empty_label(owner, state)


def _refresh_result_details_empty_label(owner: Any, state: ResultOverviewState) -> None:
    label = getattr(owner, "workbench_result_details_empty_label", None)
    if label is None:
        return
    is_empty = state.kind == "none"
    label.setText(owner._tr("暂无结果详情", "No result details") if is_empty else "")
    label.setVisible(is_empty)
    tabs = getattr(owner, "tabs", None)
    if tabs is not None:
        tabs.setVisible(not is_empty)
    _apply_result_subtab_policy(owner, state)


def _apply_result_subtab_policy(owner: Any, state: ResultOverviewState) -> None:
    previous_kind = getattr(owner, "_workbench_result_details_kind", None)
    # This is a caller-scoped suppression flag: workspace restore sets it only
    # inside a try/finally boundary while replaying saved UI state. Refresh code
    # observes it but does not own its lifetime.
    suppress_autoselect = bool(getattr(owner, "_suppress_result_log_autoselect", False))
    if (
        state.kind in {"running", "failed", "empty_success"}
        and previous_kind != state.kind
        and not suppress_autoselect
    ):
        _select_result_subtab(owner, "log")
    elif previous_kind == "running" and state.kind in {"tabular", "text"} and not suppress_autoselect:
        _select_result_subtab(owner, "numeric")
    elif previous_kind == "running" and state.kind in {"plot", "plot_text"} and not suppress_autoselect:
        _select_result_subtab(owner, "image")
    owner._workbench_result_details_kind = state.kind


def _select_result_subtab(owner: Any, key: str) -> None:
    result_tabs = getattr(owner, "result_tabs", None)
    indices = getattr(owner, "result_tabs_indices", {})
    index = indices.get(key) if isinstance(indices, dict) else None
    if result_tabs is not None and index is not None:
        result_tabs.setCurrentIndex(index)


def _refresh_summary_grid(owner: Any, state: ResultOverviewState) -> None:
    rows_label = getattr(owner, "workbench_result_summary_rows_label", None)
    columns_label = getattr(owner, "workbench_result_summary_columns_label", None)
    outputs_label = getattr(owner, "workbench_result_summary_outputs_label", None)
    rows_value = getattr(owner, "workbench_result_summary_rows_value", None)
    columns_value = getattr(owner, "workbench_result_summary_columns_value", None)
    outputs_value = getattr(owner, "workbench_result_summary_outputs_value", None)
    if None in (rows_label, columns_label, outputs_label, rows_value, columns_value, outputs_value):
        return
    rows_label.setText(owner._tr("行数", "Rows"))
    columns_label.setText(owner._tr("列数", "Columns"))
    outputs_label.setText(owner._tr("输出", "Outputs"))
    rows_value.setText(str(state.total_rows if state.kind == "tabular" else 0))
    columns_value.setText(str(len(state.headers) if state.kind == "tabular" else 0))
    outputs_value.setText(_format_outputs_summary(owner, state))
