from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from app_desktop.constants_editor import ConstantsEditor
from datalab_latex.latex_tables_error_propagation import process_constants_string


def test_text_view_button_switches_between_table_and_text(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_rows([{"name": "PI", "value": "3.14159"}])

    assert not editor.using_text_view()
    editor.use_text_view(True)

    assert editor.using_text_view()
    assert editor.text() == "PI 3.14159"

    editor.use_text_view(False)
    assert not editor.using_text_view()


def test_text_view_accepts_equals_spaces_tabs_comments_and_blanks(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_text(
        "# physical constants\n"
        "\n"
        "ALPHA = 7.2973525693(11)[-3]\n"
        "G\t6.674e-11\n"
        "C    2.998e8\n"
    )
    editor.use_text_view(True)

    assert editor.rows() == [
        {"name": "ALPHA", "value": "7.2973525693(11)[-3]"},
        {"name": "G", "value": "6.674e-11"},
        {"name": "C", "value": "2.998e8"},
    ]
    assert set(editor.constants_dict(validate=True)) == {"ALPHA", "G", "C"}


def test_text_buffer_parses_through_error_propagation_constants_parser(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_text(
        "# block of physical constants\n"
        "\n"
        "ALPHA = 7.2973525693(11)[-3]\n"
        "G\t6.674e-11\n"
        "C    2.998e8\n"
    )
    editor.use_text_view(True)

    parsed = process_constants_string(editor.text())

    assert set(parsed.keys()) == {"ALPHA", "G", "C"}


def test_switching_to_table_keeps_text_rows_available(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_text("ALPHA = 1.5e-3\nBETA 2.5e-4")
    editor.use_text_view(True)

    editor.use_text_view(False)

    assert editor.rows() == [
        {"name": "ALPHA", "value": "1.5e-3"},
        {"name": "BETA", "value": "2.5e-4"},
    ]
    assert editor.text() == "ALPHA 1.5e-3\nBETA 2.5e-4"


def test_table_edits_replace_stale_hidden_text_when_switching_to_text(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_rows([{"name": "PI", "value": "3"}])

    editor.use_text_view(True)
    editor.use_text_view(False)
    editor.set_rows([{"name": "E", "value": "2"}])
    editor.use_text_view(True)

    assert editor.raw_text() == "E 2"
    assert editor.text() == "E 2"
    assert editor.rows() == [{"name": "E", "value": "2"}]
