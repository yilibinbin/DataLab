"""Generic output inversion helpers for implicit fitting."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import multiprocessing as multiprocessing
from multiprocessing.connection import Connection
import time
from typing import Any, cast

from mpmath import mp
import sympy as sp

from fitting.implicit_model import ImplicitModelDefinition
from shared.bilingual import _dual_msg
from shared.precision import precision_guard
from shared.symbolic_math import parse_symbolic_expression
from shared.uncertainty import parse_numeric_value

_TARGET_SYMBOL_NAME = "_datalab_target_y"
_SYMBOLIC_SOLVE_TIMEOUT_SECONDS = 0.25
_SYMBOLIC_WORKER_STARTUP_TIMEOUT_SECONDS = 5.0
_DATASET_NUMERIC_BUDGET_SECONDS = 0.5
_MAX_SYMBOLIC_CANDIDATES = 8
_MAX_NUMERIC_CANDIDATES = 8
_MAX_NUMERIC_ATTEMPTS_PER_ROW = 16

_SYMPY_SREPR_CONSTRUCTORS: dict[str, object] = {
    "Add": sp.Add,
    "Float": sp.Float,
    "Integer": sp.Integer,
    "Mul": sp.Mul,
    "Pow": sp.Pow,
    "Rational": sp.Rational,
    "Symbol": sp.Symbol,
    "E": sp.E,
    "pi": sp.pi,
    "exp": sp.exp,
    "log": sp.log,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "asinh": sp.asinh,
    "acosh": sp.acosh,
    "atanh": sp.atanh,
    "sqrt": sp.sqrt,
    "Abs": sp.Abs,
}


class OutputInversion:
    """Validated output inversion API.

    Numeric row fallback stays private so production callers cannot bypass the
    dataset-level budget owned by inverse_candidates().
    """

    __slots__ = (
        "__numeric_candidates_row",
        "candidates_row",
        "derivative_row",
        "expression",
        "forward_row",
        "reason",
    )

    def __init__(
        self,
        *,
        expression: str,
        reason: str,
        candidates_row: Callable[[Mapping[str, mp.mpf], mp.mpf], tuple[mp.mpf, ...]],
        forward_row: Callable[[Mapping[str, mp.mpf], mp.mpf], mp.mpf],
        derivative_row: Callable[[Mapping[str, mp.mpf], mp.mpf], mp.mpf],
        numeric_candidates_row: Callable[[Mapping[str, mp.mpf], mp.mpf, "_InversionBudget"], tuple[mp.mpf, ...]],
    ) -> None:
        self.expression = expression
        self.reason = reason
        self.candidates_row = candidates_row
        self.forward_row = forward_row
        self.derivative_row = derivative_row
        self.__numeric_candidates_row = numeric_candidates_row

    def inverse_candidates(
        self,
        variable_data: Mapping[str, Sequence[mp.mpf]],
        targets: Sequence[mp.mpf],
    ) -> list[tuple[mp.mpf, ...]] | None:
        rows: list[tuple[mp.mpf, ...]] = []
        target_count = len(targets)
        for values in variable_data.values():
            if len(values) != target_count:
                raise ValueError(
                    _dual_msg(
                        "所有自变量的点数必须与因变量一致。",
                        "All independent variables must have the same length as targets.",
                    )
                )
        budget = _InversionBudget(seconds=_DATASET_NUMERIC_BUDGET_SECONDS)
        for index, target in enumerate(targets):
            variable_row = {name: mp.mpf(values[index]) for name, values in variable_data.items()}
            candidates = self.candidates_row(variable_row, mp.mpf(target))
            if not candidates:
                candidates = self.__numeric_candidates_row(variable_row, mp.mpf(target), budget)
            if not candidates:
                return None
            rows.append(candidates)
        return rows

    def derivative_values(
        self,
        variable_data: Mapping[str, Sequence[mp.mpf]],
        selected_values: Sequence[mp.mpf],
    ) -> list[mp.mpf | None]:
        values: list[mp.mpf | None] = []
        for index, selected in enumerate(selected_values):
            variable_row = {name: mp.mpf(row_values[index]) for name, row_values in variable_data.items()}
            try:
                value = self.derivative_row(variable_row, mp.mpf(selected))
            except (ArithmeticError, ValueError, ZeroDivisionError, OverflowError):
                values.append(None)
                continue
            values.append(value if _valid_candidate_derivative(value) else None)
        return values

    def forward_values(
        self,
        variable_data: Mapping[str, Sequence[mp.mpf]],
        selected_values: Sequence[mp.mpf],
    ) -> list[mp.mpf | None]:
        values: list[mp.mpf | None] = []
        for index, selected in enumerate(selected_values):
            variable_row = {name: mp.mpf(row_values[index]) for name, row_values in variable_data.items()}
            try:
                value = self.forward_row(variable_row, mp.mpf(selected))
            except (ArithmeticError, ValueError, ZeroDivisionError, OverflowError):
                values.append(None)
                continue
            values.append(value if _is_finite_real(value) else None)
        return values


@dataclass
class _InversionBudget:
    seconds: float
    started_at: float = field(default_factory=time.monotonic)

    def exhausted(self) -> bool:
        return time.monotonic() - self.started_at >= self.seconds


def detect_output_inversion(
    definition: ImplicitModelDefinition,
    *,
    precision: int | None = None,
) -> OutputInversion | None:
    dps = precision or int(mp.dps)
    try:
        parsed = _parse_output_expression(definition)
    except ValueError:
        return None
    expression, symbol_map = parsed
    free_names = {symbol.name for symbol in expression.free_symbols}
    parameter_names = set(definition.parameters)
    if free_names & parameter_names:
        return None

    implicit_name = definition.implicit_variable
    if implicit_name not in symbol_map:
        return None
    implicit_symbol = symbol_map[implicit_name]
    target_symbol = sp.Symbol(_TARGET_SYMBOL_NAME)

    substituted = _substitute_constants(expression, symbol_map, definition.constants, dps=dps)
    if implicit_symbol not in substituted.free_symbols:
        return None

    candidates = _solve_symbolic_candidates(
        substituted,
        target_symbol=target_symbol,
        implicit_symbol=implicit_symbol,
    )
    if candidates is None:
        return None
    x_symbols = [symbol_map[name] for name in definition.x_variables]
    compiled_candidates = [
        _harden_lambdify((*x_symbols, target_symbol), candidate)
        for candidate in candidates
    ]
    forward_func = _harden_lambdify((*x_symbols, implicit_symbol), substituted)
    derivative_expression = cast(sp.Expr, sp.diff(substituted, implicit_symbol))
    derivative_func = _harden_lambdify((*x_symbols, implicit_symbol), derivative_expression)
    allow_numeric_fallback = _allows_numeric_fallback(derivative_expression)

    def _row_values(row: Mapping[str, mp.mpf]) -> tuple[mp.mpf, ...]:
        return tuple(mp.mpf(row[name]) for name in definition.x_variables)

    def _forward_row(row: Mapping[str, mp.mpf], implicit_value: mp.mpf) -> mp.mpf:
        return _coerce_real_mpf(forward_func(*_row_values(row), mp.mpf(implicit_value)))

    def _derivative_row(row: Mapping[str, mp.mpf], implicit_value: mp.mpf) -> mp.mpf:
        return _coerce_real_mpf(derivative_func(*_row_values(row), mp.mpf(implicit_value)))

    def _candidates_row(row: Mapping[str, mp.mpf], target: mp.mpf) -> tuple[mp.mpf, ...]:
        with precision_guard(dps):
            target_value = mp.mpf(target)
            accepted: list[mp.mpf] = []
            for candidate_func in compiled_candidates:
                try:
                    candidate = _normalize_candidate(
                        _coerce_real_mpf(candidate_func(*_row_values(row), target_value))
                    )
                    if not _valid_candidate_derivative(_derivative_row(row, candidate)):
                        continue
                    reconstructed = _forward_row(row, candidate)
                except (ArithmeticError, ValueError, ZeroDivisionError, OverflowError):
                    continue
                if not _is_finite_real(reconstructed):
                    continue
                if _forward_matches_target(reconstructed, target_value):
                    _append_unique(accepted, candidate)
            return tuple(accepted)

    def _numeric_candidates_row(
        row: Mapping[str, mp.mpf],
        target: mp.mpf,
        budget: _InversionBudget,
    ) -> tuple[mp.mpf, ...]:
        if not allow_numeric_fallback:
            return ()
        return _numeric_candidates_for_row(
            forward_row=_forward_row,
            derivative_row=_derivative_row,
            row=row,
            target=target,
            budget=budget,
        )

    return OutputInversion(
        expression=definition.output_expression,
        reason="validated symbolic output inversion",
        candidates_row=_candidates_row,
        forward_row=_forward_row,
        derivative_row=_derivative_row,
        numeric_candidates_row=_numeric_candidates_row,
    )


def _parse_output_expression(definition: ImplicitModelDefinition) -> tuple[sp.Expr, dict[str, sp.Symbol]]:
    variable_names = [
        *definition.x_variables,
        definition.implicit_variable,
        *definition.constants,
        *definition.parameters,
    ]
    expression, symbol_map = parse_symbolic_expression(
        definition.output_expression,
        variables=_unique_names(variable_names),
    )
    expr = _rationalize_float_literals(cast(sp.Expr, expression))
    allowed = set(variable_names) | {"Pi", "E"}
    free_names = {symbol.name for symbol in expr.free_symbols}
    unknown = free_names - allowed
    if unknown:
        raise ValueError(f"Unknown output inversion symbols: {', '.join(sorted(unknown))}")
    return expr, symbol_map


def _rationalize_float_literals(expression: sp.Expr) -> sp.Expr:
    replacements = {atom: sp.Rational(str(atom)) for atom in expression.atoms(sp.Float)}
    if not replacements:
        return expression
    return cast(sp.Expr, expression.xreplace(replacements))


def _unique_names(names: Sequence[str]) -> list[str]:
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return unique


def _substitute_constants(
    expression: sp.Expr,
    symbol_map: Mapping[str, sp.Symbol],
    constants: Mapping[str, str],
    *,
    dps: int,
) -> sp.Expr:
    substitutions: dict[sp.Symbol, sp.Expr] = {}
    for name, value in constants.items():
        symbol = symbol_map.get(name)
        if symbol is None:
            continue
        numeric = parse_numeric_value(value)
        substitutions[symbol] = _sympy_numeric_constant(numeric, dps=dps)
    return cast(sp.Expr, expression.subs(substitutions))


def _sympy_numeric_constant(value: mp.mpf, *, dps: int) -> sp.Expr:
    text = mp.nstr(value, n=max(30, int(dps) + 10), strip_zeros=False)
    try:
        return sp.Rational(text)
    except ValueError:
        return sp.Float(text, max(30, int(dps) + 10))


def _solve_symbolic_candidates(
    expression: sp.Expr,
    *,
    target_symbol: sp.Symbol,
    implicit_symbol: sp.Symbol,
) -> list[sp.Expr] | None:
    try:
        candidates = _solve_symbolic_candidates_in_worker(
            sp.srepr(expression),
            target_symbol_name=target_symbol.name,
            implicit_symbol_name=implicit_symbol.name,
        )
        if candidates is None:
            return None
        return candidates
    except TimeoutError:
        return None
    except Exception:
        return None


def _solve_symbolic_candidates_in_worker(
    expression_payload: str,
    *,
    target_symbol_name: str,
    implicit_symbol_name: str,
) -> list[sp.Expr] | None:
    try:
        ctx = _symbolic_worker_context()
        parent_conn, child_conn = ctx.Pipe(duplex=True)
        process = ctx.Process(
            target=_symbolic_solve_worker,
            args=(child_conn, expression_payload, target_symbol_name, implicit_symbol_name),
        )
        started_at = time.monotonic()
        process.start()
    except Exception:
        return None
    child_conn.close()
    remaining_startup = max(0.0, _SYMBOLIC_WORKER_STARTUP_TIMEOUT_SECONDS - (time.monotonic() - started_at))
    if not parent_conn.poll(remaining_startup):
        process.terminate()
        process.join(timeout=0.1)
        return None
    status, payload = parent_conn.recv()
    if status != "ready":
        process.terminate()
        process.join(timeout=0.1)
        return None
    if not parent_conn.poll(_SYMBOLIC_SOLVE_TIMEOUT_SECONDS):
        process.terminate()
        process.join(timeout=0.1)
        return None
    status, payload = parent_conn.recv()
    process.join(timeout=0.1)
    if status == "too_many":
        return None
    if status in {"error", "unsupported"}:
        return None
    if status != "ok":
        return None
    if not isinstance(payload, list) or not all(isinstance(candidate, str) for candidate in payload):
        return None
    return [_deserialize_sympy_expression(candidate) for candidate in payload]


def _symbolic_solve_worker(
    conn: Connection,
    expression_payload: str,
    target_symbol_name: str,
    implicit_symbol_name: str,
) -> None:
    try:
        conn.send(("ready", None))
        expression = _deserialize_sympy_expression(expression_payload)
        target_symbol = sp.Symbol(target_symbol_name)
        implicit_symbol = sp.Symbol(implicit_symbol_name)
        raw_candidates = sp.solve(sp.Eq(expression, target_symbol), implicit_symbol)
        if not isinstance(raw_candidates, list):
            conn.send(("unsupported", repr(type(raw_candidates))))
            return
        candidates: list[sp.Expr] = []
        for candidate in raw_candidates:
            if not isinstance(candidate, sp.Expr) or candidate.has(sp.I):
                conn.send(("unsupported", repr(candidate)))
                return
            candidates.append(candidate)
        if len(candidates) > _MAX_SYMBOLIC_CANDIDATES:
            conn.send(("too_many", len(candidates)))
            return
        conn.send(("ok", [sp.srepr(candidate) for candidate in candidates]))
    except Exception as exc:
        conn.send(("error", repr(exc)))
    finally:
        conn.close()


def _symbolic_worker_context() -> Any:
    methods = multiprocessing.get_all_start_methods()
    if "forkserver" in methods:
        return multiprocessing.get_context("forkserver")
    if "fork" in methods:
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context("spawn")


def _harden_lambdify(args: Sequence[sp.Symbol], expression: sp.Expr) -> Callable[..., object]:
    func = sp.lambdify(tuple(args), expression, "mpmath")
    globals_dict = getattr(func, "__globals__", None)
    if isinstance(globals_dict, dict):
        globals_dict["__builtins__"] = {}
    return cast(Callable[..., object], func)


def _deserialize_sympy_expression(payload: str) -> sp.Expr:
    _validate_srepr_ast(payload)
    expression = eval(payload, {"__builtins__": {}}, _SYMPY_SREPR_CONSTRUCTORS)  # noqa: S307
    if not isinstance(expression, sp.Expr):
        raise ValueError("Serialized symbolic payload did not produce a SymPy expression.")
    return expression


def _validate_srepr_ast(payload: str) -> None:
    try:
        tree = ast.parse(payload, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid serialized symbolic payload.") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Expression | ast.Load | ast.keyword):
            continue
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Unsupported serialized symbolic payload.")
            if node.func.id not in _SYMPY_SREPR_CONSTRUCTORS:
                raise ValueError("Unsupported serialized symbolic constructor.")
            if node.keywords and (
                node.func.id != "Float"
                or len(node.keywords) != 1
                or node.keywords[0].arg != "precision"
                or not isinstance(node.keywords[0].value, ast.Constant)
                or not isinstance(node.keywords[0].value.value, int)
            ):
                raise ValueError("Keyword arguments are not supported in serialized symbolic payloads.")
            continue
        if isinstance(node, ast.Name):
            if node.id not in _SYMPY_SREPR_CONSTRUCTORS:
                raise ValueError("Unsupported serialized symbolic name.")
            continue
        if isinstance(node, ast.UnaryOp | ast.USub | ast.UAdd):
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float | str):
            continue
        raise ValueError("Unsupported serialized symbolic payload.")


def _coerce_real_mpf(value: object) -> mp.mpf:
    if isinstance(value, mp.mpc):
        if abs(value.imag) > mp.eps * max(1, abs(value.real)):
            raise ValueError("Complex inversion candidate.")
        return mp.mpf(value.real)
    return mp.mpf(value)


def _is_finite_real(value: mp.mpf) -> bool:
    return bool(mp.isfinite(value))


def _valid_candidate_derivative(value: mp.mpf) -> bool:
    if not _is_finite_real(value):
        return False
    return bool(value != 0)


def _allows_numeric_fallback(derivative_expression: sp.Expr) -> bool:
    try:
        simplified = sp.simplify(derivative_expression)
    except Exception:
        simplified = derivative_expression
    if simplified.is_positive is True or simplified.is_negative is True:
        return True
    if not simplified.free_symbols and simplified.is_zero is False:
        return True
    symbols = tuple(simplified.free_symbols)
    if len(symbols) == 1:
        try:
            zeros = sp.solveset(sp.Eq(simplified, 0), symbols[0], domain=sp.S.Reals)
            sample = simplified.subs(symbols[0], 0)
        except Exception:
            return False
        if zeros is sp.S.EmptySet and (sample.is_positive is True or sample.is_negative is True):
            return True
    return False


def _forward_matches_target(reconstructed: mp.mpf, target: mp.mpf) -> bool:
    tolerance = max(mp.mpf("1e-30"), mp.sqrt(mp.eps) * max(mp.mpf("1"), abs(target), abs(reconstructed)))
    return bool(abs(reconstructed - target) <= tolerance)


def _append_unique(values: list[mp.mpf], candidate: mp.mpf) -> None:
    if any(_forward_matches_target(existing, candidate) for existing in values):
        return
    values.append(candidate)


def _normalize_candidate(candidate: mp.mpf) -> mp.mpf:
    nearest_integer = mp.nint(candidate)
    tolerance = max(mp.mpf("1e-30"), mp.sqrt(mp.eps) * max(mp.mpf("1"), abs(candidate)))
    if abs(candidate - nearest_integer) <= tolerance:
        return mp.mpf(nearest_integer)
    return candidate


def _numeric_candidates_for_row(
    *,
    forward_row: Callable[[Mapping[str, mp.mpf], mp.mpf], mp.mpf],
    derivative_row: Callable[[Mapping[str, mp.mpf], mp.mpf], mp.mpf],
    row: Mapping[str, mp.mpf],
    target: mp.mpf,
    budget: _InversionBudget,
) -> tuple[mp.mpf, ...]:
    if budget.exhausted() or not _is_finite_real(target):
        return ()
    accepted: list[mp.mpf] = []

    def residual(value: mp.mpf) -> mp.mpf:
        return forward_row(row, mp.mpf(value)) - target

    attempts = 0
    for seed in _numeric_seed_values(row, target):
        if attempts >= _MAX_NUMERIC_ATTEMPTS_PER_ROW or budget.exhausted():
            break
        attempts += 1
        try:
            root = _normalize_candidate(_coerce_real_mpf(mp.findroot(residual, seed, tol=mp.sqrt(mp.eps), maxsteps=30)))
            if not _valid_candidate_derivative(derivative_row(row, root)):
                continue
            reconstructed = forward_row(row, root)
        except (ArithmeticError, ValueError, ZeroDivisionError, OverflowError):
            continue
        if _is_finite_real(reconstructed) and _forward_matches_target(reconstructed, target):
            _append_unique(accepted, root)
            if len(accepted) >= _MAX_NUMERIC_CANDIDATES:
                break
    return tuple(accepted)


def _numeric_seed_values(row: Mapping[str, mp.mpf], target: mp.mpf) -> list[mp.mpf]:
    seeds = [
        mp.mpf("0"),
        mp.mpf("1"),
        mp.mpf("-1"),
    ]
    if _is_finite_real(target):
        seeds.extend([target, -target])
    seeds.extend(mp.mpf(value) for value in row.values() if _is_finite_real(mp.mpf(value)))
    unique: list[mp.mpf] = []
    for seed in seeds:
        if not _is_finite_real(seed):
            continue
        if any(_forward_matches_target(existing, seed) for existing in unique):
            continue
        unique.append(seed)
    return unique[:_MAX_NUMERIC_ATTEMPTS_PER_ROW]
