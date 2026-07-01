from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from mpmath import mp

from shared.precision import precision_guard

from ._payload import normalize_json_payload
from .results import AnalysisRow, analysis_rows_from_json, analysis_rows_to_json
from .statistics_grouped import GROUPED_WORKFLOW_MODE, statistics_grouped_payload_from_snapshot
from .statistics_time_series import TIME_SERIES_WORKFLOW_MODE, time_series_payload_from_snapshot

HISTORY_COMPARISON_SCHEMA = "datalab.history.compare.v1"
HISTORY_COMPARISON_SCHEMA_VERSION = 1
_SUPPORTED_RESULT_SCHEMA_VERSION = 1

_METADATA_PREFIXES = (
    "comparison.",
    "taylor_order_comparison.",
    "propagation.",
)
_FITTING_METRICS = ("chi2", "reduced_chi2", "aic", "bic", "rmse", "r2")
_SUPPORTED_SCHEMAS = {
    "statistics": "datalab.result_snapshot.statistics",
    "fitting_comparison": "datalab.result_snapshot.fitting_comparison",
    "root_solving": "datalab.result_snapshot.root_solving",
    "uncertainty": "datalab.result_snapshot.uncertainty",
}


@dataclass(frozen=True)
class HistoryComparisonRequest:
    left: Mapping[str, Any]
    right: Mapping[str, Any]
    left_label: str = "Left"
    right_label: str = "Right"
    left_id: str | None = None
    right_id: str | None = None

    def __post_init__(self) -> None:
        left = normalize_json_payload(self.left, path="left")
        right = normalize_json_payload(self.right, path="right")
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            raise TypeError("history comparison snapshots must be mappings.")
        object.__setattr__(self, "left", left)
        object.__setattr__(self, "right", right)
        object.__setattr__(self, "left_label", _label(self.left_label, "left_label"))
        object.__setattr__(self, "right_label", _label(self.right_label, "right_label"))
        object.__setattr__(self, "left_id", _optional_label(self.left_id, "left_id"))
        object.__setattr__(self, "right_id", _optional_label(self.right_id, "right_id"))


@dataclass(frozen=True)
class HistoryComparisonResult:
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        payload = normalize_json_payload(self.payload, path="history_comparison")
        if not isinstance(payload, Mapping):
            raise TypeError("history comparison payload must be a mapping.")
        object.__setattr__(self, "payload", payload)

    def to_json(self) -> dict[str, Any]:
        plain = _plain_json(self.payload)
        if not isinstance(plain, dict):
            raise TypeError("history comparison payload must be a mapping.")
        return plain


def build_history_comparison(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str = "Left",
    right_label: str = "Right",
    left_id: str | None = None,
    right_id: str | None = None,
) -> dict[str, Any]:
    """Compare two semantic result snapshots without using display text."""

    try:
        request = HistoryComparisonRequest(
            left=left,
            right=right,
            left_label=left_label,
            right_label=right_label,
            left_id=left_id,
            right_id=right_id,
        )
    except (TypeError, ValueError) as exc:
        return _result_payload(
            left_label=left_label,
            right_label=right_label,
            left_id=left_id,
            right_id=right_id,
            left_family="unknown",
            right_family="unknown",
            left_mode="",
            right_mode="",
            comparison_mode="unavailable",
            rows=[],
            metadata_rows=[],
            diagnostics=[
                _diagnostic(
                    "history.compare.malformed_snapshot",
                    f"malformed snapshot input: {exc}",
                    severity="error",
                )
            ],
        )

    try:
        return _build_history_comparison(request).to_json()
    except (TypeError, ValueError, ArithmeticError) as exc:
        return _result_payload(
            left_label=request.left_label,
            right_label=request.right_label,
            left_id=request.left_id,
            right_id=request.right_id,
            left_family="unknown",
            right_family="unknown",
            left_mode="",
            right_mode="",
            comparison_mode="unavailable",
            rows=[],
            metadata_rows=[],
            diagnostics=[
                _diagnostic(
                    "history.compare.unavailable",
                    f"comparison failed closed: {exc}",
                    severity="error",
                )
            ],
        )


def history_comparison_to_json(result: HistoryComparisonResult | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(result, HistoryComparisonResult):
        return result.to_json()
    normalized = normalize_json_payload(result, path="history_comparison")
    if not isinstance(normalized, Mapping):
        raise TypeError("history comparison payload must be a mapping.")
    plain = _plain_json(normalized)
    if not isinstance(plain, dict):
        raise TypeError("history comparison payload must be a mapping.")
    return plain


def _build_history_comparison(request: HistoryComparisonRequest) -> HistoryComparisonResult:
    left_snapshot = _result_snapshot(request.left)
    right_snapshot = _result_snapshot(request.right)
    left_family = _snapshot_family(request.left, left_snapshot)
    right_family = _snapshot_family(request.right, right_snapshot)
    left_mode = _text(left_snapshot.get("mode"))
    right_mode = _text(right_snapshot.get("mode"))
    metadata_rows = _shared_metadata_rows(
        left_snapshot,
        right_snapshot,
        left_label=request.left_label,
        right_label=request.right_label,
    )

    if not left_snapshot or not right_snapshot:
        malformed_diagnostics = [
            _diagnostic(
                "history.compare.malformed_snapshot",
                "snapshot result payload is missing or malformed",
                severity="error",
            )
        ]
        return HistoryComparisonResult(
            _result_payload(
                left_label=request.left_label,
                right_label=request.right_label,
                left_id=request.left_id,
                right_id=request.right_id,
                left_family=left_family,
                right_family=right_family,
                left_mode=left_mode,
                right_mode=right_mode,
                comparison_mode="unavailable",
                rows=[],
                metadata_rows=metadata_rows,
                diagnostics=malformed_diagnostics,
            )
        )

    if left_family != right_family:
        cross_family_diagnostics = [
            _diagnostic(
                "history.compare.cross_family_unavailable",
                "scientific deltas are unavailable for cross-family comparison",
            ),
            _diagnostic(
                "history.compare.budget_rows_unavailable",
                "budget-row comparison is unavailable until budget rows are supplied",
            ),
        ]
        return HistoryComparisonResult(
            _result_payload(
                left_label=request.left_label,
                right_label=request.right_label,
                left_id=request.left_id,
                right_id=request.right_id,
                left_family=left_family,
                right_family=right_family,
                left_mode=left_mode,
                right_mode=right_mode,
                comparison_mode="cross_family_metadata_only",
                rows=[],
                metadata_rows=metadata_rows,
                diagnostics=cross_family_diagnostics,
                budget_rows=[],
            )
        )

    schema_diagnostics = _schema_diagnostics(left_snapshot, right_snapshot, left_family)
    if schema_diagnostics:
        return HistoryComparisonResult(
            _result_payload(
                left_label=request.left_label,
                right_label=request.right_label,
                left_id=request.left_id,
                right_id=request.right_id,
                left_family=left_family,
                right_family=right_family,
                left_mode=left_mode,
                right_mode=right_mode,
                comparison_mode="unavailable",
                rows=[],
                metadata_rows=metadata_rows,
                diagnostics=schema_diagnostics,
            )
        )

    rows: list[AnalysisRow] = []
    diagnostics: list[AnalysisRow] = []
    adapter = {
        "statistics": _compare_statistics,
        "fitting_comparison": _compare_fitting_comparison,
        "root_solving": _compare_root_solving,
        "uncertainty": _compare_uncertainty,
    }.get(left_family)
    if adapter is None:
        return HistoryComparisonResult(
            _result_payload(
                left_label=request.left_label,
                right_label=request.right_label,
                left_id=request.left_id,
                right_id=request.right_id,
                left_family=left_family,
                right_family=right_family,
                left_mode=left_mode,
                right_mode=right_mode,
                comparison_mode="unavailable",
                rows=[],
                metadata_rows=metadata_rows,
                diagnostics=[
                    _diagnostic(
                        "history.compare.unsupported_family",
                        f"comparison adapter is unavailable for family {left_family!r}",
                        severity="error",
                    )
                ],
            )
        )
    else:
        adapter(
            left_snapshot,
            right_snapshot,
            left_label=request.left_label,
            right_label=request.right_label,
            rows=rows,
            diagnostics=diagnostics,
            metadata_rows=metadata_rows,
        )
    # Lazy import to keep the split cycle-free: history_compare_budget imports the
    # shared formatting helpers from this module at its top level, so this import
    # must resolve at call time (after both modules have loaded), not at module top.
    from .history_compare_budget import _compare_budget_rows

    budget_rows, budget_diagnostics = _compare_budget_rows(
        left_snapshot,
        right_snapshot,
        left_label=request.left_label,
        right_label=request.right_label,
        left_id=request.left_id,
        right_id=request.right_id,
    )
    diagnostics.extend(budget_diagnostics)

    return HistoryComparisonResult(
        _result_payload(
            left_label=request.left_label,
            right_label=request.right_label,
            left_id=request.left_id,
            right_id=request.right_id,
            left_family=left_family,
            right_family=right_family,
            left_mode=left_mode,
            right_mode=right_mode,
            comparison_mode="same_family",
            rows=rows,
            metadata_rows=metadata_rows,
            diagnostics=diagnostics,
            budget_rows=budget_rows,
        )
    )


def _compare_statistics(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    _metadata_change("mode", left.get("mode"), right.get("mode"), metadata_rows, left_label, right_label)
    _metadata_change(
        "source.row_count",
        _source_value(left, "row_count"),
        _source_value(right, "row_count"),
        metadata_rows,
        left_label,
        right_label,
    )
    if left.get("mode") == "hypothesis_tests" or right.get("mode") == "hypothesis_tests":
        for key in ("test_kind", "alternative", "alpha", "backend", "value_columns"):
            _metadata_change(
                f"source.{key}",
                _source_value(left, key),
                _source_value(right, key),
                metadata_rows,
                left_label,
                right_label,
            )
    if left.get("mode") == GROUPED_WORKFLOW_MODE or right.get("mode") == GROUPED_WORKFLOW_MODE:
        _compare_grouped_statistics(
            left,
            right,
            left_label=left_label,
            right_label=right_label,
            rows=rows,
            diagnostics=diagnostics,
            metadata_rows=metadata_rows,
        )
        return
    _compare_numeric_rows(
        _statistics_metric_row_index(left.get("metric_rows"), container_key="left.metric_rows", diagnostics=diagnostics),
        _statistics_metric_row_index(right.get("metric_rows"), container_key="right.metric_rows", diagnostics=diagnostics),
        row_prefix="statistics.metric",
        label_key="history.compare.statistics.metric_delta",
        fields=("value", "uncertainty"),
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
    )
    _compare_diagnostic_changes(
        _row_index(left.get("row_flags"), container_key="left.row_flags", diagnostics=diagnostics),
        _row_index(right.get("row_flags"), container_key="right.row_flags", diagnostics=diagnostics),
        family_prefix="statistics.row_flag",
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
        metadata_rows=metadata_rows,
    )
    _compare_bootstrap_ci_overlap(
        left,
        right,
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
    )
    _compare_time_series_statistics(
        left,
        right,
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
        metadata_rows=metadata_rows,
    )


def _compare_grouped_statistics(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    for key in ("group_column", "value_columns", "group_order", "group_count", "stats_mode"):
        _metadata_change(
            f"source.{key}",
            _source_value(left, key),
            _source_value(right, key),
            metadata_rows,
            left_label,
            right_label,
        )
    if left.get("mode") != GROUPED_WORKFLOW_MODE or right.get("mode") != GROUPED_WORKFLOW_MODE:
        diagnostics.append(
            _diagnostic(
                "statistics.grouped.mode_mismatch",
                "grouped statistics can only be compared to another grouped statistics snapshot",
            )
        )
        return
    try:
        left_rows = _grouped_statistics_metric_index(left, side="left")
        right_rows = _grouped_statistics_metric_index(right, side="right")
    except (TypeError, ValueError) as exc:
        diagnostics.append(
            _diagnostic(
                "statistics.grouped.semantic_snapshot.invalid",
                f"grouped statistics snapshot validation failed: {exc}",
                severity="error",
            )
        )
        return
    compare_precision = max(80, _snapshot_compute_precision(left), _snapshot_compute_precision(right))
    for metric_key in sorted(set(left_rows) | set(right_rows)):
        metric_token = _grouped_metric_token(metric_key)
        left_row = left_rows.get(metric_key)
        right_row = right_rows.get(metric_key)
        if left_row is None or right_row is None:
            diagnostics.append(_missing_row("statistics.grouped", metric_token, left_row, right_row))
            continue
        for field in ("value", "uncertainty"):
            if field not in left_row and field not in right_row:
                continue
            if not _cell(left_row.get(field)) and not _cell(right_row.get(field)):
                continue
            left_value = _parse_number(left_row.get(field), percent=False, precision_digits=compare_precision)
            right_value = _parse_number(right_row.get(field), percent=False, precision_digits=compare_precision)
            if left_value is None or right_value is None:
                diagnostics.append(
                    _diagnostic(
                        f"statistics.grouped.{metric_token}.{field}.non_numeric",
                        f"non-numeric grouped statistics field {field!r} for {metric_key!r}",
                    )
                )
                continue
            _append_delta_from_values(
                left_value,
                right_value,
                key=f"statistics.grouped.{metric_token}.{field}",
                label_key="history.compare.statistics.grouped_metric_delta",
                left_raw=left_row.get(field),
                right_raw=right_row.get(field),
                left_label=left_label,
                right_label=right_label,
                rows=rows,
                precision_digits=compare_precision,
                display_digits=compare_precision,
            )


def _compare_fitting_comparison(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    _metadata_change(
        "source.candidate_count",
        _source_value(left, "candidate_count"),
        _source_value(right, "candidate_count"),
        metadata_rows,
        left_label,
        right_label,
    )
    left_rows = _candidate_index(
        left.get("comparison_rows"), container_key="left.comparison_rows", diagnostics=diagnostics
    )
    right_rows = _candidate_index(
        right.get("comparison_rows"), container_key="right.comparison_rows", diagnostics=diagnostics
    )
    for candidate_id in sorted(set(left_rows) | set(right_rows)):
        left_row = left_rows.get(candidate_id)
        right_row = right_rows.get(candidate_id)
        if left_row is None or right_row is None:
            diagnostics.append(_missing_row("fitting_comparison.candidate", candidate_id, left_row, right_row))
            continue
        _metadata_change(
            f"candidate.{candidate_id}.status",
            left_row.get("status"),
            right_row.get("status"),
            metadata_rows,
            left_label,
            right_label,
        )
        for metric in _FITTING_METRICS:
            _append_delta_row(
                left_row,
                right_row,
                field=metric,
                key=f"fitting_comparison.{candidate_id}.{metric}",
                label_key="history.compare.fitting_comparison.metric_delta",
                left_label=left_label,
                right_label=right_label,
                rows=rows,
                diagnostics=diagnostics,
            )
    _compare_fitting_entries(
        _candidate_index(left.get("entries"), container_key="left.entries", diagnostics=diagnostics),
        _candidate_index(right.get("entries"), container_key="right.entries", diagnostics=diagnostics),
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
        metadata_rows=metadata_rows,
    )


def _compare_root_solving(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    _metadata_change("mode", left.get("mode"), right.get("mode"), metadata_rows, left_label, right_label)
    if left.get("mode") != right.get("mode"):
        diagnostics.append(_diagnostic("root_solving.mode_mismatch", "root-solving modes differ"))
    _metadata_change(
        "source.row_count",
        _source_value(left, "row_count"),
        _source_value(right, "row_count"),
        metadata_rows,
        left_label,
        right_label,
    )
    _metadata_change(
        "source.roots_count",
        _source_value(left, "roots_count"),
        _source_value(right, "roots_count"),
        metadata_rows,
        left_label,
        right_label,
    )
    _compare_numeric_rows(
        _row_index(left.get("metric_rows"), container_key="left.metric_rows", diagnostics=diagnostics),
        _row_index(right.get("metric_rows"), container_key="right.metric_rows", diagnostics=diagnostics),
        row_prefix="root_solving.metric",
        label_key="history.compare.root_solving.metric_delta",
        fields=("value", "uncertainty"),
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
    )
    _compare_diagnostic_changes(
        _row_index(left.get("diagnostic_rows"), container_key="left.diagnostic_rows", diagnostics=diagnostics),
        _row_index(right.get("diagnostic_rows"), container_key="right.diagnostic_rows", diagnostics=diagnostics),
        family_prefix="root_solving",
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
        metadata_rows=metadata_rows,
    )


def _compare_fitting_entries(
    left_entries: Mapping[str, Mapping[str, Any]],
    right_entries: Mapping[str, Mapping[str, Any]],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    for candidate_id in sorted(set(left_entries) | set(right_entries)):
        left_entry = left_entries.get(candidate_id)
        right_entry = right_entries.get(candidate_id)
        if left_entry is None or right_entry is None:
            diagnostics.append(_missing_row("fitting_comparison.entry", candidate_id, left_entry, right_entry))
            continue
        left_fit = _optional_mapping(
            left_entry.get("fit_result"),
            container_key=f"left.entries.{candidate_id}.fit_result",
            diagnostics=diagnostics,
        )
        right_fit = _optional_mapping(
            right_entry.get("fit_result"),
            container_key=f"right.entries.{candidate_id}.fit_result",
            diagnostics=diagnostics,
        )
        if left_fit is None or right_fit is None:
            continue
        _compare_parameter_values(
            _required_mapping_value(
                left_fit,
                "params",
                container_key=f"left.entries.{candidate_id}.fit_result.params",
                diagnostics=diagnostics,
            ),
            _required_mapping_value(
                right_fit,
                "params",
                container_key=f"right.entries.{candidate_id}.fit_result.params",
                diagnostics=diagnostics,
            ),
            candidate_id=candidate_id,
            left_label=left_label,
            right_label=right_label,
            rows=rows,
            diagnostics=diagnostics,
        )
        _metadata_change(
            f"candidate.{candidate_id}.covariance_shape",
            _matrix_shape(
                left_fit.get("covariance"),
                container_key=f"left.entries.{candidate_id}.fit_result.covariance",
                diagnostics=diagnostics,
            ),
            _matrix_shape(
                right_fit.get("covariance"),
                container_key=f"right.entries.{candidate_id}.fit_result.covariance",
                diagnostics=diagnostics,
            ),
            metadata_rows,
            left_label,
            right_label,
        )
        left_details = _mapping_value(left_fit, "details")
        right_details = _mapping_value(right_fit, "details")
        for metadata_key in ("covariance_warning", "correlation_warning"):
            _metadata_change(
                f"candidate.{candidate_id}.{metadata_key}",
                left_details.get(metadata_key) if left_details is not None else None,
                right_details.get(metadata_key) if right_details is not None else None,
                metadata_rows,
                left_label,
                right_label,
            )
        _metadata_change(
            f"candidate.{candidate_id}.warnings",
            _cell(left_fit.get("warnings")),
            _cell(right_fit.get("warnings")),
            metadata_rows,
            left_label,
            right_label,
        )


def _compare_parameter_values(
    left_parameters: Mapping[str, Any] | None,
    right_parameters: Mapping[str, Any] | None,
    *,
    candidate_id: str,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
) -> None:
    if left_parameters is None or right_parameters is None:
        return
    for parameter in sorted(set(left_parameters) | set(right_parameters)):
        left_value = _parameter_nominal(left_parameters.get(parameter))
        right_value = _parameter_nominal(right_parameters.get(parameter))
        if left_value is None or right_value is None:
            diagnostics.append(
                _diagnostic(
                    f"fitting_comparison.{candidate_id}.parameter.{parameter}.missing",
                    f"parameter {parameter!r} is missing or malformed for candidate {candidate_id!r}",
                )
            )
            continue
        _append_delta_from_values(
            left_value,
            right_value,
            key=f"fitting_comparison.{candidate_id}.parameter.{parameter}",
            label_key="history.compare.fitting_comparison.parameter_delta",
            left_raw=_parameter_source(left_parameters.get(parameter)),
            right_raw=_parameter_source(right_parameters.get(parameter)),
            left_label=left_label,
            right_label=right_label,
            rows=rows,
        )


def _compare_uncertainty(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    _compare_numeric_rows(
        _row_index(left.get("metric_rows"), container_key="left.metric_rows", diagnostics=diagnostics),
        _row_index(right.get("metric_rows"), container_key="right.metric_rows", diagnostics=diagnostics),
        row_prefix="uncertainty.result",
        label_key="history.compare.uncertainty.result_delta",
        fields=("value", "uncertainty"),
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
    )
    _compare_diagnostic_changes(
        _row_index(left.get("diagnostic_rows"), container_key="left.diagnostic_rows", diagnostics=diagnostics),
        _row_index(right.get("diagnostic_rows"), container_key="right.diagnostic_rows", diagnostics=diagnostics),
        family_prefix="uncertainty",
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
        metadata_rows=metadata_rows,
    )


def _compare_numeric_rows(
    left_rows: Mapping[str, Mapping[str, Any]],
    right_rows: Mapping[str, Mapping[str, Any]],
    *,
    row_prefix: str,
    label_key: str,
    fields: Sequence[str],
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
) -> None:
    for row_key in sorted(set(left_rows) | set(right_rows)):
        left_row = left_rows.get(row_key)
        right_row = right_rows.get(row_key)
        if left_row is None or right_row is None:
            diagnostics.append(_missing_row(row_prefix, row_key, left_row, right_row))
            continue
        for field in fields:
            if field not in left_row and field not in right_row:
                continue
            _append_delta_row(
                left_row,
                right_row,
                field=field,
                key=f"{row_prefix}.{row_key}.{field}",
                label_key=label_key,
                left_label=left_label,
                right_label=right_label,
                rows=rows,
                diagnostics=diagnostics,
            )


def _compare_diagnostic_changes(
    left_rows: Mapping[str, Mapping[str, Any]],
    right_rows: Mapping[str, Mapping[str, Any]],
    *,
    family_prefix: str,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    for row_key in sorted(set(left_rows) | set(right_rows)):
        left_row = left_rows.get(row_key)
        right_row = right_rows.get(row_key)
        if left_row is None or right_row is None:
            diagnostics.append(_missing_row(f"{family_prefix}.diagnostic", row_key, left_row, right_row))
            continue
        for field in ("value", "uncertainty"):
            if field not in left_row and field not in right_row:
                continue
            left_value = _parse_number(left_row.get(field), percent="percent" in row_key)
            right_value = _parse_number(right_row.get(field), percent="percent" in row_key)
            if left_value is not None and right_value is not None:
                _append_delta_from_values(
                    left_value,
                    right_value,
                    key=f"{family_prefix}.diagnostic.{row_key}.{field}",
                    label_key=f"history.compare.{family_prefix}.diagnostic_delta",
                    left_raw=left_row.get(field),
                    right_raw=right_row.get(field),
                    left_label=left_label,
                    right_label=right_label,
                    rows=rows,
                )
            elif row_key.startswith(_METADATA_PREFIXES):
                _metadata_change(
                    f"diagnostic.{row_key}.{field}",
                    left_row.get(field),
                    right_row.get(field),
                    metadata_rows,
                    left_label,
                    right_label,
                )
            else:
                _metadata_change(
                    f"{family_prefix}.{row_key}.{field}",
                    left_row.get(field),
                    right_row.get(field),
                    metadata_rows,
                    left_label,
                    right_label,
        )


def _compare_bootstrap_ci_overlap(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
) -> None:
    if left.get("mode") != "bootstrap_confidence_intervals" or right.get("mode") != "bootstrap_confidence_intervals":
        return
    left_precision = _bootstrap_ci_precision(left.get("metric_rows"), left)
    right_precision = _bootstrap_ci_precision(right.get("metric_rows"), right)
    compare_precision = max(left_precision, right_precision)
    left_intervals = _bootstrap_ci_intervals(
        left.get("metric_rows"),
        container_key="left.metric_rows",
        diagnostics=diagnostics,
        precision_digits=left_precision,
    )
    right_intervals = _bootstrap_ci_intervals(
        right.get("metric_rows"),
        container_key="right.metric_rows",
        diagnostics=diagnostics,
        precision_digits=right_precision,
    )
    for interval_key in sorted(set(left_intervals) | set(right_intervals)):
        interval_token = _bootstrap_ci_interval_token(interval_key)
        left_interval = left_intervals.get(interval_key)
        right_interval = right_intervals.get(interval_key)
        if left_interval is None or right_interval is None:
            diagnostics.append(_missing_row("statistics.bootstrap_ci", interval_token, left_interval, right_interval))
            continue
        left_lower, left_upper = left_interval
        right_lower, right_upper = right_interval
        with precision_guard(compare_precision):
            overlap_lower = max(left_lower, right_lower)
            overlap_upper = min(left_upper, right_upper)
            overlap = overlap_upper - overlap_lower
        overlaps = overlap >= 0
        rows.append(
            AnalysisRow(
                key=f"statistics.bootstrap_ci.{interval_token}.overlap",
                label_key="history.compare.statistics.bootstrap_ci_overlap",
                value="overlap" if overlaps else "disjoint",
                uncertainty=_mp_text(overlap, digits=compare_precision) if overlaps else None,
                source=(
                    f"{left_label}=[{_mp_text(left_lower, digits=compare_precision)}, "
                    f"{_mp_text(left_upper, digits=compare_precision)}]; "
                    f"{right_label}=[{_mp_text(right_lower, digits=compare_precision)}, "
                    f"{_mp_text(right_upper, digits=compare_precision)}]"
                ),
                method="bootstrap_ci_overlap",
                render_group="metric",
            )
        )


def _compare_time_series_statistics(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
    metadata_rows: list[AnalysisRow],
) -> None:
    if left.get("mode") != TIME_SERIES_WORKFLOW_MODE and right.get("mode") != TIME_SERIES_WORKFLOW_MODE:
        return
    for key in (
        "series_method",
        "time_column",
        "value_columns",
        "sigma_columns",
        "uncertainty_assumptions",
        "window",
        "ewma",
    ):
        _metadata_change(
            f"source.{key}",
            _source_value(left, key),
            _source_value(right, key),
            metadata_rows,
            left_label,
            right_label,
        )
    if left.get("mode") != TIME_SERIES_WORKFLOW_MODE or right.get("mode") != TIME_SERIES_WORKFLOW_MODE:
        return
    _compare_diagnostic_changes(
        _row_index(left.get("diagnostic_rows"), container_key="left.diagnostic_rows", diagnostics=diagnostics),
        _row_index(right.get("diagnostic_rows"), container_key="right.diagnostic_rows", diagnostics=diagnostics),
        family_prefix="statistics.time_series",
        left_label=left_label,
        right_label=right_label,
        rows=rows,
        diagnostics=diagnostics,
        metadata_rows=metadata_rows,
    )
    try:
        left_points = _time_series_final_points(left, side="left")
        right_points = _time_series_final_points(right, side="right")
    except (TypeError, ValueError) as exc:
        diagnostics.append(
            _diagnostic(
                "statistics.time_series.semantic_snapshot.invalid",
                f"time-series snapshot validation failed: {exc}",
                severity="error",
            )
        )
        return
    compare_precision = max(80, _snapshot_compute_precision(left), _snapshot_compute_precision(right))
    for point_key in sorted(set(left_points) | set(right_points)):
        point_token = _time_series_point_token(point_key)
        left_point = left_points.get(point_key)
        right_point = right_points.get(point_key)
        if left_point is None or right_point is None:
            diagnostics.append(_missing_row("statistics.time_series.final", point_token, left_point, right_point))
            continue
        for field in ("value", "uncertainty"):
            if field not in left_point and field not in right_point:
                continue
            if left_point.get(field) is None and right_point.get(field) is None:
                continue
            left_value = _parse_number(left_point.get(field), percent=False, precision_digits=compare_precision)
            right_value = _parse_number(right_point.get(field), percent=False, precision_digits=compare_precision)
            if left_value is None or right_value is None:
                diagnostics.append(
                    _diagnostic(
                        f"statistics.time_series.final.{point_token}.{field}.non_numeric",
                        f"non-numeric final time-series field {field!r} for {point_token!r}",
                    )
                )
                continue
            _append_delta_from_values(
                left_value,
                right_value,
                key=f"statistics.time_series.final.{point_token}.{field}",
                label_key="history.compare.statistics.time_series_final_delta",
                left_raw=left_point.get(field),
                right_raw=right_point.get(field),
                left_label=left_label,
                right_label=right_label,
                rows=rows,
                precision_digits=compare_precision,
                display_digits=compare_precision,
            )


def _time_series_final_points(snapshot: Mapping[str, Any], *, side: str) -> dict[tuple[str, str], Mapping[str, Any]]:
    payload = time_series_payload_from_snapshot(snapshot)
    output: dict[tuple[str, str], Mapping[str, Any]] = {}
    columns = _mapping_sequence(payload.get("columns"), container_key=f"{side}.time_series.columns", diagnostics=[])
    column_names = [_text(column.get("value_column")) or "value" for column in columns]
    duplicate_names = {name for name in column_names if column_names.count(name) > 1}
    for position, raw_column in enumerate(columns, 1):
        column_name = _text(raw_column.get("value_column")) or "value"
        column_index = _text(raw_column.get("column_index")) or (str(position) if column_name in duplicate_names else "")
        selected: Mapping[str, Any] | None = None
        for point in _mapping_sequence(raw_column.get("points"), container_key=f"{side}.time_series.points", diagnostics=[]):
            if point.get("status") == "ok" and point.get("value") is not None:
                selected = point
        if selected is not None:
            output[(column_name, column_index)] = selected
    return output


def _time_series_point_token(point_key: tuple[str, str]) -> str:
    column, column_index = point_key
    token = f"source_{_encoded_key_component(column)}"
    if column_index:
        return f"{token}_column_{_encoded_key_component(column_index)}"
    return token


def _bootstrap_ci_intervals(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
    precision_digits: int,
) -> dict[tuple[str, str], tuple[mp.mpf, mp.mpf]]:
    rows = _mapping_sequence(value, container_key=container_key, diagnostics=diagnostics)
    bounds: dict[tuple[str, str], dict[str, mp.mpf]] = {}
    for index, row in enumerate(rows):
        key = _text(row.get("key"))
        if key not in {"bootstrap_ci_lower", "bootstrap_ci_upper"}:
            continue
        column = _text(row.get("source")) or "result"
        suffix = _text(row.get("row_index")) or ""
        interval_key = (column, suffix)
        interval_token = _bootstrap_ci_interval_token(interval_key)
        parsed = _parse_number(row.get("value"), percent=False, precision_digits=precision_digits)
        if parsed is None:
            diagnostics.append(
                _diagnostic(
                    f"statistics.bootstrap_ci.{interval_token}.{key}.non_numeric",
                    f"non-numeric bootstrap CI bound in {container_key}[{index}]",
                )
            )
            continue
        bounds.setdefault(interval_key, {})["lower" if key.endswith("lower") else "upper"] = parsed
    intervals: dict[tuple[str, str], tuple[mp.mpf, mp.mpf]] = {}
    for interval_key, interval_bounds in bounds.items():
        lower = interval_bounds.get("lower")
        upper = interval_bounds.get("upper")
        if lower is None or upper is None:
            interval_token = _bootstrap_ci_interval_token(interval_key)
            diagnostics.append(
                _diagnostic(
                    f"statistics.bootstrap_ci.{interval_token}.incomplete",
                    f"bootstrap CI interval {interval_key!r} is incomplete",
                )
            )
            continue
        intervals[interval_key] = (lower, upper)
    return intervals


def _bootstrap_ci_precision(value: Any, snapshot: Mapping[str, Any]) -> int:
    precision = max(80, _snapshot_compute_precision(snapshot))
    rows = _mapping_sequence(value, container_key="bootstrap.metric_rows.precision", diagnostics=[])
    for row in rows:
        key = _text(row.get("key"))
        if key in {"bootstrap_ci_lower", "bootstrap_ci_upper"}:
            precision = max(precision, _numeric_text_digits(row.get("value")) + 10)
    return precision


def _bootstrap_ci_interval_token(interval_key: tuple[str, str]) -> str:
    column, suffix = interval_key
    column_token = f"source_{_encoded_key_component(column)}"
    if not suffix:
        return column_token
    return f"{column_token}_row_{_encoded_key_component(suffix)}"


def _encoded_key_component(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")
    return encoded or "_"


def _safe_key_token(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    return _encoded_key_component(text)


def _append_delta_row(
    left_row: Mapping[str, Any],
    right_row: Mapping[str, Any],
    *,
    field: str,
    key: str,
    label_key: str,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    diagnostics: list[AnalysisRow],
) -> None:
    left_value = _parse_number(left_row.get(field), percent=False)
    right_value = _parse_number(right_row.get(field), percent=False)
    if left_value is None or right_value is None:
        diagnostics.append(_diagnostic(f"{key}.non_numeric", f"non-numeric metric field {field!r} for {key!r}"))
        return
    _append_delta_from_values(
        left_value,
        right_value,
        key=key,
        label_key=label_key,
        left_raw=left_row.get(field),
        right_raw=right_row.get(field),
        left_label=left_label,
        right_label=right_label,
        rows=rows,
    )


def _append_delta_from_values(
    left_value: mp.mpf,
    right_value: mp.mpf,
    *,
    key: str,
    label_key: str,
    left_raw: Any,
    right_raw: Any,
    left_label: str,
    right_label: str,
    rows: list[AnalysisRow],
    precision_digits: int = 80,
    display_digits: int = 50,
) -> None:
    precision = max(80, precision_digits)
    with precision_guard(precision):
        delta = right_value - left_value
    rows.append(
        AnalysisRow(
            key=f"delta.{key}",
            label_key=label_key,
            value=_mp_text(delta, digits=display_digits),
            source=f"{left_label}={_cell(left_raw)}; {right_label}={_cell(right_raw)}",
            method="right_minus_left",
            render_group="metric",
        )
    )


def _shared_metadata_rows(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    left_label: str,
    right_label: str,
) -> list[AnalysisRow]:
    rows: list[AnalysisRow] = []
    for field in ("schema", "schema_version", "family", "mode"):
        _metadata_change(field, left.get(field), right.get(field), rows, left_label, right_label, include_equal=True)
    for field in ("row_count", "candidate_count", "roots_count", "warning_count"):
        _metadata_change(
            f"source.{field}",
            _source_value(left, field),
            _source_value(right, field),
            rows,
            left_label,
            right_label,
            include_equal=True,
        )
    _compare_unit_metadata(
        left,
        right,
        rows=rows,
        left_label=left_label,
        right_label=right_label,
    )
    return rows


def _schema_diagnostics(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    family: str,
) -> list[AnalysisRow]:
    expected_schema = _SUPPORTED_SCHEMAS.get(family)
    if expected_schema is None:
        return []
    diagnostics: list[AnalysisRow] = []
    for side, snapshot in (("left", left), ("right", right)):
        schema = snapshot.get("schema")
        schema_version = snapshot.get("schema_version")
        if schema != expected_schema:
            diagnostics.append(
                _diagnostic(
                    f"history.compare.schema.{side}.unsupported",
                    f"{side} snapshot schema {schema!r} is not supported for {family!r}",
                    severity="error",
                )
            )
        if schema_version != _SUPPORTED_RESULT_SCHEMA_VERSION:
            diagnostics.append(
                _diagnostic(
                    f"history.compare.schema.{side}.version_unsupported",
                    f"{side} snapshot schema_version {schema_version!r} is not supported for {family!r}",
                    severity="error",
                )
            )
    return diagnostics


def _metadata_change(
    key: str,
    left_value: Any,
    right_value: Any,
    rows: list[AnalysisRow],
    left_label: str,
    right_label: str,
    *,
    include_equal: bool = False,
) -> None:
    if not include_equal and left_value == right_value:
        return
    rows.append(
        AnalysisRow(
            key=f"metadata.{key}",
            label_key=f"history.compare.metadata.{key}",
            value=_cell(right_value),
            source=f"{left_label}={_cell(left_value)}; {right_label}={_cell(right_value)}",
            method="metadata",
            render_group="diagnostic",
        )
    )


def _result_payload(
    *,
    left_label: str,
    right_label: str,
    left_id: str | None,
    right_id: str | None,
    left_family: str,
    right_family: str,
    left_mode: str,
    right_mode: str,
    comparison_mode: str,
    rows: Sequence[AnalysisRow],
    metadata_rows: Sequence[AnalysisRow],
    diagnostics: Sequence[AnalysisRow],
    budget_rows: Sequence[AnalysisRow] = (),
) -> dict[str, Any]:
    payload = {
        "schema": HISTORY_COMPARISON_SCHEMA,
        "schema_version": HISTORY_COMPARISON_SCHEMA_VERSION,
        "comparison_mode": comparison_mode,
        "family": {
            "left": left_family,
            "right": right_family,
            "same_family": left_family == right_family and left_family != "unknown",
        },
        "source": {
            "left": {"label": _label(left_label, "left_label"), "id": left_id, "family": left_family, "mode": left_mode},
            "right": {
                "label": _label(right_label, "right_label"),
                "id": right_id,
                "family": right_family,
                "mode": right_mode,
            },
        },
        "rows": analysis_rows_to_json(tuple(rows)),
        "metadata_rows": analysis_rows_to_json(tuple(metadata_rows)),
        "diagnostics": analysis_rows_to_json(tuple(diagnostics)),
        "budget_rows": analysis_rows_to_json(tuple(budget_rows)),
    }
    normalized = normalize_json_payload(payload, path="history_comparison")
    if not isinstance(normalized, Mapping):
        raise TypeError("history comparison payload must be a mapping.")
    plain = _plain_json(normalized)
    if not isinstance(plain, dict):
        raise TypeError("history comparison payload must be a mapping.")
    return plain


def _result_snapshot(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    if "result" in snapshot:
        result = snapshot.get("result")
        if not isinstance(result, Mapping):
            return {}
        candidate = result
    else:
        candidate = snapshot
    normalized = normalize_json_payload(candidate, path="snapshot.result")
    if not isinstance(normalized, Mapping):
        return {}
    return normalized


def _snapshot_family(source_snapshot: Mapping[str, Any], result_snapshot: Mapping[str, Any]) -> str:
    return _text(result_snapshot.get("family") or source_snapshot.get("family") or "unknown") or "unknown"


def _row_index(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> dict[str, Mapping[str, Any]]:
    rows = _mapping_sequence(value, container_key=container_key, diagnostics=diagnostics)
    indexed: dict[str, Mapping[str, Any]] = {}
    counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        base_key = _row_key(row, index)
        counts[base_key] = counts.get(base_key, 0) + 1
        key = base_key if counts[base_key] == 1 else f"{base_key}#{counts[base_key]}"
        while key in indexed:
            counts[base_key] += 1
            key = f"{base_key}#{counts[base_key]}"
        indexed[key] = row
    return indexed


def _statistics_metric_row_index(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> dict[str, Mapping[str, Any]]:
    rows = _mapping_sequence(value, container_key=container_key, diagnostics=diagnostics)
    indexed: dict[str, Mapping[str, Any]] = {}
    counts: dict[str, int] = {}
    for index, row in enumerate(rows):
        base_key = _row_key(row, index)
        column = _text(row.get("source"))
        if column:
            base_key = f"{column}.{base_key}"
        counts[base_key] = counts.get(base_key, 0) + 1
        key = base_key if counts[base_key] == 1 else f"{base_key}#{counts[base_key]}"
        while key in indexed:
            counts[base_key] += 1
            key = f"{base_key}#{counts[base_key]}"
        indexed[key] = row
    return indexed


def _grouped_statistics_metric_index(
    snapshot: Mapping[str, Any],
    *,
    side: str,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    payload = statistics_grouped_payload_from_snapshot(snapshot)
    indexed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for group in payload.get("groups", ()):
        if not isinstance(group, Mapping):
            raise TypeError(f"{side}.groups entries must be mappings.")
        group_label = _text(group.get("group"))
        if not group_label:
            raise ValueError(f"{side}.groups entries require group labels.")
        columns = group.get("columns")
        if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"{side}.groups[{group_label}].columns must be a sequence.")
        for column in columns:
            if not isinstance(column, Mapping):
                raise TypeError(f"{side}.groups[{group_label}].columns entries must be mappings.")
            column_name = _text(column.get("value_column"))
            if not column_name:
                raise ValueError(f"{side}.groups[{group_label}].columns entries require value_column.")
            result = column.get("result")
            if result is None:
                continue
            if not isinstance(result, Mapping):
                raise TypeError(f"{side}.groups[{group_label}].columns[{column_name}].result must be a mapping.")
            for row in _grouped_result_metric_rows(result):
                metric = _text(row.get("key") or row.get("label_key"))
                if not metric:
                    continue
                indexed[(group_label, column_name, metric)] = {
                    **dict(row),
                    "group": group_label,
                    "column": column_name,
                }
    return indexed


def _grouped_result_metric_rows(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_rows = result.get("analysis_rows")
    if raw_rows is not None:
        return [
            row.to_json()
            for row in analysis_rows_from_json(raw_rows)
            if row.render_group == "metric" and _grouped_metric_row_has_numeric_value(row.to_json())
        ]
    rows: list[Mapping[str, Any]] = []
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
            "render_group": "metric",
        }
        if key == "mean" and result.get("std_mean") is not None:
            row["uncertainty"] = result.get("std_mean")
        rows.append(row)
    return rows


def _grouped_metric_row_has_numeric_value(row: Mapping[str, Any]) -> bool:
    return _parse_number(row.get("value"), percent=False) is not None or _parse_number(
        row.get("uncertainty"),
        percent=False,
    ) is not None


def _grouped_metric_token(metric_key: tuple[str, str, str]) -> str:
    group, column, metric = metric_key
    return ".".join(_safe_key_token(part) for part in (group, column, metric))


def _candidate_index(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> dict[str, Mapping[str, Any]]:
    rows = _mapping_sequence(value, container_key=container_key, diagnostics=diagnostics)
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        indexed[_text(row.get("candidate_id")) or f"candidate.{index + 1}"] = row
    return indexed


def _mapping_sequence(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        diagnostics.append(
            _diagnostic(
                f"history.compare.schema.{container_key}.invalid",
                f"{container_key} must be a sequence of row mappings",
                severity="error",
            )
        )
        return []
    rows: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            rows.append(item)
        else:
            diagnostics.append(
                _diagnostic(
                    f"history.compare.schema.{container_key}.{index}.invalid",
                    f"{container_key}[{index}] must be a row mapping",
                    severity="error",
                )
            )
    return rows


def _row_key(row: Mapping[str, Any], index: int) -> str:
    for field in ("key", "candidate_id", "row_index", "label_key"):
        text = _text(row.get(field))
        if text:
            return text
    return f"row.{index + 1}"


def _missing_row(prefix: str, row_key: str, left_row: Any, right_row: Any) -> AnalysisRow:
    side = "left" if left_row is None else "right"
    return _diagnostic(f"{prefix}.{row_key}.missing", f"{prefix} row {row_key!r} is missing on {side}")


def _diagnostic(key: str, message: str, *, severity: str = "warning") -> AnalysisRow:
    return AnalysisRow(
        key=key,
        label_key=key,
        value=message,
        severity=severity,
        message_key=key,
        render_group="diagnostic",
    )


def _parse_number(value: Any, *, percent: bool, precision_digits: int = 80) -> mp.mpf | None:
    if isinstance(value, bool) or value is None or isinstance(value, float):
        return None
    text = str(value).strip()
    if percent and text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        with precision_guard(max(80, precision_digits)):
            parsed = mp.mpf(text)
    except (TypeError, ValueError):
        return None
    return parsed if mp.isfinite(parsed) else None


def _mp_text(value: mp.mpf, *, digits: int = 50) -> str:
    with precision_guard(max(80, digits)):
        return str(mp.nstr(value, n=max(50, digits)))


def _snapshot_compute_precision(snapshot: Mapping[str, Any]) -> int:
    precision = snapshot.get("precision")
    if not isinstance(precision, Mapping):
        return 0
    for key in ("compute_digits", "numeric_digits", "precision_digits"):
        value = precision.get(key)
        if isinstance(value, bool) or value is None or isinstance(value, float):
            continue
        try:
            parsed = int(str(value).strip())
        except ValueError:
            continue
        if parsed > 0:
            return parsed
    return 0


def _numeric_text_digits(value: Any) -> int:
    if isinstance(value, bool) or value is None or isinstance(value, float):
        return 0
    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return 0
    mantissa = text.split("e", 1)[0].split("E", 1)[0].lstrip("+-")
    digits = [char for char in mantissa if char.isdigit()]
    return len(digits)


def _source_value(snapshot: Mapping[str, Any], key: str) -> Any:
    source = snapshot.get("source")
    if isinstance(source, Mapping):
        return source.get(key)
    return None


def _compare_unit_metadata(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    rows: list[AnalysisRow],
    left_label: str,
    right_label: str,
) -> None:
    left_units = _unit_metadata_summary(left)
    right_units = _unit_metadata_summary(right)
    for key in sorted(set(left_units) | set(right_units)):
        _metadata_change(
            key,
            left_units.get(key, ""),
            right_units.get(key, ""),
            rows,
            left_label,
            right_label,
        )


def _unit_metadata_summary(snapshot: Mapping[str, Any]) -> dict[str, str]:
    units = snapshot.get("units")
    if not isinstance(units, Mapping):
        return {}
    summary: dict[str, str] = {}
    enabled = units.get("enabled")
    if isinstance(enabled, bool):
        summary["units.enabled"] = "true" if enabled else "false"
    mode = _text(units.get("mode"))
    if mode:
        summary["units.mode"] = mode
    for namespace in ("inputs", "constants", "parameters", "outputs"):
        namespace_value = _unit_namespace_summary(units.get(namespace))
        if namespace_value:
            summary[f"units.{namespace}"] = namespace_value
    compatibility_value = _unit_namespace_summary(units.get("compatibility"))
    if compatibility_value:
        summary["units.compatibility"] = compatibility_value
    return summary


def _unit_namespace_summary(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    pieces: list[str] = []
    for key in sorted(value, key=lambda item: str(item)):
        name = str(key)
        item = value.get(key)
        if isinstance(item, Mapping):
            unit = _text(item.get("unit"))
            label = _text(item.get("label"))
            descriptor = unit
            if label:
                descriptor = f"{descriptor} ({label})" if descriptor else f"label={label}"
        else:
            descriptor = _text(item)
        pieces.append(f"{name}={descriptor}" if descriptor else name)
    return "; ".join(pieces)


def _optional_mapping(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    diagnostics.append(
        _diagnostic(
            f"history.compare.schema.{container_key}.invalid",
            f"{container_key} must be a mapping",
            severity="error",
        )
    )
    return None


def _mapping_value(value: Any, key: str) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        child = value.get(key)
        if isinstance(child, Mapping):
            return child
    return None


def _required_mapping_value(
    value: Mapping[str, Any],
    key: str,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> Mapping[str, Any] | None:
    if key not in value:
        diagnostics.append(
            _diagnostic(
                f"history.compare.schema.{container_key}.missing",
                f"{container_key} is required",
                severity="error",
            )
        )
        return None
    child = value.get(key)
    if isinstance(child, Mapping):
        return child
    diagnostics.append(
        _diagnostic(
            f"history.compare.schema.{container_key}.invalid",
            f"{container_key} must be a mapping",
            severity="error",
        )
    )
    return None


def _matrix_shape(
    value: Any,
    *,
    container_key: str,
    diagnostics: list[AnalysisRow],
) -> str:
    if value is None:
        diagnostics.append(
            _diagnostic(
                f"history.compare.schema.{container_key}.missing",
                f"{container_key} is required",
                severity="error",
            )
        )
        return ""
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        diagnostics.append(
            _diagnostic(
                f"history.compare.schema.{container_key}.invalid",
                f"{container_key} must be a sequence of row sequences",
                severity="error",
            )
        )
        return ""
    row_count = 0
    column_count: int | None = None
    for index, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            diagnostics.append(
                _diagnostic(
                    f"history.compare.schema.{container_key}.{index}.invalid",
                    f"{container_key}[{index}] must be a row sequence",
                    severity="error",
                )
            )
            return "malformed"
        row_len = len(row)
        if column_count is None:
            column_count = row_len
        elif column_count != row_len:
            return "ragged"
        row_count += 1
    if column_count is None:
        return "0x0"
    return f"{row_count}x{column_count}"


def _parameter_nominal(value: Any) -> mp.mpf | None:
    candidate = value
    if isinstance(value, Mapping):
        for key in ("value", "nominal", "estimate"):
            if key in value:
                candidate = value.get(key)
                break
    return _parse_number(candidate, percent=False)


def _parameter_source(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("value", "nominal", "estimate"):
            if key in value:
                return _cell(value.get(key))
    return _cell(value)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return ""


def _label(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return field_name
    return value


def _optional_label(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _label(value, field_name)


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [_plain_json(item) for item in value]
    return deepcopy(value)
