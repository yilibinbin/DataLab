from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText, ResultViewSpec


def test_result_view_spec_exposes_localized_tabs_display_columns_and_raw_keys() -> None:
    view = ResultViewSpec(
        key="root.results",
        title=LocalizedText("求根结果", "Root results"),
        attachment_key="root_result_markdown",
        display_columns=[
            ChoiceSpec(value="root", label=LocalizedText("根", "Root")),
            ChoiceSpec(value="residual", label=LocalizedText("残差", "Residual")),
        ],
        raw_columns=["root", "uncertainty", "residual"],
    )

    assert view.title.for_lang("zh") == "求根结果"
    assert view.title.for_lang("en") == "Root results"
    assert [column.label.for_lang("en") for column in view.display_columns] == ["Root", "Residual"]
    assert [column.value for column in view.display_columns] == ["root", "residual"]
    assert view.raw_columns == ("root", "uncertainty", "residual")


def test_result_view_spec_exposes_localized_control_metadata() -> None:
    view = ResultViewSpec(
        key="results.numeric",
        title=LocalizedText("数值结果", "Numeric results"),
        controls=[
            FormFieldSpec(
                key="results.display.scientific",
                widget_kind="checkbox",
                label=LocalizedText("使用科学计数法显示结果", "Display results in scientific notation"),
                tooltip=LocalizedText(
                    "切换数值结果是否使用科学计数法显示。",
                    "Toggle scientific notation for numeric result display.",
                ),
            )
        ],
    )

    assert view.controls[0].key == "results.display.scientific"
    assert view.controls[0].label.for_lang("en") == "Display results in scientific notation"
    assert "科学计数法" in view.controls[0].tooltip.for_lang("zh")


def test_result_view_spec_is_frozen_and_sequence_fields_are_tuples() -> None:
    display_columns = [ChoiceSpec(value="value", label=LocalizedText("值", "Value"))]
    raw_columns = ["value"]
    controls = [
        FormFieldSpec(
            key="results.export.csv",
            widget_kind="button",
            label=LocalizedText("导出 CSV", "Export CSV"),
        )
    ]
    view = ResultViewSpec(
        key="results.numeric",
        title=LocalizedText("数值结果", "Numeric results"),
        display_columns=display_columns,
        raw_columns=raw_columns,
        controls=controls,
    )

    display_columns.clear()
    raw_columns.append("unexpected")
    controls.clear()

    assert view.display_columns == (ChoiceSpec(value="value", label=LocalizedText("值", "Value")),)
    assert view.raw_columns == ("value",)
    assert len(view.controls) == 1
    with pytest.raises(FrozenInstanceError):
        setattr(view, "key", "changed")
