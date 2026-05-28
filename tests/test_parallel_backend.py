import os
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import pytest

import shared.parallel_backend as parallel_backend
from shared.parallel_backend import (
    LocalWorkerBudget,
    ParallelMapExecutor,
    current_parallel_depth,
    initialize_parallel_worker_depth,
    parallel_depth,
)
from shared.parallel_config import ParallelConfig, ParallelMode, ParallelWorkload


def _square(value: int) -> int:
    return value * value


def _depth_value(value: int) -> tuple[int, int]:
    return value, current_parallel_depth()


def _slow_square(value: int) -> int:
    time.sleep(0.05)
    return value * value


def test_serial_map_preserves_order() -> None:
    executor = ParallelMapExecutor(ParallelConfig(mode=ParallelMode.SERIAL))

    assert executor.map_pure(
        _square, [3, 1, 2], workload=ParallelWorkload.CPU_FLOAT
    ) == [9, 1, 4]


def test_process_map_parent_depth_is_set_while_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    parent_depths: list[int] = []

    class ObservingProcessPoolExecutor(ProcessPoolExecutor):
        def map(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
            iterator = super().map(*args, **kwargs)

            def observed_iterator() -> Iterator[Any]:
                while True:
                    parent_depths.append(current_parallel_depth())
                    try:
                        value = next(iterator)
                    except StopIteration:
                        return
                    yield value

            return observed_iterator()

    monkeypatch.setattr(
        parallel_backend, "ProcessPoolExecutor", ObservingProcessPoolExecutor
    )
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, min_process_tasks=1)
    )

    assert executor.map_pure(
        _slow_square, [3, 1, 2], workload=ParallelWorkload.CPU_FLOAT
    ) == [9, 1, 4]
    assert parent_depths
    assert all(depth > 0 for depth in parent_depths)


def test_thread_map_workers_inherit_parallel_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.THREAD, max_workers=2),
        worker_budget=LocalWorkerBudget(total=2),
    )

    results = executor.map_pure(_depth_value, [3, 1, 2], workload=ParallelWorkload.IO)

    assert [value for value, _depth in results] == [3, 1, 2]
    assert all(depth > 0 for _value, depth in results)


def test_process_map_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, min_process_tasks=1)
    )

    assert executor.map_pure(
        _square, [3, 1, 2], workload=ParallelWorkload.CPU_FLOAT
    ) == [9, 1, 4]


def test_nested_process_map_degrades_to_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, min_process_tasks=1)
    )

    with parallel_depth():
        assert executor.map_pure(
            _square, [2, 4], workload=ParallelWorkload.CPU_FLOAT
        ) == [4, 16]


def test_overlapping_threaded_parallel_depth_does_not_leave_env_stuck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    worker_entered = threading.Event()
    main_entered = threading.Event()
    worker_can_exit = threading.Event()

    def worker() -> None:
        with parallel_depth():
            worker_entered.set()
            main_entered.wait(timeout=2)
            worker_can_exit.wait(timeout=2)

    thread = threading.Thread(target=worker)
    thread.start()
    assert worker_entered.wait(timeout=2)

    with parallel_depth():
        main_entered.set()
        worker_can_exit.set()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert os.environ.get("DATALAB_PARALLEL_DEPTH") is None

    assert os.environ.get("DATALAB_PARALLEL_DEPTH") is None
    assert current_parallel_depth() == 0


def test_parallel_worker_depth_initializer_sets_process_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)

    initialize_parallel_worker_depth()

    assert os.environ["DATALAB_PARALLEL_DEPTH"] == "1"
    assert current_parallel_depth() == 1


def test_process_mode_serial_fallback_allows_unpicklable_callable_task_count_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2))

    assert executor.map_pure(
        lambda value: value + 1, [1], workload=ParallelWorkload.CPU_FLOAT
    ) == [2]


def test_process_mode_serial_fallback_allows_unpicklable_callable_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, min_process_tasks=4)
    )

    assert executor.map_pure(
        lambda value: value + 1, [1, 2, 3], workload=ParallelWorkload.CPU_FLOAT
    ) == [2, 3, 4]


def test_unpicklable_process_callable_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, min_process_tasks=1),
        worker_budget=LocalWorkerBudget(total=2),
    )

    assert current_parallel_depth() == 0
    assert executor._execution_mode([1, 2], ParallelWorkload.IO) == (
        ParallelMode.PROCESS,
        2,
    )
    with pytest.raises(TypeError, match="picklable"):
        executor.map_pure(
            lambda value: value, [1, 2], workload=ParallelWorkload.IO
        )


def test_local_worker_budget_shared_permit_behavior() -> None:
    budget = LocalWorkerBudget(total=1)

    assert budget.try_acquire(1)
    assert not budget.try_acquire(1)
    budget.release(1)
    assert budget.try_acquire(1)
