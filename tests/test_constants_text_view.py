"""Desktop constants text-view toggle — regression tests.

The data-input table has a "Table ⇄ Text" toggle that turns the
QTableWidget into a QPlainTextEdit for bulk paste / edit. The
constants section (for error-propagation) should have the same
toggle so users can paste a text block like::

    ALPHA 7.2973525693(11)[-3]
    RYDBERG 10973731.568160(21)

These tests pin the feature's contract so a future refactor can't
silently drop it. Two layers of coverage:

1. Window-level integration via a real ``ExtrapolationWindow``
   (``_window`` fixture) — verifies the button + stack widget are
   actually wired into the constructed window.
2. Helper-level unit tests on a tiny ``_Holder`` stand-in (``holder``
   fixture) — exercises the pure helpers without instantiating the
   full window so the round-trip / parser / toggle-state contracts
   are pinned independently of mixin assembly.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
)

from app_desktop.panels import (  # noqa: E402
    _load_text_into_constants_table,
    _serialize_constants_table,
    _serialize_constants_table_as_text,
    _toggle_constants_view,
)
from datalab_latex.latex_tables_error_propagation import (  # noqa: E402
    process_constants_string,
)


# ---------------------------------------------------------------------------
# Window-level integration fixture
# ---------------------------------------------------------------------------


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
    _window.manual_constants_edit.setPlainText("ALPHA 1.5")
    assert _window.manual_constants_edit.toPlainText() == "ALPHA 1.5"


def test_constants_stack_defaults_to_table_view(_window):
    """Initial view is the table, matching the data-entry area."""
    assert hasattr(_window, "_constants_stack")
    assert _window._constants_stack.currentIndex() == 0


def test_constants_toggle_switches_to_text_view(_window):
    """Click toggle → stack shows text edit; click again → back to table."""
    _window.constants_table.setItem(0, 0, _make_item("ALPHA"))
    _window.constants_table.setItem(0, 1, _make_item("7.2973525693(11)[-3]"))

    _toggle_constants_view(_window)
    assert _window._constants_stack.currentIndex() == 1, (
        "after toggle, should show text view"
    )
    text = _window.manual_constants_edit.toPlainText()
    assert "ALPHA" in text
    assert "7.2973525693(11)[-3]" in text

    _toggle_constants_view(_window)
    assert _window._constants_stack.currentIndex() == 0, (
        "toggle again should go back to table"
    )


def test_constants_text_to_table_roundtrip(_window):
    """Text entered in text view flushes to the table on toggle-back."""
    _toggle_constants_view(_window)
    _window.manual_constants_edit.setPlainText(
        "BETA 1.234\n"
        "GAMMA 5.6789"
    )
    _toggle_constants_view(_window)
    found = {
        _cell(_window.constants_table, r, 0): _cell(_window.constants_table, r, 1)
        for r in range(_window.constants_table.rowCount())
    }
    assert found.get("BETA") == "1.234"
    assert found.get("GAMMA") == "5.6789"


def test_constants_toggle_label_reflects_current_view(_window):
    """Button text must flip between "文本视图" and "表格视图"
    to communicate what the next click will do."""
    initial = _window._constants_view_toggle.text()
    _toggle_constants_view(_window)
    after = _window._constants_view_toggle.text()
    assert initial != after, "toggle must change button label"


def test_constants_text_view_accepts_tab_separated(_window):
    """Pasted tab-separated values parse the same as space-separated."""
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


def _make_item(text: str):
    return QTableWidgetItem(text)


def _cell(table, row: int, col: int) -> str:
    item = table.item(row, col)
    return "" if item is None else item.text().strip()


# ---------------------------------------------------------------------------
# Helper-level unit tests on a minimal holder
# ---------------------------------------------------------------------------


class _Holder:
    """Stand-in for ``ExtrapolationWindow`` exposing only the attributes the
    constants helpers touch. Keeps the test hermetic and fast — no full
    window instantiation, no mixin stack, no data panels."""

    def __init__(self) -> None:
        self.constants_table = QTableWidget(4, 2)
        self.constants_table.setHorizontalHeaderLabels(["Name", "Value"])
        self.manual_constants_edit = QPlainTextEdit()
        self._constants_stack = QStackedWidget()
        self._constants_stack.addWidget(self.constants_table)
        self._constants_stack.addWidget(self.manual_constants_edit)
        self._constants_stack.setCurrentIndex(0)
        self._constants_view_toggle = QPushButton("文本视图")
        # Neutral translator — tests don't exercise language switching.
        self._tr = lambda zh, en: zh

    def _populate_table(self, rows: list[tuple[str, str]]) -> None:
        self.constants_table.setRowCount(max(len(rows), 4))
        for r, (name, val) in enumerate(rows):
            self.constants_table.setItem(r, 0, QTableWidgetItem(name))
            self.constants_table.setItem(r, 1, QTableWidgetItem(val))


@pytest.fixture
def holder(qtbot):
    # qtbot ensures a QApplication exists; we don't attach the widgets to
    # the bot because they're never shown — pure serializer round-trips.
    return _Holder()


# ---------------------------------------------------------------------------
# _serialize_constants_table_as_text — table → text seed
# ---------------------------------------------------------------------------


def test_text_seed_has_one_name_value_per_line(holder):
    """Rows serialize to ``name value`` — the format the parser expects."""
    holder._populate_table([("ALPHA", "7.2973525693(11)[-3]"), ("G", "6.674e-11")])
    text = _serialize_constants_table_as_text(holder)
    assert text == "ALPHA 7.2973525693(11)[-3]\nG 6.674e-11"


def test_text_seed_skips_blank_rows(holder):
    """Empty table rows must not leak into the text buffer."""
    holder.constants_table.setRowCount(5)
    holder.constants_table.setItem(0, 0, QTableWidgetItem("PI"))
    holder.constants_table.setItem(0, 1, QTableWidgetItem("3.14159"))
    text = _serialize_constants_table_as_text(holder)
    assert text == "PI 3.14159"


# ---------------------------------------------------------------------------
# _load_text_into_constants_table — text → table
# ---------------------------------------------------------------------------


def test_load_text_populates_rows_in_order(holder):
    text = "ALPHA 7.2973525693(11)[-3]\nG 6.674e-11\nC 2.998e8"
    _load_text_into_constants_table(holder, text)
    assert holder.constants_table.item(0, 0).text() == "ALPHA"
    assert holder.constants_table.item(0, 1).text() == "7.2973525693(11)[-3]"
    assert holder.constants_table.item(1, 0).text() == "G"
    assert holder.constants_table.item(2, 0).text() == "C"


def test_load_text_skips_comments_and_blanks(holder):
    text = (
        "# physical constants\n"
        "\n"
        "ALPHA 7.2973525693(11)[-3]\n"
        "   # another comment indented\n"
        "\n"
        "G 6.674e-11\n"
    )
    _load_text_into_constants_table(holder, text)
    assert holder.constants_table.item(0, 0).text() == "ALPHA"
    assert holder.constants_table.item(1, 0).text() == "G"
    third = holder.constants_table.item(2, 0)
    assert third is None or third.text() == ""


def test_load_text_empty_input_leaves_minimum_four_rows(holder):
    _load_text_into_constants_table(holder, "")
    assert holder.constants_table.rowCount() == 4
    for r in range(4):
        item = holder.constants_table.item(r, 0)
        assert item is None or item.text() == ""


def test_load_text_accepts_tab_and_multi_space_separators(holder):
    text = "ALPHA\t7.2973525693(11)[-3]\nG    6.674e-11"
    _load_text_into_constants_table(holder, text)
    assert holder.constants_table.item(0, 1).text() == "7.2973525693(11)[-3]"
    assert holder.constants_table.item(1, 1).text() == "6.674e-11"


# ---------------------------------------------------------------------------
# _serialize_constants_table — worker-facing serializer
# ---------------------------------------------------------------------------


def test_serialize_uses_table_when_table_view_active(holder):
    holder._populate_table([("PI", "3.14159"), ("E", "2.71828")])
    out = _serialize_constants_table(holder)
    assert out == "PI\t3.14159\nE\t2.71828"


def test_serialize_uses_text_buffer_when_text_view_active(holder):
    holder._constants_stack.setCurrentIndex(1)
    holder.manual_constants_edit.setPlainText(
        "# Freeform comments survive the trip to the worker\n"
        "ALPHA 7.2973525693(11)[-3]\n"
        "G 6.674e-11\n"
    )
    out = _serialize_constants_table(holder)
    assert "# Freeform comments" in out
    assert "ALPHA 7.2973525693(11)[-3]" in out
    assert "G 6.674e-11" in out


# ---------------------------------------------------------------------------
# End-to-end: text buffer survives downstream parsing
# ---------------------------------------------------------------------------


def test_text_buffer_parses_through_process_constants_string(holder):
    """The canonical downstream parser must accept everything the text
    view emits — comments, blanks, tabs, mixed spaces."""
    holder._constants_stack.setCurrentIndex(1)
    holder.manual_constants_edit.setPlainText(
        "# block of physical constants, R10 regression\n"
        "\n"
        "ALPHA 7.2973525693(11)[-3]\n"
        "G\t6.674e-11\n"
        "C    2.998e8\n"
    )
    text = _serialize_constants_table(holder)
    parsed = process_constants_string(text)
    assert set(parsed.keys()) == {"ALPHA", "G", "C"}


# ---------------------------------------------------------------------------
# _toggle_constants_view — stack page + button label
# ---------------------------------------------------------------------------


def test_toggle_table_to_text_seeds_buffer_from_table(holder):
    holder._populate_table([("PI", "3.14159")])
    assert holder._constants_stack.currentIndex() == 0
    _toggle_constants_view(holder)
    assert holder._constants_stack.currentIndex() == 1
    assert "PI 3.14159" in holder.manual_constants_edit.toPlainText()
    assert holder._constants_view_toggle.text() == "表格视图"


def test_toggle_table_to_text_preserves_existing_user_text(holder):
    """If the user has typed into the text buffer already, switching
    table→text must not clobber their work with a re-seed from the
    (possibly empty) table."""
    holder._populate_table([("PI", "3.14159")])
    holder.manual_constants_edit.setPlainText("# my notes\nE 2.71828\n")
    _toggle_constants_view(holder)
    buf = holder.manual_constants_edit.toPlainText()
    assert "# my notes" in buf
    assert "E 2.71828" in buf
    assert "PI 3.14159" not in buf


def test_toggle_text_to_table_parses_buffer_into_rows(holder):
    holder._constants_stack.setCurrentIndex(1)
    holder._constants_view_toggle.setText("表格视图")
    holder.manual_constants_edit.setPlainText(
        "# comment\nALPHA 7.2973525693(11)[-3]\nG 6.674e-11"
    )
    _toggle_constants_view(holder)
    assert holder._constants_stack.currentIndex() == 0
    assert holder.constants_table.item(0, 0).text() == "ALPHA"
    assert holder.constants_table.item(1, 0).text() == "G"
    assert holder._constants_view_toggle.text() == "文本视图"
