from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping, Sequence
from typing import Any

from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult

from ._payload import normalize_json_payload
from .jobs import ComputeJobRequest, JobMode, JobOptions
from .numeric_payload import numeric_to_payload_string, request_digit_hint
from .parallel_options import normalize_parallel_options
from .results import (
    AnalysisRow,
    ResultEnvelope,
    ResultKind,
    ResultStatus,
    analysis_rows_from_json,
    analysis_rows_to_json,
)
from .session import check_cancelled
from .table_payload import normalize_headers
from shared.precision import precision_guard
from shared.root_solving_engine import (
    deserialize_root_batch_result,
    execute_root_batch_from_payload,
    serialize_root_batch_result,
)
from shared.unit_annotations import (
    canonical_unit_symbol_map,
    normalize_display_only_family_units,
    unit_annotations_for_labels,
)


_ROOT_MODES = {"auto", "scalar", "polynomial", "system", "scan_multiple"}
_UNKNOWN_SOURCES = {"manual", "detected"}
_ROOT_CLASSIFICATION_TAGS = (
    "complex",
    "bracketed_sign_change",
    "suspected_tangent_or_repeated",
    "boundary",
    "unclassified",
)
ROOT_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.root_solving"
ROOT_RESULT_SNAPSHOT_SCHEMA_VERSION = 1


def build_root_solving_request(
    *,
    equations: Sequence[str],
    unknown_rows: Sequence[Mapping[str, Any]],
    data_headers: Sequence[str] = (),
    data_rows: Sequence[Sequence[Any]] = (),
    constants_enabled: bool = False,
    constants_rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None = (),
    constants_view: str = "table",
    constants_text: str = "",
    mode: str = "auto",
    scan_config: Mapping[str, Any] | None = None,
    uncertainty_options: Mapping[str, Any] | None = None,
    precision_digits: int | None = None,
    display_digits: int = 10,
    uncertainty_digits: int | None = None,
    units: Mapping[str, Any] | None = None,
    parallel: Mapping[str, Any] | None = None,
    request_id: str = "root-solving",
) -> ComputeJobRequest:
    """Build a string-preserving root-solving request.

    This is only the Phase 2 request boundary. The existing root solver,
    normalization, plotting, LaTeX, and subprocess execution paths remain
    outside ``datalab_core`` until their service adapter is migrated.
    """

    digit_hint = request_digit_hint(precision_digits)
    normalized_equations = _normalize_equations(equations)
    normalized_unknown_rows = _normalize_unknown_rows(unknown_rows, digit_hint=digit_hint)
    normalized_data_headers = _normalize_optional_headers(data_headers)
    normalized_data_rows = _normalize_data_rows(data_rows, headers=normalized_data_headers, digit_hint=digit_hint)
    normalized_constants_rows = _normalize_constants_rows(constants_rows, digit_hint=digit_hint)
    inputs: dict[str, object] = {
        "equations": normalized_equations,
        "unknown_rows": normalized_unknown_rows,
        "data_headers": normalized_data_headers,
        "data_rows": normalized_data_rows,
        "constants_enabled": _validate_bool(constants_enabled, field_name="constants_enabled"),
        "constants_rows": normalized_constants_rows,
        "constants_view": _string_value(constants_view, field_name="constants_view").strip() or "table",
        "constants_text": str(constants_text or ""),
        "mode": _normalize_mode(mode),
        "scan_config": _normalize_option_mapping(
            scan_config or {},
            field_name="scan_config",
            digit_hint=digit_hint,
        ),
        "uncertainty_options": _normalize_option_mapping(
            uncertainty_options or {},
            field_name="uncertainty_options",
            digit_hint=digit_hint,
        ),
        "display_digits": _validate_int(display_digits, field_name="display_digits"),
    }
    units_config = _normalize_root_units_config(
        units,
        data_headers=normalized_data_headers,
        unknown_rows=normalized_unknown_rows,
        constants_rows=normalized_constants_rows,
    )
    if units_config is not None:
        inputs["units"] = units_config
    return ComputeJobRequest(
        mode=JobMode.ROOT_SOLVING,
        inputs=inputs,
        options=JobOptions(
            precision_digits=precision_digits,
            uncertainty_digits=uncertainty_digits,
            parallel=normalize_parallel_options(parallel or {}, digit_hint=digit_hint),
        ),
        request_id=request_id,
    )


def run_root_solving(request: ComputeJobRequest) -> ResultEnvelope:
    """Run root-solving batch computation through the UI-neutral core service."""

    check_cancelled()
    if request.mode is not JobMode.ROOT_SOLVING:
        raise ValueError(f"Unsupported root-solving request mode: {request.mode.value}.")
    precision_digits = 16 if request.options.precision_digits is None else request.options.precision_digits
    with precision_guard(precision_digits) as precision_used:
        check_cancelled()
        equations = _required_string_sequence(request.inputs.get("equations"), field_name="equations")
        unknown_rows = _required_mapping_sequence(request.inputs.get("unknown_rows"), field_name="unknown_rows")
        data_headers = _optional_string_sequence(request.inputs.get("data_headers"), field_name="data_headers")
        data_rows = _required_row_sequence(request.inputs.get("data_rows", ()), field_name="data_rows")
        constants_rows = _required_mapping_sequence(
            request.inputs.get("constants_rows", ()),
            field_name="constants_rows",
        )
        units_config = _normalize_root_units_config(
            request.inputs.get("units") if "units" in request.inputs else None,
            data_headers=data_headers,
            unknown_rows=unknown_rows,
            constants_rows=constants_rows,
        )
        batch = execute_root_batch_from_payload(
            equations=equations,
            unknown_rows=unknown_rows,
            data_headers=data_headers,
            data_rows=data_rows,
            constants_enabled=_validate_bool(
                request.inputs.get("constants_enabled", False),
                field_name="constants_enabled",
            ),
            constants_rows=constants_rows,
            constants_view=_string_value(request.inputs.get("constants_view", "table"), field_name="constants_view"),
            constants_text=str(request.inputs.get("constants_text") or ""),
            mode=_string_value(request.inputs.get("mode", "auto"), field_name="mode") or "auto",
            scan_config=_mapping_or_empty(request.inputs.get("scan_config"), field_name="scan_config"),
            uncertainty_options=_mapping_or_empty(
                request.inputs.get("uncertainty_options"),
                field_name="uncertainty_options",
            ),
            precision=precision_used,
            parallel_options=request.options.parallel,
        )
        check_cancelled()
        roots_count = sum(len(row.result.roots) for row in batch.rows if row.result is not None)
        requested_mode = _string_value(request.inputs.get("mode", "auto"), field_name="mode") or "auto"
        payload = {
            "batch": serialize_root_batch_result(batch, digits=precision_used),
            "mode": requested_mode,
            "analysis_rows": analysis_rows_to_json(
                root_analysis_rows_from_batch(
                    batch,
                    requested_mode=requested_mode,
                )
            ),
            "precision_used": precision_used,
            "row_count": len(batch.rows),
            "roots_count": roots_count,
        }
        if units_config is not None:
            payload["units"] = units_config
    return ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload=payload,
        warnings=tuple(str(value) for value in batch.warnings),
    )


def root_batch_payload_to_result(payload: Mapping[str, Any]) -> Any:
    return deserialize_root_batch_result(payload)


def _normalize_root_units_config(
    units: Any,
    *,
    data_headers: Sequence[str],
    unknown_rows: Sequence[Mapping[str, Any]],
    constants_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if units is None:
        return None
    input_symbols = set(
        canonical_unit_symbol_map(
            data_headers,
            field_name="root data headers",
            fallback_prefix="input",
        ).values()
    )
    unknown_names = [str(row.get("name") or "").strip() for row in unknown_rows if str(row.get("name") or "").strip()]
    output_symbols = set(
        canonical_unit_symbol_map(
            unknown_names,
            field_name="root unknowns",
            fallback_prefix="root",
        ).values()
    )
    output_symbols.add("result")
    constant_names = [
        str(row.get("name") or "").strip()
        for row in constants_rows
        if str(row.get("name") or "").strip()
    ]
    constant_symbols = set(
        canonical_unit_symbol_map(
            constant_names,
            field_name="root constants",
            fallback_prefix="constant",
        ).values()
    )
    return normalize_display_only_family_units(
        units,
        family="root_solving",
        allowed_symbols={
            "inputs": input_symbols,
            "constants": constant_symbols,
            "parameters": (),
            "outputs": output_symbols,
        },
    )


def _snapshot_root_units(units: Any) -> dict[str, Any] | None:
    if units is None:
        return None
    return normalize_display_only_family_units(units, family="root_solving")


def build_root_result_snapshot(
    kind: str,
    payload: Mapping[str, Any],
    *,
    overview_state: str = "none",
    plot_metadata: Sequence[Mapping[str, Any]] = (),
    precision: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a UI-neutral root-solving semantic result snapshot."""

    if kind != "root_solving":
        return None
    batch_payload = payload.get("batch")
    if not isinstance(batch_payload, Mapping):
        return None
    display_digits = _snapshot_int(payload.get("display_digits"), default=10)
    uncertainty_digits = _snapshot_int(payload.get("uncertainty_digits"), default=1)
    language = _snapshot_language(payload.get("language"))
    precision_payload = _snapshot_plain_mapping(precision or {})
    fallback_compute_digits = _snapshot_int(
        precision_payload.get("compute_digits") if isinstance(precision_payload, Mapping) else None,
        default=max(16, display_digits),
    )
    compute_digits = _snapshot_int(
        payload.get("compute_digits", payload.get("precision_used")),
        default=fallback_compute_digits,
    )
    precision_payload["compute_digits"] = compute_digits
    try:
        with precision_guard(compute_digits):
            batch = deserialize_root_batch_result(batch_payload)
    except (TypeError, ValueError):
        return None

    roots_count = sum(len(row.result.roots) for row in batch.rows if row.result is not None)
    row_warning_count = 0
    warnings: list[str] = [str(value) for value in batch.warnings]
    for row in batch.rows:
        row_warning_count += len(row.warnings)
        warnings.extend(str(value) for value in row.warnings)
        if row.result is not None:
            row_warning_count += len(row.result.warnings)
            warnings.extend(str(value) for value in row.result.warnings)
    plots = [_snapshot_plain_mapping(plot) for plot in plot_metadata]
    analysis_rows = _snapshot_root_analysis_rows(payload, batch)
    units_config = _snapshot_root_units(payload.get("units") if "units" in payload else None)
    snapshot: dict[str, object] = {
        "schema": ROOT_RESULT_SNAPSHOT_SCHEMA,
        "schema_version": ROOT_RESULT_SNAPSHOT_SCHEMA_VERSION,
        "family": "root_solving",
        "mode": _snapshot_root_mode(batch),
        "batch": deepcopy(dict(batch_payload)),
        "display": {
            "display_digits": display_digits,
            "uncertainty_digits": uncertainty_digits,
            "language": language,
        },
        "warnings": _snapshot_dedupe_text(warnings),
        "metric_rows": _snapshot_rows_by_group(analysis_rows, "metric"),
        "diagnostic_rows": _snapshot_rows_by_group(analysis_rows, "diagnostic"),
        "row_flags": _snapshot_rows_by_group(analysis_rows, "row_flag"),
        "plot_spec_keys": ["root_solving.nominal"] if plots else [],
        "plot_metadata": {
            "image_mode": "root_solving",
            "plot_count": len(plots),
            "plots": plots,
        },
        "source": {
            "row_count": len(batch.rows),
            "roots_count": roots_count,
            "warning_count": len(batch.warnings) + row_warning_count,
            "source_columns": [str(value) for value in batch.headers],
        },
        "precision": precision_payload,
        "compatibility": {
            "result_cache_kind": kind,
            "overview_state": _snapshot_clean_text(overview_state or "none"),
            "rendered_cache_fields": ["markdown", "csv", "latex_source", "plots"],
            "rendered_caches_authoritative": False,
            "latex_regeneration": "cache_only_until_root_latex_semantic_regeneration",
        },
    }
    if units_config is not None:
        snapshot["units"] = units_config
    try:
        normalized = normalize_json_payload(snapshot, path="root_result_snapshot")
    except (TypeError, ValueError):
        return None
    if not isinstance(normalized, Mapping):
        return None
    return {str(key): value for key, value in deepcopy(normalized).items()}


def root_analysis_rows_from_batch(
    batch: RootBatchResult,
    *,
    requested_mode: str | None = None,
) -> tuple[AnalysisRow, ...]:
    """Derive UI-neutral semantic analysis rows from a root batch result."""

    roots_count = sum(len(row.result.roots) for row in batch.rows if row.result is not None)
    rows: list[AnalysisRow] = [
        AnalysisRow(
            key="root_input_row_count",
            label_key="root_solving.metric.input_row_count",
            value=len(batch.rows),
            render_group="metric",
        ),
        AnalysisRow(
            key="roots_count",
            label_key="root_solving.metric.roots_count",
            value=roots_count,
            render_group="metric",
        ),
    ]
    resolved_requested_mode = _root_requested_mode(batch, requested_mode)
    if resolved_requested_mode:
        rows.append(
            AnalysisRow(
                key="requested_mode",
                label_key="root_solving.diagnostic.requested_mode",
                value=resolved_requested_mode,
                method=resolved_requested_mode,
                render_group="diagnostic",
            )
        )
    for warning_index, warning in enumerate(batch.warnings):
        text = str(warning).strip()
        if text:
            rows.append(
                AnalysisRow(
                    key=f"batch_warning.{warning_index}",
                    label_key="root_solving.flag.batch_warning",
                    value=text,
                    severity="warning",
                    message_key="root_solving.warning.batch",
                    render_group="row_flag",
                )
            )
    for row_position, batch_row in enumerate(batch.rows):
        rows.extend(_root_batch_row_analysis_rows(batch_row, row_position=row_position))
    return tuple(rows)


def render_root_snapshot_outputs(
    snapshot: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]], list[str]] | None:
    """Regenerate root result text and CSV from a semantic batch payload."""

    if snapshot.get("family") != "root_solving":
        return None
    batch_payload = snapshot.get("batch")
    if not isinstance(batch_payload, Mapping):
        return None
    display = snapshot.get("display")
    if not isinstance(display, Mapping):
        display = {}
    try:
        display_digits = _snapshot_int(display.get("display_digits"), default=10)
        uncertainty_digits = _snapshot_int(display.get("uncertainty_digits"), default=1)
        language = _snapshot_language(display.get("language"))
        compute_digits = _snapshot_int(
            (snapshot.get("precision") or {}).get("compute_digits") if isinstance(snapshot.get("precision"), Mapping) else None,
            default=max(16, display_digits),
        )
        from root_solving.formatting import render_root_batch_result

        with precision_guard(compute_digits):
            batch = deserialize_root_batch_result(batch_payload)
            root_units_by_name = _root_units_by_name(snapshot.get("units"), batch)
            text, csv_rows, csv_headers = render_root_batch_result(
                batch,
                display_digits=display_digits,
                uncertainty_digits=uncertainty_digits,
                language=language,
                root_units_by_name=root_units_by_name,
            )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    return text, csv_rows, csv_headers


def _root_units_by_name(units: Any, batch: RootBatchResult) -> dict[str, str]:
    names: list[str] = []
    for row in batch.rows:
        if row.result is None:
            continue
        names.extend(str(root.name) for root in row.result.roots if str(root.name).strip())
    return unit_annotations_for_labels(
        units,
        "outputs",
        names,
        fallback_prefix="root",
        default_key="result",
    )


def _root_batch_row_analysis_rows(
    batch_row: RootBatchRowResult,
    *,
    row_position: int,
) -> tuple[AnalysisRow, ...]:
    row_key = _root_row_key(batch_row, row_position)
    rows: list[AnalysisRow] = []
    for warning_index, warning in enumerate(batch_row.warnings):
        text = str(warning).strip()
        if text:
            rows.append(
                AnalysisRow(
                    key=f"row_warning.{row_key}.{warning_index}",
                    label_key="root_solving.flag.row_warning",
                    value=text,
                    row_index=batch_row.row_index,
                    severity="warning",
                    message_key="root_solving.warning.row",
                    render_group="row_flag",
                )
            )
    if batch_row.failure:
        rows.append(
            AnalysisRow(
                key=f"failed_input_row.{row_key}",
                label_key="root_solving.flag.failed_input_row",
                value=str(batch_row.failure),
                row_index=batch_row.row_index,
                severity="error",
                message_key="root_solving.failure.input_row",
                render_group="row_flag",
            )
        )
        return tuple(rows)
    if batch_row.result is None:
        rows.append(
            AnalysisRow(
                key=f"failed_input_row.{row_key}",
                label_key="root_solving.flag.failed_input_row",
                value="missing result",
                row_index=batch_row.row_index,
                severity="error",
                message_key="root_solving.failure.missing_result",
                render_group="row_flag",
            )
        )
        return tuple(rows)
    rows.extend(_root_result_analysis_rows(batch_row.result, batch_row=batch_row, row_key=row_key))
    return tuple(rows)


def _root_result_analysis_rows(
    result: RootResult,
    *,
    batch_row: RootBatchRowResult,
    row_key: str,
) -> tuple[AnalysisRow, ...]:
    rows: list[AnalysisRow] = [
        AnalysisRow(
            key=f"resolved_mode.{row_key}",
            label_key="root_solving.diagnostic.resolved_mode",
            value=_root_detail_text(result, "resolved_mode") or result.mode,
            row_index=batch_row.row_index,
            method=_root_detail_text(result, "requested_mode"),
            render_group="diagnostic",
        ),
        AnalysisRow(
            key=f"backend.{row_key}",
            label_key="root_solving.diagnostic.backend",
            value=result.backend,
            row_index=batch_row.row_index,
            method=result.mode,
            render_group="diagnostic",
        ),
    ]
    if result.residual_norm is not None:
        rows.append(
            AnalysisRow(
                key=f"residual_norm.{row_key}",
                label_key="root_solving.diagnostic.residual_norm",
                value=_root_numeric_text(result.residual_norm),
                row_index=batch_row.row_index,
                method=result.mode,
                render_group="diagnostic",
            )
        )
    if result.jacobian_condition is not None:
        rows.append(
            AnalysisRow(
                key=f"jacobian_condition.{row_key}",
                label_key="root_solving.diagnostic.jacobian_condition",
                value=_root_numeric_text(result.jacobian_condition),
                row_index=batch_row.row_index,
                method=result.mode,
                render_group="diagnostic",
            )
        )
    solver_status = _root_detail_text(result, "solver_status")
    if solver_status:
        rows.append(
            AnalysisRow(
                key=f"solver_status.{row_key}",
                label_key="root_solving.diagnostic.solver_status",
                value=solver_status,
                row_index=batch_row.row_index,
                method=result.mode,
                render_group="diagnostic",
            )
        )
    initial_guess_summary = _root_detail_text(result, "initial_guess_summary")
    if initial_guess_summary:
        rows.append(
            AnalysisRow(
                key=f"initial_guess_summary.{row_key}",
                label_key="root_solving.diagnostic.initial_guess_summary",
                value=initial_guess_summary,
                row_index=batch_row.row_index,
                method=result.mode,
                render_group="diagnostic",
            )
        )
    scipy_iterations = _root_detail_int(result, "scipy_iterations")
    if scipy_iterations is not None:
        rows.append(
            AnalysisRow(
                key=f"scipy_iterations.{row_key}",
                label_key="root_solving.diagnostic.scipy_iterations",
                value=scipy_iterations,
                row_index=batch_row.row_index,
                method=result.mode,
                render_group="diagnostic",
            )
        )
    scipy_function_evaluations = _root_detail_int(result, "scipy_function_evaluations")
    if scipy_function_evaluations is not None:
        rows.append(
            AnalysisRow(
                key=f"scipy_function_evaluations.{row_key}",
                label_key="root_solving.diagnostic.scipy_function_evaluations",
                value=scipy_function_evaluations,
                row_index=batch_row.row_index,
                method=result.mode,
                render_group="diagnostic",
            )
        )
    rows.extend(
        _root_scan_summary_analysis_rows(
            result.details,
            row_key=row_key,
            row_index=batch_row.row_index,
            method=result.mode,
        )
    )
    rows.extend(
        _root_scan_evidence_analysis_rows(
            result.details,
            row_key=row_key,
            row_index=batch_row.row_index,
            method=result.mode,
            accepted_root_count=len(result.roots),
        )
    )
    rows.extend(
        _root_per_equation_residual_rows(
            result.details,
            row_key=row_key,
            row_index=batch_row.row_index,
            method=result.mode,
        )
    )
    classification_tags = _root_classification_tags(result.details)
    for root_index, tags in sorted(classification_tags.items()):
        if tags:
            rows.append(
                AnalysisRow(
                    key=f"classification_tags.{row_key}.{root_index}",
                    label_key="root_solving.diagnostic.classification_tags",
                    value=", ".join(tags),
                    row_index=batch_row.row_index,
                    method=result.mode,
                    render_group="diagnostic",
                )
            )
    for warning_index, warning in enumerate(result.warnings):
        text = str(warning).strip()
        if text:
            rows.append(
                AnalysisRow(
                    key=f"result_warning.{row_key}.{warning_index}",
                    label_key="root_solving.flag.result_warning",
                    value=text,
                    row_index=batch_row.row_index,
                    method=result.mode,
                    severity="warning",
                    message_key="root_solving.warning.result",
                    render_group="row_flag",
                )
            )
    return tuple(rows)


def _snapshot_root_analysis_rows(
    payload: Mapping[str, Any],
    batch: RootBatchResult,
) -> list[dict[str, object]]:
    requested_mode = _snapshot_clean_text(payload.get("mode"))
    rebuilt_rows = analysis_rows_to_json(
        root_analysis_rows_from_batch(batch, requested_mode=requested_mode or None)
    )
    raw_rows = payload.get("analysis_rows")
    if raw_rows is not None:
        try:
            row_payload = analysis_rows_to_json(analysis_rows_from_json(raw_rows))
            if row_payload == rebuilt_rows:
                return row_payload
        except (TypeError, ValueError):
            pass
    return rebuilt_rows


def _snapshot_rows_by_group(
    rows: Sequence[Mapping[str, object]],
    group: str,
) -> list[dict[str, object]]:
    return [dict(row) for row in rows if row.get("render_group") == group]


def _root_requested_mode(batch: RootBatchResult, requested_mode: str | None) -> str:
    text = _snapshot_clean_text(requested_mode)
    if text:
        return text
    detail_mode = _snapshot_clean_text(batch.details.get("requested_mode"))
    if detail_mode:
        return detail_mode
    for row in batch.rows:
        result = row.result
        if result is None:
            continue
        detail_mode = _root_detail_text(result, "requested_mode")
        if detail_mode:
            return detail_mode
    return ""


def _root_row_key(row: RootBatchRowResult, row_position: int) -> str:
    return str(row.row_index if row.row_index is not None else row_position)


def _root_detail_text(result: RootResult, key: str) -> str:
    return _snapshot_clean_text(result.details.get(key))


def _root_detail_int(result: RootResult, key: str) -> int | None:
    value = result.details.get(key)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("+"):
            text = text[1:]
        if not text.isdecimal():
            return None
        return int(text)
    return None


def _root_numeric_text(value: Any) -> str:
    return numeric_to_payload_string(value, field_name="root_analysis_row.value", digit_hint=100)


def _root_scan_summary_analysis_rows(
    details: Mapping[str, object],
    *,
    row_key: str,
    row_index: int | None,
    method: str,
) -> tuple[AnalysisRow, ...]:
    raw = details.get("scan_summary")
    if not isinstance(raw, Mapping):
        return ()
    rows: list[AnalysisRow] = []
    for field_name in ("lower", "upper", "sample_count", "max_roots", "accepted_roots_count"):
        value = raw.get(field_name)
        row_value = _root_diagnostic_value(value)
        if row_value is None:
            continue
        rows.append(
            AnalysisRow(
                key=f"scan_summary.{row_key}.{field_name}",
                label_key=f"root_solving.diagnostic.scan_summary.{field_name}",
                value=row_value,
                row_index=row_index,
                method=method,
                render_group="diagnostic",
            )
        )
    return tuple(rows)


def _root_scan_evidence_analysis_rows(
    details: Mapping[str, object],
    *,
    row_key: str,
    row_index: int | None,
    method: str,
    accepted_root_count: int,
) -> tuple[AnalysisRow, ...]:
    if method != "scan_multiple" or accepted_root_count <= 0:
        return ()
    raw = details.get("scan_root_evidence")
    if not isinstance(raw, Mapping):
        return ()
    rows: list[AnalysisRow] = []
    for raw_root_index, raw_evidence in sorted(raw.items(), key=lambda item: _root_residual_sort_key(item[0])):
        root_index = _root_scan_evidence_index(raw_root_index)
        if root_index is None:
            continue
        if root_index < 0 or root_index >= accepted_root_count:
            continue
        if not isinstance(raw_evidence, Mapping):
            continue
        kind_value = _root_scan_evidence_value("kind", raw_evidence.get("kind"))
        if kind_value not in {"exact_sample", "bracketed_sign_change", "local_minimum"}:
            continue
        for field_name in ("kind", "left", "right", "left_value", "right_value", "sample", "merged_candidates"):
            row_value = _root_scan_evidence_value(field_name, raw_evidence.get(field_name))
            if row_value is None:
                continue
            rows.append(
                AnalysisRow(
                    key=f"scan_evidence.{row_key}.{root_index}.{field_name}",
                    label_key=f"root_solving.diagnostic.scan_evidence.{field_name}",
                    value=row_value,
                    row_index=row_index,
                    method=method,
                    render_group="diagnostic",
                )
            )
    return tuple(rows)


def _root_scan_evidence_index(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value
        if text.isdecimal() and text == str(int(text)):
            return int(text)
    return None


def _root_scan_evidence_value(field_name: str, value: object) -> str | int | None:
    if value is None or isinstance(value, (bool, float)):
        return None
    if field_name == "merged_candidates":
        if isinstance(value, int):
            return value if value >= 0 else None
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _root_per_equation_residual_rows(
    details: Mapping[str, object],
    *,
    row_key: str,
    row_index: int | None,
    method: str,
) -> tuple[AnalysisRow, ...]:
    raw = details.get("per_equation_residuals")
    if not isinstance(raw, Mapping):
        return ()
    rows: list[AnalysisRow] = []
    for key, value in sorted(raw.items(), key=lambda item: _root_residual_sort_key(item[0])):
        try:
            equation_index = int(key)
        except (TypeError, ValueError):
            continue
        row_value = _root_diagnostic_value(value)
        if row_value is None:
            continue
        rows.append(
            AnalysisRow(
                key=f"per_equation_residual.{row_key}.{equation_index}",
                label_key="root_solving.diagnostic.per_equation_residual",
                value=row_value,
                row_index=row_index,
                method=method,
                render_group="diagnostic",
            )
        )
    return tuple(rows)


def _root_residual_sort_key(value: object) -> tuple[int, str]:
    text = str(value)
    try:
        return (int(text), text)
    except ValueError:
        return (10**9, text)


def _root_diagnostic_value(value: object) -> str | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return text or None


def _root_classification_tags(details: Mapping[str, object]) -> dict[int, tuple[str, ...]]:
    raw = details.get("root_classification_tags")
    if isinstance(raw, Mapping):
        tags_by_index: dict[int, tuple[str, ...]] = {}
        for key, value in raw.items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            tags_by_index[index] = _ordered_root_classification_tags(value)
        return tags_by_index
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return {index: _ordered_root_classification_tags(value) for index, value in enumerate(raw)}
    return {}


def _ordered_root_classification_tags(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_tags = {value}
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_tags = {str(tag) for tag in value}
    else:
        return ()
    tags = {tag for tag in raw_tags if tag in _ROOT_CLASSIFICATION_TAGS and tag != "unclassified"}
    if not tags and "unclassified" in raw_tags:
        return ("unclassified",)
    return tuple(tag for tag in _ROOT_CLASSIFICATION_TAGS if tag in tags)


def _normalize_equations(equations: Sequence[str]) -> list[str]:
    if isinstance(equations, (str, bytes, bytearray, memoryview)):
        raise TypeError("equations must be a sequence of equation strings.")
    normalized = [str(equation).strip() for equation in equations if str(equation).strip()]
    if not normalized:
        raise ValueError("equations must contain at least one equation.")
    return normalized


def _required_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    normalized = [str(item).strip() for item in value if str(item).strip()]
    if not normalized:
        raise ValueError(f"{field_name} must contain at least one value.")
    return normalized


def _optional_string_sequence(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    return [str(item).strip() for item in value if str(item).strip()]


def _required_mapping_sequence(value: Any, *, field_name: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if isinstance(value, Mapping) or isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of mappings.")
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise TypeError(f"{field_name}[{index}] must be a mapping.")
        normalized.append({str(key): str(item) for key, item in row.items()})
    return normalized


def _required_row_sequence(value: Any, *, field_name: str) -> list[list[str]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, memoryview)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of rows.")
    rows: list[list[str]] = []
    for row_index, row in enumerate(value):
        if isinstance(row, (str, bytes, bytearray, memoryview)) or not isinstance(row, Sequence):
            raise TypeError(f"{field_name}[{row_index}] must be a sequence.")
        rows.append([str(cell) for cell in row])
    return rows


def _mapping_or_empty(value: Any, *, field_name: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    return {str(key): item for key, item in value.items()}


def _normalize_unknown_rows(rows: Sequence[Mapping[str, Any]], *, digit_hint: int) -> list[dict[str, str]]:
    if isinstance(rows, Mapping) or isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("unknown_rows must be a sequence of row mappings.")
    if not rows:
        raise ValueError("unknown_rows must contain at least one row.")

    normalized: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"unknown_rows[{index}] must be a mapping.")
        name = str(row.get("name") or "").strip()
        initial = _optional_numeric_text(row.get("initial"), field_name=f"unknown_rows[{index}].initial", digit_hint=digit_hint)
        lower = _optional_numeric_text(row.get("lower"), field_name=f"unknown_rows[{index}].lower", digit_hint=digit_hint)
        upper = _optional_numeric_text(row.get("upper"), field_name=f"unknown_rows[{index}].upper", digit_hint=digit_hint)
        if not any((name, initial, lower, upper)):
            continue
        source = str(row.get("source") or "manual").strip()
        if source not in _UNKNOWN_SOURCES:
            source = "manual"
        normalized.append(
            {
                "name": name,
                "initial": initial,
                "lower": lower,
                "upper": upper,
                "source": source,
            }
        )
    if not normalized:
        raise ValueError("unknown_rows must contain at least one row with meaningful data.")
    return normalized


def _normalize_optional_headers(headers: Sequence[str]) -> list[str]:
    if not headers:
        return []
    return normalize_headers(headers)


def _snapshot_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _snapshot_language(value: Any) -> str:
    language = str(value or "en")
    return language if language in {"en", "zh"} else "en"


def _snapshot_root_mode(batch: Any) -> str:
    modes: list[str] = []
    for row in getattr(batch, "rows", ()):
        result = getattr(row, "result", None)
        if result is not None:
            mode = str(getattr(result, "mode", "") or "")
            if mode:
                modes.append(mode)
    if not modes:
        return ""
    first = modes[0]
    return first if all(mode == first for mode in modes) else "mixed"


def _snapshot_plain_mapping(value: Mapping[str, Any]) -> dict[str, object]:
    clean: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            clean[str(key)] = _snapshot_plain_mapping(item)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray, memoryview)):
            clean[str(key)] = [
                _snapshot_plain_mapping(entry) if isinstance(entry, Mapping) else entry
                for entry in item
            ]
        else:
            clean[str(key)] = item
    normalized = normalize_json_payload(clean, path="root_result_snapshot.mapping")
    return dict(normalized) if isinstance(normalized, Mapping) else {}


def _snapshot_clean_text(value: Any) -> str:
    return str(value or "").strip()


def _snapshot_dedupe_text(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _snapshot_clean_text(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _normalize_data_rows(
    rows: Sequence[Sequence[Any]],
    *,
    headers: Sequence[str],
    digit_hint: int,
) -> list[list[str]]:
    if isinstance(rows, (str, bytes, bytearray, memoryview)):
        raise TypeError("data_rows must be a sequence of row sequences.")
    if not rows:
        return []
    normalized_headers = _normalize_optional_headers(headers)
    if not normalized_headers:
        raise ValueError("data_headers must contain at least one column when data_rows are provided.")
    normalized_rows: list[list[str]] = []
    for row_index, row in enumerate(rows):
        if isinstance(row, (str, bytes, bytearray, memoryview)):
            raise TypeError(f"Root data row {row_index + 1} must be a sequence of values.")
        if len(row) < len(normalized_headers):
            missing_header = normalized_headers[len(row)]
            raise ValueError(f"Root data row {row_index + 1} is missing column {missing_header}.")
        normalized_rows.append(
            [
                _required_cell_text(
                    row[column_index],
                    field_name=f"data_rows[{row_index}][{header}]",
                    digit_hint=digit_hint,
                )
                for column_index, header in enumerate(normalized_headers)
            ]
        )
    return normalized_rows


def _normalize_constants_rows(
    rows: Sequence[Mapping[str, Any]] | Mapping[str, Any] | None,
    *,
    digit_hint: int,
) -> list[dict[str, str]]:
    source_rows: list[Mapping[str, Any]]
    if rows is None:
        return []
    if isinstance(rows, Mapping):
        source_rows = [{"name": key, "value": value} for key, value in rows.items()]
    elif isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray, memoryview)):
        source_rows = list(rows)
    else:
        raise TypeError("constants_rows must be a mapping or sequence of row mappings.")

    normalized: list[dict[str, str]] = []
    for index, row in enumerate(source_rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"constants_rows[{index}] must be a mapping.")
        name = str(row.get("name") or "").strip()
        value = row.get("value")
        if not name and (value is None or str(value).strip() == ""):
            continue
        if not name:
            raise ValueError(f"constants_rows[{index}].name must not be empty.")
        normalized.append(
            {
                "name": name,
                "value": _required_cell_text(
                    value,
                    field_name=f"constants_rows[{index}].value",
                    digit_hint=digit_hint,
                ),
            }
        )
    return normalized


def _normalize_mode(mode: str) -> str:
    normalized = _string_value(mode, field_name="mode").strip() or "auto"
    if normalized not in _ROOT_MODES:
        raise ValueError(f"Invalid root mode: {mode}.")
    return normalized


def _normalize_option_mapping(value: Mapping[str, Any], *, field_name: str, digit_hint: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping.")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be strings.")
        normalized[key] = _normalize_option_value(item, field_name=f"{field_name}.{key}", digit_hint=digit_hint)
    return normalized


def _normalize_option_value(value: Any, *, field_name: str, digit_hint: int) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass numeric inputs as strings.")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _normalize_option_mapping(value, field_name=field_name, digit_hint=digit_hint)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return [
            _normalize_option_value(item, field_name=f"{field_name}[{index}]", digit_hint=digit_hint)
            for index, item in enumerate(value)
        ]
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _optional_numeric_text(value: Any, *, field_name: str, digit_hint: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and not value.strip():
        return ""
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _required_cell_text(value: Any, *, field_name: str, digit_hint: int) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty.")
    return numeric_to_payload_string(value, field_name=field_name, digit_hint=digit_hint)


def _string_value(value: Any, *, field_name: str) -> str:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass text options as strings.")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a string.")
    return str(value or "")


def _validate_bool(value: bool, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean.")
    return value


def _validate_int(value: int, *, field_name: str) -> int:
    if isinstance(value, float):
        raise TypeError(f"JSON floats are not allowed at {field_name}; pass integer options as integers.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer.")
    return value
