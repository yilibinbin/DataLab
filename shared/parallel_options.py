from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.integer_validation import strict_int
from shared.parallel_config import NestedParallelPolicy, ParallelConfig, ParallelMode


def parallel_config_from_mapping(value: Mapping[str, Any] | None) -> ParallelConfig:
    payload: Mapping[str, Any] = {} if value is None else value
    return ParallelConfig(
        mode=parallel_mode(payload.get("mode", ParallelMode.AUTO)),
        max_workers=optional_int(payload.get("max_workers"), field_name="parallel.max_workers"),
        reserve_cores=strict_int(payload.get("reserve_cores", 1), field_name="parallel.reserve_cores"),
        default_worker_cap=strict_int(
            payload.get("default_worker_cap", 16),
            field_name="parallel.default_worker_cap",
        ),
        min_process_tasks=strict_int(
            payload.get("min_process_tasks", 4),
            field_name="parallel.min_process_tasks",
        ),
        nested_policy=nested_parallel_policy(payload.get("nested_policy", NestedParallelPolicy.SERIAL_WHEN_NESTED)),
        process_start_method=str(payload.get("process_start_method") or "spawn"),
    )


def optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    return strict_int(value, field_name=field_name)


def parallel_mode(value: object) -> ParallelMode:
    try:
        return ParallelMode(str(value))
    except ValueError:
        return ParallelMode.AUTO


def nested_parallel_policy(value: object) -> NestedParallelPolicy:
    try:
        return NestedParallelPolicy(str(value))
    except ValueError:
        return NestedParallelPolicy.SERIAL_WHEN_NESTED
