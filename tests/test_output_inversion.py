from __future__ import annotations

import multiprocessing
from collections.abc import Sequence

from mpmath import mp
import pytest
import sympy as sp

from fitting.implicit_model import ImplicitModelDefinition
import fitting.output_inversion as output_inversion
from fitting.output_inversion import detect_output_inversion


def _definition(output: str, constants: dict[str, str] | None = None) -> ImplicitModelDefinition:
    return ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="u",
        equation="d0 + d2/(n-u)^2",
        output_expression=output,
        parameters=("d0", "d2"),
        constants=constants or {},
    )


def test_detects_affine_output_as_generic_inversion() -> None:
    inversion = detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("4")}, mp.mpf("7")) == (mp.mpf("3"),)
        assert inversion.forward_row({"n": mp.mpf("4")}, mp.mpf("3")) == mp.mpf("7")


def test_serialized_symbolic_payload_accepts_float_precision_and_named_constants() -> None:
    expression = output_inversion._deserialize_sympy_expression("Add(Mul(pi, Symbol('u')), Float('1.2', precision=53))")

    assert sp.srepr(expression) == "Add(Mul(pi, Symbol('u')), Float('1.2', precision=53))"


def test_detects_inverse_square_output_with_uncertain_constants() -> None:
    definition = _definition(
        "CR*M/(M+1)/(n-u)^2",
        {"CR": "3.2898419602500(36)[+9]", "M": "7294.29954171(17)"},
    )

    inversion = detect_output_inversion(definition, precision=50)

    assert inversion is not None
    with mp.workdps(50):
        target = mp.mpf("204397210.721")
        candidates = inversion.candidates_row({"n": mp.mpf("4")}, target)
        assert candidates
        assert any(candidate < 0 for candidate in candidates)
        assert all(
            mp.almosteq(inversion.forward_row({"n": mp.mpf("4")}, candidate), target, rel_eps=mp.mpf("1e-30"))
            for candidate in candidates
        )


def test_rejects_output_that_depends_on_fit_parameter() -> None:
    assert detect_output_inversion(_definition("d0/(n-u)^2"), precision=50) is None


def test_dataset_numeric_inversion_handles_exp_output() -> None:
    inversion = detect_output_inversion(_definition("Exp[u]"), precision=50)
    assert inversion is not None
    assert not hasattr(inversion, "numeric_candidates_row")
    assert not hasattr(inversion, "_numeric_candidates_row")
    with mp.workdps(50):
        candidates = inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.e**2])
        assert candidates is not None
        solved = candidates[0][0]
        assert mp.almosteq(solved, mp.mpf("2"), rel_eps=mp.mpf("1e-30"))


def test_numeric_fallback_handles_monotonic_unsolved_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_symbolic_solution(*args: object, **kwargs: object) -> list[sp.Expr]:
        return []

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _no_symbolic_solution)
    inversion = detect_output_inversion(_definition("u^3 + u"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("2")) == ()
        candidates = inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.mpf("2")])
        assert candidates is not None
        assert len(candidates[0]) == 1
        assert mp.almosteq(inversion.forward_row({"n": mp.mpf("0")}, candidates[0][0]), mp.mpf("2"), rel_eps=mp.mpf("1e-30"))


def test_numeric_fallback_rejects_potentially_multibranch_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_symbolic_solution(*args: object, **kwargs: object) -> list[sp.Expr]:
        return []

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _no_symbolic_solution)
    inversion = detect_output_inversion(_definition("Sin[u]"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("0")) == ()
        assert inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.mpf("0")]) is None


def test_candidates_row_does_not_consume_numeric_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_symbolic_solution(*args: object, **kwargs: object) -> list[sp.Expr]:
        return []

    def _unexpected_findroot(*args: object, **kwargs: object) -> mp.mpf:
        raise AssertionError("candidates_row must remain symbolic-only")

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _no_symbolic_solution)
    monkeypatch.setattr(mp, "findroot", _unexpected_findroot)
    inversion = detect_output_inversion(_definition("u + Sin[u]"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("2")) == ()


def test_singular_output_derivative_rejects_candidate() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("0")) == ()
        assert inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.mpf("0")]) is None


def test_multibranch_inverse_preserves_output_valid_branches() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        candidates = inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("4"))
        assert set(candidates) == {mp.mpf("-2"), mp.mpf("2")}
        assert all(inversion.forward_row({"n": mp.mpf("0")}, candidate) == mp.mpf("4") for candidate in candidates)


def test_dataset_inverse_preserves_row_alignment_and_multibranch_tuples() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        rows = inversion.inverse_candidates(
            {"n": [mp.mpf("0"), mp.mpf("0")]},
            [mp.mpf("1"), mp.mpf("4")],
        )

    assert rows is not None
    assert len(rows) == 2
    assert set(rows[0]) == {mp.mpf("-1"), mp.mpf("1")}
    assert set(rows[1]) == {mp.mpf("-2"), mp.mpf("2")}


def test_dataset_inverse_fails_closed_when_middle_row_is_not_invertible() -> None:
    inversion = detect_output_inversion(_definition("Exp[u]"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert (
            inversion.inverse_candidates(
                {"n": [mp.mpf("0"), mp.mpf("0"), mp.mpf("0")]},
                [mp.e, mp.mpf("-1"), mp.e**2],
            )
            is None
        )


def test_inverse_square_output_preserves_both_algebraic_branches() -> None:
    inversion = detect_output_inversion(_definition("C/(n-u)^2", {"C": "4"}), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        candidates = inversion.candidates_row({"n": mp.mpf("4")}, mp.mpf("1"))
        assert set(candidates) == {mp.mpf("2"), mp.mpf("6")}
        assert all(inversion.forward_row({"n": mp.mpf("4")}, candidate) == mp.mpf("1") for candidate in candidates)


def test_forward_and_derivative_values_are_row_aligned_diagnostics() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        variable_data: dict[str, Sequence[mp.mpf]] = {"n": [mp.mpf("0"), mp.mpf("0")]}
        assert inversion.forward_values(variable_data, [mp.mpf("-2"), mp.mpf("3")]) == [mp.mpf("4"), mp.mpf("9")]
        assert inversion.derivative_values(variable_data, [mp.mpf("-2"), mp.mpf("3")]) == [mp.mpf("-4"), mp.mpf("6")]


def test_derivative_values_mark_singular_points_unusable() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        variable_data: dict[str, Sequence[mp.mpf]] = {"n": [mp.mpf("0"), mp.mpf("0")]}
        assert inversion.derivative_values(variable_data, [mp.mpf("0"), mp.mpf("2")]) == [None, mp.mpf("4")]


def test_exhausted_dataset_numeric_budget_fails_whole_inversion(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_symbolic_solution(*args: object, **kwargs: object) -> list[sp.Expr]:
        return []

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _no_symbolic_solution)
    monkeypatch.setattr(output_inversion, "_DATASET_NUMERIC_BUDGET_SECONDS", 0)
    inversion = detect_output_inversion(_definition("u^3 + u"), precision=50)

    assert inversion is not None
    with mp.workdps(50):
        assert inversion.candidates_row({"n": mp.mpf("0")}, mp.mpf("2")) == ()
        assert inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.mpf("2")]) is None


def test_inverse_candidates_validates_variable_lengths() -> None:
    inversion = detect_output_inversion(_definition("u^2"), precision=50)

    assert inversion is not None
    with pytest.raises(ValueError, match="自变量|independent"):
        inversion.inverse_candidates({"n": [mp.mpf("0")]}, [mp.mpf("1"), mp.mpf("4")])


def test_inversion_rejects_invalid_numeric_targets() -> None:
    cases = [
        ("Exp[u]", mp.mpf("-1")),
        ("CR*M/(M+1)/(n-u)^2", mp.mpf("0")),
        ("u^2 + 1", mp.mpf("0")),
        ("u", mp.inf),
    ]
    for output, target in cases:
        inversion = detect_output_inversion(
            _definition(output, {"CR": "3.2898419602500(36)[+9]", "M": "7294.29954171(17)"}),
            precision=50,
        )
        if inversion is None:
            continue
        with mp.workdps(50):
            assert inversion.inverse_candidates({"n": [mp.mpf("4")]}, [target]) is None


def test_symbolic_solve_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(*args: object, **kwargs: object) -> list[object]:
        raise TimeoutError("forced timeout")

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _timeout)

    assert detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50) is None


def test_symbolic_solve_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _failure(*args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("forced solve failure")

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _failure)

    assert detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50) is None


def test_symbolic_solve_none_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(output_inversion, "_solve_symbolic_candidates_in_worker", _timeout)

    assert detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50) is None


def test_symbolic_worker_too_many_candidates_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Connection:
        def close(self) -> None:
            return None

    class _Process:
        def start(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            return None

    class _Parent:
        def __init__(self) -> None:
            self._messages = [("ready", None), ("too_many", output_inversion._MAX_SYMBOLIC_CANDIDATES + 1)]

        def poll(self, timeout: float | None = None) -> bool:
            return bool(self._messages)

        def recv(self) -> tuple[str, object]:
            return self._messages.pop(0)

    class _Context:
        def Pipe(self, duplex: bool = True) -> tuple[_Parent, _Connection]:
            return _Parent(), _Connection()

        def Process(self, *args: object, **kwargs: object) -> _Process:
            return _Process()

    monkeypatch.setattr(output_inversion, "_symbolic_worker_context", lambda: _Context())

    assert (
        output_inversion._solve_symbolic_candidates_in_worker(
            "Symbol('u')",
            target_symbol_name="_datalab_target_y",
            implicit_symbol_name="u",
        )
        is None
    )


def test_symbolic_worker_error_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Connection:
        def close(self) -> None:
            return None

    class _Process:
        def start(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            return None

    class _Parent:
        def __init__(self) -> None:
            self._messages = [("ready", None), ("error", "forced")]

        def poll(self, timeout: float | None = None) -> bool:
            return bool(self._messages)

        def recv(self) -> tuple[str, object]:
            return self._messages.pop(0)

    class _Context:
        def Pipe(self, duplex: bool = True) -> tuple[_Parent, _Connection]:
            return _Parent(), _Connection()

        def Process(self, *args: object, **kwargs: object) -> _Process:
            return _Process()

    monkeypatch.setattr(output_inversion, "_symbolic_worker_context", lambda: _Context())

    assert (
        output_inversion._solve_symbolic_candidates_in_worker(
            "Symbol('u')",
            target_symbol_name="_datalab_target_y",
            implicit_symbol_name="u",
        )
        is None
    )


def test_symbolic_worker_unknown_status_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Connection:
        def close(self) -> None:
            return None

    class _Process:
        def start(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            return None

    class _Parent:
        def __init__(self) -> None:
            self._messages = [("ready", None), ("partial", ["Symbol('u')"])]

        def poll(self, timeout: float | None = None) -> bool:
            return bool(self._messages)

        def recv(self) -> tuple[str, object]:
            return self._messages.pop(0)

    class _Context:
        def Pipe(self, duplex: bool = True) -> tuple[_Parent, _Connection]:
            return _Parent(), _Connection()

        def Process(self, *args: object, **kwargs: object) -> _Process:
            return _Process()

    monkeypatch.setattr(output_inversion, "_symbolic_worker_context", lambda: _Context())

    assert (
        output_inversion._solve_symbolic_candidates_in_worker(
            "Symbol('u')",
            target_symbol_name="_datalab_target_y",
            implicit_symbol_name="u",
        )
        is None
    )


def test_symbolic_worker_unsupported_candidates_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unsupported(*args: object, **kwargs: object) -> list[object]:
        return [sp.Symbol("u"), object()]

    monkeypatch.setattr(sp, "solve", _unsupported)
    parent_conn, child_conn = multiprocessing.Pipe(duplex=True)

    output_inversion._symbolic_solve_worker(
        child_conn,
        "Symbol('u')",
        "_datalab_target_y",
        "u",
    )

    assert parent_conn.recv() == ("ready", None)
    status, _payload = parent_conn.recv()
    assert status == "unsupported"


def test_serialized_symbolic_payload_rejects_unknown_constructor() -> None:
    with pytest.raises(ValueError, match="Unsupported serialized symbolic"):
        output_inversion._deserialize_sympy_expression("__import__('os').system('echo no')")


def test_symbolic_worker_startup_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NeverReadyConnection:
        def close(self) -> None:
            return None

    class _NeverReadyProcess:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        def start(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def join(self, timeout: float | None = None) -> None:
            return None

    class _NeverReadyParent:
        def poll(self, timeout: float | None = None) -> bool:
            return False

    class _NeverReadyContext:
        def Pipe(self, duplex: bool = True) -> tuple[_NeverReadyParent, _NeverReadyConnection]:
            return _NeverReadyParent(), _NeverReadyConnection()

        def Process(self, *args: object, **kwargs: object) -> _NeverReadyProcess:
            return _NeverReadyProcess()

    monkeypatch.setattr(output_inversion, "_symbolic_worker_context", lambda: _NeverReadyContext())

    assert detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50) is None


def test_symbolic_worker_start_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Connection:
        def close(self) -> None:
            return None

    class _Process:
        def start(self) -> None:
            raise OSError("process start unavailable")

    class _Parent:
        def poll(self, timeout: float | None = None) -> bool:
            return False

    class _Context:
        def Pipe(self, duplex: bool = True) -> tuple[_Parent, _Connection]:
            return _Parent(), _Connection()

        def Process(self, *args: object, **kwargs: object) -> _Process:
            return _Process()

    monkeypatch.setattr(output_inversion, "_symbolic_worker_context", lambda: _Context())

    assert detect_output_inversion(_definition("C*u + B", {"C": "3", "B": "-2"}), precision=50) is None


def test_small_nonzero_output_derivative_is_invertible() -> None:
    inversion = detect_output_inversion(_definition("K*u", {"K": "1e-40"}), precision=80)

    assert inversion is not None
    with mp.workdps(80):
        target = mp.mpf("2e-40")
        candidates = inversion.candidates_row({"n": mp.mpf("0")}, target)
        assert len(candidates) == 1
        assert mp.almosteq(candidates[0], mp.mpf("2"), rel_eps=mp.mpf("1e-12"))


def test_compiled_inversion_callable_strips_ambient_builtins() -> None:
    u = sp.Symbol("u")
    func = output_inversion._harden_lambdify((u,), u + 1)

    assert func(mp.mpf("2")) == mp.mpf("3")
    assert func.__globals__["__builtins__"] == {}
