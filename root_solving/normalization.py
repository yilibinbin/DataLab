from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

from shared.bilingual import _dual_msg
from shared.computation_inputs import (
    SymbolCategories,
    classify_expression_symbols,
    validate_symbol_classification,
)
from shared.input_normalization import IDENTIFIER_RE, ConstantsState, normalize_constants_state, string_value
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS
from shared.uncertainty import UncertainValue, parse_uncertainty_format

from root_solving.models import RootInputValue, RootMode, RootProblem, RootScanConfig, RootUnknown

_ROOT_MODES: set[str] = {"auto", "scalar", "polynomial", "system", "scan_multiple"}
_UNKNOWN_SOURCES: set[str] = {"manual", "detected"}


def normalize_root_problem(
    *,
    equations: Iterable[Any],
    unknown_rows: Iterable[dict[str, Any]],
    known_rows: Iterable[dict[str, Any]],
    constants_enabled: bool,
    constants_rows: Iterable[dict[str, Any]] | dict[str, Any] | None = None,
    constants_view: str = "table",
    constants_text: str = "",
    mode: str = "auto",
    precision: Any = 16,
    scan_config: Mapping[str, Any] | RootScanConfig | None = None,
) -> tuple[RootProblem, dict[str, UncertainValue]]:
    clean_equations = tuple(str(equation).strip() for equation in equations if str(equation).strip())
    if not clean_equations:
        raise ValueError(_dual_msg("方程不能为空。", "Equation list cannot be empty."))

    normalized_mode = str(mode or "auto").strip()
    if normalized_mode not in _ROOT_MODES:
        raise ValueError(_dual_msg(f"求根模式无效：{mode}", f"Invalid root mode: {mode}"))

    unknowns = _normalize_unknown_rows(unknown_rows)
    known_values, uncertain_inputs = _normalize_known_rows(known_rows)

    constants_state = normalize_constants_state(
        enabled=constants_enabled,
        view=constants_view,
        rows=constants_rows,
        text=constants_text,
        numeric_mode="uncertainty",
    )
    constants = constants_state.compute_dict(validate=True)
    for name, value in constants.items():
        uncertain_inputs[name] = parse_uncertainty_format(value)

    _validate_scope(unknowns=unknowns, known_values=known_values, constants=constants)

    problem = RootProblem(
        equations=clean_equations,
        unknowns=tuple(unknowns),
        known_values=tuple(known_values),
        constants=dict(constants),
        mode=cast(RootMode, normalized_mode),
        precision=_clamp_precision(precision),
        scan_config=_normalize_scan_config(scan_config),
    )
    return problem, uncertain_inputs


def normalize_root_problem_from_context(
    *,
    equations: Iterable[Any],
    unknown_rows: Iterable[dict[str, Any]],
    row_values: Mapping[str, str],
    constants_state: ConstantsState,
    mode: str = "auto",
    precision: Any = 16,
    scan_config: Mapping[str, Any] | RootScanConfig | None = None,
) -> RootProblem:
    clean_equations = tuple(str(equation).strip() for equation in equations if str(equation).strip())
    if not clean_equations:
        raise ValueError(_dual_msg("方程不能为空。", "Equation list cannot be empty."))

    normalized_mode = str(mode or "auto").strip()
    if normalized_mode not in _ROOT_MODES:
        raise ValueError(_dual_msg(f"求根模式无效：{mode}", f"Invalid root mode: {mode}"))

    unknowns = _normalize_unknown_rows(unknown_rows)
    _validate_scope(unknowns=unknowns, known_values=(), constants={})

    constants = constants_state.compute_dict(validate=True)
    classification = classify_expression_symbols(
        clean_equations,
        SymbolCategories(
            unknowns=tuple(unknown.name for unknown in unknowns),
            data_columns=tuple(row_values),
            constants=tuple(constants),
        ),
    )
    validate_symbol_classification(classification)

    return RootProblem(
        equations=clean_equations,
        unknowns=tuple(unknowns),
        row_values=dict(row_values),
        constants=dict(constants),
        mode=cast(RootMode, normalized_mode),
        precision=_clamp_precision(precision),
        scan_config=_normalize_scan_config(scan_config),
    )


def _normalize_unknown_rows(rows: Iterable[dict[str, Any]]) -> list[RootUnknown]:
    unknowns: list[RootUnknown] = []
    for index, row in enumerate(_coerce_rows(rows, "Unknown rows"), 1):
        name = string_value(row.get("name")).strip()
        initial = string_value(row.get("initial")).strip()
        lower = string_value(row.get("lower")).strip()
        upper = string_value(row.get("upper")).strip()
        source = string_value(row.get("source")).strip()
        if not any((name, initial, lower, upper)):
            continue
        _validate_identifier(name, kind_zh="未知量", kind_en="unknown", index=index)
        if source not in _UNKNOWN_SOURCES:
            source = "manual"
        unknowns.append(RootUnknown(name=name, initial=initial, lower=lower, upper=upper, source=source))
    return unknowns


def _normalize_known_rows(rows: Iterable[dict[str, Any]]) -> tuple[list[RootInputValue], dict[str, UncertainValue]]:
    values: list[RootInputValue] = []
    uncertain: dict[str, UncertainValue] = {}
    for index, row in enumerate(_coerce_rows(rows, "Known rows"), 1):
        name = string_value(row.get("name")).strip()
        value = string_value(row.get("value")).strip()
        if not name and not value:
            continue
        _validate_identifier(name, kind_zh="已知量", kind_en="known value", index=index)
        if not value:
            raise ValueError(
                _dual_msg(
                    f"已知量 {name} 需要数值。",
                    f"Known value {name} needs a value.",
                )
            )
        try:
            uncertain[name] = parse_uncertainty_format(value)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                _dual_msg(
                    f"已知量 {name} 的数值无效。",
                    f"Invalid value for known value {name}.",
                )
            ) from exc
        values.append(RootInputValue(name=name, value=value))
    return values, uncertain


def _coerce_rows(rows: Iterable[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    if isinstance(rows, (str, bytes, dict)) or not isinstance(rows, Iterable):
        raise ValueError(_dual_msg(f"{source} 必须是行对象列表。", f"{source} must be a list of row objects."))
    clean_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(_dual_msg(f"{source} 第 {index} 行格式无效。", f"{source} row {index} is malformed."))
        clean_rows.append(row)
    return clean_rows


def _validate_identifier(name: str, *, kind_zh: str, kind_en: str, index: int) -> None:
    if not name:
        raise ValueError(_dual_msg(f"{kind_zh}第 {index} 行名称不能为空。", f"{kind_en} row {index} name cannot be empty."))
    if not IDENTIFIER_RE.fullmatch(name):
        raise ValueError(_dual_msg(f"{kind_zh}名称无效：{name}", f"Invalid {kind_en} name: {name}"))


def _validate_scope(
    *,
    unknowns: Iterable[RootUnknown],
    known_values: Iterable[RootInputValue],
    constants: Mapping[str, str],
) -> None:
    classification = classify_expression_symbols(
        (),
        SymbolCategories(
            unknowns=tuple(unknown.name for unknown in unknowns),
            data_columns=tuple(known.name for known in known_values),
            constants=tuple(constants),
        ),
    )
    validate_symbol_classification(classification)


def _clamp_precision(value: Any) -> int:
    try:
        precision = int(value)
    except (TypeError, ValueError, OverflowError):
        precision = 16
    clamped: int = max(MIN_MPMATH_DPS, min(MAX_MPMATH_DPS, precision))
    return clamped


def _normalize_scan_config(value: Mapping[str, Any] | RootScanConfig | None) -> RootScanConfig:
    if isinstance(value, RootScanConfig):
        return value
    if not value:
        return RootScanConfig()
    return RootScanConfig(
        enabled=bool(value.get("enabled", False)),
        max_roots=_clamp_positive_int(value.get("max_roots"), default=20, minimum=1, maximum=10000),
        sample_count=_clamp_positive_int(value.get("sample_count"), default=200, minimum=2, maximum=100000),
        residual_tolerance=string_value(value.get("residual_tolerance")).strip(),
        cluster_tolerance=string_value(value.get("cluster_tolerance")).strip(),
    )


def _clamp_positive_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError, OverflowError):
        numeric = default
    return max(minimum, min(maximum, numeric))
