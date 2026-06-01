from __future__ import annotations

import os
import sys
import importlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QLabel, QSizePolicy  # noqa: E402


def _pixmap_is_cleared(label: QLabel) -> bool:
    pixmap = label.pixmap()
    return pixmap is None or pixmap.isNull()


def test_formula_preview_import_does_not_eagerly_import_matplotlib_pyplot() -> None:
    sys.modules.pop("app_desktop.formula_preview", None)
    sys.modules.pop("matplotlib.pyplot", None)

    importlib.import_module("app_desktop.formula_preview")

    assert "matplotlib.pyplot" not in sys.modules


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

    assert label.maximumWidth() <= 320
    assert label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_formula_preview_falls_back_to_text_on_invalid_input(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)

    update_formula_preview(label, "A + )")

    assert _pixmap_is_cleared(label)
    assert "A + )" in label.text()


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
    from app_desktop.formula_preview import _expression_to_mathtext

    mathtext = _expression_to_mathtext("x**2+1")

    assert "x^{2}+1" in mathtext
    assert "x^{2+1}" not in mathtext


def test_caret_power_conversion_stops_before_following_addition_terms() -> None:
    from app_desktop.formula_preview import _expression_to_mathtext

    mathtext = _expression_to_mathtext("x^2+1")

    assert "x^{2}+1" in mathtext
    assert "x^{2+1}" not in mathtext


def test_signed_power_conversion_stops_before_following_symbol_terms() -> None:
    from app_desktop.formula_preview import _expression_to_mathtext

    mathtext = _expression_to_mathtext("x**-p+C")

    assert "x^{-p}+C" in mathtext
    assert "x^{-p+C}" not in mathtext


def test_formula_preview_handles_invalid_lhs_as_text(qtbot) -> None:
    from app_desktop.formula_preview import update_formula_preview

    label = QLabel()
    qtbot.addWidget(label)

    update_formula_preview(label, "d0 + d2", lhs="bad name")

    assert _pixmap_is_cleared(label)
    assert "d0 + d2" in label.text()
