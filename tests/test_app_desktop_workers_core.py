from __future__ import annotations

import ast
import pickle
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast

import mpmath as mp
import pytest

from data_extrapolation_latex_latest import ExtrapolationOptions, parse_uncertainty_format

import app_desktop.workers_core as workers_core
from app_desktop.workers_core import (
    CalcJob,
    FitBatchTask,
    FitJob,
    _deserialize_fit_job,
    _execute_calc_job,
    _execute_fit_job_payload,
    _execute_fit_job_payload_subprocess,
    _fit_job_requires_process_boundary,
    _serialize_fit_job,
)
from app_desktop.workers_qt import FitBatchWorker
from fitting.hp_fitter import FitResult
from fitting.implicit_model import (
    ImplicitEvaluationCache,
    ImplicitModelDefinition,
    ImplicitSolveOptions,
)
from fitting.model_parser import ModelSpecification
from shared.parallel_config import ParallelConfig, ParallelMode
from shared.parallel_backend import (
    KillableProcessTaskRunner,
    LocalWorkerBudget,
    current_parallel_depth,
)


_RAW_PAYLOAD_SCALAR_TYPES = (type(None), bool, int, float, str)
_FORBIDDEN_PAYLOAD_TYPES = (ModelSpecification, ImplicitEvaluationCache, mp.mpf)
_FIT_JOB_PAYLOAD_KEYS = {
    "model_type",
    "headers",
    "data_rows",
    "sigma_rows",
    "x_series",
    "y_series",
    "sigma_series",
    "weights",
    "variable_map",
    "variable_data",
    "target_series",
    "target_column",
    "model_expr",
    "parameter_config",
    "parameter_names",
    "template_expr",
    "template_params",
    "poly_degree",
    "inverse_min",
    "inverse_max",
    "pade_m",
    "pade_n",
    "auto_identifier",
    "precision",
    "generate_latex",
    "output_path",
    "use_dcolumn",
    "caption",
    "verbose",
    "render_plots",
    "latex_digits",
    "weighted",
    "label",
    "is_multidim",
    "implicit_definition",
    "timeout_seconds",
    "custom_constants",
    "parallel_config",
}
_FORBIDDEN_STATE_KEYS = {
    "cache",
    "current_point_index",
    "diagnostics",
    "evaluator",
    "implicit_cache",
    "model_specification",
    "point_index",
    "route_diagnostics",
    "warm_start",
    "warm_starts",
}
_PARALLEL_PRIMITIVES = {
    "concurrent.futures.ProcessPoolExecutor",
    "concurrent.futures.ThreadPoolExecutor",
    "multiprocessing.Pool",
    "multiprocessing.Process",
}
_PRODUCTION_PYTHON_PATHS = (
    "app_desktop",
    "app_web",
    "cli",
    "datalab_latex",
    "extrapolation_methods",
    "fitting",
    "shared",
    "data_extrapolation_gui.py",
    "data_extrapolation_latex_latest.py",
    "desktop_doc_loader.py",
    "formula_help.py",
    "statistics_utils.py",
)


def _small_self_consistent_fit_job(
    *,
    precision: int = 50,
    parallel_config: ParallelConfig | None = None,
) -> FitJob:
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("1") + mp.mpf("2") * x for x in x_series]
    data_rows = list(zip(x_series, y_series))
    sigma_rows: list[tuple[mp.mpf | None, ...]] = [(None, None) for _ in data_rows]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="u",
        parameters=("a", "b"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="1",
            tolerance="1e-30",
            max_iterations=50,
        ),
    )
    return FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="u",
        parameter_config={
            "a": {"initial": "0.8"},
            "b": {"initial": "1.8"},
        },
        parameter_names=["a", "b"],
        precision=precision,
        weighted=False,
        label="small-self-consistent",
        implicit_definition=definition,
        timeout_seconds=10.0,
        parallel_config=parallel_config or ParallelConfig(),
    )


def _custom_fit_job(*, precision: int) -> FitJob:
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3", "4"]]
    offset = mp.mpf("0.375")
    y_series = [mp.mpf("1.25") + mp.mpf("2.5") * x + offset for x in x_series]
    return FitJob(
        model_type="custom",
        headers=["x", "y"],
        data_rows=list(zip(x_series, y_series)),
        sigma_rows=[(None, None) for _ in x_series],
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="a*x + b + offset",
        parameter_config={
            "a": {"initial": "2.0"},
            "b": {"initial": "1.0"},
        },
        parameter_names=["a", "b"],
        precision=precision,
        weighted=False,
        label=f"custom-equivalence-{precision}",
        custom_constants={"offset": offset},
        parallel_config=ParallelConfig(mode=ParallelMode.SERIAL),
    )


def _general_self_consistent_fit_job(
    *,
    precision: int,
    data_sigmas: bool = False,
) -> FitJob:
    x_series = [mp.mpf(v) for v in ["1", "2", "3", "4", "5"]]
    y_series = [(mp.mpf("0.2") + mp.mpf("0.45") * x) ** 2 for x in x_series]
    sigma_series = [mp.mpf("0.01") for _ in y_series] if data_sigmas else [None] * len(y_series)
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="u*u",
        parameters=("a", "b"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-20",
            max_iterations=40,
        ),
    )
    return FitJob(
        model_type="self_consistent",
        headers=["x", "y"],
        data_rows=list(zip(x_series, y_series)),
        sigma_rows=[(None, sigma) for sigma in sigma_series],
        x_series=x_series,
        y_series=y_series,
        sigma_series=sigma_series,
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="u*u",
        parameter_config={
            "a": {"initial": "0.18"},
            "b": {"initial": "0.42"},
        },
        parameter_names=["a", "b"],
        precision=precision,
        weighted=False,
        label=f"self-consistent-equivalence-{precision}",
        implicit_definition=definition,
        timeout_seconds=20.0,
        parallel_config=ParallelConfig(mode=ParallelMode.SERIAL),
    )


def _seed_hint_self_consistent_fit_job() -> FitJob:
    n_series = [mp.mpf("4"), mp.mpf("5"), mp.mpf("6"), mp.mpf("7")]
    delta_series = [mp.mpf("-0.01"), mp.mpf("-0.011"), mp.mpf("-0.012"), mp.mpf("-0.0125")]
    target_series = [
        mp.mpf("100") / (n - delta) ** 2
        for n, delta in zip(n_series, delta_series, strict=True)
    ]
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0",
        output_expression="R/(n-delta)^2",
        parameters=("d0",),
        constants={"R": "100"},
        solve_options=ImplicitSolveOptions(
            method="fixed_point",
            initial="0",
            tolerance="1e-30",
            max_iterations=20,
        ),
    )
    return FitJob(
        model_type="self_consistent",
        headers=["n", "E"],
        data_rows=list(zip(n_series, target_series)),
        sigma_rows=[(None, None) for _ in n_series],
        x_series=n_series,
        y_series=target_series,
        sigma_series=[None] * len(target_series),
        weights=None,
        variable_map={"n": "n"},
        variable_data={"n": n_series},
        target_series=target_series,
        target_column="E",
        model_expr="R/(n-delta)^2",
        parameter_config={"d0": {"initial": "-0.012"}},
        parameter_names=["d0"],
        precision=50,
        weighted=False,
        label="self-consistent-seed-hint-equivalence",
        implicit_definition=definition,
        timeout_seconds=20.0,
        parallel_config=ParallelConfig(mode=ParallelMode.SERIAL),
    )


def _mp_almosteq(left: mp.mpf, right: mp.mpf, *, abs_eps: str = "1e-18") -> bool:
    return bool(mp.almosteq(left, right, abs_eps=mp.mpf(abs_eps), rel_eps=mp.mpf(abs_eps)))


def _assert_mpf_sequence_equivalent(
    left: list[mp.mpf],
    right: list[mp.mpf],
    *,
    abs_eps: str = "1e-18",
) -> None:
    assert len(left) == len(right)
    for index, (left_value, right_value) in enumerate(zip(left, right, strict=True)):
        assert _mp_almosteq(left_value, right_value, abs_eps=abs_eps), (
            index,
            left_value,
            right_value,
        )


def _assert_mpf_mapping_equivalent(
    left: dict[str, mp.mpf],
    right: dict[str, mp.mpf],
    *,
    abs_eps: str = "1e-18",
) -> None:
    assert set(left) == set(right)
    for key in sorted(left):
        assert _mp_almosteq(left[key], right[key], abs_eps=abs_eps), (
            key,
            left[key],
            right[key],
        )


def _normalize_details_for_equivalence(value: object) -> object:
    if isinstance(value, mp.mpf):
        return mp.nstr(value, 50)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, dict):
        return {
            str(key): _normalize_details_for_equivalence(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        return [_normalize_details_for_equivalence(item) for item in value]
    return value


def _assert_fit_result_equivalent(
    serial: FitResult,
    process: FitResult,
    *,
    abs_eps: str = "1e-18",
) -> None:
    _assert_mpf_mapping_equivalent(serial.params, process.params, abs_eps=abs_eps)
    _assert_mpf_mapping_equivalent(serial.param_errors, process.param_errors, abs_eps=abs_eps)
    _assert_mpf_mapping_equivalent(serial.param_errors_stat, process.param_errors_stat, abs_eps=abs_eps)
    _assert_mpf_mapping_equivalent(serial.param_errors_sys, process.param_errors_sys, abs_eps=abs_eps)
    _assert_mpf_mapping_equivalent(serial.param_errors_total, process.param_errors_total, abs_eps=abs_eps)
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "rmse", "r2"):
        assert _mp_almosteq(getattr(serial, attr), getattr(process, attr), abs_eps=abs_eps), attr
    _assert_mpf_sequence_equivalent(serial.fitted_curve, process.fitted_curve, abs_eps=abs_eps)
    _assert_mpf_sequence_equivalent(serial.residuals, process.residuals, abs_eps=abs_eps)
    assert len(serial.covariance) == len(process.covariance)
    for serial_row, process_row in zip(serial.covariance, process.covariance, strict=True):
        _assert_mpf_sequence_equivalent(serial_row, process_row, abs_eps=abs_eps)
    assert _normalize_details_for_equivalence(serial.details) == _normalize_details_for_equivalence(process.details)


def _assert_implicit_metadata_contract(result: FitResult) -> dict[str, Any]:
    assert "implicit_strategy" in result.details
    assert "optimizer_backend" in result.details
    diagnostics = result.details.get("implicit_diagnostics")
    assert isinstance(diagnostics, dict)
    assert isinstance(diagnostics.get("points_solved"), int)
    assert isinstance(diagnostics.get("seed_sources"), dict)
    assert isinstance(diagnostics.get("seed_attempts"), list)
    for attempt in diagnostics["seed_attempts"]:
        assert isinstance(attempt, dict)
        assert "point_index" in attempt
        assert "source" in attempt
        assert "success" in attempt
    return diagnostics


def _assert_configured_seed_state_is_not_leaked(result: FitResult) -> None:
    diagnostics = _assert_implicit_metadata_contract(result)
    points_solved = diagnostics["points_solved"]
    seed_sources = diagnostics["seed_sources"]
    seed_attempts = diagnostics["seed_attempts"]
    assert points_solved > 0
    assert seed_sources == {"configured": points_solved}
    assert all(attempt["source"] == "configured" for attempt in seed_attempts)
    assert {attempt["point_index"] for attempt in seed_attempts} <= {0, 1, 2, 3, 4}


def _depth_probe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "payload": payload,
        "env_depth": os.environ.get("DATALAB_PARALLEL_DEPTH"),
        "current_depth": current_parallel_depth(),
    }


def _implicit_seed_diagnostic_probe(payload: dict[str, str]) -> dict[str, object]:
    from fitting.implicit_model import build_implicit_model_specification
    import fitting.implicit_model as implicit_model
    from fitting.implicit_seed_hints import ImplicitSeedHint

    mode = payload["mode"]
    original_solve = implicit_model._solve_from_seed
    calls = 0

    def fail_selected_configured_seed(
        rhs: Callable[[mp.mpf], mp.mpf],
        seed: mp.mpf,
        options: ImplicitSolveOptions,
        tol: mp.mpf,
    ) -> tuple[mp.mpf, int, bool, mp.mpf]:
        nonlocal calls
        calls += 1
        if (mode == "warm" and calls == 2) or (mode == "hint" and calls == 1):
            raise ValueError("forced configured seed failure")
        return original_solve(rhs, seed, options, tol)

    implicit_model._solve_from_seed = fail_selected_configured_seed
    try:
        if mode == "warm":
            definition = ImplicitModelDefinition(
                x_variables=("x",),
                implicit_variable="u",
                equation="0.1*x + a",
                output_expression="u",
                parameters=("a",),
                solve_options=ImplicitSolveOptions(
                    method="fixed_point",
                    initial="0",
                    tolerance="1e-30",
                    max_iterations=5,
                ),
            )
            spec = build_implicit_model_specification(definition)
            params = {"a": mp.mpf("1")}
            for point_index, x_value in enumerate((mp.mpf("3"), mp.mpf("4"))):
                getattr(spec, "set_implicit_point_index")(point_index)
                spec.evaluate({"x": x_value}, params)
        elif mode == "hint":
            definition = ImplicitModelDefinition(
                x_variables=("x",),
                implicit_variable="u",
                equation="u**2 - 4",
                output_expression="u",
                parameters=("a",),
                solve_options=ImplicitSolveOptions(
                    method="root",
                    initial="0",
                    tolerance="1e-30",
                    max_iterations=20,
                ),
            )
            hint = ImplicitSeedHint(
                reason="test rescue branch",
                candidates=lambda _variables, _target: (mp.mpf("3"),),
            )
            spec = build_implicit_model_specification(
                definition,
                target_data=[mp.mpf("2")],
                seed_hint=hint,
            )
            getattr(spec, "set_implicit_point_index")(0)
            spec.evaluate({"x": mp.mpf("0")}, {"a": mp.mpf("0")})
        else:
            raise ValueError(f"Unknown seed diagnostic probe mode: {mode}")
    finally:
        implicit_model._solve_from_seed = original_solve

    diagnostics = getattr(spec, "implicit_diagnostics")
    return {
        "points_solved": int(diagnostics.points_solved),
        "warm_start_uses": int(diagnostics.warm_start_uses),
        "seed_sources": dict(diagnostics.seed_sources),
        "attempt_sources": [
            str(attempt["source"])
            for attempt in diagnostics.seed_attempts
        ],
        "attempt_success": [
            bool(attempt["success"])
            for attempt in diagnostics.seed_attempts
        ],
        "point_indexes": [
            int(attempt["point_index"])
            for attempt in diagnostics.seed_attempts
        ],
    }


def _assert_raw_serializable_payload(value: object, *, path: str = "payload") -> None:
    assert not isinstance(value, _FORBIDDEN_PAYLOAD_TYPES), path
    assert not callable(value), path
    if isinstance(value, _RAW_PAYLOAD_SCALAR_TYPES):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_raw_serializable_payload(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"{path} key {key!r}"
            assert key not in _FORBIDDEN_STATE_KEYS, f"{path}.{key}"
            _assert_raw_serializable_payload(item, path=f"{path}.{key}")
        return
    pytest.fail(f"{path} contains non-raw payload value {type(value)!r}: {value!r}")


def _collect_import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"multiprocessing", "concurrent.futures"}:
                    local = alias.asname or alias.name
                    aliases[local] = alias.name
                    if alias.asname is None and "." in alias.name:
                        aliases[alias.name.split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                local = alias.asname or alias.name
                if node.module == "multiprocessing" and alias.name in {
                    "Pool",
                    "Process",
                    "get_context",
                }:
                    aliases[local] = f"multiprocessing.{alias.name}"
                elif node.module == "concurrent.futures" and alias.name in {
                    "ProcessPoolExecutor",
                    "ThreadPoolExecutor",
                }:
                    aliases[local] = f"concurrent.futures.{alias.name}"
                elif node.module == "concurrent" and alias.name == "futures":
                    aliases[local] = "concurrent.futures"
    return aliases


def _call_qualname(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _call_qualname(node.value, aliases)
        return f"{base}.{node.attr}" if base is not None else node.attr
    if isinstance(node, ast.Call):
        func = _call_qualname(node.func, aliases)
        return f"{func}()" if func is not None else None
    return None


def _collect_multiprocessing_context_names(
    tree: ast.AST,
    aliases: dict[str, str],
) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if _call_qualname(node.value, aliases) != "multiprocessing.get_context()":
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def _is_forbidden_parallel_call(qualname: str) -> bool:
    if qualname in _PARALLEL_PRIMITIVES:
        return True
    if qualname in {
        "multiprocessing.get_context().Pool",
        "multiprocessing.get_context().Process",
    }:
        return True
    if (
        qualname.endswith((".get_context().Pool", ".get_context().Process"))
        and qualname.startswith("multiprocessing.")
    ):
        return True
    return False


def _tracked_production_python_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--", *_PRODUCTION_PYTHON_PATHS],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        root / path
        for path in result.stdout.splitlines()
        if path.endswith(".py")
    ]


def test_no_ad_hoc_parallel_primitives_outside_shared_backend() -> None:
    root = Path(__file__).resolve().parents[1]
    allowed = {root / "shared" / "parallel_backend.py"}
    violations: list[str] = []
    for path in sorted(_tracked_production_python_files(root)):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        aliases = _collect_import_aliases(tree)
        context_names = _collect_multiprocessing_context_names(tree, aliases)
        get_context_names = {
            name
            for name, target in aliases.items()
            if target == "multiprocessing.get_context"
        }
        process_names = {
            name for name, target in aliases.items() if target == "multiprocessing.Process"
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            qualname = _call_qualname(node.func, aliases)
            if qualname is not None and _is_forbidden_parallel_call(qualname):
                violations.append(
                    f"{path.relative_to(root)}:{node.lineno}: {qualname}"
                )
            if isinstance(node.func, ast.Name) and node.func.id in process_names:
                violations.append(
                    f"{path.relative_to(root)}:{node.lineno}: multiprocessing.Process"
                )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in {"Pool", "Process"}
            ):
                if (
                    isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Name)
                    and node.func.value.func.id in get_context_names
                ):
                    violations.append(
                        f"{path.relative_to(root)}:{node.lineno}: "
                        f"multiprocessing.get_context().{node.func.attr}"
                    )
                if (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id in context_names
                ):
                    violations.append(
                        f"{path.relative_to(root)}:{node.lineno}: "
                        f"multiprocessing.get_context().{node.func.attr}"
                    )

    assert violations == []


def test_parallel_boundary_guard_detects_alias_and_context_idioms() -> None:
    source = """
import concurrent.futures
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor as Threads
from concurrent import futures
from multiprocessing import Process, get_context

concurrent.futures.ProcessPoolExecutor()
futures.ProcessPoolExecutor()
mp.Process()
Threads()
Process()
get_context("spawn").Process()
ctx = mp.get_context("spawn")
ctx.Process()
ctx.Pool()
"""
    tree = ast.parse(source)
    aliases = _collect_import_aliases(tree)
    context_names = _collect_multiprocessing_context_names(tree, aliases)
    violations: list[str] = []
    get_context_names = {
        name
        for name, target in aliases.items()
        if target == "multiprocessing.get_context"
    }
    process_names = {
        name for name, target in aliases.items() if target == "multiprocessing.Process"
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        qualname = _call_qualname(node.func, aliases)
        if qualname is not None and _is_forbidden_parallel_call(qualname):
            violations.append(qualname)
        if isinstance(node.func, ast.Name) and node.func.id in process_names:
            violations.append("multiprocessing.Process")
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"Pool", "Process"}:
            if (
                isinstance(node.func.value, ast.Call)
                and isinstance(node.func.value.func, ast.Name)
                and node.func.value.func.id in get_context_names
            ):
                violations.append(f"multiprocessing.get_context().{node.func.attr}")
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id in context_names
            ):
                violations.append(f"multiprocessing.get_context().{node.func.attr}")

    assert set(violations) >= {
        "concurrent.futures.ProcessPoolExecutor",
        "concurrent.futures.ThreadPoolExecutor",
        "multiprocessing.Process",
        "multiprocessing.get_context().Process",
        "multiprocessing.get_context().Pool",
    }


def test_execute_fit_job_payload_poly_recovers_linear_params():
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]

    job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
        poly_degree=1,
        precision=80,
        weighted=False,
        label="unit-test",
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result
    assert fit is not None
    assert mp.almosteq(fit.params["b0"], mp.mpf("1"), abs_eps=mp.mpf("1e-50"))
    assert mp.almosteq(fit.params["b1"], mp.mpf("2"), abs_eps=mp.mpf("1e-50"))


def test_execute_fit_job_payload_self_consistent_wires_definition_and_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    x_series = [mp.mpf(v) for v in ["0", "1", "2"]]
    y_series = [mp.mpf(v) for v in ["0.3", "0.4", "0.5"]]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0.3",
            tolerance="1e-36",
        ),
    )
    calls: dict[str, object] = {}

    class FakeFitRunner:
        def fit(
            self,
            problem: object,
            variable_data: dict[str, list[mp.mpf]],
            target_series: list[mp.mpf],
            *,
            precision: int,
            weights: list[mp.mpf] | None = None,
            data_sigmas: list[mp.mpf | None] | None = None,
        ) -> FitResult:
            calls["problem"] = problem
            calls["variable_data"] = variable_data
            calls["target_series"] = target_series
            calls["precision"] = precision
            calls["weights"] = weights
            calls["data_sigmas"] = data_sigmas
            return FitResult(
                params={"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.4")},
                param_errors={},
                chi2=mp.mpf("0"),
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[],
                fitted_curve=list(target_series),
                covariance=[],
                details={
                    "implicit_diagnostics": {
                        "points_solved": 7,
                        "root_fallbacks": 2,
                        "max_iterations_used": 5,
                        "max_residual": "1.0e-42",
                    }
                },
            )

    monkeypatch.setattr(workers_core, "FitRunner", FakeFitRunner)

    job = FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="",
        parameter_config={
            "a": {"initial": 0.1},
            "b": {"initial": 0.2},
            "c": {"initial": 0.4},
        },
        parameter_names=["a", "b", "c"],
        precision=30,
        weighted=False,
        label="self-consistent-test",
        implicit_definition=definition,
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result

    problem = calls["problem"]
    assert getattr(problem, "implicit_definition") is definition
    assert getattr(problem, "expression") == "u"
    assert getattr(problem, "variables") == ("x",)
    assert getattr(problem, "target_name") == "u"
    assert getattr(problem, "parameter_config") == job.parameter_config
    assert calls["variable_data"] == {"x": x_series}
    assert calls["target_series"] == y_series
    assert calls["precision"] == 30
    assert calls["weights"] is None
    assert calls["data_sigmas"] == [None] * len(y_series)
    assert {name: float(value) for name, value in fit.params.items()} == {
        "a": 0.1,
        "b": 0.2,
        "c": 0.4,
    }
    assert payload.expression == "u"
    details = fit.details
    assert details["implicit_variable"] == "u"
    assert details["equation"] == "a + b*Cos[u] + c*x"
    assert details["output_expression"] == "u"
    assert details["implicit_diagnostics"] == {
        "points_solved": 7,
        "root_fallbacks": 2,
        "max_iterations_used": 5,
        "max_residual": "1.0e-42",
    }


def test_execute_fit_job_payload_self_consistent_requires_definition() -> None:
    with pytest.raises(ValueError, match="requires an implicit definition"):
        _execute_fit_job_payload(
            FitJob(
                model_type="self_consistent",
                headers=["x", "u"],
                data_rows=[],
                sigma_rows=[],
                x_series=[],
                y_series=[],
                sigma_series=[],
                weights=None,
                variable_map={"x": "x"},
                variable_data={"x": []},
                target_series=[],
                target_column="u",
                model_expr="",
                parameter_config={"a": {"initial": 0.1}},
                parameter_names=["a"],
                precision=30,
                weighted=False,
                label="missing-definition-test",
            )
        )


def test_execute_fit_job_payload_self_consistent_observed_implicit_linear_fast_path() -> None:
    with mp.workdps(80):
        n_series = [mp.mpf(n) for n in range(12, 22)]
        params = {
            "d0": mp.mpf("-0.012"),
            "d2": mp.mpf("0.0075"),
            "d4": mp.mpf("0.013"),
            "d6": mp.mpf("0.021"),
            "d8": mp.mpf("-0.11"),
        }
        y_series = [
            params["d0"]
            + params["d2"] / n**2
            + params["d4"] / n**4
            + params["d6"] / n**6
            + params["d8"] / n**8
            for n in n_series
        ]
    sigma_series = [mp.mpf("1e-9")] * len(y_series)
    weights = [1 / (sigma * sigma) for sigma in sigma_series]
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/n**2 + d4/n**4 + d6/n**6 + d8/n**8",
        output_expression="delta",
        parameters=("d0", "d2", "d4", "d6", "d8"),
        constants={},
        solve_options=ImplicitSolveOptions(method="root", initial="0", tolerance="1e-40"),
    )
    job = FitJob(
        model_type="self_consistent",
        headers=["n", "delta"],
        data_rows=list(zip(n_series, y_series)),
        sigma_rows=[(None, sigma) for sigma in sigma_series],
        x_series=n_series,
        y_series=y_series,
        sigma_series=sigma_series,
        weights=weights,
        variable_map={"n": "n"},
        variable_data={"n": n_series, "delta": y_series},
        target_series=y_series,
        target_column="delta",
        model_expr="delta",
        parameter_config={name: {"initial": "0"} for name in params},
        parameter_names=list(params),
        precision=80,
        weighted=True,
        label="observed-implicit-linear",
        implicit_definition=definition,
    )

    payload = _execute_fit_job_payload(job)

    assert payload.fit_result.details["implicit_fast_path"] == "observed_implicit_linear"
    assert payload.fit_result.details["implicit_diagnostics"]["points_solved"] == 0
    for name, expected in params.items():
        assert mp.almosteq(payload.fit_result.params[name], expected, abs_eps=mp.mpf("1e-30"))


def test_self_consistent_fit_job_is_marked_for_process_boundary() -> None:
    job = _small_self_consistent_fit_job()
    assert _fit_job_requires_process_boundary(job) is True

    direct_job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=[],
        sigma_rows=[],
        x_series=[],
        y_series=[],
        sigma_series=[],
        weights=None,
        variable_map={},
        variable_data={},
        target_series=[],
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
    )
    assert _fit_job_requires_process_boundary(direct_job) is False


def test_fit_job_default_parallel_config_has_no_removed_backend_gates() -> None:
    job = _small_self_consistent_fit_job()

    assert isinstance(job.parallel_config, ParallelConfig)
    assert not hasattr(job.parallel_config, "enable_new_implicit_backend")
    assert not hasattr(job.parallel_config, "enable_new_auto_fit_backend")


def test_self_consistent_fit_job_payload_is_spawn_picklable() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    assert "enable_new_implicit_backend" not in payload["parallel_config"]
    assert "enable_new_auto_fit_backend" not in payload["parallel_config"]
    roundtrip = pickle.loads(pickle.dumps(payload))
    restored = _deserialize_fit_job(roundtrip)

    assert restored.model_type == "self_consistent"
    assert restored.implicit_definition is not None
    assert restored.implicit_definition.equation == "a + b*x"
    assert restored.implicit_definition.solve_options.method == "root"
    assert restored.timeout_seconds == 10.0
    assert restored.parallel_config.process_start_method == "spawn"
    assert not hasattr(restored.parallel_config, "enable_new_implicit_backend")
    assert not hasattr(restored.parallel_config, "enable_new_auto_fit_backend")


def test_fit_job_payload_contains_only_raw_serializable_inputs() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())

    assert set(payload) == _FIT_JOB_PAYLOAD_KEYS
    _assert_raw_serializable_payload(payload)


def test_fit_job_payload_contract_covers_full_serialized_field_surface() -> None:
    job = _small_self_consistent_fit_job()
    high_precision_constant = mp.mpf(
        "1.2345678901234567890123456789012345678901234567890123456789"
    )
    sigmas = [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3"), mp.mpf("0.4")]
    job.sigma_rows = [(mp.mpf("0.01"), sigma) for sigma in sigmas]
    job.sigma_series = sigmas
    job.weights = [1 / (sigma * sigma) for sigma in sigmas]
    job.parameter_config = {
        "a": {
            "initial": mp.mpf("0.8"),
            "min": mp.mpf("-10"),
            "max": mp.mpf("10"),
            "fixed": False,
        },
        "b": {
            "initial": mp.mpf("1.8"),
            "bounds": (mp.mpf("-5"), mp.mpf("5")),
        },
    }
    job.template_expr = "c0 + c1*x"
    job.template_params = {
        "c0": {"initial": mp.mpf("1.0")},
        "nested": [mp.mpf("2.0"), (mp.mpf("3.0"), None)],
    }
    assert job.implicit_definition is not None
    job.implicit_definition.constants["offset"] = high_precision_constant
    job.custom_constants = {"scale": mp.mpf("2.5")}  # type: ignore[dict-item]
    job.generate_latex = True
    job.output_path = "fit-output.tex"
    job.caption = "Fit output"
    job.verbose = True
    job.render_plots = False
    job.weighted = True

    payload = _serialize_fit_job(job)

    assert set(payload) == _FIT_JOB_PAYLOAD_KEYS
    _assert_raw_serializable_payload(payload)
    assert mp.almosteq(
        mp.mpf(payload["parameter_config"]["a"]["initial"]),
        mp.mpf("0.8"),
        abs_eps=mp.mpf("1e-15"),
    )
    assert [mp.mpf(value) for value in payload["parameter_config"]["b"]["bounds"]] == [
        mp.mpf("-5"),
        mp.mpf("5"),
    ]
    assert mp.mpf(payload["template_params"]["nested"][0]) == mp.mpf("2")
    assert mp.mpf(payload["template_params"]["nested"][1][0]) == mp.mpf("3")
    assert payload["template_params"]["nested"][1][1] is None
    assert mp.almosteq(
        mp.mpf(payload["implicit_definition"]["constants"]["offset"]),
        high_precision_constant,
        abs_eps=mp.mpf("1e-85"),
    )
    assert mp.mpf(payload["custom_constants"]["scale"]) == mp.mpf("2.5")
    assert [mp.mpf(value) for value in payload["sigma_series"]] == sigmas
    assert payload["weights"] is not None
    assert [mp.mpf(value) for value in payload["weights"]] == [
        1 / (sigma * sigma)
        for sigma in sigmas
    ]


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(lambda: None, id="callable"),
        pytest.param(ImplicitEvaluationCache(), id="implicit-cache"),
        pytest.param(
            ModelSpecification(
                expression="x",
                variables=["x"],
                parameters=[],
                constants={},
                evaluate_func=lambda variables, _params: variables[0],
                gradient_funcs={},
            ),
            id="model-specification",
        ),
    ],
)
def test_fit_job_payload_rejects_non_raw_parameter_objects(bad_value: object) -> None:
    job = _small_self_consistent_fit_job()
    job.parameter_config = {"a": {"initial": bad_value}}

    with pytest.raises(TypeError, match="Unsupported fit-job payload value"):
        _serialize_fit_job(job)


def test_fit_job_payload_rejects_non_raw_implicit_solve_option() -> None:
    job = _small_self_consistent_fit_job()
    assert job.implicit_definition is not None
    job.implicit_definition = replace(
        job.implicit_definition,
        solve_options=replace(
            job.implicit_definition.solve_options,
            initial=ImplicitEvaluationCache(),  # type: ignore[arg-type]
        ),
    )

    with pytest.raises(TypeError, match="Unsupported fit-job payload value"):
        _serialize_fit_job(job)


def test_fit_job_payload_round_trips_weight_values() -> None:
    job = _small_self_consistent_fit_job()
    job.weights = [mp.mpf("1.25"), mp.mpf("2.5"), mp.mpf("5"), mp.mpf("10")]

    restored = _deserialize_fit_job(_serialize_fit_job(job))

    assert restored.weights == job.weights


def test_fit_job_payload_rejects_none_weight_values_at_serialize_time() -> None:
    job = _small_self_consistent_fit_job()
    job.weights = [mp.mpf("1"), None]  # type: ignore[list-item]

    with pytest.raises(TypeError, match="weight values must not be None"):
        _serialize_fit_job(job)


def test_fit_job_payload_rejects_none_weight_values() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["weights"] = ["1", None]

    with pytest.raises(TypeError, match="weight payload values must not be None"):
        _deserialize_fit_job(payload)


def test_stale_fit_job_payload_false_backend_gates_are_ignored() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"]["enable_new_implicit_backend"] = False
    payload["parallel_config"]["enable_new_auto_fit_backend"] = True

    restored = _deserialize_fit_job(payload)

    assert not hasattr(restored.parallel_config, "enable_new_implicit_backend")
    assert not hasattr(restored.parallel_config, "enable_new_auto_fit_backend")


def test_self_consistent_fit_subprocess_uses_killable_runner_and_forwards_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    calls: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, Any]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, Any]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return workers_core._serialize_fit_result_payload(
                workers_core.FitResultPayload(
                    job=job,
                    fit_result=FitResult(
                        params={"a": mp.mpf("1"), "b": mp.mpf("2")},
                        param_errors={},
                        chi2=mp.mpf("0"),
                        reduced_chi2=mp.mpf("0"),
                        aic=mp.mpf("0"),
                        bic=mp.mpf("0"),
                        r2=mp.mpf("1"),
                        rmse=mp.mpf("0"),
                        residuals=[],
                        fitted_curve=[],
                        covariance=[],
                        details={},
                    ),
                    expression="u",
                    logs=[],
                    warnings=[],
                )
            )

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FakeRunner)

    result = _execute_fit_job_payload_subprocess(
        job,
        timeout_seconds=12.5,
        should_cancel=lambda: False,
    )

    assert result.fit_result.params["a"] == mp.mpf("1")
    assert calls["config"] is job.parallel_config
    assert calls["target"] is workers_core._fit_job_subprocess_entry
    assert calls["payload"] == _serialize_fit_job(job)
    assert calls["timeout_seconds"] == 12.5
    assert callable(calls["should_cancel"])


def test_self_consistent_fit_subprocess_ignores_stale_disabled_legacy_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"]["enable_new_implicit_backend"] = False
    payload["parallel_config"]["enable_new_auto_fit_backend"] = True
    job = _deserialize_fit_job(payload)
    calls: dict[str, object] = {}

    class FailingRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, Any]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, Any]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return workers_core._serialize_fit_result_payload(
                workers_core.FitResultPayload(
                    job=job,
                    fit_result=FitResult(
                        params={"a": mp.mpf("1"), "b": mp.mpf("2")},
                        param_errors={},
                        chi2=mp.mpf("0"),
                        reduced_chi2=mp.mpf("0"),
                        aic=mp.mpf("0"),
                        bic=mp.mpf("0"),
                        r2=mp.mpf("1"),
                        rmse=mp.mpf("0"),
                        residuals=[],
                        fitted_curve=[],
                        covariance=[],
                        details={},
                    ),
                    expression="u",
                    logs=[],
                    warnings=[],
                )
            )

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FailingRunner)

    result = _execute_fit_job_payload_subprocess(
        job,
        timeout_seconds=9.5,
        should_cancel=lambda: False,
    )

    assert result.fit_result.params["a"] == mp.mpf("1")
    assert calls["timeout_seconds"] == 9.5
    assert callable(calls["should_cancel"])
    assert calls["config"] is job.parallel_config
    assert calls["target"] is workers_core._fit_job_subprocess_entry


def test_legacy_implicit_backend_surfaces_are_removed() -> None:
    assert not hasattr(ParallelConfig, "enable_new_implicit_backend")
    assert not hasattr(ParallelConfig, "enable_new_auto_fit_backend")
    assert not hasattr(workers_core, "_execute_fit_job_payload_subprocess_legacy")
    assert not hasattr(workers_core, "_fit_job_subprocess_queue_entry")
    assert not hasattr(workers_core, "_terminate_fit_subprocess")
    assert not hasattr(workers_core, "_deserialize_fit_subprocess_queue_payload")
    assert not hasattr(workers_core, "_fit_self_consistent_with_legacy_hooks")
    assert not hasattr(workers_core, "_self_consistent_hooks_replaced")
    assert not hasattr(workers_core, "_ORIGINAL_BUILD_IMPLICIT_MODEL_SPECIFICATION")
    assert not hasattr(workers_core, "_ORIGINAL_CAN_FIT_OBSERVED_IMPLICIT_VARIABLE")
    assert not hasattr(workers_core, "_ORIGINAL_FIT_OBSERVED_IMPLICIT_VARIABLE_LINEAR_MODEL")
    assert not hasattr(workers_core, "_ORIGINAL_FIT_CUSTOM_MODEL")


def test_self_consistent_fit_subprocess_target_uses_job_precision_under_low_ambient_dps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job(precision=90)
    precise = mp.mpf("1.234567890123456789012345678901234567890123456789")
    job.y_series[0] = precise
    job.target_series[0] = precise
    observed: dict[str, object] = {}

    def fake_execute(received_job: FitJob) -> workers_core.FitResultPayload:
        observed["mp_dps"] = mp.mp.dps
        observed["target_value"] = received_job.target_series[0]
        return workers_core.FitResultPayload(
            job=received_job,
            fit_result=FitResult(
                params={"a": precise},
                param_errors={},
                chi2=precise,
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[precise],
                fitted_curve=[precise],
                covariance=[],
                details={},
            ),
            expression="u",
            logs=[],
            warnings=[],
        )

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload", fake_execute)
    payload = _serialize_fit_job(job)

    with mp.workdps(15):
        result_payload = workers_core._fit_job_subprocess_entry(payload)
        restored = workers_core._deserialize_fit_result_payload(result_payload)

    assert observed["mp_dps"] == 90
    with mp.workdps(100):
        assert mp.almosteq(observed["target_value"], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.params["a"], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_fit_subprocess_maps_backend_interruption_to_cancelled_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()

    class InterruptingRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            self.config = config

        def run_killable(self, *args: object, **kwargs: object) -> object:
            raise InterruptedError("backend interrupted")

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", InterruptingRunner)

    with pytest.raises(InterruptedError, match="Self-consistent fit cancelled"):
        _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)


def test_fit_killable_runner_child_depth_marker_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    runner = KillableProcessTaskRunner(config=ParallelConfig())

    payload = runner.run_killable(
        _depth_probe_payload,
        {"kind": "fit"},
        timeout_seconds=2.0,
    )

    assert payload["payload"] == {"kind": "fit"}
    assert payload["env_depth"] == "1" or payload["current_depth"] >= 1


@pytest.mark.parametrize(
    ("mode", "expected_source"),
    [
        ("warm", "warm"),
        ("hint", "hint"),
    ],
)
def test_implicit_seed_sources_match_across_serial_and_process_worker_probe(
    mode: str,
    expected_source: str,
) -> None:
    serial = _implicit_seed_diagnostic_probe({"mode": mode})
    process = KillableProcessTaskRunner(config=ParallelConfig()).run_killable(
        _implicit_seed_diagnostic_probe,
        {"mode": mode},
        timeout_seconds=5.0,
    )

    assert process == serial
    seed_sources = process["seed_sources"]
    assert isinstance(seed_sources, dict)
    assert seed_sources[expected_source] == 1
    assert expected_source in process["attempt_sources"]
    if mode == "warm":
        assert set(process["point_indexes"]) == {0, 1}
    else:
        assert set(process["point_indexes"]) == {0}


def test_self_consistent_fit_job_serialization_preserves_high_precision_values() -> None:
    with mp.workdps(100):
        precise = mp.mpf("1.234567890123456789012345678901234567890123456789")
        job = _small_self_consistent_fit_job(precision=80)
        job.x_series[0] = precise
        row = list(job.data_rows[0])
        row[0] = precise
        job.data_rows[0] = tuple(row)
        job.variable_data["x"][0] = precise

        payload = _serialize_fit_job(job)

    with mp.workdps(15):
        restored = _deserialize_fit_job(payload)

    with mp.workdps(100):
        assert mp.almosteq(restored.x_series[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.data_rows[0][0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.variable_data["x"][0], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_fit_job_serialization_unwraps_uncertainty_sigmas() -> None:
    job = _small_self_consistent_fit_job(precision=50)
    uncertain = parse_uncertainty_format("1.23(4)", lang="en")
    job.sigma_rows[0] = (None, uncertain)
    job.sigma_series[0] = uncertain  # type: ignore[list-item]

    payload = _serialize_fit_job(job)

    assert mp.almosteq(mp.mpf(payload["sigma_rows"][0][1]), mp.mpf("0.04"), abs_eps=mp.mpf("1e-18"))
    assert mp.almosteq(mp.mpf(payload["sigma_series"][0]), mp.mpf("0.04"), abs_eps=mp.mpf("1e-18"))

    restored = _deserialize_fit_job(payload)

    assert restored.sigma_rows[0][1] == mp.mpf("0.04")
    assert restored.sigma_series[0] == mp.mpf("0.04")


def test_self_consistent_fit_result_deserialization_preserves_high_precision_values() -> None:
    with mp.workdps(100):
        precise = mp.mpf("2.34567890123456789012345678901234567890123456789")
        job = _small_self_consistent_fit_job(precision=80)
        fit = FitResult(
            params={"a": precise},
            param_errors={"a": mp.mpf("1e-40")},
            chi2=precise,
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[precise],
            fitted_curve=[precise],
            covariance=[[precise]],
            details={"metric": precise},
        )
        result_payload = workers_core._serialize_fit_result_payload(
            workers_core.FitResultPayload(
                job=job,
                fit_result=fit,
                expression="u",
                logs=[],
                warnings=[],
            )
        )

    with mp.workdps(15):
        restored = workers_core._deserialize_fit_result_payload(result_payload)

    with mp.workdps(100):
        assert mp.almosteq(restored.fit_result.params["a"], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.chi2, precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.residuals[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.fitted_curve[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.covariance[0][0], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_subprocess_executes_real_fit_roundtrip() -> None:
    job = _small_self_consistent_fit_job()

    payload = _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)
    fit = payload.fit_result

    assert mp.almosteq(fit.params["a"], mp.mpf("1"), abs_eps=mp.mpf("1e-20"))
    assert mp.almosteq(fit.params["b"], mp.mpf("2"), abs_eps=mp.mpf("1e-20"))
    assert payload.job.model_type == "self_consistent"
    assert payload.expression == "u"


def test_custom_fit_serialized_payload_is_equivalent_low_precision_with_constants() -> None:
    job = _custom_fit_job(precision=16)

    serial = _execute_fit_job_payload(job)
    process = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_fit_result_equivalent(serial.fit_result, process.fit_result, abs_eps="1e-10")
    assert process.fit_result.details["optimizer_backend"] == serial.fit_result.details["optimizer_backend"]


def test_custom_fit_serialized_payload_is_equivalent_high_precision_with_constants() -> None:
    job = _custom_fit_job(precision=50)

    serial = _execute_fit_job_payload(job)
    process = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_fit_result_equivalent(serial.fit_result, process.fit_result, abs_eps="1e-30")
    assert process.fit_result.details["optimizer_backend"] == "mpmath_high_precision"


def test_self_consistent_serial_and_process_are_equivalent_low_precision_scipy_candidate_fallback() -> None:
    job = _general_self_consistent_fit_job(precision=16, data_sigmas=True)

    serial = _execute_fit_job_payload(job)
    process = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_fit_result_equivalent(serial.fit_result, process.fit_result, abs_eps="1e-8")
    _assert_configured_seed_state_is_not_leaked(process.fit_result)
    assert process.fit_result.details["optimizer_backend"] == "mpmath_high_precision"
    assert process.fit_result.details["scipy_safety_passed"] is False
    history = process.fit_result.details.get("fallback_history", [])
    assert isinstance(history, list)
    assert any(
        isinstance(item, dict)
        and item.get("from") == "scipy_implicit_least_squares"
        and "unweighted data_sigmas" in str(item.get("reason", ""))
        for item in history
    )


def test_self_consistent_serial_and_process_are_equivalent_high_precision_mpmath() -> None:
    job = _general_self_consistent_fit_job(precision=50)

    serial = _execute_fit_job_payload(job)
    process = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_fit_result_equivalent(serial.fit_result, process.fit_result, abs_eps="1e-25")
    _assert_configured_seed_state_is_not_leaked(process.fit_result)
    assert process.fit_result.details["optimizer_backend"] == "mpmath_high_precision"


def test_self_consistent_serial_and_process_preserve_seed_hint_metadata() -> None:
    job = _seed_hint_self_consistent_fit_job()

    serial = _execute_fit_job_payload(job)
    process = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_fit_result_equivalent(serial.fit_result, process.fit_result, abs_eps="1e-25")
    _assert_implicit_metadata_contract(process.fit_result)
    assert process.fit_result.details["implicit_seed_hint"] == "validated inverse-square output seed"


def test_self_consistent_process_cancel_then_retry_matches_clean_serial_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    job = _small_self_consistent_fit_job()
    budget = LocalWorkerBudget(1)
    ambient_dps = mp.mp.dps

    class BudgetedRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            self._runner = KillableProcessTaskRunner(config=config, worker_budget=budget)

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, Any]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, Any]:
            result = self._runner.run_killable(
                target,
                payload,
                timeout_seconds=timeout_seconds,
                should_cancel=should_cancel,
            )
            return cast(dict[str, Any], result)

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", BudgetedRunner)

    with pytest.raises(InterruptedError, match="cancel"):
        _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0, should_cancel=lambda: True)

    assert budget.available == 1
    assert current_parallel_depth() == 0
    assert mp.mp.dps == ambient_dps

    serial = _execute_fit_job_payload(job)
    retry = _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)

    _assert_fit_result_equivalent(serial.fit_result, retry.fit_result, abs_eps="1e-18")
    assert budget.available == 1
    assert current_parallel_depth() == 0


def test_self_consistent_repeated_process_runs_do_not_leak_cache_or_diagnostics() -> None:
    job = _general_self_consistent_fit_job(precision=30)
    serial = _execute_fit_job_payload(job)

    first = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)
    second = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_fit_result_equivalent(serial.fit_result, first.fit_result, abs_eps="1e-18")
    _assert_fit_result_equivalent(serial.fit_result, second.fit_result, abs_eps="1e-18")
    _assert_configured_seed_state_is_not_leaked(first.fit_result)
    _assert_configured_seed_state_is_not_leaked(second.fit_result)
    assert first.fit_result.details["implicit_diagnostics"] == second.fit_result.details["implicit_diagnostics"]


def test_self_consistent_worker_rebuilds_model_spec_and_cache_inside_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ParentOnlyFailingRunner:
        def fit(self, *_args: object, **_kwargs: object) -> FitResult:
            raise AssertionError("parent FitRunner should not execute inside spawned child")

    monkeypatch.setattr(workers_core, "FitRunner", lambda: ParentOnlyFailingRunner())
    job = _general_self_consistent_fit_job(precision=30)

    process = _execute_fit_job_payload_subprocess(job, timeout_seconds=20.0)

    _assert_configured_seed_state_is_not_leaked(process.fit_result)
    assert process.fit_result.details["implicit_strategy"] == "analytic_implicit_output_space"


def test_fit_job_worker_dto_preserves_variable_target_and_single_series_consistency() -> None:
    job = _small_self_consistent_fit_job()

    restored = _deserialize_fit_job(_serialize_fit_job(job))

    assert restored.variable_map == {"x": "x"}
    assert restored.variable_data["x"] == restored.x_series
    assert restored.target_series == restored.y_series
    assert restored.sigma_series == [None] * len(restored.y_series)
    assert [row[0] for row in restored.data_rows] == restored.x_series
    assert [row[1] for row in restored.data_rows] == restored.target_series


def test_fit_batch_worker_routes_self_consistent_fit_through_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    calls: dict[str, object] = {}

    def fake_subprocess(received_job, *, timeout_seconds, should_cancel):
        calls["job"] = received_job
        calls["timeout_seconds"] = timeout_seconds
        calls["should_cancel"] = should_cancel
        return SimpleNamespace(fit_result=None, logs=[], warnings=[])

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload_subprocess", fake_subprocess)

    worker = FitBatchWorker([], capture_output=False)
    payload = worker._run_fit_task(job)

    assert payload.fit_result is None
    assert calls["job"] is job
    assert calls["timeout_seconds"] == 10.0
    assert callable(calls["should_cancel"])


def test_fit_batch_worker_emits_cancelled_when_self_consistent_subprocess_interrupts(
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    job = _small_self_consistent_fit_job()

    def fake_subprocess(received_job, *, timeout_seconds, should_cancel):
        raise InterruptedError("cancelled")

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload_subprocess", fake_subprocess)

    worker = FitBatchWorker([FitBatchTask(index=0, fit_job=job)], capture_output=False)
    with qtbot.waitSignal(worker.cancelled, timeout=3000):
        worker.start()

    assert worker.wait(3000)


def test_execute_calc_job_extrapolation_returns_payload() -> None:
    with mp.workdps(80):
        limit = mp.mpf("1")
        amp = mp.mpf("0.5")
        terms = [limit + amp / mp.power(n, 2) for n in range(1, 9)]  # 8 columns
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + " ".join(mp.nstr(v, 50) for v in terms) + "\n"

        opts = ExtrapolationOptions(method="richardson", mp_precision=80)
        job = CalcJob(
            mode="extrapolation",
            data_path=None,
            manual_content=data_text,
            manual_constants="",
            constants_file_path=None,
            options=opts,
            caption=None,
            generate_latex=False,
            output_path="",
            use_dcolumn=False,
            verbose=False,
            render_plots=False,
            lang="en",
            latex_digits=16,
            latex_group_size=3,
            uncertainty_digits=2,
        )

        result = _execute_calc_job(job)
        assert result.mode == "extrapolation"
        assert result.latex_path is None
        payload = result.payload
        assert payload["headers"] == headers
        assert len(payload["data_rows"]) == 1
        assert len(payload["results"]) == 1
        assert payload["precision_used"] == 80
        assert payload["render_plots"] is False
        assert "plots" not in payload

        res0 = payload["results"][0]
        assert mp.fabs(res0.value - limit) < mp.mpf("1e-2")


def test_run_calculation_excludes_disabled_error_constants_from_calc_job(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.window import ExtrapolationWindow

    class _Signal:
        def connect(self, _callback: object) -> None:
            return

    class _DummyCalcWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

    captured: dict[str, object] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("error"))
    win._data_stack.setCurrentIndex(1)
    win.manual_data_edit.setPlainText("A B\n1 2\n")
    win.formula_edit.setPlainText("A + B")
    win.error_constants_editor.set_rows([{"name": "K", "value": "1.23(4)"}])
    win.error_constants_editor.setChecked(False)

    win.run_calculation()

    job = captured["job"]
    assert isinstance(job, CalcJob)
    assert captured["started"] is True
    assert win.error_constants_editor.constants_dict(validate=False) == {"K": "1.23(4)"}
    assert job.constants_enabled is False
    assert job.manual_constants == ""
