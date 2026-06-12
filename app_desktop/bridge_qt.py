from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from datalab_core.jobs import ComputeJobRequest
from datalab_core.results import ResultEnvelope
from datalab_core.session import SessionCallbacks, SessionStatus


class CoreSessionQtBridge(QObject):
    """Qt signal adapter for ``datalab_core.session.SessionService`` callbacks."""

    status_changed = Signal(object, object)
    result_ready = Signal(object, object)
    failure_ready = Signal(object, object)

    def callbacks(self) -> SessionCallbacks:
        return SessionCallbacks(
            on_status=self._emit_status,
            on_result=self._emit_result,
            on_failure=self._emit_failure,
        )

    def _emit_status(self, status: SessionStatus, request: ComputeJobRequest | None) -> None:
        self.status_changed.emit(status, request)

    def _emit_result(self, result: ResultEnvelope, request: ComputeJobRequest) -> None:
        self.result_ready.emit(result, request)

    def _emit_failure(self, result: ResultEnvelope, request: ComputeJobRequest) -> None:
        self.failure_ready.emit(result, request)


__all__ = ["CoreSessionQtBridge"]
