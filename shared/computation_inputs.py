from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, TypeVar, cast

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.expression_names import is_reserved_expression_name
from shared.input_normalization import ConstantsState
from shared.symbolic_math import normalize_symbolic_expression
from shared.uncertainty import UncertainValue, parse_numeric_value, parse_uncertainty_format

__all__ = [
    "ComputationDataRow",
    "ComputationInputContext",
    "ComputationScopePolicy",
    "SymbolCategories",
    "SymbolClassification",
    "SymbolIssue",
    "build_data_rows",
    "classify_expression_symbols",
    "extract_expression_symbols",
    "extract_uncertainties",
    "merge_scope",
    "validate_symbol_classification",
]

_IDENTIFIER_TOKEN_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_K = TypeVar("_K")
_V = TypeVar("_V")


def _immutable_mapping(values: Mapping[_K, _V] | None = None) -> Mapping[_K, _V]:
    return MappingProxyType(dict(values or {}))


@dataclass(frozen=True)
class SymbolCategories:
    unknowns: tuple[str, ...] = ()
    data_columns: tuple[str, ...] = ()
    constants: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()
    duplicates: tuple[tuple[str, str], ...] = field(default=(), init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "duplicates",
            (
                *_duplicate_names("unknown", self.unknowns),
                *_duplicate_names("data", self.data_columns),
                *_duplicate_names("constant", self.constants),
                *_duplicate_names("parameter", self.parameters),
                *_duplicate_names("target", self.targets),
            ),
        )
        object.__setattr__(self, "unknowns", _normalize_names(self.unknowns))
        object.__setattr__(self, "data_columns", _normalize_names(self.data_columns))
        object.__setattr__(self, "constants", _normalize_names(self.constants))
        object.__setattr__(self, "parameters", _normalize_names(self.parameters))
        object.__setattr__(self, "targets", _normalize_names(self.targets))


@dataclass(frozen=True)
class SymbolIssue:
    kind: str
    name: str
    message: str


@dataclass(frozen=True)
class SymbolClassification:
    used_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...] = ()
    collisions: tuple[SymbolIssue, ...] = ()
    duplicates: tuple[SymbolIssue, ...] = ()
    reserved_conflicts: tuple[SymbolIssue, ...] = ()
    categories: SymbolCategories = field(default_factory=SymbolCategories)

    @property
    def expression_symbols(self) -> tuple[str, ...]:
        return self.used_symbols

    @property
    def collision_symbols(self) -> tuple[str, ...]:
        return tuple(issue.name for issue in self.collisions)

    @property
    def reserved_symbols(self) -> tuple[str, ...]:
        return tuple(issue.name for issue in self.reserved_conflicts)

    @property
    def issues(self) -> tuple[SymbolIssue, ...]:
        missing = tuple(
            SymbolIssue("missing", name, f"expression symbols are not defined: {name}")
            for name in self.missing_symbols
        )
        return self.duplicates + self.collisions + missing + self.reserved_conflicts


@dataclass(frozen=True)
class ComputationDataRow:
    index: int | None
    values: Mapping[str, mp.mpf] = field(default_factory=_immutable_mapping)
    uncertainties: Mapping[str, UncertainValue] = field(default_factory=_immutable_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _immutable_mapping(self.values))
        object.__setattr__(self, "uncertainties", _immutable_mapping(self.uncertainties))


@dataclass(frozen=True)
class ComputationInputContext:
    data_rows: tuple[ComputationDataRow, ...]
    constants_state: ConstantsState
    categories: SymbolCategories


@dataclass(frozen=True)
class ComputationScopePolicy:
    collisions: Literal["reject"] = "reject"


def extract_expression_symbols(expressions: Iterable[str]) -> tuple[str, ...]:
    """Extract non-reserved identifier tokens from normalized expressions."""

    symbols: set[str] = set()
    for expression in expressions:
        normalized = normalize_symbolic_expression(str(expression))
        for token in _IDENTIFIER_TOKEN_RE.findall(normalized):
            if is_reserved_expression_name(token):
                continue
            symbols.add(token)
    return tuple(sorted(symbols))


def classify_expression_symbols(
    expressions: Iterable[str],
    categories: SymbolCategories,
) -> SymbolClassification:
    used_symbols = extract_expression_symbols(expressions)
    category_map = _category_membership(categories)

    missing_symbols = tuple(symbol for symbol in used_symbols if symbol not in category_map)
    collisions = tuple(
        SymbolIssue(
            "collision",
            name,
            _dual_msg(
                f"名称冲突：{name} 同时出现在 {', '.join(scopes)}。",
                f"name collision: {name} appears in {', '.join(scopes)}.",
            ),
        )
        for name, scopes in sorted(category_map.items())
        if len(set(scopes)) > 1
    )
    duplicates = tuple(
        SymbolIssue(
            "duplicate",
            name,
            _dual_msg(f"{scope} 名称重复：{name}", f"Duplicate {scope}: {name}"),
        )
        for scope, name in categories.duplicates
    )
    reserved_conflicts = tuple(
        SymbolIssue(
            "reserved",
            name,
            _dual_msg(f"名称是保留字：{name}", f"symbol name is reserved: {name}"),
        )
        for name in sorted(_category_names(categories))
        if is_reserved_expression_name(name)
    )

    return SymbolClassification(
        used_symbols=used_symbols,
        missing_symbols=missing_symbols,
        collisions=collisions,
        duplicates=duplicates,
        reserved_conflicts=reserved_conflicts,
        categories=categories,
    )


def validate_symbol_classification(classification: SymbolClassification) -> None:
    if classification.duplicates:
        raise ValueError(classification.duplicates[0].message)
    if classification.collisions:
        raise ValueError(classification.collisions[0].message)
    if classification.reserved_conflicts:
        raise ValueError(classification.reserved_conflicts[0].message)
    if classification.missing_symbols:
        names = ", ".join(classification.missing_symbols)
        raise ValueError(_dual_msg(f"表达式符号未定义：{names}", f"expression symbols are not defined: {names}"))


def build_data_rows(
    headers: Sequence[str],
    rows: Iterable[Sequence[UncertainValue | object]],
) -> tuple[ComputationDataRow, ...]:
    clean_headers = tuple(str(header).strip() for header in headers)
    if any(not header for header in clean_headers):
        raise ValueError(_dual_msg("数据列名不能为空。", "Data column names cannot be empty."))
    invalid_headers = tuple(header for header in clean_headers if not _IDENTIFIER_TOKEN_RE.fullmatch(header))
    if invalid_headers:
        raise ValueError(
            _dual_msg(
                f"数据列名无效：{invalid_headers[0]}",
                f"Invalid data column name: {invalid_headers[0]}",
            )
        )
    if len(set(clean_headers)) != len(clean_headers):
        raise ValueError(_dual_msg("数据列名重复。", "Duplicate data column names."))

    data_rows: list[ComputationDataRow] = []
    for index, raw_row in enumerate(rows):
        values = tuple(raw_row)
        if len(values) != len(clean_headers):
            raise ValueError(
                _dual_msg(
                    f"第 {index + 1} 行数据列数不匹配。",
                    f"Data row {index + 1} has the wrong number of columns.",
                )
            )
        uncertain_values = tuple(_as_uncertain_value(value) for value in values)
        data_rows.append(
            ComputationDataRow(
                index=index,
                values={header: uncertain.value for header, uncertain in zip(clean_headers, uncertain_values, strict=True)},
                uncertainties={
                    header: uncertain for header, uncertain in zip(clean_headers, uncertain_values, strict=True)
                },
            )
        )
    return tuple(data_rows)


def merge_scope(
    row: ComputationDataRow | None,
    constants: Mapping[str, object],
    unknown_values: Mapping[str, object],
) -> Mapping[str, mp.mpf]:
    row_values = row.values if row is not None else {}
    _reject_scope_collisions(row_values, constants, unknown_values)
    scope: dict[str, mp.mpf] = dict(row_values)
    scope.update({name: parse_numeric_value(value) for name, value in constants.items()})
    scope.update({name: _mp_from_value(value) for name, value in unknown_values.items()})
    return MappingProxyType(scope)


def extract_uncertainties(
    row: ComputationDataRow | None,
    constants_state: ConstantsState,
) -> Mapping[str, UncertainValue]:
    uncertainties = {
        name: value
        for name, value in (row.uncertainties.items() if row is not None else ())
        if _has_uncertainty(value)
    }
    for name, value in constants_state.compute_dict(validate=True).items():
        uncertain = parse_uncertainty_format(value)
        if _has_uncertainty(uncertain):
            if name in uncertainties:
                raise ValueError(_dual_msg(f"名称冲突：{name}", f"symbol collision: {name}"))
            uncertainties[name] = uncertain
    return MappingProxyType(uncertainties)


def _category_membership(categories: SymbolCategories) -> dict[str, list[str]]:
    category_map: dict[str, list[str]] = {}
    for category_name, names in (
        ("unknown", categories.unknowns),
        ("data", categories.data_columns),
        ("constant", categories.constants),
        ("parameter", categories.parameters),
        ("target", categories.targets),
    ):
        for name in names:
            category_map.setdefault(name, []).append(category_name)
    return category_map


def _category_names(categories: SymbolCategories) -> tuple[str, ...]:
    return (
        categories.unknowns
        + categories.data_columns
        + categories.constants
        + categories.parameters
        + categories.targets
    )


def _normalize_names(names: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for name in names:
        clean = str(name).strip()
        if not clean:
            continue
        if clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    return tuple(normalized)


def _duplicate_names(scope: str, names: Iterable[str]) -> tuple[tuple[str, str], ...]:
    seen: set[str] = set()
    duplicates: list[tuple[str, str]] = []
    for name in names:
        clean = str(name).strip()
        if not clean:
            continue
        if clean in seen:
            duplicates.append((scope, clean))
            continue
        seen.add(clean)
    return tuple(duplicates)


def _as_uncertain_value(value: UncertainValue | object) -> UncertainValue:
    if isinstance(value, UncertainValue):
        return value
    return parse_uncertainty_format(str(value))


def _mp_from_value(value: object) -> mp.mpf:
    return cast(mp.mpf, mp.mpf(value))


def _reject_scope_collisions(
    row_values: Mapping[str, object],
    constants: Mapping[str, object],
    unknown_values: Mapping[str, object],
) -> None:
    seen: dict[str, str] = {}
    for scope, names in (
        ("data", row_values),
        ("constant", constants),
        ("unknown", unknown_values),
    ):
        for name in names:
            previous = seen.get(name)
            if previous is not None:
                raise ValueError(
                    _dual_msg(
                        f"名称冲突：{name} 同时出现在 {previous} 和 {scope}。",
                        f"symbol collision: {name} appears in both {previous} and {scope}.",
                    )
                )
            seen[name] = scope


def _has_uncertainty(value: UncertainValue) -> bool:
    return bool(value.uncertainty != 0)
