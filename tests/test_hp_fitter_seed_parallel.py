"""P1-6: the seed-variant solve is a pure, picklable, process-parallel step.

The historical per-variant solve was a closure over compiled evaluators, so it
could not be parallelized. It is now a top-level function operating on a
serializable task, driven by ParallelMapExecutor. These tests pin the load-
bearing invariants: the task pickles, the worker rebuilds the model correctly,
and — the one that matters — a parallel run yields the SAME solution as a serial
run (determinism), so the best-χ² pick can never diverge from the serial path.
"""

from __future__ import annotations

import pickle

from mpmath import mp

from fitting.constraints import ParameterState
from fitting.hp_fitter import (
    _SeedSolveTask,
    _solve_seed_variant_task,
)
from shared.parallel_backend import ParallelMapExecutor
from shared.parallel_config import ParallelConfig, ParallelMode, ParallelWorkload


def _linear_task(seed, index=0, precision=50):
    # Fit a*x + b to y = 2x + 1 through the gradient system; the least-squares
    # root of the normal equations is the exact (a=2, b=1).
    xs = [mp.mpf(k) for k in range(6)]
    ys = [mp.mpf(2) * x + mp.mpf(1) for x in xs]
    observations = tuple({"x": x} for x in xs)
    state = ParameterState(
        free_params=["a", "b"],
        bounds={},
        initial_guess={"a": mp.mpf("0"), "b": mp.mpf("0")},
        fixed_values={},
        dependent_defs={},
    )
    return _SeedSolveTask(
        variant_index=index,
        seed_variant=tuple(mp.mpf(v) for v in seed),
        expression="a*x + b",
        variables=("x",),
        parameters=("a", "b"),
        constants={},
        parameter_state=state,
        observations=observations,
        targets=tuple(ys),
        weights=None,
        precision=precision,
    )


def test_seed_solve_task_is_picklable():
    # The whole point of the refactor: the task carries only serializable data
    # (recipe strings + mpf values), so it can cross a process boundary.
    task = _linear_task([1, 1])
    restored = pickle.loads(pickle.dumps(task))
    assert restored.expression == "a*x + b"
    assert restored.seed_variant == task.seed_variant


def test_worker_rebuilds_model_and_solves():
    mp.dps = 50
    result = _solve_seed_variant_task(_linear_task([1, 1]))
    assert result.solution is not None
    a, b = result.solution
    assert mp.almosteq(a, mp.mpf("2"), abs_eps=mp.mpf("1e-30"))
    assert mp.almosteq(b, mp.mpf("1"), abs_eps=mp.mpf("1e-30"))


def test_parallel_solve_matches_serial_solve():
    # Determinism: running the same variant tasks through a PROCESS pool must
    # produce bit-identical solutions to a SERIAL run. If this ever diverged,
    # the best-χ² pick could differ between machines.
    seeds = [[0.5, 0.5], [1, 1], [3, -1], [-2, 4]]
    tasks = [_linear_task(seed, index=i) for i, seed in enumerate(seeds)]

    serial = ParallelMapExecutor(ParallelConfig(mode=ParallelMode.SERIAL))
    serial_results = serial.map_pure(
        _solve_seed_variant_task, tasks, workload=ParallelWorkload.CPU_MPMATH
    )

    parallel = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, reserve_cores=0, min_process_tasks=2)
    )
    parallel_results = parallel.map_pure(
        _solve_seed_variant_task, tasks, workload=ParallelWorkload.CPU_MPMATH
    )

    serial_by_index = {r.variant_index: r for r in serial_results}
    parallel_by_index = {r.variant_index: r for r in parallel_results}
    assert set(serial_by_index) == set(parallel_by_index)
    for index, s in serial_by_index.items():
        p = parallel_by_index[index]
        assert (s.solution is None) == (p.solution is None)
        if s.solution is not None:
            for sv, pv in zip(s.solution, p.solution):
                # Identical to full precision — same algorithm, same inputs.
                assert mp.almosteq(sv, pv, abs_eps=mp.mpf("1e-40"))
