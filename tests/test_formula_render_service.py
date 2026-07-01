from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def _clear_render_cache_between_tests():
    import datalab_latex.formula_render_service as service

    service.clear_formula_render_cache()
    yield
    service.clear_formula_render_cache()


def test_render_service_import_stays_metadata_lightweight() -> None:
    script = r"""
import sys

import datalab_latex.formula_render_service

forbidden_prefixes = (
    "PySide6",
    "matplotlib.pyplot",
    "data_extrapolation_latex_latest",
    "datalab_latex.latex_tables_extrapolation",
    "datalab_latex.latex_formatting",
    "mpmath",
    "sympy",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_render_formula_metadata_does_not_import_desktop_renderer() -> None:
    script = r"""
import sys

from datalab_latex.formula_render_service import RenderRequest, render_formula_metadata

result = render_formula_metadata(RenderRequest(source="x^2 + 1"))
if not result.ok:
    raise SystemExit(result.error_message)
if "app_desktop.formula_renderer" in sys.modules:
    raise SystemExit("desktop renderer imported by metadata service")
print("ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_datalab_latex_package_import_stays_lightweight() -> None:
    script = r"""
import sys

import datalab_latex

forbidden_prefixes = (
    "PySide6",
    "matplotlib.pyplot",
    "data_extrapolation_latex_latest",
    "datalab_latex.derivatives",
    "datalab_latex.expression_engine",
    "datalab_latex.latex_formatting",
    "datalab_latex.latex_tables",
    "datalab_latex.latex_tables_extrapolation",
    "mpmath",
    "sympy",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
if "format_result_with_uncertainty_latex" not in dir(datalab_latex):
    raise SystemExit("lazy export missing from dir(datalab_latex)")
print("ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_render_formula_metadata_does_not_render_png(monkeypatch: pytest.MonkeyPatch) -> None:
    import datalab_latex.formula_render_service as service
    from datalab_latex.formula_render_service import RenderRequest, render_formula_metadata

    def fail_png_render(*_args, **_kwargs) -> bytes:
        raise AssertionError("metadata preview must not render PNG bytes")

    monkeypatch.setattr(service, "_render_mathtext_png", fail_png_render)

    result = render_formula_metadata(RenderRequest(source="sqrt(x)/(a+b)", lhs="y"))

    assert result.ok
    assert result.latex.startswith("y = ")
    assert result.mathtext.startswith("$")


def test_render_service_accepts_datalab_python_and_mathematica_sources() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    datalab = render_formula(RenderRequest(source="A*x**(-p) + C", language=InputLanguage.DATALAB))
    python = render_formula(RenderRequest(source="sqrt(A) + exp(-x)", language=InputLanguage.PYTHON))
    mathematica = render_formula(RenderRequest(source="Sin[x] + Sqrt[A]", language=InputLanguage.MATHEMATICA))

    assert datalab.ok
    assert "x^{-p}" in datalab.latex
    assert r"\cdot" in datalab.latex
    assert python.ok
    assert r"\sqrt{A}" in python.latex
    assert r"\exp" in python.latex
    assert mathematica.ok
    assert r"\sin" in mathematica.latex
    assert r"\sqrt{A}" in mathematica.latex


def test_render_service_does_not_double_escape_pi_inside_nested_calls() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(
        RenderRequest(
            source="Exp[-x] + Log[Pi*x]",
            language=InputLanguage.MATHEMATICA,
        )
    )

    assert result.ok, result.error_message
    assert r"\pi\cdot x" in result.latex
    assert r"\\pi" not in result.latex
    assert result.png_bytes.startswith(b"\x89PNG")


def test_python_formula_preview_handles_nested_calls_and_function_exponents() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula_metadata,
    )

    result = render_formula_metadata(
        RenderRequest(
            source="sin(cos(x)) + x**((y+1)) + a**f(y) + b**sin(y) + c**sqrt(A)",
            language=InputLanguage.PYTHON,
        )
    )

    assert result.ok
    assert r"\sin\left(\cos\left(x\right)\right)" in result.latex
    assert "x^{(y+1)}" in result.latex
    assert "a^{f(y)}" in result.latex
    assert r"b^{\sin\left(y\right)}" in result.latex
    assert r"c^{\sqrt{A}}" in result.latex


def test_formula_preview_supports_abs_and_extended_trig_functions() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula_metadata,
    )

    python = render_formula_metadata(
        RenderRequest(
            source="abs(x) + sinh(x) + cosh(x) + tanh(x) + asin(x) + acos(x) + atan(x)",
            language=InputLanguage.PYTHON,
        )
    )
    mathematica = render_formula_metadata(
        RenderRequest(
            source="Abs[x] + Sinh[x] + Cosh[x] + Tanh[x] + ArcSin[x] + ArcCos[x] + ArcTan[x]",
            language=InputLanguage.MATHEMATICA,
        )
    )

    for result in (python, mathematica):
        assert result.ok
        assert r"\left|x\right|" in result.latex
        assert r"\sinh\left(x\right)" in result.latex
        assert r"\cosh\left(x\right)" in result.latex
        assert r"\tanh\left(x\right)" in result.latex
        assert r"\arcsin\left(x\right)" in result.latex
        assert r"\arccos\left(x\right)" in result.latex
        assert r"\arctan\left(x\right)" in result.latex


def test_formula_preview_preserves_uppercase_greek_identifiers() -> None:
    from datalab_latex.formula_render_service import RenderRequest, render_formula_metadata

    result = render_formula_metadata(RenderRequest(source="Delta + Gamma + delta"))

    assert result.ok
    assert r"\Delta" in result.latex
    assert r"\Gamma" in result.latex
    assert r"\delta" in result.latex


def test_python_language_does_not_convert_mathematica_bracket_calls() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    python = render_formula(RenderRequest(source="Sin[x]", language=InputLanguage.PYTHON))
    datalab = render_formula(RenderRequest(source="Sin[x]", language=InputLanguage.DATALAB))

    assert python.ok
    assert r"\sin" not in python.latex
    assert datalab.ok
    assert r"\sin" in datalab.latex


def test_render_service_supports_lhs_and_png_bytes() -> None:
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    result = render_formula(RenderRequest(source="d0 + d2/(n-delta)^2", lhs="delta"))

    assert result.ok
    assert result.latex.startswith(r"\delta = ")
    assert result.mathtext.startswith("$")
    assert result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_service_accepts_safe_latex_passthrough() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(RenderRequest(source=r"\frac{x}{y}", language=InputLanguage.LATEX))

    assert result.ok
    assert result.latex == r"\frac{x}{y}"
    assert result.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    "source",
    [
        r"\begin{cases} x & x>0 \\ -x & x<0 \end{cases}",
        r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
        r"\begin{aligned} x &= y+1 \\ z &= 2 \end{aligned}",
    ],
)
def test_sanitizer_allows_safe_formula_latex_environments_without_unsafe_error(source: str) -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(RenderRequest(source=source, language=InputLanguage.LATEX))

    assert "unsafe" not in result.error_message.lower()


@pytest.mark.parametrize(
    "source",
    [
        r"\input{secret}",
        r"\include{/tmp/file}",
        r"\write18{rm -rf /}",
        r"\newcommand{\x}{y}",
        r"\def\x{y}",
        r"\special{shell:rm -rf /}",
        r"\primitive",
        r"\primitive\write18{rm -rf /}",
        r"\begin{document}\frac{x}{y}",
        r"\end{document}\frac{x}{y}",
        r"\begin{filecontents}{x.tex}secret\end{filecontents}",
        r"\begin{tcblisting}secret\end{tcblisting}",
    ],
)
def test_render_service_rejects_unsafe_latex_commands(source: str) -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(RenderRequest(source=source, language=InputLanguage.LATEX))

    assert not result.ok
    assert result.png_bytes == b""
    assert "unsafe" in result.error_message.lower()
    assert result.fallback_text == source


def test_render_service_rejects_raw_latex_commands_in_non_latex_sources() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(RenderRequest(source=r"\input{secret}", language=InputLanguage.DATALAB))

    assert not result.ok
    assert "unsafe" in result.error_message.lower()


def test_render_service_rejects_raw_latex_environments_in_non_latex_sources() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(
        RenderRequest(
            source=r"\begin{filecontents}{x.tex}secret\end{filecontents}",
            language=InputLanguage.DATALAB,
        )
    )

    assert not result.ok
    assert "unsafe" in result.error_message.lower()


def test_render_service_reports_unsafe_before_unbalanced_for_non_latex_sources() -> None:
    from datalab_latex.formula_render_service import (
        InputLanguage,
        RenderRequest,
        render_formula,
    )

    result = render_formula(
        RenderRequest(
            source=r"\begin{filecontents}{",
            language=InputLanguage.DATALAB,
        )
    )

    assert not result.ok
    assert "unsafe" in result.error_message.lower()
    assert "unbalanced" not in result.error_message.lower()


def test_render_service_cache_avoids_duplicate_png_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    import datalab_latex.formula_render_service as service
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    calls: list[str] = []

    def fake_render(mathtext: str, *, dpi: int, color: str) -> bytes:
        calls.append(mathtext)
        return b"\x89PNG\r\n\x1a\nfake"

    service.clear_formula_render_cache()
    monkeypatch.setattr(service, "_render_mathtext_png", fake_render)

    request = RenderRequest(source="x^2 + 1", dpi=144)
    first = render_formula(request)
    second = render_formula(request)

    assert first.png_bytes == second.png_bytes
    assert calls == [first.mathtext]

    service.clear_formula_render_cache()
    third = render_formula(request)

    assert third.png_bytes == first.png_bytes
    assert calls == [first.mathtext, third.mathtext]


def test_render_service_length_limit_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    import datalab_latex.formula_render_service as service
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    service.clear_formula_render_cache()
    monkeypatch.setattr(service, "_MAX_SOURCE_LENGTH", 3)
    monkeypatch.setattr(
        service,
        "_render_mathtext_png",
        lambda _mathtext, *, dpi, color: b"\x89PNG\r\n\x1a\nfake",
    )

    assert render_formula(RenderRequest(source="x+1")).ok

    too_long = render_formula(RenderRequest(source="x+12"))
    assert not too_long.ok
    assert "too long" in too_long.error_message.lower()


def test_render_service_returns_structured_error_for_bad_input() -> None:
    from datalab_latex.formula_render_service import RenderRequest, render_formula

    result = render_formula(RenderRequest(source="A + )"))

    assert not result.ok
    assert result.png_bytes == b""
    assert result.fallback_text == "A + )"
    assert result.error_message


def test_sympy_formatter_rejects_attribute_access_gadget() -> None:
    # P0-2: the SymPy formatter parses arbitrary expressions with parse_expr. Without an
    # AST pre-check, attribute-access gadgets (e.g. `.__class__`) slip through and render
    # to an object repr instead of being rejected — the first rung of a sandbox escape.
    from datalab_latex.formula_render_service import _format_latex_formula_sympy

    with pytest.raises(ValueError):
        _format_latex_formula_sympy("sqrt(1).__class__")


def test_sympy_formatter_still_renders_ordinary_lowercase_formula() -> None:
    # Regression guard: the renderer accepts lowercase function names (sin, cos, ...),
    # so the AST hardening must not reject legitimate formulas.
    from datalab_latex.formula_render_service import _format_latex_formula_sympy

    out = _format_latex_formula_sympy("sin(x) + a*x^2")
    assert isinstance(out, str) and out.strip()
