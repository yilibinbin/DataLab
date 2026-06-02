from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

from shared.bilingual import _dual_msg
from shared.computation_inputs import (
    SymbolCategories,
    classify_expression_symbols,
    validate_symbol_classification,
)
from shared.expression_names import is_reserved_expression_name
from shared.input_normalization import IDENTIFIER_RE, ConstantsState, normalize_constants_state, string_value
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS
from shared.uncertainty import UncertainValue, parse_uncertainty_format

from root_solving.models import RootInputValue, RootMode, RootProblem, RootUnknown

_ROOT_MODES: set[str] = {"auto", "scalar", "polynomial", "system"}
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
    seen: dict[str, str] = {}
    for scope, names in (
        ("unknown", [unknown.name for unknown in unknowns]),
        ("known value", [known.name for known in known_values]),
        ("constant", list(constants)),
    ):
        local_seen: set[str] = set()
        for name in names:
            if is_reserved_expression_name(name):
                raise ValueError(_dual_msg(f"名称是保留字：{name}", f"Name is reserved: {name}"))
            if name in local_seen:
                if scope == "unknown":
                    raise ValueError(_dual_msg(f"未知量重复：{name}", f"Duplicate unknown: {name}"))
                if scope == "known value":
                    raise ValueError(_dual_msg(f"已知量重复：{name}", f"Duplicate known value: {name}"))
                raise ValueError(_dual_msg(f"常数名重复：{name}", f"Duplicate constant name: {name}"))
            local_seen.add(name)
            previous = seen.get(name)
            if previous is not None:
                raise ValueError(
                    _dual_msg(
                        f"名称冲突：{name} 同时出现在 {previous} 和 {scope}。",
                        f"name collision: {name} appears in both {previous} and {scope}.",
                    )
                )
            seen[name] = scope


def _clamp_precision(value: Any) -> int:
    try:
        precision = int(value)
    except (TypeError, ValueError, OverflowError):
        precision = 16
    clamped: int = max(MIN_MPMATH_DPS, min(MAX_MPMATH_DPS, precision))
    return clamped
