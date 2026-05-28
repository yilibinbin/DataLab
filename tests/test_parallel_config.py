import os

from shared.parallel_config import (
    NestedParallelPolicy,
    ParallelConfig,
    ParallelMode,
    ParallelWorkload,
    resolve_worker_count,
    should_use_serial_for_nested,
)


def test_auto_worker_count_reserves_one_core(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    config = ParallelConfig(mode=ParallelMode.AUTO, max_workers=None, reserve_cores=1)

    assert (
        resolve_worker_count(
            config, task_count=99, workload=ParallelWorkload.CPU_MPMATH
        )
        == 7
    )


def test_worker_count_is_capped_by_task_count(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    config = ParallelConfig(
        mode=ParallelMode.AUTO,
        max_workers=None,
        reserve_cores=1,
        min_process_tasks=4,
    )

    assert (
        resolve_worker_count(config, task_count=5, workload=ParallelWorkload.CPU_FLOAT)
        == 5
    )


def test_small_cpu_float_task_count_uses_serial(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    config = ParallelConfig(
        mode=ParallelMode.AUTO,
        max_workers=None,
        min_process_tasks=4,
    )

    assert (
        resolve_worker_count(config, task_count=3, workload=ParallelWorkload.CPU_FLOAT)
        == 1
    )


def test_small_cpu_mpmath_task_count_uses_serial(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    config = ParallelConfig(
        mode=ParallelMode.AUTO,
        max_workers=None,
        min_process_tasks=4,
    )

    assert (
        resolve_worker_count(config, task_count=3, workload=ParallelWorkload.CPU_MPMATH)
        == 1
    )


def test_nested_parallel_defaults_to_serial():
    config = ParallelConfig(nested_policy=NestedParallelPolicy.SERIAL_WHEN_NESTED)

    assert should_use_serial_for_nested(config, depth=1)


def test_thread_mode_rejected_for_mpmath_workload():
    config = ParallelConfig(mode=ParallelMode.THREAD, max_workers=4)

    assert (
        resolve_worker_count(config, task_count=10, workload=ParallelWorkload.CPU_MPMATH)
        == 1
    )


def test_low_core_machine_avoids_process_parallelism(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    config = ParallelConfig(mode=ParallelMode.AUTO, max_workers=None)

    assert (
        resolve_worker_count(config, task_count=20, workload=ParallelWorkload.CPU_MPMATH)
        == 1
    )


def test_default_worker_count_is_capped(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 96)
    config = ParallelConfig(
        mode=ParallelMode.AUTO, max_workers=None, default_worker_cap=16
    )

    assert (
        resolve_worker_count(config, task_count=99, workload=ParallelWorkload.CPU_FLOAT)
        == 16
    )
