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


def test_about_dialog_includes_repository_url() -> None:
    window_text = (ROOT / "app_desktop" / "window.py").read_text(encoding="utf-8")
    about_text = (ROOT / "app_desktop" / "about_dialog.py").read_text(encoding="utf-8")

    assert "from shared.update_checker import REPOSITORY_URL" in window_text
    assert "REPOSITORY_URL" in window_text
    assert "REPOSITORY_URL" in about_text
    assert "项目主页" in about_text
    assert "Repository" in about_text
