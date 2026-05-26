from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_file_menu_exposes_workspace_actions() -> None:
    text = (ROOT / "app_desktop" / "panels.py").read_text(encoding="utf-8")

    assert 'file_menu = menubar.addMenu("文件")' in text
    assert 'QAction("新建工作区", self)' in text
    assert 'new_workspace_action.triggered.connect(self.new_workspace)' in text
    assert 'QAction("打开工作区…", self)' in text
    assert 'open_workspace_action.triggered.connect(self.open_workspace)' in text
    assert 'QAction("保存工作区", self)' in text
    assert 'save_workspace_action.triggered.connect(self.save_workspace)' in text
    assert 'QAction("工作区另存为…", self)' in text
    assert 'save_workspace_as_action.triggered.connect(self.save_workspace_as)' in text


def test_window_has_workspace_file_methods_and_worker_guard() -> None:
    text = (ROOT / "app_desktop" / "window.py").read_text(encoding="utf-8")

    assert "def new_workspace(self" in text
    assert "def open_workspace(self" in text
    assert "def save_workspace(self" in text
    assert "def save_workspace_as(self" in text
    assert "capture_workspace" in text
    assert "restore_workspace" in text
    assert "read_workspace" in text
    assert "write_workspace" in text
    assert "self._has_running_worker()" in text


def test_workspace_window_title_tracks_path_and_dirty_state(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow

    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    win._workspace_path = tmp_path / "case.datalab"
    win._workspace_dirty = False
    win._update_workspace_window_title()
    assert win.windowTitle() == "DataLab - case.datalab"

    win._mark_workspace_dirty()
    assert win.windowTitle() == "DataLab - case.datalab *"
