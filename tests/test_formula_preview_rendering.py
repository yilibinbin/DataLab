from __future__ import annotations

import os
import subprocess
import sys
import textwrap

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QLabel, QSizePolicy  # noqa: E402


def _pixmap_is_cleared(label: QLabel) -> bool:
    pixmap = label.pixmap()
    return pixmap is None or pixmap.isNull()


def test_formula_preview_import_does_not_eagerly_import_matplotlib_pyplot() -> None:
    probe = textwrap.dedent(
        """
        import importlib
        import sys

        importlib.import_module("app_desktop.formula_preview")

        if "matplotlib.pyplot" in sys.modules:
            raise SystemExit("matplotlib.pyplot imported eagerly")
        """
    )

    subprocess.run([sys.executable, "-c", probe], check=True)


def test_formula_preview_renders_pixmap(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)

    update_formula_preview(label, "A*x**(-p) + C")

    assert label.pixmap() is not None
    assert not label.pixmap().isNull()
    assert not label.text().strip()


def test_formula_preview_label_does_not_force_parent_width(qtbot) -> None:
    from app_desktop.formula_preview import FormulaPreviewLabel, update_formula_preview

    label = FormulaPreviewLabel()
    qtbot.addWidget(label)

    update_formula_preview(
        label,
        "d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8",
        lhs="delta",
    )

    assert label.maximumWidth() <= 544
    assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_formula_preview_plain_label_does_not_force_inline_size(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)
    original_min_height = label.minimumHeight()
    original_max_height = label.maximumHeight()
    original_max_width = label.maximumWidth()
    original_style = label.styleSheet()
    original_alignment = label.alignment()
    original_word_wrap = label.wordWrap()

    update_formula_preview(label, "x^2 + 1")

    assert label.minimumHeight() == original_min_height
    assert label.maximumHeight() == original_max_height
    assert label.maximumWidth() == original_max_width
    assert label.styleSheet() == original_style
    assert label.alignment() == original_alignment
    assert label.wordWrap() == original_word_wrap


def test_configure_formula_preview_plain_label_is_noop_without_opt_in(qtbot) -> None:
    from app_desktop.formula_preview import configure_formula_preview_label

    label = QLabel()
    qtbot.addWidget(label)
    original_state = (
        label.minimumHeight(),
        label.maximumHeight(),
        label.maximumWidth(),
        label.styleSheet(),
        label.alignment(),
        label.wordWrap(),
        label.cursor().shape(),
        label.toolTip(),
    )

    configure_formula_preview_label(label)

    assert (
        label.minimumHeight(),
        label.maximumHeight(),
        label.maximumWidth(),
        label.styleSheet(),
        label.alignment(),
        label.wordWrap(),
        label.cursor().shape(),
        label.toolTip(),
    ) == original_state


def test_formula_preview_falls_back_to_text_on_invalid_input(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)

    update_formula_preview(label, "A + )")

    assert _pixmap_is_cleared(label)
    assert "A + )" in label.text()


def test_formula_preview_empty_legacy_call_does_not_hardcode_english(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)

    update_formula_preview(label, "")

    assert _pixmap_is_cleared(label)
    assert label.text() == ""


def test_formula_preview_with_empty_text_clears_click_source(qtbot) -> None:
    from app_desktop.formula_preview import FormulaPreviewLabel, update_formula_preview_with_empty_text

    label = FormulaPreviewLabel()
    qtbot.addWidget(label)
    label.set_preview_source("old*x", "y")

    result = update_formula_preview_with_empty_text(
        label,
        "",
        lhs="z",
        empty_text="No active formula",
        constrain_size=True,
    )

    assert result is None
    assert _pixmap_is_cleared(label)
    assert label.text() == "No active formula"
    assert label._preview_expression == ""
    assert label._preview_lhs == "z"


def test_formula_preview_with_empty_text_dispatches_selected_language(qtbot, monkeypatch) -> None:
    from datalab_latex.formula_render_service import InputLanguage, RenderResult

    import app_desktop.formula_preview as formula_preview

    captured = []

    def fake_render_formula(request):
        captured.append(request)
        return RenderResult(
            ok=False,
            source=request.source,
            language=request.language,
            latex="",
            mathtext="",
            png_bytes=b"",
            fallback_text=request.source,
        )

    monkeypatch.setattr(formula_preview, "render_formula", fake_render_formula)
    label = formula_preview.FormulaPreviewLabel()
    qtbot.addWidget(label)

    result = formula_preview.update_formula_preview_with_empty_text(
        label,
        r"  \frac{1}{2}  ",
        lhs="y",
        language=InputLanguage.LATEX,
        constrain_size=True,
    )

    assert captured
    assert captured[0].source == r"\frac{1}{2}"
    assert captured[0].language is InputLanguage.LATEX
    assert captured[0].lhs == "y"
    assert result is not None
    assert result.language is InputLanguage.LATEX
    assert _pixmap_is_cleared(label)
    assert label.text() == r"  \frac{1}{2}  "
    assert label._preview_expression == r"  \frac{1}{2}  "
    assert label._preview_lhs == "y"


def test_implicit_equation_preview_adds_left_hand_side(qtbot) -> None:
    from app_desktop.formula_preview import render_formula_pixmap

    pixmap = render_formula_pixmap("d0 + d2/(n-delta)^2", lhs="delta")

    assert pixmap is not None
    assert not pixmap.isNull()


def test_formula_preview_renders_common_function_names(qtbot) -> None:
    from app_desktop.formula_preview import render_formula_pixmap

    pixmap = render_formula_pixmap("Sin[x] + cos(u) + Exp[-x1] + sqrt(A)", lhs="y")

    assert pixmap is not None
    assert not pixmap.isNull()


def test_power_conversion_stops_before_following_addition_terms() -> None:
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    mathtext = render_formula(RenderRequest(source="x**2+1")).mathtext

    assert "x^{2}+1" in mathtext
    assert "x^{2+1}" not in mathtext


def test_caret_power_conversion_stops_before_following_addition_terms() -> None:
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    mathtext = render_formula(RenderRequest(source="x^2+1")).mathtext

    assert "x^{2}+1" in mathtext
    assert "x^{2+1}" not in mathtext


def test_signed_power_conversion_stops_before_following_symbol_terms() -> None:
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    mathtext = render_formula(RenderRequest(source="x**-p+C")).mathtext

    assert "x^{-p}+C" in mathtext
    assert "x^{-p+C}" not in mathtext


def test_formula_preview_handles_invalid_lhs_as_text(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)

    update_formula_preview(label, "d0 + d2", lhs="bad name")

    assert _pixmap_is_cleared(label)
    assert "d0 + d2" in label.text()
