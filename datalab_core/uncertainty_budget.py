from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from ._payload import normalize_json_payload
from .results import AnalysisRow, AnalysisValue, analysis_rows_from_json, analysis_rows_to_json


@dataclass(frozen=True)
class UncertaintyBudgetRow:
    family: str
    result_id: str
    source_snapshot_id: str
    source_row_id: str | None
    source_key: str | None
    category: str
    label_key: str
    value: AnalysisValue = None
    uncertainty: str | None = None
    percent: str | None = None
    cumulative_percent: str | None = None
    method: str | None = None
    severity: str = "info"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", _required_text(self.family, "family"))
        object.__setattr__(self, "result_id", _required_text(self.result_id, "result_id"))
        object.__setattr__(self, "source_snapshot_id", _required_text(self.source_snapshot_id, "source_snapshot_id"))
        object.__setattr__(self, "source_row_id", _optional_text(self.source_row_id, "source_row_id"))
        object.__setattr__(self, "source_key", _optional_text(self.source_key, "source_key"))
        object.__setattr__(self, "category", _required_text(self.category, "category"))
        object.__setattr__(self, "label_key", _required_text(self.label_key, "label_key"))
        object.__setattr__(self, "value", _analysis_value(self.value, "value"))
        object.__setattr__(self, "uncertainty", _optional_text(self.uncertainty, "uncertainty"))
        object.__setattr__(self, "percent", _optional_text(self.percent, "percent"))
        object.__setattr__(self, "cumulative_percent", _optional_text(self.cumulative_percent, "cumulative_percent"))
        object.__setattr__(self, "method", _optional_text(self.method, "method"))
        object.__setattr__(self, "severity", _severity(self.severity))
        object.__setattr__(self, "notes", _text_tuple(self.notes, "notes"))

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "family": self.family,
            "result_id": self.result_id,
            "source_snapshot_id": self.source_snapshot_id,
            "category": self.category,
            "label_key": self.label_key,
            "severity": self.severity,
            "notes": list(self.notes),
        }
        for field_name in (
            "source_row_id",
            "source_key",
            "value",
            "uncertainty",
            "percent",
            "cumulative_percent",
            "method",
        ):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        normalized = normalize_json_payload(payload, path="uncertainty_budget_row")
        if not isinstance(normalized, Mapping):
            raise TypeError("uncertainty budget row must normalize to a mapping.")
        return {str(key): value for key, value in normalized.items()}


@dataclass(frozen=True)
class BudgetExtractionResult:
    rows: tuple[UncertaintyBudgetRow, ...] = ()
    diagnostics: tuple[AnalysisRow, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "rows": budget_rows_to_json(self.rows),
            "diagnostics": analysis_rows_to_json(self.diagnostics),
        }


class BudgetExtractor(Protocol):
    family: str
    supported_snapshot_schemas: tuple[str, ...]

    def extract(self, snapshot: Mapping[str, Any], *, source_snapshot_id: str) -> BudgetExtractionResult:
        ...


def extract_uncertainty_budget(
    snapshot: Mapping[str, Any],
    *,
    source_snapshot_id: str = "snapshot",
    extractors: Sequence[BudgetExtractor] | None = None,
) -> BudgetExtractionResult:
    if not isinstance(snapshot, Mapping):
        return BudgetExtractionResult(diagnostics=(_diagnostic("budget.snapshot.invalid", "snapshot is not a mapping"),))
    family = snapshot.get("family")
    if not isinstance(family, str) or not family:
        return BudgetExtractionResult(diagnostics=(_diagnostic("budget.snapshot.family_missing", "snapshot family missing"),))
    registry = {extractor.family: extractor for extractor in (extractors or default_budget_extractors())}
    extractor = registry.get(family)
    if extractor is None:
        return BudgetExtractionResult(
            diagnostics=(_diagnostic("budget.snapshot.unsupported_family", f"unsupported family: {family}"),)
        )
    return extractor.extract(snapshot, source_snapshot_id=source_snapshot_id)


def default_budget_extractors() -> tuple[BudgetExtractor, ...]:
    return cast(
        tuple[BudgetExtractor, ...],
        (
            _RowGroupBudgetExtractor(
                family="statistics",
                supported_snapshot_schemas=("datalab.result_snapshot.statistics",),
                category_prefix="statistics",
            ),
            _FittingComparisonBudgetExtractor(),
            _RowGroupBudgetExtractor(
                family="root_solving",
                supported_snapshot_schemas=("datalab.result_snapshot.root_solving",),
                category_prefix="root_solving",
            ),
            _UncertaintySnapshotBudgetExtractor(),
        ),
    )


def budget_rows_to_json(rows: Sequence[UncertaintyBudgetRow]) -> list[dict[str, object]]:
    return [row.to_json() for row in rows]


@dataclass(frozen=True)
class _RowGroupBudgetExtractor:
    family: str
    supported_snapshot_schemas: tuple[str, ...]
    category_prefix: str

    def extract(self, snapshot: Mapping[str, Any], *, source_snapshot_id: str) -> BudgetExtractionResult:
        schema_diagnostic = _schema_diagnostic(snapshot, self.supported_snapshot_schemas)
        if schema_diagnostic is not None:
            return BudgetExtractionResult(diagnostics=(schema_diagnostic,))
        if self.family == "statistics" and snapshot.get("mode") == "bootstrap_confidence_intervals":
            return BudgetExtractionResult(
                diagnostics=(
                    AnalysisRow(
                        key="budget.statistics.bootstrap.diagnostic_only",
                        label_key="budget.statistics.bootstrap.diagnostic_only",
                        value="Bootstrap confidence intervals are diagnostic context, not variance contributions.",
                        severity="info",
                        message_key="budget.statistics.bootstrap.diagnostic_only",
                        render_group="diagnostic",
                    ),
                )
            )
        if self.family == "statistics" and snapshot.get("mode") == "hypothesis_tests":
            return BudgetExtractionResult(
                diagnostics=(
                    AnalysisRow(
                        key="budget.statistics.hypothesis.diagnostic_only",
                        label_key="budget.statistics.hypothesis.diagnostic_only",
                        value="Hypothesis-test p-values and decisions are diagnostic context, not variance contributions.",
                        severity="info",
                        message_key="budget.statistics.hypothesis.diagnostic_only",
                        render_group="diagnostic",
                    ),
                )
            )
        if self.family == "statistics" and snapshot.get("mode") == "time_series_rolling":
            return BudgetExtractionResult(
                diagnostics=(
                    AnalysisRow(
                        key="budget.statistics.time_series.diagnostic_only",
                        label_key="budget.statistics.time_series.diagnostic_only",
                        value=(
                            "Time-series rolling and smoothing outputs are diagnostic series context, "
                            "not variance contributions."
                        ),
                        severity="info",
                        message_key="budget.statistics.time_series.diagnostic_only",
                        render_group="diagnostic",
                    ),
                )
            )
        rows, diagnostics = _analysis_group_budget_rows(
            snapshot,
            family=self.family,
            source_snapshot_id=source_snapshot_id,
            category_prefix=self.category_prefix,
        )
        return BudgetExtractionResult(rows=rows, diagnostics=diagnostics)


@dataclass(frozen=True)
class _UncertaintySnapshotBudgetExtractor:
    family: str = "uncertainty"
    supported_snapshot_schemas: tuple[str, ...] = ("datalab.result_snapshot.uncertainty",)

    def extract(self, snapshot: Mapping[str, Any], *, source_snapshot_id: str) -> BudgetExtractionResult:
        schema_diagnostic = _schema_diagnostic(snapshot, self.supported_snapshot_schemas)
        if schema_diagnostic is not None:
            return BudgetExtractionResult(diagnostics=(schema_diagnostic,))
        rows, diagnostics = _analysis_group_budget_rows(
            snapshot,
            family=self.family,
            source_snapshot_id=source_snapshot_id,
            category_prefix="uncertainty",
        )
        contribution_rows = tuple(_uncertainty_contribution_row(row) or row for row in rows)
        if _unit_metadata_present(snapshot):
            diagnostics = diagnostics + (
                AnalysisRow(
                    key="budget.uncertainty.units.provenance",
                    label_key="budget.uncertainty.units.provenance",
                    value="Unit metadata is provenance; budget aggregation remains numeric and unchanged.",
                    severity="info",
                    message_key="budget.uncertainty.units.provenance",
                    render_group="diagnostic",
                ),
            )
        return BudgetExtractionResult(rows=contribution_rows, diagnostics=diagnostics)


@dataclass(frozen=True)
class _FittingComparisonBudgetExtractor:
    family: str = "fitting_comparison"
    supported_snapshot_schemas: tuple[str, ...] = ("datalab.result_snapshot.fitting_comparison",)

    def extract(self, snapshot: Mapping[str, Any], *, source_snapshot_id: str) -> BudgetExtractionResult:
        schema_diagnostic = _schema_diagnostic(snapshot, self.supported_snapshot_schemas)
        if schema_diagnostic is not None:
            return BudgetExtractionResult(diagnostics=(schema_diagnostic,))
        rows: list[UncertaintyBudgetRow] = []
        diagnostics: list[AnalysisRow] = []
        comparison_rows = snapshot.get("comparison_rows")
        if not isinstance(comparison_rows, Sequence) or isinstance(
            comparison_rows,
            (str, bytes, bytearray, memoryview),
        ):
            return BudgetExtractionResult(
                diagnostics=(_diagnostic("budget.fitting_comparison.malformed_rows", "comparison_rows malformed"),)
            )
        for index, item in enumerate(comparison_rows):
            if not isinstance(item, Mapping):
                return BudgetExtractionResult(
                    diagnostics=(_diagnostic("budget.fitting_comparison.malformed_row", f"row {index} malformed"),)
                )
            candidate_id = _text_or_default(item.get("candidate_id"), f"candidate-{index + 1}")
            status = _text_or_default(item.get("status"), "unknown")
            notes = tuple(
                text
                for text in (
                    _optional_text_or_none(item.get("warnings")),
                    _optional_text_or_none(item.get("error")),
                )
                if text
            )
            try:
                chi2_value = _analysis_value(item.get("chi2"), "chi2")
            except TypeError as exc:
                return BudgetExtractionResult(
                    diagnostics=(_diagnostic("budget.fitting_comparison.malformed_value", str(exc)),)
                )
            rows.append(
                UncertaintyBudgetRow(
                    family=self.family,
                    result_id=candidate_id,
                    source_snapshot_id=source_snapshot_id,
                    source_row_id=str(index + 1),
                    source_key=candidate_id,
                    category="fitting_comparison.candidate",
                    label_key="fitting_comparison.candidate",
                    value=chi2_value or status,
                    method="selected_fit_comparison",
                    severity="warning" if status != "success" or notes else "info",
                    notes=notes,
                )
            )
        rows.extend(_fitting_covariance_rows(snapshot, source_snapshot_id=source_snapshot_id))
        return BudgetExtractionResult(rows=tuple(rows), diagnostics=tuple(diagnostics))


def _analysis_group_budget_rows(
    snapshot: Mapping[str, Any],
    *,
    family: str,
    source_snapshot_id: str,
    category_prefix: str,
) -> tuple[tuple[UncertaintyBudgetRow, ...], tuple[AnalysisRow, ...]]:
    rows: list[UncertaintyBudgetRow] = []
    diagnostics: list[AnalysisRow] = []
    for group in ("metric_rows", "diagnostic_rows", "row_flags"):
        raw_rows = snapshot.get(group, ())
        if raw_rows in (None, ()):
            continue
        try:
            analysis_rows = analysis_rows_from_json(raw_rows)
        except (TypeError, ValueError) as exc:
            return (), (_diagnostic(f"budget.{family}.{group}.malformed", str(exc)),)
        category = f"{category_prefix}.{_category_from_group(group)}"
        rows.extend(
            _budget_row_from_analysis_row(
                row,
                family=family,
                source_snapshot_id=source_snapshot_id,
                category=category,
            )
            for row in analysis_rows
        )
    return tuple(rows), tuple(diagnostics)


def _category_from_group(group: str) -> str:
    return {
        "metric_rows": "metric",
        "diagnostic_rows": "diagnostic",
        "row_flags": "row_flag",
    }[group]


def _budget_row_from_analysis_row(
    row: AnalysisRow,
    *,
    family: str,
    source_snapshot_id: str,
    category: str,
) -> UncertaintyBudgetRow:
    return UncertaintyBudgetRow(
        family=family,
        result_id=str(row.row_index) if row.row_index is not None else source_snapshot_id,
        source_snapshot_id=source_snapshot_id,
        source_row_id=str(row.row_index) if row.row_index is not None else None,
        source_key=_analysis_row_source_key(row),
        category=category,
        label_key=row.label_key,
        value=row.value,
        uncertainty=str(row.uncertainty) if row.uncertainty is not None else None,
        method=row.method,
        severity=row.severity,
        notes=tuple(text for text in (row.message_key, row.source) if text),
    )


def _uncertainty_contribution_row(row: UncertaintyBudgetRow) -> UncertaintyBudgetRow | None:
    key = row.source_key or ""
    base_key = _analysis_row_source_key_base(key)
    if base_key.startswith("contribution_percent."):
        return _replace_budget_row(row, category="uncertainty.contribution_percent", value=None, percent=row.value)
    if base_key.startswith("contribution_cumulative_percent."):
        return _replace_budget_row(
            row,
            category="uncertainty.contribution_cumulative_percent",
            value=None,
            cumulative_percent=row.value,
        )
    if base_key.startswith("contribution_total."):
        return _replace_budget_row(row, category="uncertainty.contribution_total_variance")
    if base_key.startswith("contribution."):
        return _replace_budget_row(row, category="uncertainty.contribution_variance")
    return None


def _unit_metadata_present(snapshot: Mapping[str, Any]) -> bool:
    units = snapshot.get("units")
    if not isinstance(units, Mapping):
        return False
    enabled = units.get("enabled")
    if enabled is True:
        return True
    mode = units.get("mode")
    if isinstance(mode, str) and mode and mode != "display_only":
        return True
    for namespace in ("inputs", "constants", "parameters", "outputs"):
        value = units.get(namespace)
        if isinstance(value, Mapping) and value:
            return True
    compatibility = units.get("compatibility")
    if isinstance(compatibility, Mapping) and compatibility:
        return True
    return False


def _analysis_row_source_key(row: AnalysisRow) -> str:
    payload = [row.key, row.source, row.row_index]
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    token = base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")
    return f"analysis_row:v1:{token}"


def budget_source_key_base(source_key: str | None) -> str:
    """Decode an encoded ``analysis_row:v1:<base64>`` source key to its plain
    base key for display (e.g. ``contribution_percent.A``). Passthrough for keys
    that are not encoded. Public wrapper so UI/label paths render the readable
    key instead of the opaque token."""
    return _analysis_row_source_key_base(source_key or "")


def _analysis_row_source_key_base(source_key: str) -> str:
    prefix = "analysis_row:v1:"
    if not source_key.startswith(prefix):
        return source_key
    token = source_key[len(prefix) :]
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, TypeError, UnicodeDecodeError):
        return source_key
    if (
        isinstance(payload, list)
        and len(payload) == 3
        and isinstance(payload[0], str)
        and (payload[1] is None or isinstance(payload[1], str))
        and (payload[2] is None or isinstance(payload[2], (str, int)))
        and not isinstance(payload[2], bool)
    ):
        return payload[0]
    return source_key


def _replace_budget_row(
    row: UncertaintyBudgetRow,
    *,
    category: str,
    value: AnalysisValue | None = None,
    percent: AnalysisValue | None = None,
    cumulative_percent: AnalysisValue | None = None,
) -> UncertaintyBudgetRow:
    return UncertaintyBudgetRow(
        family=row.family,
        result_id=row.result_id,
        source_snapshot_id=row.source_snapshot_id,
        source_row_id=row.source_row_id,
        source_key=row.source_key,
        category=category,
        label_key=row.label_key,
        value=row.value if value is None and percent is None and cumulative_percent is None else value,
        uncertainty=row.uncertainty,
        percent=str(percent) if percent is not None else row.percent,
        cumulative_percent=str(cumulative_percent) if cumulative_percent is not None else row.cumulative_percent,
        method=row.method,
        severity=row.severity,
        notes=row.notes,
    )


def _fitting_covariance_rows(
    snapshot: Mapping[str, Any],
    *,
    source_snapshot_id: str,
) -> tuple[UncertaintyBudgetRow, ...]:
    entries = snapshot.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray, memoryview)):
        return ()
    rows: list[UncertaintyBudgetRow] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        candidate_id = _text_or_default(entry.get("candidate_id"), f"candidate-{index + 1}")
        fit_result = entry.get("fit_result")
        if not isinstance(fit_result, Mapping):
            continue
        covariance = fit_result.get("covariance")
        if not isinstance(covariance, Sequence) or isinstance(covariance, (str, bytes, bytearray, memoryview)):
            continue
        rows.append(
            UncertaintyBudgetRow(
                family="fitting_comparison",
                result_id=candidate_id,
                source_snapshot_id=source_snapshot_id,
                source_row_id=str(index + 1),
                source_key=f"covariance.{candidate_id}",
                category="fitting_comparison.covariance",
                label_key="fitting_comparison.covariance",
                value=len(covariance),
                method="selected_fit_comparison",
                notes=("covariance_matrix_present",),
            )
        )
    return tuple(rows)


def _schema_diagnostic(snapshot: Mapping[str, Any], supported_schemas: tuple[str, ...]) -> AnalysisRow | None:
    if snapshot.get("schema") not in supported_schemas:
        return _diagnostic("budget.snapshot.unsupported_schema", "unsupported snapshot schema")
    if snapshot.get("schema_version") != 1:
        return _diagnostic("budget.snapshot.unsupported_schema_version", "unsupported snapshot schema version")
    return None


def _diagnostic(key: str, message: str) -> AnalysisRow:
    return AnalysisRow(
        key=key,
        label_key=key,
        value=message,
        severity="error",
        message_key=key,
        render_group="diagnostic",
    )


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or None.")
    return value


def _analysis_value(value: Any, field_name: str) -> AnalysisValue:
    if value is None:
        return None
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric values as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string, integer, or None.")
    if isinstance(value, str | int):
        return value
    raise TypeError(f"{field_name} must be a string, integer, or None.")


def _analysis_value_or_none(value: Any) -> AnalysisValue:
    try:
        return _analysis_value(value, "value")
    except TypeError:
        return None


def _severity(value: Any) -> str:
    if value not in {"info", "warning", "error"}:
        raise ValueError("severity must be info, warning, or error.")
    return str(value)


def _text_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string.")
    result = tuple(values)
    for index, value in enumerate(result):
        if not isinstance(value, str):
            raise TypeError(f"{field_name}[{index}] must be a string.")
    return result


def _text_or_default(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


def _optional_text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


__all__ = [
    "BudgetExtractionResult",
    "BudgetExtractor",
    "UncertaintyBudgetRow",
    "budget_rows_to_json",
    "default_budget_extractors",
    "extract_uncertainty_budget",
]
