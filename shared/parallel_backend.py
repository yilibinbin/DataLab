from __future__ import annotations

import contextlib
import contextvars
import multiprocessing
import os
import pickle
import queue
import threading
import time
import traceback
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError as _FutureTimeout,
)
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Iterable, Iterator, Sequence, TypeVar, cast

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


def _terminate_process_pool_workers(pool: ProcessPoolExecutor) -> None:
    # Python 3.11 has no public ProcessPoolExecutor terminate/kill API.
    # Timeout cleanup must stop already-running workers before caller-owned
    # worker-budget permits are released, so this is deliberately isolated.
    processes = getattr(pool, "_processes", None)
    if not processes:
        return
    workers = list(processes.values())
    for process in workers:
        with contextlib.suppress(Exception):
            if process.is_alive():
                process.terminate()
    for process in workers:
        with contextlib.suppress(Exception):
            process.join(timeout=1.0)
    for process in workers:
        with contextlib.suppress(Exception):
            if process.is_alive():
                process.kill()
    for process in workers:
        with contextlib.suppress(Exception):
            process.join(timeout=1.0)


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
    """Hard-kill subprocess handle for one isolated task."""

    _process: Any
    _result_queue: Any
    _release_budget: Callable[[], None]
    _closed: bool = False
    _finalize_lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def wait(
        self,
        timeout_seconds: float | None = None,
        *,
        should_cancel: Callable[[], bool] | None = None,
    ) -> R:
        deadline = (
            None
            if timeout_seconds is None
            else time.monotonic() + max(0.0, float(timeout_seconds))
        )
        try:
            while True:
                if should_cancel is not None and should_cancel():
                    self.terminate()
                    raise InterruptedError("Killable process task cancelled")

                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self.terminate()
                    if self._process.is_alive():
                        self.kill()
                    raise TimeoutError("Killable process task timed out")

                poll_timeout = 0.05 if remaining is None else min(0.05, remaining)
                try:
                    status, payload = self._result_queue.get(timeout=poll_timeout)
                except queue.Empty:
                    if not self._process.is_alive():
                        self._process.join(timeout=0.5)
                        try:
                            status, payload = self._result_queue.get(timeout=0.2)
                        except queue.Empty:
                            raise RuntimeError(
                                "Killable process task exited without returning "
                                f"a result (exitcode={self._process.exitcode})"
                            ) from None
                        except Exception as exc:
                            raise RuntimeError(
                                "Killable process task wait was interrupted by result "
                                "queue closure"
                            ) from exc
                        return self._handle_result(status, payload)
                    continue
                except Exception as exc:
                    raise RuntimeError(
                        "Killable process task wait was interrupted by result "
                        "queue closure"
                    ) from exc

                self._process.join(timeout=1.0)
                return self._handle_result(status, payload)
        finally:
            self._ensure_stopped()
            self._finalize_if_process_dead()

    def terminate(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=1.0)
        self._finalize_if_process_dead()

    def kill(self) -> None:
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=1.0)
        self._finalize_if_process_dead()

    def _handle_result(self, status: object, payload: object) -> R:
        if status == "ok":
            return cast(R, payload)
        raise RuntimeError(f"Killable process task failed: {payload}")

    def _ensure_stopped(self) -> None:
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=1.0)

    def _finalize_if_process_dead(self) -> None:
        if self._process.is_alive():
            return
        with self._finalize_lock:
            if self._closed:
                return
            self._closed = True
            self._close_queue()
            self._release_budget()

    def _close_queue(self) -> None:
        with contextlib.suppress(Exception):
            self._result_queue.close()
        with contextlib.suppress(Exception):
            self._result_queue.join_thread()


def _run_killable_process_task(
    target: Callable[[T], R],
    payload: T,
    parent_depth: int,
    result_queue: Any,
) -> None:
    _initialize_process_worker_depth(parent_depth)
    try:
        result = target(payload)
        pickle.dumps(result)
        result_queue.put(("ok", result))
    except BaseException as exc:
        message = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        result_queue.put(("error", message))


class KillableProcessTaskRunner:
    def __init__(
        self,
        *,
        config: ParallelConfig | None = None,
        worker_budget: LocalWorkerBudget | None = None,
        process_start_method: str | None = None,
    ):
        self.worker_budget = worker_budget or _GLOBAL_WORKER_BUDGET
        self.config = config or ParallelConfig()
        self.process_start_method = process_start_method or self.config.process_start_method

    def run_killable(
        self,
        target: Callable[[T], R],
        payload: T,
        *,
        timeout_seconds: float | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> R:
        handle = self.start_killable(target, payload)
        return handle.wait(
            timeout_seconds=timeout_seconds,
            should_cancel=should_cancel,
        )

    def start_killable(
        self,
        target: Callable[[T], R],
        payload: T,
    ) -> KillableHandle[R]:
        self._assert_picklable(target, payload)
        if not self.worker_budget.try_acquire(1):
            raise RuntimeError("Cannot start killable process task: worker budget exhausted")

        acquired = True
        result_queue = None
        try:
            context = cast(Any, multiprocessing.get_context(self.process_start_method))
            result_queue = context.Queue()
            parent_depth = _current_parallel_depth()
            process = context.Process(
                target=_run_killable_process_task,
                args=(target, payload, parent_depth, result_queue),
            )
            process.start()
            acquired = False
            return KillableHandle(
                _process=process,
                _result_queue=result_queue,
                _release_budget=lambda: self.worker_budget.release(1),
            )
        finally:
            if acquired:
                if result_queue is not None:
                    with contextlib.suppress(Exception):
                        result_queue.close()
                    with contextlib.suppress(Exception):
                        result_queue.join_thread()
                self.worker_budget.release(1)

    def _assert_picklable(self, target: Callable[[T], R], payload: T) -> None:
        try:
            pickle.dumps(target)
            pickle.dumps(payload)
        except Exception as exc:
            raise TypeError(
                "Killable process task requires a picklable callable and payload"
            ) from exc


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
        timeout: float | None = None,
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
                return self._map_process(
                    func, item_list, workers=workers, timeout=timeout
                )
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
        self,
        func: Callable[[T], R],
        items: Sequence[T],
        *,
        workers: int,
        timeout: float | None = None,
    ) -> list[R]:
        parent_depth = _current_parallel_depth()
        with parallel_depth():
            context = multiprocessing.get_context(self.config.process_start_method)
            pool = ProcessPoolExecutor(
                max_workers=workers,
                mp_context=context,
                initializer=_initialize_process_worker_depth,
                initargs=(parent_depth,),
            )
            futures: list[Future[R]] = []
            shutdown_wait = True
            try:
                deadline = (
                    None
                    if timeout is None
                    else time.monotonic() + max(0.0, float(timeout))
                )
                futures = [pool.submit(func, item) for item in items]
                results: list[R] = []
                for future in futures:
                    remaining = (
                        None if deadline is None else deadline - time.monotonic()
                    )
                    if remaining is not None and remaining <= 0:
                        for pending in futures:
                            pending.cancel()
                        _terminate_process_pool_workers(pool)
                        shutdown_wait = False
                        pool.shutdown(wait=True, cancel_futures=True)
                        raise _FutureTimeout()
                    try:
                        results.append(future.result(timeout=remaining))
                    except _FutureTimeout:
                        for pending in futures:
                            pending.cancel()
                        _terminate_process_pool_workers(pool)
                        shutdown_wait = False
                        pool.shutdown(wait=True, cancel_futures=True)
                        raise
                return results
            finally:
                if shutdown_wait:
                    pool.shutdown(wait=True)

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
