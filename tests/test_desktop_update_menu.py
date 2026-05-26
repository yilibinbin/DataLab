from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_help_menu_exposes_repository_and_update_actions() -> None:
    text = (ROOT / "app_desktop" / "panels.py").read_text(encoding="utf-8")

    assert 'QAction("项目主页", self)' in text
    assert 'self._register_text(project_action, "项目主页", "Project Homepage", "setText")' in text
    assert "project_action.triggered.connect(self._open_project_homepage)" in text
    assert 'QAction("检查更新", self)' in text
    assert 'self._register_text(update_action, "检查更新", "Check for Updates", "setText")' in text
    assert "update_action.triggered.connect(self._check_for_updates)" in text


def test_help_menu_exposes_auto_update_toggle() -> None:
    text = (ROOT / "app_desktop" / "panels.py").read_text(encoding="utf-8")

    assert 'QAction("自动更新", self)' in text
    assert "auto_update_action.setCheckable(True)" in text
    assert "auto_update_action.setChecked(self._update_controller.auto_update_enabled())" in text
    assert "auto_update_action.toggled.connect(self._set_auto_update_enabled)" in text
    assert 'self._register_text(auto_update_action, "自动更新", "Automatic Updates", "setText")' in text


def test_window_delegates_update_flow_to_controller() -> None:
    text = (ROOT / "app_desktop" / "window.py").read_text(encoding="utf-8")

    assert "from app_desktop.update_controller import UpdateController" in text
    assert "self._update_controller = UpdateController(self)" in text
    assert "self._update_controller.check_now()" in text
    assert "self._update_controller.set_auto_update_enabled" in text
    assert "self._update_controller.maybe_auto_check" in text
    assert "def exit_for_update" in text


def test_about_dialog_includes_repository_url() -> None:
    window_text = (ROOT / "app_desktop" / "window.py").read_text(encoding="utf-8")
    about_text = (ROOT / "app_desktop" / "about_dialog.py").read_text(encoding="utf-8")

    assert "from shared.update_checker import REPOSITORY_URL" in window_text
    assert "REPOSITORY_URL" in window_text
    assert "REPOSITORY_URL" in about_text
    assert "项目主页" in about_text
    assert "Repository" in about_text
