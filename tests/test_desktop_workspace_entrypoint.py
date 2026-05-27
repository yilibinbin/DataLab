from __future__ import annotations

from pathlib import Path


def test_workspace_paths_from_argv_keeps_first_datalab_path() -> None:
    from app_desktop.main import workspace_paths_from_argv

    first = Path("/tmp/case.datalab")
    second = Path("/tmp/second.DATALAB")

    assert workspace_paths_from_argv(["DataLab", "/tmp/notes.txt", str(first), str(second)]) == [
        first
    ]


def test_workspace_paths_from_argv_ignores_options_and_end_of_options() -> None:
    from app_desktop.main import workspace_paths_from_argv

    workspace = Path("/tmp/case.datalab")

    assert workspace_paths_from_argv(
        ["DataLab", "-psn_0_12345", "--debug", "--", str(workspace)]
    ) == [workspace]


def test_workspace_paths_from_argv_can_be_disabled_for_macos() -> None:
    from app_desktop.main import workspace_paths_from_argv

    assert workspace_paths_from_argv(["DataLab", "/tmp/case.datalab"], enabled=False) == []


class _FakeWindow:
    def __init__(self) -> None:
        self.opened: list[tuple[Path, bool]] = []

    def open_workspace_path(self, path: Path, *, confirm_discard: bool = True) -> bool:
        self.opened.append((path, confirm_discard))
        return True


def test_workspace_open_dispatcher_keeps_single_pending_path(tmp_path) -> None:
    from app_desktop.main import WorkspaceOpenDispatcher

    first = tmp_path / "first.datalab"
    second = tmp_path / "second.datalab"
    dispatcher = WorkspaceOpenDispatcher()
    window = _FakeWindow()

    assert dispatcher.request_open(first, confirm_discard=True) is True
    assert dispatcher.request_open(second, confirm_discard=True) is True
    assert window.opened == []

    dispatcher.set_window(window)
    assert window.opened == [(first, True)]


def test_workspace_open_dispatcher_dropped_pending_path_can_open_later(tmp_path) -> None:
    from app_desktop.main import WorkspaceOpenDispatcher

    first = tmp_path / "first.datalab"
    second = tmp_path / "second.datalab"
    dispatcher = WorkspaceOpenDispatcher()
    window = _FakeWindow()

    assert dispatcher.request_open(first, confirm_discard=True) is True
    assert dispatcher.request_open(second, confirm_discard=True) is True
    dispatcher.set_window(window)
    assert window.opened == [(first, True)]

    assert dispatcher.request_open(second, confirm_discard=True) is True
    assert window.opened == [(first, True), (second, True)]


def test_workspace_open_dispatcher_deduplicates_paths_after_window_registered(tmp_path) -> None:
    from app_desktop.main import WorkspaceOpenDispatcher

    path = tmp_path / "case.datalab"
    dispatcher = WorkspaceOpenDispatcher()
    window = _FakeWindow()
    dispatcher.set_window(window)

    assert dispatcher.request_open(path, confirm_discard=True) is True
    assert dispatcher.request_open(path, confirm_discard=False) is True
    assert window.opened == [(path, True)]


def test_workspace_file_open_filter_accepts_qfileopen_event(qtbot, tmp_path) -> None:
    from PySide6.QtGui import QFileOpenEvent

    from app_desktop.main import WorkspaceFileOpenFilter, WorkspaceOpenDispatcher

    path = tmp_path / "event.datalab"
    dispatcher = WorkspaceOpenDispatcher()
    window = _FakeWindow()
    dispatcher.set_window(window)
    file_filter = WorkspaceFileOpenFilter(dispatcher)

    assert file_filter.eventFilter(None, QFileOpenEvent(str(path))) is True
    assert window.opened == [(path, True)]
