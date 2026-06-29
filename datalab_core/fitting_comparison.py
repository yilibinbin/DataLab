from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import mpmath as mp

from fitting.auto_models import build_inverse_series_definition, build_polynomial_definition
from fitting.comparison_formatting import (
    COMPARISON_TABLE_HEADERS,
    build_comparison_table_rows_from_payload,
)
from fitting.model_comparison import (
    FitComparisonCandidate,
    FitComparisonEntry,
    FitComparisonResult,
    FitComparisonRow,
    compare_selected_fits,
)
from fitting.problem import ModelProblem
from shared.fitting_engine import deserialize_fit_result, serialize_fit_result
from shared.precision import precision_guard

from ._payload import normalize_json_payload
from .fitting import DEFAULT_FITTING_PRECISION_DIGITS, build_fitting_request
from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import numeric_payload_tree, request_digit_hint
from .results import ResultEnvelope, ResultKind, ResultStatus

_SUPPORTED_MODEL_TYPES = {"polynomial", "inverse_power", "custom"}
_EXPECTED_CANDIDATE_FAILURES = (ValueError, TypeError, ArithmeticError)
FITTING_COMPARISON_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.fitting_comparison"
FITTING_COMPARISON_RESULT_SNAPSHOT_SCHEMA_VERSION = 1


def build_fitting_comparison_request(
    *,
    headers: Sequence[str],
    data_rows: Sequence[Sequence[Any]],
    variable_map: Mapping[str, str],
    target_column: str,
    candidates: Sequence[Mapping[str, Any]],
    sigma_rows: Sequence[Sequence[Any | None]] | None = None,
    sigma_series: Sequence[Any | None] | None = None,
    weighted: bool = False,
    weights: Sequence[Any | None] | None = None,
    precision_digits: int | None = None,
    uncertainty_digits: int | None = None,
    parallel: Mapping[str, Any] | None = None,
    request_id: str = "fitting-comparison",
) -> ComputeJobRequest:
    candidate_payloads = _candidate_payload_sequence(
        candidates,
        precision_digits=precision_digits,
    )
    if not candidate_payloads:
        raise ValueError("comparison candidates must contain at least one candidate.")
    base_request = build_fitting_request(
        model_type="polynomial",
        headers=headers,
        data_rows=data_rows,
        variable_map=variable_map,
        target_column=target_column,
        model_expr="",
        sigma_rows=sigma_rows,
        sigma_series=sigma_series,
        parameter_config={},
        parameter_names=(),
        poly_degree=1,
        inverse_min=1,
        inverse_max=3,
        pade_m=1,
        pade_n=1,
        weighted=weighted,
        label="",
        custom_constants={},
        weights=weights,
        precision_digits=precision_digits,
        uncertainty_digits=uncertainty_digits,
        parallel=parallel,
        request_id=request_id,
    )
    inputs = dict(base_request.inputs)
    inputs["comparison"] = True
    inputs["comparison_candidates"] = candidate_payloads
    return ComputeJobRequest(
        mode=JobMode.FITTING,
        inputs=inputs,
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
            parallel=parallel or {},
        ),
        request_id=request_id,
    )


def run_fitting_comparison(request: ComputeJobRequest) -> ResultEnvelope:
    if request.mode is not JobMode.FITTING:
        raise ValueError(f"Unsupported fitting comparison request mode: {request.mode.value}.")
    if request.inputs.get("comparison") is not True:
        raise ValueError("fitting comparison request must set inputs.comparison to true.")
    precision = (
        DEFAULT_FITTING_PRECISION_DIGITS
        if request.options.precision_digits is None
        else request.options.precision_digits
    )
    candidates_payload = _required_candidate_sequence(
        request.inputs.get("comparison_candidates", ())
    )
    variable_data = _mapping_or_empty(request.inputs.get("variable_data"))
    variable_names = tuple(str(name) for name in variable_data) or ("x",)
    # mp.dps is process-global; serialization below re-rounds high-precision mpf values
    # to the active dps. Guard the whole compute+serialize span so results keep the
    # requested precision regardless of the ambient dps left by a prior job (desktop
    # workers run on shared QThreads). The web path already wraps this call in its own
    # guard; nested precision_guard is safe (it save/restores).
    with precision_guard(precision):
        result = _compare_candidate_payloads(
            candidates_payload,
            variable_names=variable_names,
            x_data=_mp_sequence(request.inputs.get("x_series"), field_name="x_series"),
            y_data=_mp_sequence(request.inputs.get("y_series"), field_name="y_series"),
            precision=precision,
            weights=_optional_mpf_sequence(request.inputs.get("weights"), field_name="weights"),
            data_sigmas=_optional_mpf_or_none_sequence(
                request.inputs.get("sigma_series"),
                field_name="sigma_series",
            ),
            variable_data={
                str(name): _mp_sequence(values, field_name=f"variable_data.{name}")
                for name, values in variable_data.items()
            },
        )
        keep_digits = max(int(precision) + 10, 30)
        payload = serialize_fitting_comparison_result(result, keep_digits=keep_digits)
    payload["comparison"] = True
    payload["precision_used"] = int(precision)
    payload["candidate_count"] = len(candidates_payload)
    warnings = tuple(
        warning
        for row in result.rows
        for warning in row.warnings
    )
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=warnings,
    )


def _compare_candidate_payloads(
    candidates_payload: Sequence[Mapping[str, Any]],
    *,
    variable_names: Sequence[str],
    x_data: Sequence[mp.mpf],
    y_data: Sequence[mp.mpf],
    precision: int,
    weights: list[mp.mpf] | None,
    data_sigmas: list[mp.mpf | None] | None,
    variable_data: Mapping[str, Sequence[mp.mpf]],
) -> FitComparisonResult:
    entries: list[FitComparisonEntry] = []
    rows: list[FitComparisonRow] = []
    for order, payload in enumerate(candidates_payload, start=1):
        try:
            normalized_payload = _normalize_candidate_payload(
                payload,
                precision_digits=precision,
            )
            candidate = _candidate_from_payload(normalized_payload, variable_names=variable_names)
        except _EXPECTED_CANDIDATE_FAILURES as exc:
            candidate_id = _candidate_id_or_fallback(payload, order)
            label = str(payload.get("label") or payload.get("model_type") or candidate_id)
            free_parameter_count = _safe_payload_free_parameter_count(payload)
            candidate = FitComparisonCandidate(
                candidate_id=candidate_id,
                label=label,
                kind="linear",
                free_parameter_count=free_parameter_count,
            )
            entries.append(
                FitComparisonEntry(
                    candidate_id=candidate_id,
                    order=order,
                    label=label,
                    candidate=candidate,
                    fit_result=None,
                    error=str(exc),
                )
            )
            rows.append(
                FitComparisonRow(
                    candidate_id=candidate_id,
                    order=order,
                    model_label=label,
                    status="failed",
                    free_parameter_count=free_parameter_count,
                    chi2=None,
                    reduced_chi2=None,
                    aic=None,
                    bic=None,
                    rmse=None,
                    r2=None,
                    warnings=(),
                    error=str(exc),
                )
            )
            continue
        single = compare_selected_fits(
            [candidate],
            x_data=x_data,
            y_data=y_data,
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
            variable_data=variable_data,
        )
        entries.append(replace(single.entries[0], order=order))
        rows.append(replace(single.rows[0], order=order))
    return FitComparisonResult(entries=entries, rows=rows)


def serialize_fitting_comparison_result(
    result: FitComparisonResult,
    *,
    keep_digits: int,
) -> dict[str, Any]:
    return {
        "rows": [_serialize_row(row, keep_digits=keep_digits) for row in result.rows],
        "entries": [_serialize_entry(entry, keep_digits=keep_digits) for entry in result.entries],
    }


def fitting_comparison_payload_to_fit_results(payload: Mapping[str, Any]) -> dict[str, Any]:
    entries = payload.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray, memoryview)):
        raise ValueError("payload.entries must be a sequence.")
    results: dict[str, Any] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"payload.entries[{index}] must be a mapping.")
        fit_payload = entry.get("fit_result")
        if fit_payload is None:
            continue
        if not isinstance(fit_payload, Mapping):
            raise ValueError(f"payload.entries[{index}].fit_result must be a mapping or null.")
        results[str(entry.get("candidate_id") or index)] = deserialize_fit_result(fit_payload)
    return results


def build_fitting_comparison_result_snapshot(
    kind: str,
    payload: Mapping[str, Any],
    *,
    overview_state: str = "none",
    plot_metadata: Sequence[Mapping[str, Any]] = (),
    precision: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a semantic result snapshot for selected-fit comparison payloads."""

    if kind != "fitting_comparison" or payload.get("comparison") is not True:
        return None
    try:
        comparison_rows = build_comparison_table_rows_from_payload(payload)
    except ValueError:
        return None
    if not comparison_rows:
        return None

    entries = _snapshot_comparison_entries(payload.get("entries"))
    successful_count = sum(1 for row in comparison_rows if str(row.get("status")) == "success")
    failed_count = sum(1 for row in comparison_rows if str(row.get("status")) == "failed")
    candidate_ids = [str(row.get("candidate_id") or "") for row in comparison_rows]
    plots = [_snapshot_plain_mapping(plot) for plot in plot_metadata]
    snapshot: dict[str, object] = {
        "schema": FITTING_COMPARISON_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": FITTING_COMPARISON_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "fitting_comparison",
        "mode": "selected",
        "comparison_rows": comparison_rows,
        "entries": entries,
        "warnings": _snapshot_comparison_warnings(comparison_rows),
        "plot_spec_keys": ["fitting.comparison.overlay"] if plots else [],
        "plot_metadata": {
            "image_mode": "fitting_comparison",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": {
            "candidate_count": len(comparison_rows),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "candidate_ids": candidate_ids,
        },
        "precision": _snapshot_plain_mapping(precision or {}),
        "compatibility": {
            "result_cache_kind": kind,
            "overview_state": _snapshot_clean_text(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_fitting_comparison_ui_adapter",
        },
    }
    try:
        normalized = normalize_json_payload(snapshot, path="fitting_comparison_result_snapshot")
    except (TypeError, ValueError):
        return None
    if not isinstance(normalized, Mapping):
        return None
    return {str(key): value for key, value in deepcopy(normalized).items()}


def render_fitting_comparison_snapshot_outputs(
    snapshot: Mapping[str, Any],
) -> tuple[str, list[dict[str, object]], list[str]] | None:
    """Regenerate deterministic text and CSV from a fitting-comparison snapshot."""

    if snapshot.get("family") != "fitting_comparison":
        return None
    rows = _snapshot_comparison_rows(snapshot.get("comparison_rows"))
    if not rows:
        return None

    lines = [
        "=== Selected Fit Comparison ===",
        "",
        "Model | Status | Params | χ² | Reduced χ² | AIC | BIC | RMSE | R² | Warnings | Error",
        "--- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---",
    ]
    for row in rows:
        lines.append(
            " | ".join(
                (
                    _snapshot_cell(row.get("model_label")),
                    _snapshot_cell(row.get("status")),
                    _snapshot_cell(row.get("free_parameters")),
                    _snapshot_cell(row.get("chi2")),
                    _snapshot_cell(row.get("reduced_chi2")),
                    _snapshot_cell(row.get("aic")),
                    _snapshot_cell(row.get("bic")),
                    _snapshot_cell(row.get("rmse")),
                    _snapshot_cell(row.get("r2")),
                    _snapshot_cell(row.get("warnings")),
                    _snapshot_cell(row.get("error")),
                )
            )
        )
    csv_rows = [{header: row.get(header, "") for header in COMPARISON_TABLE_HEADERS} for row in rows]
    return "\n".join(lines), csv_rows, list(COMPARISON_TABLE_HEADERS)


def _normalize_candidate_payload(
    candidate: Mapping[str, Any],
    *,
    precision_digits: int | None,
) -> dict[str, Any]:
    digit_hint = request_digit_hint(precision_digits)
    model_type = _candidate_model_type(candidate)
    _require_supported_model_type(model_type)
    parameter_config = _mapping_or_empty(
        numeric_payload_tree(
            _mapping_or_empty(candidate.get("parameter_config")),
            field_name="parameter_config",
            digit_hint=digit_hint,
        )
    )
    custom_constants = _mapping_or_empty(
        numeric_payload_tree(
            _mapping_or_empty(candidate.get("custom_constants")),
            field_name="custom_constants",
            digit_hint=digit_hint,
        )
    )
    return {
        "candidate_id": _candidate_id(candidate),
        "label": str(candidate.get("label") or model_type),
        "model_type": model_type,
        "model_expr": str(candidate.get("model_expr") or ""),
        "parameter_config": parameter_config,
        "parameter_names": _string_sequence(candidate.get("parameter_names")),
        "poly_degree": _int_value(candidate.get("poly_degree"), default=1),
        "inverse_min": _int_value(candidate.get("inverse_min"), default=1),
        "inverse_max": _int_value(candidate.get("inverse_max"), default=3),
        "pade_m": _int_value(candidate.get("pade_m"), default=1),
        "pade_n": _int_value(candidate.get("pade_n"), default=1),
        "custom_constants": custom_constants,
        **(
            {"free_parameter_count": _non_negative_int(candidate["free_parameter_count"])}
            if "free_parameter_count" in candidate
            else {}
        ),
    }


def _candidate_from_payload(
    payload: Mapping[str, Any],
    *,
    variable_names: Sequence[str],
) -> FitComparisonCandidate:
    model_type = _candidate_model_type(payload)
    candidate_id = _candidate_id(payload)
    label = str(payload.get("label") or model_type)
    free_parameter_count = (
        _non_negative_int(payload["free_parameter_count"])
        if "free_parameter_count" in payload
        else None
    )
    if model_type == "polynomial":
        return FitComparisonCandidate.linear(
            candidate_id=candidate_id,
            label=label,
            definition=build_polynomial_definition(_int_value(payload.get("poly_degree"), default=1)),
            free_parameter_count=free_parameter_count,
        )
    if model_type == "inverse_power":
        return FitComparisonCandidate.linear(
            candidate_id=candidate_id,
            label=label,
            definition=build_inverse_series_definition(
                _int_value(payload.get("inverse_min"), default=1),
                _int_value(payload.get("inverse_max"), default=3),
            ),
            free_parameter_count=free_parameter_count,
        )
    if model_type == "custom":
        problem = ModelProblem(
            model_type="custom",
            expression=str(payload.get("model_expr") or ""),
            variables=tuple(variable_names),
            parameter_config=_mapping_or_empty(payload.get("parameter_config")),
            constants=_mapping_or_empty(payload.get("custom_constants")),
            constants_enabled=True,
        )
        return FitComparisonCandidate.runner(
            candidate_id=candidate_id,
            label=label,
            problem=problem,
            free_parameter_count=free_parameter_count,
        )
    raise ValueError(f"Unsupported fitting comparison model_type: {model_type}.")


def _serialize_entry(entry: Any, *, keep_digits: int) -> dict[str, Any]:
    return {
        "candidate_id": entry.candidate_id,
        "order": entry.order,
        "label": entry.label,
        "status": "success" if entry.success else "failed",
        "fit_result": (
            serialize_fit_result(entry.fit_result, keep_digits)
            if entry.fit_result is not None
            else None
        ),
        "error": entry.error,
    }


def _serialize_row(row: Any, *, keep_digits: int) -> dict[str, Any]:
    return {
        "candidate_id": row.candidate_id,
        "order": row.order,
        "model_label": row.model_label,
        "status": row.status,
        "free_parameter_count": row.free_parameter_count,
        "chi2": _mp_or_none(row.chi2, keep_digits),
        "reduced_chi2": _mp_or_none(row.reduced_chi2, keep_digits),
        "aic": _mp_or_none(row.aic, keep_digits),
        "bic": _mp_or_none(row.bic, keep_digits),
        "rmse": _mp_or_none(row.rmse, keep_digits),
        "r2": _mp_or_none(row.r2, keep_digits),
        "warnings": list(row.warnings),
        "error": row.error,
    }


def _mp_or_none(value: Any, keep_digits: int) -> str | None:
    if value is None:
        return None
    return str(mp.nstr(mp.mpf(value), n=max(1, int(keep_digits))))


def _required_candidate_sequence(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError("comparison candidates must be a sequence of mappings.")
    candidates: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(f"comparison candidates[{index}] must be a mapping.")
        candidates.append(item)
    return candidates


def _candidate_payload_sequence(
    value: Any,
    *,
    precision_digits: int | None,
) -> list[dict[str, Any]]:
    digit_hint = request_digit_hint(precision_digits)
    return [
        _candidate_payload_tree(candidate, index=index, digit_hint=digit_hint)
        for index, candidate in enumerate(_required_candidate_sequence(value))
    ]


def _candidate_payload_tree(
    candidate: Mapping[str, Any],
    *,
    index: int,
    digit_hint: int,
) -> dict[str, Any]:
    payload = _json_safe_candidate_tree(
        dict(candidate),
        field_name=f"comparison_candidates[{index}]",
        digit_hint=digit_hint,
    )
    if not isinstance(payload, Mapping):
        raise TypeError(f"comparison candidates[{index}] must normalize to a mapping.")
    result = {
        "candidate_id": "",
        "label": "",
        "model_type": "polynomial",
        "model_expr": "",
        "parameter_config": {},
        "parameter_names": [],
        "poly_degree": 1,
        "inverse_min": 1,
        "inverse_max": 3,
        "pade_m": 1,
        "pade_n": 1,
        "custom_constants": {},
    }
    result.update(dict(payload))
    if not result.get("label"):
        result["label"] = str(result.get("model_type") or "")
    return result


def _json_safe_candidate_tree(value: Any, *, field_name: str, digit_hint: int) -> Any:
    if isinstance(value, mp.mpf):
        return str(mp.nstr(value, n=max(1, int(digit_hint))))
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe_candidate_tree(
                item,
                field_name=f"{field_name}.{key}",
                digit_hint=digit_hint,
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [
            _json_safe_candidate_tree(
                item,
                field_name=f"{field_name}[{index}]",
                digit_hint=digit_hint,
            )
            for index, item in enumerate(value)
        ]
    return value


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    value = str(candidate.get("candidate_id") or candidate.get("id") or "").strip()
    if not value:
        raise ValueError("comparison candidate requires a non-empty candidate_id.")
    return value


def _candidate_id_or_fallback(candidate: Mapping[str, Any], order: int) -> str:
    try:
        return _candidate_id(candidate)
    except ValueError:
        return f"candidate-{order}"


def _candidate_model_type(candidate: Mapping[str, Any]) -> str:
    model_type = str(candidate.get("model_type") or "polynomial").strip()
    if not model_type:
        raise ValueError("comparison candidate model_type must not be empty.")
    return model_type


def _require_supported_model_type(model_type: str) -> None:
    if model_type not in _SUPPORTED_MODEL_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_MODEL_TYPES))
        raise ValueError(f"Unsupported fitting comparison model_type {model_type!r}; supported: {supported}.")


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError("expected a mapping.")
    return {str(key): item for key, item in value.items()}


def _string_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError("expected a sequence of strings.")
    return [str(item) for item in value if str(item)]


def _mp_sequence(value: Any, *, field_name: str) -> list[mp.mpf]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    return [mp.mpf(item) for item in value]


def _optional_mpf_sequence(value: Any, *, field_name: str) -> list[mp.mpf] | None:
    if value is None:
        return None
    return _mp_sequence(value, field_name=field_name)


def _optional_mpf_or_none_sequence(value: Any, *, field_name: str) -> list[mp.mpf | None] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence.")
    return [None if item is None else mp.mpf(item) for item in value]


def _int_value(value: Any, *, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("free_parameter_count must be non-negative.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("free_parameter_count must be non-negative.")
    result = _int_value(value, default=0)
    if result < 0:
        raise ValueError("free_parameter_count must be non-negative.")
    return result


def _payload_free_parameter_count(payload: Mapping[str, Any]) -> int:
    if "free_parameter_count" in payload:
        return _non_negative_int(payload["free_parameter_count"])
    parameter_names = _string_sequence(payload.get("parameter_names"))
    return len(parameter_names)


def _safe_payload_free_parameter_count(payload: Mapping[str, Any]) -> int:
    try:
        return _payload_free_parameter_count(payload)
    except _EXPECTED_CANDIDATE_FAILURES:
        return 0


def _snapshot_comparison_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        return []
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                header: _snapshot_cell(row.get(header))
                if header not in {"order", "free_parameters"}
                else row.get(header, index + 1 if header == "order" else "")
                for header in COMPARISON_TABLE_HEADERS
            }
        )
    return rows


def _snapshot_comparison_entries(value: Any) -> list[dict[str, object]]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        return []
    entries: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        entries.append(_snapshot_plain_mapping(item))
    return entries


def _snapshot_comparison_warnings(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = _snapshot_clean_text(row.get("warnings"))
        if not text or text in seen:
            continue
        warnings.append(text)
        seen.add(text)
    return warnings


def _snapshot_plain_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, float):
            continue
        if isinstance(item, Mapping):
            payload[key] = _snapshot_plain_mapping(item)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray, memoryview)):
            payload[key] = [
                _snapshot_plain_mapping(element) if isinstance(element, Mapping) else element
                for element in item
                if not isinstance(element, float)
            ]
        elif isinstance(item, (str, int, bool)) or item is None:
            payload[key] = item
    return payload


def _snapshot_clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _snapshot_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
