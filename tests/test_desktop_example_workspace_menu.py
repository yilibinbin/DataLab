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

    # The toolbar run button carries the execute shortcut (the bottom 开始执行 button that
    # used to own it was removed in 4·4c).
    assert not win.workbench_run_button.shortcut().isEmpty()
    assert win.workbench_run_button.shortcut() == QKeySequence("Ctrl+Return")


def test_run_state_survives_language_switch(qtbot):
    """Switching language mid-run must keep the run-state consistent. The bottom 开始执行
    toggle was removed (4·4c); run-state lives on _datalab_run_state and drives the toolbar
    运行/停止 pair. A language switch replays retranslation (which re-runs the state setter),
    so a running (stop) state must survive it — 运行 stays disabled, 停止 enabled — and the
    Ctrl+Return shortcut must stay installed on the toolbar run button.
    """
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)

    win._apply_language("zh")
    win._set_button_to_stop_mode()
    assert win._datalab_run_state == "stop"
    assert win.workbench_run_button.isEnabled() is False
    assert win.workbench_stop_button.isEnabled() is True

    win._apply_language("en")
    # Still in stop state after the language switch.
    assert win._datalab_run_state == "stop"
    assert win.workbench_run_button.isEnabled() is False
    assert win.workbench_stop_button.isEnabled() is True
    assert not win.workbench_run_button.shortcut().isEmpty()

    # Returning to run state re-enables 运行 and disables 停止.
    win._set_button_to_run_mode()
    assert win._datalab_run_state == "run"
    assert win.workbench_run_button.isEnabled() is True
    assert win.workbench_stop_button.isEnabled() is False
    win._apply_language("zh")
    assert win._datalab_run_state == "run"
    assert win.workbench_run_button.isEnabled() is True
    assert not win.workbench_run_button.shortcut().isEmpty()


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
        assert win.workbench_run_button.isEnabled()
        assert win.result_edit.toPlainText().strip()
        if win.workbench_formula_panel.isVisible():
            assert _formula_preview_has_content(win), source.name


def test_example_workspaces_keep_manual_table_editable(qtbot):
    """User-reported: after opening an example (e.g. 外推示例), the +列/-列/+行/-行
    table-editing buttons were dead. Cause: example workspaces ship in "file"
    data-source mode whose source_path is a RELATIVE path into examples/. When the
    app runs from the repo root that path resolves, so the file-precedence rule
    grey-disabled the whole manual_box (table + toolbar). The example rows are
    inlined into the table anyway, so a template open must land in editable manual
    mode — the bundled file path is not the user's live data source.
    """
    from PySide6.QtWidgets import QAbstractButton, QGroupBox

    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)
    # Pin the language so the button-label match is deterministic regardless of the
    # runner's system locale (CI defaults to English).
    win._apply_language("zh")

    editing_labels = {"+ 列", "- 列", "+ 行", "- 行", "清除", "文本视图"}
    for source in list_example_workspaces():
        assert win._open_workspace_from_path(source, as_template=True), source.name
        # The bundled relative file path must not linger as an active data source.
        assert win.data_file_edit.text().strip() == "", source.name
        # The manual data box + every editing button are enabled and editable.
        manual_box = win.findChild(QGroupBox, "manual_box")
        assert manual_box is not None and manual_box.isEnabled(), source.name
        assert win.manual_table.isEnabled(), source.name
        buttons = {
            b.text(): b
            for b in manual_box.findChildren(QAbstractButton)
            if b.text() in editing_labels
        }
        assert editing_labels <= set(buttons), source.name
        assert all(b.isEnabled() for b in buttons.values()), source.name
        # The example rows survive the fall-back to manual mode (data not lost).
        assert win.manual_table.rowCount() > 0, source.name
        # And a table edit actually takes effect (button is live, not just enabled).
        before = win.manual_table.columnCount()
        buttons["+ 列"].click()
        QApplication.processEvents()
        assert win.manual_table.columnCount() == before + 1, source.name


def test_example_with_file_mode_constants_keeps_constants_editor_editable(qtbot):
    """Same file-precedence bug as the data table, but for the CONSTANTS editor:
    error-propagation.datalab ships its constants in "file" mode (source_path
    examples/constants.txt). Opening it as a template must clear the bundled
    constants path too, so the constants editor + its +行/-行/清除 buttons stay
    editable and the inlined constants rows survive.
    """
    from PySide6.QtWidgets import QAbstractButton, QTableWidget, QWidget

    from app_desktop.window import ExtrapolationWindow, list_example_workspaces

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    _allow_discard(win)
    qtbot.addWidget(win)
    win._apply_language("zh")

    source = next(p for p in list_example_workspaces() if p.name == "error-propagation.datalab")
    assert win._open_workspace_from_path(source, as_template=True)

    # The bundled constants file path must not linger and disable the editor.
    assert win.constants_file_edit.text().strip() == ""
    editor = win.findChild(QWidget, "input_constants_editor")
    assert editor is not None and editor.isEnabled()
    labels = {"+ 行", "- 行", "清除"}
    buttons = {b.text(): b for b in editor.findChildren(QAbstractButton) if b.text() in labels}
    assert labels <= set(buttons)
    assert all(b.isEnabled() for b in buttons.values())
    # The inlined constants rows survive the fall-back to manual mode.
    table = editor.findChild(QTableWidget)
    assert table is not None and table.rowCount() > 0


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
        # generate_latex_checkbox removed in 4·4d — run never writes tex, so no toggle needed.
        win.generate_plots_checkbox.setChecked(False)
        # The implicit example ships a 300s self-consistent-fit timeout. On slow
        # shared CI runners (~2-3x slower, suite run concurrently) the fit needs
        # more than 300s and self-aborts as "failed" — an environment artifact,
        # not a logic error. Disable the internal cap for the test (0 = no auto
        # timeout); the qtbot.waitUntil budget below still bounds the run, so a
        # genuine hang is still caught.
        if "implicit" in example_name and hasattr(win, "implicit_timeout_spin"):
            win.implicit_timeout_spin.setValue(0)
        win.run_calculation()
        # The implicit (self-consistent) example runs a per-point inner root-find
        # for every seed variant, so it is far heavier than the others (~1-2 min
        # locally). Shared CI runners are ~2-3x slower and run the suite
        # concurrently, so give the wait a generous 600s budget (a genuine stall
        # still trips it, just later).
        run_timeout_ms = 600000 if "implicit" in example_name else 120000
        qtbot.waitUntil(
            lambda: getattr(win, "_workbench_result_state", "") != "running" and not win._has_running_worker(),
            timeout=run_timeout_ms,
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
