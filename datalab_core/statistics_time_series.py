from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import mpmath as mp

from ._payload import normalize_json_payload
from .results import AnalysisRow, analysis_rows_from_json
from .statistics_compute import type7_quantile
from shared.bilingual import _dual_msg
from shared.precision import precision_guard
from shared.unit_annotations import first_unit_annotation_text, normalize_display_only_family_units

TIME_SERIES_WORKFLOW_MODE = "time_series_rolling"
TIME_SERIES_RESULT_CACHE_KIND = "statistics_time_series"
TIME_SERIES_PAYLOAD_SCHEMA = "datalab.statistics.time_series.v1"
TIME_SERIES_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.statistics"
TIME_SERIES_RESULT_SNAPSHOT_SCHEMA_VERSION = 1

_ROLLING_METHODS = {"rolling_mean", "rolling_median", "rolling_std"}
_SERIES_METHODS = _ROLLING_METHODS | {"ewma"}
_ALIGNMENTS = {"right", "center"}
_DENOMINATORS = {"sample", "population"}
_POINT_STATUSES = {"ok", "insufficient_window"}


@dataclass(frozen=True)
class TimeSeriesOptions:
    series_method: str
    window_size: int
    alignment: str
    min_periods: int
    denominator: str
    alpha: mp.mpf | None
    alpha_source: str | None
    alpha_input: str | None
    ewma_adjust: bool


def run_statistics_time_series(
    *,
    values: Sequence[mp.mpf],
    source_row_ids: Sequence[str | int] | None,
    precision_digits: int,
    inputs: Mapping[str, Any],
    value_column: str = "",
    column_index: int | None = None,
) -> dict[str, Any]:
    """Run precision-safe row-count rolling statistics for one value series."""

    with precision_guard(precision_digits) as precision_used:
        value_list = [mp.mpf(value) for value in values]
        if not value_list:
            raise ValueError(_dual_msg("时间序列统计至少需要一个值。", "time-series statistics require at least one value."))
        if any(not mp.isfinite(value) for value in value_list):
            raise ValueError(_dual_msg("时间序列统计要求所有值为有限值。", "time-series statistics require finite values."))

        options = normalize_statistics_time_series_options(inputs)
        row_ids = _source_row_ids(source_row_ids, len(value_list))
        time_labels = _time_labels(inputs.get("time_labels", inputs.get("times")), len(value_list))
        time_column = _string_option(inputs.get("time_column"), default="", field_name="time_column")
        diagnostics = _time_diagnostics(time_labels)
        sigmas, sigma_column, sigma_diagnostics = _parse_optional_sigmas(inputs, len(value_list))
        diagnostics.extend(sigma_diagnostics)

        uncertainty_assumption = ""
        if sigmas is not None and options.series_method == "rolling_mean":
            uncertainty_assumption = "independent"
        elif sigmas is not None:
            diagnostics.append(
                _diagnostic(
                    "series_uncertainty_not_available",
                    "Uncertainty propagation is not available for this time-series method.",
                    severity="warning",
                )
            )

        points = _series_points(
            values=value_list,
            sigmas=sigmas,
            source_row_ids=row_ids,
            time_labels=time_labels,
            options=options,
            precision_digits=precision_used,
        )
        if any(point.get("status") == "insufficient_window" for point in points):
            diagnostics.append(
                _diagnostic(
                    "insufficient_window",
                    "Some time-series points do not satisfy the window/min-period requirements.",
                    severity="warning",
                )
            )

        value_column_text = value_column or "value"
        sigma_columns = {value_column_text: sigma_column} if sigma_column else {}
        uncertainty_assumptions = (
            {value_column_text: uncertainty_assumption} if uncertainty_assumption else {}
        )
        column = {
            "value_column": value_column_text,
            "sigma_column": sigma_column,
            "column_index": column_index,
            "row_count": len(value_list),
            "source_row_ids": list(row_ids),
            "uncertainty_assumption": uncertainty_assumption,
            "points": points,
            "diagnostics": diagnostics,
        }
        payload: dict[str, Any] = {
            "schema": TIME_SERIES_PAYLOAD_SCHEMA,
            "workflow_mode": TIME_SERIES_WORKFLOW_MODE,
            "series_method": options.series_method,
            "value_columns": [value_column_text],
            "sigma_columns": sigma_columns,
            "uncertainty_assumptions": uncertainty_assumptions,
            "time_column": time_column,
            "window": _window_payload(options),
            "ewma": _ewma_payload(options, precision_digits=precision_used),
            "columns": [column],
            "diagnostics": diagnostics,
            "precision_used": precision_used,
        }

    validate_statistics_time_series_payload(payload)
    normalized = normalize_json_payload(payload, path="statistics_time_series_payload")
    if not isinstance(normalized, Mapping):
        raise TypeError(_dual_msg("统计时间序列载荷必须归一化为映射。", "statistics time-series payload must normalize to a mapping."))
    return dict(normalized)


def normalize_statistics_time_series_options(inputs: Mapping[str, Any]) -> TimeSeriesOptions:
    merged = _series_option_inputs(inputs)
    method = _string_option(
        merged.get("series_method"),
        default="rolling_mean",
        field_name="series_method",
    )
    if method not in _SERIES_METHODS:
        raise ValueError(_dual_msg(f"不支持的时间序列方法：{method}。", f"Unsupported time-series method: {method}."))

    window_size = _positive_int_option(merged.get("window_size"), default=3, field_name="window_size")
    min_periods = _positive_int_option(merged.get("min_periods"), default=window_size, field_name="min_periods")
    if min_periods > window_size:
        raise ValueError(_dual_msg("min_periods 必须小于或等于 window_size。", "min_periods must be less than or equal to window_size."))
    alignment = _string_option(merged.get("alignment"), default="right", field_name="alignment")
    if alignment not in _ALIGNMENTS:
        raise ValueError(_dual_msg("alignment 必须是 'right' 或 'center'。", "alignment must be 'right' or 'center'."))
    denominator = _string_option(merged.get("denominator"), default="sample", field_name="denominator")
    if denominator not in _DENOMINATORS:
        raise ValueError(_dual_msg("denominator 必须是 'sample' 或 'population'。", "denominator must be 'sample' or 'population'."))

    alpha: mp.mpf | None = None
    alpha_source: str | None = None
    alpha_input: str | None = None
    if method == "ewma":
        alpha_raw = _optional_text(merged.get("alpha"))
        span_raw = _optional_text(merged.get("span"))
        if bool(alpha_raw) == bool(span_raw):
            raise ValueError(_dual_msg("EWMA 需要 alpha 或 span 中恰好一个。", "EWMA requires exactly one of alpha or span."))
        if alpha_raw:
            alpha = _parse_probability(alpha_raw, field_name="alpha")
            alpha_source = "alpha"
            alpha_input = alpha_raw
        else:
            span = _parse_positive_mpf(span_raw or "", field_name="span")
            if span < 1:
                raise ValueError(_dual_msg("span 必须大于或等于 1。", "span must be greater than or equal to 1."))
            alpha = mp.mpf("2") / (span + 1)
            alpha_source = "span"
            alpha_input = span_raw

    return TimeSeriesOptions(
        series_method=method,
        window_size=window_size,
        alignment=alignment,
        min_periods=min_periods,
        denominator=denominator,
        alpha=alpha,
        alpha_source=alpha_source,
        alpha_input=alpha_input,
        ewma_adjust=_bool_option(merged.get("adjust"), default=False),
    )


def validate_statistics_time_series_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(_dual_msg("统计时间序列载荷必须是映射。", "statistics time-series payload must be a mapping."))
    _reject_json_floats(payload, path="statistics_time_series_payload")
    payload_without_optional = {key: value for key, value in payload.items() if key != "units"}
    _require_keys(
        payload_without_optional,
        {
            "schema",
            "workflow_mode",
            "series_method",
            "value_columns",
            "sigma_columns",
            "uncertainty_assumptions",
            "time_column",
            "window",
            "ewma",
            "columns",
            "diagnostics",
            "precision_used",
        },
        "statistics_time_series_payload",
    )
    if "units" in payload:
        normalize_display_only_family_units(payload.get("units"), family="statistics")
    if payload.get("schema") != TIME_SERIES_PAYLOAD_SCHEMA:
        raise ValueError(_dual_msg("统计时间序列载荷的 schema 不受支持。", "statistics time-series payload schema is unsupported."))
    if payload.get("workflow_mode") != TIME_SERIES_WORKFLOW_MODE:
        raise ValueError(_dual_msg("统计时间序列载荷的 workflow_mode 不受支持。", "statistics time-series workflow_mode is unsupported."))
    method = _required_text(payload.get("series_method"), "series_method")
    if method not in _SERIES_METHODS:
        raise ValueError(_dual_msg("统计时间序列方法不受支持。", "statistics time-series method is unsupported."))
    if method in _ROLLING_METHODS:
        window = payload.get("window")
        if not isinstance(window, Mapping):
            raise TypeError(_dual_msg("滚动时间序列载荷需要 window 元数据。", "rolling time-series payload requires window metadata."))
        _validate_window(window, method=method)
        if payload.get("ewma") is not None:
            raise ValueError(_dual_msg("滚动时间序列载荷不得包含 ewma 元数据。", "rolling time-series payload must not include ewma metadata."))
    else:
        if payload.get("window") is not None:
            raise ValueError(_dual_msg("EWMA 时间序列载荷不得包含 window 元数据。", "EWMA time-series payload must not include window metadata."))
        ewma = payload.get("ewma")
        if not isinstance(ewma, Mapping):
            raise TypeError(_dual_msg("EWMA 时间序列载荷需要 ewma 元数据。", "EWMA time-series payload requires ewma metadata."))
        _validate_ewma(ewma)

    value_columns = _required_text_list(payload.get("value_columns"), "value_columns")
    sigma_columns = _required_mapping(payload.get("sigma_columns"), "sigma_columns")
    assumptions = _required_mapping(payload.get("uncertainty_assumptions"), "uncertainty_assumptions")
    columns = _required_sequence(payload.get("columns"), "columns")
    if len(columns) != len(value_columns):
        raise ValueError(_dual_msg("时间序列列数必须与 value_columns 匹配。", "time-series column count must match value_columns."))

    for index, raw_column in enumerate(columns):
        column = _required_mapping(raw_column, f"columns[{index}]")
        _validate_column(
            column,
            value_column=value_columns[index],
            method=method,
            sigma_columns=sigma_columns,
            assumptions=assumptions,
        )
    _validate_diagnostics(payload.get("diagnostics"), "diagnostics")


def statistics_time_series_diagnostic_rows_from_payload(payload: Mapping[str, Any]) -> tuple[AnalysisRow, ...]:
    validate_statistics_time_series_payload(payload)
    rows: list[AnalysisRow] = []
    for diagnostic in _required_sequence(payload.get("diagnostics"), "diagnostics"):
        rows.append(_analysis_row_from_diagnostic(_required_mapping(diagnostic, "diagnostic"), source=""))
    for raw_column in _required_sequence(payload.get("columns"), "columns"):
        column = _required_mapping(raw_column, "column")
        source = _required_text(column.get("value_column"), "column.value_column")
        for diagnostic in _required_sequence(column.get("diagnostics"), "column.diagnostics"):
            rows.append(_analysis_row_from_diagnostic(_required_mapping(diagnostic, "diagnostic"), source=source))
    return tuple(rows)


def render_statistics_time_series_payload_outputs(
    payload: Mapping[str, Any],
    *,
    units: Mapping[str, Any] | None = None,
) -> tuple[str, list[dict[str, object]], list[str]]:
    validate_statistics_time_series_payload(payload)
    method = _required_text(payload.get("series_method"), "series_method")
    lines = ["=== Time-Series Statistics ===", f"Method: {method}"]
    time_column = str(payload.get("time_column") or "")
    lines.append(f"Time/index: {time_column or 'row index'}")
    window = payload.get("window")
    ewma = payload.get("ewma")
    if isinstance(window, Mapping):
        lines.append(
            "Window: "
            f"{window.get('type')} size={window.get('size')} "
            f"alignment={window.get('alignment')} min_periods={window.get('min_periods')}"
        )
    if isinstance(ewma, Mapping):
        lines.append(f"EWMA: alpha={ewma.get('alpha')} adjust={ewma.get('adjust')}")
    column_units: dict[str, str] = {}
    for raw_column in _required_sequence(payload.get("columns"), "columns"):
        column = _required_mapping(raw_column, "column")
        value_column = _required_text(column.get("value_column"), "column.value_column")
        unit = _time_series_output_unit(units, value_column)
        if unit:
            column_units[value_column] = unit
    include_units = bool(column_units)
    if include_units:
        lines.extend(
            [
                "",
                "Column | Row | Time | Value | Value unit | Uncertainty | Uncertainty unit | Status | Window Source Rows",
                "--- | --- | --- | --- | --- | --- | --- | --- | ---",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Column | Row | Time | Value | Uncertainty | Status | Window Source Rows",
                "--- | --- | --- | --- | --- | --- | ---",
            ]
        )

    csv_rows: list[dict[str, object]] = []
    for raw_column in _required_sequence(payload.get("columns"), "columns"):
        column = _required_mapping(raw_column, "column")
        value_column = _required_text(column.get("value_column"), "column.value_column")
        value_unit = column_units.get(value_column, "")
        for raw_point in _required_sequence(column.get("points"), "column.points"):
            point = _required_mapping(raw_point, "point")
            window_source_rows = " ".join(str(item) for item in point.get("window_source_row_ids", ()))
            row = {
                "column": value_column,
                "row": point.get("source_row_id", ""),
                "time": point.get("time", ""),
                "method": method,
                "value": point.get("value") or "",
                "uncertainty": point.get("uncertainty") or "",
                "status": point.get("status") or "",
                "window_source_rows": window_source_rows,
            }
            if include_units:
                row["value_unit"] = value_unit
                row["uncertainty_unit"] = value_unit if row["uncertainty"] else ""
                lines.append(
                    f"{row['column']} | {row['row']} | {row['time']} | {row['value']} | "
                    f"{row['value_unit']} | {row['uncertainty']} | {row['uncertainty_unit']} | "
                    f"{row['status']} | {row['window_source_rows']}"
                )
            else:
                lines.append(
                    f"{row['column']} | {row['row']} | {row['time']} | {row['value']} | "
                    f"{row['uncertainty']} | {row['status']} | {row['window_source_rows']}"
                )
            csv_rows.append(row)

    for diagnostic in statistics_time_series_diagnostic_rows_from_payload(payload):
        lines.append(f"Diagnostic | {diagnostic.source or ''} |  | {diagnostic.value} |  | {diagnostic.severity} | ")

    headers = ["column", "row", "time", "method", "value", "uncertainty", "status", "window_source_rows"]
    if include_units:
        headers = [
            "column",
            "row",
            "time",
            "method",
            "value",
            "value_unit",
            "uncertainty",
            "uncertainty_unit",
            "status",
            "window_source_rows",
        ]
    return ("\n".join(lines), csv_rows, headers)


def _time_series_output_unit(units: Mapping[str, Any] | None, value_column: str) -> str:
    return first_unit_annotation_text(units, "outputs", (value_column, "series", "smoothed", "result"))


def validate_statistics_time_series_snapshot(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot, Mapping):
        raise TypeError(_dual_msg("统计时间序列快照必须是映射。", "statistics time-series snapshot must be a mapping."))
    _reject_json_floats(snapshot, path="statistics_time_series_snapshot")
    if snapshot.get("schema") != TIME_SERIES_RESULT_SNAPSHOT_SCHEMA:
        raise ValueError(_dual_msg("统计时间序列快照的 schema 不受支持。", "statistics time-series snapshot schema is unsupported."))
    if snapshot.get("schema_version") != TIME_SERIES_RESULT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(_dual_msg("统计时间序列快照的 schema_version 不受支持。", "statistics time-series snapshot schema_version is unsupported."))
    if snapshot.get("family") != "statistics":
        raise ValueError(_dual_msg("统计时间序列快照的 family 必须为 statistics。", "statistics time-series snapshot family must be statistics."))
    if snapshot.get("mode") != TIME_SERIES_WORKFLOW_MODE:
        raise ValueError(_dual_msg("统计时间序列快照的 mode 不受支持。", "statistics time-series snapshot mode is unsupported."))
    source = _required_mapping(snapshot.get("source"), "source")
    time_series = _required_sequence(snapshot.get("time_series"), "time_series")
    payload = _payload_from_snapshot(source, time_series)
    validate_statistics_time_series_payload(payload)
    rows = snapshot.get("diagnostic_rows", ())
    if rows not in (None, ()):
        analysis_rows_from_json(rows)


def time_series_payload_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_statistics_time_series_snapshot(snapshot)
    source = _required_mapping(snapshot.get("source"), "source")
    time_series = _required_sequence(snapshot.get("time_series"), "time_series")
    return _payload_from_snapshot(source, time_series)


def _series_points(
    *,
    values: Sequence[mp.mpf],
    sigmas: Sequence[mp.mpf] | None,
    source_row_ids: Sequence[str | int],
    time_labels: Sequence[str],
    options: TimeSeriesOptions,
    precision_digits: int,
) -> list[dict[str, Any]]:
    if options.series_method == "ewma":
        return _ewma_points(
            values=values,
            sigmas=sigmas,
            source_row_ids=source_row_ids,
            time_labels=time_labels,
            options=options,
            precision_digits=precision_digits,
        )
    points: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        start, end = _window_bounds(index, len(values), options.window_size, options.alignment)
        window_values = list(values[start:end])
        window_sigmas = list(sigmas[start:end]) if sigmas is not None else None
        status = "ok" if _has_sufficient_window(window_values, options) else "insufficient_window"
        output_value: mp.mpf | None = None
        uncertainty: mp.mpf | None = None
        if status == "ok":
            output_value = _rolling_value(window_values, options)
            if options.series_method == "rolling_mean" and window_sigmas is not None:
                uncertainty = mp.sqrt(mp.fsum(sigma * sigma for sigma in window_sigmas)) / len(window_sigmas)
        points.append(
            _point_payload(
                index=index,
                source_row_ids=source_row_ids,
                time_labels=time_labels,
                observed_value=value,
                observed_uncertainty=sigmas[index] if sigmas is not None else None,
                value=output_value,
                uncertainty=uncertainty,
                window_source_row_ids=source_row_ids[start:end],
                status=status,
                precision_digits=precision_digits,
            )
        )
    return points


def _ewma_points(
    *,
    values: Sequence[mp.mpf],
    sigmas: Sequence[mp.mpf] | None,
    source_row_ids: Sequence[str | int],
    time_labels: Sequence[str],
    options: TimeSeriesOptions,
    precision_digits: int,
) -> list[dict[str, Any]]:
    if options.alpha is None:
        raise ValueError(_dual_msg("EWMA alpha 未归一化。", "EWMA alpha was not normalized."))
    alpha = options.alpha
    points: list[dict[str, Any]] = []
    previous: mp.mpf | None = None
    adjusted_numerator = mp.mpf("0")
    adjusted_denominator = mp.mpf("0")
    for index, value in enumerate(values):
        if options.ewma_adjust:
            adjusted_numerator = alpha * value + (1 - alpha) * adjusted_numerator
            adjusted_denominator = alpha + (1 - alpha) * adjusted_denominator
            output_value = adjusted_numerator / adjusted_denominator
        else:
            output_value = value if previous is None else alpha * value + (1 - alpha) * previous
            previous = output_value
        points.append(
            _point_payload(
                index=index,
                source_row_ids=source_row_ids,
                time_labels=time_labels,
                observed_value=value,
                observed_uncertainty=sigmas[index] if sigmas is not None else None,
                value=output_value,
                uncertainty=None,
                window_source_row_ids=(source_row_ids[index],),
                status="ok",
                precision_digits=precision_digits,
            )
        )
    return points


def _point_payload(
    *,
    index: int,
    source_row_ids: Sequence[str | int],
    time_labels: Sequence[str],
    observed_value: mp.mpf,
    observed_uncertainty: mp.mpf | None,
    value: mp.mpf | None,
    uncertainty: mp.mpf | None,
    window_source_row_ids: Sequence[str | int],
    status: str,
    precision_digits: int,
) -> dict[str, Any]:
    return {
        "index": index + 1,
        "source_row_id": source_row_ids[index],
        "time": time_labels[index],
        "observed_value": _mp_text(observed_value, precision_digits),
        "observed_uncertainty": (
            _mp_text(observed_uncertainty, precision_digits) if observed_uncertainty is not None else None
        ),
        "value": _mp_text(value, precision_digits) if value is not None else None,
        "uncertainty": _mp_text(uncertainty, precision_digits) if uncertainty is not None else None,
        "window_source_row_ids": list(window_source_row_ids),
        "skipped_source_row_ids": [],
        "window_size_effective": len(window_source_row_ids),
        "status": status,
    }


def _rolling_value(window_values: Sequence[mp.mpf], options: TimeSeriesOptions) -> mp.mpf:
    if options.series_method == "rolling_mean":
        return mp.fsum(window_values) / len(window_values)
    if options.series_method == "rolling_median":
        return type7_quantile(sorted(window_values), mp.mpf("0.5"))
    if options.series_method == "rolling_std":
        if options.denominator == "sample":
            if len(window_values) < 2:
                raise ValueError(_dual_msg("样本滚动标准差至少需要两个值。", "sample rolling standard deviation requires at least two values."))
            denominator = len(window_values) - 1
        else:
            denominator = len(window_values)
        mean = mp.fsum(window_values) / len(window_values)
        return mp.sqrt(mp.fsum((value - mean) ** 2 for value in window_values) / denominator)
    raise ValueError(_dual_msg(f"不支持的时间序列方法：{options.series_method}。", f"Unsupported time-series method: {options.series_method}."))


def _has_sufficient_window(window_values: Sequence[mp.mpf], options: TimeSeriesOptions) -> bool:
    if len(window_values) < options.min_periods:
        return False
    return not (options.series_method == "rolling_std" and options.denominator == "sample" and len(window_values) < 2)


def _window_bounds(index: int, row_count: int, window_size: int, alignment: str) -> tuple[int, int]:
    if alignment == "right":
        return max(0, index - window_size + 1), index + 1
    left = (window_size - 1) // 2
    right = window_size - left - 1
    return max(0, index - left), min(row_count, index + right + 1)


def _window_payload(options: TimeSeriesOptions) -> dict[str, Any] | None:
    if options.series_method not in _ROLLING_METHODS:
        return None
    return {
        "type": "row_count",
        "size": options.window_size,
        "alignment": options.alignment,
        "min_periods": options.min_periods,
        "denominator": options.denominator if options.series_method == "rolling_std" else None,
    }


def _ewma_payload(options: TimeSeriesOptions, *, precision_digits: int) -> dict[str, Any] | None:
    if options.series_method != "ewma":
        return None
    if options.alpha is None or options.alpha_source is None or options.alpha_input is None:
        raise ValueError(_dual_msg("EWMA 选项未归一化。", "EWMA options were not normalized."))
    return {
        "alpha": _mp_text(options.alpha, precision_digits),
        "parameter": options.alpha_source,
        "parameter_value": options.alpha_input,
        "adjust": options.ewma_adjust,
    }


def _series_option_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    nested = inputs.get("time_series")
    if isinstance(nested, Mapping):
        merged.update(dict(nested))
    for key, value in inputs.items():
        if key != "time_series":
            merged[str(key)] = value
    return merged


def _parse_optional_sigmas(
    inputs: Mapping[str, Any],
    count: int,
) -> tuple[tuple[mp.mpf, ...] | None, str, list[dict[str, Any]]]:
    raw_sigmas = inputs.get("sigmas")
    sigma_column = _string_option(inputs.get("sigma_column"), default="", field_name="sigma_column")
    if raw_sigmas is None:
        return None, sigma_column, []
    try:
        items = _required_sequence(raw_sigmas, "sigmas")
        if len(items) != count:
            raise ValueError(_dual_msg("sigmas 的长度必须与 values 的长度一致。", "sigmas length must match values length."))
        sigmas = tuple(_parse_finite_mpf(item, field_name=f"sigmas[{index}]") for index, item in enumerate(items))
        if any(sigma < 0 for sigma in sigmas):
            raise ValueError(_dual_msg("sigma 值必须为非负数。", "sigma values must be non-negative."))
    except (TypeError, ValueError) as exc:
        return None, sigma_column, [_diagnostic("invalid_sigma", str(exc), severity="warning")]
    return sigmas, sigma_column, []


def _time_labels(value: Any, count: int) -> tuple[str, ...]:
    if value is None:
        return tuple(str(index + 1) for index in range(count))
    labels = _required_sequence(value, "time_labels")
    if len(labels) != count:
        raise ValueError(_dual_msg("time_labels 的长度必须与 values 的长度一致。", "time_labels length must match values length."))
    return tuple(str(label) for label in labels)


def _time_diagnostics(labels: Sequence[str]) -> list[dict[str, Any]]:
    parsed: list[mp.mpf] = []
    for label in labels:
        try:
            parsed.append(mp.mpf(str(label).strip()))
        except Exception:  # noqa: BLE001 - advisory parse only.
            return []
    if any(not mp.isfinite(value) for value in parsed):
        return []
    for previous, current in zip(parsed, parsed[1:]):
        if current <= previous:
            return [
                _diagnostic(
                    "time_index_not_strictly_increasing",
                    "Time/index labels are not strictly increasing; input order was preserved.",
                    severity="warning",
                )
            ]
    return []


def _source_row_ids(source_row_ids: Sequence[str | int] | None, count: int) -> tuple[str | int, ...]:
    if source_row_ids is None:
        return tuple(str(index + 1) for index in range(count))
    if len(source_row_ids) != count:
        raise ValueError(_dual_msg("source_row_ids 的长度必须与 values 的长度一致。", "source_row_ids length must match values length."))
    normalized: list[str | int] = []
    for value in source_row_ids:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise TypeError(_dual_msg("source row ID 必须是字符串或整数。", "source row IDs must be strings or integers."))
        normalized.append(value)
    return tuple(normalized)


def _parse_finite_mpf(value: Any, *, field_name: str) -> mp.mpf:
    parsed = _parse_mpf(value, field_name=field_name)
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限值。", f"{field_name} must be finite."))
    return parsed


def _parse_mpf(value: Any, *, field_name: str) -> mp.mpf:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(_dual_msg(f"{field_name} 必须是数值字符串或整数。", f"{field_name} must be a numeric string or integer."))
    try:
        return mp.mpf(str(value).strip())
    except Exception as exc:  # noqa: BLE001 - user numeric boundary.
        raise ValueError(_dual_msg(f"{field_name} 不是有效的数字：{value!r}。", f"{field_name} is not a valid number: {value!r}.")) from exc


def _parse_positive_mpf(value: str, *, field_name: str) -> mp.mpf:
    parsed = _parse_finite_mpf(value, field_name=field_name)
    if parsed <= 0:
        raise ValueError(_dual_msg(f"{field_name} 必须为正数。", f"{field_name} must be positive."))
    return parsed


def _parse_probability(value: str, *, field_name: str) -> mp.mpf:
    parsed = _parse_finite_mpf(value, field_name=field_name)
    if not (0 < parsed <= 1):
        raise ValueError(_dual_msg(f"{field_name} 必须满足 0 < {field_name} <= 1。", f"{field_name} must satisfy 0 < {field_name} <= 1."))
    return parsed


def _positive_int_option(value: Any, *, default: int, field_name: str) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(_dual_msg(f"{field_name} 必须是整数。", f"{field_name} must be an integer."))
    parsed = int(str(value).strip())
    if parsed < 1:
        raise ValueError(_dual_msg(f"{field_name} 必须至少为 1。", f"{field_name} must be at least 1."))
    return parsed


def _bool_option(value: Any, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(_dual_msg(f"无效的布尔值：{value!r}。", f"Invalid boolean value: {value!r}."))


def _string_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是文本。", f"{field_name} must be text."))
    return value.strip() or default


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(_dual_msg("选项必须是文本。", "option must be text."))
    text = value.strip()
    return text or None


def _mp_text(value: mp.mpf, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _diagnostic(code: str, message: str, *, severity: str) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message}


def _analysis_row_from_diagnostic(diagnostic: Mapping[str, Any], *, source: str) -> AnalysisRow:
    code = _required_text(diagnostic.get("code"), "diagnostic.code")
    severity = _required_text(diagnostic.get("severity"), "diagnostic.severity")
    message = _required_text(diagnostic.get("message"), "diagnostic.message")
    return AnalysisRow(
        key=f"time_series.{code}",
        label_key=f"statistics.time_series.diagnostic.{code}",
        value=message,
        severity=severity,
        message_key=f"statistics.time_series.diagnostic.{code}",
        source=source,
        render_group="diagnostic",
    )


def _payload_from_snapshot(source: Mapping[str, Any], time_series: Sequence[Any]) -> dict[str, Any]:
    payload = {
        "schema": TIME_SERIES_PAYLOAD_SCHEMA,
        "workflow_mode": TIME_SERIES_WORKFLOW_MODE,
        "series_method": source.get("series_method"),
        "value_columns": source.get("value_columns"),
        "sigma_columns": source.get("sigma_columns", {}),
        "uncertainty_assumptions": source.get("uncertainty_assumptions", {}),
        "time_column": source.get("time_column", ""),
        "window": source.get("window"),
        "ewma": source.get("ewma"),
        "columns": list(time_series),
        "diagnostics": source.get("diagnostics", []),
        "precision_used": source.get("precision_used", 1),
    }
    normalized = normalize_json_payload(payload, path="statistics_time_series_snapshot_payload")
    if not isinstance(normalized, Mapping):
        raise TypeError(_dual_msg("统计时间序列快照载荷必须归一化为映射。", "statistics time-series snapshot payload must normalize to a mapping."))
    return dict(normalized)


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{path} 处不允许 JSON 浮点数。", f"JSON floats are not allowed at {path}."))
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, float):
                raise TypeError(_dual_msg(f"{path} 处不允许 JSON 浮点数键。", f"JSON float keys are not allowed at {path}."))
            _reject_json_floats(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, item in enumerate(value):
            _reject_json_floats(item, path=f"{path}[{index}]")


def _require_keys(mapping: Mapping[str, Any], expected: set[str], field_name: str) -> None:
    actual = set(mapping)
    extra = actual - expected
    missing = expected - actual
    if extra or missing:
        raise ValueError(_dual_msg(f"{field_name} 的键不匹配；多余={sorted(extra)}，缺失={sorted(missing)}。", f"{field_name} keys mismatch; extra={sorted(extra)}, missing={sorted(missing)}."))


def _required_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(_dual_msg(f"{field_name} 必须是映射。", f"{field_name} must be a mapping."))
    return value


def _required_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是序列。", f"{field_name} must be a sequence."))
    return value


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(_dual_msg(f"{field_name} 必须是非空文本。", f"{field_name} must be non-empty text."))
    return value


def _required_text_list(value: Any, field_name: str) -> list[str]:
    items = _required_sequence(value, field_name)
    output = []
    for index, item in enumerate(items):
        output.append(_required_text(item, f"{field_name}[{index}]"))
    return output


def _validate_column(
    column: Mapping[str, Any],
    *,
    value_column: str,
    method: str,
    sigma_columns: Mapping[str, Any],
    assumptions: Mapping[str, Any],
) -> None:
    _require_keys(
        column,
        {
            "value_column",
            "sigma_column",
            "column_index",
            "row_count",
            "source_row_ids",
            "uncertainty_assumption",
            "points",
            "diagnostics",
        },
        f"columns[{value_column}]",
    )
    if column.get("value_column") != value_column:
        raise ValueError(_dual_msg("column 的 value_column 必须与根 value_columns 的顺序一致。", "column value_column must match root value_columns order."))
    source_row_ids = _required_sequence(column.get("source_row_ids"), "column.source_row_ids")
    points = _required_sequence(column.get("points"), "column.points")
    row_count = column.get("row_count")
    if not isinstance(row_count, int) or isinstance(row_count, bool):
        raise TypeError(_dual_msg("column 的 row_count 必须是整数。", "column row_count must be an integer."))
    column_index = column.get("column_index")
    if column_index is not None and (isinstance(column_index, bool) or not isinstance(column_index, int)):
        raise TypeError(_dual_msg("column_index 必须是整数或 null。", "column_index must be an integer or null."))
    if row_count != len(source_row_ids) or row_count != len(points):
        raise ValueError(_dual_msg("column 的 row_count、source_row_ids 与 points 的长度必须一致。", "column row_count, source_row_ids, and points length must match."))
    sigma_column = column.get("sigma_column")
    if sigma_column not in (None, "") and sigma_columns.get(value_column) != sigma_column:
        raise ValueError(_dual_msg("column 的 sigma_column 必须与根 sigma_columns 一致。", "column sigma_column must match root sigma_columns."))
    assumption = column.get("uncertainty_assumption")
    if assumption not in (None, "") and assumptions.get(value_column) != assumption:
        raise ValueError(_dual_msg("column 的 uncertainty_assumption 必须与根 uncertainty_assumptions 一致。", "column uncertainty_assumption must match root uncertainty_assumptions."))
    if method != "rolling_mean" and assumption:
        raise ValueError(_dual_msg("只有 rolling_mean 可携带传播的不确定度假设。", "only rolling_mean may carry propagated uncertainty assumptions."))
    for index, raw_point in enumerate(points):
        point = _required_mapping(raw_point, f"points[{index}]")
        _validate_point(point, expected_index=index + 1)
        if point.get("source_row_id") != source_row_ids[index]:
            raise ValueError(_dual_msg("point 的 source_row_id 必须与 column source_row_ids 的顺序一致。", "point source_row_id must match column source_row_ids order."))
    _validate_diagnostics(column.get("diagnostics"), "column.diagnostics")


def _validate_window(window: Mapping[str, Any], *, method: str) -> None:
    _require_keys(window, {"type", "size", "alignment", "min_periods", "denominator"}, "window")
    if window.get("type") != "row_count":
        raise ValueError(_dual_msg("时间序列 window 的 type 必须为 row_count。", "time-series window type must be row_count."))
    for key in ("size", "min_periods"):
        value = window.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise TypeError(_dual_msg(f"window.{key} 必须是正整数。", f"window.{key} must be a positive integer."))
    if window["min_periods"] > window["size"]:
        raise ValueError(_dual_msg("window.min_periods 必须 <= window.size。", "window.min_periods must be <= window.size."))
    if window.get("alignment") not in _ALIGNMENTS:
        raise ValueError(_dual_msg("window.alignment 不受支持。", "window.alignment is unsupported."))
    denominator = window.get("denominator")
    if method == "rolling_std":
        if denominator not in _DENOMINATORS:
            raise ValueError(_dual_msg("rolling_std 需要受支持的 denominator。", "rolling_std requires a supported denominator."))
    elif denominator is not None:
        raise ValueError(_dual_msg("非 std 的滚动方法不得设置 denominator。", "non-std rolling methods must not set denominator."))


def _validate_ewma(ewma: Mapping[str, Any]) -> None:
    _require_keys(ewma, {"alpha", "parameter", "parameter_value", "adjust"}, "ewma")
    alpha = _parse_probability(_required_text(ewma.get("alpha"), "ewma.alpha"), field_name="ewma.alpha")
    if not (0 < alpha <= 1):
        raise ValueError(_dual_msg("ewma.alpha 必须满足 0 < alpha <= 1。", "ewma.alpha must satisfy 0 < alpha <= 1."))
    if ewma.get("parameter") not in {"alpha", "span"}:
        raise ValueError(_dual_msg("ewma.parameter 不受支持。", "ewma.parameter is unsupported."))
    _required_text(ewma.get("parameter_value"), "ewma.parameter_value")
    if not isinstance(ewma.get("adjust"), bool):
        raise TypeError(_dual_msg("ewma.adjust 必须是布尔值。", "ewma.adjust must be boolean."))


def _validate_point(point: Mapping[str, Any], *, expected_index: int) -> None:
    _require_keys(
        point,
        {
            "index",
            "source_row_id",
            "time",
            "observed_value",
            "observed_uncertainty",
            "value",
            "uncertainty",
            "window_source_row_ids",
            "skipped_source_row_ids",
            "window_size_effective",
            "status",
        },
        f"points[{expected_index}]",
    )
    if point.get("index") != expected_index:
        raise ValueError(_dual_msg("point 索引必须从 1 开始并保持有序。", "point indexes must be 1-based and ordered."))
    if not isinstance(point.get("time"), str):
        raise TypeError(_dual_msg("point 的 time 必须是文本。", "point time must be text."))
    if isinstance(point.get("source_row_id"), bool) or not isinstance(point.get("source_row_id"), (str, int)):
        raise TypeError(_dual_msg("point 的 source_row_id 必须是字符串或整数。", "point source_row_id must be a string or integer."))
    _numeric_text(point.get("observed_value"), "point.observed_value")
    if point.get("observed_uncertainty") is not None:
        _numeric_text(point.get("observed_uncertainty"), "point.observed_uncertainty")
    status = point.get("status")
    if status not in _POINT_STATUSES:
        raise ValueError(_dual_msg("point 的 status 不受支持。", "point status is unsupported."))
    if status == "insufficient_window":
        if point.get("value") is not None:
            raise ValueError(_dual_msg("insufficient_window 的 point 必须具有 null value。", "insufficient_window points must have null value."))
    else:
        _numeric_text(point.get("value"), "point.value")
    if point.get("uncertainty") is not None:
        _numeric_text(point.get("uncertainty"), "point.uncertainty")
    window_ids = _required_sequence(point.get("window_source_row_ids"), "point.window_source_row_ids")
    skipped_ids = _required_sequence(point.get("skipped_source_row_ids"), "point.skipped_source_row_ids")
    if len(window_ids) != point.get("window_size_effective"):
        raise ValueError(_dual_msg("window_size_effective 必须与 window_source_row_ids 的长度一致。", "window_size_effective must match window_source_row_ids length."))
    for item in list(window_ids) + list(skipped_ids):
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise TypeError(_dual_msg("point 的 source row ID 必须是字符串或整数。", "point source row IDs must be strings or integers."))


def _validate_diagnostics(value: Any, field_name: str) -> None:
    diagnostics = _required_sequence(value, field_name)
    for index, raw_item in enumerate(diagnostics):
        item = _required_mapping(raw_item, f"{field_name}[{index}]")
        _require_keys(item, {"code", "severity", "message"}, f"{field_name}[{index}]")
        _required_text(item.get("code"), f"{field_name}[{index}].code")
        _required_text(item.get("severity"), f"{field_name}[{index}].severity")
        _required_text(item.get("message"), f"{field_name}[{index}].message")


def _numeric_text(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是数值文本。", f"{field_name} must be numeric text."))
    parsed = mp.mpf(value)
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限的数值文本。", f"{field_name} must be finite numeric text."))
