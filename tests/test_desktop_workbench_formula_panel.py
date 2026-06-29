from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_formula_workspace_panel_mounts_existing_editors(qtbot: Any) -> None:
    window = _window(qtbot)
    panel = window.findChild(QWidget, "workbench_formula_panel")

    assert panel is not None
    assert window.workbench_formula_preview_label.parentWidget() is panel
    assert window.fit_expr_edit.parentWidget().objectName() == "workbench_formula_editor_wrap_fit_expr_edit"
    assert window.fit_expr_edit.parentWidget().property("datalab_state_role") is None
    assert window.fit_expr_edit in panel.findChildren(type(window.fit_expr_edit))
    assert window.fit_formula_preview_button.parentWidget() is not None


def test_formula_workspace_uses_single_visible_formula_title(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    header, _editor = window._workbench_formula_mount_widgets["fit_expr_edit"]

    assert window.workbench_formula_panel_title.text() == "公式预览"
    assert header.schema_label.isVisible() is False
    assert window.workbench_formula_actions_stack.currentWidget() is header


def test_formula_workspace_moves_formula_actions_to_title_row(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    action_page = window.workbench_formula_actions_stack.currentWidget()

    assert action_page.objectName() == "workbench_formula_actions_root_equations_edit"
    assert window.root_formula_preview_button.parentWidget() is action_page
    assert window.root_equations_help_button.parentWidget() is action_page
    header, _editor = window._workbench_formula_mount_widgets["root_equations_edit"]
    assert action_page is header
    assert header.schema_label.isVisible() is False


def test_formula_workspace_has_no_preview_language_selector(qtbot: Any) -> None:
    window = _window(qtbot)

    assert not hasattr(window, "workbench_formula_language_row")
    assert not hasattr(window, "workbench_formula_language_label")
    assert not hasattr(window, "workbench_formula_language_combo")


def test_formula_workspace_ignores_legacy_preview_language_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window._workbench_formula_preview_languages = {
        "fitting.custom.expression": "latex"
    }

    window.refresh_workbench_formula_panel()

    assert not hasattr(window, "workbench_formula_language_combo")
    assert window.workbench_formula_preview_label.text() or not window.workbench_formula_preview_label.pixmap().isNull()


def test_formula_workspace_spec_duplicate_guards_report_editor_and_schema_keys(
    monkeypatch: Any,
) -> None:
    from app_desktop import workbench_formula_panel as panel
    from app_desktop.workbench_specs import FormulaMount, ModeWorkbenchSpec

    monkeypatch.setattr(
        panel,
        "MODE_WORKBENCH_SPECS",
        {
            "extrapolation": ModeWorkbenchSpec(
                mode_key="extrapolation",
                mode_stack_index=0,
                formulas=(
                    FormulaMount("shared_editor", "first_preview", "first.formula"),
                ),
            ),
            "error": ModeWorkbenchSpec(
                mode_key="error",
                mode_stack_index=1,
                formulas=(
                    FormulaMount("shared_editor", "second_preview", "second.formula"),
                    FormulaMount("third_editor", "third_preview", "first.formula"),
                ),
            ),
        },
    )

    assert panel._duplicate_formula_editor_attrs() == ["shared_editor"]
    assert panel._duplicate_formula_schema_keys() == ["first.formula"]


def test_formula_workspace_actions_fall_back_to_empty_page(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import _show_formula_actions
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    window = _window(qtbot)
    mount = MODE_WORKBENCH_SPECS["fitting"].formulas[0]
    window._workbench_formula_action_pages.pop(mount.editor_attr, None)

    _show_formula_actions(window, mount)

    assert window.workbench_formula_actions_stack.currentWidget() is window.workbench_formula_empty_actions_page


def test_formula_header_lookup_does_not_cross_intervening_widgets(qtbot: Any) -> None:
    from PySide6.QtWidgets import QPlainTextEdit, QPushButton, QVBoxLayout

    from app_desktop.workbench_formula_panel import _adjacent_editor_header
    from app_desktop.workbench_specs import FormulaMount

    owner = type("Owner", (), {})()
    parent = QWidget()
    qtbot.addWidget(parent)
    layout = QVBoxLayout(parent)
    header = QWidget()
    header_layout = QVBoxLayout(header)
    owner.preview_button = QPushButton("preview")
    header_layout.addWidget(owner.preview_button)
    incidental = QWidget()
    incidental.schema_label = object()
    editor = QPlainTextEdit()
    layout.addWidget(header)
    layout.addWidget(incidental)
    layout.addWidget(editor)

    mount = FormulaMount("editor", "preview_button", "test.formula")

    assert _adjacent_editor_header(owner, editor, mount) is None


def test_formula_header_lookup_accepts_immediate_previous_header(qtbot: Any) -> None:
    from PySide6.QtWidgets import QPlainTextEdit, QPushButton, QVBoxLayout

    from app_desktop.workbench_formula_panel import _adjacent_editor_header
    from app_desktop.workbench_specs import FormulaMount

    owner = type("Owner", (), {})()
    parent = QWidget()
    qtbot.addWidget(parent)
    layout = QVBoxLayout(parent)
    header = QWidget()
    header_layout = QVBoxLayout(header)
    owner.preview_button = QPushButton("preview")
    header_layout.addWidget(owner.preview_button)
    editor = QPlainTextEdit()
    layout.addWidget(header)
    layout.addWidget(editor)

    mount = FormulaMount("editor", "preview_button", "test.formula")

    assert _adjacent_editor_header(owner, editor, mount) is header


def test_formula_workspace_has_single_persistent_preview_label(qtbot: Any) -> None:
    from app_desktop.formula_preview import FormulaPreviewLabel

    window = _window(qtbot)

    assert window.findChildren(FormulaPreviewLabel) == [window.workbench_formula_preview_label]


def test_formula_workspace_preview_is_readable_canvas(qtbot: Any) -> None:
    window = _window(qtbot)

    label = window.workbench_formula_preview_label
    assert label.minimumHeight() >= 92
    assert "background: #f8fafc" in label.styleSheet()
    assert "border-radius" in label.styleSheet()


def test_formula_workspace_preview_has_visible_empty_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.clear()
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert "输入公式" in window.workbench_formula_preview_label.text()


def test_formula_workspace_preview_uses_current_editor_text(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_expr_edit.setPlainText("A*x+B")
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert window.workbench_formula_preview_label.text() or not window.workbench_formula_preview_label.pixmap().isNull()


def test_formula_workspace_preview_has_single_rendered_style(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("Sin[x] + Sqrt[A]")
    window.refresh_workbench_formula_panel()

    assert not hasattr(window, "workbench_formula_language_combo")
    assert window.workbench_formula_preview_label.text() or not window.workbench_formula_preview_label.pixmap().isNull()


def test_formula_workspace_description_uses_schema_metadata(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("")
    window.refresh_workbench_formula_panel()

    description = window.workbench_formula_description_label

    assert description.isVisibleTo(window.workbench_formula_panel)
    assert description.property("datalab_schema_key") == "fitting.custom.expression"
    assert "输入自定义拟合表达式" in description.text()
    assert "自定义模型表达式" in description.text()
    assert description.accessibleDescription() == description.text()

    window.fit_expr_edit.setPlainText("a*x + b")
    window.refresh_workbench_formula_panel()

    assert not description.isVisibleTo(window.workbench_formula_panel)
    assert description.property("datalab_schema_key") == "fitting.custom.expression"
    assert "输入自定义拟合表达式" in description.toolTip()
    assert description.accessibleDescription() == description.text()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("")
    window.refresh_workbench_formula_panel()

    assert description.isVisibleTo(window.workbench_formula_panel)
    assert description.property("datalab_schema_key") == "root.equations"
    assert "输入要求解的方程" in description.text()
    assert "x^2 - A" in description.text()

    window.root_equations_edit.setPlainText("x^2 - A")
    window.refresh_workbench_formula_panel()

    assert not description.isVisibleTo(window.workbench_formula_panel)
    assert "输入要求解的方程" in description.toolTip()

    window.root_equations_edit.setPlainText("")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    assert description.isVisibleTo(window.workbench_formula_panel)
    assert "Enter equations to solve" in description.text()
    assert "example: x^2 - a" in description.text().lower()


def test_formula_workspace_function_entry_reuses_function_help(qtbot: Any, monkeypatch: Any) -> None:
    from formula_help import get_function_tooltip

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.refresh_workbench_formula_panel()
    button = window.workbench_formula_function_button

    assert button.isVisibleTo(window.workbench_formula_panel)
    assert button.text() == "函数支持"
    assert button.toolTip() == get_function_tooltip("zh")
    assert button.accessibleDescription() == button.toolTip()
    assert button.parentWidget() is window.workbench_formula_actions_stack.currentWidget()

    called: list[str] = []
    monkeypatch.setattr(window, "_show_error_functions", lambda: called.append("functions"))
    button.click()
    assert called == ["functions"]

    window._apply_language("en")
    window.refresh_workbench_formula_panel()
    assert button.text() == "Functions"
    assert button.toolTip() == get_function_tooltip("en")
    assert button.parentWidget() is window.workbench_formula_actions_stack.currentWidget()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.refresh_workbench_formula_panel()
    assert button.parentWidget().objectName() == "workbench_formula_actions_root_equations_edit"


def test_formula_workspace_action_buttons_do_not_overlap_in_english_self_consistent(
    qtbot: Any,
) -> None:
    window = _window(qtbot)
    window._apply_language("en")
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_equation_edit.setPlainText("u - a*x")
    window.implicit_output_edit.setPlainText("u + b")
    window.implicit_output_edit.setFocus()
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    action_page = window.workbench_formula_actions_stack.currentWidget()
    preview_button = window.implicit_output_preview_button
    function_button = window.workbench_formula_function_button

    assert action_page is preview_button.parentWidget()
    assert action_page is function_button.parentWidget()
    assert preview_button.isVisibleTo(action_page)
    assert function_button.isVisibleTo(action_page)
    assert [
        button
        for button in (
            window.fit_formula_preview_button,
            window.implicit_equation_preview_button,
            window.implicit_output_preview_button,
        )
        if button.isVisibleTo(window)
    ] == [preview_button]
    assert window.workbench_formula_actions_stack.minimumWidth() >= action_page.sizeHint().width()
    assert preview_button.width() >= preview_button.sizeHint().width()
    assert function_button.width() >= function_button.sizeHint().width()
    assert not preview_button.geometry().intersects(function_button.geometry())


def test_formula_workspace_action_stack_width_tracks_current_page(qtbot: Any) -> None:
    from PySide6.QtWidgets import QHBoxLayout, QPushButton

    from app_desktop.workbench_formula_panel import (
        _CurrentPageSizeStack,
        _formula_action_page_required_width,
        _reserve_formula_actions_width,
    )

    class Owner:
        pass

    owner = Owner()
    owner.workbench_formula_actions_stack = _CurrentPageSizeStack()
    qtbot.addWidget(owner.workbench_formula_actions_stack)

    wide_page = QWidget()
    wide_layout = QHBoxLayout(wide_page)
    wide_button = QPushButton("wide")
    wide_button.setMinimumWidth(220)
    wide_layout.addWidget(wide_button)

    narrow_page = QWidget()
    narrow_layout = QHBoxLayout(narrow_page)
    narrow_button = QPushButton("narrow")
    narrow_button.setMinimumWidth(60)
    narrow_layout.addWidget(narrow_button)

    owner.workbench_formula_actions_stack.addWidget(wide_page)
    owner.workbench_formula_actions_stack.addWidget(narrow_page)

    owner.workbench_formula_actions_stack.setCurrentWidget(wide_page)
    _reserve_formula_actions_width(owner, wide_page)
    wide_width = owner.workbench_formula_actions_stack.minimumWidth()
    owner.workbench_formula_actions_stack.setCurrentWidget(narrow_page)
    _reserve_formula_actions_width(owner, narrow_page)

    assert _formula_action_page_required_width(narrow_page) < _formula_action_page_required_width(wide_page)
    assert owner.workbench_formula_actions_stack.minimumWidth() < wide_width
    assert owner.workbench_formula_actions_stack.minimumWidth() == _formula_action_page_required_width(narrow_page)
    assert owner.workbench_formula_actions_stack.minimumSizeHint().width() == narrow_page.minimumSizeHint().width()
    assert owner.workbench_formula_actions_stack.minimumSizeHint().width() < wide_page.minimumSizeHint().width()


def test_formula_action_required_width_includes_fixed_spacers(qtbot: Any) -> None:
    from PySide6.QtWidgets import QHBoxLayout, QPushButton

    from app_desktop.workbench_formula_panel import _formula_action_page_required_width

    page = QWidget()
    qtbot.addWidget(page)
    layout = QHBoxLayout(page)
    layout.setSpacing(8)
    first = QPushButton("first")
    first.setMinimumWidth(100)
    second = QPushButton("second")
    second.setMinimumWidth(120)
    layout.addWidget(first)
    layout.addSpacing(40)
    layout.addWidget(second)
    layout.activate()
    page.adjustSize()

    margins = layout.contentsMargins()
    expected_minimum = margins.left() + margins.right() + 100 + 40 + 120 + (8 * 2)

    assert _formula_action_page_required_width(page) >= expected_minimum


def test_formula_action_required_width_uses_style_spacing_when_layout_inherits_spacing(qtbot: Any) -> None:
    from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStyle

    from app_desktop.workbench_formula_panel import _formula_action_page_required_width

    page = QWidget()
    qtbot.addWidget(page)
    layout = QHBoxLayout(page)
    layout.setSpacing(-1)
    first = QPushButton("first")
    first.setMinimumWidth(100)
    second = QPushButton("second")
    second.setMinimumWidth(120)
    layout.addWidget(first)
    layout.addWidget(second)
    layout.activate()
    page.adjustSize()

    margins = layout.contentsMargins()
    style_spacing = page.style().pixelMetric(QStyle.PixelMetric.PM_LayoutHorizontalSpacing, None, page)
    if style_spacing < 0:
        style_spacing = 6
    expected_minimum = margins.left() + margins.right() + 100 + 120 + style_spacing

    assert _formula_action_page_required_width(page) >= expected_minimum


def test_formula_action_required_width_includes_nested_layouts(qtbot: Any) -> None:
    from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout

    from app_desktop.workbench_formula_panel import _formula_action_page_required_width

    page = QWidget()
    qtbot.addWidget(page)
    outer_layout = QHBoxLayout(page)
    outer_layout.setSpacing(6)
    nested_layout = QVBoxLayout()
    nested_button = QPushButton("nested")
    nested_button.setMinimumWidth(140)
    nested_layout.addWidget(nested_button)
    sibling = QPushButton("sibling")
    sibling.setMinimumWidth(80)
    outer_layout.addLayout(nested_layout)
    outer_layout.addWidget(sibling)
    outer_layout.activate()
    page.adjustSize()

    margins = outer_layout.contentsMargins()
    expected_minimum = (
        margins.left()
        + margins.right()
        + nested_layout.minimumSize().width()
        + sibling.minimumSizeHint().width()
        + outer_layout.spacing()
    )

    assert _formula_action_page_required_width(page) >= expected_minimum


def test_formula_workspace_function_entry_requires_action_page_layout(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import _attach_formula_function_button

    window = _window(qtbot)
    layoutless_page = QWidget()

    with pytest.raises(RuntimeError, match="Formula action page has no layout"):
        _attach_formula_function_button(window, layoutless_page)

    assert window.workbench_formula_function_button.parentWidget() is not layoutless_page


def test_formula_workspace_preview_uses_datalab_render_language(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    from datalab_latex.formula_render_service import InputLanguage, RenderResult

    import app_desktop.formula_preview as preview

    calls: list[InputLanguage] = []

    def fake_render(request: Any) -> RenderResult:
        calls.append(request.language)
        return RenderResult(
            ok=False,
            source=request.source,
            language=request.language,
            latex="",
            mathtext="",
            png_bytes=b"",
            fallback_text=request.source,
            error_message="forced fallback",
        )

    monkeypatch.setattr(preview, "render_desktop_preview", fake_render)
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("Sin[x]")
    window.refresh_workbench_formula_panel()

    assert calls
    assert calls[-1] is InputLanguage.DATALAB


def test_formula_workspace_legacy_language_state_during_restore_does_not_mark_dirty(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.refresh_workbench_formula_panel()
    called: list[str] = []
    monkeypatch.setattr(window, "_mark_workspace_dirty", lambda: called.append("dirty"))

    window._workspace_restoring = True
    window._workbench_formula_preview_languages = {"fitting.custom.expression": "python"}
    window.refresh_workbench_formula_panel()
    assert called == []

    window._workspace_restoring = False
    window._workbench_formula_preview_languages = {"fitting.custom.expression": "mathematica"}
    window.refresh_workbench_formula_panel()
    assert called == []


def test_formula_workspace_refresh_populates_panel_if_needed(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.workbench_formula_panel as formula_panel

    window = _window(qtbot)
    calls: list[bool] = []

    def fake_populate(owner: Any) -> None:
        calls.append(owner is window)
        owner._workbench_formula_populated = True

    monkeypatch.setattr(formula_panel, "populate_formula_workspace_panel", fake_populate)
    window._workbench_formula_populated = False

    window.refresh_workbench_formula_panel()

    assert calls == [True]


def test_formula_workspace_sync_visibility_before_population_is_noop(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import _sync_formula_mount_visibility

    window = _window(qtbot)
    window._workbench_formula_populated = False

    _sync_formula_mount_visibility(window, "fitting")


def test_formula_workspace_visible_mounts_empty_before_population(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import _visible_formula_mounts

    window = _window(qtbot)
    window._workbench_formula_populated = False

    assert _visible_formula_mounts(window, "fitting") == []


def test_formula_workspace_does_not_create_preview_language_controls(qtbot: Any) -> None:
    window = _window(qtbot)

    assert not window.workbench_formula_panel.findChildren(type(window.mode_combo), "workbench_formula_language_combo")


def test_formula_workspace_population_failure_is_cached(qtbot: Any) -> None:
    window = _window(qtbot)
    original_editor = window.fit_expr_edit
    delattr(window, "fit_expr_edit")
    window._workbench_formula_populated = False

    with pytest.raises(RuntimeError, match="fit_expr_edit"):
        window.refresh_workbench_formula_panel()

    assert window._workbench_formula_populating is False
    cached_error = window._workbench_formula_population_error
    assert isinstance(cached_error, RuntimeError)

    with pytest.raises(RuntimeError) as second_error:
        window.refresh_workbench_formula_panel()
    assert second_error.value is not cached_error
    assert str(second_error.value) == str(cached_error)

    window.fit_expr_edit = original_editor
    window._workbench_formula_populated = False
    window.refresh_workbench_formula_panel()
    assert window._workbench_formula_populated is True
    assert window._workbench_formula_population_error is None


def test_formula_workspace_population_rejects_missing_preview_button(qtbot: Any) -> None:
    window = _window(qtbot)
    delattr(window, "fit_formula_preview_button")
    window._workbench_formula_populated = False
    window._workbench_formula_population_error = None

    with pytest.raises(RuntimeError, match="missing widgets: .*fit_formula_preview_button"):
        window.refresh_workbench_formula_panel()


def test_formula_workspace_population_does_not_skip_missing_editor(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.workbench_formula_panel as formula_panel

    window = _window(qtbot)
    delattr(window, "fit_expr_edit")
    window._workbench_formula_populated = False
    window._workbench_formula_population_error = None
    monkeypatch.setattr(formula_panel, "_missing_formula_mount_attrs", lambda _owner: [])

    with pytest.raises(RuntimeError, match="missing widgets: fit_expr_edit"):
        formula_panel.populate_formula_workspace_panel(window)


def test_formula_workspace_population_rejects_duplicate_editor_attrs(qtbot: Any, monkeypatch: Any) -> None:
    from dataclasses import replace

    import app_desktop.workbench_formula_panel as formula_panel
    from app_desktop.workbench_specs import FormulaMount

    window = _window(qtbot)
    specs = dict(formula_panel.MODE_WORKBENCH_SPECS)
    statistics = specs["statistics"]
    specs["statistics"] = replace(
        statistics,
        formulas=(FormulaMount("fit_expr_edit", "fit_formula_preview_button", "duplicate.formula"),),
    )
    monkeypatch.setattr(formula_panel, "MODE_WORKBENCH_SPECS", specs)
    window._workbench_formula_populated = False
    window._workbench_formula_population_error = None

    with pytest.raises(RuntimeError, match="duplicate editors: fit_expr_edit"):
        formula_panel.populate_formula_workspace_panel(window)


def test_formula_workspace_population_rejects_duplicate_schema_keys(qtbot: Any, monkeypatch: Any) -> None:
    from dataclasses import replace

    from PySide6.QtWidgets import QPlainTextEdit, QPushButton

    import app_desktop.workbench_formula_panel as formula_panel
    from app_desktop.workbench_specs import FormulaMount

    window = _window(qtbot)
    window.dummy_formula_edit = QPlainTextEdit(window)
    window.dummy_formula_preview_button = QPushButton(window)
    specs = dict(formula_panel.MODE_WORKBENCH_SPECS)
    statistics = specs["statistics"]
    specs["statistics"] = replace(
        statistics,
        formulas=(
            FormulaMount(
                "dummy_formula_edit",
                "dummy_formula_preview_button",
                "fitting.custom.expression",
            ),
        ),
    )
    monkeypatch.setattr(formula_panel, "MODE_WORKBENCH_SPECS", specs)
    window._workbench_formula_populated = False
    window._workbench_formula_population_error = None

    with pytest.raises(RuntimeError, match="duplicate schema keys: fitting\\.custom\\.expression"):
        formula_panel.populate_formula_workspace_panel(window)


def test_formula_workspace_population_reentrant_call_raises(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import populate_formula_workspace_panel

    window = _window(qtbot)
    window._workbench_formula_populated = False
    window._workbench_formula_populating = True

    with pytest.raises(RuntimeError, match="already in progress"):
        populate_formula_workspace_panel(window)


def test_formula_workspace_population_wraps_unexpected_failures(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.workbench_formula_panel as formula_panel

    window = _window(qtbot)
    window._workbench_formula_populated = False
    window._workbench_formula_population_error = None
    calls = 0

    def fail_reparent(*_args: Any, **_kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        raise TypeError("forced unexpected failure")

    monkeypatch.setattr(formula_panel, "reparent_widget", fail_reparent)

    with pytest.raises(RuntimeError, match="Formula workbench population failed") as first_error:
        window.refresh_workbench_formula_panel()

    assert isinstance(first_error.value.__cause__, TypeError)
    assert window._workbench_formula_population_error is first_error.value
    assert calls == 1

    with pytest.raises(RuntimeError) as second_error:
        window.refresh_workbench_formula_panel()

    assert second_error.value is not first_error.value
    assert str(second_error.value) == str(first_error.value)
    assert calls == 1


def test_formula_workspace_population_keeps_non_attr_failure_cached(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.workbench_formula_panel as formula_panel

    window = _window(qtbot)
    window._workbench_formula_populated = False
    window._workbench_formula_population_error = None

    def fail_reparent(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("forced transient-looking failure")

    monkeypatch.setattr(formula_panel, "reparent_widget", fail_reparent)

    with pytest.raises(RuntimeError) as first_error:
        formula_panel.populate_formula_workspace_panel(window)

    monkeypatch.setattr(formula_panel, "reparent_widget", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError) as second_error:
        formula_panel.populate_formula_workspace_panel(window)

    assert second_error.value is not first_error.value
    assert str(second_error.value) == str(first_error.value)


def test_formula_workspace_hidden_panel_keeps_wrapper_visibility_semantics(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import _formula_editor_available

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.refresh_workbench_formula_panel()
    wrapper = window._workbench_formula_mount_wrappers["fit_expr_edit"]

    window.workbench_formula_panel.hide()
    wrapper.hide()
    QApplication.processEvents()

    assert _formula_editor_available(window, window.fit_expr_edit) is False

    wrapper.show()
    QApplication.processEvents()

    assert _formula_editor_available(window, window.fit_expr_edit) is True


def test_formula_workspace_available_respects_hidden_external_ancestor(qtbot: Any) -> None:
    from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout

    from app_desktop.workbench_formula_panel import _formula_editor_available

    window = _window(qtbot)
    container = QWidget(window)
    qtbot.addWidget(container)
    layout = QVBoxLayout(container)
    editor = QPlainTextEdit()
    layout.addWidget(editor)

    container.hide()

    assert _formula_editor_available(window, editor) is False


def test_formula_workspace_error_strip_tracks_bad_preview_input(qtbot: Any, monkeypatch: Any) -> None:
    from datalab_latex.formula_render_service import RenderResult

    import app_desktop.formula_preview as preview

    def fake_render(request: Any) -> RenderResult:
        if request.source == "bad":
            return RenderResult(
                ok=False,
                source=request.source,
                language=request.language,
                latex="",
                mathtext="",
                png_bytes=b"",
                fallback_text=request.source,
                error_message="forced parse error",
            )
        return RenderResult(
            ok=True,
            source=request.source,
            language=request.language,
            latex=request.source,
            mathtext=f"${request.source}$",
            png_bytes=b"",
            fallback_text=request.source,
            error_message="",
        )

    monkeypatch.setattr(preview, "render_desktop_preview", fake_render)
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("bad")
    window.refresh_workbench_formula_panel()

    assert window.workbench_formula_error_label.isVisibleTo(window.workbench_formula_panel)
    assert "forced parse error" in window.workbench_formula_error_label.text()

    window.fit_expr_edit.setPlainText("A + x")
    window.refresh_workbench_formula_panel()

    assert not window.workbench_formula_error_label.isVisibleTo(window.workbench_formula_panel)


def test_formula_workspace_preview_pixmap_is_large_enough_to_read(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x^2-A")
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    pixmap = window.workbench_formula_preview_label.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    assert pixmap.height() >= 64


def test_formula_workspace_keeps_variable_panel_visible_for_multi_formula_modes(qtbot: Any) -> None:
    from app_desktop.theme import WORKBENCH_FORMULA_PANEL_MULTI_MAX_HEIGHT

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_equation_edit.setPlainText("u - a*x")
    window.implicit_output_edit.setPlainText("u + b")
    window.refresh_workbench_formula_panel()
    window.refresh_workbench_variable_panel()
    QApplication.processEvents()

    assert window.workbench_variable_panel.isVisible()
    assert window.workbench_formula_panel.maximumHeight() == WORKBENCH_FORMULA_PANEL_MULTI_MAX_HEIGHT


def test_formula_workspace_labels_multi_formula_editors(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.refresh_workbench_formula_panel()
    window.show()
    QApplication.processEvents()

    equation_label = window._workbench_formula_mount_labels["implicit_equation_edit"]
    output_label = window._workbench_formula_mount_labels["implicit_output_edit"]
    equation_wrapper = window._workbench_formula_mount_wrappers["implicit_equation_edit"]
    output_wrapper = window._workbench_formula_mount_wrappers["implicit_output_edit"]

    assert equation_label.text() == "自洽方程："
    assert output_label.text() == "输出表达式："
    assert window.isVisible()
    assert equation_wrapper.isVisibleTo(window.workbench_formula_panel)
    assert output_wrapper.isVisibleTo(window.workbench_formula_panel)
    assert equation_wrapper.geometry().y() == output_wrapper.geometry().y()
    assert equation_wrapper.geometry().x() < output_wrapper.geometry().x()


def test_formula_workspace_uses_compact_height_for_single_formula_modes(qtbot: Any) -> None:
    from app_desktop.theme import WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    window.root_equations_edit.setPlainText("x^2-A")
    window.refresh_workbench_formula_panel()
    window.refresh_workbench_variable_panel()
    QApplication.processEvents()

    assert window.workbench_formula_panel.maximumHeight() == WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT


def test_formula_workspace_preview_tracks_last_edited_implicit_formula(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    assert window._workbench_active_formula_attr == "implicit_output_edit"
    window.refresh_workbench_formula_panel()

    assert current_formula_mount(window).editor_attr == "implicit_output_edit"


def test_formula_workspace_ignores_hidden_programmatic_text_changes(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("A*x+B")
    QApplication.processEvents()

    assert window._workbench_active_formula_attr == "fit_expr_edit"

    window.implicit_output_edit.setPlainText("u + x")
    QApplication.processEvents()

    assert window._workbench_active_formula_attr == "fit_expr_edit"
    assert current_formula_mount(window).editor_attr == "fit_expr_edit"


def test_formula_workspace_preview_prefers_focused_formula(qtbot: Any) -> None:
    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window.implicit_equation_edit.setPlainText("u - x")
    window.implicit_equation_edit.setFocus()
    QApplication.processEvents()

    assert current_formula_mount(window).editor_attr == "implicit_equation_edit"


def test_formula_workspace_focus_filter_updates_active_formula(qtbot: Any) -> None:
    from PySide6.QtCore import QEvent

    from app_desktop.workbench_formula_panel import current_formula_mount

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")

    handled = window._workbench_formula_focus_filter.eventFilter(
        window.implicit_equation_edit,
        QEvent(QEvent.Type.FocusIn),
    )

    assert handled is False
    assert window._workbench_active_formula_attr == "implicit_equation_edit"
    assert current_formula_mount(window).editor_attr == "implicit_equation_edit"


def test_formula_workspace_installs_editor_local_focus_filter(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window._workbench_formula_focus_filter is not None
    assert not hasattr(window, "_workbench_formula_focus_disconnect")
    assert len(window._workbench_formula_text_changed_callbacks) == 6


def test_formula_workspace_title_describes_multi_formula_card(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    assert window.workbench_formula_panel_title.text() == "Model formulas"
    assert window._workbench_formula_mount_labels["implicit_output_edit"].text() == "Output expression:"


def test_formula_workspace_mode_switch_uses_bound_schema_title_without_manual_refresh(qtbot: Any) -> None:
    window = _window(qtbot)
    window._apply_language("en")
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert window.workbench_formula_panel_title.text() == "Formula preview"


def test_formula_workspace_title_does_not_expose_raw_schema_key_when_label_missing(qtbot: Any) -> None:
    from app_desktop.ui_schema_binder import SCHEMA_LABEL_EN_PROPERTY, SCHEMA_LABEL_ZH_PROPERTY

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    window.implicit_output_edit.setPlainText("u + x")
    window.implicit_output_edit.setProperty(SCHEMA_LABEL_ZH_PROPERTY, "")
    window.implicit_output_edit.setProperty(SCHEMA_LABEL_EN_PROPERTY, "")
    window._apply_language("en")
    window.refresh_workbench_formula_panel()

    title = window.workbench_formula_panel_title.text()
    output_label = window._workbench_formula_mount_labels["implicit_output_edit"].text()
    assert "fitting.implicit.output_expression" not in title
    assert "fitting.implicit.output_expression" not in output_label
    assert title == "Model formulas"
    assert output_label == "Output Expression:"


def test_formula_panel_hidden_when_mode_has_no_formulas(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()
    assert not window.workbench_formula_function_button.isVisible()


def test_formula_panel_tracks_extrapolation_method_visibility(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("extrapolation"))
    window.method_combo.setCurrentIndex(window.method_combo.findData("power_law"))
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()

    window.method_combo.setCurrentIndex(window.method_combo.findData("custom"))
    QApplication.processEvents()

    assert window.workbench_formula_panel.isVisible()
    assert window.workbench_formula_panel_title.text() == "公式预览"


def test_formula_panel_hidden_when_fitting_submode_has_no_visible_formula(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.refresh_workbench_formula_panel()
    assert window.workbench_formula_panel.isVisible()

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("polynomial"))
    window.refresh_workbench_formula_panel()
    QApplication.processEvents()

    assert not window.workbench_formula_panel.isVisible()


def test_formula_workspace_refreshes_on_fitting_submode_visibility_change(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    calls = 0

    def refresh() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(window, "refresh_workbench_formula_panel", refresh)

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()

    assert calls >= 1
