"""Desktop constants text-view toggle — regression tests.

The data-input table has a "Table ⇄ Text" toggle that turns the
QTableWidget into a QPlainTextEdit for bulk paste / edit. The
constants section (for error-propagation) should have the same
toggle so users can paste a text block like::

    ALPHA 7.2973525693(11)[-3]
    RYDBERG 10973731.568160(21)

These tests pin the feature's contract so a future refactor can't
silently drop it.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def _window(_app, qtbot):
    from app_desktop.window import ExtrapolationWindow

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    yield win
    win.close()


def test_constants_view_toggle_button_exists(_window):
    """The constants toolbar must expose a toggle button just like the
    data table."""
    assert hasattr(_window, "_constants_view_toggle"), (
        "constants toolbar must expose _constants_view_toggle for "
        "table/text switching"
    )


def test_constants_text_edit_exists(_window):
    """The ``manual_constants_edit`` attribute must be a real widget,
    not None — it was set to None in baseline but should now hold a
    QPlainTextEdit so the i18n mixin's ``setPlaceholderText`` call
    works against a real widget."""
    assert _window.manual_constants_edit is not None
    # Widget must accept plain text input
    _window.manual_constants_edit.setPlainText("ALPHA 1.5")
    assert _window.manual_constants_edit.toPlainText() == "ALPHA 1.5"


def test_constants_stack_defaults_to_table_view(_window):
    """Initial view is the table, matching the data-entry area."""
    assert hasattr(_window, "_constants_stack")
    assert _window._constants_stack.currentIndex() == 0


def test_constants_toggle_switches_to_text_view(_window):
    """Click toggle → stack shows text edit; click again → back to table."""
    from app_desktop.panels import _toggle_constants_view

    # Populate the table so serialization has something to show
    _window.constants_table.setItem(0, 0, _make_item("ALPHA"))
    _window.constants_table.setItem(0, 1, _make_item("7.2973525693(11)[-3]"))

    _toggle_constants_view(_window)
    assert _window._constants_stack.currentIndex() == 1, (
        "after toggle, should show text view"
    )
    # Text view must reflect the table contents
    text = _window.manual_constants_edit.toPlainText()
    assert "ALPHA" in text
    assert "7.2973525693(11)[-3]" in text

    _toggle_constants_view(_window)
    assert _window._constants_stack.currentIndex() == 0, (
        "toggle again should go back to table"
    )


def test_constants_text_to_table_roundtrip(_window):
    """Text entered in text view flushes to the table on toggle-back."""
    from app_desktop.panels import _toggle_constants_view

    # Go to text view
    _toggle_constants_view(_window)
    _window.manual_constants_edit.setPlainText(
        "BETA 1.234\n"
        "GAMMA 5.6789"
    )
    # Toggle back to table
    _toggle_constants_view(_window)
    # Table must now contain the typed values
    found = {
        _cell(_window.constants_table, r, 0): _cell(_window.constants_table, r, 1)
        for r in range(_window.constants_table.rowCount())
    }
    assert found.get("BETA") == "1.234"
    assert found.get("GAMMA") == "5.6789"


def test_constants_toggle_label_reflects_current_view(_window):
    """Button text must flip between "文本视图" and "表格视图"
    to communicate what the next click will do."""
    from app_desktop.panels import _toggle_constants_view

    initial = _window._constants_view_toggle.text()
    _toggle_constants_view(_window)
    after = _window._constants_view_toggle.text()
    assert initial != after, "toggle must change button label"


def test_constants_text_view_accepts_tab_separated(_window):
    """Pasted tab-separated values parse the same as space-separated."""
    from app_desktop.panels import _toggle_constants_view

    _toggle_constants_view(_window)
    _window.manual_constants_edit.setPlainText("ALPHA\t1.5e-3\nBETA\t2.5e-4")
    _toggle_constants_view(_window)
    names = [
        _cell(_window.constants_table, r, 0)
        for r in range(_window.constants_table.rowCount())
    ]
    values = [
        _cell(_window.constants_table, r, 1)
        for r in range(_window.constants_table.rowCount())
    ]
    assert "ALPHA" in names
    assert "BETA" in names
    assert any("1.5e-3" in v or v == "0.0015" for v in values)


# ---- helpers ---------------------------------------------------------


def _make_item(text: str):
    from PySide6.QtWidgets import QTableWidgetItem

    return QTableWidgetItem(text)


def _cell(table, row: int, col: int) -> str:
    item = table.item(row, col)
    return "" if item is None else item.text().strip()
