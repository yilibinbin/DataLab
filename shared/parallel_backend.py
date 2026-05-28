from __future__ import annotations

import contextlib
import contextvars
import multiprocessing
import os
import pickle
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, Iterator, Sequence, TypeVar

from shared.parallel_config import (
    ParallelConfig,
    ParallelMode,
    ParallelWorkload,
    resolve_worker_count,
)


T = TypeVar("T")
R = TypeVar("R")

_PARALLEL_DEPTH_ENV = "DATALAB_PARALLEL_DEPTH"
_parallel_depth_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "datalab_parallel_depth", default=0
)


def _env_parallel_depth() -> int:
    try:
        return max(0, int(os.environ.get(_PARALLEL_DEPTH_ENV, "0")))
    except ValueError:
        return 0


def _current_parallel_depth() -> int:
    return max(_parallel_depth_var.get(), _env_parallel_depth())


def current_parallel_depth() -> int:
    return _current_parallel_depth()


def initialize_parallel_worker_depth(depth: int = 1) -> None:
    os.environ[_PARALLEL_DEPTH_ENV] = str(max(1, int(depth)))


@contextlib.contextmanager
def parallel_depth() -> Iterator[None]:
    depth = _current_parallel_depth()
    token = _parallel_depth_var.set(depth + 1)
    try:
        yield
    finally:
        _parallel_depth_var.reset(token)


def _initialize_process_worker_depth(parent_depth: int) -> None:
    initialize_parallel_worker_depth(parent_depth + 1)


class LocalWorkerBudget:
    def __init__(self, total: int):
        if total < 1:
            raise ValueError("LocalWorkerBudget total must be at least 1")
        self._total = int(total)
        self._used = 0
        self._lock = threading.Lock()

    @property
    def total(self) -> int:
        return self._total

    @property
    def available(self) -> int:
        with self._lock:
            return self._total - self._used

    def try_acquire(self, permits: int = 1) -> bool:
        if permits < 1:
            raise ValueError("permits must be at least 1")
        permits = int(permits)
        with self._lock:
            if self._used + permits > self._total:
                return False
            self._used += permits
            return True

    def release(self, permits: int = 1) -> None:
        if permits < 1:
            raise ValueError("permits must be at least 1")
        permits = int(permits)
        with self._lock:
            if permits > self._used:
                raise ValueError("cannot release more permits than acquired")
            self._used -= permits


_GLOBAL_WORKER_BUDGET = LocalWorkerBudget(
    max(1, min(16, (os.cpu_count() or 2) - 1 if (os.cpu_count() or 2) > 2 else 1))
)


@dataclass
class MapHandle(Generic[R]):
    """Lightweight cooperative-map handle; not a hard-kill process handle."""

    _wait: Callable[[], Sequence[R]]
    _request_stop: Callable[[], None] | None = None

    def wait(self) -> list[R]:
        return list(self._wait())

    def request_stop(self) -> None:
        if self._request_stop is not None:
            self._request_stop()


@dataclass
class KillableHandle(Generic[R]):
    """API placeholder for Task 3 subprocess timeout/terminate/kill work."""

    def wait(self, timeout_seconds: float | None = None) -> R:
        raise NotImplementedError("KillableHandle is implemented in Task 3")

    def terminate(self) -> None:
        raise NotImplementedError("KillableHandle is implemented in Task 3")

    def kill(self) -> None:
        raise NotImplementedError("KillableHandle is implemented in Task 3")


class ParallelMapExecutor:
    def __init__(
        self,
        config: ParallelConfig | None = None,
        *,
        worker_budget: LocalWorkerBudget | None = None,
    ):
        self.config = config or ParallelConfig()
        self.worker_budget = worker_budget or _GLOBAL_WORKER_BUDGET

    def map_pure(
        self,
        func: Callable[[T], R],
        items: Iterable[T],
        *,
        workload: ParallelWorkload,
    ) -> list[R]:
        item_list = list(items)
        if not item_list:
            return []

        mode, workers = self._execution_mode(item_list, workload)
        if mode == ParallelMode.SERIAL or workers <= 1:
            return self._map_serial(func, item_list)

        if not self.worker_budget.try_acquire(workers):
            return self._map_serial(func, item_list)

        try:
            if mode == ParallelMode.THREAD:
                return self._map_thread(func, item_list, workers=workers)
            if mode == ParallelMode.PROCESS:
                self._assert_picklable_for_process(func, item_list)
                return self._map_process(func, item_list, workers=workers)
        finally:
            self.worker_budget.release(workers)

        return self._map_serial(func, item_list)

    def map_pure_handle(
        self,
        func: Callable[[T], R],
        items: Iterable[T],
        *,
        workload: ParallelWorkload,
    ) -> MapHandle[R]:
        return MapHandle(lambda: self.map_pure(func, items, workload=workload))

    def _execution_mode(
        self, items: Sequence[T], workload: ParallelWorkload
    ) -> tuple[ParallelMode, int]:
        depth = _current_parallel_depth()
        workers = resolve_worker_count(
            self.config,
            task_count=len(items),
            workload=workload,
            depth=depth,
        )
        if workers <= 1:
            return ParallelMode.SERIAL, 1

        if self.config.mode == ParallelMode.THREAD:
            if workload == ParallelWorkload.CPU_MPMATH:
                return ParallelMode.SERIAL, 1
            return ParallelMode.THREAD, workers

        if self.config.mode == ParallelMode.PROCESS:
            return ParallelMode.PROCESS, workers

        if self.config.mode == ParallelMode.SERIAL:
            return ParallelMode.SERIAL, 1

        if workload == ParallelWorkload.IO:
            return ParallelMode.THREAD, workers
        if workload in {ParallelWorkload.CPU_FLOAT, ParallelWorkload.CPU_MPMATH}:
            return ParallelMode.PROCESS, workers

        return ParallelMode.SERIAL, 1

    def _map_serial(self, func: Callable[[T], R], items: Sequence[T]) -> list[R]:
        with parallel_depth():
            return [func(item) for item in items]

    def _map_thread(
        self, func: Callable[[T], R], items: Sequence[T], *, workers: int
    ) -> list[R]:
        with parallel_depth():
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = []
                for item in items:
                    context = contextvars.copy_context()
                    futures.append(pool.submit(context.run, func, item))
                return [future.result() for future in futures]

    def _map_process(
        self, func: Callable[[T], R], items: Sequence[T], *, workers: int
    ) -> list[R]:
        parent_depth = _current_parallel_depth()
        with parallel_depth():
            context = multiprocessing.get_context(self.config.process_start_method)
            with ProcessPoolExecutor(
                max_workers=workers,
                mp_context=context,
                initializer=_initialize_process_worker_depth,
                initargs=(parent_depth,),
            ) as pool:
                return list(pool.map(func, items))

    def _assert_picklable_for_process(
        self, func: Callable[[T], R], items: Sequence[T]
    ) -> None:
        try:
            pickle.dumps(func)
            for item in items:
                pickle.dumps(item)
        except Exception as exc:
            raise TypeError(
                "Process parallel map requires a picklable callable and payload"
            ) from exc
