from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from io import StringIO
from pathlib import Path

import mpmath as mp

from data_extrapolation_latex_latest import _dual_msg, parse_uncertainty_format
from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
from datalab_core.results import ResultStatus
from datalab_core.service_factory import create_core_session_service
from datalab_core.statistics import (
    build_multi_column_statistics_requests,
    build_statistics_result_snapshot,
    render_statistics_snapshot_outputs,
    statistics_csv_rows_from_result,
    statistics_outlier_flag_display_texts,
    statistics_output_value_unit,
    statistics_payload_to_compute_result,
    statistics_warning_display_text,
)
from datalab_core.statistics_grouped import GROUPED_RESULT_CACHE_KIND, GROUPED_WORKFLOW_MODE
from datalab_core.statistics_matrix import MATRIX_RESULT_CACHE_KIND, MATRIX_WORKFLOW_MODE
from datalab_core.statistics_time_series import (
    TIME_SERIES_RESULT_CACHE_KIND,
    TIME_SERIES_WORKFLOW_MODE,
    time_series_payload_from_snapshot,
    validate_statistics_time_series_payload,
)
from shared.unit_annotations import unit_annotation_text, unit_annotations_for_labels
from statistics_utils import (
    generate_statistics_bootstrap_latex,
    generate_statistics_hypothesis_latex,
    generate_statistics_latex,
    generate_statistics_latex_batches,
    generate_statistics_time_series_latex,
)
from datalab_latex.latex_tables_statistics_grouped import generate_statistics_grouped_latex
from datalab_latex.latex_tables_statistics_matrix import generate_statistics_matrix_latex

from .parallel_preferences import current_parallel_config_from_widgets
from .workers_core import _mp_precision_guard, _safe_read_text


def _statistics_batch_value_columns(batches: list[Mapping[str, object]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for entry in batches:
        column = str(entry.get("value_col") or "").strip()
        if not column or column in seen:
            continue
        seen.add(column)
        columns.append(column)
    return columns


def _statistics_values_from_source_rows(
    rows: list[tuple[mp.mpf, ...]],
    *,
    value_index: int,
    source_row_ids: Sequence[object],
) -> list[mp.mpf]:
    values: list[mp.mpf] = []
    for source_row_id in source_row_ids:
        row_index = int(str(source_row_id)) - 1
        cell = rows[row_index][value_index]
        values.append(cell if isinstance(cell, mp.mpf) else mp.mpf(str(cell)))
    return values


def _statistics_first_column_name(text: str, *, default: str = "") -> str:
    for item in str(text or "").split(","):
        column = item.strip()
        if column:
            return column
    return default


def _statistics_output_unit_from_snapshot(snapshot: Mapping[str, object], *keys: object) -> str:
    units = snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None
    if not isinstance(units, Mapping):
        return ""
    for key in keys:
        text = str(key or "").strip()
        if not text:
            continue
        unit = statistics_output_value_unit(units, text)
        if unit:
            return unit
    return ""


def _statistics_column_names(text: str) -> list[str]:
    return [item.strip() for item in str(text or "").split(",") if item.strip()]


def _statistics_value_unit_for_label(units: object, value_col: object) -> str:
    label = str(value_col or "").strip()
    if not isinstance(units, Mapping):
        return ""
    if label:
        input_units = unit_annotations_for_labels(units, "inputs", [label], fallback_prefix="column")
        if input_units.get(label):
            return input_units[label]
    return unit_annotation_text(units, "outputs", "mean") or unit_annotation_text(units, "outputs", "result")


def _statistics_column_values(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    column: str,
) -> tuple[list[str], list[str]]:
    if column not in headers:
        raise ValueError(f"Statistics column not found: {column}")
    index = list(headers).index(column)
    values: list[str] = []
    row_ids: list[str] = []
    for row_index, row in enumerate(rows, 1):
        values.append(str(row[index]))
        row_ids.append(str(row_index))
    return values, row_ids


def _statistics_raw_table(text: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(
            _dual_msg(
                "输入内容需要至少包含表头和一行数据。",
                "Input must include a header and at least one data row.",
            )
        )
    headers = lines[0].split()
    if not headers:
        raise ValueError(_dual_msg("表头至少需要一列。", "Header must contain at least one column."))
    rows: list[list[str]] = []
    for line_num, line in enumerate(lines[1:], 2):
        parts = line.split()
        if len(parts) != len(headers):
            raise ValueError(
                _dual_msg(
                    f"第 {line_num} 行列数与表头不匹配（期望 {len(headers)} 列，实际 {len(parts)} 列）。",
                    f"Column count mismatch on line {line_num} (expected {len(headers)}, got {len(parts)}).",
                )
            )
        rows.append(parts)
    return headers, rows


def _statistics_raw_table_preserving_cells(text: str) -> tuple[list[str], list[list[str]]]:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(
            _dual_msg(
                "输入内容需要至少包含表头和一行数据。",
                "Input must include a header and at least one data row.",
            )
        )
    delimiter = next((candidate for candidate in ("\t", ",", ";") if candidate in lines[0]), "")
    if not delimiter:
        return _statistics_raw_table(text)

    reader = csv.reader(StringIO("\n".join(lines)), delimiter=delimiter)
    table = [[cell.strip() for cell in row] for row in reader]
    if not table:
        raise ValueError(_dual_msg("表头至少需要一列。", "Header must contain at least one column."))
    headers = table[0]
    if not headers or any(not header for header in headers):
        raise ValueError(_dual_msg("表头不能包含空列名。", "Header cannot contain blank column names."))
    rows: list[list[str]] = []
    for line_num, row in enumerate(table[1:], 2):
        if len(row) != len(headers):
            raise ValueError(
                _dual_msg(
                    f"第 {line_num} 行列数与表头不匹配（期望 {len(headers)} 列，实际 {len(row)} 列）。",
                    f"Column count mismatch on line {line_num} (expected {len(headers)}, got {len(row)}).",
                )
            )
        rows.append(row)
    if not rows:
        raise ValueError(
            _dual_msg(
                "输入内容需要至少包含表头和一行数据。",
                "Input must include a header and at least one data row.",
            )
        )
    return headers, rows


def _statistics_mpf_text(value: object, precision: int) -> str:
    return mp.nstr(mp.mpf(value), max(16, int(precision)))


def _statistics_time_series_parse_numeric_token(token: str, *, lang: str, precision: int, line_num: int) -> str:
    try:
        uncertain = parse_uncertainty_format(token, lang=lang, precision=precision)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(
            _dual_msg(
                f"第 {line_num} 行存在无法解析的数字: {token} ({exc})",
                f"Cannot parse value on line {line_num}: {token} ({exc})",
            )
        ) from exc
    try:
        embedded_uncertainty = mp.mpf(uncertain.uncertainty)
    except Exception as exc:
        raise ValueError(
            _dual_msg(
                f"第 {line_num} 行包含无效不确定度: {token} ({exc})",
                f"Invalid uncertainty on line {line_num}: {token} ({exc})",
            )
        ) from exc
    if not mp.isfinite(embedded_uncertainty):
        raise ValueError(
            _dual_msg(
                f"第 {line_num} 行包含非有限不确定度: {token}",
                f"Line {line_num} contains non-finite uncertainty: {token}",
            )
        )
    if embedded_uncertainty != 0:
        raise ValueError(
            _dual_msg(
                f"第 {line_num} 行包含不支持的内嵌不确定度: {token}。时间序列目前仅支持显式不确定度列。",
                f"Line {line_num} contains unsupported embedded uncertainty: {token}. Time-series currently requires explicit sigma columns.",
            )
        )
    try:
        return _statistics_mpf_text(uncertain.value, precision)
    except Exception as exc:
        raise ValueError(
            _dual_msg(
                f"第 {line_num} 行包含无效数字: {exc}",
                f"Invalid numeric value on line {line_num}: {exc}",
            )
        ) from exc


class WindowStatisticsMixin:
    def _parallel_options_mapping(self) -> dict[str, object]:
        config_getter = getattr(self, "_current_parallel_config", None)
        config = config_getter() if callable(config_getter) else current_parallel_config_from_widgets(self)
        return {
            "mode": config.mode,
            "max_workers": config.max_workers,
            "reserve_cores": config.reserve_cores,
            "default_worker_cap": config.default_worker_cap,
            "min_process_tasks": config.min_process_tasks,
            "nested_policy": config.nested_policy,
            "process_start_method": config.process_start_method,
        }

    def _statistics_warning_texts(self, result: dict) -> list[str]:
        warnings: list[str] = []
        seen: set[str] = set()

        def _add(value: object, *, fallback: object = None) -> None:
            text = statistics_warning_display_text(value, fallback=fallback).strip()
            if not text or text in seen:
                return
            seen.add(text)
            warnings.append(text)

        raw_warnings = result.get("warnings")
        if isinstance(raw_warnings, (list, tuple)):
            for warning in raw_warnings:
                _add(warning)
        analysis_rows = result.get("analysis_rows")
        if isinstance(analysis_rows, (list, tuple)):
            for row in analysis_rows:
                if not isinstance(row, dict):
                    continue
                severity = str(row.get("severity") or "")
                key = str(row.get("key") or "")
                if severity == "warning" or key.startswith("warning."):
                    _add(row.get("value"), fallback=row.get("message_key") or key)
        return warnings

    def _append_statistics_warning_logs(self, result: dict, *, prefix: str = "") -> None:
        for warning in self._statistics_warning_texts(result):
            message = f"{prefix}{warning}" if prefix else warning
            self._append_log(message)

    def _run_statistics_mode(self, generate_latex: bool, output_path: str):
        precision = self._read_precision()
        with _mp_precision_guard(precision):
            self._set_fit_output_precision(precision)
            value_columns_text = self.stats_value_column_edit.text().strip()
            if not value_columns_text:
                raise ValueError(
                    _dual_msg(
                        "请在统计设置中指定数值列。",
                        "Please select the value column(s) in statistics settings.",
                    )
                )
            sigma_col = self.stats_sigma_column_edit.text().strip()
            workflow_mode = (
                str(self.stats_workflow_combo.currentData() or "standard")
                if hasattr(self, "stats_workflow_combo")
                else "standard"
            )
            if workflow_mode == TIME_SERIES_WORKFLOW_MODE:
                self._run_statistics_time_series_mode(
                    value_columns_text=value_columns_text,
                    precision=precision,
                    generate_latex=generate_latex,
                    output_path=output_path,
                )
                return
            if workflow_mode == MATRIX_WORKFLOW_MODE:
                self._run_statistics_matrix_mode(
                    value_columns_text=value_columns_text,
                    precision=precision,
                    generate_latex=generate_latex,
                    output_path=output_path,
                )
                return
            if workflow_mode == GROUPED_WORKFLOW_MODE:
                self._run_statistics_grouped_mode(
                    value_columns_text=value_columns_text,
                    precision=precision,
                    generate_latex=generate_latex,
                    output_path=output_path,
                    sigma_col=sigma_col,
                )
                return
            headers, rows, sigma_rows = self._collect_fitting_dataset(precision_hint=precision)
            if workflow_mode == "bootstrap_confidence_intervals":
                self._run_statistics_bootstrap_mode(
                    headers=headers,
                    rows=rows,
                    sigma_rows=sigma_rows,
                    value_columns_text=value_columns_text,
                    precision=precision,
                    generate_latex=generate_latex,
                    output_path=output_path,
                )
                return
            if workflow_mode == "hypothesis_tests":
                self._run_statistics_hypothesis_mode(
                    headers=headers,
                    rows=rows,
                    precision=precision,
                    generate_latex=generate_latex,
                    output_path=output_path,
                )
                return
            stats_units_config = self._collect_statistics_units_config()
            column_groups = build_multi_column_statistics_requests(
                headers=headers,
                rows=rows,
                sigma_rows=sigma_rows,
                value_columns=value_columns_text,
                sigma_col=sigma_col if sigma_col else None,
                stats_mode=str(self.stats_mode_combo.currentData() or "mean"),
                use_sample=self.stats_sample_checkbox.isChecked(),
                use_weighted_variance=self.stats_weight_variance_checkbox.isChecked(),
                trim_fraction=self.stats_trim_fraction_edit.text() if hasattr(self, "stats_trim_fraction_edit") else None,
                precision_digits=precision,
                uncertainty_digits=self._uncertainty_digits_value(),
                request_id_prefix="desktop-statistics",
                units=stats_units_config,
            )
            statistics_service = create_core_session_service()
            display_batches: list[dict[str, object]] = []
            for column_group in column_groups:
                for core_batch in column_group.batches:
                    envelope = statistics_service.submit(core_batch.request)
                    if envelope.status is not ResultStatus.SUCCEEDED:
                        payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
                        raise ValueError(str(payload.get("message") or "Statistics failed."))
                    result = statistics_payload_to_compute_result(envelope.payload, envelope.warnings)
                    request_sigmas = [
                        None if sigma is None else mp.mpf(str(sigma))
                        for sigma in core_batch.request.inputs["sigmas"]
                    ]
                    value_index = headers.index(column_group.value_col)
                    request_values = _statistics_values_from_source_rows(
                        rows,
                        value_index=value_index,
                        source_row_ids=core_batch.source_row_ids,
                    )
                    if len(column_group.batches) == 1:
                        batch_index = 1
                    else:
                        batch_index = core_batch.index
                    display_batches.append(
                        {
                            "index": len(display_batches) + 1,
                            "column_index": column_group.column_index,
                            "batch_index": batch_index,
                            "headers": headers,
                            "value_col": column_group.value_col,
                            "rows": rows,
                            "sigma_rows": sigma_rows,
                            "values": request_values,
                            "sigmas": request_sigmas,
                            "result": result,
                            "row_count": core_batch.row_count,
                            "source_row_ids": core_batch.source_row_ids,
                            "units": envelope.payload.get("units") if isinstance(envelope.payload, Mapping) else None,
                        }
                    )

        if not display_batches:
            raise ValueError(_dual_msg("统计列中没有数据。", "No data in the statistics column."))

        if len(display_batches) == 1:
            entry = display_batches[0]
            render_plots = bool(getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked())
            self._display_statistics_result(
                entry["result"],
                str(entry["value_col"]),
                int(entry["row_count"]),
                values=entry["values"],
                sigmas=entry["sigmas"],
                render_plots=render_plots,
                units=entry.get("units"),
            )
        else:
            value_columns = [group.value_col for group in column_groups]
            render_plots = bool(getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked())
            self._display_statistics_batches(display_batches, ", ".join(value_columns), render_plots=render_plots)

        self._append_log(self._tr("统计平均计算完成。", "Statistics completed."))
        if generate_latex and output_path:
            digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
            if len(display_batches) == 1:
                entry = display_batches[0]
                generate_statistics_latex(
                    str(entry["value_col"]),
                    rows,
                    sigma_rows,
                    entry["result"],
                    digits,
                    output_path,
                    self.dcolumn_checkbox.isChecked(),
                    uncertainty_digits=self._uncertainty_digits_value(),
                    caption=self._caption_value(),
                    latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
                    units=entry.get("units") if isinstance(entry.get("units"), Mapping) else None,
                )
            else:
                generate_statistics_latex_batches(
                    ", ".join(group.value_col for group in column_groups),
                    display_batches,
                    digits,
                    output_path,
                    self.dcolumn_checkbox.isChecked(),
                    caption=self._caption_value(),
                    uncertainty_digits=self._uncertainty_digits_value(),
                    latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
                )
            self._append_log(f"统计平均 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _run_statistics_grouped_mode(
        self,
        *,
        value_columns_text: str,
        precision: int,
        generate_latex: bool,
        output_path: str,
        sigma_col: str,
    ) -> None:
        source_text = self._statistics_source_text()
        headers, raw_rows = _statistics_raw_table_preserving_cells(source_text)
        value_columns = _statistics_column_names(value_columns_text)
        if not value_columns:
            raise ValueError(_dual_msg("请指定至少一个数值列。", "Please specify at least one value column."))
        group_column = (
            self.stats_group_column_edit.text().strip()
            if hasattr(self, "stats_group_column_edit")
            else ""
        )
        if not group_column:
            raise ValueError(_dual_msg("请指定分组列。", "Please specify the group column."))
        stats_units_config = self._collect_statistics_units_config()
        inputs: dict[str, object] = {
            "workflow_mode": GROUPED_WORKFLOW_MODE,
            "headers": tuple(headers),
            "rows": tuple(tuple(row) for row in raw_rows),
            "group_column": group_column,
            "value_columns": tuple(value_columns),
            "sigma_column": sigma_col if sigma_col else None,
            "stats_mode": str(self.stats_mode_combo.currentData() or "mean"),
            "use_sample": bool(self.stats_sample_checkbox.isChecked())
            if hasattr(self, "stats_sample_checkbox")
            else True,
            "use_weighted_variance": bool(self.stats_weight_variance_checkbox.isChecked())
            if hasattr(self, "stats_weight_variance_checkbox")
            else False,
            "trim_fraction": self.stats_trim_fraction_edit.text()
            if hasattr(self, "stats_trim_fraction_edit")
            else None,
            "source_row_ids": tuple(str(index) for index in range(1, len(raw_rows) + 1)),
        }
        if stats_units_config is not None:
            inputs["units"] = stats_units_config
        statistics_service = create_core_session_service()
        envelope = statistics_service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs=inputs,
                options=JobOptions(
                    precision_digits=precision,
                    uncertainty_digits=self._uncertainty_digits_value(),
                    parallel=self._parallel_options_mapping(),
                ),
                request_id="desktop-statistics-grouped",
            )
        )
        if envelope.status is not ResultStatus.SUCCEEDED:
            payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
            raise ValueError(str(payload.get("message") or "Grouped statistics failed."))
        payload = dict(deepcopy(envelope.payload))
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        render_plots = bool(getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked())
        if render_plots:
            figure_paths, figure_metadata = self._render_statistics_grouped_plots(payload)
        snapshot = build_statistics_result_snapshot(
            GROUPED_RESULT_CACHE_KIND,
            payload,
            plot_metadata=figure_metadata,
            precision={"compute_digits": precision, "uncertainty_digits": self._uncertainty_digits_value()},
        )
        if snapshot is None:
            raise ValueError(_dual_msg("无法生成分组统计快照。", "Could not build grouped statistics snapshot."))
        rendered = render_statistics_snapshot_outputs(snapshot)
        if rendered is None:
            raise ValueError(_dual_msg("无法渲染分组统计结果。", "Could not render grouped statistics result."))
        text, csv_rows, csv_headers = rendered
        self._set_result_text(text, final_result=True)
        self._set_csv_data(csv_rows, csv_headers, suggestion="statistics_grouped_results.csv")
        self._remember_last_result(GROUPED_RESULT_CACHE_KIND, payload)
        self._last_result_semantic_snapshot = snapshot
        self._last_result_semantic_snapshot_kind = GROUPED_RESULT_CACHE_KIND
        self._image_mode = "stats"
        if figure_paths:
            self._current_stats_plot_metadata = figure_metadata
            self._set_image_list("stats", figure_paths)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._current_stats_plot_metadata = []
            self._update_image_status()
        self._append_log(self._tr("分组统计计算完成。", "Grouped statistics completed."))
        if generate_latex and output_path:
            generate_statistics_grouped_latex(
                payload,
                output_path,
                caption_text=self._caption_value(),
                use_dcolumn=self.dcolumn_checkbox.isChecked(),
                digits=self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16,
                uncertainty_digits=self._uncertainty_digits_value(),
                latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
                units=snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None,
            )
            self._append_log(f"分组统计 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _run_statistics_matrix_mode(
        self,
        *,
        value_columns_text: str,
        precision: int,
        generate_latex: bool,
        output_path: str,
    ) -> None:
        source_text = self._statistics_source_text()
        headers, raw_rows = _statistics_raw_table_preserving_cells(source_text)
        value_columns = _statistics_column_names(value_columns_text)
        if len(value_columns) < 2:
            raise ValueError(
                _dual_msg(
                    "协方差/相关矩阵需要至少两个数值列。",
                    "Covariance/correlation matrix requires at least two value columns.",
                )
            )
        missing_policy = (
            str(self.stats_matrix_missing_policy_combo.currentData() or "listwise")
            if hasattr(self, "stats_matrix_missing_policy_combo")
            else "listwise"
        )
        stats_units_config = self._collect_statistics_units_config()
        inputs: dict[str, object] = {
            "workflow_mode": MATRIX_WORKFLOW_MODE,
            "headers": tuple(headers),
            "rows": tuple(tuple(row) for row in raw_rows),
            "value_columns": tuple(value_columns),
            "missing_policy": missing_policy,
            "use_sample": bool(self.stats_sample_checkbox.isChecked())
            if hasattr(self, "stats_sample_checkbox")
            else True,
            "source_row_ids": tuple(str(index) for index in range(1, len(raw_rows) + 1)),
        }
        if stats_units_config is not None:
            inputs["units"] = stats_units_config
        statistics_service = create_core_session_service()
        envelope = statistics_service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs=inputs,
                options=JobOptions(
                    precision_digits=precision,
                    uncertainty_digits=self._uncertainty_digits_value(),
                    parallel=self._parallel_options_mapping(),
                ),
                request_id="desktop-statistics-matrix",
            )
        )
        if envelope.status is not ResultStatus.SUCCEEDED:
            payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
            raise ValueError(str(payload.get("message") or "Covariance/correlation matrix failed."))
        payload = dict(deepcopy(envelope.payload))
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        render_plots = bool(getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked())
        if render_plots:
            figure_paths, figure_metadata = self._render_statistics_matrix_plots(payload)
        snapshot = build_statistics_result_snapshot(
            MATRIX_RESULT_CACHE_KIND,
            payload,
            plot_metadata=figure_metadata,
            precision={"compute_digits": precision, "uncertainty_digits": self._uncertainty_digits_value()},
        )
        if snapshot is None:
            raise ValueError(_dual_msg("无法生成矩阵统计快照。", "Could not build matrix statistics snapshot."))
        rendered = render_statistics_snapshot_outputs(snapshot)
        if rendered is None:
            raise ValueError(_dual_msg("无法渲染矩阵统计结果。", "Could not render matrix statistics result."))
        text, csv_rows, csv_headers = rendered
        self._set_result_text(text, final_result=True)
        self._set_csv_data(csv_rows, csv_headers, suggestion="statistics_matrix_results.csv")
        self._remember_last_result(MATRIX_RESULT_CACHE_KIND, payload)
        self._last_result_semantic_snapshot = snapshot
        self._last_result_semantic_snapshot_kind = MATRIX_RESULT_CACHE_KIND
        self._image_mode = "stats"
        if figure_paths:
            self._current_stats_plot_metadata = figure_metadata
            self._set_image_list("stats", figure_paths)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._current_stats_plot_metadata = []
            self._update_image_status()
        self._append_log(self._tr("协方差/相关矩阵计算完成。", "Covariance/correlation matrix completed."))
        if generate_latex and output_path:
            generate_statistics_matrix_latex(
                payload,
                output_path,
                caption_text=self._caption_value(),
                use_dcolumn=self.dcolumn_checkbox.isChecked(),
                latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
                units=snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None,
            )
            self._append_log(f"协方差/相关矩阵 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _render_statistics_grouped_plots(
        self,
        payload: Mapping[str, object],
    ) -> tuple[list[Path], list[dict[str, object]]]:
        try:
            from datalab_core.statistics_grouped import statistics_grouped_mean_overview_spec_from_payload
            from shared.plotting import render_statistics_grouped_mean_overview_from_spec
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"分组统计图不可用: {exc}", f"Grouped statistics plot unavailable: {exc}"))
            return [], []
        spec = statistics_grouped_mean_overview_spec_from_payload(payload)
        if spec is None:
            self._append_log(
                self._tr(
                    "分组统计缺少可绘制的均值，已跳过概览图。",
                    "Grouped statistics has no plottable means; overview plot skipped.",
                )
            )
            return [], []
        plot_bytes = render_statistics_grouped_mean_overview_from_spec(spec)
        if plot_bytes is None:
            return [], []
        img_path = self._save_batch_figure(plot_bytes, "", 1, prefix="stats_grouped_mean")
        if img_path is None:
            return [], []
        metadata = [
            {
                "role": "statistics_grouped",
                "batch": 1,
                "plot_index": 1,
                "plot_key": spec.plot_key,
                "title": spec.plot_labels.title,
            }
        ]
        return [img_path], metadata

    def _render_statistics_matrix_plots(
        self,
        payload: Mapping[str, object],
    ) -> tuple[list[Path], list[dict[str, object]]]:
        try:
            from shared.plotting import (
                render_correlation_heatmap_from_spec,
                statistics_matrix_correlation_heatmap_spec_from_payload,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"矩阵统计图不可用: {exc}", f"Matrix statistics plot unavailable: {exc}"))
            return [], []
        spec = statistics_matrix_correlation_heatmap_spec_from_payload(
            payload,
            title=self._tr("相关矩阵", "Correlation Matrix"),
        )
        if spec is None:
            self._append_log(
                self._tr(
                    "相关矩阵包含空值或无效值，已跳过热图。",
                    "Correlation matrix has null or invalid cells; heatmap skipped.",
                )
            )
            return [], []
        plot_bytes = render_correlation_heatmap_from_spec(spec)
        if plot_bytes is None:
            return [], []
        img_path = self._save_batch_figure(plot_bytes, "", 1, prefix="stats_matrix_correlation")
        if img_path is None:
            return [], []
        metadata = [
            {
                "role": "statistics",
                "columns": list(spec.names),
                "batch": 1,
                "plot_index": 1,
                "plot_key": spec.plot_key,
                "title": spec.title,
            }
        ]
        return [img_path], metadata

    def _run_statistics_time_series_mode(
        self,
        *,
        value_columns_text: str,
        precision: int,
        generate_latex: bool,
        output_path: str,
    ) -> None:
        source_text = self._statistics_source_text()
        headers, raw_rows = _statistics_raw_table_preserving_cells(source_text)
        value_columns = _statistics_column_names(value_columns_text)
        if not value_columns:
            raise ValueError(_dual_msg("请指定至少一个数值列。", "Please specify at least one value column."))
        header_index = {header: index for index, header in enumerate(headers)}
        missing_columns = [column for column in value_columns if column not in header_index]
        if missing_columns:
            raise ValueError(
                _dual_msg(
                    f"找不到时间序列数值列: {', '.join(missing_columns)}",
                    f"Time-series value column(s) not found: {', '.join(missing_columns)}",
                )
            )
        method = (
            str(self.stats_time_series_method_combo.currentData() or "rolling_mean")
            if hasattr(self, "stats_time_series_method_combo")
            else "rolling_mean"
        )
        sigma_columns = self._statistics_time_series_sigma_columns(value_columns) if method == "rolling_mean" else {}
        missing_sigma_columns = [column for column in sigma_columns.values() if column not in header_index]
        if missing_sigma_columns:
            raise ValueError(
                _dual_msg(
                    f"找不到时间序列不确定度列: {', '.join(missing_sigma_columns)}",
                    f"Time-series sigma column(s) not found: {', '.join(missing_sigma_columns)}",
                )
            )
        time_column = (
            self.stats_time_series_time_column_edit.text().strip()
            if hasattr(self, "stats_time_series_time_column_edit")
            else ""
        )
        if time_column and time_column not in header_index:
            raise ValueError(
                _dual_msg(
                    f"找不到时间/索引列: {time_column}",
                    f"Time/index column not found: {time_column}",
                )
            )
        lang = "en" if self._is_en() else "zh"
        source_row_ids = [str(index) for index in range(1, len(raw_rows) + 1)]
        time_labels = [row[header_index[time_column]] for row in raw_rows] if time_column else []
        statistics_service = create_core_session_service()
        columns: list[object] = []
        combined_payload: dict[str, object] | None = None
        diagnostics: list[object] = []
        diagnostics_seen: set[str] = set()
        combined_sigma_columns: dict[str, object] = {}
        combined_uncertainty_assumptions: dict[str, object] = {}
        stats_units_config = self._collect_statistics_units_config()
        for column_index, value_column in enumerate(value_columns, 1):
            value_index = header_index[value_column]
            values = [
                _statistics_time_series_parse_numeric_token(
                    row[value_index],
                    lang=lang,
                    precision=precision,
                    line_num=row_index,
                )
                for row_index, row in enumerate(raw_rows, 2)
            ]
            inputs: dict[str, object] = {
                "workflow_mode": TIME_SERIES_WORKFLOW_MODE,
                "series_method": method,
                "values": tuple(values),
                "source_row_ids": tuple(source_row_ids),
                "value_column": value_column,
                "column_index": column_index,
                "time_column": time_column,
            }
            if stats_units_config is not None:
                inputs["units"] = stats_units_config
            if time_labels:
                inputs["time_labels"] = tuple(time_labels)
            sigma_column = sigma_columns.get(value_column)
            if sigma_column:
                sigma_index = header_index[sigma_column]
                sigmas: list[str] = []
                for row_index, row in enumerate(raw_rows, 2):
                    sigma_text = _statistics_time_series_parse_numeric_token(
                        row[sigma_index],
                        lang=lang,
                        precision=precision,
                        line_num=row_index,
                    )
                    sigma_value = mp.mpf(sigma_text)
                    if sigma_value < 0:
                        raise ValueError(
                            _dual_msg(
                                f"第 {row_index} 行包含负不确定度: {row[sigma_index]}",
                                f"Negative uncertainty on line {row_index}: {row[sigma_index]}",
                            )
                        )
                    sigmas.append(sigma_text)
                inputs["sigmas"] = tuple(sigmas)
                inputs["sigma_column"] = sigma_column
            if method == "ewma":
                parameter = (
                    str(self.stats_time_series_ewma_parameter_combo.currentData() or "alpha")
                    if hasattr(self, "stats_time_series_ewma_parameter_combo")
                    else "alpha"
                )
                parameter_value = (
                    self.stats_time_series_ewma_value_edit.text().strip()
                    if hasattr(self, "stats_time_series_ewma_value_edit")
                    else ""
                )
                inputs[parameter] = parameter_value or ("0.5" if parameter == "alpha" else "3")
                inputs["adjust"] = (
                    bool(self.stats_time_series_ewma_adjust_checkbox.isChecked())
                    if hasattr(self, "stats_time_series_ewma_adjust_checkbox")
                    else False
                )
            else:
                window_size = (
                    int(self.stats_time_series_window_size_spin.value())
                    if hasattr(self, "stats_time_series_window_size_spin")
                    else 3
                )
                min_periods = (
                    int(self.stats_time_series_min_periods_spin.value())
                    if hasattr(self, "stats_time_series_min_periods_spin")
                    else window_size
                )
                inputs["window_size"] = window_size
                inputs["min_periods"] = min_periods
                inputs["alignment"] = (
                    str(self.stats_time_series_alignment_combo.currentData() or "right")
                    if hasattr(self, "stats_time_series_alignment_combo")
                    else "right"
                )
                if method == "rolling_std":
                    inputs["denominator"] = (
                        str(self.stats_time_series_denominator_combo.currentData() or "sample")
                        if hasattr(self, "stats_time_series_denominator_combo")
                        else "sample"
                    )
            envelope = statistics_service.submit(
                ComputeJobRequest(
                    mode=JobMode.STATISTICS,
                    inputs=inputs,
                    options=JobOptions(
                        precision_digits=precision,
                        uncertainty_digits=self._uncertainty_digits_value(),
                        parallel=self._parallel_options_mapping(),
                    ),
                    request_id=f"desktop-statistics-time-series-c{column_index}",
                )
            )
            if envelope.status is not ResultStatus.SUCCEEDED:
                payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
                raise ValueError(str(payload.get("message") or "Time-series statistics failed."))
            payload = dict(deepcopy(envelope.payload))
            if combined_payload is None:
                combined_payload = payload
            payload_columns = payload.get("columns")
            if isinstance(payload_columns, Sequence) and not isinstance(payload_columns, (str, bytes, bytearray)):
                columns.extend(deepcopy(list(payload_columns)))
            if isinstance(payload.get("sigma_columns"), Mapping):
                combined_sigma_columns.update(dict(payload["sigma_columns"]))
            if isinstance(payload.get("uncertainty_assumptions"), Mapping):
                combined_uncertainty_assumptions.update(dict(payload["uncertainty_assumptions"]))
            raw_diagnostics = payload.get("diagnostics")
            if isinstance(raw_diagnostics, Sequence) and not isinstance(raw_diagnostics, (str, bytes, bytearray)):
                for diagnostic in raw_diagnostics:
                    marker = repr(diagnostic)
                    if marker in diagnostics_seen:
                        continue
                    diagnostics_seen.add(marker)
                    diagnostics.append(deepcopy(diagnostic))
        if combined_payload is None or not columns:
            raise ValueError(_dual_msg("统计列中没有数据。", "No data in the statistics column."))
        combined_payload["columns"] = columns
        combined_payload["value_columns"] = value_columns
        combined_payload["sigma_columns"] = combined_sigma_columns
        combined_payload["uncertainty_assumptions"] = combined_uncertainty_assumptions
        combined_payload["diagnostics"] = diagnostics
        validate_statistics_time_series_payload(combined_payload)
        snapshot = build_statistics_result_snapshot(
            TIME_SERIES_RESULT_CACHE_KIND,
            combined_payload,
            precision={"compute_digits": precision, "uncertainty_digits": self._uncertainty_digits_value()},
        )
        if snapshot is None:
            raise ValueError(_dual_msg("无法生成时间序列统计快照。", "Could not build time-series statistics snapshot."))
        rendered = render_statistics_snapshot_outputs(snapshot)
        if rendered is None:
            raise ValueError(_dual_msg("无法渲染时间序列统计结果。", "Could not render time-series statistics result."))
        text, csv_rows, csv_headers = rendered
        self._set_result_text(text, final_result=True)
        self._set_csv_data(csv_rows, csv_headers, suggestion="statistics_time_series_results.csv")
        self._remember_last_result(TIME_SERIES_RESULT_CACHE_KIND, combined_payload)
        self._last_result_semantic_snapshot = snapshot
        self._last_result_semantic_snapshot_kind = TIME_SERIES_RESULT_CACHE_KIND
        render_plots = bool(getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked())
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        if render_plots:
            figure_paths, figure_metadata = self._render_statistics_time_series_plots(snapshot)
        self._image_mode = "stats"
        if figure_paths:
            self._current_stats_plot_metadata = figure_metadata
            self._set_image_list("stats", figure_paths)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._current_stats_plot_metadata = []
            self._update_image_status()
        self._append_log(self._tr("时间序列统计计算完成。", "Time-series statistics completed."))
        if generate_latex and output_path:
            digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
            generate_statistics_time_series_latex(
                snapshot,
                output_path,
                self.dcolumn_checkbox.isChecked(),
                digits,
                caption=self._caption_value(),
                uncertainty_digits=self._uncertainty_digits_value(),
                latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
            )
            self._append_log(f"时间序列统计 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _render_statistics_time_series_plots(
        self,
        snapshot: Mapping[str, object],
    ) -> tuple[list[Path], list[dict[str, object]]]:
        try:
            from shared.plotting import (
                plot_label_with_unit,
                render_statistics_time_series_plot_from_spec,
                statistics_time_series_plot_specs_from_payload,
                StatisticsTimeSeriesPlotLabels,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"时间序列统计图不可用: {exc}", f"Time-series statistics plot unavailable: {exc}"))
            return [], []
        try:
            payload = time_series_payload_from_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"时间序列统计图载荷无效: {exc}", f"Invalid time-series plot payload: {exc}"))
            return [], []
        specs = statistics_time_series_plot_specs_from_payload(
            payload,
            StatisticsTimeSeriesPlotLabels(
                observed=self._tr("观测值", "Observed"),
                result=self._tr("滚动/平滑结果", "Rolling / smoothed"),
                uncertainty_band=self._tr("不确定度带", "Uncertainty band"),
                x_axis=self._tr("时间/索引", "Time / index"),
                y_axis=self._tr("数值", "Value"),
                title=self._tr("时间序列统计", "Time-series statistics"),
            ),
        )
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        for plot_index, spec in enumerate(specs, 1):
            value_unit = _statistics_output_unit_from_snapshot(
                snapshot,
                spec.column,
                "series",
                "smoothed",
                "result",
            )
            if value_unit:
                spec = replace(
                    spec,
                    labels=replace(
                        spec.labels,
                        y_axis=plot_label_with_unit(spec.labels.y_axis, value_unit),
                    ),
                )
            plot_bytes = render_statistics_time_series_plot_from_spec(spec)
            img_path = self._save_batch_figure(plot_bytes, "", plot_index, prefix="stats_time_series")
            if img_path is None:
                continue
            figure_paths.append(img_path)
            figure_metadata.append(
                {
                    "role": "statistics_time_series",
                    "column": spec.column,
                    "batch": plot_index,
                    "plot_index": plot_index,
                    "plot_key": spec.plot_key,
                    "title": f"{spec.column} time-series statistics",
                }
            )
        return figure_paths, figure_metadata

    def _statistics_time_series_source_text(self) -> str:
        return self._statistics_source_text()

    def _statistics_source_text(self) -> str:
        data_path, manual_content = self._active_data_source()
        if data_path:
            if not data_path.exists():
                raise ValueError(_dual_msg("请选择有效的数据文件路径。", "Please select a valid data file path."))
            return _safe_read_text(data_path)
        if manual_content:
            return manual_content
        raise ValueError(_dual_msg("没有可用于统计的数据。", "No data available for statistics."))

    def _statistics_time_series_sigma_columns(self, value_columns: Sequence[str]) -> dict[str, str]:
        sigma_text = self.stats_sigma_column_edit.text().strip() if hasattr(self, "stats_sigma_column_edit") else ""
        sigma_columns = _statistics_column_names(sigma_text)
        if not sigma_columns:
            return {}
        if len(sigma_columns) != len(value_columns):
            raise ValueError(
                _dual_msg(
                    "时间序列多列计算需要为每个数值列填写一个对应的不确定度列。",
                    "Time-series multi-column runs require one sigma column for each value column.",
                )
            )
        return dict(zip(value_columns, sigma_columns, strict=True))

    def _run_statistics_hypothesis_mode(
        self,
        *,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        precision: int,
        generate_latex: bool,
        output_path: str,
    ) -> None:
        value_column = _statistics_first_column_name(
            self.stats_value_column_edit.text() if hasattr(self, "stats_value_column_edit") else "",
            default="A",
        )
        values, source_row_ids = _statistics_column_values(headers, rows, value_column)
        test_kind = (
            str(self.stats_hypothesis_test_combo.currentData() or "one_sample_t")
            if hasattr(self, "stats_hypothesis_test_combo")
            else "one_sample_t"
        )
        alternative = (
            str(self.stats_hypothesis_alternative_combo.currentData() or "two_sided")
            if hasattr(self, "stats_hypothesis_alternative_combo")
            else "two_sided"
        )
        alpha_text = self.stats_hypothesis_alpha_edit.text().strip() if hasattr(self, "stats_hypothesis_alpha_edit") else ""
        null_text = self.stats_hypothesis_null_edit.text().strip() if hasattr(self, "stats_hypothesis_null_edit") else ""
        inputs: dict[str, object] = {
            "workflow_mode": "hypothesis_tests",
            "test_kind": test_kind,
            "values": tuple(values),
            "source_row_ids": tuple(source_row_ids),
            "value_column": value_column,
            "alpha": alpha_text or "0.05",
        }
        stats_units_config = self._collect_statistics_units_config()
        if stats_units_config is not None:
            inputs["units"] = stats_units_config
        if test_kind != "chi_square_gof":
            inputs["alternative"] = alternative
        if test_kind == "one_sample_t":
            inputs["mu0"] = null_text or "0"
        elif test_kind == "sign_test":
            inputs["m0"] = null_text or "0"
            inputs["sign_mode"] = "one_sample"
        elif test_kind in {"paired_t", "welch_t"}:
            inputs["delta0"] = null_text or "0"
            second_column = _statistics_first_column_name(
                self.stats_hypothesis_b_column_edit.text()
                if hasattr(self, "stats_hypothesis_b_column_edit")
                else "",
                default="B",
            )
            second_values, second_source_row_ids = _statistics_column_values(headers, rows, second_column)
            inputs["value_column_b"] = second_column
            inputs["source_row_ids_b"] = tuple(second_source_row_ids)
            if test_kind == "paired_t":
                inputs["paired_values"] = tuple(second_values)
            else:
                inputs["values_b"] = tuple(second_values)
        elif test_kind == "chi_square_gof":
            second_column = _statistics_first_column_name(
                self.stats_hypothesis_b_column_edit.text()
                if hasattr(self, "stats_hypothesis_b_column_edit")
                else "",
                default="B",
            )
            expected_values, _expected_source_row_ids = _statistics_column_values(headers, rows, second_column)
            expected_source = (
                str(self.stats_hypothesis_expected_source_combo.currentData() or "counts")
                if hasattr(self, "stats_hypothesis_expected_source_combo")
                else "counts"
            )
            inputs["expected_column"] = second_column
            inputs["fitted_parameter_count"] = (
                int(self.stats_hypothesis_fitted_parameters_spin.value())
                if hasattr(self, "stats_hypothesis_fitted_parameters_spin")
                else 0
            )
            if expected_source == "probabilities":
                inputs["expected_probabilities"] = tuple(expected_values)
            else:
                inputs["expected_counts"] = tuple(expected_values)
        statistics_service = create_core_session_service()
        envelope = statistics_service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs=inputs,
                options=JobOptions(
                    precision_digits=precision,
                    uncertainty_digits=self._uncertainty_digits_value(),
                    parallel=self._parallel_options_mapping(),
                ),
                request_id="desktop-statistics-hypothesis",
            )
        )
        if envelope.status is not ResultStatus.SUCCEEDED:
            payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
            raise ValueError(str(payload.get("message") or "Hypothesis test failed."))
        payload = dict(deepcopy(envelope.payload))
        snapshot = build_statistics_result_snapshot(
            "statistics_hypothesis_test",
            payload,
            precision={"compute_digits": precision, "uncertainty_digits": self._uncertainty_digits_value()},
        )
        if snapshot is None:
            raise ValueError(_dual_msg("无法生成假设检验快照。", "Could not build hypothesis-test snapshot."))
        rendered = render_statistics_snapshot_outputs(snapshot)
        if rendered is None:
            raise ValueError(_dual_msg("无法渲染假设检验结果。", "Could not render hypothesis-test result."))
        text, csv_rows, csv_headers = rendered
        self._set_result_text(text, final_result=True)
        self._set_csv_data(csv_rows, csv_headers, suggestion="statistics_hypothesis_results.csv")
        self._remember_last_result("statistics_hypothesis_test", payload)
        self._last_result_semantic_snapshot = snapshot
        self._last_result_semantic_snapshot_kind = "statistics_hypothesis_test"
        self._image_mode = "stats"
        self._result_plot_base_pixmap = None
        self.result_plot_bytes = None
        self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
        self.current_stats_figures = []
        self.current_stats_index = 0
        self._current_stats_plot_metadata = []
        self._update_image_status()
        self._append_log(self._tr("假设检验完成。", "Hypothesis test completed."))
        if generate_latex and output_path:
            digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
            generate_statistics_hypothesis_latex(
                snapshot,
                output_path,
                self.dcolumn_checkbox.isChecked(),
                digits,
                caption=self._caption_value(),
                uncertainty_digits=self._uncertainty_digits_value(),
                latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
            )
            self._append_log(f"假设检验 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _run_statistics_bootstrap_mode(
        self,
        *,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        sigma_rows: Sequence[Sequence[object | None]] | None,
        value_columns_text: str,
        precision: int,
        generate_latex: bool,
        output_path: str,
    ) -> None:
        column_groups = build_multi_column_statistics_requests(
            headers=headers,
            rows=rows,
            sigma_rows=sigma_rows,
            value_columns=value_columns_text,
            sigma_col=None,
            stats_mode="mean",
            use_sample=self.stats_sample_checkbox.isChecked(),
            use_weighted_variance=False,
            trim_fraction=None,
            precision_digits=precision,
            uncertainty_digits=self._uncertainty_digits_value(),
            request_id_prefix="desktop-statistics-bootstrap",
        )
        target = (
            str(self.stats_bootstrap_target_combo.currentData() or "mean")
            if hasattr(self, "stats_bootstrap_target_combo")
            else "mean"
        )
        resample_count = (
            int(self.stats_bootstrap_resamples_spin.value())
            if hasattr(self, "stats_bootstrap_resamples_spin")
            else 2000
        )
        seed_text = self.stats_bootstrap_seed_edit.text().strip() if hasattr(self, "stats_bootstrap_seed_edit") else ""
        seed: int | None = int(seed_text) if seed_text else None
        trim_fraction = self.stats_trim_fraction_edit.text().strip() if hasattr(self, "stats_trim_fraction_edit") else ""
        sample_mode = "sample" if self.stats_sample_checkbox.isChecked() else "population"
        stats_units_config = self._collect_statistics_units_config()
        statistics_service = create_core_session_service()
        combined_payload: dict[str, object] | None = None
        columns: list[object] = []
        for column_group in column_groups:
            for core_batch in column_group.batches:
                inputs: dict[str, object] = {
                    "workflow_mode": "bootstrap_confidence_intervals",
                    "values": tuple(core_batch.request.inputs["values"]),
                    "source_row_ids": tuple(core_batch.source_row_ids),
                    "value_column": column_group.value_col,
                    "column_index": column_group.column_index,
                    "target_statistic": target,
                    "confidence_level": "0.95",
                    "resample_count": resample_count,
                    "sample_mode": sample_mode,
                }
                if stats_units_config is not None:
                    inputs["units"] = stats_units_config
                if seed is not None:
                    inputs["seed"] = seed
                if target == "trimmed_mean" and trim_fraction:
                    inputs["trim_fraction"] = trim_fraction
                envelope = statistics_service.submit(
                    ComputeJobRequest(
                        mode=JobMode.STATISTICS,
                        inputs=inputs,
                        options=JobOptions(
                            precision_digits=precision,
                            uncertainty_digits=self._uncertainty_digits_value(),
                            parallel=self._parallel_options_mapping(),
                        ),
                        request_id=f"desktop-statistics-bootstrap-c{column_group.column_index}-b{core_batch.index}",
                    )
                )
                if envelope.status is not ResultStatus.SUCCEEDED:
                    payload = envelope.payload if isinstance(envelope.payload, Mapping) else {}
                    raise ValueError(str(payload.get("message") or "Bootstrap statistics failed."))
                payload = dict(deepcopy(envelope.payload))
                if combined_payload is None:
                    combined_payload = payload
                payload_columns = payload.get("columns")
                if isinstance(payload_columns, Sequence) and not isinstance(payload_columns, (str, bytes, bytearray)):
                    columns.extend(deepcopy(list(payload_columns)))
        if combined_payload is None or not columns:
            raise ValueError(_dual_msg("统计列中没有数据。", "No data in the statistics column."))
        combined_payload["columns"] = columns
        snapshot = build_statistics_result_snapshot(
            "statistics_bootstrap",
            combined_payload,
            precision={"compute_digits": precision, "uncertainty_digits": self._uncertainty_digits_value()},
        )
        if snapshot is None:
            raise ValueError(_dual_msg("无法生成 Bootstrap 统计快照。", "Could not build bootstrap statistics snapshot."))
        rendered = render_statistics_snapshot_outputs(snapshot)
        if rendered is None:
            raise ValueError(_dual_msg("无法渲染 Bootstrap 统计结果。", "Could not render bootstrap statistics result."))
        text, csv_rows, csv_headers = rendered
        self._set_result_text(text, final_result=True)
        self._set_csv_data(csv_rows, csv_headers, suggestion="statistics_bootstrap_results.csv")
        self._remember_last_result("statistics_bootstrap", combined_payload)
        self._last_result_semantic_snapshot = snapshot
        self._last_result_semantic_snapshot_kind = "statistics_bootstrap"
        render_plots = bool(getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked())
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        if render_plots:
            figure_paths, figure_metadata = self._render_statistics_bootstrap_distribution_plots(snapshot)
        self._image_mode = "stats"
        if figure_paths:
            self._current_stats_plot_metadata = figure_metadata
            self._set_image_list("stats", figure_paths)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._current_stats_plot_metadata = []
            self._update_image_status()
        self._append_log(self._tr("Bootstrap 统计计算完成。", "Bootstrap statistics completed."))
        if generate_latex and output_path:
            digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
            generate_statistics_bootstrap_latex(
                snapshot,
                output_path,
                self.dcolumn_checkbox.isChecked(),
                digits,
                caption=self._caption_value(),
                uncertainty_digits=self._uncertainty_digits_value(),
                latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
            )
            self._append_log(f"Bootstrap 统计 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _render_statistics_bootstrap_distribution_plots(
        self,
        snapshot: Mapping[str, object],
    ) -> tuple[list[Path], list[dict[str, object]]]:
        try:
            from shared.plotting import (
                MonteCarloDistributionPlotLabels,
                monte_carlo_distribution_plot_spec_from_summary,
                plot_label_with_unit,
                render_monte_carlo_distribution_plot_from_spec,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"Bootstrap 分布图不可用: {exc}", f"Bootstrap distribution plot unavailable: {exc}"))
            return [], []

        bootstrap = snapshot.get("bootstrap") if isinstance(snapshot.get("bootstrap"), Mapping) else {}
        columns = bootstrap.get("columns") if isinstance(bootstrap, Mapping) else ()
        if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray)):
            return [], []
        target_statistic = str(bootstrap.get("target_statistic") or "") if isinstance(bootstrap, Mapping) else ""
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        for index, column in enumerate(columns, 1):
            if not isinstance(column, Mapping):
                continue
            distribution = column.get("distribution")
            if not isinstance(distribution, Mapping):
                continue
            value_col = str(column.get("value_column") or f"Column {index}")
            value_unit = _statistics_output_unit_from_snapshot(
                snapshot,
                str(column.get("value_column") or ""),
                target_statistic,
                "result",
            )
            labels = MonteCarloDistributionPlotLabels(
                title=self._tr("Bootstrap 分布", "Bootstrap distribution"),
                x_axis=plot_label_with_unit(self._tr("统计量值", "Statistic value"), value_unit),
                y_axis=self._tr("重采样次数", "Resample count"),
            )
            spec = monte_carlo_distribution_plot_spec_from_summary(
                distribution,
                labels,
                title_suffix=value_col,
            )
            if spec is None:
                continue
            plot_bytes = render_monte_carlo_distribution_plot_from_spec(spec)
            img_path = self._save_batch_figure(plot_bytes, "", index, prefix="stats_bootstrap_distribution")
            if img_path is None:
                continue
            figure_paths.append(img_path)
            figure_metadata.append(
                {
                    "role": "statistics_bootstrap",
                    "column": value_col,
                    "batch": index,
                    "plot_index": 1,
                    "plot_key": "statistics.bootstrap_distribution",
                    "title": f"{value_col} bootstrap distribution",
                }
            )
        return figure_paths, figure_metadata

    def _build_stats_csv_rows(
        self,
        result: dict,
        batch_idx: int | None = None,
        row_count: int | None = None,
        units: Mapping[str, object] | None = None,
    ) -> list[dict[str, object]]:
        return statistics_csv_rows_from_result(
            result,
            row_count=row_count,
            batch=batch_idx if batch_idx is not None else 1,
            include_batch=True,
            units=units,
        )

    def _render_statistics_text(
        self,
        result: dict,
        value_col: str,
        n: int,
        units: Mapping[str, object] | None = None,
    ) -> str:
        mean = result.get("mean", mp.nan)
        std_mean = result.get("std_mean", mp.nan)
        std = result.get("std", mp.nan)
        v_min = result.get("v_min", mp.nan)
        v_max = result.get("v_max", mp.nan)
        method_label = result.get("method_label", "")
        eff_n = result.get("effective_n", None)
        show_eff_n = eff_n is not None and "Weighted" in str(method_label)

        def _fmt_plain(val: mp.mpf) -> str:
            return self._format_display_value(val)

        mean_str = f"{self._format_display_value(mean)} ± {self._format_display_value(std_mean)}"
        unit_text = _statistics_value_unit_for_label(units, value_col)
        lines = [
            self._tr("=== 统计平均结果 ===", "=== Statistics ==="),
            self._tr(f"模式: {method_label}", f"Mode: {method_label}"),
            self._tr(f"数据点数 n = {n}", f"Data points n = {n}"),
            self._tr(f"列名: {value_col}", f"Column: {value_col}"),
        ]
        if unit_text:
            lines.append(self._tr(f"单位: {unit_text}", f"Unit: {unit_text}"))
        lines.extend(
            [
                "",
                self._tr(f"平均值 (带标准误差): {mean_str}", f"Mean (with SE): {mean_str}"),
                self._tr(f"平均值 = { _fmt_plain(mean)}", f"Mean = { _fmt_plain(mean)}"),
            ]
        )
        lines.append(
            self._tr(
                f"标准误差 σ_mean = { _fmt_plain(std_mean)}",
                f"Std. error σ_mean = { _fmt_plain(std_mean)}",
            )
        )
        for key, zh_label, en_label in (
            ("mean_ci_lower", "均值 95% CI 下限", "Mean 95% CI lower"),
            ("mean_ci_upper", "均值 95% CI 上限", "Mean 95% CI upper"),
            ("mean_ci_margin", "均值 95% CI 半宽", "Mean 95% CI margin"),
            ("mean_sample_se_for_ci", "CI 样本标准误差", "CI sample SE"),
            ("weighted_se_known_sigma", "已知 σ 加权 CI 标准误差", "Known-sigma weighted CI SE"),
            ("mean_ci_dof", "CI 自由度", "CI dof"),
            ("mean_ci_critical_value", "CI 临界值", "CI critical value"),
        ):
            value = result.get(key)
            if value is None:
                continue
            lines.append(self._tr(f"{zh_label} = { _fmt_plain(value)}", f"{en_label} = { _fmt_plain(value)}"))
        ci_method = str(result.get("mean_ci_method_label") or "").strip()
        if ci_method:
            lines.append(self._tr(f"CI 方法 = {ci_method}", f"CI method = {ci_method}"))
        if show_eff_n:
            lines.append(
                self._tr(
                    f"加权有效点数 n_eff = { _fmt_plain(eff_n)}",
                    f"Weighted effective n_eff = { _fmt_plain(eff_n)}",
                )
            )
        for key, zh_label, en_label in (
            ("weighted_chi_square", "加权均值 χ²", "Weighted mean chi-square"),
            ("weighted_consistency_dof", "加权一致性自由度", "Weighted consistency dof"),
            ("weighted_reduced_chi_square", "加权约化 χ²", "Weighted reduced chi-square"),
            ("birge_ratio", "Birge 比率", "Birge ratio"),
        ):
            value = result.get(key)
            if value is None:
                continue
            try:
                numeric = mp.mpf(value)
                if mp.isnan(numeric) or mp.isinf(numeric):
                    continue
            except Exception:
                pass
            lines.append(self._tr(f"{zh_label} = { _fmt_plain(value)}", f"{en_label} = { _fmt_plain(value)}"))
        if not mp.isnan(std):
            lines.append(
                self._tr(
                    f"标准差 σ = { _fmt_plain(std)}",
                    f"Std. dev. σ = { _fmt_plain(std)}",
                )
            )
        for key, zh_label, en_label in (
            ("trimmed_mean", "修剪均值", "Trimmed mean"),
            ("variance", "方差", "Variance"),
            ("median", "中位数", "Median"),
            ("q1", "第一四分位数 Q1", "Q1"),
            ("q3", "第三四分位数 Q3", "Q3"),
            ("iqr", "四分位距 IQR", "IQR"),
            ("mad", "中位数绝对偏差 MAD", "MAD"),
            ("skewness", "偏度", "Skewness"),
            ("excess_kurtosis", "超额峰度", "Excess kurtosis"),
        ):
            value = result.get(key)
            if value is None:
                continue
            try:
                if mp.isnan(mp.mpf(value)) or mp.isinf(mp.mpf(value)):
                    continue
            except Exception:
                pass
            lines.append(self._tr(f"{zh_label} = { _fmt_plain(value)}", f"{en_label} = { _fmt_plain(value)}"))
        lines.extend(
            [
                "",
                self._tr(
                    f"最小值 min = { _fmt_plain(v_min)}",
                    f"Min = { _fmt_plain(v_min)}",
                ),
                self._tr(
                    f"最大值 max = { _fmt_plain(v_max)}",
                    f"Max = { _fmt_plain(v_max)}",
                ),
            ]
        )
        dropped = result.get("dropped", 0)
        if dropped:
            lines.append(
                self._tr(
                    f"提示: 有 {dropped} 行因缺失或非正 σ 被忽略。",
                    f"Notice: {dropped} rows skipped due to missing or non-positive sigma.",
                )
            )
        warning_texts = self._statistics_warning_texts(result)
        if warning_texts:
            lines.append("")
            lines.append(self._tr("警告:", "Warnings:"))
            for warning in warning_texts:
                lines.append(f"- {warning}")
        outlier_texts = statistics_outlier_flag_display_texts(result)
        if outlier_texts:
            lines.append("")
            lines.append(self._tr("异常值标记:", "Outlier flags:"))
            lines.extend(f"- {text}" for text in outlier_texts)
        return "\n".join(lines)

    def _format_statistics_display(
        self,
        result: dict,
        value_col: str,
        n: int,
        units: Mapping[str, object] | None = None,
    ) -> tuple[str, list[dict[str, object]]]:
        """Return formatted statistics text/CSV rows (numbers only; LaTeX unchanged elsewhere)."""
        text = self._render_statistics_text(result, value_col, n, units=units)
        csv_rows = self._build_stats_csv_rows(result, batch_idx=1, row_count=n, units=units)
        return text, csv_rows

    def _format_statistics_batches_display(self, batches: list[dict], value_col: str) -> tuple[str, list[dict[str, object]]]:
        block_texts: list[str] = []
        csv_rows: list[dict[str, object]] = []
        value_columns = _statistics_batch_value_columns(batches)
        multi_column = len(value_columns) > 1
        for entry in batches:
            idx = entry.get("index") or (len(block_texts) + 1)
            batch_idx = entry.get("batch_index") or idx
            val_col = str(entry.get("value_col") or value_col)
            row_count = entry.get("row_count") or len(entry.get("rows", []) or [])
            body = self._render_statistics_text(
                entry.get("result", {}),
                val_col,
                row_count,
                units=entry.get("units") if isinstance(entry.get("units"), Mapping) else None,
            )
            body_lines = body.splitlines()
            if body_lines and body_lines[0].startswith("==="):
                body_lines = body_lines[1:]
            if multi_column:
                if batch_idx != 1:
                    header = self._tr(
                        f"=== 统计结果：列 {val_col}，批次 {batch_idx} ===",
                        f"=== Statistics: Column {val_col}, Batch {batch_idx} ===",
                    )
                else:
                    header = self._tr(
                        f"=== 统计结果：列 {val_col} ===",
                        f"=== Statistics: Column {val_col} ===",
                    )
            else:
                header = self._tr(f"=== 统计结果：批次 {idx} ===", f"=== Statistics: Batch {idx} ===")
            block_texts.append("\n".join([header, *body_lines]))
            entry_units = entry.get("units") if isinstance(entry.get("units"), Mapping) else None
            entry_rows = self._build_stats_csv_rows(
                entry.get("result", {}),
                batch_idx=batch_idx,
                row_count=row_count,
                units=entry_units,
            )
            if multi_column:
                entry_rows = [{"column": val_col, **row} for row in entry_rows]
            csv_rows.extend(entry_rows)
        return "\n\n".join(block_texts), csv_rows

    def _display_statistics_result(
        self,
        result: dict,
        value_col: str,
        n: int,
        values: list[mp.mpf] | None = None,
        sigmas: list[mp.mpf | None] | None = None,
        render_plots: bool = True,
        units: Mapping[str, object] | None = None,
    ):
        text, csv_rows = self._format_statistics_display(result=result, value_col=value_col, n=n, units=units)
        if result.get("dropped", 0):
            self._append_log(
                self._tr(
                    f"提示: 有 {result['dropped']} 行因缺失或非正 σ 被忽略。",
                    f"Notice: {result['dropped']} rows skipped due to missing or non-positive sigma.",
                )
            )
        self._append_statistics_warning_logs(result)
        self._set_result_text(text, final_result=True)
        if csv_rows:
            headers = ["batch", "metric", "value", "uncertainty"]
            if any("value_unit" in row or "uncertainty_unit" in row for row in csv_rows):
                headers.extend(["value_unit", "uncertainty_unit"])
            self._set_csv_data(csv_rows, headers, suggestion="statistics_results.csv")
        else:
            self._reset_csv_data()
        remembered: dict[str, object] = {"result": result, "value_col": value_col, "n": n}
        if units is not None:
            remembered["units"] = units
        self._remember_last_result("statistics_single", remembered)
        plot_bytes_list: list[bytes] = []
        if render_plots and values:
            value_unit = _statistics_value_unit_for_label(units, value_col)
            plot_bytes_list = self._render_statistics_plots(
                values,
                sigmas,
                result,
                batch_idx=None,
                value_unit=value_unit,
            )
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        for plot_index, plot_bytes in enumerate(plot_bytes_list, 1):
            img_path = self._save_batch_figure(plot_bytes, "", 1, prefix=f"stats{plot_index}")
            if img_path:
                figure_paths.append(img_path)
                figure_metadata.append(
                    {
                        "role": "statistics",
                        "column": value_col,
                        "batch": 1,
                        "plot_index": plot_index,
                        "title": f"{value_col} statistics plot {plot_index}",
                    }
                )
        if figure_paths:
            self._current_stats_plot_metadata = figure_metadata
            self._set_image_list("stats", figure_paths)
            self._image_mode = "stats"
            return
        self._image_mode = "stats"
        self._result_plot_base_pixmap = None
        self.result_plot_bytes = None
        self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
        self.current_stats_figures = []
        self.current_stats_index = 0
        self._current_stats_plot_metadata = []
        self._update_image_status()

    def _display_error_contributions(self, breakdown: list[dict[str, object]], plot_bytes: bytes | None):
        if breakdown:
            lines = [self._tr("=== 不确定度贡献分解 ===", "=== Uncertainty breakdown ===")]
            for entry in breakdown:
                name = entry.get("name", "")
                percent = entry.get("percent", 0.0)
                sigma = entry.get("sigma", mp.mpf("0"))
                try:
                    sigma_val = sigma if isinstance(sigma, mp.mpf) else mp.mpf(sigma)
                except Exception:
                    sigma_val = mp.mpf("0")
                lines.append(f"{name}: {percent:.2f}% (σ={mp.nstr(sigma_val, 8)})")
            self._append_log("\n".join(lines))
        if plot_bytes:
            self._image_mode = "error"
            self._update_result_plot(plot_bytes, final_result=True)

    def _display_statistics_batches(self, batches: list[dict], value_col: str, render_plots: bool = True):
        if not batches:
            self._set_result_text("", final_result=True)
            self._image_mode = "stats"
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._current_stats_plot_metadata = []
            self._update_image_status()
            self._reset_csv_data()
            return
        figure_paths: list[Path] = []
        figure_metadata: list[dict[str, object]] = []
        block_texts: list[str] = []
        csv_rows: list[dict[str, object]] = []
        value_columns = _statistics_batch_value_columns(batches)
        multi_column = len(value_columns) > 1
        for entry in batches:
            idx = entry.get("index") or (len(block_texts) + 1)
            batch_idx = entry.get("batch_index") or idx
            row_count = entry.get("row_count") or len(entry.get("rows", []) or [])
            val_col = str(entry.get("value_col") or value_col)
            entry_units = entry.get("units") if isinstance(entry.get("units"), Mapping) else None
            body = self._render_statistics_text(entry.get("result", {}), val_col, row_count, units=entry_units)
            body_lines = body.splitlines()
            if body_lines and body_lines[0].startswith("==="):
                body_lines = body_lines[1:]
            if multi_column:
                if batch_idx != 1:
                    header = self._tr(
                        f"=== 统计结果：列 {val_col}，批次 {batch_idx} ===",
                        f"=== Statistics: Column {val_col}, Batch {batch_idx} ===",
                    )
                else:
                    header = self._tr(
                        f"=== 统计结果：列 {val_col} ===",
                        f"=== Statistics: Column {val_col} ===",
                    )
            else:
                header = self._tr(f"=== 统计结果：批次 {idx} ===", f"=== Statistics: Batch {idx} ===")
            block_texts.append("\n".join([header, *body_lines]))
            dropped = entry.get("result", {}).get("dropped", 0)
            if dropped:
                self._append_log(
                    self._tr(
                        f"提示: 批次 {idx} 有 {dropped} 行因缺失或非正 σ 被忽略。",
                        f"Notice: batch {idx} skipped {dropped} rows due to missing or non-positive sigma.",
                    )
                )
            self._append_statistics_warning_logs(
                entry.get("result", {}),
                prefix=self._tr(f"批次 {idx}: ", f"Batch {idx}: "),
            )
            headers = entry.get("headers") or []
            rows = entry.get("rows") or []
            sigma_rows = entry.get("sigma_rows") or []
            val_col = entry.get("value_col") or value_col
            values = entry.get("values")
            sigmas = entry.get("sigmas")
            if (not values) and headers and rows and val_col in headers:
                val_idx = headers.index(val_col)
                values = [row[val_idx] for row in rows]
                sigmas = []
                for sigma_row in sigma_rows:
                    if val_idx < len(sigma_row):
                        entry_sigma = sigma_row[val_idx]
                        if hasattr(entry_sigma, "uncertainty"):
                            entry_sigma = getattr(entry_sigma, "uncertainty", None)
                        try:
                            sigmas.append(mp.mpf(entry_sigma) if entry_sigma is not None else None)
                        except Exception:
                            sigmas.append(None)
                    else:
                        sigmas.append(None)
            if render_plots and values:
                value_unit = _statistics_value_unit_for_label(entry.get("units"), val_col)
                plot_bytes_list = self._render_statistics_plots(
                    values,
                    sigmas,
                    entry.get("result", {}),
                    batch_idx=idx,
                    value_unit=value_unit,
                )
                for plot_index, plot_bytes in enumerate(plot_bytes_list, 1):
                    img_path = self._save_batch_figure(plot_bytes, "", idx, prefix=f"stats{plot_index}")
                    if img_path:
                        figure_paths.append(img_path)
                        figure_metadata.append(
                            {
                                "role": "statistics",
                                "column": val_col,
                                "batch": batch_idx,
                                "plot_index": plot_index,
                                "title": f"{val_col} statistics plot {plot_index}",
                            }
                        )
            entry_rows = self._build_stats_csv_rows(
                entry.get("result", {}),
                batch_idx=batch_idx,
                row_count=row_count,
                units=entry_units,
            )
            if multi_column:
                entry_rows = [{"column": val_col, **row} for row in entry_rows]
            csv_rows.extend(entry_rows)
        self._set_result_text("\n\n".join(block_texts), final_result=True)
        if csv_rows:
            headers = ["column", "batch", "metric", "value", "uncertainty"] if multi_column else ["batch", "metric", "value", "uncertainty"]
            if any("value_unit" in row or "uncertainty_unit" in row for row in csv_rows):
                headers.extend(["value_unit", "uncertainty_unit"])
            self._set_csv_data(csv_rows, headers, suggestion="statistics_results.csv")
        else:
            self._reset_csv_data()
        self._image_mode = "stats"
        if figure_paths:
            self._current_stats_plot_metadata = figure_metadata
            self._set_image_list("stats", figure_paths)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._current_stats_plot_metadata = []
            self._update_image_status()
        payload: dict[str, object] = {"batches": batches, "value_col": value_col}
        if multi_column:
            payload["value_columns"] = value_columns
        self._remember_last_result("statistics_batches", payload)

    def _render_statistics_plot(
        self,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None] | None,
        stats_result: dict[str, object],
        batch_idx: int | None = None,
        value_unit: str | None = None,
    ) -> bytes | None:
        try:
            from shared.plotting import (
                render_statistics_plot_from_spec,
                statistics_plot_labels_with_unit,
                statistics_plot_spec_from_result,
                StatisticsPlotLabels,
            )
        except Exception:
            return None
        labels = StatisticsPlotLabels(
            data=self._tr("数据", "Data"),
            mean=self._tr("平均值", "Mean"),
            mean_band=self._tr("平均值±标准误差", "Mean ± SE"),
            x_axis=self._tr("点序号", "Point index"),
            y_axis=self._tr("数值", "Value"),
            title=self._tr("统计平均", "Statistics"),
        )
        spec = statistics_plot_spec_from_result(
            values,
            sigmas,
            stats_result,
            statistics_plot_labels_with_unit(labels, value_unit),
            batch_suffix=f" #{batch_idx}" if batch_idx is not None else "",
        )
        if spec is None:
            return None
        return render_statistics_plot_from_spec(spec)

    def _render_statistics_plots(
        self,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None] | None,
        stats_result: dict[str, object],
        batch_idx: int | None = None,
        value_unit: str | None = None,
    ) -> list[bytes]:
        try:
            from shared.plotting import (
                render_statistics_plots_from_specs,
                statistics_plot_labels_with_unit,
                statistics_plot_specs_from_result,
                StatisticsPlotLabels,
            )
        except Exception:
            return []
        labels = StatisticsPlotLabels(
            data=self._tr("数据", "Data"),
            mean=self._tr("平均值", "Mean"),
            mean_band=self._tr("平均值±标准误差", "Mean ± SE"),
            x_axis=self._tr("点序号", "Point index"),
            y_axis=self._tr("数值", "Value"),
            title=self._tr("统计平均", "Statistics"),
            median=self._tr("中位数", "Median"),
            histogram_title=self._tr("直方图", "Histogram"),
            box_title=self._tr("箱线图", "Box plot"),
            qq_title=self._tr("正态 QQ 图", "Normal QQ plot"),
            weighted_residual_title=self._tr("加权残差", "Weighted residuals"),
            frequency_axis=self._tr("频数", "Frequency"),
            theoretical_quantile_axis=self._tr("理论正态分位数", "Theoretical normal quantile"),
            sample_quantile_axis=self._tr("样本标准化分位数", "Sample standardized quantile"),
            residual_axis=self._tr("标准化残差", "Standardized residual"),
        )
        specs = statistics_plot_specs_from_result(
            values,
            sigmas,
            stats_result,
            statistics_plot_labels_with_unit(labels, value_unit),
            batch_suffix=f" #{batch_idx}" if batch_idx is not None else "",
        )
        return render_statistics_plots_from_specs(specs)
