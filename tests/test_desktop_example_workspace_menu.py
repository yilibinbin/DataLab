from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from examples.catalog import EXAMPLE_NAMES


def _allow_discard(win):
    win._confirm_workspace_discard_or_save = lambda: True
    return win


def _formula_preview_has_content(win) -> bool:
    label = win.workbench_formula_preview_label
    pixmap = label.pixmap()
    return bool(label.text().strip()) or (pixmap is not None and not pixmap.isNull())


def test_example_workspace_menu_action_exists(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    actions = [action.text() for action in win.menuBar().actions()]
    menu_text = " ".join(actions).lower()
    assert "example" in menu_text or "示例" in menu_text


def test_workspace_and_run_keyboard_shortcuts_are_installed(qtbot):
    """P1-7: the primary actions carry standard keyboard shortcuts (a11y /
    discoverability). Standard keys auto-map per platform, so assert against
    QKeySequence.StandardKey rather than a hard-coded string."""
    from PySide6.QtGui import QAction, QKeySequence

    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    # Collect installed shortcuts as a list — QKeySequence is not reliably
    # hashable in PySide6 (putting it in a set can segfault), so compare by
    # equality against the list instead.
    installed = [
        action.shortcut()
        for action in win.findChildren(QAction)
        if not action.shortcut().isEmpty()
    ]
    for std in (
        QKeySequence.StandardKey.New,
        QKeySequence.StandardKey.Open,
        QKeySequence.StandardKey.Save,
        QKeySequence.StandardKey.SaveAs,
    ):
        assert any(seq == QKeySequence(std) for seq in installed), f"missing shortcut for {std}"

    # The run button carries the execute shortcut and runs/stops on trigger.
    assert not win.run_button.shortcut().isEmpty()
    assert win.run_button.shortcut() == QKeySequence("Ctrl+Return")


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


def test_example_workspaces_open_as_live_templates(qtbot):
    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    for source in list_example_workspaces():
        assert win._open_workspace_from_path(source, as_template=True), source.name
        assert win._workspace_path is None
        assert win._workspace_template_source == source
        assert win._workspace_snapshot_only is False
        assert win.scientific_checkbox.isEnabled()
        assert win.display_digits_spin.isEnabled()
        assert win.run_button.isEnabled()
        assert win.workbench_run_button.isEnabled()
        assert win.result_edit.toPlainText().strip()
        if win.workbench_formula_panel.isVisible():
            assert _formula_preview_has_content(win), source.name


def test_opening_narrow_example_clears_stale_manual_table_columns(qtbot):
    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)
    examples = {path.name: path for path in list_example_workspaces()}

    assert win._open_workspace_from_path(examples["quantum-defect-implicit.datalab"], as_template=True)
    assert win.manual_table.columnCount() == 3

    assert win._open_workspace_from_path(examples["root-batch-quadratic.datalab"], as_template=True)

    assert win.manual_table.columnCount() == 1
    assert win.manual_table.horizontalHeaderItem(0).text() == "A"
    assert win.manual_table.item(0, 0).text() == "1.0(1)"


@pytest.mark.parametrize("example_name", EXAMPLE_NAMES)
def test_example_workspace_can_run_default_calculation(qtbot, monkeypatch, example_name: str):
    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Ok))
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)
    examples = {path.name: path for path in list_example_workspaces()}
    source = examples[example_name]

    try:
        assert win._open_workspace_from_path(source, as_template=True), source.name
        win.generate_latex_checkbox.setChecked(False)
        win.generate_plots_checkbox.setChecked(False)
        win.run_calculation()
        qtbot.waitUntil(
            lambda: getattr(win, "_workbench_result_state", "") != "running" and not win._has_running_worker(),
            timeout=120000,
        )
        QApplication.processEvents()

        result_text = win.result_edit.toPlainText().strip()
        log_text = win.log_edit.toPlainText()
        assert getattr(win, "_workbench_result_state", "") != "failed", source.name + "\n" + log_text
        assert result_text or win._csv_rows, source.name
        assert "Traceback" not in log_text, source.name
    finally:
        if win._has_running_worker():
            win._stop_current_worker()
            qtbot.waitUntil(lambda: not win._has_running_worker(), timeout=10000)
        win.close()


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
