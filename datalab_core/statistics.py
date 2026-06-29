from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from itertools import zip_longest
from typing import Any

import mpmath as mp

from shared.parallel_options import parallel_config_from_mapping
from shared.precision import precision_guard
from shared.unit_annotations import (
    canonical_unit_symbol_map,
    first_unit_annotation_text,
    normalize_display_only_family_units,
    unit_annotation_text,
)

from ._payload import normalize_json_payload
from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import (
    numeric_to_payload_string as _numeric_to_payload_string,
    optional_numeric_to_payload_string as _optional_numeric_to_payload_string,
    request_digit_hint as _request_digit_hint,
)
from .results import (
    AnalysisRow,
    ResultEnvelope,
    ResultKind,
    ResultStatus,
    analysis_rows_from_json,
    analysis_rows_to_json,
)
from .session import check_cancelled
from .statistics_bootstrap import (
    BOOTSTRAP_PAYLOAD_SCHEMA,
    BOOTSTRAP_WORKFLOW_MODE,
    normalize_statistics_bootstrap_options,
    run_statistics_bootstrap,
    statistics_bootstrap_analysis_rows_from_column,
    validate_statistics_bootstrap_payload,
)
from .statistics_compute import compute_statistics
from .statistics_hypothesis import (
    HYPOTHESIS_RESULT_CACHE_KIND,
    HYPOTHESIS_WORKFLOW_MODE,
    render_statistics_hypothesis_payload_outputs,
    run_statistics_hypothesis,
    statistics_hypothesis_analysis_rows_from_payload,
    validate_statistics_hypothesis_payload,
    validate_statistics_hypothesis_snapshot,
)
from .statistics_grouped import (
    GROUPED_PAYLOAD_SCHEMA,
    GROUPED_RESULT_CACHE_KIND,
    GROUPED_WORKFLOW_MODE,
    build_statistics_grouped_result_snapshot,
    render_statistics_grouped_payload_outputs,
    run_statistics_grouped,
    statistics_grouped_payload_from_snapshot,
    validate_statistics_grouped_snapshot,
)
from .statistics_matrix import (
    MATRIX_PAYLOAD_SCHEMA,
    MATRIX_RESULT_CACHE_KIND,
    MATRIX_WORKFLOW_MODE,
    build_statistics_matrix_result_snapshot,
    render_statistics_matrix_payload_outputs,
    run_statistics_matrix,
    statistics_matrix_payload_from_snapshot,
    validate_statistics_matrix_snapshot,
)
from .statistics_time_series import (
    TIME_SERIES_PAYLOAD_SCHEMA,
    TIME_SERIES_RESULT_CACHE_KIND,
    TIME_SERIES_WORKFLOW_MODE,
    render_statistics_time_series_payload_outputs,
    run_statistics_time_series,
    statistics_time_series_diagnostic_rows_from_payload,
    time_series_payload_from_snapshot,
    validate_statistics_time_series_payload,
    validate_statistics_time_series_snapshot,
)
from .table_payload import normalize_segments


DEFAULT_STATISTICS_PRECISION_DIGITS = 50
STATISTICS_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.statistics"
STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION = 1

_STATISTICS_METRIC_ROWS = (
    ("count", "statistics.metric.count", "count", None),
    ("mean", "statistics.metric.mean", "mean", "std_mean"),
    ("trimmed_mean", "statistics.metric.trimmed_mean", "trimmed_mean", None),
    ("std_mean", "statistics.metric.std_mean", "std_mean", None),
    ("mean_ci_lower", "statistics.metric.mean_ci_lower", "mean_ci_lower", None),
    ("mean_ci_upper", "statistics.metric.mean_ci_upper", "mean_ci_upper", None),
    ("mean_ci_margin", "statistics.metric.mean_ci_margin", "mean_ci_margin", None),
    ("mean_ci_confidence_level", "statistics.metric.mean_ci_confidence_level", "mean_ci_confidence_level", None),
    ("mean_ci_method", "statistics.metric.mean_ci_method", "mean_ci_method_label", None),
    ("mean_sample_se_for_ci", "statistics.metric.mean_sample_se_for_ci", "mean_sample_se_for_ci", None),
    ("weighted_se_known_sigma", "statistics.metric.weighted_se_known_sigma", "weighted_se_known_sigma", None),
    ("mean_ci_dof", "statistics.metric.mean_ci_dof", "mean_ci_dof", None),
    ("mean_ci_critical_value", "statistics.metric.mean_ci_critical_value", "mean_ci_critical_value", None),
    ("std", "statistics.metric.std", "std", None),
    ("variance", "statistics.metric.variance", "variance", None),
    ("min", "statistics.metric.min", "min", None),
    ("max", "statistics.metric.max", "max", None),
    ("median", "statistics.metric.median", "median", None),
    ("q1", "statistics.metric.q1", "q1", None),
    ("q3", "statistics.metric.q3", "q3", None),
    ("iqr", "statistics.metric.iqr", "iqr", None),
    ("mad", "statistics.metric.mad", "mad", None),
    ("skewness", "statistics.metric.skewness", "skewness", None),
    ("excess_kurtosis", "statistics.metric.excess_kurtosis", "excess_kurtosis", None),
)
_STATISTICS_ROW_UNCERTAINTY_KEYS = {
    row_key: uncertainty_key
    for row_key, _label_key, _value_key, uncertainty_key in _STATISTICS_METRIC_ROWS
    if uncertainty_key
}

_STATISTICS_WARNING_MESSAGE_KEYS = {
    "zero_sigma_anchor": "statistics.warning.zero_sigma_anchor",
    "weight_sum_invalid": "statistics.warning.weight_sum_invalid",
    "weighted_dof": "statistics.warning.weighted_dof",
    "weighted_consistency_dof_insufficient": "statistics.warning.weighted_consistency_dof_insufficient",
    "effective_n": "statistics.warning.effective_n",
    "descriptive_sample_variance_n_lt_2": "statistics.warning.descriptive_sample_variance_n_lt_2",
    "descriptive_sample_skewness_n_lt_3": "statistics.warning.descriptive_sample_skewness_n_lt_3",
    "descriptive_sample_kurtosis_n_lt_4": "statistics.warning.descriptive_sample_kurtosis_n_lt_4",
    "descriptive_zero_variance": "statistics.warning.descriptive_zero_variance",
    "mean_ci_n_lt_2": "statistics.warning.mean_ci_n_lt_2",
    "outlier_robust_mad_zero_fallback": "statistics.warning.outlier_robust_mad_zero_fallback",
}

_STATISTICS_WARNING_DISPLAY_MESSAGES = {
    "generic": "Statistics warning.",
    "zero_sigma_anchor": "Detected σ=0; treated as infinite weight.",
    "weight_sum_invalid": "Sum of weights is 0 (or non-finite); fell back to arithmetic mean.",
    "weighted_dof": "Effective weighted degrees of freedom is insufficient; fell back to population-weighted variance.",
    "weighted_consistency_dof_insufficient": (
        "Weighted consistency diagnostics require at least two finite positive sigma values."
    ),
    "effective_n": "Could not compute effective sample size (W2<=0 or non-finite).",
    "descriptive_sample_variance_n_lt_2": (
        "Sample descriptive statistics require n>=2 for variance, standard deviation, and standard error."
    ),
    "descriptive_sample_skewness_n_lt_3": "Sample descriptive statistics require n>=3 for skewness.",
    "descriptive_sample_kurtosis_n_lt_4": (
        "Sample descriptive statistics require n>=4 for bias-corrected excess kurtosis."
    ),
    "descriptive_zero_variance": "Zero variance; skewness and kurtosis are unavailable.",
    "mean_ci_n_lt_2": "Mean confidence interval requires n>=2 to estimate the sample standard error.",
    "outlier_robust_mad_zero_fallback": (
        "MAD is zero; robust outlier detection flagged non-median values by direct median residual."
    ),
}

_STATISTICS_CSV_ROW_ORDER = (
    "method",
    "mean",
    "trimmed_mean",
    "mean_ci_lower",
    "mean_ci_upper",
    "mean_ci_margin",
    "mean_ci_confidence_level",
    "mean_ci_method",
    "mean_sample_se_for_ci",
    "weighted_se_known_sigma",
    "mean_ci_dof",
    "mean_ci_critical_value",
    "bootstrap_original_statistic",
    "bootstrap_ci_lower",
    "bootstrap_ci_median",
    "bootstrap_ci_upper",
    "bootstrap_mean",
    "bootstrap_std",
    "row_count",
    "count",
    "std",
    "variance",
    "min",
    "max",
    "median",
    "q1",
    "q3",
    "iqr",
    "mad",
    "skewness",
    "excess_kurtosis",
    "effective_n",
    "weighted_chi_square",
    "weighted_consistency_dof",
    "weighted_reduced_chi_square",
    "birge_ratio",
    "dropped",
    "zero_sigma_anchor",
)
_STATISTICS_OUTPUT_UNIT_SYMBOLS = frozenset(
    {
        *_STATISTICS_CSV_ROW_ORDER,
        *(
            unit_key
            for row in _STATISTICS_METRIC_ROWS
            for unit_key in (row[0], row[2], row[3])
            if unit_key
        ),
        "result",
        "covariance",
        "correlation",
        "statistic",
        "p_value",
        "reject_null",
        "series",
        "smoothed",
        "rolling_mean",
        "rolling_median",
        "rolling_std",
        "ewma",
    }
)

_STATISTICS_CSV_KEY_MAP = {
    "method": "method",
    "row_count": "rows",
    "count": "count",
    "mean": "mean",
    "trimmed_mean": "trimmed_mean",
    "mean_ci_lower": "mean_ci_lower",
    "mean_ci_upper": "mean_ci_upper",
    "mean_ci_margin": "mean_ci_margin",
    "mean_ci_confidence_level": "mean_ci_confidence_level",
    "mean_ci_method": "mean_ci_method",
    "mean_sample_se_for_ci": "mean_sample_se_for_ci",
    "weighted_se_known_sigma": "weighted_se_known_sigma",
    "mean_ci_dof": "mean_ci_dof",
    "mean_ci_critical_value": "mean_ci_critical_value",
    "bootstrap_original_statistic": "bootstrap_original_statistic",
    "bootstrap_ci_lower": "bootstrap_ci_lower",
    "bootstrap_ci_median": "bootstrap_ci_median",
    "bootstrap_ci_upper": "bootstrap_ci_upper",
    "bootstrap_mean": "bootstrap_mean",
    "bootstrap_std": "bootstrap_std",
    "std": "std",
    "variance": "variance",
    "min": "min",
    "max": "max",
    "median": "median",
    "q1": "q1",
    "q3": "q3",
    "iqr": "iqr",
    "mad": "mad",
    "skewness": "skewness",
    "excess_kurtosis": "excess_kurtosis",
    "effective_n": "effective_n",
    "weighted_chi_square": "weighted_chi_square",
    "weighted_consistency_dof": "weighted_consistency_dof",
    "weighted_reduced_chi_square": "weighted_reduced_chi_square",
    "birge_ratio": "birge_ratio",
    "dropped": "dropped",
    "zero_sigma_anchor": "zero_sigma_anchor",
}

_OUTLIER_SIGMA_REASON = "statistics.flag.outlier_sigma.residual_gt_3sigma"
_OUTLIER_ROBUST_REASON = "statistics.flag.outlier_robust.modified_z_gt_3_5"
_OUTLIER_MAD_ZERO_REASON = "statistics.flag.outlier_robust.mad_zero_nonmedian"
_OUTLIER_REASON_TEXT = {
    _OUTLIER_SIGMA_REASON: "absolute residual exceeds 3 sigma",
    _OUTLIER_ROBUST_REASON: "absolute modified z-score exceeds 3.5",
    _OUTLIER_MAD_ZERO_REASON: "MAD is zero and value differs from the median",
}


@dataclass(frozen=True)
class StatisticsRequestBatch:
    index: int
    request: ComputeJobRequest
    headers: tuple[str, ...]
    value_col: str
    row_count: int
    source_row_ids: tuple[str | int, ...]


@dataclass(frozen=True)
class StatisticsColumnRequestBatches:
    column_index: int
    value_col: str
    batches: tuple[StatisticsRequestBatch, ...]


def statistics_source_row_ids(row_count: int, *, start_index: int = 0) -> tuple[str, ...]:
    """Return stable IDs for parsed statistics rows.

    Defaults are 1-based parsed data-row ordinals, not raw file or Excel line
    numbers.
    """
    if isinstance(row_count, bool) or not isinstance(row_count, int):
        raise TypeError("row_count must be an integer.")
    if isinstance(start_index, bool) or not isinstance(start_index, int):
        raise TypeError("start_index must be an integer.")
    if row_count < 0:
        raise ValueError("row_count must be non-negative.")
    if start_index < 0:
        raise ValueError("start_index must be non-negative.")
    return tuple(str(index + 1) for index in range(start_index, start_index + row_count))


def statistics_outlier_diagnostics(
    *,
    values: Sequence[mp.mpf],
    sigmas: Sequence[mp.mpf | None],
    result: Mapping[str, Any],
    source_row_ids: Sequence[str | int] | None,
    precision_digits: int,
) -> tuple[list[dict[str, object]], tuple[str, ...], tuple[str, ...]]:
    """Build advisory outlier flag records without changing statistics inputs."""

    values_mp = [mp.mpf(value) for value in values]
    row_ids = (
        statistics_source_row_ids(len(values_mp))
        if source_row_ids is None
        else _normalize_source_row_ids(source_row_ids, count=len(values_mp), field_name="source_row_ids")
    )
    flags: list[dict[str, object]] = []

    def add_flag(index: int, *, metric: str, reason: str) -> None:
        flags.append(
            {
                "source_row_id": row_ids[index],
                "value": _format_mpf(values_mp[index], precision_digits),
                "metric": metric,
                "reason": reason,
            }
        )

    mean = _mpf_or_none(result.get("mean"))
    if mean is not None and mp.isfinite(mean):
        for index, (value, sigma) in enumerate(zip(values_mp, sigmas)):
            if sigma is None:
                continue
            sigma_mp = mp.mpf(sigma)
            if not (mp.isfinite(value) and mp.isfinite(sigma_mp) and sigma_mp > 0):
                continue
            if mp.fabs(value - mean) > 3 * sigma_mp:
                add_flag(index, metric="sigma", reason=_OUTLIER_SIGMA_REASON)

    median = _mpf_or_none(result.get("median"))
    mad = _mpf_or_none(result.get("mad"))
    mad_zero_fallback = False
    if median is not None and mad is not None and mp.isfinite(median) and mp.isfinite(mad):
        if mad > 0:
            for index, value in enumerate(values_mp):
                if not mp.isfinite(value):
                    continue
                modified_z = mp.fabs(mp.mpf("0.6745") * (value - median) / mad)
                if modified_z > mp.mpf("3.5"):
                    add_flag(index, metric="robust_modified_z", reason=_OUTLIER_ROBUST_REASON)
        elif mad == 0:
            for index, value in enumerate(values_mp):
                if not mp.isfinite(value):
                    continue
                if mp.fabs(value - median) > 0:
                    add_flag(index, metric="robust_mad_zero", reason=_OUTLIER_MAD_ZERO_REASON)
                    mad_zero_fallback = True

    if not mad_zero_fallback:
        return flags, (), ()
    return (
        flags,
        (_STATISTICS_WARNING_DISPLAY_MESSAGES["outlier_robust_mad_zero_fallback"],),
        ("outlier_robust_mad_zero_fallback",),
    )


def statistics_attach_outlier_diagnostics(
    result: dict[str, Any],
    *,
    values: Sequence[mp.mpf],
    sigmas: Sequence[mp.mpf | None],
    source_row_ids: Sequence[str | int] | None,
    precision_digits: int,
) -> dict[str, Any]:
    """Attach advisory outlier flags to a legacy statistics result in place."""

    flags, warnings, warning_codes = statistics_outlier_diagnostics(
        values=values,
        sigmas=sigmas,
        result=result,
        source_row_ids=source_row_ids,
        precision_digits=precision_digits,
    )
    if flags:
        result["outlier_flags"] = flags
    if warnings:
        result["warnings"] = [*list(result.get("warnings") or ()), *warnings]
        result["warning_codes"] = [*list(result.get("warning_codes") or ()), *warning_codes]
    return result


def build_statistics_requests(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    value_col: str,
    sigma_col: str | None = None,
    stats_mode: str = "mean_sample",
    use_sample: bool = True,
    use_weighted_variance: bool = True,
    trim_fraction: str | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    segments: Sequence[tuple[int, int]] | None = None,
    request_id_prefix: str = "statistics",
    source_row_ids: Sequence[str | int] | None = None,
    units: Mapping[str, Any] | None = None,
) -> tuple[StatisticsRequestBatch, ...]:
    """Build string-only statistics core requests from normalized tabular data."""

    normalized_headers = tuple(str(header) for header in headers)
    if not value_col:
        raise ValueError("value_col must be provided.")
    if value_col not in normalized_headers:
        raise ValueError(f"Column not found: {value_col}.")
    value_index = normalized_headers.index(value_col)

    sigma_index: int | None = None
    normalized_sigma_col = (sigma_col or "").strip()
    if normalized_sigma_col:
        if normalized_sigma_col not in normalized_headers:
            raise ValueError(f"Column not found: {normalized_sigma_col}.")
        sigma_index = normalized_headers.index(normalized_sigma_col)

    normalized_segments = normalize_segments(segments, row_count=len(rows))
    all_source_row_ids = (
        statistics_source_row_ids(len(rows))
        if source_row_ids is None
        else _normalize_source_row_ids(source_row_ids, count=len(rows), field_name="source_row_ids")
    )
    batches: list[StatisticsRequestBatch] = []
    digit_hint = _request_digit_hint(precision_digits)
    for clamped_start, clamped_end in normalized_segments:
        if clamped_start >= clamped_end:
            continue
        values: list[str] = []
        sigmas: list[str | None] = []
        batch_source_row_ids: list[str | int] = []
        for row_index in range(clamped_start, clamped_end):
            row = rows[row_index]
            if value_index >= len(row):
                raise ValueError(f"Row {row_index + 1} is missing column {value_col}.")
            values.append(
                _numeric_to_payload_string(
                    row[value_index],
                    field_name=f"rows[{row_index}][{value_col}]",
                    digit_hint=digit_hint,
                )
            )
            sigmas.append(
                _resolve_sigma_payload(
                    rows,
                    sigma_rows,
                    row_index=row_index,
                    value_index=value_index,
                    sigma_index=sigma_index,
                    digit_hint=digit_hint,
                )
            )
            batch_source_row_ids.append(all_source_row_ids[row_index])
        if not values:
            continue
        batch_index = len(batches) + 1
        inputs: dict[str, object] = {
            "headers": normalized_headers,
            "value_col": value_col,
            "sigma_col": normalized_sigma_col or None,
            "values": tuple(values),
            "sigmas": tuple(sigmas),
            "stats_mode": stats_mode,
            "use_sample": use_sample,
            "use_weighted_variance": use_weighted_variance,
            "source_row_ids": tuple(batch_source_row_ids),
        }
        if trim_fraction is not None:
            inputs["trim_fraction"] = trim_fraction
        units_config = _normalize_statistics_units_config(units, inputs=inputs)
        if units_config is not None:
            inputs["units"] = units_config
        request = ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs=inputs,
            options=JobOptions(
                precision_digits=precision_digits,
                uncertainty_digits=uncertainty_digits,
            ),
            request_id=f"{request_id_prefix}-{batch_index}",
        )
        batches.append(
            StatisticsRequestBatch(
                index=batch_index,
                request=request,
                headers=normalized_headers,
                value_col=value_col,
                row_count=len(values),
                source_row_ids=tuple(batch_source_row_ids),
            )
        )
    if not batches:
        raise ValueError("values must contain at least one value.")
    return tuple(batches)


def normalize_statistics_value_columns(
    *,
    value_col: str | None = None,
    value_columns: Sequence[str] | str | None = None,
    headers: Sequence[str],
) -> tuple[str, ...]:
    """Return ordered, validated statistics value columns.

    ``value_col`` is the legacy single-column setting. ``value_columns`` accepts
    either an explicit sequence or the desktop compact comma-separated text.
    """

    normalized_headers = tuple(str(header) for header in headers)
    raw_columns: list[str] = []
    if isinstance(value_columns, str):
        raw_columns = [part.strip() for part in value_columns.split(",")]
    elif value_columns is not None:
        if not isinstance(value_columns, Sequence) or isinstance(value_columns, (bytes, bytearray, memoryview)):
            raise TypeError("value_columns must be a sequence of column names or a comma-separated string.")
        raw_columns = [str(column).strip() for column in value_columns]

    columns = [column for column in raw_columns if column]
    if not columns:
        fallback = str(value_col or "").strip()
        if fallback:
            columns = [fallback]
    if not columns:
        raise ValueError("value_col must be provided.")

    seen: set[str] = set()
    duplicates: list[str] = []
    for column in columns:
        if column in seen and column not in duplicates:
            duplicates.append(column)
        seen.add(column)
    if duplicates:
        raise ValueError(f"Duplicate statistics value column: {', '.join(duplicates)}.")

    missing = [column for column in columns if column not in normalized_headers]
    if missing:
        raise ValueError(f"Column not found: {missing[0]}.")
    return tuple(columns)


def build_multi_column_statistics_requests(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    value_col: str | None = None,
    value_columns: Sequence[str] | str | None = None,
    sigma_col: str | None = None,
    stats_mode: str = "mean_sample",
    use_sample: bool = True,
    use_weighted_variance: bool = True,
    trim_fraction: str | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    segments: Sequence[tuple[int, int]] | None = None,
    request_id_prefix: str = "statistics",
    source_row_ids: Sequence[str | int] | None = None,
    units: Mapping[str, Any] | None = None,
) -> tuple[StatisticsColumnRequestBatches, ...]:
    """Build normal statistics requests for several value columns."""

    columns = normalize_statistics_value_columns(
        value_col=value_col,
        value_columns=value_columns,
        headers=headers,
    )
    column_batches: list[StatisticsColumnRequestBatches] = []
    for column_index, column in enumerate(columns, 1):
        batches = build_statistics_requests(
            headers=headers,
            rows=rows,
            sigma_rows=sigma_rows,
            value_col=column,
            sigma_col=sigma_col,
            stats_mode=stats_mode,
            use_sample=use_sample,
            use_weighted_variance=use_weighted_variance,
            trim_fraction=trim_fraction,
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
            segments=segments,
            request_id_prefix=f"{request_id_prefix}-c{column_index}",
            source_row_ids=source_row_ids,
            units=units,
        )
        column_batches.append(
            StatisticsColumnRequestBatches(
                column_index=column_index,
                value_col=column,
                batches=batches,
            )
        )
    return tuple(column_batches)


def run_statistics(request: ComputeJobRequest) -> ResultEnvelope:
    """Run the core statistics subset for UI-neutral service migration."""

    check_cancelled()
    workflow_mode = _string_option(request.inputs.get("workflow_mode"), default="", field_name="workflow_mode")
    stats_mode = _string_option(request.inputs.get("stats_mode"), default="mean_sample", field_name="stats_mode")
    use_sample = _bool_option(request.inputs.get("use_sample"), default=True)
    use_weighted_variance = _bool_option(request.inputs.get("use_weighted_variance"), default=True)
    confidence_level_input = request.inputs.get("confidence_level")
    trim_fraction_input = _optional_numeric_string_option(
        request.inputs.get("trim_fraction"),
        field_name="trim_fraction",
    )
    units_config = _normalize_statistics_units_config(
        request.inputs.get("units") if "units" in request.inputs else None,
        inputs=request.inputs,
    )
    precision_digits = (
        DEFAULT_STATISTICS_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )

    if workflow_mode == MATRIX_WORKFLOW_MODE:
        payload = run_statistics_matrix(
            precision_digits=precision_digits,
            inputs=request.inputs,
        )
        payload = _statistics_payload_with_units(payload, units_config)
        diagnostics = payload.get("diagnostics", ())
        warning_items = (
            diagnostics
            if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview))
            else ()
        )
        return ResultEnvelope(
            kind=ResultKind.TABLE,
            status=ResultStatus.SUCCEEDED,
            payload=payload,
            warnings=tuple(_warning_message_text(item) for item in warning_items),
        )
    if workflow_mode == GROUPED_WORKFLOW_MODE:
        payload = run_statistics_grouped(
            precision_digits=precision_digits,
            uncertainty_digits=request.options.uncertainty_digits,
            inputs=request.inputs,
            statistics_runner=run_statistics,
        )
        payload = _statistics_payload_with_units(payload, units_config)
        diagnostics = payload.get("diagnostics", ())
        warning_items = (
            diagnostics
            if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview))
            else ()
        )
        return ResultEnvelope(
            kind=ResultKind.TABLE,
            status=ResultStatus.SUCCEEDED,
            payload=payload,
            warnings=tuple(_warning_message_text(item) for item in warning_items),
        )

    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        values = _parse_values(request.inputs.get("values"), field_name="values")
        source_row_ids = _parse_source_row_ids(request.inputs.get("source_row_ids"), count=len(values))
        if workflow_mode == TIME_SERIES_WORKFLOW_MODE:
            payload = run_statistics_time_series(
                values=values,
                source_row_ids=source_row_ids,
                precision_digits=precision_used,
                inputs=request.inputs,
                value_column=_string_option(
                    request.inputs.get("value_column", request.inputs.get("value_col")),
                    default="",
                    field_name="value_column",
                ),
                column_index=_optional_int_option(request.inputs.get("column_index"), field_name="column_index"),
            )
            payload = _statistics_payload_with_units(payload, units_config)
            diagnostics = payload.get("diagnostics", ())
            warning_items = (
                diagnostics
                if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview))
                else ()
            )
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload=payload,
                warnings=tuple(_warning_message_text(item) for item in warning_items),
            )
        if workflow_mode == HYPOTHESIS_WORKFLOW_MODE:
            payload = run_statistics_hypothesis(
                values=values,
                source_row_ids=source_row_ids,
                precision_digits=precision_used,
                inputs=request.inputs,
                value_column=_string_option(
                    request.inputs.get("value_column", request.inputs.get("value_col")),
                    default="",
                    field_name="value_column",
                ),
            )
            payload = _statistics_payload_with_units(payload, units_config)
            diagnostics = payload.get("diagnostics", ())
            warning_items = (
                diagnostics
                if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview))
                else ()
            )
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload=payload,
                warnings=tuple(_warning_message_text(item) for item in warning_items),
            )
        if workflow_mode == BOOTSTRAP_WORKFLOW_MODE:
            bootstrap_options = normalize_statistics_bootstrap_options(request.inputs)
            payload = run_statistics_bootstrap(
                values=values,
                source_row_ids=source_row_ids,
                precision_digits=precision_used,
                options=bootstrap_options,
                parallel_config=parallel_config_from_mapping(request.options.parallel),
                value_column=_string_option(
                    request.inputs.get("value_column", request.inputs.get("value_col")),
                    default="",
                    field_name="value_column",
                ),
                column_index=_optional_int_option(request.inputs.get("column_index"), field_name="column_index"),
            )
            payload = _statistics_payload_with_units(payload, units_config)
            diagnostics = payload.get("diagnostics", ())
            warning_items = (
                diagnostics
                if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview))
                else ()
            )
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload=payload,
                warnings=tuple(str(item) for item in warning_items),
            )
        sigmas = _parse_sigmas(request.inputs.get("sigmas"), count=len(values))
        confidence_level = _parse_optional_mpf_option(
            confidence_level_input,
            default="0.95",
            field_name="confidence_level",
        )
        check_cancelled()
        result = compute_statistics(
            values,
            sigmas,
            stats_mode,
            use_sample=use_sample,
            use_weighted_variance=use_weighted_variance,
            confidence_level=confidence_level,
            trim_fraction=trim_fraction_input,
        )
        check_cancelled()
        outlier_flags, outlier_warnings, outlier_warning_codes = statistics_outlier_diagnostics(
            values=values,
            sigmas=sigmas,
            result=result,
            source_row_ids=source_row_ids,
            precision_digits=precision_used,
        )
        payload = {
            "mode": stats_mode,
            "row_count": len(values),
            "precision_used": precision_used,
            "mean": _format_mpf(result.get("mean"), precision_used),
            "std_mean": _format_mpf(result.get("std_mean"), precision_used),
            "std": _format_mpf(result.get("std"), precision_used),
            "variance": _format_optional_mpf(result.get("variance"), precision_used),
            "min": _format_mpf(result.get("v_min"), precision_used),
            "max": _format_mpf(result.get("v_max"), precision_used),
            "median": _format_optional_mpf(result.get("median"), precision_used),
            "q1": _format_optional_mpf(result.get("q1"), precision_used),
            "q3": _format_optional_mpf(result.get("q3"), precision_used),
            "iqr": _format_optional_mpf(result.get("iqr"), precision_used),
            "mad": _format_optional_mpf(result.get("mad"), precision_used),
            "skewness": _format_optional_mpf(result.get("skewness"), precision_used),
            "excess_kurtosis": _format_optional_mpf(result.get("excess_kurtosis"), precision_used),
            "method_label": str(result.get("method_label") or ""),
            "dropped": int(result.get("dropped") or 0),
            "effective_n": _format_optional_mpf(result.get("effective_n"), precision_used),
            "zero_sigma_anchor": bool(result.get("zero_sigma_anchor", False)),
        }
        trimmed_mean = _format_optional_mpf(result.get("trimmed_mean"), precision_used)
        if trimmed_mean is not None:
            payload["trimmed_mean"] = trimmed_mean
        if outlier_flags:
            payload["outlier_flags"] = outlier_flags
        for target_key, result_key in (
            ("weighted_chi_square", "weighted_chi_square"),
            ("weighted_reduced_chi_square", "weighted_reduced_chi_square"),
            ("birge_ratio", "birge_ratio"),
        ):
            formatted = _format_optional_mpf(result.get(result_key), precision_used)
            if formatted is not None:
                payload[target_key] = formatted
        if result.get("weighted_consistency_dof") is not None:
            payload["weighted_consistency_dof"] = int(result.get("weighted_consistency_dof") or 0)
        for target_key, result_key in (
            ("mean_ci_confidence_level", "mean_ci_confidence_level"),
            ("mean_ci_lower", "mean_ci_lower"),
            ("mean_ci_upper", "mean_ci_upper"),
            ("mean_ci_margin", "mean_ci_margin"),
            ("mean_ci_critical_value", "mean_ci_critical_value"),
            ("mean_sample_se_for_ci", "mean_sample_se_for_ci"),
            ("weighted_se_known_sigma", "weighted_se_known_sigma"),
        ):
            formatted = _format_optional_mpf(result.get(result_key), precision_used)
            if formatted is not None:
                payload[target_key] = formatted
        if result.get("mean_ci_dof") is not None:
            payload["mean_ci_dof"] = int(result.get("mean_ci_dof") or 0)
        if result.get("mean_ci_method_label"):
            payload["mean_ci_method_label"] = str(result.get("mean_ci_method_label"))
        if "count" in result:
            payload["count"] = int(result.get("count") or len(values))
        if source_row_ids is not None:
            payload["source_row_ids"] = source_row_ids
        warnings = tuple(str(item) for item in (result.get("warnings") or ())) + tuple(outlier_warnings)
        warning_codes = tuple(str(item) for item in (result.get("warning_codes") or ())) + tuple(
            outlier_warning_codes
        )
        payload["warning_codes"] = list(warning_codes)
        payload["analysis_rows"] = analysis_rows_to_json(
            statistics_analysis_rows_from_payload(payload, warnings, warning_codes=warning_codes)
        )
        payload = _statistics_payload_with_units(payload, units_config)
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=warnings,
    )


def statistics_payload_to_compute_result(
    payload: Mapping[str, Any],
    warnings: Sequence[str] = (),
) -> dict[str, object]:
    """Convert a core statistics payload back to the legacy compute-result shape.

    Desktop and web adapters still share plotting and LaTeX renderers that expect
    the historical ``compute_statistics()`` dictionary. Keep the conversion here
    so both hosts use one interpretation of the JSON-safe core payload.
    """

    def _mpf_from_payload(key: str) -> mp.mpf:
        value = payload.get(key)
        if value is None:
            return mp.nan
        return mp.mpf(str(value))

    effective_n = payload.get("effective_n")
    result: dict[str, object] = {
        "mode": str(payload.get("mode") or ""),
        "mean": _mpf_from_payload("mean"),
        "std_mean": _mpf_from_payload("std_mean"),
        "std": _mpf_from_payload("std"),
        "variance": _mpf_from_payload("variance"),
        "v_min": _mpf_from_payload("min"),
        "v_max": _mpf_from_payload("max"),
        "median": _mpf_from_payload("median"),
        "q1": _mpf_from_payload("q1"),
        "q3": _mpf_from_payload("q3"),
        "iqr": _mpf_from_payload("iqr"),
        "mad": _mpf_from_payload("mad"),
        "skewness": _mpf_from_payload("skewness"),
        "excess_kurtosis": _mpf_from_payload("excess_kurtosis"),
        "method_label": str(payload.get("method_label") or ""),
        "dropped": int(payload.get("dropped") or 0),
        "effective_n": None if effective_n is None else mp.mpf(str(effective_n)),
        "zero_sigma_anchor": bool(payload.get("zero_sigma_anchor", False)),
        "warnings": list(warnings),
    }
    for key in ("weighted_chi_square", "weighted_reduced_chi_square", "birge_ratio"):
        if key in payload:
            result[key] = _mpf_from_payload(key)
    if "trimmed_mean" in payload:
        result["trimmed_mean"] = _mpf_from_payload("trimmed_mean")
    for key in (
        "mean_ci_confidence_level",
        "mean_ci_lower",
        "mean_ci_upper",
        "mean_ci_margin",
        "mean_ci_critical_value",
        "mean_sample_se_for_ci",
        "weighted_se_known_sigma",
    ):
        if key in payload:
            result[key] = _mpf_from_payload(key)
    if payload.get("weighted_consistency_dof") is not None:
        result["weighted_consistency_dof"] = int(payload.get("weighted_consistency_dof") or 0)
    if payload.get("mean_ci_dof") is not None:
        result["mean_ci_dof"] = int(payload.get("mean_ci_dof") or 0)
    if payload.get("mean_ci_method_label") is not None:
        result["mean_ci_method_label"] = str(payload.get("mean_ci_method_label") or "")
    warning_codes = payload.get("warning_codes")
    if warning_codes is not None:
        result["warning_codes"] = _snapshot_text_list(warning_codes)
    if "count" in payload:
        result["count"] = int(payload.get("count") or payload.get("row_count") or 0)
    source_row_ids = payload.get("source_row_ids")
    if source_row_ids is not None:
        result["source_row_ids"] = _parse_source_row_ids(
            source_row_ids,
            count=int(payload.get("row_count") or len(source_row_ids)),
        )
    outlier_flags = _snapshot_outlier_flags(payload.get("outlier_flags"))
    if outlier_flags:
        result["outlier_flags"] = outlier_flags
    analysis_rows = payload.get("analysis_rows")
    if analysis_rows is not None:
        result["analysis_rows"] = analysis_rows
    return result


def _normalize_statistics_units_config(
    units: Any,
    *,
    inputs: Mapping[str, Any],
) -> dict[str, Any] | None:
    if units is None:
        return None
    input_symbols = set(
        canonical_unit_symbol_map(
            _statistics_unit_input_labels(inputs),
            field_name="statistics inputs",
            fallback_prefix="input",
        ).values()
    )
    output_symbols = set(_STATISTICS_OUTPUT_UNIT_SYMBOLS)
    output_symbols.update(input_symbols)
    return normalize_display_only_family_units(
        units,
        family="statistics",
        allowed_symbols={
            "inputs": input_symbols,
            "constants": (),
            "parameters": (),
            "outputs": output_symbols,
        },
    )


def _statistics_unit_input_labels(inputs: Mapping[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []

    def add_text(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            labels.append(text)

    def add_many(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            add_text(value)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
            for item in value:
                add_text(item)
            return
        add_text(value)

    add_many(inputs.get("headers", inputs.get("data_headers")))
    for key in (
        "value_col",
        "value_column",
        "sigma_col",
        "sigma_column",
        "group_column",
        "time_col",
        "time_column",
    ):
        add_text(inputs.get(key))
    for key in ("value_columns", "columns"):
        add_many(inputs.get(key))
    if not labels and "values" in inputs:
        labels.append("values")
        if "sigmas" in inputs:
            labels.append("sigmas")
    return tuple(dict.fromkeys(labels))


def _statistics_payload_with_units(
    payload: Mapping[str, Any],
    units_config: Mapping[str, Any] | None,
) -> dict[str, Any]:
    output = dict(payload)
    if units_config is not None:
        output["units"] = dict(units_config)
    return output


def statistics_csv_rows_from_result(
    result: Mapping[str, Any],
    *,
    row_count: int | None = None,
    batch: int | None = None,
    include_batch: bool = True,
    precision_digits: int | None = None,
    units: Mapping[str, Any] | None = None,
) -> list[dict[str, object]]:
    """Build public statistics CSV rows from semantic analysis rows.

    Legacy callers may still pass the historical ``compute_statistics()``
    dictionary; this adapter first projects it to ``AnalysisRow`` records and
    then uses the same semantic CSV serializer as snapshot restore.
    """

    analysis_rows = _statistics_analysis_rows_for_result(
        result,
        row_count=row_count,
        precision_digits=precision_digits,
    )
    method_label = _snapshot_clean_text(result.get("method_label"))
    if method_label:
        analysis_rows = tuple(
            replace(row, value=method_label) if row.key == "method" else row
            for row in analysis_rows
        )
    return statistics_csv_rows_from_analysis_rows(
        analysis_rows,
        batch=batch,
        include_batch=include_batch,
        units=units,
    )


def statistics_csv_rows_from_analysis_rows(
    rows: Sequence[AnalysisRow | Mapping[str, Any]],
    *,
    batch: int | None = None,
    include_batch: bool = True,
    column: str | None = None,
    units: Mapping[str, Any] | None = None,
) -> list[dict[str, object]]:
    """Serialize semantic statistics rows to the public CSV row shape."""

    analysis_rows = tuple(
        row
        for row in _normalize_statistics_analysis_rows(rows)
        if row.render_group != "plot_annotation"
    )
    output: list[dict[str, object]] = []
    emitted_indexes: set[int] = set()
    for key in _STATISTICS_CSV_ROW_ORDER:
        for index, row in enumerate(analysis_rows):
            if row.key != key:
                continue
            output.append(
                _statistics_csv_row(
                    row,
                    batch=batch,
                    include_batch=include_batch,
                    column=column,
                    units=units,
                )
            )
            emitted_indexes.add(index)

    for index, row in enumerate(analysis_rows):
        if index in emitted_indexes or row.key == "std_mean":
            continue
        if row.render_group == "plot_annotation":
            continue
        if row.render_group not in {"diagnostic", "row_flag"} and row.severity != "warning":
            continue
        output.append(
            _statistics_csv_row(
                row,
                batch=batch,
                include_batch=include_batch,
                column=column,
                units=units,
            )
        )
        emitted_indexes.add(index)
    return output


def build_statistics_result_snapshot(
    kind: str,
    payload: Mapping[str, Any],
    *,
    overview_state: str = "none",
    plot_metadata: Sequence[Mapping[str, Any]] = (),
    precision: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build the first semantic statistics result snapshot from result-cache payloads."""

    if kind == HYPOTHESIS_RESULT_CACHE_KIND or payload.get("schema") == "datalab.statistics.hypothesis_test.v1":
        return _statistics_snapshot_with_units(
            _build_statistics_hypothesis_result_snapshot(
                payload,
                overview_state=overview_state,
                precision=precision,
            ),
            payload,
        )
    if kind == TIME_SERIES_RESULT_CACHE_KIND or payload.get("schema") == TIME_SERIES_PAYLOAD_SCHEMA:
        return _statistics_snapshot_with_units(
            _build_statistics_time_series_result_snapshot(
                payload,
                overview_state=overview_state,
                plot_metadata=plot_metadata,
                precision=precision,
            ),
            payload,
        )
    if kind == MATRIX_RESULT_CACHE_KIND or payload.get("schema") == MATRIX_PAYLOAD_SCHEMA:
        return _statistics_snapshot_with_units(
            build_statistics_matrix_result_snapshot(
                payload,
                overview_state=overview_state,
                plot_metadata=plot_metadata,
                precision=precision,
            ),
            payload,
        )
    if kind == GROUPED_RESULT_CACHE_KIND or payload.get("schema") == GROUPED_PAYLOAD_SCHEMA:
        return _statistics_snapshot_with_units(
            build_statistics_grouped_result_snapshot(
                payload,
                overview_state=overview_state,
                plot_metadata=plot_metadata,
                precision=precision,
            ),
            payload,
        )

    entries = _snapshot_statistics_entries(kind, payload)
    if not entries:
        return None

    metric_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    row_flags: list[dict[str, object]] = []
    warnings: list[str] = []
    source_batches: list[dict[str, object]] = []
    source_row_ids: list[str | int] = []
    modes: list[str] = []
    batch_snapshots: list[dict[str, object]] = []

    entry_value_columns = [
        _snapshot_clean_text(entry.get("value_col"))
        for entry in entries
        if _snapshot_clean_text(entry.get("value_col"))
    ]
    payload_value_columns = _snapshot_text_list(payload.get("value_columns"))
    value_columns = payload_value_columns or _snapshot_dedupe_text(entry_value_columns)
    has_column_scope = len(value_columns) > 1
    row_source_is_multi_column = len(value_columns) > 1

    for entry in entries:
        result = entry["result"]
        mode = _snapshot_clean_text(result.get("mode") or result.get("stats_mode") or "")
        if mode:
            modes.append(mode)
        row_count = _snapshot_optional_int(entry.get("row_count"))
        batch_index = _snapshot_optional_int(entry.get("index")) or len(batch_snapshots) + 1
        source_batch_index = _snapshot_optional_int(entry.get("batch_index")) or batch_index
        column_index = _snapshot_optional_int(entry.get("column_index"))
        value_col = _snapshot_clean_text(entry.get("value_col") or payload.get("value_col") or "")
        batch_source_row_ids = _snapshot_source_row_ids(
            result.get("source_row_ids", entry.get("source_row_ids"))
        )
        source_row_ids.extend(batch_source_row_ids)

        core_payload = _snapshot_statistics_core_payload(
            result,
            mode=mode,
            row_count=row_count,
            source_row_ids=batch_source_row_ids,
            precision=precision,
        )
        entry_warnings = _snapshot_text_list(result.get("warnings"))
        warnings.extend(entry_warnings)
        rows = _snapshot_analysis_rows(
            result,
            core_payload,
            entry_warnings,
            column_source=value_col if row_source_is_multi_column else "",
        )
        entry_metric_rows = _snapshot_rows_by_group(rows, "metric")
        entry_diagnostic_rows = _snapshot_rows_by_group(rows, "diagnostic")
        entry_row_flags = _snapshot_rows_by_group(rows, "row_flag")
        metric_rows.extend(entry_metric_rows)
        diagnostic_rows.extend(entry_diagnostic_rows)
        row_flags.extend(entry_row_flags)

        source_batch = {
            "index": batch_index,
            "row_count": row_count if row_count is not None else len(batch_source_row_ids),
            "value_column": value_col,
            "source_row_ids": batch_source_row_ids,
        }
        if has_column_scope:
            if column_index is None and value_col in value_columns:
                column_index = value_columns.index(value_col) + 1
            if column_index is not None:
                source_batch["column_index"] = column_index
            source_batch["batch_index"] = source_batch_index
        source_batches.append(source_batch)
        batch_snapshots.append(
            {
                "index": batch_index,
                "mode": mode,
                "metric_rows": entry_metric_rows,
                "diagnostic_rows": entry_diagnostic_rows,
                "row_flags": entry_row_flags,
                "warnings": entry_warnings,
                "source": source_batch,
            }
        )

    plots = [_snapshot_plain_mapping(plot) for plot in plot_metadata]
    plot_spec_keys = _snapshot_plot_spec_keys(kind, plots)
    source: dict[str, object] = {
        "value_column": _snapshot_clean_text(payload.get("value_col") or ""),
        "batch_count": len(batch_snapshots),
        "row_count": sum(
            _snapshot_optional_int(batch.get("row_count")) or 0 for batch in source_batches
        ),
        "source_row_ids": source_row_ids,
        "batches": source_batches,
    }
    if has_column_scope:
        source["value_columns"] = value_columns
        source["column_count"] = len(value_columns)
    if kind == "statistics_bootstrap":
        validate_statistics_bootstrap_payload(payload)
        source.update(_statistics_bootstrap_source_metadata(payload))

    snapshot: dict[str, object] = {
        "schema": STATISTICS_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "statistics",
        "mode": _snapshot_common_mode(modes),
        "metric_rows": metric_rows,
        "diagnostic_rows": diagnostic_rows,
        "row_flags": row_flags,
        "warnings": _snapshot_dedupe_text(warnings),
        "plot_spec_keys": plot_spec_keys,
        "plot_metadata": {
            "image_mode": "stats",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": source,
        "precision": _snapshot_plain_mapping(precision or {}),
        "compatibility": {
            "result_cache_kind": kind,
            "overview_state": _snapshot_clean_text(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_p0_5_shared_latex",
        },
        "batches": batch_snapshots,
    }
    if kind == "statistics_bootstrap":
        snapshot["bootstrap"] = _snapshot_plain_mapping(payload)
    units_config = _snapshot_statistics_units(payload.get("units") if "units" in payload else None)
    if units_config is not None:
        snapshot["units"] = units_config
    normalized = normalize_json_payload(snapshot, path="statistics_result_snapshot")
    if not isinstance(normalized, Mapping):
        return None
    output = {str(key): value for key, value in deepcopy(normalized).items()}
    if kind == "statistics_bootstrap":
        validate_statistics_bootstrap_snapshot(output)
    return output


def _statistics_snapshot_with_units(
    snapshot: dict[str, Any] | None,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    units_config = _snapshot_statistics_units(payload.get("units") if "units" in payload else None)
    if units_config is None:
        return snapshot
    output = {str(key): value for key, value in snapshot.items()}
    output["units"] = units_config
    normalized = normalize_json_payload(output, path="statistics_result_snapshot")
    if not isinstance(normalized, Mapping):
        return None
    return {str(key): value for key, value in deepcopy(normalized).items()}


def _snapshot_statistics_units(units: Any) -> dict[str, Any] | None:
    if units is None:
        return None
    return normalize_display_only_family_units(units, family="statistics")


def render_statistics_snapshot_outputs(
    snapshot: Mapping[str, Any],
) -> tuple[str, list[dict[str, object]], list[str]] | None:
    """Regenerate deterministic text and CSV from a semantic statistics snapshot."""

    if snapshot.get("family") != "statistics":
        return None
    units_config = snapshot.get("units") if isinstance(snapshot.get("units"), Mapping) else None
    if snapshot.get("mode") == HYPOTHESIS_WORKFLOW_MODE or snapshot.get("hypothesis_test") is not None:
        validate_statistics_hypothesis_snapshot(snapshot)
        hypothesis_payload = snapshot.get("hypothesis_test")
        if not isinstance(hypothesis_payload, Mapping):
            return None
        return render_statistics_hypothesis_payload_outputs(hypothesis_payload, units=units_config)
    if snapshot.get("mode") == TIME_SERIES_WORKFLOW_MODE or snapshot.get("time_series") is not None:
        validate_statistics_time_series_snapshot(snapshot)
        return render_statistics_time_series_payload_outputs(
            time_series_payload_from_snapshot(snapshot),
            units=units_config,
        )
    if snapshot.get("mode") == MATRIX_WORKFLOW_MODE or snapshot.get("statistics_matrix") is not None:
        validate_statistics_matrix_snapshot(snapshot)
        return render_statistics_matrix_payload_outputs(
            statistics_matrix_payload_from_snapshot(snapshot),
            units=units_config,
        )
    if snapshot.get("mode") == GROUPED_WORKFLOW_MODE or snapshot.get("statistics_grouped") is not None:
        validate_statistics_grouped_snapshot(snapshot)
        return render_statistics_grouped_payload_outputs(
            statistics_grouped_payload_from_snapshot(snapshot),
            units=units_config,
        )
    if snapshot.get("mode") == BOOTSTRAP_WORKFLOW_MODE or snapshot.get("bootstrap") is not None:
        validate_statistics_bootstrap_snapshot(snapshot)
    batches = _snapshot_render_batches(snapshot)
    if not batches:
        return None

    text_blocks: list[str] = []
    csv_rows: list[dict[str, object]] = []
    include_unit_columns = _statistics_units_have_output_annotations(units_config)
    snapshot_source = snapshot.get("source") if isinstance(snapshot.get("source"), Mapping) else {}
    source_column_count = _snapshot_optional_int(snapshot_source.get("column_count")) if isinstance(snapshot_source, Mapping) else None
    batch_value_columns = [
        _snapshot_clean_text((batch.get("source") or {}).get("value_column"))
        for batch in batches
        if isinstance(batch.get("source"), Mapping)
    ]
    multi_column = (source_column_count or 0) > 1 or len({column for column in batch_value_columns if column}) > 1
    multi_batch = len(batches) > 1
    for fallback_index, batch in enumerate(batches, 1):
        index = _snapshot_optional_int(batch.get("index")) or fallback_index
        source = batch.get("source") if isinstance(batch.get("source"), Mapping) else {}
        row_count = _snapshot_optional_int(source.get("row_count")) if isinstance(source, Mapping) else None
        value_col = (
            _snapshot_clean_text(source.get("value_column"))
            if isinstance(source, Mapping)
                else _snapshot_clean_text((snapshot.get("source") or {}).get("value_column"))
        )
        source_batch_index = (
            _snapshot_optional_int(source.get("batch_index"))
            if isinstance(source, Mapping)
            else None
        ) or index
        mode = _snapshot_clean_text(batch.get("mode") or snapshot.get("mode") or "")
        if multi_column:
            column_label = value_col or f"Column {index}"
            if source_batch_index != 1:
                heading = f"=== Statistics: Column {column_label}, Batch {source_batch_index} ==="
            else:
                heading = f"=== Statistics: Column {column_label} ==="
        else:
            heading = f"=== Statistics: Batch {index} ===" if multi_batch else "=== Statistics ==="
        lines = [heading]
        if mode:
            lines.append(f"Mode: {mode}")
        if row_count is not None:
            lines.append(f"Data points n = {row_count}")
        if value_col:
            lines.append(f"Column: {value_col}")
        lines.append("")
        if include_unit_columns:
            lines.append("Metric | Value | Value unit | Uncertainty | Uncertainty unit")
            lines.append("--- | --- | --- | --- | ---")
        else:
            lines.append("Metric | Value | Uncertainty")
            lines.append("--- | --- | ---")

        render_rows = _snapshot_render_rows(batch)
        for row in render_rows:
            value = _snapshot_cell_text(row.get("value"))
            uncertainty = _snapshot_cell_text(row.get("uncertainty"))
            if _statistics_row_is_outlier_flag(row) and not uncertainty:
                uncertainty = statistics_row_flag_detail(row)
            if not value and _snapshot_row_is_warning(row):
                value = statistics_warning_display_text(
                    row.get("message_key"),
                    fallback=row.get("key"),
                )
            label = _snapshot_row_label(row)
            if include_unit_columns:
                value_unit = _snapshot_cell_text(_statistics_value_unit_for_mapping(units_config, row))
                uncertainty_unit = _snapshot_cell_text(_statistics_uncertainty_unit_for_mapping(units_config, row))
                lines.append(f"{label} | {value} | {value_unit} | {uncertainty} | {uncertainty_unit}")
            else:
                lines.append(f"{label} | {value} | {uncertainty}")
        csv_rows.extend(
            statistics_csv_rows_from_analysis_rows(
                render_rows,
                batch=source_batch_index if multi_column else index,
                include_batch=True,
                column=value_col if multi_column else None,
                units=units_config,
            )
        )
        text_blocks.append("\n".join(lines))

    if multi_column:
        headers = ["column", "batch", "metric", "value", "uncertainty"]
    else:
        headers = ["batch", "metric", "value", "uncertainty"]
    if include_unit_columns:
        headers.extend(["value_unit", "uncertainty_unit"])
    return "\n\n".join(text_blocks), csv_rows, headers


def _build_statistics_hypothesis_result_snapshot(
    payload: Mapping[str, Any],
    *,
    overview_state: str,
    precision: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    validate_statistics_hypothesis_payload(payload)
    rows = analysis_rows_to_json(statistics_hypothesis_analysis_rows_from_payload(payload))
    metric_rows = _snapshot_rows_by_group(rows, "metric")
    diagnostic_rows = _snapshot_rows_by_group(rows, "diagnostic")
    row_flags = _snapshot_rows_by_group(rows, "row_flag")
    inputs = payload.get("inputs") if isinstance(payload.get("inputs"), Mapping) else {}
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    value_columns = _snapshot_text_list(inputs.get("value_columns")) if isinstance(inputs, Mapping) else []
    source_row_ids = _snapshot_source_row_ids(inputs.get("source_row_ids")) if isinstance(inputs, Mapping) else []
    row_count = _snapshot_optional_int(result.get("sample_size")) if isinstance(result, Mapping) else None
    source: dict[str, object] = {
        "test_kind": _snapshot_clean_text(payload.get("test_kind")),
        "value_columns": value_columns,
        "alternative": _snapshot_clean_text(payload.get("alternative")),
        "alpha": _snapshot_clean_text(payload.get("alpha")),
        "backend": _snapshot_clean_text(payload.get("backend")),
        "row_count": row_count if row_count is not None else len(source_row_ids),
        "source_row_ids": source_row_ids,
    }
    if isinstance(inputs, Mapping) and inputs.get("source_row_ids_b") is not None:
        source["source_row_ids_b"] = _snapshot_source_row_ids(inputs.get("source_row_ids_b"))
    snapshot: dict[str, object] = {
        "schema": STATISTICS_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "statistics",
        "mode": HYPOTHESIS_WORKFLOW_MODE,
        "hypothesis_test": _snapshot_plain_mapping(payload),
        "metric_rows": metric_rows,
        "diagnostic_rows": diagnostic_rows,
        "row_flags": row_flags,
        "warnings": [],
        "plot_spec_keys": [],
        "plot_metadata": {
            "image_mode": "stats",
            "plot_count": 0,
            "plots": [],
        },
        "source": source,
        "precision": _snapshot_plain_mapping(precision or {}),
        "compatibility": {
            "result_cache_kind": HYPOTHESIS_RESULT_CACHE_KIND,
            "overview_state": _snapshot_clean_text(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_p0_5_shared_latex",
        },
        "batches": [
            {
                "index": 1,
                "mode": HYPOTHESIS_WORKFLOW_MODE,
                "metric_rows": metric_rows,
                "diagnostic_rows": diagnostic_rows,
                "row_flags": row_flags,
                "warnings": [],
                "source": source,
            }
        ],
    }
    normalized = normalize_json_payload(snapshot, path="statistics_hypothesis_result_snapshot")
    if not isinstance(normalized, Mapping):
        return None
    output = {str(key): value for key, value in deepcopy(normalized).items()}
    validate_statistics_hypothesis_snapshot(output)
    return output


def _build_statistics_time_series_result_snapshot(
    payload: Mapping[str, Any],
    *,
    overview_state: str,
    plot_metadata: Sequence[Mapping[str, Any]],
    precision: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    validate_statistics_time_series_payload(payload)
    diagnostic_rows = analysis_rows_to_json(statistics_time_series_diagnostic_rows_from_payload(payload))
    value_columns = _snapshot_text_list(payload.get("value_columns"))
    plots = [_snapshot_plain_mapping(plot) for plot in plot_metadata]
    source: dict[str, object] = {
        "value_columns": value_columns,
        "sigma_columns": _snapshot_plain_mapping(payload.get("sigma_columns") or {}),
        "uncertainty_assumptions": _snapshot_plain_mapping(payload.get("uncertainty_assumptions") or {}),
        "column_count": len(value_columns),
        "time_column": _snapshot_clean_text(payload.get("time_column") or ""),
        "series_method": _snapshot_clean_text(payload.get("series_method") or ""),
        "window": _snapshot_plain_mapping(payload["window"]) if isinstance(payload.get("window"), Mapping) else None,
        "ewma": _snapshot_plain_mapping(payload["ewma"]) if isinstance(payload.get("ewma"), Mapping) else None,
        "diagnostics": list(payload.get("diagnostics", ())),
        "precision_used": _snapshot_optional_int(payload.get("precision_used")) or DEFAULT_STATISTICS_PRECISION_DIGITS,
    }
    time_series = [
        _snapshot_plain_mapping(column)
        for column in payload.get("columns", ())
        if isinstance(column, Mapping)
    ]
    snapshot: dict[str, object] = {
        "schema": STATISTICS_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "statistics",
        "mode": TIME_SERIES_WORKFLOW_MODE,
        "metric_rows": [],
        "diagnostic_rows": diagnostic_rows,
        "row_flags": [],
        "warnings": _snapshot_warning_texts(payload.get("diagnostics")),
        "plot_spec_keys": _snapshot_plot_spec_keys(TIME_SERIES_RESULT_CACHE_KIND, plots),
        "plot_metadata": {
            "image_mode": "stats",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": source,
        "time_series": time_series,
        "precision": _snapshot_plain_mapping(precision or {}),
        "compatibility": {
            "result_cache_kind": TIME_SERIES_RESULT_CACHE_KIND,
            "overview_state": _snapshot_clean_text(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_p0_5_shared_latex",
        },
        "batches": [
            {
                "index": index,
                "mode": TIME_SERIES_WORKFLOW_MODE,
                "metric_rows": [],
                "diagnostic_rows": diagnostic_rows,
                "row_flags": [],
                "warnings": _snapshot_warning_texts(column.get("diagnostics")) if isinstance(column, Mapping) else [],
                "source": {
                    "value_column": _snapshot_clean_text(column.get("value_column")) if isinstance(column, Mapping) else "",
                    "row_count": _snapshot_optional_int(column.get("row_count")) if isinstance(column, Mapping) else 0,
                    "source_row_ids": (
                        _snapshot_source_row_ids(column.get("source_row_ids")) if isinstance(column, Mapping) else []
                    ),
                },
            }
            for index, column in enumerate(time_series, 1)
        ],
    }
    normalized = normalize_json_payload(snapshot, path="statistics_time_series_result_snapshot")
    if not isinstance(normalized, Mapping):
        return None
    output = {str(key): value for key, value in deepcopy(normalized).items()}
    validate_statistics_time_series_snapshot(output)
    return output


def statistics_analysis_rows_from_payload(
    payload: Mapping[str, Any],
    warnings: Sequence[str] = (),
    *,
    warning_codes: Sequence[str] = (),
) -> tuple[AnalysisRow, ...]:
    """Build semantic statistics rows from the current core payload shape."""

    stats_mode = str(payload.get("mode") or "")
    method = stats_mode or None
    rows: list[AnalysisRow] = [
        AnalysisRow(
            key="method",
            label_key="statistics.method",
            value=stats_mode,
            method=method,
            render_group="diagnostic",
        )
    ]
    row_count = payload.get("row_count")
    if row_count is not None:
        rows.append(
            AnalysisRow(
                key="row_count",
                label_key="statistics.metric.row_count",
                value=_analysis_int_value(row_count, field_name="row_count"),
                method=method,
            )
        )

    for key, label_key, value_field, uncertainty_field in _STATISTICS_METRIC_ROWS:
        value = _analysis_optional_value(payload.get(value_field), field_name=value_field)
        if value is None:
            continue
        uncertainty = None
        if uncertainty_field is not None:
            uncertainty = _analysis_optional_value(
                payload.get(uncertainty_field),
                field_name=uncertainty_field,
            )
        rows.append(
            AnalysisRow(
                key=key,
                label_key=label_key,
                value=value,
                uncertainty=uncertainty,
                method=method,
            )
        )

    effective_n = _analysis_optional_value(payload.get("effective_n"), field_name="effective_n")
    if effective_n is not None:
        rows.append(
            AnalysisRow(
                key="effective_n",
                label_key="statistics.metric.effective_n",
                value=effective_n,
                method=method,
            )
        )

    for key, label_key, field_name in (
        ("weighted_chi_square", "statistics.metric.weighted_chi_square", "weighted_chi_square"),
        (
            "weighted_consistency_dof",
            "statistics.metric.weighted_consistency_dof",
            "weighted_consistency_dof",
        ),
        (
            "weighted_reduced_chi_square",
            "statistics.metric.weighted_reduced_chi_square",
            "weighted_reduced_chi_square",
        ),
        ("birge_ratio", "statistics.metric.birge_ratio", "birge_ratio"),
    ):
        value = _analysis_optional_value(payload.get(field_name), field_name=field_name)
        if value is None:
            continue
        rows.append(
            AnalysisRow(
                key=key,
                label_key=label_key,
                value=value,
                method=method,
            )
        )

    dropped = int(payload.get("dropped") or 0)
    if dropped:
        rows.append(
            AnalysisRow(
                key="dropped",
                label_key="statistics.metric.dropped",
                value=dropped,
                method=method,
                render_group="row_flag",
            )
        )

    if bool(payload.get("zero_sigma_anchor", False)):
        rows.append(
            AnalysisRow(
                key="zero_sigma_anchor",
                label_key="statistics.flag.zero_sigma_anchor",
                value="true",
                method=method,
                render_group="row_flag",
            )
        )

    for index, flag in enumerate(_snapshot_outlier_flags(payload.get("outlier_flags")), 1):
        metric = _snapshot_clean_text(flag.get("metric")) or "outlier"
        reason = _snapshot_clean_text(flag.get("reason")) or "statistics.flag.outlier"
        source_row_id = flag.get("source_row_id")
        row_index: str | int | None = (
            source_row_id
            if isinstance(source_row_id, (str, int)) and not isinstance(source_row_id, bool)
            else None
        )
        rows.append(
            AnalysisRow(
                key=f"outlier.{metric}.{index}",
                label_key=f"statistics.flag.outlier.{metric}",
                value=_analysis_optional_value(flag.get("value"), field_name=f"outlier_flags[{index - 1}].value"),
                source=metric,
                row_index=row_index,
                method=method,
                message_key=reason,
                render_group="row_flag",
            )
        )

    for warning, warning_code in zip_longest(warnings, warning_codes, fillvalue=None):
        warning_code_text = "generic" if warning_code is None else str(warning_code)
        message_key = _statistics_warning_message_key(warning_code_text)
        warning_key = message_key.removeprefix("statistics.")
        warning_text = statistics_warning_display_text(warning, fallback=warning_code_text)
        rows.append(
            AnalysisRow(
                key=warning_key,
                label_key="statistics.warning",
                value=warning_text,
                method=method,
                severity="warning",
                message_key=message_key,
                render_group="diagnostic",
            )
        )
    return tuple(rows)


def _statistics_analysis_rows_for_result(
    result: Mapping[str, Any],
    *,
    row_count: int | None,
    precision_digits: int | None,
) -> tuple[AnalysisRow, ...]:
    raw_rows = result.get("analysis_rows")
    if raw_rows is not None:
        try:
            return analysis_rows_from_json(raw_rows)
        except (TypeError, ValueError):
            pass

    mode = _snapshot_clean_text(result.get("mode") or result.get("stats_mode") or result.get("method_label") or "")
    source_row_ids = _snapshot_source_row_ids(result.get("source_row_ids"))
    payload = _snapshot_statistics_core_payload(
        result,
        mode=mode,
        row_count=row_count,
        source_row_ids=source_row_ids,
        precision={"compute_digits": precision_digits} if precision_digits is not None else None,
    )
    warnings = _snapshot_text_list(result.get("warnings"))
    warning_codes = _snapshot_text_list(result.get("warning_codes"))
    return statistics_analysis_rows_from_payload(payload, warnings, warning_codes=warning_codes)


def _normalize_statistics_analysis_rows(
    rows: Sequence[AnalysisRow | Mapping[str, Any]],
) -> tuple[AnalysisRow, ...]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("statistics CSV rows must be built from a sequence of analysis rows.")
    normalized: list[AnalysisRow] = []
    for row in rows:
        if isinstance(row, AnalysisRow):
            normalized.append(row)
        elif isinstance(row, Mapping):
            normalized.append(analysis_rows_from_json([row])[0])
        else:
            raise TypeError("statistics CSV rows must be built from AnalysisRow or mapping entries.")
    return tuple(normalized)


def _statistics_csv_row(
    row: AnalysisRow,
    *,
    batch: int | None,
    include_batch: bool,
    column: str | None,
    units: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    metric = _STATISTICS_CSV_KEY_MAP.get(row.key, row.key)
    value = _statistics_csv_value(row)
    uncertainty = (
        statistics_row_flag_detail(row)
        if _statistics_row_is_outlier_flag(row)
        else _analysis_csv_text(row.uncertainty)
    )
    output: dict[str, object] = {"metric": metric, "value": value, "uncertainty": uncertainty}
    if _statistics_units_have_output_annotations(units):
        output["value_unit"] = _statistics_value_unit_for_row(units, row)
        output["uncertainty_unit"] = _statistics_uncertainty_unit_for_row(units, row)
    if include_batch:
        output = {"batch": batch if batch is not None else 1, **output}
    if column is not None:
        output = {"column": column, **output}
    return output


def statistics_output_value_unit(units: Mapping[str, Any] | None, key: str) -> str:
    """Return the display unit for a statistics output value key."""

    if units is None:
        return ""
    metric = _STATISTICS_CSV_KEY_MAP.get(key, key)
    candidates: tuple[str, ...]
    if key in _STATISTICS_OUTPUT_UNIT_SYMBOLS or metric in _STATISTICS_OUTPUT_UNIT_SYMBOLS:
        candidates = (key, metric, "result")
    else:
        candidates = (key, metric)
    return first_unit_annotation_text(units, "outputs", candidates)


def statistics_output_uncertainty_unit(units: Mapping[str, Any] | None, key: str) -> str:
    """Return the display unit for a statistics output uncertainty key."""

    if units is None:
        return ""
    uncertainty_key = _STATISTICS_ROW_UNCERTAINTY_KEYS.get(key)
    if not uncertainty_key:
        return ""
    return unit_annotation_text(units, "outputs", uncertainty_key)


def statistics_units_have_output_annotations(units: Any) -> bool:
    """Return whether a statistics units payload has output annotations."""

    if not isinstance(units, Mapping):
        return False
    outputs = units.get("outputs")
    return isinstance(outputs, Mapping) and bool(outputs)


def _statistics_value_unit_for_row(units: Mapping[str, Any] | None, row: AnalysisRow) -> str:
    return statistics_output_value_unit(units, row.key)


def _statistics_uncertainty_unit_for_row(units: Mapping[str, Any] | None, row: AnalysisRow) -> str:
    return statistics_output_uncertainty_unit(units, row.key)


def _statistics_units_have_output_annotations(units: Any) -> bool:
    return statistics_units_have_output_annotations(units)


def _statistics_value_unit_for_mapping(units: Mapping[str, Any] | None, row: Mapping[str, Any]) -> str:
    if units is None:
        return ""
    key = _snapshot_clean_text(row.get("key"))
    if not key:
        return ""
    return statistics_output_value_unit(units, key)


def _statistics_uncertainty_unit_for_mapping(units: Mapping[str, Any] | None, row: Mapping[str, Any]) -> str:
    if units is None:
        return ""
    key = _snapshot_clean_text(row.get("key"))
    return statistics_output_uncertainty_unit(units, key)


def _statistics_csv_value(row: AnalysisRow) -> object:
    if row.key == "zero_sigma_anchor" and str(row.value).lower() == "true":
        return "True"
    if row.value is not None:
        return _analysis_csv_text(row.value)
    if row.render_group == "diagnostic" and row.message_key:
        return statistics_warning_display_text(row.message_key)
    return ""


def _analysis_csv_text(value: object) -> object:
    if value is None:
        return ""
    return value


def statistics_row_flag_detail(row: AnalysisRow | Mapping[str, Any]) -> str:
    """Return compact detail text for row-level statistics flags."""

    row_index = row.row_index if isinstance(row, AnalysisRow) else row.get("row_index")
    metric = row.source if isinstance(row, AnalysisRow) else row.get("source")
    reason = row.message_key if isinstance(row, AnalysisRow) else row.get("message_key")
    parts: list[str] = []
    if row_index is not None:
        parts.append(f"source row {row_index}")
    if metric:
        parts.append(f"metric {metric}")
    reason_text = _OUTLIER_REASON_TEXT.get(str(reason), str(reason or "").strip())
    if reason_text:
        parts.append(reason_text)
    return "; ".join(parts)


def statistics_outlier_flag_display_texts(result: Mapping[str, Any]) -> list[str]:
    """Build user-visible compact outlier flag lines from semantic or legacy results."""

    rows: list[AnalysisRow] = []
    raw_rows = result.get("analysis_rows")
    if raw_rows is not None:
        try:
            rows.extend(row for row in analysis_rows_from_json(raw_rows) if _statistics_row_is_outlier_flag(row))
        except (TypeError, ValueError):
            pass
    if not rows:
        rows.extend(statistics_analysis_rows_from_payload(result))
        rows = [row for row in rows if _statistics_row_is_outlier_flag(row)]
    return [
        f"{row.label_key}: value {row.value}; {statistics_row_flag_detail(row)}"
        for row in rows
    ]


def _analysis_optional_value(value: Any, *, field_name: str) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must not be a boolean analysis value.")
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric values as strings.")
    if isinstance(value, int):
        return value
    text = str(value)
    if text.lower() in {"nan", "+nan", "-nan"}:
        return None
    return text


def _analysis_int_value(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer analysis value.")
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer analysis value.")
    return value


def _normalize_source_row_ids(
    value: Sequence[str | int],
    *,
    count: int,
    field_name: str,
) -> tuple[str | int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(f"{field_name} must be a list of source row identifiers.")
    if len(value) != count:
        raise ValueError(f"{field_name} must have the same length as values.")
    return tuple(_normalize_source_row_id(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value))


def _parse_source_row_ids(value: Any, *, count: int) -> tuple[str | int, ...] | None:
    if value is None:
        return None
    return _normalize_source_row_ids(value, count=count, field_name="source_row_ids")


def _warning_message_text(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("message") or item)
    return str(item)


def _normalize_source_row_id(value: Any, *, field_name: str) -> str | int:
    if isinstance(value, float):
        raise ValueError(f"JSON floats are not allowed at {field_name}; pass row identifiers as strings.")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a string or integer source row identifier.")
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{field_name} must not be blank.")
        return value
    if isinstance(value, int):
        return value
    raise ValueError(f"{field_name} must be a string or integer source row identifier.")


def _statistics_warning_message_key(warning_code: str) -> str:
    return _STATISTICS_WARNING_MESSAGE_KEYS.get(warning_code, "statistics.warning.generic")


def statistics_warning_display_text(value: Any, *, fallback: Any = None) -> str:
    """Return user-facing warning text without exposing internal message keys."""

    for candidate in (value, fallback):
        text = _snapshot_clean_text(candidate)
        if not text:
            continue
        code = _statistics_warning_code_from_text(text)
        if code is None:
            return text
        return _STATISTICS_WARNING_DISPLAY_MESSAGES.get(code, _humanize_statistics_warning_code(code))
    return _STATISTICS_WARNING_DISPLAY_MESSAGES["generic"]


def _statistics_warning_code_from_text(text: str) -> str | None:
    if text.startswith("statistics.warning."):
        return text.removeprefix("statistics.warning.")
    if text.startswith("warning."):
        return text.removeprefix("warning.")
    if text in _STATISTICS_WARNING_MESSAGE_KEYS or text == "generic":
        return text
    return None


def _humanize_statistics_warning_code(code: str) -> str:
    cleaned = code.replace("_", " ").strip()
    if not cleaned:
        return _STATISTICS_WARNING_DISPLAY_MESSAGES["generic"]
    return f"Statistics warning: {cleaned}."


def _parse_values(value: Any, *, field_name: str) -> list[mp.mpf]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"{field_name} must be a list of numeric strings.")
    parsed = [_parse_mpf(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value)]
    if not parsed:
        raise ValueError(f"{field_name} must contain at least one value.")
    return parsed


def _parse_sigmas(value: Any, *, count: int) -> list[mp.mpf | None]:
    if value is None:
        return [None] * count
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError("sigmas must be a list of numeric strings or nulls.")
    if len(value) != count:
        raise ValueError("sigmas must have the same length as values.")
    return [
        None if item is None else _parse_mpf(item, field_name=f"sigmas[{index}]")
        for index, item in enumerate(value)
    ]


def _parse_mpf(value: Any, *, field_name: str) -> mp.mpf:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a numeric string.")
    try:
        return mp.mpf(value)
    except Exception as exc:  # noqa: BLE001 - user numeric text boundary.
        raise ValueError(f"{field_name} is not a valid number: {value!r}.") from exc


def _string_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    return value.strip() or default


def _optional_numeric_string_option(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a numeric string.")
    return value


def _bool_option(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError("boolean statistics options must be booleans.")
    return value


def _optional_int_option(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer or null.")
    return int(value)


def _parse_optional_mpf_option(value: Any, *, default: str, field_name: str) -> mp.mpf:
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a numeric string.")
    try:
        return mp.mpf(value)
    except Exception as exc:  # noqa: BLE001 - user numeric text boundary.
        raise ValueError(f"{field_name} is not a valid number: {value!r}.") from exc


def _format_optional_mpf(value: Any, precision_digits: int) -> str | None:
    if value is None:
        return None
    return _format_mpf(value, precision_digits)


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _resolve_sigma_payload(
    rows: Sequence[Sequence[Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None,
    *,
    row_index: int,
    value_index: int,
    sigma_index: int | None,
    digit_hint: int,
) -> str | None:
    if sigma_index is not None:
        row = rows[row_index]
        if sigma_index >= len(row):
            return None
        sigma_text = _optional_numeric_to_payload_string(
            row[sigma_index],
            field_name=f"rows[{row_index}][sigma]",
            digit_hint=digit_hint,
            absolute=False,
        )
        return sigma_text
    if not sigma_rows or row_index >= len(sigma_rows):
        return None
    sigma_row = sigma_rows[row_index]
    if value_index >= len(sigma_row):
        return None
    entry = sigma_row[value_index]
    if entry is None:
        return None
    if hasattr(entry, "uncertainty"):
        entry = getattr(entry, "uncertainty", None)
    return _optional_numeric_to_payload_string(
        entry,
        field_name=f"sigma_rows[{row_index}][{value_index}]",
        digit_hint=digit_hint,
        absolute=False,
    )


def _snapshot_statistics_entries(kind: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if kind == "statistics_bootstrap":
        validate_statistics_bootstrap_payload(payload)
        raw_columns = payload.get("columns")
        if not isinstance(raw_columns, Sequence) or isinstance(
            raw_columns, (str, bytes, bytearray)
        ):
            return []
        bootstrap_entries: list[dict[str, Any]] = []
        for index, column in enumerate(raw_columns, 1):
            if not isinstance(column, Mapping):
                continue
            value_col = _snapshot_clean_text(column.get("value_column"))
            rows = statistics_bootstrap_analysis_rows_from_column(payload, column)
            result: dict[str, Any] = {
                "mode": BOOTSTRAP_WORKFLOW_MODE,
                "analysis_rows": analysis_rows_to_json(rows),
                "warnings": _snapshot_warning_texts(payload.get("diagnostics"))
                + _snapshot_warning_texts(column.get("diagnostics")),
                "source_row_ids": column.get("source_row_ids"),
            }
            bootstrap_entries.append(
                {
                    "index": index,
                    "result": result,
                    "row_count": column.get("row_count"),
                    "value_col": value_col,
                    "column_index": column.get("column_index"),
                    "batch_index": 1,
                    "source_row_ids": column.get("source_row_ids"),
                }
            )
        return bootstrap_entries
    if kind == "statistics_single":
        single_result = payload.get("result")
        if not isinstance(single_result, Mapping):
            return []
        return [
            {
                "index": 1,
                "result": single_result,
                "row_count": payload.get("n"),
                "value_col": payload.get("value_col"),
                "column_index": payload.get("column_index"),
                "batch_index": payload.get("batch_index"),
            }
        ]
    if kind == "statistics_batches":
        raw_batches = payload.get("batches")
        if not isinstance(raw_batches, Sequence) or isinstance(
            raw_batches, (str, bytes, bytearray)
        ):
            return []
        batch_entries: list[dict[str, Any]] = []
        for index, batch in enumerate(raw_batches, 1):
            if not isinstance(batch, Mapping):
                continue
            batch_result = batch.get("result")
            if not isinstance(batch_result, Mapping):
                continue
            batch_entries.append(
                {
                    "index": batch.get("index", index),
                    "result": batch_result,
                    "row_count": batch.get("row_count"),
                    "value_col": batch.get("value_col") or payload.get("value_col"),
                    "column_index": batch.get("column_index"),
                    "batch_index": batch.get("batch_index"),
                    "source_row_ids": batch.get("source_row_ids"),
                }
            )
        return batch_entries
    return []


def _statistics_bootstrap_source_metadata(payload: Mapping[str, Any]) -> dict[str, object]:
    columns = payload.get("columns")
    value_columns: list[str] = []
    if isinstance(columns, Sequence) and not isinstance(columns, (str, bytes, bytearray)):
        for column in columns:
            if not isinstance(column, Mapping):
                continue
            value_column = _snapshot_clean_text(column.get("value_column"))
            if value_column:
                value_columns.append(value_column)
    metadata: dict[str, object] = {
        "value_column": value_columns[0] if len(value_columns) == 1 else "",
        "value_columns": value_columns,
        "column_count": len(value_columns),
        "target_statistic": _snapshot_clean_text(payload.get("target_statistic")),
        "confidence_level": _snapshot_clean_text(payload.get("confidence_level")),
        "resample_count": _snapshot_optional_int(payload.get("resample_count")) or 0,
        "method": _snapshot_clean_text(payload.get("method")),
        "seed": payload.get("seed"),
        "seeded": bool(payload.get("seeded")),
        "rng_algorithm": _snapshot_clean_text(payload.get("rng_algorithm")),
        "rng_schedule": _snapshot_clean_text(payload.get("rng_schedule")),
        "sample_mode": _snapshot_clean_text(payload.get("sample_mode")),
    }
    trim_fraction = payload.get("trim_fraction")
    if trim_fraction is not None:
        metadata["trim_fraction"] = _snapshot_clean_text(trim_fraction)
    return metadata


def validate_statistics_bootstrap_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("schema") != STATISTICS_RESULT_SNAPSHOT_SCHEMA:
        raise ValueError("Invalid statistics result snapshot schema.")
    if snapshot.get("schema_version") != STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Invalid statistics result snapshot schema version.")
    if snapshot.get("family") != "statistics":
        raise ValueError("Invalid statistics result snapshot family.")
    if snapshot.get("mode") != BOOTSTRAP_WORKFLOW_MODE:
        raise ValueError("Invalid statistics bootstrap snapshot mode.")
    bootstrap = snapshot.get("bootstrap")
    if not isinstance(bootstrap, Mapping):
        raise TypeError("statistics bootstrap snapshot requires a bootstrap payload.")
    if bootstrap.get("schema") != BOOTSTRAP_PAYLOAD_SCHEMA:
        raise ValueError("Invalid statistics bootstrap snapshot payload schema.")
    validate_statistics_bootstrap_payload(bootstrap)

    source = snapshot.get("source")
    if not isinstance(source, Mapping):
        raise TypeError("statistics bootstrap snapshot source must be a mapping.")
    expected_source = _statistics_bootstrap_source_metadata(bootstrap)
    for key, expected_value in expected_source.items():
        if source.get(key) != expected_value:
            raise ValueError(f"statistics bootstrap snapshot source {key} does not match payload.")

    columns = bootstrap.get("columns")
    batches = snapshot.get("batches")
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray)):
        raise TypeError("statistics bootstrap snapshot payload columns must be a sequence.")
    if not isinstance(batches, Sequence) or isinstance(batches, (str, bytes, bytearray)):
        raise TypeError("statistics bootstrap snapshot batches must be a sequence.")
    if len(batches) != len(columns):
        raise ValueError("statistics bootstrap snapshot batch count does not match payload columns.")

    expected_top_rows: dict[str, list[dict[str, object]]] = {
        "metric_rows": [],
        "diagnostic_rows": [],
        "row_flags": [],
    }
    column_count = _snapshot_optional_int(source.get("column_count")) or 0
    multi_column = column_count > 1
    for index, batch in enumerate(batches):
        if not isinstance(batch, Mapping):
            raise TypeError("statistics bootstrap snapshot batches must contain mappings.")
        batch_source = batch.get("source")
        column = columns[index]
        if not isinstance(batch_source, Mapping) or not isinstance(column, Mapping):
            raise TypeError("statistics bootstrap snapshot source/column entries must be mappings.")
        if batch_source.get("row_count") != column.get("row_count"):
            raise ValueError("statistics bootstrap snapshot row_count does not match payload column.")
        if batch_source.get("value_column") != column.get("value_column"):
            raise ValueError("statistics bootstrap snapshot value_column does not match payload column.")
        if batch_source.get("source_row_ids") != column.get("source_row_ids"):
            raise ValueError("statistics bootstrap snapshot source_row_ids do not match payload column.")
        if (
            multi_column
            and column.get("column_index") is not None
            and batch_source.get("column_index") != column.get("column_index")
        ):
            raise ValueError("statistics bootstrap snapshot column_index does not match payload column.")
        value_col = _snapshot_clean_text(column.get("value_column"))
        expected_rows = analysis_rows_to_json(
            _statistics_rows_with_column_source(
                statistics_bootstrap_analysis_rows_from_column(bootstrap, column),
                column_source=value_col if multi_column else "",
            )
        )
        expected_by_field = {
            "metric_rows": _snapshot_rows_by_group(expected_rows, "metric"),
            "diagnostic_rows": _snapshot_rows_by_group(expected_rows, "diagnostic"),
            "row_flags": _snapshot_rows_by_group(expected_rows, "row_flag"),
        }
        for field, expected_rows_for_field in expected_by_field.items():
            raw_rows = batch.get(field, ())
            if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes, bytearray)):
                raise TypeError(f"statistics bootstrap snapshot {field} must be a sequence.")
            normalized_rows = analysis_rows_to_json(_normalize_statistics_analysis_rows(raw_rows))
            if normalized_rows != expected_rows_for_field:
                raise ValueError(f"statistics bootstrap snapshot {field} rows do not match payload.")
            expected_top_rows[field].extend(expected_rows_for_field)

    for field, expected_rows_for_field in expected_top_rows.items():
        raw_top_rows = snapshot.get(field, ())
        if not isinstance(raw_top_rows, Sequence) or isinstance(raw_top_rows, (str, bytes, bytearray)):
            raise TypeError(f"statistics bootstrap snapshot top-level {field} must be a sequence.")
        normalized_top_rows = analysis_rows_to_json(_normalize_statistics_analysis_rows(raw_top_rows))
        if normalized_top_rows != expected_rows_for_field:
            raise ValueError(f"statistics bootstrap snapshot top-level rows do not match payload for {field}.")


def _snapshot_statistics_core_payload(
    result: Mapping[str, Any],
    *,
    mode: str,
    row_count: int | None,
    source_row_ids: Sequence[str | int],
    precision: Mapping[str, Any] | None,
) -> dict[str, object]:
    precision_digits = _snapshot_optional_int((precision or {}).get("compute_digits"))
    payload: dict[str, object] = {
        "mode": mode,
        "row_count": row_count if row_count is not None else len(source_row_ids),
        "precision_used": precision_digits,
        "method_label": _snapshot_clean_text(result.get("method_label") or ""),
        "dropped": _snapshot_optional_int(result.get("dropped")) or 0,
        "zero_sigma_anchor": bool(result.get("zero_sigma_anchor", False)),
    }
    for target_key, source_key in (
        ("mean", "mean"),
        ("trimmed_mean", "trimmed_mean"),
        ("std_mean", "std_mean"),
        ("std", "std"),
        ("variance", "variance"),
        ("min", "v_min"),
        ("max", "v_max"),
        ("median", "median"),
        ("q1", "q1"),
        ("q3", "q3"),
        ("iqr", "iqr"),
        ("mad", "mad"),
        ("skewness", "skewness"),
        ("excess_kurtosis", "excess_kurtosis"),
        ("effective_n", "effective_n"),
        ("weighted_chi_square", "weighted_chi_square"),
        ("weighted_reduced_chi_square", "weighted_reduced_chi_square"),
        ("birge_ratio", "birge_ratio"),
        ("mean_ci_confidence_level", "mean_ci_confidence_level"),
        ("mean_ci_lower", "mean_ci_lower"),
        ("mean_ci_upper", "mean_ci_upper"),
        ("mean_ci_margin", "mean_ci_margin"),
        ("mean_ci_critical_value", "mean_ci_critical_value"),
        ("mean_sample_se_for_ci", "mean_sample_se_for_ci"),
        ("weighted_se_known_sigma", "weighted_se_known_sigma"),
    ):
        source_value = result.get(source_key)
        if source_value is None and target_key in {"min", "max"}:
            source_value = result.get(target_key)
        value = _snapshot_numeric_text(source_value, precision_digits=precision_digits)
        if value is not None:
            payload[target_key] = value
    count = _snapshot_optional_int(result.get("count"))
    if count is not None:
        payload["count"] = count
    consistency_dof = _snapshot_optional_int(result.get("weighted_consistency_dof"))
    if consistency_dof is not None:
        payload["weighted_consistency_dof"] = consistency_dof
    mean_ci_dof = _snapshot_optional_int(result.get("mean_ci_dof"))
    if mean_ci_dof is not None:
        payload["mean_ci_dof"] = mean_ci_dof
    mean_ci_method_label = _snapshot_clean_text(result.get("mean_ci_method_label") or "")
    if mean_ci_method_label:
        payload["mean_ci_method_label"] = mean_ci_method_label
    if source_row_ids:
        payload["source_row_ids"] = list(source_row_ids)
    outlier_flags = _snapshot_outlier_flags(result.get("outlier_flags"))
    if outlier_flags:
        payload["outlier_flags"] = outlier_flags
    return payload


def _snapshot_analysis_rows(
    result: Mapping[str, Any],
    payload: Mapping[str, Any],
    warnings: Sequence[str],
    *,
    column_source: str = "",
) -> list[dict[str, object]]:
    raw_rows = result.get("analysis_rows")
    if raw_rows is not None:
        try:
            return analysis_rows_to_json(
                _statistics_rows_with_column_source(
                    analysis_rows_from_json(raw_rows),
                    column_source=column_source,
                )
            )
        except (TypeError, ValueError):
            pass
    warning_codes = _snapshot_text_list(result.get("warning_codes"))
    return analysis_rows_to_json(
        _statistics_rows_with_column_source(
            statistics_analysis_rows_from_payload(payload, warnings, warning_codes=warning_codes),
            column_source=column_source,
        )
    )


def _statistics_rows_with_column_source(
    rows: Sequence[AnalysisRow],
    *,
    column_source: str,
) -> tuple[AnalysisRow, ...]:
    source = _snapshot_clean_text(column_source)
    if not source:
        return tuple(rows)
    return tuple(
        replace(row, source=source)
        if row.render_group in {"metric", "diagnostic"} and row.source is None
        else row
        for row in rows
    )


def _snapshot_rows_by_group(
    rows: Sequence[Mapping[str, object]],
    group: str,
) -> list[dict[str, object]]:
    return [dict(row) for row in rows if row.get("render_group") == group]


def _snapshot_outlier_flags(value: Any) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    flags: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        source_row_id = item.get("source_row_id")
        if isinstance(source_row_id, bool) or not isinstance(source_row_id, (str, int)):
            continue
        if isinstance(source_row_id, str) and not source_row_id.strip():
            continue
        metric = _snapshot_clean_text(item.get("metric"))
        reason = _snapshot_clean_text(item.get("reason"))
        flag_value = item.get("value")
        if not metric or not reason or isinstance(flag_value, float):
            continue
        normalized_value = _snapshot_numeric_text(flag_value, precision_digits=None)
        if normalized_value is None:
            continue
        flags.append(
            {
                "source_row_id": source_row_id,
                "value": normalized_value,
                "metric": metric,
                "reason": reason,
            }
        )
    return flags


def _snapshot_source_row_ids(value: Any) -> list[str | int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    row_ids: list[str | int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            row_ids.append(item)
        elif isinstance(item, str) and item.strip():
            row_ids.append(item)
    return row_ids


def _snapshot_numeric_text(value: Any, *, precision_digits: int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError("JSON floats are not allowed in statistics snapshot numeric values.")
    try:
        digits = max(1, precision_digits or mp.mp.dps)
        with mp.workdps(digits):
            text = str(mp.nstr(mp.mpf(value), n=digits))
    except Exception:
        text = str(value)
    if text.lower() in {"nan", "+nan", "-nan"}:
        return None
    return text


def _snapshot_plot_spec_keys(kind: str, plots: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: list[str] = []
    for plot in plots:
        key = _snapshot_clean_text(plot.get("plot_key"))
        if key and key not in keys:
            keys.append(key)
    if keys:
        return keys
    if not plots:
        return []
    if kind == "statistics_bootstrap":
        return ["statistics.bootstrap_distribution"]
    return ["statistics.series_with_mean"]


def _snapshot_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _snapshot_text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return []
    return [item for item in (str(item) for item in value) if item]


def _snapshot_warning_texts(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        text = _warning_message_text(value)
        return [text] if text else []
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray)):
        return []
    return [text for text in (_warning_message_text(item) for item in value) if text]


def _snapshot_dedupe_text(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _snapshot_common_mode(modes: Sequence[str]) -> str:
    if not modes:
        return ""
    first = modes[0]
    if all(mode == first for mode in modes):
        return first
    return "mixed"


def _snapshot_plain_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, float):
            continue
        if isinstance(item, Mapping):
            payload[key] = _snapshot_plain_mapping(item)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            payload[key] = [
                _snapshot_plain_mapping(element) if isinstance(element, Mapping) else element
                for element in item
                if not isinstance(element, float)
            ]
        elif isinstance(item, (str, int, bool)) or item is None:
            payload[key] = item
    return payload


def _snapshot_render_batches(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_batches = snapshot.get("batches")
    if isinstance(raw_batches, Sequence) and not isinstance(raw_batches, (str, bytes, bytearray)):
        batches = [batch for batch in raw_batches if isinstance(batch, Mapping)]
        if batches:
            return batches
    source = snapshot.get("source")
    source_payload = source if isinstance(source, Mapping) else {}
    return [
        {
            "index": 1,
            "mode": snapshot.get("mode"),
            "metric_rows": snapshot.get("metric_rows") or [],
            "diagnostic_rows": snapshot.get("diagnostic_rows") or [],
            "row_flags": snapshot.get("row_flags") or [],
            "source": {
                "row_count": source_payload.get("row_count"),
                "value_column": source_payload.get("value_column"),
            },
        }
    ]


def _snapshot_render_rows(batch: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for field in ("metric_rows", "row_flags", "diagnostic_rows"):
        raw_rows = batch.get(field)
        if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes, bytearray)):
            rows.extend(
                row
                for row in raw_rows
                if isinstance(row, Mapping) and row.get("render_group") != "plot_annotation"
            )
    return rows


_SNAPSHOT_ROW_LABELS = {
    "method": "Method",
    "row_count": "Rows",
    "count": "Count",
    "mean": "Mean",
    "trimmed_mean": "Trimmed mean",
    "std_mean": "Std. error",
    "mean_ci_lower": "Mean CI lower",
    "mean_ci_upper": "Mean CI upper",
    "mean_ci_margin": "Mean CI margin",
    "mean_ci_confidence_level": "CI level",
    "mean_ci_method": "CI method",
    "mean_sample_se_for_ci": "CI sample SE",
    "weighted_se_known_sigma": "Known-sigma weighted CI SE",
    "mean_ci_dof": "CI dof",
    "mean_ci_critical_value": "CI critical value",
    "bootstrap_original_statistic": "Bootstrap original statistic",
    "bootstrap_ci_lower": "Bootstrap CI lower",
    "bootstrap_ci_median": "Bootstrap CI median",
    "bootstrap_ci_upper": "Bootstrap CI upper",
    "bootstrap_mean": "Bootstrap mean",
    "bootstrap_std": "Bootstrap std. dev.",
    "bootstrap_target_statistic": "Bootstrap target statistic",
    "bootstrap_confidence_level": "Bootstrap CI level",
    "bootstrap_resample_count": "Bootstrap resamples",
    "bootstrap_method": "Bootstrap method",
    "bootstrap_sample_mode": "Bootstrap sample mode",
    "bootstrap_seeded": "Bootstrap seeded",
    "bootstrap_rng_algorithm": "Bootstrap RNG algorithm",
    "bootstrap_rng_schedule": "Bootstrap RNG schedule",
    "bootstrap_requested_sample_count": "Bootstrap requested samples",
    "bootstrap_accepted_sample_count": "Bootstrap accepted samples",
    "bootstrap_rejected_sample_count": "Bootstrap rejected samples",
    "bootstrap_finite_sample_count": "Bootstrap finite samples",
    "bootstrap_seed": "Bootstrap seed",
    "bootstrap_trim_fraction": "Bootstrap trim fraction",
    "std": "Std. dev.",
    "variance": "Variance",
    "min": "Min",
    "max": "Max",
    "median": "Median",
    "q1": "Q1",
    "q3": "Q3",
    "iqr": "IQR",
    "mad": "MAD",
    "skewness": "Skewness",
    "excess_kurtosis": "Excess kurtosis",
    "effective_n": "Effective n",
    "weighted_chi_square": "Weighted chi-square",
    "weighted_consistency_dof": "Weighted consistency dof",
    "weighted_reduced_chi_square": "Weighted reduced chi-square",
    "birge_ratio": "Birge ratio",
    "dropped": "Dropped rows",
    "zero_sigma_anchor": "Zero-sigma anchor",
}


def _snapshot_row_label(row: Mapping[str, Any]) -> str:
    key = _snapshot_clean_text(row.get("key"))
    if _snapshot_row_is_warning(row):
        return "Warning"
    if key in _SNAPSHOT_ROW_LABELS:
        return _SNAPSHOT_ROW_LABELS[key]
    if key.startswith("outlier.sigma."):
        return "Sigma outlier"
    if key.startswith("outlier.robust_modified_z."):
        return "Robust outlier"
    if key.startswith("outlier.robust_mad_zero."):
        return "Robust outlier (MAD=0)"
    message_key = _snapshot_clean_text(row.get("message_key"))
    if message_key:
        return message_key
    label_key = _snapshot_clean_text(row.get("label_key"))
    return label_key or key


def statistics_snapshot_row_label(row: Mapping[str, Any]) -> str:
    """Return the display label used for a statistics semantic snapshot row."""

    return _snapshot_row_label(row)


def _snapshot_row_is_warning(row: Mapping[str, Any]) -> bool:
    key = _snapshot_clean_text(row.get("key"))
    message_key = _snapshot_clean_text(row.get("message_key"))
    return (
        row.get("render_group") == "diagnostic"
        and (
            row.get("severity") == "warning"
            or key.startswith("warning.")
            or message_key.startswith("statistics.warning.")
        )
    )


def _snapshot_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | str):
        return str(value)
    return str(value)


def _snapshot_clean_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _statistics_row_is_outlier_flag(row: AnalysisRow | Mapping[str, Any]) -> bool:
    key = row.key if isinstance(row, AnalysisRow) else _snapshot_clean_text(row.get("key"))
    return key.startswith("outlier.") and (
        row.render_group if isinstance(row, AnalysisRow) else row.get("render_group")
    ) == "row_flag"


def _mpf_or_none(value: Any) -> mp.mpf | None:
    if value is None:
        return None
    try:
        numeric = mp.mpf(value)
    except Exception:
        return None
    if mp.isnan(numeric):
        return None
    return numeric
