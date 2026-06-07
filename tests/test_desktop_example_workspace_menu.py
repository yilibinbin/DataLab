from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox


def _allow_discard(win):
    win._confirm_workspace_discard_or_save = lambda: True
    return win


def test_example_workspace_menu_action_exists(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    actions = [action.text() for action in win.menuBar().actions()]
    menu_text = " ".join(actions).lower()
    assert "example" in menu_text or "示例" in menu_text


def test_open_example_workspace_uses_current_language_for_menu_labels(qtbot, monkeypatch):
    from app_desktop.window import ExtrapolationWindow, list_example_menu_entries, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)
    win._apply_language("en")
    examples = list_example_workspaces()
    entries = {entry.filename: entry for entry in list_example_menu_entries()}
    expected_label = entries[examples[0].name].label(lang="en")
    captured: dict[str, list[str]] = {}

    def fake_get_item(*args, **kwargs):
        captured["labels"] = list(args[3])
        return "", False

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(fake_get_item))

    assert not win.open_example_workspace()
    assert expected_label in captured["labels"]


def test_open_example_workspace_marks_template_and_save_requires_save_as(qtbot, monkeypatch, tmp_path):
    from app_desktop.window import EXAMPLE_WORKSPACE_NAMES, ExtrapolationWindow, list_example_menu_entries, list_example_workspaces
    from shared.workspace_io import read_workspace
    from tests.test_example_workspaces import FORBIDDEN_STRATEGY_KEYS, _walk_keys

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    examples = list_example_workspaces()
    assert {path.name for path in examples} == set(EXAMPLE_WORKSPACE_NAMES)
    assert [entry.filename for entry in list_example_menu_entries()] == list(EXAMPLE_WORKSPACE_NAMES)
    assert examples
    selected = examples[0]
    original_bytes = selected.read_bytes()
    saved_path = tmp_path / "saved-example.datalab"

    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        staticmethod(lambda *args, **kwargs: (selected.name, True)),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(saved_path), "DataLab Workspace (*.datalab)")),
    )

    assert win.open_example_workspace()
    assert win._workspace_path is None
    assert win._workspace_template_source == selected
    assert selected.name in win.windowTitle()

    win.result_edit.setPlainText("changed example result")
    win._mark_workspace_dirty()
    assert win._workspace_dirty is True

    assert win.save_workspace()
    assert saved_path.is_file()
    assert win._workspace_path == saved_path
    assert win._workspace_template_source is None
    assert selected.read_bytes() == original_bytes
    saved = read_workspace(saved_path)
    assert FORBIDDEN_STRATEGY_KEYS & set(_walk_keys(saved.manifest)) == set()


def test_direct_template_open_save_as_does_not_write_temp_or_bundle(qtbot, monkeypatch, tmp_path):
    from app_desktop.window import ExtrapolationWindow, copy_example_workspace, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    source = list_example_workspaces()[0]
    temp_copy = copy_example_workspace(source.name, tmp_path / "copy")
    temp_before = temp_copy.read_bytes()
    bundle_before = source.read_bytes()
    saved_path = tmp_path / "user" / "analysis.datalab"

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(saved_path), "DataLab Workspace (*.datalab)")),
    )

    assert win._open_workspace_from_path(temp_copy, as_template=True)
    assert win.save_workspace()

    assert saved_path.is_file()
    assert temp_copy.read_bytes() == temp_before
    assert source.read_bytes() == bundle_before
    assert win._workspace_path == saved_path


def test_template_save_as_refuses_bundled_example_path(qtbot, monkeypatch):
    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    source = list_example_workspaces()[0]
    source_before = source.read_bytes()
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(source), "DataLab Workspace (*.datalab)")),
    )
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args, **kwargs: None))

    assert win._open_workspace_from_path(source, as_template=True)
    win.result_edit.setPlainText("changed example result")
    win._mark_workspace_dirty()

    assert not win.save_workspace()
    assert source.read_bytes() == source_before
    assert win._workspace_path is None
    assert win._workspace_template_source == source


def test_regular_open_of_bundled_example_is_treated_as_template(qtbot, monkeypatch, tmp_path):
    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    source = list_example_workspaces()[0]
    source_before = source.read_bytes()
    saved_path = tmp_path / "opened-example-copy.datalab"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *args, **kwargs: (str(saved_path), "DataLab Workspace (*.datalab)")),
    )

    assert win._open_workspace_from_path(source)
    assert win._workspace_path is None
    assert win._workspace_template_source == source

    win.result_edit.setPlainText("changed after regular open")
    win._mark_workspace_dirty()
    assert win.save_workspace()

    assert saved_path.is_file()
    assert source.read_bytes() == source_before
    assert win._workspace_path == saved_path
    assert win._workspace_template_source is None
