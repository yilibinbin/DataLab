from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, TypedDict

from mpmath import mp

from ._payload import normalize_json_payload
from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import (
    numeric_to_payload_string,
    optional_numeric_to_payload_string,
    request_digit_hint,
)
from .results import AnalysisRow, ResultEnvelope, ResultKind, ResultStatus, analysis_rows_to_json
from .session import check_cancelled
from .table_payload import normalize_headers, normalize_segments
from shared.error_propagation_engine import _apply_aliases, _normalize_header_to_symbol, apply_formula_to_data
from shared.precision import precision_guard
from shared.unit_annotations import ACTIVE_UNIT_MODES, UnitAnnotationError, normalize_unit_annotations
from shared.unit_expression_validation import UnitExpressionError, validate_expression_units
from shared.uncertainty import UncertainValue


DEFAULT_UNCERTAINTY_PRECISION_DIGITS = 50
DEFAULT_MONTE_CARLO_SAMPLE_COUNT = 5000
COMPARISON_ABSOLUTE_RESULT_TOLERANCE = "1e-12"
COMPARISON_RELATIVE_RESULT_TOLERANCE = "1e-8"
COMPARISON_UNAVAILABLE_REASONS = frozenset({"taylor_unavailable", "result_count_mismatch"})
COMPARISON_MEAN_OMISSION_REASONS = frozenset({"nonfinite_mean"})
COMPARISON_STD_OMISSION_REASONS = frozenset({"nonfinite_std", "zero_std"})
TAYLOR_ORDER_COMPARISON_METHOD = "taylor_order_1_vs_2"
SENSITIVITY_RELATIVE_OMISSION_REASONS = frozenset({"nonfinite", "zero_output", "zero_input"})
UNCERTAINTY_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.uncertainty"
UNCERTAINTY_RESULT_SNAPSHOT_SCHEMA_VERSION = 1


class UncertaintyPropagationConfig(TypedDict):
    method: str
    order: int
    mc_samples: int | None
    mc_seed: int | None


def build_uncertainty_request(
    *,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    formula: str,
    uncertainty_rows: Sequence[Sequence[Any | None]] | None = None,
    constants: Mapping[str, Any] | None = None,
    units: Mapping[str, Any] | None = None,
    propagation_method: str = "taylor",
    propagation_order: int = 1,
    mc_samples: int | None = None,
    mc_seed: int | None = None,
    collect_monte_carlo_distribution: bool = False,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    segments: Sequence[tuple[int, int]] | None = None,
    request_id: str = "uncertainty",
) -> ComputeJobRequest:
    """Build a string-only uncertainty propagation request.

    This is a Phase 2 request boundary only. Existing desktop/web error
    propagation execution stays in the legacy path until that implementation is
    split from LaTeX/PDF/rendering concerns.
    """

    digit_hint = request_digit_hint(precision_digits)
    normalized_headers = normalize_headers(headers)
    normalized_formula = _normalize_formula(formula)
    propagation = normalize_uncertainty_propagation_config(
        method=propagation_method,
        order=propagation_order,
        mc_samples=mc_samples,
        mc_seed=mc_seed,
    )
    values, uncertainties = _normalize_uncertainty_rows(
        rows,
        uncertainty_rows=uncertainty_rows,
        headers=normalized_headers,
        digit_hint=digit_hint,
    )
    normalized_constants = _normalize_constants(constants or {}, digit_hint=digit_hint)
    units_config = _normalize_uncertainty_units_config(
        units,
        headers=normalized_headers,
        constants=normalized_constants,
    )
    normalized_segments = normalize_segments(segments, row_count=len(values))
    if not normalized_segments:
        raise ValueError("segments must include at least one row.")

    inputs: dict[str, object] = {
        "headers": normalized_headers,
        "values": values,
        "uncertainties": uncertainties,
        "constants": normalized_constants,
        "formula": normalized_formula,
        "propagation": propagation,
        "collect_monte_carlo_distribution": bool(collect_monte_carlo_distribution),
        "segments": normalized_segments,
    }
    if units_config is not None:
        inputs["units"] = units_config

    return ComputeJobRequest(
        mode=JobMode.UNCERTAINTY,
        inputs=inputs,
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
        ),
        request_id=request_id,
    )


def run_uncertainty(request: ComputeJobRequest) -> ResultEnvelope:
    """Run uncertainty propagation through the UI-neutral core service boundary."""

    check_cancelled()
    if request.mode is not JobMode.UNCERTAINTY:
        raise ValueError(f"Unsupported uncertainty request mode: {request.mode.value}.")
    precision_digits = (
        DEFAULT_UNCERTAINTY_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )
    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        headers = _required_string_sequence(request.inputs.get("headers"), field_name="headers")
        values = _required_matrix(request.inputs.get("values"), field_name="values", headers=headers)
        uncertainties = _required_matrix(
            request.inputs.get("uncertainties"),
            field_name="uncertainties",
            headers=headers,
        )
        if len(uncertainties) != len(values):
            raise ValueError("uncertainties must have the same row count as values.")
        parsed_data = _uncertain_rows(values, uncertainties)
        constants = _uncertain_constants(request.inputs.get("constants"))
        units_config = _normalize_uncertainty_units_config(
            request.inputs.get("units") if "units" in request.inputs else None,
            headers=headers,
            constants=_mapping_or_empty(request.inputs.get("constants"), field_name="constants"),
        )
        check_cancelled()
        formula = _required_text(request.inputs.get("formula"), field_name="formula")
        _validate_uncertainty_units_before_evaluation(
            units_config,
            headers=headers,
            constants=constants,
            formula=formula,
        )
        propagation = _mapping_or_empty(request.inputs.get("propagation"), field_name="propagation")
        method = _required_text(propagation.get("method", "taylor"), field_name="propagation.method")
        order = _validate_int(propagation.get("order", 1), field_name="propagation.order")
        mc_samples = _validate_optional_int(propagation.get("mc_samples"), field_name="propagation.mc_samples")
        mc_seed = _validate_optional_int(propagation.get("mc_seed"), field_name="propagation.mc_seed")
        propagation_config = normalize_uncertainty_propagation_config(
            method=method,
            order=order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
        )
        collect_monte_carlo_distribution = _required_bool(
            request.inputs.get("collect_monte_carlo_distribution", False),
            field_name="collect_monte_carlo_distribution",
        )
        collect_monte_carlo_distribution = (
            collect_monte_carlo_distribution and propagation_config["method"] == "monte_carlo"
        )
        warnings: list[str] = []
        results = apply_formula_to_data(
            list(headers),
            parsed_data,
            constants,
            formula,
            False,
            warnings=warnings,
            return_components=True,
            propagation_method=propagation_config["method"],
            propagation_order=propagation_config["order"],
            mc_samples=propagation_config["mc_samples"],
            mc_seed=propagation_config["mc_seed"],
            return_sensitivities=propagation_config["method"] == "taylor",
            collect_monte_carlo_distribution=collect_monte_carlo_distribution,
            cancellation_checker=check_cancelled,
        )
        comparison_payloads = _taylor_monte_carlo_comparison_payloads(
            headers=list(headers),
            parsed_data=parsed_data,
            constants=constants,
            formula=formula,
            monte_carlo_results=results,
            propagation_config=propagation_config,
            precision_digits=precision_used,
        )
        taylor_order_comparison_payloads = _taylor_order_comparison_payloads(
            headers=list(headers),
            parsed_data=parsed_data,
            constants=constants,
            formula=formula,
            selected_results=results,
            propagation_config=propagation_config,
            precision_digits=precision_used,
        )
        check_cancelled()
        result_payloads = [_uncertain_result_payload(result, precision_used) for result in results]
        if comparison_payloads is not None:
            for result_payload, comparison_payload in zip(result_payloads, comparison_payloads, strict=True):
                result_payload["comparison"] = comparison_payload
        if taylor_order_comparison_payloads is not None:
            for result_payload, taylor_order_comparison_payload in zip(
                result_payloads,
                taylor_order_comparison_payloads,
                strict=True,
            ):
                result_payload["taylor_order_comparison"] = taylor_order_comparison_payload
        payload = {
            "headers": list(headers),
            "formula": formula,
            "segments": request.inputs.get("segments") or [[0, len(values)]],
            "precision_used": precision_used,
            "propagation": propagation_config,
            "results": result_payloads,
        }
        if units_config is not None:
            payload["units"] = units_config
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=tuple(warnings),
    )


def _normalize_uncertainty_units_config(
    units: Any,
    *,
    headers: Sequence[str],
    constants: Mapping[str, Any],
) -> dict[str, Any] | None:
    if units is None:
        return None
    canonical_headers, _alias_map = _canonical_error_symbols(headers)
    try:
        normalized_units = normalize_unit_annotations(
            units,
            allowed_symbols={
                "inputs": canonical_headers,
                "constants": tuple(str(name) for name in constants),
                "outputs": ("result",),
            },
        )
    except UnitAnnotationError as exc:
        raise ValueError(f"units config is invalid: {exc}") from exc
    return dict(normalized_units)


def _validate_uncertainty_units_before_evaluation(
    units_config: Mapping[str, Any] | None,
    *,
    headers: Sequence[str],
    constants: Mapping[str, UncertainValue],
    formula: str,
) -> None:
    if not units_config or not units_config.get("enabled"):
        return
    mode = str(units_config.get("mode") or "display_only")
    if mode not in ACTIVE_UNIT_MODES:
        return
    canonical_headers, alias_map = _canonical_error_symbols(headers)
    rewritten_formula = _apply_aliases(formula, alias_map)
    symbol_units = {symbol: "1" for symbol in canonical_headers}
    symbol_units.update({str(name): "1" for name in constants})
    symbol_units.update(_unit_map_for_namespace(units_config.get("inputs")))
    symbol_units.update(_unit_map_for_namespace(units_config.get("constants")))
    outputs = _unit_map_for_namespace(units_config.get("outputs"))
    output_unit = outputs.get("result")
    try:
        validate_expression_units(rewritten_formula, symbol_units, output_unit=output_unit)
    except UnitExpressionError as exc:
        raise ValueError(f"unit validation failed: {exc}") from exc


def _unit_map_for_namespace(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    units: dict[str, str] = {}
    for key, annotation in value.items():
        if isinstance(annotation, Mapping) and isinstance(annotation.get("unit"), str):
            units[str(key)] = str(annotation["unit"])
    return units


def _canonical_error_symbols(headers: Sequence[str]) -> tuple[list[str], dict[str, str]]:
    canonical_vars: list[str] = []
    alias_map: dict[str, str] = {}
    seen: set[str] = set()
    for index, header in enumerate(headers):
        symbol = _normalize_header_to_symbol(str(header), index)
        base = symbol
        counter = 2
        while symbol in seen:
            symbol = f"{base}_{counter}"
            counter += 1
        seen.add(symbol)
        canonical_vars.append(symbol)
        alias_map[f"x{index + 1}"] = symbol
    return canonical_vars, alias_map


def uncertainty_payload_to_results(payload: Mapping[str, Any]) -> list[UncertainValue]:
    """Convert JSON-safe core uncertainty payload back to legacy result objects."""

    raw_results = payload.get("results")
    if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes, bytearray, memoryview)):
        raise ValueError("payload.results must be a sequence.")
    results: list[UncertainValue] = []
    precision_digits = _snapshot_optional_int(payload.get("precision_used")) or mp.dps
    propagation_method = _snapshot_raw_propagation_method(payload.get("propagation"))
    allow_sensitivities = propagation_method != "monte_carlo"
    allow_distribution = propagation_method == "monte_carlo"
    for index, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, Mapping):
            raise ValueError(f"payload.results[{index}] must be a mapping.")
        contributions_raw = raw_result.get("contributions") or {}
        if not isinstance(contributions_raw, Mapping):
            raise ValueError(f"payload.results[{index}].contributions must be a mapping.")
        contributions = {
            str(name): mp.mpf(str(value))
            for name, value in contributions_raw.items()
        }
        results.append(
            UncertainValue(
                mp.mpf(str(raw_result.get("value"))),
                mp.mpf(str(raw_result.get("uncertainty"))),
                contributions=contributions or None,
                sensitivities=(
                    _snapshot_sensitivity_metadata(
                        raw_result.get("sensitivities"),
                        precision_digits=precision_digits,
                    )
                    if allow_sensitivities
                    else None
                ),
                monte_carlo_distribution=(
                    _snapshot_monte_carlo_distribution_metadata(
                        raw_result.get("monte_carlo_distribution"),
                        precision_digits=precision_digits,
                    )
                    if allow_distribution
                    else None
                ),
            )
        )
    return results


def build_uncertainty_result_snapshot(
    kind: str,
    payload: Mapping[str, Any],
    *,
    overview_state: str = "none",
    plot_metadata: Sequence[Mapping[str, Any]] = (),
    precision: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a JSON-safe semantic snapshot for error propagation results."""

    if kind != "error":
        return None
    headers = _snapshot_text_sequence(payload.get("headers"))
    data_rows = _snapshot_rows(payload.get("data_rows"))
    precision_payload = _snapshot_plain_mapping(precision or {})
    precision_used = _snapshot_optional_int(payload.get("precision_used"))
    if precision_used is not None:
        precision_payload["compute_digits"] = precision_used
    format_digits = precision_used or _snapshot_optional_int(precision_payload.get("compute_digits")) or mp.dps

    propagation_payload = payload.get("propagation")
    propagation_method = _snapshot_raw_propagation_method(propagation_payload)
    propagation_config = _snapshot_propagation_metadata(propagation_payload)
    results = _snapshot_result_rows(
        payload.get("results"),
        precision_digits=format_digits,
        propagation_config=propagation_config,
        propagation_method=propagation_method,
    )
    if not results:
        return None
    formula = str(payload.get("formula") or "")
    plots = [_snapshot_plain_mapping(plot) for plot in plot_metadata]
    row_count = len(data_rows) if data_rows else len(results)

    metric_rows = [
        {
            "key": f"result_value.{row['index']}",
            "label_key": "uncertainty.metric.result_value",
            "value": row["value"],
            "uncertainty": row["uncertainty"],
            "row_index": row["index"],
            "render_group": "metric",
        }
        for row in results
    ]
    diagnostic_rows = analysis_rows_to_json(
        [
            *_contribution_diagnostic_rows(results, precision_digits=format_digits),
            *_sensitivity_diagnostic_rows(results, precision_digits=format_digits),
            *_comparison_diagnostic_rows(results),
            *_taylor_order_comparison_diagnostic_rows(results),
            *_propagation_diagnostic_rows(propagation_config),
        ]
    )
    units = payload.get("units")
    output_unit = _unit_annotation_text(units, "outputs", "result")
    csv_headers = ["index", "value", "uncertainty", "latex"]
    if output_unit:
        csv_headers.append("output_unit")
    snapshot: dict[str, object] = {
        "schema": UNCERTAINTY_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": UNCERTAINTY_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "uncertainty",
        "mode": "error_propagation",
        "formula": formula,
        "results": results,
        "metric_rows": metric_rows,
        "diagnostic_rows": diagnostic_rows,
        "row_flags": [],
        "warnings": _snapshot_text_sequence(payload.get("warnings")),
        "plot_spec_keys": ["uncertainty.result"] if plots else [],
        "plot_metadata": {
            "image_mode": "error",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": {
            "row_count": row_count,
            "source_columns": headers,
        },
        "display": {
            "csv_headers": csv_headers,
        },
        "precision": precision_payload,
        "compatibility": {
            "result_cache_kind": kind,
            "overview_state": str(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_uncertainty_latex_semantic_regeneration",
        },
    }
    if propagation_config is not None:
        snapshot["configuration"] = {"propagation": propagation_config}
    if isinstance(units, Mapping):
        snapshot["units"] = _snapshot_plain_mapping(units)
    try:
        normalized = normalize_json_payload(snapshot, path="uncertainty_result_snapshot")
    except (TypeError, ValueError):
        return None
    if not isinstance(normalized, Mapping):
        return None
    return {str(key): value for key, value in deepcopy(normalized).items()}


def render_uncertainty_snapshot_outputs(
    snapshot: Mapping[str, Any],
) -> tuple[str, list[dict[str, object]], list[str]] | None:
    """Regenerate deterministic error propagation text and CSV from a snapshot."""

    if snapshot.get("family") != "uncertainty":
        return None
    results = _snapshot_render_result_rows(snapshot.get("results"))
    if not results:
        return None
    formula = str(snapshot.get("formula") or "")
    source = snapshot.get("source")
    row_count = _snapshot_optional_int(source.get("row_count")) if isinstance(source, Mapping) else None
    output_unit = _unit_annotation_text(snapshot.get("units"), "outputs", "result")
    value_header = _label_with_unit("Value", output_unit)
    uncertainty_header = _label_with_unit("Uncertainty", output_unit)
    csv_headers = ["index", "value", "uncertainty", "latex"]
    if output_unit:
        csv_headers.append("output_unit")
    lines = [
        "## Error Propagation Results",
        "",
        f"**Formula**: `{formula}`",
        f"**Rows**: {row_count if row_count is not None else len(results)}",
        "",
        f"| # | {value_header} | {uncertainty_header} | LaTeX |",
        "| --- | --- | --- | --- |",
    ]
    csv_rows: list[dict[str, object]] = []
    for row in results:
        index = row["index"]
        value = row["value"]
        uncertainty = row["uncertainty"]
        latex = row["latex"]
        lines.append(
            f"| {index} | {_escape_markdown_cell(value)} | "
            f"{_escape_markdown_cell(uncertainty)} | {_escape_markdown_cell(latex)} |"
        )
        csv_rows.append(
            {
                "index": index,
                "value": value,
                "uncertainty": uncertainty,
                "latex": latex,
            }
        )
        if output_unit:
            csv_rows[-1]["output_unit"] = output_unit
    lines.append("")
    return "\n".join(lines), csv_rows, csv_headers


def _unit_annotation_text(units: Any, namespace: str, key: str) -> str:
    if not isinstance(units, Mapping):
        return ""
    annotations = units.get(namespace)
    if not isinstance(annotations, Mapping):
        return ""
    annotation = annotations.get(key)
    if isinstance(annotation, Mapping):
        unit = annotation.get("unit")
    else:
        unit = annotation
    return str(unit or "").strip()


def _label_with_unit(label: str, unit: str) -> str:
    unit_text = str(unit or "").strip()
    if not unit_text:
        return label
    return f"{label} [{_escape_markdown_cell(unit_text)}]"


def _snapshot_text_sequence(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return []
    return [str(item) for item in value]


def _snapshot_rows(value: Any) -> list[list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return []
    rows: list[list[str]] = []
    for row in value:
        if isinstance(row, Mapping):
            rows.append([str(item) for item in row.values()])
        elif isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray, memoryview)):
            rows.append([_snapshot_numeric_text(item) for item in row])
        else:
            rows.append([_snapshot_numeric_text(row)])
    return rows


def _snapshot_result_rows(
    value: Any,
    *,
    precision_digits: int,
    propagation_config: UncertaintyPropagationConfig | None = None,
    propagation_method: str | None = None,
) -> list[dict[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return []
    rows: list[dict[str, object]] = []
    for index, result in enumerate(value, 1):
        allow_sensitivities = propagation_method != "monte_carlo" and (
            propagation_config is None or propagation_config["method"] == "taylor"
        )
        if isinstance(result, Mapping):
            value_text = _snapshot_numeric_text(result.get("value", ""), precision_digits=precision_digits)
            uncertainty_text = _snapshot_numeric_text(
                result.get("uncertainty", "0") or "0",
                precision_digits=precision_digits,
            )
            contributions = result.get("contributions") or {}
            sensitivities = (
                _snapshot_sensitivity_metadata(
                    result.get("sensitivities"),
                    precision_digits=precision_digits,
                )
                if allow_sensitivities
                else None
            )
            latex_text = _snapshot_numeric_text(
                result.get("latex", f"{value_text} +/- {uncertainty_text}"),
                precision_digits=precision_digits,
            )
        else:
            value_text = _snapshot_numeric_text(getattr(result, "value", result), precision_digits=precision_digits)
            uncertainty_text = _snapshot_numeric_text(
                getattr(result, "uncertainty", "0") or "0",
                precision_digits=precision_digits,
            )
            contributions = getattr(result, "contributions", None) or {}
            sensitivities = (
                _snapshot_sensitivity_metadata(
                    getattr(result, "sensitivities", None),
                    precision_digits=precision_digits,
                )
                if allow_sensitivities
                else None
            )
            latex_text = f"{value_text} +/- {uncertainty_text}"
        if not isinstance(contributions, Mapping):
            contributions = {}
        comparison = None
        if isinstance(result, Mapping):
            comparison = _snapshot_comparison_metadata(
                result.get("comparison"),
                propagation_config=propagation_config,
                result_value=value_text,
                result_uncertainty=uncertainty_text,
                precision_digits=precision_digits,
            )
        taylor_order_comparison = None
        if isinstance(result, Mapping):
            taylor_order_comparison = _snapshot_taylor_order_comparison_metadata(
                result.get("taylor_order_comparison"),
                propagation_config=propagation_config,
                result_value=value_text,
                result_uncertainty=uncertainty_text,
                precision_digits=precision_digits,
            )
        result_row: dict[str, object] = {
            "index": index,
            "value": value_text,
            "uncertainty": uncertainty_text,
            "latex": latex_text,
            "contributions": {
                str(name): _snapshot_numeric_text(contribution, precision_digits=precision_digits)
                for name, contribution in contributions.items()
            },
        }
        if comparison is not None:
            result_row["comparison"] = comparison
        if taylor_order_comparison is not None:
            result_row["taylor_order_comparison"] = taylor_order_comparison
        if sensitivities:
            result_row["sensitivities"] = sensitivities
        rows.append(
            result_row
        )
    return rows


def _snapshot_render_result_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return []
    rows: list[dict[str, Any]] = []
    for fallback_index, item in enumerate(value, 1):
        if not isinstance(item, Mapping):
            continue
        index = _snapshot_optional_int(item.get("index")) or fallback_index
        rows.append(
            {
                "index": index,
                "value": str(item.get("value") or ""),
                "uncertainty": str(item.get("uncertainty") or ""),
                "latex": str(item.get("latex") or ""),
            }
        )
    return rows


def _contribution_diagnostic_rows(
    results: Sequence[Mapping[str, object]],
    *,
    precision_digits: int,
) -> list[AnalysisRow]:
    with precision_guard(precision_digits):
        rows: list[AnalysisRow] = []
        totals: dict[str, mp.mpf] = {}
        first_seen: dict[str, int] = {}
        key_tokens: dict[str, str] = {}
        used_key_tokens: set[str] = set()
        for result in results:
            result_index = _snapshot_optional_int(result.get("index"))
            if result_index is None:
                continue
            contributions = result.get("contributions")
            if not isinstance(contributions, Mapping):
                continue
            for raw_name, raw_variance in contributions.items():
                variance = _nonnegative_finite_mpf_or_none(raw_variance, precision_digits=precision_digits)
                if variance is None:
                    continue
                name = str(raw_name)
                key_token = _contribution_key_token(
                    name,
                    key_tokens=key_tokens,
                    used_key_tokens=used_key_tokens,
                )
                rows.append(
                    AnalysisRow(
                        key=f"contribution.{result_index}.{key_token}",
                        label_key="uncertainty.diagnostic.contribution_variance",
                        value=_format_contribution_mpf(variance, precision_digits=precision_digits),
                        source=name,
                        row_index=result_index,
                        render_group="diagnostic",
                    )
                )
                if name not in first_seen:
                    first_seen[name] = len(first_seen)
                    totals[name] = mp.mpf("0")
                totals[name] += variance

        total_variance = mp.fsum(totals.values()) if totals else mp.mpf("0")
        ordered_totals = sorted(totals.items(), key=lambda item: (-item[1], first_seen[item[0]]))
        for name, variance in ordered_totals:
            key_token = _contribution_key_token(
                name,
                key_tokens=key_tokens,
                used_key_tokens=used_key_tokens,
            )
            rows.append(
                AnalysisRow(
                    key=f"contribution_total.{key_token}",
                    label_key="uncertainty.diagnostic.contribution_total_variance",
                    value=_format_contribution_mpf(variance, precision_digits=precision_digits),
                    uncertainty=_contribution_percent_text(
                        variance,
                        total_variance,
                        precision_digits=precision_digits,
                    ),
                    source=name,
                    render_group="diagnostic",
                )
            )
        for name, variance in ordered_totals:
            key_token = _contribution_key_token(
                name,
                key_tokens=key_tokens,
                used_key_tokens=used_key_tokens,
            )
            rows.append(
                AnalysisRow(
                    key=f"contribution_percent.{key_token}",
                    label_key="uncertainty.diagnostic.contribution_percent",
                    value=_contribution_percent_text(
                        variance,
                        total_variance,
                        precision_digits=precision_digits,
                    ),
                    source=name,
                    render_group="diagnostic",
                )
            )
        cumulative_variance = mp.mpf("0")
        for name, variance in ordered_totals:
            cumulative_variance += variance
            key_token = _contribution_key_token(
                name,
                key_tokens=key_tokens,
                used_key_tokens=used_key_tokens,
            )
            rows.append(
                AnalysisRow(
                    key=f"contribution_cumulative_percent.{key_token}",
                    label_key="uncertainty.diagnostic.contribution_cumulative_percent",
                    value=_contribution_percent_text(
                        cumulative_variance,
                        total_variance,
                        precision_digits=precision_digits,
                    ),
                    source=name,
                    render_group="diagnostic",
                )
            )
        return rows


def _sensitivity_diagnostic_rows(
    results: Sequence[Mapping[str, object]],
    *,
    precision_digits: int,
) -> list[AnalysisRow]:
    with precision_guard(precision_digits):
        rows: list[AnalysisRow] = []
        key_tokens: dict[str, str] = {}
        used_key_tokens: set[str] = set()
        for result in results:
            result_index = _snapshot_optional_int(result.get("index"))
            if result_index is None:
                continue
            sensitivities = result.get("sensitivities")
            if not isinstance(sensitivities, Mapping):
                continue
            for raw_name, raw_entry in sensitivities.items():
                entry = _normalized_sensitivity_entry(raw_entry, precision_digits=precision_digits)
                if entry is None:
                    continue
                name = str(raw_name)
                key_token = _contribution_key_token(
                    name,
                    key_tokens=key_tokens,
                    used_key_tokens=used_key_tokens,
                )
                rows.append(
                    AnalysisRow(
                        key=f"sensitivity_absolute.{result_index}.{key_token}",
                        label_key="uncertainty.diagnostic.sensitivity_absolute",
                        value=str(entry["absolute"]),
                        source=name,
                        row_index=result_index,
                        render_group="diagnostic",
                    )
                )
                relative = entry.get("relative")
                if relative is not None:
                    rows.append(
                        AnalysisRow(
                            key=f"sensitivity_relative.{result_index}.{key_token}",
                            label_key="uncertainty.diagnostic.sensitivity_relative",
                            value=str(relative),
                            source=name,
                            row_index=result_index,
                            render_group="diagnostic",
                        )
                    )
                    continue
                omission_reason = entry.get("relative_omission_reason")
                if omission_reason is not None:
                    rows.append(
                        AnalysisRow(
                            key=f"sensitivity_relative_omitted.{result_index}.{key_token}",
                            label_key="uncertainty.diagnostic.sensitivity_relative_omitted",
                            value=str(omission_reason),
                            source=name,
                            row_index=result_index,
                            message_key=(
                                "uncertainty.diagnostic.sensitivity_relative_omitted."
                                f"{omission_reason}"
                            ),
                            render_group="diagnostic",
                        )
                    )
        return rows


def _comparison_diagnostic_rows(results: Sequence[Mapping[str, object]]) -> list[AnalysisRow]:
    rows: list[AnalysisRow] = []
    for result in results:
        result_index = _snapshot_optional_int(result.get("index"))
        comparison = result.get("comparison")
        if result_index is None or not isinstance(comparison, Mapping):
            continue
        method = str(comparison.get("method") or "taylor_vs_monte_carlo")
        for field_name in (
            "absolute_result_tolerance",
            "relative_result_tolerance",
            "sample_count",
            "taylor_order",
            "taylor_mean",
            "taylor_std",
            "monte_carlo_mean",
            "monte_carlo_std",
            "monte_carlo_standard_error",
            "practical_floor",
            "absolute_mean_difference",
            "mean_disagreement_threshold",
            "mean_disagreement",
        ):
            value = _comparison_analysis_value(comparison.get(field_name))
            if value is None:
                continue
            rows.append(
                AnalysisRow(
                    key=f"comparison.{result_index}.{field_name}",
                    label_key=f"uncertainty.diagnostic.comparison.{field_name}",
                    value=value,
                    row_index=result_index,
                    method=method,
                    render_group="diagnostic",
                )
            )
        unavailable_reason = _comparison_analysis_value(comparison.get("comparison_unavailable_reason"))
        if unavailable_reason is not None:
            rows.append(
                AnalysisRow(
                    key=f"comparison.{result_index}.unavailable",
                    label_key="uncertainty.diagnostic.comparison.unavailable",
                    value=unavailable_reason,
                    row_index=result_index,
                    method=method,
                    message_key=f"uncertainty.diagnostic.comparison.unavailable.{unavailable_reason}",
                    render_group="diagnostic",
                )
            )
            continue
        mean_omission_reason = _comparison_analysis_value(comparison.get("mean_disagreement_omission_reason"))
        if mean_omission_reason is not None:
            rows.append(
                AnalysisRow(
                    key=f"comparison.{result_index}.mean_disagreement_omitted",
                    label_key="uncertainty.diagnostic.comparison.mean_disagreement_omitted",
                    value=mean_omission_reason,
                    row_index=result_index,
                    method=method,
                    message_key=f"uncertainty.diagnostic.comparison.mean_disagreement_omitted.{mean_omission_reason}",
                    render_group="diagnostic",
                )
            )
        relative_std_difference = _comparison_analysis_value(comparison.get("relative_std_difference"))
        if relative_std_difference is not None:
            rows.append(
                AnalysisRow(
                    key=f"comparison.{result_index}.relative_std_difference",
                    label_key="uncertainty.diagnostic.comparison.relative_std_difference",
                    value=relative_std_difference,
                    row_index=result_index,
                    method=method,
                    render_group="diagnostic",
                )
            )
            continue
        omission_reason = _comparison_analysis_value(comparison.get("relative_std_difference_omission_reason"))
        if omission_reason is not None:
            rows.append(
                AnalysisRow(
                    key=f"comparison.{result_index}.relative_std_difference_omitted",
                    label_key="uncertainty.diagnostic.comparison.relative_std_difference_omitted",
                    value=omission_reason,
                    row_index=result_index,
                    method=method,
                    message_key=f"uncertainty.diagnostic.comparison.relative_std_difference_omitted.{omission_reason}",
                    render_group="diagnostic",
                )
            )
    return rows


def _taylor_order_comparison_diagnostic_rows(results: Sequence[Mapping[str, object]]) -> list[AnalysisRow]:
    rows: list[AnalysisRow] = []
    for result in results:
        result_index = _snapshot_optional_int(result.get("index"))
        comparison = result.get("taylor_order_comparison")
        if result_index is None or not isinstance(comparison, Mapping):
            continue
        method = str(comparison.get("method") or TAYLOR_ORDER_COMPARISON_METHOD)
        for field_name in (
            "order_low",
            "order_high",
            "order1_mean",
            "order1_std",
            "order2_mean",
            "order2_std",
            "absolute_mean_difference",
        ):
            value = _comparison_analysis_value(comparison.get(field_name))
            if value is None:
                continue
            rows.append(
                AnalysisRow(
                    key=f"taylor_order_comparison.{result_index}.{field_name}",
                    label_key=f"uncertainty.diagnostic.taylor_order_comparison.{field_name}",
                    value=value,
                    row_index=result_index,
                    method=method,
                    render_group="diagnostic",
                )
            )
        unavailable_reason = _comparison_analysis_value(comparison.get("comparison_unavailable_reason"))
        if unavailable_reason is not None:
            rows.append(
                AnalysisRow(
                    key=f"taylor_order_comparison.{result_index}.unavailable",
                    label_key="uncertainty.diagnostic.taylor_order_comparison.unavailable",
                    value=unavailable_reason,
                    row_index=result_index,
                    method=method,
                    message_key=(
                        "uncertainty.diagnostic.taylor_order_comparison.unavailable."
                        f"{unavailable_reason}"
                    ),
                    render_group="diagnostic",
                )
            )
            continue
        relative_std_difference = _comparison_analysis_value(comparison.get("relative_std_difference"))
        if relative_std_difference is not None:
            rows.append(
                AnalysisRow(
                    key=f"taylor_order_comparison.{result_index}.relative_std_difference",
                    label_key="uncertainty.diagnostic.taylor_order_comparison.relative_std_difference",
                    value=relative_std_difference,
                    row_index=result_index,
                    method=method,
                    render_group="diagnostic",
                )
            )
            continue
        omission_reason = _comparison_analysis_value(
            comparison.get("relative_std_difference_omission_reason")
        )
        if omission_reason is not None:
            rows.append(
                AnalysisRow(
                    key=f"taylor_order_comparison.{result_index}.relative_std_difference_omitted",
                    label_key="uncertainty.diagnostic.taylor_order_comparison.relative_std_difference_omitted",
                    value=omission_reason,
                    row_index=result_index,
                    method=method,
                    message_key=(
                        "uncertainty.diagnostic.taylor_order_comparison.relative_std_difference_omitted."
                        f"{omission_reason}"
                    ),
                    render_group="diagnostic",
                )
            )
    return rows


def _comparison_analysis_value(value: object) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def normalize_uncertainty_propagation_config(
    *,
    method: str,
    order: int,
    mc_samples: int | None,
    mc_seed: int | None,
) -> UncertaintyPropagationConfig:
    """Return the effective error-propagation configuration used by the engine."""

    normalized_method = _normalize_method(method)
    normalized_order = _normalize_propagation_order(order)
    if normalized_method == "taylor":
        if normalized_order not in {1, 2}:
            raise ValueError(
                f"propagation.order must be 1 or 2 for Taylor propagation; got {normalized_order}."
            )
        return {
            "method": "taylor",
            "order": normalized_order,
            "mc_samples": None,
            "mc_seed": None,
        }
    normalized_samples = _validate_optional_int(mc_samples, field_name="propagation.mc_samples")
    if normalized_samples is None:
        normalized_samples = DEFAULT_MONTE_CARLO_SAMPLE_COUNT
    if normalized_samples is not None and normalized_samples < 100:
        raise ValueError("propagation.mc_samples must be at least 100 when Monte Carlo propagation is used.")
    return {
        "method": "monte_carlo",
        "order": normalized_order,
        "mc_samples": normalized_samples,
        "mc_seed": _validate_optional_int(mc_seed, field_name="propagation.mc_seed"),
    }


def _snapshot_propagation_metadata(value: Any) -> UncertaintyPropagationConfig | None:
    if not isinstance(value, Mapping):
        return None
    raw_method = value.get("method")
    raw_order = value.get("order")
    raw_mc_samples = value.get("mc_samples")
    raw_mc_seed = value.get("mc_seed")
    if not isinstance(raw_method, str):
        return None
    if isinstance(raw_order, bool) or not isinstance(raw_order, int):
        return None
    try:
        method = _normalize_method(raw_method)
    except (TypeError, ValueError):
        return None
    if method == "monte_carlo":
        if raw_mc_samples is not None and (isinstance(raw_mc_samples, bool) or not isinstance(raw_mc_samples, int)):
            return None
        if raw_mc_seed is not None and (isinstance(raw_mc_seed, bool) or not isinstance(raw_mc_seed, int)):
            return None
        mc_samples = raw_mc_samples
        mc_seed = raw_mc_seed
    else:
        mc_samples = None
        mc_seed = None
    try:
        return normalize_uncertainty_propagation_config(
            method=method,
            order=raw_order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
        )
    except (TypeError, ValueError):
        return None


def _propagation_diagnostic_rows(propagation: UncertaintyPropagationConfig | None) -> list[AnalysisRow]:
    if propagation is None:
        return []
    rows: list[AnalysisRow] = []
    fields: tuple[tuple[str, str | int | None], ...] = (
        ("method", propagation["method"]),
        ("order", propagation["order"]),
        ("mc_samples", propagation["mc_samples"]),
        ("mc_seed", propagation["mc_seed"]),
    )
    for field_name, value in fields:
        rows.append(
            AnalysisRow(
                key=f"configuration.propagation.{field_name}",
                label_key=f"uncertainty.configuration.propagation.{field_name}",
                value=value,
                render_group="diagnostic",
            )
        )
    return rows


def _contribution_key_token(
    name: str,
    *,
    key_tokens: dict[str, str],
    used_key_tokens: set[str],
) -> str:
    existing = key_tokens.get(name)
    if existing is not None:
        return existing

    base = "".join(character if character.isascii() and (character.isalnum() or character in "_-") else "_" for character in name)
    base = base.strip("_") or "item"
    token = base
    suffix = 2
    while token in used_key_tokens:
        token = f"{base}_{suffix}"
        suffix += 1
    key_tokens[name] = token
    used_key_tokens.add(token)
    return token


def _nonnegative_finite_mpf_or_none(value: object, *, precision_digits: int) -> mp.mpf | None:
    try:
        with precision_guard(precision_digits):
            parsed = mp.mpf(str(value))
    except (TypeError, ValueError):
        return None
    if not mp.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _contribution_percent_text(
    variance: mp.mpf,
    total_variance: mp.mpf,
    *,
    precision_digits: int,
) -> str:
    if not mp.isfinite(total_variance) or total_variance <= 0:
        return "0%"
    with precision_guard(precision_digits):
        percent = (variance / total_variance) * 100
    return f"{_format_contribution_mpf(percent, precision_digits=min(15, precision_digits))}%"


def _format_contribution_mpf(value: mp.mpf, *, precision_digits: int) -> str:
    digits = max(1, int(precision_digits))
    text = mp.nstr(value, n=digits)
    return "0" if text == "0.0" else text


def _snapshot_numeric_text(value: Any, *, precision_digits: int | None = None) -> str:
    if isinstance(value, mp.mpf):
        integer_text = _mpf_exact_integer_text(value)
        if integer_text is not None:
            return integer_text
        requested_digits = max(1, int(precision_digits or mp.dps))
        effective_digits = min(requested_digits, _mpf_display_decimal_digits(value))
        with precision_guard(effective_digits):
            return str(value)
    return str(value)


def _mpf_exact_integer_text(value: mp.mpf) -> str | None:
    if not mp.isfinite(value):
        return None
    try:
        sign, mantissa, exponent, _bit_count = value._mpf_  # noqa: SLF001 - exact mpf payload is needed here.
        mantissa_int = int(mantissa)
        exponent_int = int(exponent)
    except (AttributeError, TypeError, ValueError):
        return None
    if exponent_int >= 0:
        integer = mantissa_int << exponent_int
    else:
        denominator = 1 << abs(exponent_int)
        if mantissa_int % denominator != 0:
            return None
        integer = mantissa_int // denominator
    if sign:
        integer = -integer
    return str(integer)


def _mpf_display_decimal_digits(value: mp.mpf) -> int:
    stored_digits = _mpf_stored_decimal_digits(value)
    try:
        exponent = int(value._mpf_[2])  # noqa: SLF001 - mpmath exposes stored precision only here.
    except (AttributeError, TypeError, ValueError, IndexError):
        return stored_digits
    if exponent < 0 and abs(exponent) <= 12:
        return max(15, stored_digits)
    return stored_digits


def _mpf_stored_decimal_digits(value: mp.mpf) -> int:
    try:
        bit_count = int(value._mpf_[3])  # noqa: SLF001 - mpmath exposes stored precision only here.
    except (AttributeError, TypeError, ValueError, IndexError):
        return max(1, int(mp.dps))
    return max(1, int(bit_count * 0.3010299956639812))


def _snapshot_plain_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    return {str(key): _snapshot_plain_value(item) for key, item in value.items()}


def _format_monte_carlo_distribution_payload(
    value: Any,
    *,
    precision_digits: int,
) -> dict[str, object]:
    return _snapshot_monte_carlo_distribution_metadata(value, precision_digits=precision_digits) or {}


def _snapshot_monte_carlo_distribution_metadata(
    value: Any,
    *,
    precision_digits: int,
) -> dict[str, object] | None:
    if _contains_json_float(value) or not isinstance(value, Mapping):
        return None
    if value.get("schema") != "datalab.monte_carlo_distribution_summary" or value.get("schema_version") != 1:
        return None
    count_fields = (
        "requested_sample_count",
        "evaluated_sample_count",
        "accepted_sample_count",
        "rejected_sample_count",
        "finite_sample_count",
    )
    counts: dict[str, int] = {}
    for field_name in count_fields:
        count = _nonnegative_int(value.get(field_name))
        if count is None:
            return None
        counts[field_name] = count
    if counts["evaluated_sample_count"] != counts["requested_sample_count"]:
        return None
    if counts["accepted_sample_count"] + counts["rejected_sample_count"] != counts["evaluated_sample_count"]:
        return None
    if counts["finite_sample_count"] > counts["accepted_sample_count"]:
        return None
    mean = _distribution_numeric_text(value.get("mean"), precision_digits=precision_digits)
    std = _distribution_numeric_text(value.get("std"), precision_digits=precision_digits)
    if mean is None or std is None:
        return None
    try:
        std_value = mp.mpf(std)
    except (TypeError, ValueError):
        return None
    if not mp.isfinite(std_value) or std_value < 0:
        return None
    histogram = value.get("histogram")
    if not isinstance(histogram, Mapping):
        return None
    bin_edges = _distribution_numeric_sequence(histogram.get("bin_edges"), precision_digits=precision_digits)
    histogram_counts = _distribution_count_sequence(histogram.get("counts"))
    if bin_edges is None or histogram_counts is None:
        return None
    if len(bin_edges) != len(histogram_counts) + 1:
        return None
    if any(mp.mpf(right) <= mp.mpf(left) for left, right in zip(bin_edges, bin_edges[1:])):
        return None
    if sum(histogram_counts) != counts["finite_sample_count"]:
        return None
    percentiles_raw = value.get("percentiles")
    if not isinstance(percentiles_raw, Mapping):
        return None
    percentiles: dict[str, str] = {}
    for key in ("2.5", "50", "97.5"):
        percentile = _distribution_numeric_text(percentiles_raw.get(key), precision_digits=precision_digits)
        if percentile is None:
            return None
        percentiles[key] = percentile
    p_low = mp.mpf(percentiles["2.5"])
    p_mid = mp.mpf(percentiles["50"])
    p_high = mp.mpf(percentiles["97.5"])
    if not (
        mp.isfinite(p_low)
        and mp.isfinite(p_mid)
        and mp.isfinite(p_high)
        and p_low <= p_mid <= p_high
    ):
        return None
    if bin_edges and (p_low < mp.mpf(bin_edges[0]) or p_high > mp.mpf(bin_edges[-1])):
        return None
    return {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        **counts,
        "mean": mean,
        "std": std,
        "histogram": {
            "bin_edges": bin_edges,
            "counts": histogram_counts,
        },
        "percentiles": percentiles,
    }


def _contains_json_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_json_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return any(_contains_json_float(item) for item in value)
    return False


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _distribution_numeric_sequence(value: object, *, precision_digits: int) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return None
    normalized: list[str] = []
    for item in value:
        numeric_text = _distribution_numeric_text(item, precision_digits=precision_digits)
        if numeric_text is None:
            return None
        normalized.append(numeric_text)
    return normalized


def _distribution_count_sequence(value: object) -> list[int] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        return None
    normalized: list[int] = []
    for item in value:
        count = _nonnegative_int(item)
        if count is None:
            return None
        normalized.append(count)
    return normalized


def _distribution_numeric_text(value: object, *, precision_digits: int) -> str | None:
    if isinstance(value, float):
        return None
    try:
        with precision_guard(precision_digits):
            parsed = mp.mpf(str(value))
    except (TypeError, ValueError):
        return None
    if not mp.isfinite(parsed):
        return None
    return _format_contribution_mpf(parsed, precision_digits=precision_digits)


def _snapshot_raw_propagation_method(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    raw_method = value.get("method")
    if not isinstance(raw_method, str):
        return None
    try:
        return _normalize_method(raw_method)
    except (TypeError, ValueError):
        return None


def _snapshot_plain_value(value: Any) -> object:
    if isinstance(value, float):
        raise TypeError("JSON floats are not allowed in uncertainty result snapshots.")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, mp.mpf):
        return str(value)
    if isinstance(value, Mapping):
        return _snapshot_plain_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [_snapshot_plain_value(item) for item in value]
    return str(value)


def _format_sensitivity_payload(
    value: Any,
    *,
    precision_digits: int,
) -> dict[str, dict[str, object]]:
    return _snapshot_sensitivity_metadata(value, precision_digits=precision_digits) or {}


def _snapshot_sensitivity_metadata(
    value: Any,
    *,
    precision_digits: int,
) -> dict[str, dict[str, object]] | None:
    if not isinstance(value, Mapping):
        return None
    normalized: dict[str, dict[str, object]] = {}
    for raw_name, raw_entry in value.items():
        if _sensitivity_entry_has_float_numbers(raw_entry):
            return None
        entry = _normalized_sensitivity_entry(raw_entry, precision_digits=precision_digits)
        if entry is not None:
            normalized[str(raw_name)] = entry
    return normalized or None


def _sensitivity_entry_has_float_numbers(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and (isinstance(value.get("absolute"), float) or isinstance(value.get("relative"), float))
    )


def _normalized_sensitivity_entry(
    value: object,
    *,
    precision_digits: int,
) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    if isinstance(value.get("absolute"), float) or isinstance(value.get("relative"), float):
        return None
    absolute = _nonnegative_finite_mpf_or_none(value.get("absolute"), precision_digits=precision_digits)
    if absolute is None:
        return None
    relative_raw = value.get("relative")
    omission_reason_raw = value.get("relative_omission_reason")
    if relative_raw is None:
        omission_reason = _sensitivity_relative_omission_reason(omission_reason_raw)
        if omission_reason is None:
            return None
        return {
            "absolute": _format_contribution_mpf(absolute, precision_digits=precision_digits),
            "relative": None,
            "relative_omission_reason": omission_reason,
        }
    if omission_reason_raw is not None:
        return None
    relative = _nonnegative_finite_mpf_or_none(relative_raw, precision_digits=precision_digits)
    if relative is None:
        return None
    return {
        "absolute": _format_contribution_mpf(absolute, precision_digits=precision_digits),
        "relative": _format_contribution_mpf(relative, precision_digits=precision_digits),
        "relative_omission_reason": None,
    }


def _sensitivity_relative_omission_reason(value: object) -> str | None:
    if not isinstance(value, str) or value not in SENSITIVITY_RELATIVE_OMISSION_REASONS:
        return None
    return value


def _snapshot_comparison_metadata(
    value: Any,
    *,
    propagation_config: UncertaintyPropagationConfig | None,
    result_value: str,
    result_uncertainty: str,
    precision_digits: int,
) -> dict[str, object] | None:
    if propagation_config is None or propagation_config["method"] != "monte_carlo":
        return None
    if not isinstance(value, Mapping):
        return None
    if value.get("method") != "taylor_vs_monte_carlo":
        return None
    sample_count = _comparison_positive_int(value.get("sample_count"))
    taylor_order = _comparison_positive_int(value.get("taylor_order"))
    if sample_count is None or taylor_order is None:
        return None
    if sample_count != propagation_config["mc_samples"] or taylor_order != propagation_config["order"]:
        return None
    if (
        value.get("absolute_result_tolerance") != COMPARISON_ABSOLUTE_RESULT_TOLERANCE
        or value.get("relative_result_tolerance") != COMPARISON_RELATIVE_RESULT_TOLERANCE
    ):
        return None
    normalized: dict[str, object] = {}
    normalized["method"] = "taylor_vs_monte_carlo"
    normalized["absolute_result_tolerance"] = COMPARISON_ABSOLUTE_RESULT_TOLERANCE
    normalized["relative_result_tolerance"] = COMPARISON_RELATIVE_RESULT_TOLERANCE
    normalized["sample_count"] = sample_count
    normalized["taylor_order"] = taylor_order
    raw_unavailable_reason = value.get("comparison_unavailable_reason")
    if raw_unavailable_reason is not None:
        unavailable_reason = _comparison_omission_reason(
            raw_unavailable_reason,
            allowed=COMPARISON_UNAVAILABLE_REASONS,
        )
        if unavailable_reason is None:
            return None
        normalized["comparison_unavailable_reason"] = unavailable_reason
        return normalized

    if taylor_order not in {1, 2}:
        return None
    for field_name in (
        "taylor_mean",
        "taylor_std",
        "monte_carlo_mean",
        "monte_carlo_std",
        "monte_carlo_standard_error",
        "practical_floor",
        "absolute_mean_difference",
        "mean_disagreement_threshold",
    ):
        field_value = _comparison_numeric_text(value.get(field_name))
        if field_value is None:
            return None
        normalized[field_name] = field_value
    with precision_guard(precision_digits):
        parsed_values = {
            field_name: mp.mpf(str(normalized[field_name]))
            for field_name in (
                "taylor_mean",
                "taylor_std",
                "monte_carlo_mean",
                "monte_carlo_std",
                "monte_carlo_standard_error",
                "practical_floor",
                "absolute_mean_difference",
                "mean_disagreement_threshold",
            )
        }
        try:
            result_mean = mp.mpf(result_value)
            result_std = mp.fabs(mp.mpf(result_uncertainty))
        except (TypeError, ValueError):
            return None
        if not _comparison_mpf_equal(
            parsed_values["monte_carlo_mean"],
            result_mean,
        ):
            return None
        if not _comparison_mpf_equal(
            parsed_values["monte_carlo_std"],
            result_std,
        ):
            return None
        for nonnegative_field in (
            "taylor_std",
            "monte_carlo_std",
            "monte_carlo_standard_error",
            "practical_floor",
            "absolute_mean_difference",
            "mean_disagreement_threshold",
        ):
            field_value = parsed_values[nonnegative_field]
            if mp.isfinite(field_value) and field_value < 0:
                return None
        expected_standard_error = parsed_values["monte_carlo_std"] / mp.sqrt(sample_count)
        expected_practical_floor = max(
            mp.mpf(COMPARISON_ABSOLUTE_RESULT_TOLERANCE),
            mp.mpf(COMPARISON_RELATIVE_RESULT_TOLERANCE)
            * max(mp.fabs(parsed_values["taylor_mean"]), mp.fabs(parsed_values["monte_carlo_mean"])),
        )
        expected_mean_difference = mp.fabs(parsed_values["monte_carlo_mean"] - parsed_values["taylor_mean"])
        expected_threshold = max(3 * expected_standard_error, expected_practical_floor)
        if not _comparison_mpf_matches(
            parsed_values["monte_carlo_standard_error"],
            expected_standard_error,
            precision_digits=precision_digits,
        ):
            return None
        if not _comparison_mpf_matches(
            parsed_values["practical_floor"],
            expected_practical_floor,
            precision_digits=precision_digits,
        ):
            return None
        if not _comparison_mpf_matches(
            parsed_values["absolute_mean_difference"],
            expected_mean_difference,
            precision_digits=precision_digits,
        ):
            return None
        if not _comparison_mpf_matches(
            parsed_values["mean_disagreement_threshold"],
            expected_threshold,
            precision_digits=precision_digits,
        ):
            return None
        mean_disagreement = value.get("mean_disagreement")
        mean_omission_reason = _comparison_omission_reason(
            value.get("mean_disagreement_omission_reason"),
            allowed=COMPARISON_MEAN_OMISSION_REASONS,
        )
        if isinstance(mean_disagreement, bool):
            if not mp.isfinite(expected_mean_difference) or not mp.isfinite(expected_threshold):
                return None
            if mean_disagreement is not bool(expected_mean_difference > expected_threshold):
                return None
            normalized["mean_disagreement"] = mean_disagreement
        elif mean_disagreement is None and mean_omission_reason is not None:
            if (
                mean_omission_reason == "nonfinite_mean"
                and mp.isfinite(expected_mean_difference)
                and mp.isfinite(expected_threshold)
            ):
                return None
            normalized["mean_disagreement"] = None
            normalized["mean_disagreement_omission_reason"] = mean_omission_reason
        else:
            return None

        relative_std_difference = value.get("relative_std_difference")
        raw_relative_omission_reason = value.get("relative_std_difference_omission_reason")
        if relative_std_difference is not None:
            if raw_relative_omission_reason is not None:
                return None
            relative_value = _comparison_numeric_text(relative_std_difference)
            if relative_value is None:
                return None
            parsed_relative_value = mp.mpf(relative_value)
            expected_relative_value = _expected_relative_std_difference(
                parsed_values["taylor_std"],
                parsed_values["monte_carlo_std"],
            )
            if expected_relative_value is None:
                return None
            if not _comparison_mpf_matches(
                parsed_relative_value,
                expected_relative_value,
                precision_digits=precision_digits,
            ):
                return None
            normalized["relative_std_difference"] = relative_value
            normalized["relative_std_difference_omission_reason"] = None
        else:
            relative_omission_reason = _comparison_omission_reason(
                raw_relative_omission_reason,
                allowed=COMPARISON_STD_OMISSION_REASONS,
            )
            if relative_omission_reason is not None:
                expected_relative_omission = _expected_relative_std_omission_reason(
                    parsed_values["taylor_std"],
                    parsed_values["monte_carlo_std"],
                )
                if relative_omission_reason != expected_relative_omission:
                    return None
                normalized["relative_std_difference"] = None
                normalized["relative_std_difference_omission_reason"] = relative_omission_reason
            elif raw_relative_omission_reason is not None:
                return None
            else:
                return None
    return normalized


def _snapshot_taylor_order_comparison_metadata(
    value: Any,
    *,
    propagation_config: UncertaintyPropagationConfig | None,
    result_value: str,
    result_uncertainty: str,
    precision_digits: int,
) -> dict[str, object] | None:
    if propagation_config is None or propagation_config["order"] != 2:
        return None
    if not isinstance(value, Mapping):
        return None
    if value.get("method") != TAYLOR_ORDER_COMPARISON_METHOD:
        return None
    order_low = _comparison_positive_int(value.get("order_low"))
    order_high = _comparison_positive_int(value.get("order_high"))
    if order_low != 1 or order_high != 2:
        return None
    normalized: dict[str, object] = {
        "method": TAYLOR_ORDER_COMPARISON_METHOD,
        "order_low": 1,
        "order_high": 2,
    }
    raw_unavailable_reason = value.get("comparison_unavailable_reason")
    if raw_unavailable_reason is not None:
        unavailable_reason = _comparison_omission_reason(
            raw_unavailable_reason,
            allowed=COMPARISON_UNAVAILABLE_REASONS,
        )
        if unavailable_reason is None:
            return None
        normalized["comparison_unavailable_reason"] = unavailable_reason
        return normalized

    for field_name in (
        "order1_mean",
        "order1_std",
        "order2_mean",
        "order2_std",
        "absolute_mean_difference",
    ):
        field_value = _comparison_numeric_text(value.get(field_name))
        if field_value is None:
            return None
        normalized[field_name] = field_value

    with precision_guard(precision_digits):
        parsed_values = {
            field_name: mp.mpf(str(normalized[field_name]))
            for field_name in (
                "order1_mean",
                "order1_std",
                "order2_mean",
                "order2_std",
                "absolute_mean_difference",
            )
        }
        for nonnegative_field in ("order1_std", "order2_std", "absolute_mean_difference"):
            field_value = parsed_values[nonnegative_field]
            if mp.isfinite(field_value) and field_value < 0:
                return None
        if propagation_config["method"] == "taylor":
            try:
                selected_result_value = mp.mpf(result_value)
                selected_result_uncertainty = mp.fabs(mp.mpf(result_uncertainty))
            except (TypeError, ValueError):
                return None
            if not _comparison_mpf_equal(parsed_values["order2_mean"], selected_result_value):
                return None
            if not _comparison_mpf_equal(parsed_values["order2_std"], selected_result_uncertainty):
                return None
        expected_absolute_mean_difference = mp.fabs(parsed_values["order2_mean"] - parsed_values["order1_mean"])
        if not _comparison_mpf_matches(
            parsed_values["absolute_mean_difference"],
            expected_absolute_mean_difference,
            precision_digits=precision_digits,
        ):
            return None
        relative_std_difference = value.get("relative_std_difference")
        raw_relative_omission_reason = value.get("relative_std_difference_omission_reason")
        relative_omission_reason = _comparison_omission_reason(
            raw_relative_omission_reason,
            allowed=COMPARISON_STD_OMISSION_REASONS,
        )
        if relative_std_difference is not None:
            if raw_relative_omission_reason is not None:
                return None
            relative_value = _comparison_numeric_text(relative_std_difference)
            if relative_value is None:
                return None
            parsed_relative_value = mp.mpf(relative_value)
            expected_relative_value = _expected_relative_std_difference(
                parsed_values["order1_std"],
                parsed_values["order2_std"],
            )
            if expected_relative_value is None:
                return None
            if not _comparison_mpf_matches(
                parsed_relative_value,
                expected_relative_value,
                precision_digits=precision_digits,
            ):
                return None
            normalized["relative_std_difference"] = relative_value
            normalized["relative_std_difference_omission_reason"] = None
        elif relative_omission_reason is not None:
            expected_relative_omission = _expected_relative_std_omission_reason(
                parsed_values["order1_std"],
                parsed_values["order2_std"],
            )
            if relative_omission_reason != expected_relative_omission:
                return None
            normalized["relative_std_difference"] = None
            normalized["relative_std_difference_omission_reason"] = relative_omission_reason
        elif raw_relative_omission_reason is not None:
            return None
        else:
            return None
    return normalized


def _comparison_mpf_matches(actual: mp.mpf, expected: mp.mpf, *, precision_digits: int) -> bool:
    if mp.isfinite(actual) and mp.isfinite(expected):
        exponent = -max(12, min(max(1, precision_digits) // 2, 40))
        tolerance = mp.mpf(10) ** exponent
        scale = max(mp.mpf("1"), mp.fabs(actual), mp.fabs(expected))
        return bool(mp.fabs(actual - expected) <= tolerance * scale)
    if mp.isnan(actual) or mp.isnan(expected):
        return bool(mp.isnan(actual) and mp.isnan(expected))
    return bool(actual == expected)


def _comparison_mpf_equal(actual: mp.mpf, expected: mp.mpf) -> bool:
    if mp.isnan(actual) or mp.isnan(expected):
        return bool(mp.isnan(actual) and mp.isnan(expected))
    return bool(actual == expected)


def _expected_relative_std_difference(taylor_std: mp.mpf, monte_carlo_std: mp.mpf) -> mp.mpf | None:
    if not mp.isfinite(taylor_std) or not mp.isfinite(monte_carlo_std):
        return None
    if taylor_std == 0 and monte_carlo_std == 0:
        return None
    return mp.fabs(monte_carlo_std - taylor_std) / max(taylor_std, monte_carlo_std)


def _expected_relative_std_omission_reason(taylor_std: mp.mpf, monte_carlo_std: mp.mpf) -> str | None:
    if not mp.isfinite(taylor_std) or not mp.isfinite(monte_carlo_std):
        return "nonfinite_std"
    if taylor_std == 0 and monte_carlo_std == 0:
        return "zero_std"
    return None


def _comparison_positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _comparison_numeric_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        mp.mpf(value)
    except (TypeError, ValueError):
        return None
    return value


def _comparison_omission_reason(value: object, *, allowed: frozenset[str]) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if value not in allowed:
        return None
    return value


def _snapshot_optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _escape_markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _required_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(f"{field_name} must be a sequence of strings.")
    items = [str(item) for item in value]
    if not items:
        raise ValueError(f"{field_name} must contain at least one item.")
    return items


def _required_matrix(value: Any, *, field_name: str, headers: Sequence[str]) -> list[list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(f"{field_name} must be a sequence of rows.")
    rows: list[list[str]] = []
    for row_index, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray, memoryview)):
            raise ValueError(f"{field_name}[{row_index}] must be a sequence.")
        if len(row) != len(headers):
            raise ValueError(f"{field_name}[{row_index}] must have {len(headers)} columns.")
        rows.append([str(item) for item in row])
    if not rows:
        raise ValueError(f"{field_name} must contain at least one row.")
    return rows


def _uncertain_rows(values: Sequence[Sequence[str]], uncertainties: Sequence[Sequence[str]]) -> list[list[UncertainValue]]:
    return [
        [
            UncertainValue(mp.mpf(value), mp.mpf(uncertainty))
            for value, uncertainty in zip(value_row, uncertainty_row, strict=True)
        ]
        for value_row, uncertainty_row in zip(values, uncertainties, strict=True)
    ]


def _uncertain_constants(value: Any) -> dict[str, UncertainValue]:
    constants = _mapping_or_empty(value, field_name="constants")
    parsed: dict[str, UncertainValue] = {}
    for raw_name, raw_entry in constants.items():
        name = str(raw_name)
        if not isinstance(raw_entry, Mapping):
            raise ValueError(f"constants.{name} must be a mapping.")
        parsed[name] = UncertainValue(
            mp.mpf(str(raw_entry.get("value"))),
            mp.mpf(str(raw_entry.get("uncertainty", "0"))),
        )
    return parsed


def _mapping_or_empty(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping.")
    return value


def _required_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _required_bool(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean.")
    return value


def _uncertain_result_payload(result: UncertainValue, precision_digits: int) -> dict[str, Any]:
    contributions = getattr(result, "contributions", None) or {}
    payload: dict[str, Any] = {
        "value": _format_mpf(result.value, precision_digits),
        "uncertainty": _format_mpf(result.uncertainty, precision_digits),
        "contributions": {
            str(name): _format_mpf(value, precision_digits)
            for name, value in contributions.items()
        },
    }
    sensitivities = _format_sensitivity_payload(
        getattr(result, "sensitivities", None),
        precision_digits=precision_digits,
    )
    if sensitivities:
        payload["sensitivities"] = sensitivities
    monte_carlo_distribution = _format_monte_carlo_distribution_payload(
        getattr(result, "monte_carlo_distribution", None),
        precision_digits=precision_digits,
    )
    if monte_carlo_distribution:
        payload["monte_carlo_distribution"] = monte_carlo_distribution
    return payload


def _taylor_order_comparison_payloads(
    *,
    headers: list[str],
    parsed_data: list[list[UncertainValue]],
    constants: dict[str, UncertainValue],
    formula: str,
    selected_results: Sequence[UncertainValue],
    propagation_config: UncertaintyPropagationConfig,
    precision_digits: int,
) -> list[dict[str, object]] | None:
    if propagation_config["order"] != 2:
        return None
    if propagation_config["method"] == "taylor":
        try:
            order1_results = apply_formula_to_data(
                headers,
                parsed_data,
                constants,
                formula,
                False,
                warnings=None,
                return_components=True,
                propagation_method="taylor",
                propagation_order=1,
                mc_samples=None,
                mc_seed=None,
                cancellation_checker=check_cancelled,
            )
        except ValueError:
            return [
                _taylor_order_comparison_unavailable_payload(reason="taylor_unavailable")
                for _ in selected_results
            ]
        order2_results = selected_results
    elif propagation_config["method"] == "monte_carlo":
        try:
            order1_results = apply_formula_to_data(
                headers,
                parsed_data,
                constants,
                formula,
                False,
                warnings=None,
                return_components=True,
                propagation_method="taylor",
                propagation_order=1,
                mc_samples=None,
                mc_seed=None,
                cancellation_checker=check_cancelled,
            )
            order2_results = apply_formula_to_data(
                headers,
                parsed_data,
                constants,
                formula,
                False,
                warnings=None,
                return_components=True,
                propagation_method="taylor",
                propagation_order=2,
                mc_samples=None,
                mc_seed=None,
                cancellation_checker=check_cancelled,
            )
        except ValueError:
            return [
                _taylor_order_comparison_unavailable_payload(reason="taylor_unavailable")
                for _ in selected_results
            ]
    else:
        return None
    if len(order1_results) != len(order2_results) or len(order2_results) != len(selected_results):
        return [
            _taylor_order_comparison_unavailable_payload(reason="result_count_mismatch")
            for _ in selected_results
        ]
    return [
        _taylor_order_comparison_payload(
            order1_result=order1_result,
            order2_result=order2_result,
            precision_digits=precision_digits,
        )
        for order1_result, order2_result in zip(order1_results, order2_results, strict=True)
    ]


def _taylor_order_comparison_unavailable_payload(*, reason: str) -> dict[str, object]:
    return {
        "method": TAYLOR_ORDER_COMPARISON_METHOD,
        "order_low": 1,
        "order_high": 2,
        "comparison_unavailable_reason": reason,
    }


def _taylor_order_comparison_payload(
    *,
    order1_result: UncertainValue,
    order2_result: UncertainValue,
    precision_digits: int,
) -> dict[str, object]:
    with precision_guard(precision_digits):
        order1_mean = mp.mpf(order1_result.value)
        order1_std = mp.fabs(mp.mpf(order1_result.uncertainty))
        order2_mean = mp.mpf(order2_result.value)
        order2_std = mp.fabs(mp.mpf(order2_result.uncertainty))
        absolute_mean_difference = mp.fabs(order2_mean - order1_mean)
        relative_std_difference: mp.mpf | None
        relative_std_difference_omission_reason: str | None
        if not mp.isfinite(order1_std) or not mp.isfinite(order2_std):
            relative_std_difference = None
            relative_std_difference_omission_reason = "nonfinite_std"
        elif order1_std == 0 and order2_std == 0:
            relative_std_difference = None
            relative_std_difference_omission_reason = "zero_std"
        else:
            relative_std_difference = mp.fabs(order2_std - order1_std) / max(order1_std, order2_std)
            relative_std_difference_omission_reason = None
    return {
        "method": TAYLOR_ORDER_COMPARISON_METHOD,
        "order_low": 1,
        "order_high": 2,
        "order1_mean": _format_comparison_mpf(order1_mean, precision_digits=precision_digits),
        "order1_std": _format_comparison_mpf(order1_std, precision_digits=precision_digits),
        "order2_mean": _format_comparison_mpf(order2_mean, precision_digits=precision_digits),
        "order2_std": _format_comparison_mpf(order2_std, precision_digits=precision_digits),
        "absolute_mean_difference": _format_comparison_mpf(
            absolute_mean_difference,
            precision_digits=precision_digits,
        ),
        "relative_std_difference": (
            None
            if relative_std_difference is None
            else _format_comparison_mpf(relative_std_difference, precision_digits=precision_digits)
        ),
        "relative_std_difference_omission_reason": relative_std_difference_omission_reason,
    }


def _taylor_monte_carlo_comparison_payloads(
    *,
    headers: list[str],
    parsed_data: list[list[UncertainValue]],
    constants: dict[str, UncertainValue],
    formula: str,
    monte_carlo_results: Sequence[UncertainValue],
    propagation_config: UncertaintyPropagationConfig,
    precision_digits: int,
) -> list[dict[str, object]] | None:
    if propagation_config["method"] != "monte_carlo":
        return None
    sample_count = propagation_config["mc_samples"] or DEFAULT_MONTE_CARLO_SAMPLE_COUNT
    try:
        taylor_results = apply_formula_to_data(
            headers,
            parsed_data,
            constants,
            formula,
            False,
            warnings=None,
            return_components=True,
            propagation_method="taylor",
            propagation_order=propagation_config["order"],
            mc_samples=None,
            mc_seed=None,
            cancellation_checker=check_cancelled,
        )
    except ValueError:
        return [
            _taylor_monte_carlo_unavailable_payload(
                sample_count=sample_count,
                taylor_order=propagation_config["order"],
                reason="taylor_unavailable",
            )
            for _ in monte_carlo_results
        ]
    if len(taylor_results) != len(monte_carlo_results):
        return [
            _taylor_monte_carlo_unavailable_payload(
                sample_count=sample_count,
                taylor_order=propagation_config["order"],
                reason="result_count_mismatch",
            )
            for _ in monte_carlo_results
        ]
    return [
        _taylor_monte_carlo_comparison_payload(
            monte_carlo_result=monte_carlo_result,
            taylor_result=taylor_result,
            sample_count=sample_count,
            taylor_order=propagation_config["order"],
            precision_digits=precision_digits,
        )
        for monte_carlo_result, taylor_result in zip(monte_carlo_results, taylor_results, strict=True)
    ]


def _taylor_monte_carlo_unavailable_payload(
    *,
    sample_count: int,
    taylor_order: int,
    reason: str,
) -> dict[str, object]:
    return {
        "method": "taylor_vs_monte_carlo",
        "absolute_result_tolerance": COMPARISON_ABSOLUTE_RESULT_TOLERANCE,
        "relative_result_tolerance": COMPARISON_RELATIVE_RESULT_TOLERANCE,
        "sample_count": int(sample_count),
        "taylor_order": int(taylor_order),
        "comparison_unavailable_reason": reason,
    }


def _taylor_monte_carlo_comparison_payload(
    *,
    monte_carlo_result: UncertainValue,
    taylor_result: UncertainValue,
    sample_count: int,
    taylor_order: int,
    precision_digits: int,
) -> dict[str, object]:
    with precision_guard(precision_digits):
        absolute_tolerance = mp.mpf(COMPARISON_ABSOLUTE_RESULT_TOLERANCE)
        relative_tolerance = mp.mpf(COMPARISON_RELATIVE_RESULT_TOLERANCE)
        taylor_mean = mp.mpf(taylor_result.value)
        taylor_std = mp.fabs(mp.mpf(taylor_result.uncertainty))
        monte_carlo_mean = mp.mpf(monte_carlo_result.value)
        monte_carlo_std = mp.fabs(mp.mpf(monte_carlo_result.uncertainty))
        monte_carlo_standard_error = monte_carlo_std / mp.sqrt(sample_count)
        practical_floor = max(
            absolute_tolerance,
            relative_tolerance * max(mp.fabs(taylor_mean), mp.fabs(monte_carlo_mean)),
        )
        absolute_mean_difference = mp.fabs(monte_carlo_mean - taylor_mean)
        mean_disagreement_threshold = max(3 * monte_carlo_standard_error, practical_floor)
        mean_disagreement: bool | None
        mean_disagreement_omission_reason: str | None
        if not mp.isfinite(absolute_mean_difference) or not mp.isfinite(mean_disagreement_threshold):
            mean_disagreement = None
            mean_disagreement_omission_reason = "nonfinite_mean"
        else:
            mean_disagreement = bool(absolute_mean_difference > mean_disagreement_threshold)
            mean_disagreement_omission_reason = None
        relative_std_difference: mp.mpf | None
        relative_std_difference_omission_reason: str | None
        if not mp.isfinite(taylor_std) or not mp.isfinite(monte_carlo_std):
            relative_std_difference = None
            relative_std_difference_omission_reason = "nonfinite_std"
        elif taylor_std == 0 and monte_carlo_std == 0:
            relative_std_difference = None
            relative_std_difference_omission_reason = "zero_std"
        else:
            relative_std_difference = mp.fabs(monte_carlo_std - taylor_std) / max(taylor_std, monte_carlo_std)
            relative_std_difference_omission_reason = None
    return {
        "method": "taylor_vs_monte_carlo",
        "absolute_result_tolerance": COMPARISON_ABSOLUTE_RESULT_TOLERANCE,
        "relative_result_tolerance": COMPARISON_RELATIVE_RESULT_TOLERANCE,
        "sample_count": int(sample_count),
        "taylor_order": int(taylor_order),
        "taylor_mean": _format_comparison_mpf(taylor_mean, precision_digits=precision_digits),
        "taylor_std": _format_comparison_mpf(taylor_std, precision_digits=precision_digits),
        "monte_carlo_mean": _format_comparison_mpf(monte_carlo_mean, precision_digits=precision_digits),
        "monte_carlo_std": _format_comparison_mpf(monte_carlo_std, precision_digits=precision_digits),
        "monte_carlo_standard_error": _format_comparison_mpf(
            monte_carlo_standard_error,
            precision_digits=precision_digits,
        ),
        "practical_floor": _format_comparison_mpf(practical_floor, precision_digits=precision_digits),
        "absolute_mean_difference": _format_comparison_mpf(
            absolute_mean_difference,
            precision_digits=precision_digits,
        ),
        "mean_disagreement_threshold": _format_comparison_mpf(
            mean_disagreement_threshold,
            precision_digits=precision_digits,
        ),
        "mean_disagreement": mean_disagreement,
        "mean_disagreement_omission_reason": mean_disagreement_omission_reason,
        "relative_std_difference": (
            None
            if relative_std_difference is None
            else _format_comparison_mpf(relative_std_difference, precision_digits=precision_digits)
        ),
        "relative_std_difference_omission_reason": relative_std_difference_omission_reason,
    }


def _format_comparison_mpf(value: mp.mpf, *, precision_digits: int) -> str:
    if value == mp.mpf(COMPARISON_ABSOLUTE_RESULT_TOLERANCE):
        return COMPARISON_ABSOLUTE_RESULT_TOLERANCE
    if value == mp.mpf(COMPARISON_RELATIVE_RESULT_TOLERANCE):
        return COMPARISON_RELATIVE_RESULT_TOLERANCE
    return _format_mpf(value, precision_digits)


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _normalize_uncertainty_rows(
    rows: Sequence[Sequence[Any]],
    *,
    uncertainty_rows: Sequence[Sequence[Any | None]] | None,
    headers: Sequence[str],
    digit_hint: int,
) -> tuple[list[list[str]], list[list[str]]]:
    if isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("rows must be a sequence of row sequences.")
    if not rows:
        raise ValueError("rows must contain at least one row.")
    if uncertainty_rows is not None and len(uncertainty_rows) != len(rows):
        raise ValueError("uncertainty_rows must have the same length as rows.")

    values: list[list[str]] = []
    uncertainties: list[list[str]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"Row {row_index + 1} must be a sequence of values.")
        if len(row) < len(headers):
            missing_header = headers[len(row)]
            raise ValueError(f"Row {row_index + 1} is missing column {missing_header}.")
        uncertainty_row = None if uncertainty_rows is None else uncertainty_rows[row_index]
        row_values: list[str] = []
        row_uncertainties: list[str] = []
        for column_index, header in enumerate(headers):
            cell_value, embedded_uncertainty = _split_uncertain_value(row[column_index])
            row_values.append(
                numeric_to_payload_string(
                    cell_value,
                    field_name=f"rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
            )
            explicit_uncertainty = None
            if uncertainty_row is not None and column_index < len(uncertainty_row):
                explicit_uncertainty = uncertainty_row[column_index]
            uncertainty_value = embedded_uncertainty if explicit_uncertainty is None else explicit_uncertainty
            row_uncertainties.append(
                _uncertainty_payload_or_zero(
                    uncertainty_value,
                    field_name=f"uncertainty_rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
            )
        values.append(row_values)
        uncertainties.append(row_uncertainties)
    return values, uncertainties


def _normalize_constants(constants: Mapping[str, Any], *, digit_hint: int) -> dict[str, dict[str, str]]:
    if not isinstance(constants, Mapping):
        raise TypeError("constants must be a mapping.")
    normalized: dict[str, dict[str, str]] = {}
    for raw_name, raw_value in constants.items():
        if not isinstance(raw_name, str):
            raise TypeError("constant names must be strings.")
        name = raw_name.strip()
        if not name:
            raise ValueError("constant names must not be empty.")
        value, uncertainty = _split_constant_value(raw_value)
        normalized[name] = {
            "value": numeric_to_payload_string(
                value,
                field_name=f"constants.{name}.value",
                digit_hint=digit_hint,
            ),
            "uncertainty": _uncertainty_payload_or_zero(
                uncertainty,
                field_name=f"constants.{name}.uncertainty",
                digit_hint=digit_hint,
            ),
        }
    return normalized


def _split_uncertain_value(value: Any) -> tuple[Any, Any | None]:
    if hasattr(value, "value") and hasattr(value, "uncertainty"):
        return getattr(value, "value"), getattr(value, "uncertainty")
    return value, None


def _split_constant_value(value: Any) -> tuple[Any, Any | None]:
    if hasattr(value, "value") and hasattr(value, "uncertainty"):
        return getattr(value, "value"), getattr(value, "uncertainty")
    if isinstance(value, Mapping):
        if "value" not in value:
            raise ValueError("constant mappings must include a value field.")
        return value.get("value"), value.get("uncertainty")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        if len(value) != 2:
            raise ValueError("constant tuple values must contain value and uncertainty.")
        return value[0], value[1]
    return value, None


def _uncertainty_payload_or_zero(value: Any | None, *, field_name: str, digit_hint: int) -> str:
    text = optional_numeric_to_payload_string(
        value,
        field_name=field_name,
        digit_hint=digit_hint,
        absolute=True,
    )
    return "0" if text is None else text


def _normalize_formula(formula: str) -> str:
    if not isinstance(formula, str):
        raise TypeError("formula must be a string.")
    normalized = formula.strip()
    if not normalized:
        raise ValueError("formula must not be empty.")
    return normalized


def _normalize_method(method: str) -> str:
    if not isinstance(method, str):
        raise TypeError("propagation.method must be a string.")
    normalized = method.strip().lower() or "taylor"
    if normalized in {"mc", "montecarlo", "monte_carlo", "monte-carlo"}:
        return "monte_carlo"
    return "taylor"


def _normalize_propagation_order(value: int) -> int:
    return max(1, _validate_int(value, field_name="propagation.order"))


def _validate_int(value: int, *, field_name: str) -> int:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass integer options as integers.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    return value


def _validate_optional_int(value: int | None, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _validate_int(value, field_name=field_name)
