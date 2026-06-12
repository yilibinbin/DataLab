from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum

from shared.integer_validation import strict_int


class ParallelMode(StrEnum):
    AUTO = "auto"
    SERIAL = "serial"
    THREAD = "thread"
    PROCESS = "process"


class ParallelWorkload(StrEnum):
    CPU_MPMATH = "cpu_mpmath"
    CPU_FLOAT = "cpu_float"
    IO = "io"
    KILLABLE_FIT = "killable_fit"


class NestedParallelPolicy(StrEnum):
    SERIAL_WHEN_NESTED = "serial_when_nested"
    ALLOW = "allow"


@dataclass(frozen=True)
class ParallelConfig:
    mode: ParallelMode = ParallelMode.AUTO
    max_workers: int | None = None
    reserve_cores: int = 1
    default_worker_cap: int = 16
    min_process_tasks: int = 4
    nested_policy: NestedParallelPolicy = NestedParallelPolicy.SERIAL_WHEN_NESTED
    process_start_method: str = "spawn"


def should_use_serial_for_nested(config: ParallelConfig, *, depth: int) -> bool:
    depth = strict_int(depth, field_name="depth")
    return (
        depth > 0
        and config.nested_policy == NestedParallelPolicy.SERIAL_WHEN_NESTED
    )


def resolve_worker_count(
    config: ParallelConfig,
    *,
    task_count: int,
    workload: ParallelWorkload,
    depth: int = 0,
) -> int:
    task_count = strict_int(task_count, field_name="task_count")
    depth = strict_int(depth, field_name="depth")
    min_process_tasks = strict_int(config.min_process_tasks, field_name="min_process_tasks")
    reserve_cores = strict_int(config.reserve_cores, field_name="reserve_cores")
    default_worker_cap = strict_int(config.default_worker_cap, field_name="default_worker_cap")
    max_workers = (
        None
        if config.max_workers is None
        else strict_int(config.max_workers, field_name="max_workers")
    )
    if task_count <= 1 or should_use_serial_for_nested(config, depth=depth):
        return 1

    cpu_workloads = {ParallelWorkload.CPU_MPMATH, ParallelWorkload.CPU_FLOAT}
    if task_count < min_process_tasks and workload in cpu_workloads:
        return 1

    if config.mode == ParallelMode.SERIAL:
        return 1

    if config.mode == ParallelMode.THREAD and workload == ParallelWorkload.CPU_MPMATH:
        return 1

    if workload == ParallelWorkload.KILLABLE_FIT:
        return 1

    cpu_count = os.cpu_count() or 2
    if cpu_count <= 2 and workload in cpu_workloads:
        return 1

    configured = (
        max_workers
        if max_workers is not None and max_workers > 0
        else None
    )
    available_workers = max(1, cpu_count - max(0, reserve_cores))
    workers = configured or min(default_worker_cap, available_workers)

    return max(1, min(workers, task_count))
