from __future__ import annotations

from contextvars import ContextVar
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from enum import Enum
from threading import Event
from typing import TypeAlias

from .jobs import ComputeJobRequest, JobMode
from .results import ResultEnvelope, ResultKind, ResultStatus


JobHandler: TypeAlias = Callable[[ComputeJobRequest], ResultEnvelope]
StatusCallback: TypeAlias = Callable[["SessionStatus", ComputeJobRequest | None], None]
ResultCallback: TypeAlias = Callable[[ResultEnvelope, ComputeJobRequest], None]
CancellationChecker: TypeAlias = Callable[[], bool]


class CoreJobCancelled(Exception):
    """Raised inside migrated core handlers when cooperative cancellation is requested."""


class SessionStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"


@dataclass(frozen=True)
class SessionCallbacks:
    on_status: StatusCallback | None = None
    on_result: ResultCallback | None = None
    on_failure: ResultCallback | None = None


@dataclass
class _CancellationToken:
    request_id: str
    external_checker: CancellationChecker | None = None
    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        if self._event.is_set():
            return True
        if self.external_checker is None:
            return False
        try:
            return bool(self.external_checker())
        except Exception:
            return True


_CURRENT_CANCELLATION_TOKEN: ContextVar[_CancellationToken | None] = ContextVar(
    "datalab_core_current_cancellation_token",
    default=None,
)


def cancellation_requested() -> bool:
    """Return whether the currently submitted core job has been cancelled."""

    token = _CURRENT_CANCELLATION_TOKEN.get()
    return bool(token is not None and token.is_cancelled())


def check_cancelled() -> None:
    """Raise ``CoreJobCancelled`` if the current core job should stop."""

    if cancellation_requested():
        raise CoreJobCancelled("Core job was cancelled.")


@dataclass
class SessionService:
    """Synchronous core dispatcher boundary for incremental service migration.

    Host callbacks are fail-fast adapter hooks: callback exceptions propagate
    to the caller after the service resets its active request state. Reentrant
    busy rejections intentionally do not emit callbacks or replace
    ``last_result`` because they are guard failures inside an active submit.
    Failed envelopes emit ``on_failure`` only; successful envelopes emit
    ``on_result`` only, so adapters can keep error handling and result
    rendering separate.
    """

    handlers: MutableMapping[JobMode | str, JobHandler] = field(default_factory=dict)
    callbacks: SessionCallbacks = field(default_factory=SessionCallbacks)
    cancellation_checker: CancellationChecker | None = None

    def __post_init__(self) -> None:
        handlers: dict[JobMode | str, JobHandler] = {}
        self._active_request_id: str | None = None
        self._last_result: ResultEnvelope | None = None
        self._cancel_token: _CancellationToken | None = None
        if self.cancellation_checker is not None and not callable(self.cancellation_checker):
            raise TypeError("cancellation_checker must be callable.")
        for mode, handler in self.handlers.items():
            if not callable(handler):
                raise TypeError("handler must be callable.")
            handlers[_normalize_mode(mode)] = handler
        self.handlers = handlers

    @property
    def active_request_id(self) -> str | None:
        return self._active_request_id

    @property
    def last_result(self) -> ResultEnvelope | None:
        return self._last_result

    @property
    def status(self) -> SessionStatus:
        return SessionStatus.RUNNING if self._active_request_id is not None else SessionStatus.IDLE

    def register_handler(self, mode: JobMode | str, handler: JobHandler) -> None:
        if not callable(handler):
            raise TypeError("handler must be callable.")
        self.handlers[_normalize_mode(mode)] = handler

    def submit(self, request: ComputeJobRequest) -> ResultEnvelope:
        if self._active_request_id is not None:
            return _failure_envelope(
                request,
                error_code="busy",
                message="A core job is already running.",
                extra={"active_request_id": self._active_request_id},
            )

        self._active_request_id = request.request_id
        self._cancel_token = _CancellationToken(
            request_id=request.request_id,
            external_checker=self.cancellation_checker,
        )
        context_token = _CURRENT_CANCELLATION_TOKEN.set(self._cancel_token)
        primary_exception: BaseException | None = None
        try:
            self._emit_status(SessionStatus.RUNNING, request)
            handler = self.handlers.get(request.mode)
            if handler is None:
                result = _failure_envelope(
                    request,
                    error_code="unsupported_mode",
                    message=f"No core handler is registered for mode: {request.mode.value}.",
                )
            else:
                try:
                    check_cancelled()
                    result = handler(request)
                    check_cancelled()
                except CoreJobCancelled:
                    result = _cancelled_envelope(request)
                except Exception as exc:  # noqa: BLE001 - service boundary converts failures.
                    result = _failure_envelope(
                        request,
                        error_code="handler_exception",
                        message=str(exc),
                        extra={"error_type": type(exc).__name__},
                    )
                if not isinstance(result, ResultEnvelope):
                    result = _failure_envelope(
                        request,
                        error_code="invalid_handler_result",
                        message="Core handler did not return a ResultEnvelope.",
                        extra={"result_type": type(result).__name__},
                    )
            self._last_result = result
            if result.status is ResultStatus.SUCCEEDED:
                self._emit_result(result, request)
            else:
                self._emit_failure(result, request)
            return result
        except BaseException as exc:
            primary_exception = exc
            raise
        finally:
            _CURRENT_CANCELLATION_TOKEN.reset(context_token)
            self._cancel_token = None
            self._active_request_id = None
            try:
                self._emit_status(SessionStatus.IDLE, None)
            except BaseException:
                if primary_exception is None:
                    raise

    def cancel(self, request_id: str | None = None) -> bool:
        if request_id is not None and not isinstance(request_id, str):
            raise TypeError("request_id must be a string or None.")
        if self._active_request_id is None:
            return False
        if request_id is not None and request_id != self._active_request_id:
            return False
        if self._cancel_token is None:
            return False
        self._cancel_token.cancel()
        return True

    def _emit_status(self, status: SessionStatus, request: ComputeJobRequest | None) -> None:
        if self.callbacks.on_status is not None:
            self.callbacks.on_status(status, request)

    def _emit_result(self, result: ResultEnvelope, request: ComputeJobRequest) -> None:
        if self.callbacks.on_result is not None:
            self.callbacks.on_result(result, request)

    def _emit_failure(self, result: ResultEnvelope, request: ComputeJobRequest) -> None:
        if self.callbacks.on_failure is not None:
            self.callbacks.on_failure(result, request)


def _normalize_mode(mode: JobMode | str) -> JobMode:
    try:
        return mode if isinstance(mode, JobMode) else JobMode(str(mode))
    except ValueError as exc:
        raise ValueError(f"Unsupported job mode: {mode!r}.") from exc


def _failure_envelope(
    request: ComputeJobRequest,
    *,
    error_code: str,
    message: str,
    extra: Mapping[str, str] | None = None,
) -> ResultEnvelope:
    payload: dict[str, str] = {
        "error_code": error_code,
        "message": message,
        "mode": request.mode.value,
        "request_id": request.request_id,
    }
    if extra:
        payload.update(extra)
    return ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.FAILED, payload=payload)


def _cancelled_envelope(request: ComputeJobRequest) -> ResultEnvelope:
    return ResultEnvelope(
        kind=ResultKind.TEXT,
        status=ResultStatus.CANCELLED,
        payload={
            "error_code": "cancelled",
            "message": "Core job was cancelled.",
            "mode": request.mode.value,
            "request_id": request.request_id,
        },
    )
