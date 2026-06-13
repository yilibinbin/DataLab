from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


def test_core_session_qt_bridge_emits_status_and_result_signals(qtbot) -> None:
    from app_desktop.bridge_qt import CoreSessionQtBridge
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionService, SessionStatus

    QApplication.instance() or QApplication([])
    bridge = CoreSessionQtBridge()
    statuses: list[tuple[object, object]] = []
    results: list[tuple[object, object]] = []
    failures: list[tuple[object, object]] = []
    bridge.status_changed.connect(lambda status, request: statuses.append((status, request)))
    bridge.result_ready.connect(lambda result, request: results.append((result, request)))
    bridge.failure_ready.connect(lambda result, request: failures.append((result, request)))

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        return ResultEnvelope(
            kind=ResultKind.TEXT,
            status=ResultStatus.SUCCEEDED,
            payload={"value": "ok"},
        )

    service = SessionService(
        handlers={JobMode.STATISTICS: _handler},
        callbacks=bridge.callbacks(),
    )
    request = ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="success")

    result = service.submit(request)

    assert statuses == [(SessionStatus.RUNNING, request), (SessionStatus.IDLE, None)]
    assert results == [(result, request)]
    assert failures == []


def test_core_session_qt_bridge_emits_failure_signal_without_result(qtbot) -> None:
    from app_desktop.bridge_qt import CoreSessionQtBridge
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService

    QApplication.instance() or QApplication([])
    bridge = CoreSessionQtBridge()
    results: list[tuple[object, object]] = []
    failures: list[tuple[object, object]] = []
    bridge.result_ready.connect(lambda result, request: results.append((result, request)))
    bridge.failure_ready.connect(lambda result, request: failures.append((result, request)))

    service = SessionService(callbacks=bridge.callbacks())
    request = ComputeJobRequest(mode=JobMode.ROOT_SOLVING, inputs={}, request_id="unsupported")

    result = service.submit(request)

    assert result.status is ResultStatus.FAILED
    assert failures == [(result, request)]
    assert results == []


def test_core_session_qt_bridge_works_with_default_statistics_service(qtbot) -> None:
    from app_desktop.bridge_qt import CoreSessionQtBridge
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.service_factory import create_core_session_service
    from datalab_core.session import SessionStatus

    QApplication.instance() or QApplication([])
    bridge = CoreSessionQtBridge()
    statuses: list[tuple[object, object]] = []
    results: list[tuple[object, object]] = []
    failures: list[tuple[object, object]] = []
    bridge.status_changed.connect(lambda status, request: statuses.append((status, request)))
    bridge.result_ready.connect(lambda result, request: results.append((result, request)))
    bridge.failure_ready.connect(lambda result, request: failures.append((result, request)))

    service = create_core_session_service(callbacks=bridge.callbacks())
    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "values": ("1.0000000000000000001", "2.0000000000000000002"),
            "sigmas": (None, None),
            "stats_mode": "mean",
            "use_sample": True,
            "use_weighted_variance": True,
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
        request_id="qt-statistics",
    )

    result = service.submit(request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"].startswith("1.50000000000000000015")
    assert statuses == [(SessionStatus.RUNNING, request), (SessionStatus.IDLE, None)]
    assert results == [(result, request)]
    assert failures == []
