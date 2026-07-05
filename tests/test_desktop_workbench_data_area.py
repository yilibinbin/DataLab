from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget, QTableWidgetItem


def _expected_table_height_for_rows(table: Any, rows: int) -> int:
    row_height = table.rowHeight(0) if table.rowCount() > 0 else 24
    if row_height <= 0:
        row_height = 24
    header = table.horizontalHeader()
    header_height = 0
    if not header.isHidden():
        header_height = header.height() or 25
        if header_height <= 0:
            header_height = 25
    return header_height + (rows * row_height) + (table.frameWidth() * 2) + 4


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_actual_data_editor_lives_in_left_input_area(qtbot: Any) -> None:
    window = _window(qtbot)

    # Two-pane layout: the input section lives in the merged workspace pane.
    assert window.input_section.parentWidget() is window.workbench_workspace_content
    assert window.manual_box.parentWidget() is window.input_section
    assert window.input_section_layout.indexOf(window.manual_box) >= 0
    assert window.manual_table.parentWidget() is window._data_stack
    assert window.manual_data_edit.parentWidget() is window._data_stack
    assert window.file_box.parentWidget() is window.input_section


def test_manual_data_card_has_title_and_live_summary(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.manual_box.property("datalab_data_card") is True
    title = window.findChild(QLabel, "manual_data_title")
    summary = window.findChild(QLabel, "manual_data_summary")
    assert title is not None
    assert summary is not None
    assert title.text() in {"输入数据", "Data input"}
    assert "0" in summary.text()

    window.manual_table.setItem(0, 0, QTableWidgetItem("1.0"))
    QApplication.processEvents()

    assert "1" in summary.text()
    assert str(window.manual_table.columnCount()) in summary.text()


def test_manual_data_summary_refreshes_on_language_change(qtbot: Any) -> None:
    window = _window(qtbot)

    summary = window.findChild(QLabel, "manual_data_summary")
    assert summary is not None

    window._apply_language("zh")
    QApplication.processEvents()
    assert "行" in summary.text()
    assert "列" in summary.text()

    window._apply_language("en")
    QApplication.processEvents()
    assert "rows" in summary.text()
    assert "columns" in summary.text()


def test_manual_data_help_mentions_sectioned_constants_and_uncertainty(qtbot: Any) -> None:
    window = _window(qtbot)

    window._apply_language("en")
    en_placeholder = window.manual_data_edit.placeholderText()
    assert "[data]" in en_placeholder
    assert "[constants]" in en_placeholder
    assert "Non-empty constants are used automatically" in en_placeholder
    assert "1.23(4)[-5]" in en_placeholder

    window._apply_language("zh")
    zh_placeholder = window.manual_data_edit.placeholderText()
    assert "[data]" in zh_placeholder
    assert "[constants]" in zh_placeholder
    assert "非空常数会自动参与" in zh_placeholder
    assert "1.23(4)[-5]" in zh_placeholder


def test_manual_data_card_uses_shared_theme_and_compact_toolbar(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.manual_box.property("datalab_data_card") is True
    assert "QGroupBox#manual_box" in window.manual_box.styleSheet()
    assert "datalab_data_toolbar_button" in window.manual_box.styleSheet()

    buttons = [
        button
        for button in window.manual_box.findChildren(QPushButton)
        if button.property("datalab_data_toolbar_button") is True
    ]
    assert len(buttons) >= 6


def test_data_card_theme_refresh_does_not_recompute_summary(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.panels as panels

    window = _window(qtbot)
    calls = 0

    def count_summary_refresh(owner: Any) -> None:
        nonlocal calls
        assert owner is window
        calls += 1

    monkeypatch.setattr(panels, "_update_data_summary", count_summary_refresh)

    window.refresh_workbench_data_card()
    assert calls == 0

    window.refresh_workbench_data_summary()
    assert calls == 1


def test_data_input_state_is_not_duplicated_or_mirrored(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.findChild(type(window.manual_table), "workbench_data_preview_table") is None
    window._data_view_toggle.click()
    QApplication.processEvents()
    assert window._data_stack.currentWidget() is window.manual_data_edit
    window._data_view_toggle.click()
    QApplication.processEvents()
    assert window._data_stack.currentWidget() is window.manual_table


def test_active_input_bundle_parses_sectioned_text_and_prefers_editor_constants(qtbot: Any) -> None:
    window = _window(qtbot)
    window._data_stack.setCurrentIndex(1)
    window.manual_data_edit.setPlainText(
        "[data]\n"
        "x y\n"
        "1 2\n"
        "\n"
        "[constants]\n"
        "K = 1\n"
    )

    bundle = window._active_input_bundle()

    assert bundle.data_path is None
    assert bundle.data_text == "x y\n1 2"
    assert bundle.constants_text == "K = 1"
    assert bundle.constants_rows == ({"name": "K", "value": "1"},)
    assert bundle.explicit_sections is True
    assert window._active_data_source() == (None, "x y\n1 2")

    window.input_constants_editor.set_rows([{"name": "K", "value": "2"}])
    bundle = window._active_input_bundle()

    assert bundle.constants_text == "K 2"
    assert bundle.constants_rows == ({"name": "K", "value": "2"},)


def test_active_input_bundle_parses_sectioned_file_without_regressing_plain_files(qtbot: Any, tmp_path: Any) -> None:
    window = _window(qtbot)
    plain = tmp_path / "plain.txt"
    plain.write_text("x y\n1 2\n", encoding="utf-8")
    sectioned = tmp_path / "sectioned.txt"
    sectioned.write_text("[data]\nx y\n1 2\n\n[constants]\nK = 3\n", encoding="utf-8")

    window.use_file_checkbox.setChecked(True)
    window.data_file_edit.setText(str(plain))
    plain_bundle = window._active_input_bundle()

    assert plain_bundle.data_path == plain
    assert plain_bundle.data_text == ""
    assert plain_bundle.constants_rows == ()
    assert window._active_data_source() == (plain, "")

    window.data_file_edit.setText(str(sectioned))
    sectioned_bundle = window._active_input_bundle()

    assert sectioned_bundle.data_path is None
    assert sectioned_bundle.data_text == "x y\n1 2"
    assert sectioned_bundle.constants_rows == ({"name": "K", "value": "3"},)
    assert window._active_data_source() == (None, "x y\n1 2")


def test_left_rail_sections_are_ordered_input_first(qtbot: Any) -> None:
    window = _window(qtbot)

    section_names = [
        item.widget().objectName()
        for index in range(window.left_layout.count())
        if (item := window.left_layout.itemAt(index)).widget() is not None
    ]

    # Two-pane layout: the merged pane starts with 输入 (input_section) and ends with
    # the output/run footer; the per-mode config panels sit in between. The mode
    # selector moved to the toolbar.
    assert section_names[0] == "input_section"
    assert section_names[-2:] == ["output_setup_section", "run_section"]
    assert "mode_section" not in section_names


def test_empty_manual_table_uses_one_editable_draft_row(qtbot: Any) -> None:
    window = _window(qtbot)
    table = window.manual_table

    assert table.rowCount() == 1
    assert table.columnCount() == 3
    assert table.item(0, 0) is None
    assert table.minimumHeight() == table.maximumHeight()
    assert table.maximumHeight() == _expected_table_height_for_rows(table, 1)


def test_manual_table_height_grows_caps_and_shrinks_on_clear(qtbot: Any) -> None:
    from app_desktop.panels import _add_table_row, _clear_table

    window = _window(qtbot)
    table = window.manual_table
    one_row_height = _expected_table_height_for_rows(table, 1)
    max_row_height = _expected_table_height_for_rows(table, 8)

    assert table.maximumHeight() == one_row_height

    for row in range(9):
        if row >= table.rowCount():
            _add_table_row(window)
        table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
    QApplication.processEvents()

    assert table.maximumHeight() == max_row_height

    _clear_table(window)
    QApplication.processEvents()

    assert table.rowCount() == 1
    assert table.maximumHeight() == one_row_height


def test_text_view_round_trip_height_uses_populated_rows_plus_draft(qtbot: Any) -> None:
    window = _window(qtbot)

    window._data_view_toggle.click()
    window.manual_data_edit.setPlainText("A\tB\n1\t2\n3\t4\n")
    window._data_view_toggle.click()
    QApplication.processEvents()

    assert window.manual_table.rowCount() == 3
    assert window.manual_table.maximumHeight() == _expected_table_height_for_rows(window.manual_table, 3)


def test_text_table_load_refreshes_summary_once(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.panels as panels

    window = _window(qtbot)
    calls = 0

    def count_summary_refresh(owner: Any) -> None:
        nonlocal calls
        assert owner is window
        calls += 1

    monkeypatch.setattr(panels, "_update_data_summary", count_summary_refresh)

    panels._load_text_into_table(
        window,
        "A\tB\tC\n"
        + "\n".join(f"{index}\t{index + 1}\t{index + 2}" for index in range(20)),
    )

    assert calls == 1


def test_text_to_table_toggle_refreshes_summary_once(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.panels as panels

    window = _window(qtbot)
    window._data_view_toggle.click()
    window.manual_data_edit.setPlainText("A\tB\n1\t2\n3\t4\n")
    calls = 0

    def count_summary_refresh(owner: Any) -> None:
        nonlocal calls
        assert owner is window
        calls += 1

    monkeypatch.setattr(panels, "_update_data_summary", count_summary_refresh)

    window._data_view_toggle.click()

    assert window._data_stack.currentWidget() is window.manual_table
    assert calls == 1


def test_table_height_excludes_hidden_horizontal_header(qtbot: Any) -> None:
    from app_desktop.views import helpers as view_helpers

    table = QTableWidget(1, 2)
    qtbot.addWidget(table)
    table.horizontalHeader().setVisible(False)
    table.show()
    QApplication.processEvents()

    view_helpers.fit_table_height_to_contents(table)

    assert table.maximumHeight() == _expected_table_height_for_rows(table, 1)


def test_configuration_sections_live_in_the_merged_pane(qtbot: Any) -> None:
    window = _window(qtbot)
    merged = window.workbench_workspace_content
    # Two-pane layout: the config sections merged into the workspace pane.
    # mode_section moved to the toolbar (parented to neither pane's content).
    assert window.mode_section.parentWidget() is not merged
    assert window.mode_section.parentWidget() is not window.workbench_config_content
    assert window.input_section.parentWidget() is merged
    assert window.output_setup_section.parentWidget() is merged
    assert window.run_section.parentWidget() is merged
