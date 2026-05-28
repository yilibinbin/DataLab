import contextlib
import multiprocessing
import os
import queue
import signal
import threading
import time
from concurrent.futures import ProcessPoolExecutor, TimeoutError as _FutureTimeout
from pathlib import Path
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


def _sleep_then_square(payload: tuple[int, float]) -> int:
    value, seconds = payload
    time.sleep(seconds)
    return value * value


def _write_pid_then_sleep(payload: tuple[str, float]) -> int:
    marker_dir, seconds = payload
    pid = os.getpid()
    Path(marker_dir, f"{pid}.pid").write_text(str(pid), encoding="utf-8")
    time.sleep(seconds)
    return pid


def _killable_echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "payload": payload}


def _killable_depth_payload(payload: object) -> dict[str, Any]:
    return {
        "payload": payload,
        "env_depth": os.environ.get("DATALAB_PARALLEL_DEPTH"),
        "current_depth": current_parallel_depth(),
    }


def _killable_sleep(seconds: float) -> str:
    time.sleep(seconds)
    return "finished"


def _killable_ignore_sigterm_and_sleep(payload: tuple[str, float]) -> str:
    ready_path, seconds = payload
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path(ready_path).write_text("ready", encoding="utf-8")
    time.sleep(seconds)
    return "finished"


def _killable_object_payload(payload: object) -> object:
    return payload


def _killable_raise(payload: object) -> object:
    raise ValueError(f"bad payload: {payload!r}")


def _wait_for_path(path: Path, timeout_seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return path.exists()


def _marked_worker_pids(marker_dir: Path) -> list[int]:
    pids: list[int] = []
    for marker in marker_dir.glob("*.pid"):
        with contextlib.suppress(ValueError):
            pids.append(int(marker.read_text(encoding="utf-8").strip()))
    return pids


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_marked_pids_to_exit(
    marker_dir: Path, *, timeout_seconds: float = 3.0
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pids = _marked_worker_pids(marker_dir)
        if pids and all(not _pid_exists(pid) for pid in pids):
            return True
        time.sleep(0.02)
    pids = _marked_worker_pids(marker_dir)
    return bool(pids) and all(not _pid_exists(pid) for pid in pids)


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
        def submit(self, *args: Any, **kwargs: Any) -> Any:
            future = super().submit(*args, **kwargs)

            class ObservingFuture:
                def result(self, *result_args: Any, **result_kwargs: Any) -> Any:
                    parent_depths.append(current_parallel_depth())
                    return future.result(*result_args, **result_kwargs)

                def cancel(self) -> bool:
                    return future.cancel()

            return ObservingFuture()

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


def test_process_map_timeout_does_not_wait_for_long_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    executor = ParallelMapExecutor(
        ParallelConfig(mode=ParallelMode.PROCESS, max_workers=2, min_process_tasks=1),
        worker_budget=LocalWorkerBudget(total=2),
    )
    sleep_seconds = 3.0
    started = time.monotonic()

    with pytest.raises(_FutureTimeout):
        executor.map_pure(
            _sleep_then_square,
            [(2, sleep_seconds), (3, sleep_seconds)],
            workload=ParallelWorkload.CPU_FLOAT,
            timeout=0.2,
        )

    assert time.monotonic() - started < 2.0


def test_process_map_timeout_stops_workers_before_releasing_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    marker_dir = tmp_path / "worker-pids"
    marker_dir.mkdir()

    class ObservingBudget(LocalWorkerBudget):
        def __init__(self) -> None:
            super().__init__(total=2)
            self.live_pids_at_release: list[list[int]] = []

        def release(self, permits: int = 1) -> None:
            self.live_pids_at_release.append(
                [
                    pid
                    for pid in _marked_worker_pids(marker_dir)
                    if _pid_exists(pid)
                ]
            )
            super().release(permits)

    start_method = (
        "forkserver"
        if "forkserver" in multiprocessing.get_all_start_methods()
        else "spawn"
    )
    timeout = 1.5
    budget = ObservingBudget()
    executor = ParallelMapExecutor(
        ParallelConfig(
            mode=ParallelMode.PROCESS,
            max_workers=2,
            min_process_tasks=1,
            process_start_method=start_method,
        ),
        worker_budget=budget,
    )

    with pytest.raises(_FutureTimeout):
        executor.map_pure(
            _write_pid_then_sleep,
            [(str(marker_dir), 10.0), (str(marker_dir), 10.0)],
            workload=ParallelWorkload.CPU_FLOAT,
            timeout=timeout,
        )

    pids = _marked_worker_pids(marker_dir)
    assert len(pids) == 2
    assert _wait_for_marked_pids_to_exit(marker_dir)
    assert budget.available == 2
    assert budget.live_pids_at_release
    assert all(not live_pids for live_pids in budget.live_pids_at_release)


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


def test_killable_runner_returns_payload() -> None:
    runner = parallel_backend.KillableProcessTaskRunner(
        worker_budget=LocalWorkerBudget(total=1)
    )

    result = runner.run_killable(
        _killable_echo,
        {"value": 42},
        timeout_seconds=2.0,
    )

    assert result == {"ok": True, "payload": {"value": 42}}


def test_killable_runner_timeout_terminates_child() -> None:
    runner = parallel_backend.KillableProcessTaskRunner(
        worker_budget=LocalWorkerBudget(total=1)
    )
    started = time.monotonic()

    with pytest.raises(TimeoutError):
        runner.run_killable(_killable_sleep, 5.0, timeout_seconds=0.1)

    assert time.monotonic() - started < 3.0


def test_killable_handle_kill_releases_budget_and_allows_next_task() -> None:
    budget = LocalWorkerBudget(total=1)
    runner = parallel_backend.KillableProcessTaskRunner(worker_budget=budget)
    handle = runner.start_killable(_killable_sleep, 5.0)

    handle.kill()
    handle.kill()

    assert budget.available == 1
    second = runner.start_killable(_killable_echo, {"value": 2})
    assert second.wait(timeout_seconds=2.0) == {"ok": True, "payload": {"value": 2}}
    assert budget.available == 1


def test_killable_handle_terminate_releases_budget_and_allows_next_task() -> None:
    budget = LocalWorkerBudget(total=1)
    runner = parallel_backend.KillableProcessTaskRunner(worker_budget=budget)
    handle = runner.start_killable(_killable_sleep, 5.0)

    handle.terminate()
    handle.terminate()

    assert budget.available == 1
    second = runner.start_killable(_killable_echo, {"value": 3})
    assert second.wait(timeout_seconds=2.0) == {"ok": True, "payload": {"value": 3}}
    assert budget.available == 1


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows process termination does not use SIGTERM handlers",
)
def test_killable_handle_terminate_kills_sigterm_resistant_child(
    tmp_path: Path,
) -> None:
    budget = LocalWorkerBudget(total=1)
    runner = parallel_backend.KillableProcessTaskRunner(worker_budget=budget)
    ready_path = tmp_path / "sigterm-ready"
    handle = runner.start_killable(
        _killable_ignore_sigterm_and_sleep, (str(ready_path), 5.0)
    )
    assert _wait_for_path(ready_path)

    handle.terminate()

    assert not handle._process.is_alive()
    assert budget.available == 1
    second = runner.start_killable(_killable_echo, {"value": 4})
    assert second.wait(timeout_seconds=2.0) == {"ok": True, "payload": {"value": 4}}
    assert budget.available == 1


def test_killable_handle_wait_and_kill_concurrent_finalization_is_safe() -> None:
    budget = LocalWorkerBudget(total=1)
    runner = parallel_backend.KillableProcessTaskRunner(worker_budget=budget)
    handle = runner.start_killable(_killable_sleep, 5.0)
    errors: list[BaseException] = []

    def wait_for_handle() -> None:
        try:
            handle.wait(timeout_seconds=10.0)
        except (RuntimeError, TimeoutError, InterruptedError) as exc:
            errors.append(exc)

    waiter = threading.Thread(target=wait_for_handle)
    waiter.start()
    time.sleep(0.1)

    handle.kill()
    waiter.join(timeout=3.0)

    assert not waiter.is_alive()
    assert not handle._process.is_alive()
    assert budget.available == 1
    assert all(
        isinstance(exc, RuntimeError | TimeoutError | InterruptedError)
        for exc in errors
    )


def test_killable_handle_wait_drains_queue_after_process_exit() -> None:
    budget = LocalWorkerBudget(total=1)
    assert budget.try_acquire(1)

    class ExitedProcess:
        exitcode = 0

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float | None = None) -> None:
            return None

        def terminate(self) -> None:
            raise AssertionError("terminate should not run for an exited process")

        def kill(self) -> None:
            raise AssertionError("kill should not run for an exited process")

    class DelayedQueue:
        closed = False
        joined = False
        calls = 0

        def get(self, timeout: float | None = None) -> tuple[str, int]:
            self.calls += 1
            if self.calls == 1:
                raise queue.Empty
            assert timeout == pytest.approx(0.2)
            return ("ok", 123)

        def close(self) -> None:
            self.closed = True

        def join_thread(self) -> None:
            self.joined = True

    delayed_queue = DelayedQueue()
    handle = parallel_backend.KillableHandle[int](
        _process=ExitedProcess(),
        _result_queue=delayed_queue,
        _release_budget=lambda: budget.release(1),
    )

    assert handle.wait(timeout_seconds=1.0) == 123
    assert delayed_queue.calls == 2
    assert delayed_queue.closed
    assert delayed_queue.joined
    assert budget.available == 1


def test_killable_runner_child_sees_parallel_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    runner = parallel_backend.KillableProcessTaskRunner(
        worker_budget=LocalWorkerBudget(total=1)
    )

    result = runner.run_killable(
        _killable_depth_payload,
        "marker",
        timeout_seconds=2.0,
    )

    assert result["payload"] == "marker"
    assert result["env_depth"] == "1" or result["current_depth"] >= 1


def test_killable_runner_unpicklable_target_raises_parent_type_error() -> None:
    runner = parallel_backend.KillableProcessTaskRunner(
        worker_budget=LocalWorkerBudget(total=1)
    )

    with pytest.raises(TypeError, match="picklable"):
        runner.run_killable(lambda payload: payload, 1, timeout_seconds=1.0)


def test_killable_runner_unpicklable_payload_raises_parent_type_error() -> None:
    runner = parallel_backend.KillableProcessTaskRunner(
        worker_budget=LocalWorkerBudget(total=1)
    )

    with pytest.raises(TypeError, match="picklable"):
        runner.run_killable(
            _killable_object_payload, threading.Lock(), timeout_seconds=1.0
        )


def test_killable_runner_uses_worker_budget_before_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    budget = LocalWorkerBudget(total=1)
    assert budget.try_acquire(1)

    class FailingContext:
        def Process(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("process should not start without budget")

        def Queue(self) -> object:
            raise AssertionError("queue should not start without budget")

    monkeypatch.setattr(
        multiprocessing,
        "get_context",
        lambda method: FailingContext(),
    )
    runner = parallel_backend.KillableProcessTaskRunner(worker_budget=budget)

    with pytest.raises(RuntimeError, match="worker budget|budget"):
        runner.run_killable(_killable_echo, {"value": 1}, timeout_seconds=1.0)

    budget.release(1)


def test_killable_runner_child_exception_surfaces_as_runtime_error() -> None:
    runner = parallel_backend.KillableProcessTaskRunner(
        worker_budget=LocalWorkerBudget(total=1)
    )

    with pytest.raises(RuntimeError, match="ValueError|bad payload"):
        runner.run_killable(_killable_raise, "x", timeout_seconds=2.0)
