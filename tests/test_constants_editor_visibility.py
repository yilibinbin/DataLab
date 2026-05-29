from __future__ import annotations


def test_constants_editor_hides_inputs_when_disabled_and_preserves_draft(qtbot):
    from app_desktop.constants_editor import ConstantsEditor

    editor = ConstantsEditor(checked=True)
    qtbot.addWidget(editor)
    editor.set_rows([{"name": "CR", "value": "3.2898419602500(36)[+9]"}])

    editor.setChecked(False)
    assert not editor.controls_widget.isVisible()
    assert not editor.stack.isVisible()
    assert editor.constants_dict(validate=False) == {"CR": "3.2898419602500(36)[+9]"}

    editor.setChecked(True)
    assert editor.controls_widget.isVisible()
    assert editor.stack.isVisible()
