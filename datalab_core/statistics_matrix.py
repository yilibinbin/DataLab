from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

import mpmath as mp

from shared.bilingual import _dual_msg
from shared.precision import precision_guard
from shared.unit_annotations import first_unit_annotation_text

from ._payload import normalize_json_payload

MATRIX_WORKFLOW_MODE = "covariance_correlation"
MATRIX_RESULT_CACHE_KIND = "statistics_matrix"
MATRIX_PAYLOAD_SCHEMA = "datalab.statistics.matrix.v1"
MATRIX_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.statistics"
MATRIX_RESULT_SNAPSHOT_SCHEMA_VERSION = 1

_MISSING_MARKERS = {"", "na", "n/a", "null", "none", "missing"}
_MISSING_POLICIES = {"listwise", "pairwise"}
_DENOMINATORS = {"sample", "population"}
_DIAGNOSTIC_SEVERITIES = {"info", "warning", "error"}


def run_statistics_matrix(*, precision_digits: int, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Run covariance/correlation matrix statistics on nullable tabular rows."""

    with precision_guard(precision_digits) as precision_used:
        columns = _text_sequence(
            inputs.get("value_columns", inputs.get("columns")),
            field_name="value_columns",
        )
        if len(columns) < 2:
            raise ValueError(_dual_msg("协方差/相关性至少需要两个数值列。", "covariance/correlation requires at least two value columns."))
        if len(set(columns)) != len(columns):
            raise ValueError(_dual_msg("协方差/相关性的数值列必须唯一。", "covariance/correlation value columns must be unique."))

        headers = _text_sequence(inputs.get("headers", inputs.get("data_headers")), field_name="headers")
        rows = _row_sequence(inputs.get("rows", inputs.get("data_rows")), field_name="rows")
        source_row_ids = _source_row_ids(inputs.get("source_row_ids"), count=len(rows))
        missing_policy = _choice(
            inputs.get("missing_policy", inputs.get("matrix_missing_policy")),
            _MISSING_POLICIES,
            default="listwise",
            field_name="missing_policy",
        )
        denominator = _denominator(inputs)
        column_indexes = _selected_indexes(headers, columns)
        nullable_rows = _collect_nullable_rows(
            rows=rows,
            column_indexes=column_indexes,
            columns=columns,
        )

        if missing_policy == "listwise":
            payload = _listwise_payload(
                columns=columns,
                nullable_rows=nullable_rows,
                source_row_ids=source_row_ids,
                denominator=denominator,
                precision_digits=precision_used,
            )
        else:
            payload = _pairwise_payload(
                columns=columns,
                nullable_rows=nullable_rows,
                source_row_ids=source_row_ids,
                denominator=denominator,
                precision_digits=precision_used,
            )

        payload["input_row_count"] = len(rows)
        payload["precision_used"] = precision_used

    validate_statistics_matrix_payload(payload)
    normalized = normalize_json_payload(payload, path="statistics_matrix_payload")
    if not isinstance(normalized, Mapping):
        raise TypeError(_dual_msg("统计矩阵载荷必须规范化为映射。", "statistics matrix payload must normalize to a mapping."))
    return dict(normalized)


def validate_statistics_matrix_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(_dual_msg("统计矩阵载荷必须是映射。", "statistics matrix payload must be a mapping."))
    _reject_json_floats(payload, path="statistics_matrix_payload")
    _require_keys(
        payload,
        {
            "schema",
            "workflow_mode",
            "mode",
            "columns",
            "missing_policy",
            "denominator",
            "row_count",
            "input_row_count",
            "source_row_ids",
            "matrices",
            "correlation_components",
            "diagnostics",
            "correlation_metadata",
            "precision_used",
        },
        "statistics_matrix_payload",
    )
    if payload.get("schema") != MATRIX_PAYLOAD_SCHEMA:
        raise ValueError(_dual_msg("不支持该统计矩阵载荷 schema。", "statistics matrix payload schema is unsupported."))
    if payload.get("workflow_mode") != MATRIX_WORKFLOW_MODE or payload.get("mode") != MATRIX_WORKFLOW_MODE:
        raise ValueError(_dual_msg("不支持该统计矩阵工作流模式。", "statistics matrix workflow mode is unsupported."))
    columns = _required_text_list(payload.get("columns"), "columns")
    if len(columns) < 2 or len(set(columns)) != len(columns):
        raise ValueError(_dual_msg("统计矩阵列必须包含至少两个唯一名称。", "statistics matrix columns must contain at least two unique names."))
    size = len(columns)
    missing_policy = _choice(payload.get("missing_policy"), _MISSING_POLICIES, field_name="missing_policy")
    _choice(payload.get("denominator"), _DENOMINATORS, field_name="denominator")
    _non_negative_int(payload.get("row_count"), field_name="row_count")
    _non_negative_int(payload.get("input_row_count"), field_name="input_row_count")
    _positive_int(payload.get("precision_used"), field_name="precision_used")
    source_row_ids = _required_text_list(payload.get("source_row_ids"), "source_row_ids")
    if len(source_row_ids) != payload.get("row_count"):
        raise ValueError(_dual_msg("source_row_ids 必须与 row_count 匹配。", "source_row_ids must match row_count."))

    matrices = _required_mapping(payload.get("matrices"), "matrices")
    _require_keys(matrices, {"covariance", "correlation"}, "matrices")
    covariance = _validate_matrix_block(matrices.get("covariance"), size=size, name="covariance")
    correlation = _validate_matrix_block(matrices.get("correlation"), size=size, name="correlation")
    _validate_symmetric(covariance["values"], "covariance.values")
    _validate_symmetric(correlation["values"], "correlation.values")
    _validate_correlation_values(correlation["values"])

    components = _required_mapping(payload.get("correlation_components"), "correlation_components")
    _require_keys(components, {"mean_x", "mean_y", "variance_x", "variance_y"}, "correlation_components")
    for key in ("mean_x", "mean_y", "variance_x", "variance_y"):
        _validate_numeric_string_matrix(components.get(key), size=size, name=f"correlation_components.{key}")

    metadata = _required_mapping(payload.get("correlation_metadata"), "correlation_metadata")
    _require_keys(metadata, {"source", "row_alignment", "weighted", "budget_eligible"}, "correlation_metadata")
    if metadata.get("source") != "statistics_covariance_correlation":
        raise ValueError(_dual_msg("不支持该相关性元数据 source。", "correlation metadata source is unsupported."))
    expected_alignment = "pairwise" if missing_policy == "pairwise" else "listwise"
    if metadata.get("row_alignment") != expected_alignment:
        raise ValueError(_dual_msg("相关性元数据 row_alignment 与 missing_policy 不匹配。", "correlation metadata row_alignment does not match missing_policy."))
    if metadata.get("weighted") is not False:
        raise ValueError(_dual_msg("首个版本的统计矩阵载荷必须是非加权的。", "first-release statistics matrix payloads must be unweighted."))
    budget_eligible = metadata.get("budget_eligible")
    if not isinstance(budget_eligible, bool):
        raise TypeError(_dual_msg("correlation_metadata.budget_eligible 必须是布尔值。", "correlation_metadata.budget_eligible must be boolean."))
    finite_correlation = all(cell is not None for row in correlation["values"] for cell in row)
    if budget_eligible and (missing_policy != "listwise" or not finite_correlation):
        raise ValueError(_dual_msg("budget_eligible 需要成列删除且有限的相关性单元格。", "budget_eligible requires listwise finite correlation cells."))
    _validate_diagnostics(payload.get("diagnostics"))


def build_statistics_matrix_result_snapshot(
    payload: Mapping[str, Any],
    *,
    overview_state: str,
    plot_metadata: Sequence[Mapping[str, Any]] = (),
    precision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_statistics_matrix_payload(payload)
    normalized_payload = normalize_json_payload(payload, path="statistics_matrix_snapshot.payload")
    if not isinstance(normalized_payload, Mapping):
        raise TypeError(_dual_msg("统计矩阵快照载荷必须规范化为映射。", "statistics matrix snapshot payload must normalize to a mapping."))
    payload_dict = {str(key): value for key, value in deepcopy(normalized_payload).items()}
    matrices = _snapshot_matrices(payload_dict)
    plots = [dict(item) for item in plot_metadata]
    snapshot: dict[str, Any] = {
        "schema": MATRIX_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": MATRIX_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "statistics",
        "mode": MATRIX_WORKFLOW_MODE,
        "statistics_matrix": payload_dict,
        "metric_rows": [],
        "diagnostic_rows": [],
        "row_flags": [],
        "warnings": _diagnostic_messages(payload_dict.get("diagnostics")),
        "plot_spec_keys": [str(plot.get("plot_key")) for plot in plots if plot.get("plot_key")],
        "plot_metadata": {
            "image_mode": "stats",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": {
            "value_columns": list(payload_dict["columns"]),
            "column_count": len(payload_dict["columns"]),
            "missing_policy": str(payload_dict["missing_policy"]),
            "denominator": str(payload_dict["denominator"]),
            "row_count": payload_dict["row_count"],
            "input_row_count": payload_dict["input_row_count"],
            "source_row_ids": list(payload_dict["source_row_ids"]),
        },
        "matrices": matrices,
        "correlation_metadata": dict(payload_dict["correlation_metadata"]),
        "precision": dict(precision or {}),
        "compatibility": {
            "result_cache_kind": MATRIX_RESULT_CACHE_KIND,
            "overview_state": str(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_p4_2_c_shared_latex",
        },
        "batches": [],
    }
    normalized_snapshot = normalize_json_payload(snapshot, path="statistics_matrix_result_snapshot")
    if not isinstance(normalized_snapshot, Mapping):
        raise TypeError(_dual_msg("统计矩阵快照必须规范化为映射。", "statistics matrix snapshot must normalize to a mapping."))
    output = {str(key): value for key, value in deepcopy(normalized_snapshot).items()}
    validate_statistics_matrix_snapshot(output)
    return output


def validate_statistics_matrix_snapshot(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot, Mapping):
        raise TypeError(_dual_msg("统计矩阵快照必须是映射。", "statistics matrix snapshot must be a mapping."))
    _reject_json_floats(snapshot, path="statistics_matrix_snapshot")
    _require_keys(
        snapshot,
        {
            "schema",
            "schema_version",
            "family",
            "mode",
            "statistics_matrix",
            "source",
            "matrices",
            "correlation_metadata",
            "compatibility",
        },
        "statistics_matrix_snapshot",
    )
    if snapshot.get("schema") != MATRIX_RESULT_SNAPSHOT_SCHEMA:
        raise ValueError(_dual_msg("不支持该统计矩阵快照 schema。", "statistics matrix snapshot schema is unsupported."))
    if snapshot.get("schema_version") != MATRIX_RESULT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(_dual_msg("不支持该统计矩阵快照 schema_version。", "statistics matrix snapshot schema_version is unsupported."))
    if snapshot.get("family") != "statistics" or snapshot.get("mode") != MATRIX_WORKFLOW_MODE:
        raise ValueError(_dual_msg("不支持该统计矩阵快照 family/mode。", "statistics matrix snapshot family/mode is unsupported."))
    payload = _required_mapping(snapshot.get("statistics_matrix"), "statistics_matrix")
    validate_statistics_matrix_payload(payload)
    source = _required_mapping(snapshot.get("source"), "source")
    payload_columns = _required_text_list(payload.get("columns"), "payload.columns")
    if _required_text_list(source.get("value_columns"), "source.value_columns") != payload_columns:
        raise ValueError(_dual_msg("统计矩阵快照 source 列与载荷不匹配。", "statistics matrix snapshot source columns do not match payload."))
    if source.get("column_count") != len(payload_columns):
        raise ValueError(_dual_msg("统计矩阵快照 source column_count 与载荷不匹配。", "statistics matrix snapshot source column_count does not match payload."))
    for key in ("missing_policy", "denominator", "row_count", "input_row_count"):
        if source.get(key) != payload.get(key):
            raise ValueError(_dual_msg(f"统计矩阵快照 source {key} 与载荷不匹配。", f"statistics matrix snapshot source {key} does not match payload."))
    if list(_required_text_list(source.get("source_row_ids"), "source.source_row_ids")) != list(
        _required_text_list(payload.get("source_row_ids"), "payload.source_row_ids")
    ):
        raise ValueError(_dual_msg("统计矩阵快照 source_row_ids 与载荷不匹配。", "statistics matrix snapshot source_row_ids do not match payload."))
    matrices = _required_sequence(snapshot.get("matrices"), "matrices")
    matrix_kinds = {str(item.get("kind")) for item in matrices if isinstance(item, Mapping)}
    if matrix_kinds != {"covariance", "correlation"}:
        raise ValueError(_dual_msg("统计矩阵快照必须包含协方差矩阵和相关性矩阵。", "statistics matrix snapshot must include covariance and correlation matrices."))
    if list(matrices) != _snapshot_matrices(payload):
        raise ValueError(_dual_msg("统计矩阵快照 matrices 与载荷不匹配。", "statistics matrix snapshot matrices do not match payload."))
    metadata = _required_mapping(snapshot.get("correlation_metadata"), "correlation_metadata")
    if dict(metadata) != dict(_required_mapping(payload.get("correlation_metadata"), "payload.correlation_metadata")):
        raise ValueError(_dual_msg("统计矩阵快照相关性元数据与载荷不匹配。", "statistics matrix snapshot correlation metadata does not match payload."))
    compatibility = _required_mapping(snapshot.get("compatibility"), "compatibility")
    if compatibility.get("result_cache_kind") != MATRIX_RESULT_CACHE_KIND:
        raise ValueError(_dual_msg("不支持该统计矩阵快照 compatibility kind。", "statistics matrix snapshot compatibility kind is unsupported."))


def statistics_matrix_payload_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_statistics_matrix_snapshot(snapshot)
    payload = _required_mapping(snapshot.get("statistics_matrix"), "statistics_matrix")
    return {str(key): value for key, value in deepcopy(payload).items()}


def render_statistics_matrix_payload_outputs(
    payload: Mapping[str, Any],
    *,
    units: Mapping[str, Any] | None = None,
) -> tuple[str, list[dict[str, object]], list[str]]:
    validate_statistics_matrix_payload(payload)
    columns = _required_text_list(payload.get("columns"), "columns")
    lines = [
        "=== Statistics: Covariance/correlation matrix ===",
        f"Columns: {', '.join(columns)}",
        f"Missing data: {payload['missing_policy']}",
        f"Denominator: {payload['denominator']}",
        f"Rows: {payload['row_count']} of {payload['input_row_count']}",
        "",
    ]
    csv_rows: list[dict[str, object]] = []
    matrices = _required_mapping(payload.get("matrices"), "matrices")
    for kind in ("covariance", "correlation"):
        block = _required_mapping(matrices.get(kind), f"matrices.{kind}")
        unit = _matrix_output_unit(units, kind)
        lines.extend(_render_matrix_block(kind, columns, block, unit=unit))
        lines.append("")
        csv_rows.extend(_matrix_csv_rows(kind, columns, block, unit=unit))
    diagnostics = _diagnostic_messages(payload.get("diagnostics"))
    if diagnostics:
        lines.append("Diagnostics:")
        lines.extend(f"- {message}" for message in diagnostics)
    headers = ["matrix", "row_column", "column", "value", "count", "denominator"]
    if any(str(row.get("unit") or "") for row in csv_rows):
        headers.append("unit")
    return "\n".join(lines).rstrip(), csv_rows, headers


def _listwise_payload(
    *,
    columns: tuple[str, ...],
    nullable_rows: tuple[tuple[mp.mpf | None, ...], ...],
    source_row_ids: tuple[str, ...],
    denominator: str,
    precision_digits: int,
) -> dict[str, Any]:
    included: list[tuple[mp.mpf, ...]] = []
    included_ids: list[str] = []
    for row, row_id in zip(nullable_rows, source_row_ids):
        if any(value is None for value in row):
            continue
        included.append(tuple(mp.mpf(value) for value in row if value is not None))
        included_ids.append(row_id)
    if not included:
        raise ValueError(_dual_msg("协方差/相关性的成列删除策略未留下完整行。", "covariance/correlation listwise policy left no complete rows."))

    values = tuple(included)
    result = _matrix_from_row_provider(
        columns=columns,
        row_provider=lambda _i, _j: values,
        denominator=denominator,
        precision_digits=precision_digits,
        pairwise_rows=False,
    )
    diagnostics = result["diagnostics"]
    budget_eligible = all(cell is not None for row in result["correlation_values"] for cell in row)
    return _payload(
        columns=columns,
        missing_policy="listwise",
        denominator=denominator,
        row_count=len(values),
        source_row_ids=tuple(included_ids),
        result=result,
        diagnostics=diagnostics,
        budget_eligible=budget_eligible,
        precision_digits=precision_digits,
    )


def _pairwise_payload(
    *,
    columns: tuple[str, ...],
    nullable_rows: tuple[tuple[mp.mpf | None, ...], ...],
    source_row_ids: tuple[str, ...],
    denominator: str,
    precision_digits: int,
) -> dict[str, Any]:
    def row_provider(i: int, j: int) -> tuple[tuple[mp.mpf, ...], ...]:
        rows: list[tuple[mp.mpf, ...]] = []
        for row in nullable_rows:
            left = row[i]
            right = row[j]
            if left is None or right is None:
                continue
            rows.append((left, right))
        return tuple(rows)

    result = _matrix_from_row_provider(
        columns=columns,
        row_provider=row_provider,
        denominator=denominator,
        precision_digits=precision_digits,
        pairwise_rows=True,
    )
    diagnostics = [
        _diagnostic(
            "pairwise_not_budget_eligible",
            "Pairwise covariance/correlation uses pair-local rows and is diagnostic-only for future budget aggregation.",
            severity="info",
        ),
        *result["diagnostics"],
    ]
    return _payload(
        columns=columns,
        missing_policy="pairwise",
        denominator=denominator,
        row_count=len(nullable_rows),
        source_row_ids=source_row_ids,
        result=result,
        diagnostics=diagnostics,
        budget_eligible=False,
        precision_digits=precision_digits,
    )


def _matrix_from_row_provider(
    *,
    columns: tuple[str, ...],
    row_provider: Any,
    denominator: str,
    precision_digits: int,
    pairwise_rows: bool,
) -> dict[str, Any]:
    size = len(columns)
    covariance_values: list[list[str | None]] = []
    correlation_values: list[list[str | None]] = []
    counts: list[list[int | None]] = []
    denominators: list[list[int | None]] = []
    mean_x: list[list[str | None]] = []
    mean_y: list[list[str | None]] = []
    variance_x: list[list[str | None]] = []
    variance_y: list[list[str | None]] = []
    diagnostics: list[dict[str, str]] = []

    for i in range(size):
        covariance_row: list[str | None] = []
        correlation_row: list[str | None] = []
        count_row: list[int | None] = []
        denominator_row: list[int | None] = []
        mean_x_row: list[str | None] = []
        mean_y_row: list[str | None] = []
        variance_x_row: list[str | None] = []
        variance_y_row: list[str | None] = []
        for j in range(size):
            rows = tuple(row_provider(i, j))
            x_values = tuple(row[0] if pairwise_rows else row[i] for row in rows)
            y_values = tuple(row[1] if pairwise_rows else row[j] for row in rows)
            count = len(rows)
            denom = _denominator_value(count, denominator)
            count_row.append(count)
            denominator_row.append(denom)
            if denom is None:
                covariance_row.append(None)
                correlation_row.append(None)
                mean_x_row.append(None)
                mean_y_row.append(None)
                variance_x_row.append(None)
                variance_y_row.append(None)
                diagnostics.append(
                    _diagnostic(
                        "insufficient_rows",
                        f"Columns {columns[i]} and {columns[j]} do not have enough rows for {denominator} covariance.",
                        severity="warning",
                    )
                )
                continue

            mean_left = mp.fsum(x_values) / count
            mean_right = mp.fsum(y_values) / count
            cov_xy = mp.fsum((x - mean_left) * (y - mean_right) for x, y in zip(x_values, y_values)) / denom
            var_x = mp.fsum((x - mean_left) ** 2 for x in x_values) / denom
            var_y = mp.fsum((y - mean_right) ** 2 for y in y_values) / denom
            covariance_row.append(_format_mpf(cov_xy, precision_digits))
            mean_x_row.append(_format_mpf(mean_left, precision_digits))
            mean_y_row.append(_format_mpf(mean_right, precision_digits))
            variance_x_row.append(_format_mpf(var_x, precision_digits))
            variance_y_row.append(_format_mpf(var_y, precision_digits))
            if var_x <= 0 or var_y <= 0:
                correlation_row.append(None)
                diagnostics.append(
                    _diagnostic(
                        "zero_variance",
                        f"Correlation is unavailable for columns {columns[i]} and {columns[j]} because a variance is zero.",
                        severity="warning",
                    )
                )
            elif i == j:
                correlation_row.append("1")
            else:
                corr = cov_xy / mp.sqrt(var_x * var_y)
                corr = _clamp_correlation(corr, precision_digits=precision_digits)
                correlation_row.append(_format_mpf(corr, precision_digits))
        covariance_values.append(covariance_row)
        correlation_values.append(correlation_row)
        counts.append(count_row)
        denominators.append(denominator_row)
        mean_x.append(mean_x_row)
        mean_y.append(mean_y_row)
        variance_x.append(variance_x_row)
        variance_y.append(variance_y_row)

    return {
        "covariance_values": covariance_values,
        "correlation_values": correlation_values,
        "counts": counts,
        "denominators": denominators,
        "mean_x": mean_x,
        "mean_y": mean_y,
        "variance_x": variance_x,
        "variance_y": variance_y,
        "diagnostics": diagnostics,
    }


def _payload(
    *,
    columns: tuple[str, ...],
    missing_policy: str,
    denominator: str,
    row_count: int,
    source_row_ids: tuple[str, ...],
    result: Mapping[str, Any],
    diagnostics: Sequence[Mapping[str, str]],
    budget_eligible: bool,
    precision_digits: int,
) -> dict[str, Any]:
    return {
        "schema": MATRIX_PAYLOAD_SCHEMA,
        "workflow_mode": MATRIX_WORKFLOW_MODE,
        "mode": MATRIX_WORKFLOW_MODE,
        "columns": list(columns),
        "missing_policy": missing_policy,
        "denominator": denominator,
        "row_count": row_count,
        "source_row_ids": list(source_row_ids),
        "matrices": {
            "covariance": {
                "values": result["covariance_values"],
                "counts": result["counts"],
                "denominators": result["denominators"],
            },
            "correlation": {
                "values": result["correlation_values"],
                "counts": result["counts"],
                "denominators": result["denominators"],
            },
        },
        "correlation_components": {
            "mean_x": result["mean_x"],
            "mean_y": result["mean_y"],
            "variance_x": result["variance_x"],
            "variance_y": result["variance_y"],
        },
        "diagnostics": [dict(item) for item in diagnostics],
        "correlation_metadata": {
            "source": "statistics_covariance_correlation",
            "row_alignment": missing_policy,
            "weighted": False,
            "budget_eligible": budget_eligible,
        },
        "precision_used": precision_digits,
    }


def _collect_nullable_rows(
    *,
    rows: Sequence[Sequence[Any]],
    column_indexes: tuple[int, ...],
    columns: tuple[str, ...],
) -> tuple[tuple[mp.mpf | None, ...], ...]:
    collected: list[tuple[mp.mpf | None, ...]] = []
    for row_index, row in enumerate(rows):
        values: list[mp.mpf | None] = []
        for column, column_index in zip(columns, column_indexes):
            if column_index >= len(row):
                raise ValueError(_dual_msg(f"第 {row_index + 1} 行缺少列 {column}。", f"Row {row_index + 1} is missing column {column}."))
            values.append(_nullable_mpf(row[column_index], field_name=f"rows[{row_index}][{column}]"))
        collected.append(tuple(values))
    if not collected:
        raise ValueError(_dual_msg("协方差/相关性的行不能为空。", "covariance/correlation rows must not be empty."))
    return tuple(collected)


def _nullable_mpf(value: Any, *, field_name: str) -> mp.mpf | None:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{field_name} 处不允许 JSON 浮点数；请以字符串形式传入数值。", f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings."))
    text = str(value).strip()
    if text.lower() in _MISSING_MARKERS:
        return None
    try:
        parsed = mp.mpf(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(_dual_msg(f"{field_name} 不是有效的数字或受支持的缺失标记：{value!r}。", f"{field_name} is not a valid number or supported missing marker: {value!r}.")) from exc
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限数。", f"{field_name} must be finite."))
    return parsed


def _selected_indexes(headers: tuple[str, ...], columns: tuple[str, ...]) -> tuple[int, ...]:
    indexes: list[int] = []
    for column in columns:
        count = headers.count(column)
        if count == 0:
            raise ValueError(_dual_msg(f"未找到列：{column}。", f"Column not found: {column}."))
        if count > 1:
            raise ValueError(_dual_msg(f"列有歧义：{column}。", f"Column is ambiguous: {column}."))
        indexes.append(headers.index(column))
    return tuple(indexes)


def _denominator(inputs: Mapping[str, Any]) -> str:
    raw = inputs.get("denominator")
    if raw is not None and str(raw).strip():
        return _choice(raw, _DENOMINATORS, field_name="denominator")
    return "sample" if _bool_option(inputs.get("use_sample"), default=True) else "population"


def _denominator_value(count: int, denominator: str) -> int | None:
    if denominator == "sample":
        return count - 1 if count >= 2 else None
    if denominator == "population":
        return count if count >= 1 else None
    raise ValueError(_dual_msg(f"不支持的分母：{denominator}。", f"Unsupported denominator: {denominator}."))


def _text_sequence(value: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [item.strip() for item in value.replace(",", " ").split()]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview)):
        items = [str(item).strip() for item in value]
    else:
        raise TypeError(_dual_msg(f"{field_name} 必须是字符串或序列。", f"{field_name} must be a string or sequence."))
    result = tuple(item for item in items if item)
    if not result:
        raise ValueError(_dual_msg(f"{field_name} 不能为空。", f"{field_name} must not be empty."))
    return result


def _row_sequence(value: Any, *, field_name: str) -> tuple[tuple[Any, ...], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是行的序列。", f"{field_name} must be a sequence of rows."))
    rows: list[tuple[Any, ...]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(_dual_msg(f"{field_name}[{index}] 必须是行序列。", f"{field_name}[{index}] must be a row sequence."))
        rows.append(tuple(row))
    if not rows:
        raise ValueError(_dual_msg(f"{field_name} 不能为空。", f"{field_name} must not be empty."))
    return tuple(rows)


def _source_row_ids(value: Any, *, count: int) -> tuple[str, ...]:
    if value is None:
        return tuple(str(index + 1) for index in range(count))
    ids = _text_sequence(value, field_name="source_row_ids")
    if len(ids) != count:
        raise ValueError(_dual_msg("source_row_ids 长度必须与行数匹配。", "source_row_ids length must match row count."))
    return ids


def _choice(value: Any, choices: set[str], *, field_name: str, default: str | None = None) -> str:
    text = default if value is None else str(value).strip()
    if not text:
        if default is None:
            raise ValueError(_dual_msg(f"{field_name} 不能为空。", f"{field_name} must not be empty."))
        text = default
    if text not in choices:
        raise ValueError(_dual_msg(f"{field_name} 必须是以下之一：{', '.join(sorted(choices))}。", f"{field_name} must be one of: {', '.join(sorted(choices))}."))
    return text


def _bool_option(value: Any, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise TypeError(_dual_msg("布尔选项必须是布尔值或布尔字符串。", "boolean option must be a boolean or boolean string."))


def _format_mpf(value: mp.mpf, precision_digits: int) -> str:
    return str(mp.nstr(value, n=max(2, precision_digits), strip_zeros=False))


def _clamp_correlation(value: mp.mpf, *, precision_digits: int) -> mp.mpf:
    tolerance_digits = max(8, precision_digits - 4)
    tolerance = mp.power(10, -tolerance_digits)
    if value > 1 and value - 1 <= tolerance:
        return mp.mpf("1")
    if value < -1 and -1 - value <= tolerance:
        return mp.mpf("-1")
    return value


def _diagnostic(code: str, message: str, *, severity: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _require_keys(mapping: Mapping[str, Any], keys: set[str], path: str) -> None:
    missing = keys - set(mapping.keys())
    if missing:
        raise ValueError(_dual_msg(f"{path} 缺少必需的键：{', '.join(sorted(missing))}。", f"{path} missing required keys: {', '.join(sorted(missing))}."))


def _required_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(_dual_msg(f"{field_name} 必须是映射。", f"{field_name} must be a mapping."))
    return value


def _required_sequence(value: Any, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是序列。", f"{field_name} must be a sequence."))
    return value


def _required_text_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是字符串序列。", f"{field_name} must be a sequence of strings."))
    result = tuple(str(item) for item in value)
    if any(not item for item in result):
        raise ValueError(_dual_msg(f"{field_name} 不能包含空字符串。", f"{field_name} must not contain empty strings."))
    return result


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是整数。", f"{field_name} must be an integer."))
    if value <= 0:
        raise ValueError(_dual_msg(f"{field_name} 必须是正数。", f"{field_name} must be positive."))
    return int(value)


def _non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是整数。", f"{field_name} must be an integer."))
    if value < 0:
        raise ValueError(_dual_msg(f"{field_name} 必须是非负数。", f"{field_name} must be non-negative."))
    return int(value)


def _validate_matrix_block(value: Any, *, size: int, name: str) -> dict[str, list[list[Any]]]:
    block = _required_mapping(value, name)
    _require_keys(block, {"values", "counts", "denominators"}, name)
    values = _validate_numeric_string_matrix(block.get("values"), size=size, name=f"{name}.values")
    counts = _validate_optional_int_matrix(block.get("counts"), size=size, name=f"{name}.counts")
    denominators = _validate_optional_int_matrix(
        block.get("denominators"),
        size=size,
        name=f"{name}.denominators",
    )
    for row_index in range(size):
        for column_index in range(size):
            if values[row_index][column_index] is None:
                continue
            if counts[row_index][column_index] is None or denominators[row_index][column_index] is None:
                raise ValueError(_dual_msg(f"{name} 的数值单元格需要计数和分母。", f"{name} numeric cells require count and denominator."))
    return {"values": values, "counts": counts, "denominators": denominators}


def _validate_numeric_string_matrix(value: Any, *, size: int, name: str) -> list[list[str | None]]:
    matrix = _square_matrix(value, size=size, name=name)
    normalized: list[list[str | None]] = []
    for row_index, row in enumerate(matrix):
        normalized_row: list[str | None] = []
        for column_index, cell in enumerate(row):
            if cell is None:
                normalized_row.append(None)
                continue
            if not isinstance(cell, str):
                raise TypeError(_dual_msg(f"{name}[{row_index}][{column_index}] 必须是字符串或 null。", f"{name}[{row_index}][{column_index}] must be a string or null."))
            _finite_numeric_string(cell, field_name=f"{name}[{row_index}][{column_index}]")
            normalized_row.append(cell)
        normalized.append(normalized_row)
    return normalized


def _validate_optional_int_matrix(value: Any, *, size: int, name: str) -> list[list[int | None]]:
    matrix = _square_matrix(value, size=size, name=name)
    normalized: list[list[int | None]] = []
    for row_index, row in enumerate(matrix):
        normalized_row: list[int | None] = []
        for column_index, cell in enumerate(row):
            if cell is None:
                normalized_row.append(None)
                continue
            normalized_row.append(_non_negative_int(cell, field_name=f"{name}[{row_index}][{column_index}]"))
        normalized.append(normalized_row)
    return normalized


def _square_matrix(value: Any, *, size: int, name: str) -> list[list[Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{name} 必须是矩阵。", f"{name} must be a matrix."))
    if len(value) != size:
        raise ValueError(_dual_msg(f"{name} 的行数必须与列数匹配。", f"{name} row count must match columns."))
    result: list[list[Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(_dual_msg(f"{name}[{index}] 必须是行序列。", f"{name}[{index}] must be a row sequence."))
        if len(row) != size:
            raise ValueError(_dual_msg(f"{name}[{index}] 的列数必须与列数匹配。", f"{name}[{index}] column count must match columns."))
        result.append(list(row))
    return result


def _validate_symmetric(values: Sequence[Sequence[str | None]], name: str) -> None:
    size = len(values)
    for i in range(size):
        for j in range(size):
            left = values[i][j]
            right = values[j][i]
            if left is None or right is None:
                if left is not right:
                    raise ValueError(_dual_msg(f"{name} 的 null 单元格必须对称。", f"{name} null cells must be symmetric."))
                continue
            if mp.almosteq(mp.mpf(left), mp.mpf(right), rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40")):
                continue
            raise ValueError(_dual_msg(f"{name} 必须对称。", f"{name} must be symmetric."))


def _validate_correlation_values(values: Sequence[Sequence[str | None]]) -> None:
    for row_index, row in enumerate(values):
        for column_index, cell in enumerate(row):
            if cell is None:
                continue
            numeric = mp.mpf(cell)
            if numeric < -1 - mp.mpf("1e-30") or numeric > 1 + mp.mpf("1e-30"):
                raise ValueError(_dual_msg("相关性值必须在 [-1, 1] 范围内。", "correlation values must be within [-1, 1]."))
            if row_index == column_index and not mp.almosteq(numeric, 1, rel_eps=mp.mpf("1e-30"), abs_eps=mp.mpf("1e-30")):
                raise ValueError(_dual_msg("有限的相关性对角线单元格必须为 1。", "finite correlation diagonal cells must be 1."))


def _finite_numeric_string(value: str, *, field_name: str) -> mp.mpf:
    try:
        parsed = mp.mpf(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(_dual_msg(f"{field_name} 必须是数值字符串。", f"{field_name} must be a numeric string.")) from exc
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限数。", f"{field_name} must be finite."))
    return parsed


def _validate_diagnostics(value: Any) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg("diagnostics 必须是序列。", "diagnostics must be a sequence."))
    for index, item in enumerate(value):
        diagnostic = _required_mapping(item, f"diagnostics[{index}]")
        _require_keys(diagnostic, {"code", "severity", "message"}, f"diagnostics[{index}]")
        if str(diagnostic.get("severity")) not in _DIAGNOSTIC_SEVERITIES:
            raise ValueError(_dual_msg("不支持该诊断 severity。", "diagnostic severity is unsupported."))
        for key in ("code", "message"):
            if not isinstance(diagnostic.get(key), str) or not diagnostic.get(key):
                raise ValueError(_dual_msg(f"diagnostics[{index}].{key} 必须是非空字符串。", f"diagnostics[{index}].{key} must be a non-empty string."))


def _diagnostic_messages(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return []
    messages: list[str] = []
    for item in value:
        if isinstance(item, Mapping) and item.get("message"):
            messages.append(str(item["message"]))
    return messages


def _snapshot_matrices(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    matrices = _required_mapping(payload.get("matrices"), "matrices")
    output: list[dict[str, Any]] = []
    for kind in ("covariance", "correlation"):
        block = _required_mapping(matrices.get(kind), f"matrices.{kind}")
        output.append(
            {
                "kind": kind,
                "columns": list(payload["columns"]),
                "values": deepcopy(block["values"]),
                "counts": deepcopy(block["counts"]),
                "denominators": deepcopy(block["denominators"]),
            }
        )
    return output


def _render_matrix_block(kind: str, columns: tuple[str, ...], block: Mapping[str, Any], *, unit: str = "") -> list[str]:
    values = _square_matrix(block.get("values"), size=len(columns), name=f"{kind}.values")
    lines = [kind.capitalize(), "row_column | " + " | ".join(columns), "---" + " | ---" * len(columns)]
    if unit:
        lines.insert(1, f"Unit: {unit}")
    for row_column, row in zip(columns, values):
        cells = [_display_cell(cell) for cell in row]
        lines.append(f"{row_column} | " + " | ".join(cells))
    return lines


def _matrix_csv_rows(
    kind: str,
    columns: tuple[str, ...],
    block: Mapping[str, Any],
    *,
    unit: str = "",
) -> list[dict[str, object]]:
    values = _square_matrix(block.get("values"), size=len(columns), name=f"{kind}.values")
    counts = _square_matrix(block.get("counts"), size=len(columns), name=f"{kind}.counts")
    denominators = _square_matrix(block.get("denominators"), size=len(columns), name=f"{kind}.denominators")
    rows: list[dict[str, object]] = []
    for row_index, row_column in enumerate(columns):
        for column_index, column in enumerate(columns):
            row = {
                "matrix": kind,
                "row_column": row_column,
                "column": column,
                "value": "" if values[row_index][column_index] is None else str(values[row_index][column_index]),
                "count": "" if counts[row_index][column_index] is None else counts[row_index][column_index],
                "denominator": (
                    ""
                    if denominators[row_index][column_index] is None
                    else denominators[row_index][column_index]
                ),
            }
            if unit:
                row["unit"] = unit
            rows.append(row)
    return rows


def _matrix_output_unit(units: Mapping[str, Any] | None, kind: str) -> str:
    if kind != "covariance":
        return ""
    return first_unit_annotation_text(units, "outputs", ("covariance", "result"))


def _display_cell(value: Any) -> str:
    return "--" if value is None else str(value)


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{path} 处不允许 JSON 浮点数；请以字符串形式传入数值。", f"JSON floats are not allowed at {path}; pass numeric inputs as strings."))
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, float):
                raise TypeError(_dual_msg(f"{path}.<key> 处不允许 JSON 浮点数。", f"JSON floats are not allowed at {path}.<key>."))
            _reject_json_floats(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, item in enumerate(value):
            _reject_json_floats(item, path=f"{path}[{index}]")
