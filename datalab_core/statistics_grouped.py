from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from typing import Any

import mpmath as mp

from shared.bilingual import _dual_msg
from shared.parsing import clean_tabular_cell
from shared.precision import precision_guard
from shared.unit_annotations import first_unit_annotation_text
from shared.uncertainty import has_explicit_uncertainty, parse_uncertainty_format

from ._payload import normalize_json_payload
from .jobs import ComputeJobRequest, JobMode, JobOptions
from .results import AnalysisRow, ResultStatus, analysis_rows_from_json
from .session import check_cancelled
from .statistics_helpers import _bool_option

GROUPED_WORKFLOW_MODE = "grouped_statistics"
GROUPED_RESULT_CACHE_KIND = "statistics_grouped"
GROUPED_PAYLOAD_SCHEMA = "datalab.statistics.grouped.v1"
GROUPED_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.statistics"
GROUPED_RESULT_SNAPSHOT_SCHEMA_VERSION = 1

_DIAGNOSTIC_SEVERITIES = {"info", "warning", "error"}
_STANDARD_NUMERIC_STRING_KEYS = {
    "mean",
    "std_mean",
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
    "trimmed_mean",
    "weighted_chi_square",
    "weighted_reduced_chi_square",
    "birge_ratio",
    "mean_ci_confidence_level",
    "mean_ci_lower",
    "mean_ci_upper",
    "mean_ci_margin",
    "mean_ci_critical_value",
    "mean_sample_se_for_ci",
    "weighted_se_known_sigma",
}
_STANDARD_INTEGER_KEYS = {"dropped", "count", "weighted_consistency_dof", "mean_ci_dof", "precision_used"}
_STANDARD_BOOLEAN_KEYS = {"zero_sigma_anchor"}
_STANDARD_TEXT_KEYS = {"mode", "method_label", "mean_ci_method_label"}
_STANDARD_STRUCTURED_KEYS = {"source_row_ids", "warning_codes", "analysis_rows", "outlier_flags"}

StatisticsRunner = Callable[[ComputeJobRequest], Any]


def run_statistics_grouped(
    *,
    precision_digits: int,
    uncertainty_digits: int | None,
    inputs: Mapping[str, Any],
    statistics_runner: StatisticsRunner,
) -> dict[str, Any]:
    """Run grouped statistics by delegating per-group work to standard statistics."""

    with precision_guard(precision_digits) as precision_used:
        headers = _text_sequence(inputs.get("headers", inputs.get("data_headers")), field_name="headers")
        rows = _row_sequence(inputs.get("rows", inputs.get("data_rows")), field_name="rows")
        source_row_ids = _source_row_ids(inputs.get("source_row_ids"), count=len(rows))
        group_column = _required_column(
            inputs.get("group_column"),
            headers=headers,
            field_name="group_column",
        )
        value_columns = _value_columns(inputs, headers=headers)
        sigma_column = _optional_column(inputs.get("sigma_column", inputs.get("sigma_col")), headers=headers)
        stats_mode = _text_option(inputs.get("stats_mode"), default="mean_sample", field_name="stats_mode")
        use_sample = _bool_option(inputs.get("use_sample"), default=True)
        use_weighted_variance = _bool_option(inputs.get("use_weighted_variance"), default=True)
        trim_fraction = inputs.get("trim_fraction")
        if trim_fraction is not None and not isinstance(trim_fraction, str):
            raise ValueError(_dual_msg("trim_fraction 必须是数字字符串或 null。", "trim_fraction must be a numeric string or null."))

        group_index = headers.index(group_column)
        value_indexes = {column: headers.index(column) for column in value_columns}
        sigma_index = headers.index(sigma_column) if sigma_column else None
        groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        diagnostics: list[dict[str, object]] = []

        for row_index, row in enumerate(rows):
            if row_index % 256 == 0:
                check_cancelled()
            row_id = source_row_ids[row_index]
            group_label = clean_tabular_cell(row[group_index] if group_index < len(row) else "")
            if not group_label:
                diagnostics.append(
                    _diagnostic(
                        "blank_group",
                        "Blank group labels are excluded from grouped statistics.",
                        source_row_id=row_id,
                    )
                )
                continue
            if group_label not in groups:
                groups[group_label] = {
                    "group": group_label,
                    "group_index": len(groups) + 1,
                    "group_source_row_ids": [],
                    "_columns": {
                        column: {
                            "value_column": column,
                            "values": [],
                            "sigmas": [],
                            "included_source_row_ids": [],
                            "skipped_source_row_ids": [],
                        }
                        for column in value_columns
                    },
                }
            group_state = groups[group_label]
            group_state["group_source_row_ids"].append(row_id)
            for column, value_index in value_indexes.items():
                column_state = group_state["_columns"][column]
                cell = clean_tabular_cell(row[value_index] if value_index < len(row) else "")
                if not cell:
                    column_state["skipped_source_row_ids"].append(row_id)
                    diagnostics.append(
                        _diagnostic(
                            "blank_value",
                            f"Blank value cell skipped for group {group_label} and column {column}.",
                            source_row_id=row_id,
                            group=group_label,
                            column=column,
                        )
                    )
                    continue
                value_text, embedded_sigma_text = _parse_value_cell(
                    cell,
                    precision_digits=precision_used,
                    field_name=f"rows[{row_index}][{column}]",
                )
                sigma_text = embedded_sigma_text
                if sigma_index is not None:
                    sigma_cell = clean_tabular_cell(row[sigma_index] if sigma_index < len(row) else "")
                    sigma_text = None
                    if sigma_cell:
                        sigma_text, _ = _parse_value_cell(
                            sigma_cell,
                            precision_digits=precision_used,
                            field_name=f"rows[{row_index}][{sigma_column}]",
                        )
                column_state["values"].append(value_text)
                column_state["sigmas"].append(sigma_text)
                column_state["included_source_row_ids"].append(row_id)

        output_groups: list[dict[str, object]] = []
        for group_label, group_state in groups.items():
            check_cancelled()
            output_columns: list[dict[str, object]] = []
            for column in value_columns:
                column_state = group_state["_columns"][column]
                values = tuple(column_state["values"])
                sigmas = tuple(column_state["sigmas"])
                included_ids = tuple(column_state["included_source_row_ids"])
                skipped_ids = tuple(column_state["skipped_source_row_ids"])
                if values:
                    result_payload, warnings = _run_standard_statistics(
                        statistics_runner=statistics_runner,
                        values=values,
                        sigmas=sigmas,
                        source_row_ids=included_ids,
                        stats_mode=stats_mode,
                        use_sample=use_sample,
                        use_weighted_variance=use_weighted_variance,
                        trim_fraction=trim_fraction,
                        precision_digits=precision_used,
                        uncertainty_digits=uncertainty_digits,
                        request_id=f"grouped-{group_state['group_index']}-{column}",
                    )
                    row_count = int(result_payload.get("row_count") or len(values))
                else:
                    diagnostics.append(
                        _diagnostic(
                            "empty_group_column",
                            f"No numeric values for group {group_label} and column {column}.",
                            group=group_label,
                            column=column,
                        )
                    )
                    result_payload = None
                    warnings = []
                    row_count = 0
                output_columns.append(
                    {
                        "value_column": column,
                        "input_row_count": len(group_state["group_source_row_ids"]),
                        "row_count": row_count,
                        "included_source_row_ids": list(included_ids),
                        "skipped_source_row_ids": list(skipped_ids),
                        "result": result_payload,
                        "warnings": list(warnings),
                    }
                )
            output_groups.append(
                {
                    "group": group_label,
                    "group_index": int(group_state["group_index"]),
                    "group_source_row_ids": list(group_state["group_source_row_ids"]),
                    "columns": output_columns,
                }
            )

        if not output_groups:
            raise ValueError(_dual_msg("分组统计未找到任何非空分组。", "grouped statistics found no nonblank groups."))
        payload: dict[str, object] = {
            "schema": GROUPED_PAYLOAD_SCHEMA,
            "workflow_mode": GROUPED_WORKFLOW_MODE,
            "stats_mode": stats_mode,
            "group_column": group_column,
            "value_columns": list(value_columns),
            "group_order": [str(group["group"]) for group in output_groups],
            "row_count": len(rows),
            "source_row_ids": list(source_row_ids),
            "groups": output_groups,
            "diagnostics": diagnostics,
            "precision_used": precision_used,
        }

    validate_statistics_grouped_payload(payload)
    normalized = normalize_json_payload(payload, path="statistics_grouped_payload")
    if not isinstance(normalized, Mapping):
        raise TypeError(_dual_msg("分组统计载荷必须归一化为映射。", "statistics grouped payload must normalize to a mapping."))
    return dict(normalized)


def validate_statistics_grouped_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(_dual_msg("分组统计载荷必须是映射。", "statistics grouped payload must be a mapping."))
    _reject_json_floats(payload, path="statistics_grouped_payload")
    _require_keys(
        payload,
        {
            "schema",
            "workflow_mode",
            "stats_mode",
            "group_column",
            "value_columns",
            "group_order",
            "row_count",
            "source_row_ids",
            "groups",
            "diagnostics",
            "precision_used",
        },
        "statistics_grouped_payload",
    )
    if payload.get("schema") != GROUPED_PAYLOAD_SCHEMA:
        raise ValueError(_dual_msg("分组统计载荷的 schema 不受支持。", "statistics grouped payload schema is unsupported."))
    if payload.get("workflow_mode") != GROUPED_WORKFLOW_MODE:
        raise ValueError(_dual_msg("分组统计的 workflow_mode 不受支持。", "statistics grouped workflow_mode is unsupported."))
    _required_text(payload.get("stats_mode"), "stats_mode")
    _required_text(payload.get("group_column"), "group_column")
    value_columns = _required_text_list(payload.get("value_columns"), "value_columns")
    group_order = _required_text_list(payload.get("group_order"), "group_order")
    if len(set(value_columns)) != len(value_columns):
        raise ValueError(_dual_msg("分组统计的 value_columns 必须唯一。", "statistics grouped value_columns must be unique."))
    if len(set(group_order)) != len(group_order):
        raise ValueError(_dual_msg("分组统计的 group_order 必须唯一。", "statistics grouped group_order must be unique."))
    row_count = _non_negative_int(payload.get("row_count"), field_name="row_count")
    source_row_ids = _required_source_row_ids(payload.get("source_row_ids"), field_name="source_row_ids")
    if len(source_row_ids) != row_count:
        raise ValueError(_dual_msg("分组统计的 source_row_ids 必须与 row_count 匹配。", "statistics grouped source_row_ids must match row_count."))
    groups = _required_sequence(payload.get("groups"), "groups")
    if len(groups) != len(group_order):
        raise ValueError(_dual_msg("分组统计的 groups 必须与 group_order 匹配。", "statistics grouped groups must match group_order."))
    seen_indexes: set[int] = set()
    for expected_index, group in enumerate(groups, 1):
        _validate_group(group, expected_index=expected_index, group_order=group_order, value_columns=value_columns)
        group_index = int(group["group_index"])
        if group_index in seen_indexes:
            raise ValueError(_dual_msg("分组统计的 group_index 值必须唯一。", "statistics grouped group_index values must be unique."))
        seen_indexes.add(group_index)
    _validate_diagnostics(payload.get("diagnostics"))
    _positive_int(payload.get("precision_used"), field_name="precision_used")


def build_statistics_grouped_result_snapshot(
    payload: Mapping[str, Any],
    *,
    overview_state: str,
    plot_metadata: Sequence[Mapping[str, Any]] = (),
    precision: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_statistics_grouped_payload(payload)
    normalized_payload = normalize_json_payload(payload, path="statistics_grouped_snapshot.payload")
    if not isinstance(normalized_payload, Mapping):
        raise TypeError(_dual_msg("分组统计快照载荷必须归一化为映射。", "statistics grouped snapshot payload must normalize to a mapping."))
    payload_dict = {str(key): value for key, value in deepcopy(normalized_payload).items()}
    plots = [_plain_mapping(plot) for plot in plot_metadata]
    source = {
        "group_column": str(payload_dict["group_column"]),
        "value_columns": list(payload_dict["value_columns"]),
        "group_order": list(payload_dict["group_order"]),
        "group_count": len(payload_dict["group_order"]),
        "stats_mode": str(payload_dict["stats_mode"]),
        "row_count": payload_dict["row_count"],
        "source_row_ids": list(payload_dict["source_row_ids"]),
        "precision_used": payload_dict["precision_used"],
    }
    snapshot: dict[str, object] = {
        "schema": GROUPED_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": GROUPED_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "statistics",
        "mode": GROUPED_WORKFLOW_MODE,
        "statistics_grouped": payload_dict,
        "metric_rows": [],
        "diagnostic_rows": _grouped_diagnostic_rows(payload_dict),
        "row_flags": [],
        "warnings": _grouped_warning_messages(payload_dict),
        "plot_spec_keys": [str(plot.get("plot_key")) for plot in plots if plot.get("plot_key")],
        "plot_metadata": {
            "image_mode": "stats",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": source,
        "groups": deepcopy(payload_dict["groups"]),
        "precision": _plain_mapping(precision or {}),
        "compatibility": {
            "result_cache_kind": GROUPED_RESULT_CACHE_KIND,
            "overview_state": str(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_p4_3_c_shared_latex",
        },
        "batches": [],
    }
    normalized_snapshot = normalize_json_payload(snapshot, path="statistics_grouped_result_snapshot")
    if not isinstance(normalized_snapshot, Mapping):
        raise TypeError(_dual_msg("分组统计快照必须归一化为映射。", "statistics grouped snapshot must normalize to a mapping."))
    output = {str(key): value for key, value in deepcopy(normalized_snapshot).items()}
    validate_statistics_grouped_snapshot(output)
    return output


def validate_statistics_grouped_snapshot(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot, Mapping):
        raise TypeError(_dual_msg("分组统计快照必须是映射。", "statistics grouped snapshot must be a mapping."))
    _reject_json_floats(snapshot, path="statistics_grouped_snapshot")
    _require_keys(
        snapshot,
        {
            "schema",
            "schema_version",
            "family",
            "mode",
            "statistics_grouped",
            "source",
            "groups",
            "compatibility",
        },
        "statistics_grouped_snapshot",
    )
    if snapshot.get("schema") != GROUPED_RESULT_SNAPSHOT_SCHEMA:
        raise ValueError(_dual_msg("分组统计快照的 schema 不受支持。", "statistics grouped snapshot schema is unsupported."))
    if snapshot.get("schema_version") != GROUPED_RESULT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(_dual_msg("分组统计快照的 schema_version 不受支持。", "statistics grouped snapshot schema_version is unsupported."))
    if snapshot.get("family") != "statistics" or snapshot.get("mode") != GROUPED_WORKFLOW_MODE:
        raise ValueError(_dual_msg("分组统计快照的 family/mode 不受支持。", "statistics grouped snapshot family/mode is unsupported."))
    payload = _required_mapping(snapshot.get("statistics_grouped"), "statistics_grouped")
    validate_statistics_grouped_payload(payload)
    source = _required_mapping(snapshot.get("source"), "source")
    if source.get("group_column") != payload.get("group_column"):
        raise ValueError(_dual_msg("分组统计快照的 source group_column 与载荷不匹配。", "statistics grouped snapshot source group_column does not match payload."))
    if list(_required_text_list(source.get("value_columns"), "source.value_columns")) != list(
        _required_text_list(payload.get("value_columns"), "payload.value_columns")
    ):
        raise ValueError(_dual_msg("分组统计快照的 source value_columns 与载荷不匹配。", "statistics grouped snapshot source value_columns do not match payload."))
    if list(_required_text_list(source.get("group_order"), "source.group_order")) != list(
        _required_text_list(payload.get("group_order"), "payload.group_order")
    ):
        raise ValueError(_dual_msg("分组统计快照的 source group_order 与载荷不匹配。", "statistics grouped snapshot source group_order does not match payload."))
    if source.get("group_count") != len(_required_text_list(payload.get("group_order"), "payload.group_order")):
        raise ValueError(_dual_msg("分组统计快照的 source group_count 与载荷不匹配。", "statistics grouped snapshot source group_count does not match payload."))
    for key in ("stats_mode", "row_count", "precision_used"):
        if source.get(key) != payload.get(key):
            raise ValueError(_dual_msg(f"分组统计快照的 source {key} 与载荷不匹配。", f"statistics grouped snapshot source {key} does not match payload."))
    if list(_required_source_row_ids(source.get("source_row_ids"), field_name="source.source_row_ids")) != list(
        _required_source_row_ids(payload.get("source_row_ids"), field_name="payload.source_row_ids")
    ):
        raise ValueError(_dual_msg("分组统计快照的 source_row_ids 与载荷不匹配。", "statistics grouped snapshot source_row_ids do not match payload."))
    groups = _required_sequence(snapshot.get("groups"), "groups")
    if list(groups) != list(_required_sequence(payload.get("groups"), "payload.groups")):
        raise ValueError(_dual_msg("分组统计快照的 groups 与载荷不匹配。", "statistics grouped snapshot groups do not match payload."))
    if snapshot.get("diagnostic_rows") is not None:
        analysis_rows_from_json(snapshot.get("diagnostic_rows"))
    compatibility = _required_mapping(snapshot.get("compatibility"), "compatibility")
    if compatibility.get("result_cache_kind") != GROUPED_RESULT_CACHE_KIND:
        raise ValueError(_dual_msg("分组统计快照的 compatibility kind 不受支持。", "statistics grouped snapshot compatibility kind is unsupported."))


def statistics_grouped_payload_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    validate_statistics_grouped_snapshot(snapshot)
    payload = _required_mapping(snapshot.get("statistics_grouped"), "statistics_grouped")
    return {str(key): value for key, value in deepcopy(payload).items()}


def render_statistics_grouped_payload_outputs(
    payload: Mapping[str, Any],
    *,
    units: Mapping[str, Any] | None = None,
) -> tuple[str, list[dict[str, object]], list[str]]:
    validate_statistics_grouped_payload(payload)
    group_column = _required_text(payload.get("group_column"), "group_column")
    value_columns = _required_text_list(payload.get("value_columns"), "value_columns")
    lines = [
        "=== Statistics: Grouped statistics ===",
        f"Group column: {group_column}",
        f"Value columns: {', '.join(value_columns)}",
        f"Mode: {_required_text(payload.get('stats_mode'), 'stats_mode')}",
        f"Groups: {len(_required_text_list(payload.get('group_order'), 'group_order'))}",
        f"Rows: {payload['row_count']}",
        "",
    ]
    csv_rows: list[dict[str, object]] = []
    groups = _required_sequence(payload.get("groups"), "groups")
    for fallback_group_index, group in enumerate(groups, 1):
        if not isinstance(group, Mapping):
            continue
        group_label = _required_text(group.get("group"), "group")
        group_index = _positive_int(group.get("group_index"), field_name="group_index")
        lines.append(f"## Group {group_index}: {group_label}")
        for column in _required_sequence(group.get("columns"), "columns"):
            if not isinstance(column, Mapping):
                continue
            column_name = _required_text(column.get("value_column"), "value_column")
            row_count = _non_negative_int(column.get("row_count"), field_name="row_count")
            input_row_count = _non_negative_int(column.get("input_row_count"), field_name="input_row_count")
            skipped_count = len(_required_source_row_ids(column.get("skipped_source_row_ids"), field_name="skipped_source_row_ids"))
            lines.extend(
                [
                    "",
                    f"Column: {column_name}",
                    f"Data points n = {row_count} of {input_row_count}",
                ]
            )
            if skipped_count:
                lines.append(f"Skipped blank value cells: {skipped_count}")
            warnings = _text_list(column.get("warnings"), "warnings")
            for warning in warnings:
                lines.append(f"Warning: {warning}")
                csv_rows.append(
                    _grouped_csv_row(
                        group=group_label,
                        column=column_name,
                        batch=group_index or fallback_group_index,
                        metric="warning",
                        value=warning,
                    )
                )
            result = column.get("result")
            if result is None:
                lines.append("No numeric values.")
                csv_rows.append(
                    _grouped_csv_row(
                        group=group_label,
                        column=column_name,
                        batch=group_index or fallback_group_index,
                        metric="empty_group_column",
                        value="No numeric values.",
                    )
                )
                continue
            if not isinstance(result, Mapping):
                raise TypeError(_dual_msg("分组统计列结果必须是映射。", "statistics grouped column result must be a mapping."))
            render_rows = _standard_render_rows(result)
            row_units = {
                str(row.get("key") or row.get("label_key") or "").strip(): _grouped_output_unit(
                    units,
                    column_name,
                    str(row.get("key") or row.get("label_key") or "").strip(),
                )
                for row in render_rows
                if str(row.get("key") or row.get("label_key") or "").strip()
            }
            include_units = any(row_units.values())
            if include_units:
                lines.append("Metric | Value | Value unit | Uncertainty | Uncertainty unit")
                lines.append("--- | --- | --- | --- | ---")
            else:
                lines.append("Metric | Value | Uncertainty")
                lines.append("--- | --- | ---")
            for row in render_rows:
                metric = str(row.get("key") or row.get("label_key") or "").strip()
                if not metric:
                    continue
                value = _cell_text(row.get("value"))
                uncertainty = _cell_text(row.get("uncertainty"))
                if metric.startswith("outlier.") and not uncertainty:
                    uncertainty = _statistics_row_flag_detail(row)
                row_data = _grouped_csv_row(
                    group=group_label,
                    column=column_name,
                    batch=group_index or fallback_group_index,
                    metric=metric,
                    value=value,
                    uncertainty=uncertainty,
                )
                if include_units:
                    unit = row_units.get(metric, "")
                    row_data["value_unit"] = unit
                    row_data["uncertainty_unit"] = unit if uncertainty else ""
                    lines.append(
                        f"{_statistics_row_label(row)} | {value} | {unit} | {uncertainty} | "
                        f"{row_data['uncertainty_unit']}"
                    )
                else:
                    lines.append(f"{_statistics_row_label(row)} | {value} | {uncertainty}")
                csv_rows.append(row_data)
        lines.append("")
    diagnostics = _diagnostic_messages(payload.get("diagnostics"))
    if diagnostics:
        lines.append("Diagnostics:")
        for message in diagnostics:
            lines.append(f"- {message}")
            csv_rows.append(
                _grouped_csv_row(
                    group="",
                    column="",
                    batch=0,
                    metric="diagnostic",
                    value=message,
                )
            )
    headers = ["group", "column", "batch", "metric", "value", "uncertainty"]
    if any("value_unit" in row for row in csv_rows):
        headers.extend(["value_unit", "uncertainty_unit"])
    return "\n".join(lines).rstrip(), csv_rows, headers


def _grouped_output_unit(units: Mapping[str, Any] | None, column_name: str, metric: str) -> str:
    return first_unit_annotation_text(units, "outputs", (metric, column_name, "result"))


def statistics_grouped_mean_overview_spec_from_payload(payload: Mapping[str, Any]) -> Any | None:
    """Build a grouped mean overview plot spec from a validated grouped payload."""

    from shared.plotting import StatisticsGroupedMeanOverviewSpec

    validate_statistics_grouped_payload(payload)
    value_columns = _required_text_list(payload.get("value_columns"), "value_columns")
    include_column_name = len(value_columns) > 1
    labels: list[str] = []
    means: list[Any] = []
    std_means: list[Any | None] = []
    for group in _required_sequence(payload.get("groups"), "groups"):
        if not isinstance(group, Mapping):
            continue
        group_label = _required_text(group.get("group"), "group")
        for column in _required_sequence(group.get("columns"), "columns"):
            if not isinstance(column, Mapping):
                continue
            result = column.get("result")
            if not isinstance(result, Mapping):
                continue
            mean = result.get("mean")
            if _finite_mpf_or_none(mean) is None:
                continue
            column_name = _required_text(column.get("value_column"), "value_column")
            label = f"{group_label} / {column_name}" if include_column_name else group_label
            std_mean = result.get("std_mean")
            std_means.append(std_mean if _non_negative_mpf_or_none(std_mean) is not None else None)
            labels.append(label)
            means.append(mean)
    if not labels:
        return None
    return StatisticsGroupedMeanOverviewSpec(
        labels=tuple(labels),
        means=tuple(means),
        std_means=tuple(std_means),
    )


def _run_standard_statistics(
    *,
    statistics_runner: StatisticsRunner,
    values: Sequence[str],
    sigmas: Sequence[str | None],
    source_row_ids: Sequence[str | int],
    stats_mode: str,
    use_sample: bool,
    use_weighted_variance: bool,
    trim_fraction: object,
    precision_digits: int,
    uncertainty_digits: int | None,
    request_id: str,
) -> tuple[dict[str, Any], list[str]]:
    inputs: dict[str, object] = {
        "values": tuple(values),
        "sigmas": tuple(sigmas),
        "source_row_ids": tuple(source_row_ids),
        "stats_mode": stats_mode,
        "use_sample": use_sample,
        "use_weighted_variance": use_weighted_variance,
    }
    if trim_fraction is not None:
        inputs["trim_fraction"] = trim_fraction
    envelope = statistics_runner(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs=inputs,
            options=JobOptions(
                precision_digits=precision_digits,
                uncertainty_digits=uncertainty_digits,
            ),
            request_id=request_id,
        )
    )
    if getattr(envelope, "status", None) is not ResultStatus.SUCCEEDED:
        payload = getattr(envelope, "payload", {})
        message = payload.get("message") if isinstance(payload, Mapping) else None
        raise ValueError(str(message or _dual_msg("分组统计的标准请求失败。", "Grouped statistics standard request failed.")))
    payload = getattr(envelope, "payload", None)
    if not isinstance(payload, Mapping):
        raise TypeError(_dual_msg("分组统计的标准请求返回了格式错误的载荷。", "Grouped statistics standard request returned malformed payload."))
    result = {str(key): value for key, value in payload.items()}
    _validate_standard_statistics_payload(result)
    return result, [str(item) for item in getattr(envelope, "warnings", ())]


def _parse_value_cell(
    value: str,
    *,
    precision_digits: int,
    field_name: str,
) -> tuple[str, str | None]:
    try:
        uncertain = parse_uncertainty_format(value, precision=precision_digits)
    except Exception as exc:  # noqa: BLE001 - user numeric boundary.
        raise ValueError(_dual_msg(f"{field_name} 不是有效的数值：{value!r}。", f"{field_name} is not a valid numeric value: {value!r}.")) from exc
    parsed_value = mp.mpf(uncertain.value)
    parsed_uncertainty = mp.mpf(uncertain.uncertainty)
    if not mp.isfinite(parsed_value):
        raise ValueError(_dual_msg(f"{field_name} 必须为有限值。", f"{field_name} must be finite."))
    if not mp.isfinite(parsed_uncertainty):
        raise ValueError(_dual_msg(f"{field_name} 的不确定度必须为有限值。", f"{field_name} uncertainty must be finite."))
    digit_count = max(16, int(precision_digits))
    sigma_text = mp.nstr(parsed_uncertainty, n=digit_count) if has_explicit_uncertainty(value) else None
    return mp.nstr(parsed_value, n=digit_count), sigma_text


def _value_columns(inputs: Mapping[str, Any], *, headers: tuple[str, ...]) -> tuple[str, ...]:
    raw = inputs.get("value_columns", inputs.get("columns", inputs.get("value_col")))
    columns = _text_sequence_or_csv(raw, field_name="value_columns")
    if not columns:
        raise ValueError(_dual_msg("分组统计至少需要一个值列。", "grouped statistics require at least one value column."))
    if len(set(columns)) != len(columns):
        raise ValueError(_dual_msg("分组统计的值列必须唯一。", "grouped statistics value columns must be unique."))
    missing = [column for column in columns if column not in headers]
    if missing:
        raise ValueError(_dual_msg(f"未找到该列：{missing[0]}。", f"Column not found: {missing[0]}."))
    return columns


def _text_sequence_or_csv(value: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if value is None:
        return ()
    return _text_sequence(value, field_name=field_name)


def _required_column(value: Any, *, headers: tuple[str, ...], field_name: str) -> str:
    column = _required_text(value, field_name)
    if column not in headers:
        raise ValueError(_dual_msg(f"未找到该列：{column}。", f"Column not found: {column}."))
    return column


def _optional_column(value: Any, *, headers: tuple[str, ...]) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(_dual_msg("sigma_column 必须是字符串。", "sigma_column must be a string."))
    column = value.strip()
    if not column:
        return ""
    if column not in headers:
        raise ValueError(_dual_msg(f"未找到该列：{column}。", f"Column not found: {column}."))
    return column


def _text_sequence(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(_dual_msg(f"{field_name} 必须是字符串列表。", f"{field_name} must be a list of strings."))
    items = tuple(clean_tabular_cell(item) for item in value)
    if not all(items):
        raise ValueError(_dual_msg(f"{field_name} 不得包含空值。", f"{field_name} must not contain blank values."))
    if len(set(items)) != len(items) and field_name == "headers":
        raise ValueError(_dual_msg("分组统计的 headers 必须唯一。", "headers must be unique for grouped statistics."))
    return items


def _row_sequence(value: Any, *, field_name: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(_dual_msg(f"{field_name} 必须是行的列表。", f"{field_name} must be a list of rows."))
    rows: list[tuple[str, ...]] = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            raise ValueError(_dual_msg(f"{field_name}[{index}] 必须是一行。", f"{field_name}[{index}] must be a row."))
        rows.append(tuple(clean_tabular_cell(cell) for cell in row))
    if not rows:
        raise ValueError(_dual_msg(f"{field_name} 必须至少包含一行。", f"{field_name} must contain at least one row."))
    return tuple(rows)


def _source_row_ids(value: Any, *, count: int) -> tuple[str | int, ...]:
    if value is None:
        return tuple(str(index) for index in range(1, count + 1))
    ids = _required_source_row_ids(value, field_name="source_row_ids")
    if len(ids) != count:
        raise ValueError(_dual_msg("source_row_ids 必须与行数匹配。", "source_row_ids must match row count."))
    return ids


def _required_source_row_ids(value: Any, *, field_name: str) -> tuple[str | int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(_dual_msg(f"{field_name} 必须是源行标识符的列表。", f"{field_name} must be a list of source row identifiers."))
    ids: list[str | int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or isinstance(item, float):
            raise ValueError(_dual_msg(f"{field_name}[{index}] 必须是字符串或整数。", f"{field_name}[{index}] must be a string or integer."))
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, str) and item.strip():
            ids.append(item)
        else:
            raise ValueError(_dual_msg(f"{field_name}[{index}] 必须是非空字符串或整数。", f"{field_name}[{index}] must be a nonblank string or integer."))
    return tuple(ids)


def _text_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(_dual_msg(f"{field_name} 必须是字符串。", f"{field_name} must be a string."))
    return value.strip() or default


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: str = "warning",
    source_row_id: str | int | None = None,
    group: str | None = None,
    column: str | None = None,
) -> dict[str, object]:
    output: dict[str, object] = {"severity": severity, "code": code, "message": message}
    if source_row_id is not None:
        output["source_row_id"] = source_row_id
    if group:
        output["group"] = group
    if column:
        output["column"] = column
    return output


def _validate_group(
    group: Any,
    *,
    expected_index: int,
    group_order: Sequence[str],
    value_columns: Sequence[str],
) -> None:
    if not isinstance(group, Mapping):
        raise TypeError(_dual_msg("分组统计的 group 条目必须是映射。", "statistics grouped group entries must be mappings."))
    _require_keys(
        group,
        {"group", "group_index", "group_source_row_ids", "columns"},
        "statistics_grouped_payload.groups[]",
    )
    label = _required_text(group.get("group"), "group")
    if label != group_order[expected_index - 1]:
        raise ValueError(_dual_msg("分组统计的 group order 与 groups 不匹配。", "statistics grouped group order does not match groups."))
    if _positive_int(group.get("group_index"), field_name="group_index") != expected_index:
        raise ValueError(_dual_msg("分组统计的 group_index 值必须连续。", "statistics grouped group_index values must be contiguous."))
    _required_source_row_ids(group.get("group_source_row_ids"), field_name="group_source_row_ids")
    columns = _required_sequence(group.get("columns"), "columns")
    if len(columns) != len(value_columns):
        raise ValueError(_dual_msg("分组统计的 group columns 必须与 value_columns 匹配。", "statistics grouped group columns must match value_columns."))
    seen_columns: set[str] = set()
    for column in columns:
        _validate_group_column(column, value_columns=value_columns)
        name = str(column["value_column"])
        if name in seen_columns:
            raise ValueError(_dual_msg("分组统计的 value_column 条目在每个分组内必须唯一。", "statistics grouped value_column entries must be unique per group."))
        seen_columns.add(name)


def _validate_group_column(column: Any, *, value_columns: Sequence[str]) -> None:
    if not isinstance(column, Mapping):
        raise TypeError(_dual_msg("分组统计的 column 条目必须是映射。", "statistics grouped column entries must be mappings."))
    _require_keys(
        column,
        {
            "value_column",
            "input_row_count",
            "row_count",
            "included_source_row_ids",
            "skipped_source_row_ids",
            "result",
            "warnings",
        },
        "statistics_grouped_payload.groups[].columns[]",
    )
    value_column = _required_text(column.get("value_column"), "value_column")
    if value_column not in value_columns:
        raise ValueError(_dual_msg("分组统计的 column value_column 未被选中。", "statistics grouped column value_column is not selected."))
    input_row_count = _non_negative_int(column.get("input_row_count"), field_name="input_row_count")
    row_count = _non_negative_int(column.get("row_count"), field_name="row_count")
    included = _required_source_row_ids(column.get("included_source_row_ids"), field_name="included_source_row_ids")
    skipped = _required_source_row_ids(column.get("skipped_source_row_ids"), field_name="skipped_source_row_ids")
    if len(included) != row_count:
        raise ValueError(_dual_msg("分组统计的 included_source_row_ids 必须与 row_count 匹配。", "statistics grouped included_source_row_ids must match row_count."))
    if len(included) + len(skipped) != input_row_count:
        raise ValueError(_dual_msg("分组统计的 included/skipped 行 ID 必须与 input_row_count 匹配。", "statistics grouped included/skipped row IDs must match input_row_count."))
    result = column.get("result")
    if row_count == 0:
        if result is not None:
            raise ValueError(_dual_msg("分组统计的空列结果必须为 null。", "statistics grouped empty column result must be null."))
    elif not isinstance(result, Mapping):
        raise TypeError(_dual_msg("分组统计的非空列结果必须是映射。", "statistics grouped non-empty column result must be a mapping."))
    else:
        _validate_standard_statistics_payload(result)
    _text_list(column.get("warnings"), "warnings")


def _validate_standard_statistics_payload(payload: Mapping[str, Any]) -> None:
    _reject_json_floats(payload, path="statistics_grouped_payload.result")
    _require_keys(payload, {"mode", "row_count", "mean", "std_mean", "std", "source_row_ids"}, "result")
    _required_text(payload.get("mode"), "result.mode")
    row_count = _non_negative_int(payload.get("row_count"), field_name="result.row_count")
    ids = _required_source_row_ids(payload.get("source_row_ids"), field_name="result.source_row_ids")
    if len(ids) != row_count:
        raise ValueError(_dual_msg("result.source_row_ids 必须与 result.row_count 匹配。", "result.source_row_ids must match result.row_count."))
    if "warning_codes" in payload:
        _text_list(payload.get("warning_codes"), "result.warning_codes")
    if "analysis_rows" in payload:
        analysis_rows_from_json(payload.get("analysis_rows"))
    if "outlier_flags" in payload:
        _validate_outlier_flags(payload.get("outlier_flags"))
    for key, value in payload.items():
        if value is None:
            continue
        if key in _STANDARD_NUMERIC_STRING_KEYS:
            _numeric_string(value, field_name=f"result.{key}")
            continue
        if key in _STANDARD_INTEGER_KEYS:
            _non_negative_int(value, field_name=f"result.{key}")
            continue
        if key in _STANDARD_BOOLEAN_KEYS:
            _bool_value(value, field_name=f"result.{key}")
            continue
        if key in _STANDARD_TEXT_KEYS or key in _STANDARD_STRUCTURED_KEYS:
            continue
        if isinstance(value, str):
            _finite_numeric_string_or_text(value, field_name=f"result.{key}")


def _numeric_string(value: Any, *, field_name: str) -> mp.mpf:
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是数字字符串。", f"{field_name} must be a numeric string."))
    text = value.strip()
    if not text:
        raise ValueError(_dual_msg(f"{field_name} 不得为空。", f"{field_name} must not be blank."))
    try:
        return mp.mpf(text)
    except Exception as exc:  # noqa: BLE001 - validation boundary for persisted payloads.
        raise ValueError(_dual_msg(f"{field_name} 必须是有效的数字字符串。", f"{field_name} must be a valid numeric string.")) from exc


def _finite_numeric_string(value: Any, *, field_name: str) -> None:
    parsed = _numeric_string(value, field_name=field_name)
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须为有限值。", f"{field_name} must be finite."))


def _finite_numeric_string_or_text(value: str, *, field_name: str) -> None:
    text = value.strip()
    if not text:
        return
    try:
        parsed = mp.mpf(text)
    except Exception:
        return
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须为有限值。", f"{field_name} must be finite."))


def _finite_mpf_or_none(value: Any) -> mp.mpf | None:
    try:
        parsed = mp.mpf(value)
    except Exception:
        return None
    if not mp.isfinite(parsed):
        return None
    return parsed


def _non_negative_mpf_or_none(value: Any) -> mp.mpf | None:
    parsed = _finite_mpf_or_none(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _validate_outlier_flags(value: Any) -> None:
    flags = _required_sequence(value, "result.outlier_flags")
    for index, item in enumerate(flags):
        if not isinstance(item, Mapping):
            raise TypeError(_dual_msg(f"result.outlier_flags[{index}] 必须是映射。", f"result.outlier_flags[{index}] must be a mapping."))
        _require_keys(
            item,
            {"source_row_id", "value", "metric", "reason"},
            f"result.outlier_flags[{index}]",
        )
        _required_source_row_ids(
            (item.get("source_row_id"),),
            field_name=f"result.outlier_flags[{index}].source_row_id",
        )
        _finite_numeric_string(item.get("value"), field_name=f"result.outlier_flags[{index}].value")
        _required_text(item.get("metric"), f"result.outlier_flags[{index}].metric")
        _required_text(item.get("reason"), f"result.outlier_flags[{index}].reason")


def _grouped_diagnostic_rows(payload: Mapping[str, Any]) -> list[dict[str, object]]:
    rows: list[AnalysisRow] = []
    for index, item in enumerate(_required_sequence(payload.get("diagnostics"), "diagnostics")):
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or f"diagnostic.{index + 1}")
        message = str(item.get("message") or code)
        severity = str(item.get("severity") or "warning")
        rows.append(
            AnalysisRow(
                key=f"grouped.{code}",
                label_key="statistics.grouped.diagnostic",
                value=message,
                source=_diagnostic_source(item),
                severity=severity if severity in _DIAGNOSTIC_SEVERITIES else "warning",
                message_key=code,
                render_group="diagnostic",
            )
        )
    return [row.to_json() for row in rows]


def _statistics_row_label(row: Mapping[str, Any]) -> str:
    from .statistics import statistics_snapshot_row_label

    return str(statistics_snapshot_row_label(row))


def _statistics_row_flag_detail(row: Mapping[str, Any]) -> str:
    from .statistics import statistics_row_flag_detail

    return str(statistics_row_flag_detail(row))


def _diagnostic_source(item: Mapping[str, Any]) -> str | None:
    parts: list[str] = []
    group = str(item.get("group") or "").strip()
    column = str(item.get("column") or "").strip()
    source_row_id = item.get("source_row_id")
    if group:
        parts.append(f"group={group}")
    if column:
        parts.append(f"column={column}")
    if source_row_id is not None:
        parts.append(f"source_row_id={source_row_id}")
    return "; ".join(parts) or None


def _grouped_warning_messages(payload: Mapping[str, Any]) -> list[str]:
    messages = _diagnostic_messages(payload.get("diagnostics"))
    for group in _required_sequence(payload.get("groups"), "groups"):
        if not isinstance(group, Mapping):
            continue
        for column in _required_sequence(group.get("columns"), "columns"):
            if not isinstance(column, Mapping):
                continue
            messages.extend(_text_list(column.get("warnings"), "warnings"))
    return _dedupe_text(messages)


def _diagnostic_messages(value: Any) -> list[str]:
    messages: list[str] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return messages
    for item in value:
        if isinstance(item, Mapping):
            message = str(item.get("message") or "").strip()
            if message:
                messages.append(message)
    return messages


def _dedupe_text(values: Sequence[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _standard_render_rows(result: Mapping[str, Any]) -> list[dict[str, object]]:
    raw_rows = result.get("analysis_rows")
    if raw_rows is not None:
        return [
            row.to_json()
            for row in analysis_rows_from_json(raw_rows)
            if row.render_group in {"metric", "row_flag"}
        ]
    rows: list[dict[str, object]] = []
    for key in (
        "mean",
        "std_mean",
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
        "trimmed_mean",
        "weighted_chi_square",
        "weighted_reduced_chi_square",
        "birge_ratio",
        "effective_n",
    ):
        value = result.get(key)
        if value is None:
            continue
        row: dict[str, object] = {
            "key": key,
            "label_key": f"statistics.metric.{key}",
            "value": value,
            "severity": "info",
            "render_group": "metric",
        }
        if key == "mean" and result.get("std_mean") is not None:
            row["uncertainty"] = result.get("std_mean")
        rows.append(row)
    return rows


def _grouped_csv_row(
    *,
    group: str,
    column: str,
    batch: int,
    metric: str,
    value: object,
    uncertainty: object = "",
) -> dict[str, object]:
    return {
        "group": group,
        "column": column,
        "batch": batch,
        "metric": metric,
        "value": value,
        "uncertainty": uncertainty,
    }


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    normalized = normalize_json_payload(value, path="statistics_grouped_plain_mapping")
    if not isinstance(normalized, Mapping):
        raise TypeError(_dual_msg("plain mapping 必须归一化为映射。", "plain mapping must normalize to a mapping."))
    return {str(key): nested for key, nested in deepcopy(normalized).items()}


def _text_list(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是字符串列表。", f"{field_name} must be a list of strings."))
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(_dual_msg(f"{field_name}[{index}] 必须是字符串。", f"{field_name}[{index}] must be a string."))
        items.append(item)
    return tuple(items)


def _validate_diagnostics(value: Any) -> None:
    diagnostics = _required_sequence(value, "diagnostics")
    for item in diagnostics:
        if not isinstance(item, Mapping):
            raise TypeError(_dual_msg("分组统计的 diagnostics 必须是映射。", "statistics grouped diagnostics must be mappings."))
        severity = item.get("severity")
        code = item.get("code")
        message = item.get("message")
        if severity not in _DIAGNOSTIC_SEVERITIES:
            raise ValueError(_dual_msg("分组统计的 diagnostic severity 不受支持。", "statistics grouped diagnostic severity is unsupported."))
        _required_text(code, "diagnostic.code")
        _required_text(message, "diagnostic.message")


def _required_sequence(value: Any, field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是列表。", f"{field_name} must be a list."))
    return tuple(value)


def _required_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(_dual_msg(f"{field_name} 必须是映射。", f"{field_name} must be a mapping."))
    return value


def _required_text_list(value: Any, field_name: str) -> tuple[str, ...]:
    return tuple(_required_text(item, f"{field_name}[]") for item in _required_sequence(value, field_name))


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是字符串。", f"{field_name} must be a string."))
    text = value.strip()
    if not text:
        raise ValueError(_dual_msg(f"{field_name} 不得为空。", f"{field_name} must not be blank."))
    return text


def _bool_value(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(_dual_msg(f"{field_name} 必须是布尔值。", f"{field_name} must be a boolean."))
    return value


def _require_keys(payload: Mapping[str, Any], keys: set[str], path: str) -> None:
    missing = sorted(key for key in keys if key not in payload)
    if missing:
        raise ValueError(_dual_msg(f"{path} 缺少键：{', '.join(missing)}。", f"{path} is missing keys: {', '.join(missing)}."))


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是整数。", f"{field_name} must be an integer."))
    if value <= 0:
        raise ValueError(_dual_msg(f"{field_name} 必须为正数。", f"{field_name} must be positive."))
    return int(value)


def _non_negative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是整数。", f"{field_name} must be an integer."))
    if value < 0:
        raise ValueError(_dual_msg(f"{field_name} 必须为非负数。", f"{field_name} must be non-negative."))
    return int(value)


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{path} 处不允许使用 JSON 浮点数。", f"JSON floats are not allowed at {path}."))
    if isinstance(value, Mapping):
        for key, nested in value.items():
            _reject_json_floats(nested, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, nested in enumerate(value):
            _reject_json_floats(nested, path=f"{path}[{index}]")
