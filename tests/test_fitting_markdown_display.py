"""Pin the Markdown structure of fitting result display.

Background: the desktop GUI's result panel uses ``setMarkdown`` (with
plain-text fallback) to render every result. Three of the four core
features — extrapolation, error propagation, statistics — already
emit Markdown:

  - ``## 外推结果`` / ``## 误差传递结果`` / ``## 统计平均结果``
  - bilingual headers, then a Markdown table (``| ... | ... |``)

Fitting was the holdout: it emitted a plain-text block headed by
``=== 拟合结果 ===`` with parameter rows like ``a = 1.5 ± 0.01``.
The block rendered "fine" but with a different visual style than
its three siblings.

This test pins the new Markdown format. If a future maintainer
reverts the formatter to plain text, the assertion fails loudly.

Why test the Markdown OUTPUT, not the rendered HTML?
----------------------------------------------------

``setMarkdown`` is Qt's; we trust Qt to render Markdown. The only
thing we own is the Markdown text we pass IN. Test that.
"""
from __future__ import annotations

from dataclasses import dataclass

from mpmath import mp

from fitting.diagnostics import attach_fit_diagnostics
from fitting.hp_fitter import FitResult


@dataclass
class _MinimalSelf:
    """A tiny stand-in for the Mixin's ``self`` — provides only the
    helpers ``_format_fit_result_text`` actually calls.

    Faster and clearer than instantiating a real ``ExtrapolationWindow``
    (which needs a QApplication, full UI tree, etc.). The methods here
    mimic the production behaviour without any Qt dependency.
    """

    is_en: bool = False
    _current_precision: int | None = None

    def _is_en(self) -> bool:  # noqa: D401
        return self.is_en

    def _tr(self, zh: str, en: str) -> str:
        return en if self.is_en else zh

    def _format_precision_value(self, value: object) -> str:
        if value is None:
            return "—"
        try:
            mpf_val = value if isinstance(value, mp.mpf) else mp.mpf(value)
        except (TypeError, ValueError):
            return str(value)
        if mp.isnan(mpf_val):
            return "nan"
        return mp.nstr(mpf_val, 6)

    def _format_uncertainty_value(
        self, value: object, error: object, latex: bool = False
    ) -> str:
        # Production version handles "value ± error" with significant-
        # figure tracking; the test only cares about a deterministic
        # render, so use a simple "{value} ± {error}" form.
        try:
            v = value if isinstance(value, mp.mpf) else mp.mpf(value)
            e = error if isinstance(error, mp.mpf) else mp.mpf(error)
        except (TypeError, ValueError):
            return f"{value} ± {error}"
        if mp.isnan(e) or e == 0:
            return mp.nstr(v, 6)
        return f"{mp.nstr(v, 6)} ± {mp.nstr(e, 4)}"

    def _format_display_value(self, value: object) -> str:
        return self._format_precision_value(value)

    def _localize_text(self, text: str) -> str:
        if not text:
            return text
        if " / " in text:
            zh, _, en = text.partition(" / ")
            return en if self.is_en else zh
        return text

    def _fit_output_unit(self, units: dict[str, object] | None, target_column: str | None = None) -> str:
        from shared.unit_annotations import unit_annotation_text

        return unit_annotation_text(units, "outputs", "result")

    def _fit_parameter_units(self, units: dict[str, object] | None, names) -> dict[str, str]:
        from shared.unit_annotations import unit_annotations_for_labels

        return unit_annotations_for_labels(
            units,
            "parameters",
            list(names),
            fallback_prefix="parameter",
        )

    def _fit_csv_headers(self, rows: list[dict[str, object]]) -> list[str]:
        headers = ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error"]
        if any("unit" in row for row in rows):
            headers.append("unit")
        headers.append("note")
        return headers


def _make_fit_result(
    *,
    params: dict[str, mp.mpf],
    stat: dict[str, mp.mpf] | None = None,
    sys: dict[str, mp.mpf] | None = None,
    extras: dict[str, object] | None = None,
) -> FitResult:
    """Build a minimal FitResult with the fields the formatter reads.

    Computes ``param_errors_total`` as ``sqrt(stat² + sys²)`` per the
    standard quadrature combination so the mock matches what
    ``fitting.hp_fitter.combine_error_components`` would produce in
    production. Earlier versions of this factory passed
    ``param_errors_total=stat`` which silently dropped the systematic
    contribution from the rendered ``Value ± Total`` cell.
    """
    n = len(params)
    stat_d = stat or {}
    sys_d = sys or {}
    if stat_d or sys_d:
        total = {
            name: mp.sqrt(
                stat_d.get(name, mp.mpf("0")) ** 2
                + sys_d.get(name, mp.mpf("0")) ** 2
            )
            for name in params
        }
    else:
        total = {name: mp.mpf("0") for name in params}
    return FitResult(
        params=params,
        param_errors=total,
        chi2=mp.mpf("1.5"),
        reduced_chi2=mp.mpf("0.5"),
        aic=mp.mpf("12.3"),
        bic=mp.mpf("14.7"),
        r2=mp.mpf("0.9876"),
        rmse=mp.mpf("0.025"),
        residuals=[mp.mpf("0")] * n,
        fitted_curve=[mp.mpf("0")] * n,
        covariance=[[mp.mpf("0")] * n for _ in range(n)],
        param_errors_stat=stat,
        param_errors_sys=sys,
        param_errors_total=total,
        details=extras or {},
    )


def _format(
    instance: _MinimalSelf,
    fit_result: FitResult,
    expression: str | None = "a*x + b",
    substituted: str | None = "1.5*x + 2.0",
    units: dict[str, object] | None = None,
) -> str:
    """Invoke the fitting mixin's formatter via the bound method.

    Imported lazily so the module doesn't pull in PySide6 just to
    build the stand-in self.
    """
    from app_desktop.window_fitting_mixin import WindowFittingMixin

    return WindowFittingMixin._format_fit_result_text(
        instance,  # type: ignore[arg-type]
        fit_result, expression, substituted, units=units,
    )


# ---------------------------------------------------------------- structural

def test_fit_text_starts_with_markdown_h2_heading() -> None:
    """The output must begin with a Markdown ``## `` heading so
    ``setMarkdown`` renders it as a section title — matching the
    extrapolation/error/statistics formatters."""
    instance = _MinimalSelf(is_en=False)
    text = _format(instance, _make_fit_result(params={"a": mp.mpf("1.5")}))
    first = text.splitlines()[0]
    assert first.startswith("## "), (
        f"Fit result must start with a Markdown H2 heading; got first "
        f"line: {first!r}"
    )
    assert "拟合结果" in first


def test_fit_text_starts_with_markdown_h2_heading_en() -> None:
    instance = _MinimalSelf(is_en=True)
    text = _format(instance, _make_fit_result(params={"a": mp.mpf("1.5")}))
    first = text.splitlines()[0]
    assert first.startswith("## "), (
        f"English heading must also use Markdown H2; got: {first!r}"
    )
    assert "Fit Results" in first


def test_fit_text_does_not_use_legacy_equals_separator() -> None:
    """The pre-Markdown format wrapped the title in
    ``=== 拟合结果 ===``. After the Markdown migration, that pattern
    should be gone."""
    instance = _MinimalSelf(is_en=False)
    text = _format(instance, _make_fit_result(params={"a": mp.mpf("1.5")}))
    assert "=== 拟合结果 ===" not in text, (
        "Legacy ``=== ... ===`` separator leaked into the new "
        "Markdown formatter — replace with ``## `` heading."
    )
    assert "=== Fit Results ===" not in text


def test_fit_text_renders_parameters_in_markdown_table() -> None:
    """Parameters should appear in a Markdown table with header
    ``| Parameter | Value | ... |`` and separator ``| --- | --- |``."""
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5"), "b": mp.mpf("2.0")},
        stat={"a": mp.mpf("0.01"), "b": mp.mpf("0.02")},
    )
    text = _format(instance, fit)

    # The Markdown-table separator row is the cheapest distinguishing
    # feature: it's pure ``---`` cells and only Markdown formatters
    # produce it.
    assert "| --- |" in text, (
        "Parameter block must be rendered as a Markdown table — no "
        "separator row found.\n\nOutput was:\n" + text
    )
    # Parameter names must still show up, in their original order.
    a_pos = text.find("| a |")
    b_pos = text.find("| b |")
    assert a_pos != -1 and b_pos != -1, (
        "Parameter names must appear as Markdown table cells.\n\n"
        "Output was:\n" + text
    )
    assert a_pos < b_pos, "Parameters must preserve insertion order."


def test_fit_text_renders_metrics_in_markdown_table() -> None:
    """χ² / Reduced χ² / AIC / BIC / R² / RMSE should be rows of a
    Markdown table, NOT bare ``key = value`` lines."""
    instance = _MinimalSelf(is_en=False)
    text = _format(instance, _make_fit_result(params={"a": mp.mpf("1.0")}))
    # A bare ``AIC = 12.3`` line outside a Markdown table would be the
    # legacy format. The new format renders it as ``| AIC | 12.3 |``.
    for metric in ("χ²", "AIC", "BIC", "R²", "RMSE"):
        # Match the start-of-cell form so the regex won't accidentally
        # find ``AIC`` inside a comment.
        assert f"| {metric} " in text, (
            f"Metric {metric!r} must appear as a Markdown table row "
            f"(``| {metric} | ... |``). Output was:\n{text}"
        )


def test_fit_text_and_csv_include_display_only_units_when_present() -> None:
    from app_desktop.window_fitting_mixin import WindowFittingMixin

    instance = _MinimalSelf(is_en=True)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        stat={"a": mp.mpf("0.01")},
    )
    units = {
        "parameters": {"a": {"unit": "m/s"}},
        "outputs": {"result": {"unit": "J"}},
    }

    text = _format(instance, fit, units=units)
    rows = WindowFittingMixin._build_fit_csv_rows(  # type: ignore[misc]
        instance,  # type: ignore[arg-type]
        fit,
        "a*x",
        units=units,
    )
    headers = WindowFittingMixin._fit_csv_headers(  # type: ignore[misc]
        instance,  # type: ignore[arg-type]
        rows,
    )

    assert "| Parameter | Unit | Value ± Error |" in text
    assert "| a | m/s |" in text
    assert "| RMSE | J |" in text
    by_name = {str(row["name"]): row for row in rows}
    assert by_name["a"]["unit"] == "m/s"
    assert by_name["rmse"]["unit"] == "J"
    assert headers == [
        "batch",
        "section",
        "name",
        "value",
        "uncertainty",
        "stat_error",
        "sys_error",
        "unit",
        "note",
    ]


def test_fit_text_reads_sentinel_metrics_from_fit_result() -> None:
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(params={"a": mp.mpf("1.0")})
    fit.chi2 = mp.mpf("101")
    fit.reduced_chi2 = mp.mpf("202")
    fit.aic = mp.mpf("303")
    fit.bic = mp.mpf("404")
    fit.r2 = mp.mpf("0.505")
    fit.rmse = mp.mpf("0.606")

    text = _format(instance, fit)

    for value in ("101", "202", "303", "404", "0.505", "0.606"):
        assert value in text


def test_fit_text_and_csv_include_attached_diagnostics() -> None:
    from app_desktop.window_fitting_mixin import WindowFittingMixin

    instance = _MinimalSelf(is_en=True)
    fit = _make_fit_result(
        params={"a": mp.mpf("1"), "b": mp.mpf("2")},
        stat={"a": mp.mpf("2"), "b": mp.mpf("3")},
    )
    fit.chi2 = mp.mpf("4.6051701859880913680359829093687284152022029772575")
    fit.reduced_chi2 = fit.chi2 / 2
    fit.residuals = [mp.mpf("1"), mp.mpf("-2")]
    fit.rmse = mp.mpf("2")
    fit.covariance = [[mp.mpf("4"), mp.mpf("6")], [mp.mpf("6"), mp.mpf("9")]]
    fit.details["dof"] = 2
    fit.details["covariance_parameters"] = ["a", "b"]
    attach_fit_diagnostics(fit, sigma_series=[mp.mpf("2"), mp.mpf("4")])

    text = _format(instance, fit)
    rows = WindowFittingMixin._build_fit_csv_rows(  # type: ignore[misc]
        instance,  # type: ignore[arg-type]
        fit,
        "a*x + b",
    )

    assert "χ² p-value" in text
    assert "Max standardized residual" in text
    assert "Parameter Correlation Matrix" in text
    assert "Sigma-standardized residual" in text
    by_name = {str(row["name"]): row for row in rows}
    assert by_name["chi_square_p_value"]["section"] == "metric"
    assert by_name["max_standardized_residual"]["value"] == "0.5"
    assert by_name["corr[a,b]"]["section"] == "correlation"
    assert by_name["standardized_residual[1]"]["note"] == "Sigma-standardized residual"


def test_fit_text_includes_model_and_substituted_as_bold_metadata() -> None:
    """Model + substituted-expression should appear as Markdown
    bold-prefix metadata (``**模型**:`` / ``**Model**:``), matching the
    sibling formatters."""
    instance = _MinimalSelf(is_en=False)
    text = _format(
        instance,
        _make_fit_result(params={"a": mp.mpf("1.5")}),
        expression="a*x",
        substituted="1.5*x",
    )
    assert "**模型**" in text or "**Model**" in text, (
        "Metadata header must be Markdown-bold.\n\nOutput was:\n" + text
    )
    assert "a*x" in text
    assert "1.5*x" in text


def test_fit_text_handles_systematic_errors_in_table() -> None:
    """When systematic errors are present, the parameter table should
    keep the new column structure, not regress to the parenthesised
    inline form."""
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        stat={"a": mp.mpf("0.01")},
        sys={"a": mp.mpf("0.005")},
    )
    text = _format(instance, fit)
    # The legacy form put systematic errors as
    # "1.5 ± 0.01 (统计 0.01, 系统 0.005)" — verify it's gone.
    assert "(统计" not in text and "(stat" not in text, (
        "Systematic errors must use a Markdown table column, not "
        "the legacy parenthesised inline form.\n\nOutput was:\n" + text
    )
    assert "0.005" in text  # the systematic value still appears


def test_fit_text_warnings_render_below_table() -> None:
    """Boundary / systematic warnings should still appear, prefixed
    with a Markdown bold ``**警告**`` so they stand out visually
    matching the sibling formatters' convention."""
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        extras={
            "boundary_warning": "参数 a 触及边界 / Parameter a hit boundary",
        },
    )
    text = _format(instance, fit)
    assert "**警告**" in text or "**Warning**" in text, (
        "Warnings should render as bold Markdown metadata.\n\n"
        "Output was:\n" + text
    )
    assert "边界" in text or "boundary" in text


def test_fit_text_systematic_warning_renders_with_bold_prefix() -> None:
    """``systematic_warning`` is a separate ``details`` key from
    ``boundary_warning`` and lives on its own branch in the
    formatter — guard against a regression that drops one of them."""
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        extras={
            "systematic_warning": "系统误差不收敛 / Systematic error did not converge",
        },
    )
    text = _format(instance, fit)
    assert "**警告**" in text, (
        "systematic_warning must render as bold Markdown metadata.\n\n"
        "Output was:\n" + text
    )
    assert "系统误差不收敛" in text


def test_fit_text_uncertainty_note_dict_form_renders_zh_then_en() -> None:
    """``details["uncertainty_note"]`` can be either a plain string
    (already-localized) or a ``{"zh": ..., "en": ...}`` dict that
    the formatter must split per the active locale."""
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        extras={
            "uncertainty_note": {
                "zh": "序列加速不确定度估计为启发式量。",
                "en": "Sequence-acceleration uncertainty is heuristic.",
            },
        },
    )
    zh_text = _format(_MinimalSelf(is_en=False), fit)
    en_text = _format(_MinimalSelf(is_en=True), fit)
    assert "**说明**" in zh_text and "启发式" in zh_text, (
        f"ZH dict-form note must render with bold prefix.\n\n{zh_text}"
    )
    assert "**Note**" in en_text and "heuristic" in en_text, (
        f"EN dict-form note must render with bold prefix.\n\n{en_text}"
    )


def test_fit_text_uncertainty_note_string_form_renders_localized() -> None:
    """``details["uncertainty_note"]`` as a plain string takes the
    ``" / "`` bilingual-marker path through ``_localize_text``."""
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        extras={
            "uncertainty_note": "请人工验证 / Please verify manually",
        },
    )
    text = _format(instance, fit)
    assert "**说明**" in text, (
        "String-form uncertainty_note must render with bold prefix.\n\n"
        + text
    )
    # The ZH side of the " / " split should appear in zh mode
    assert "请人工验证" in text
    # The EN half must NOT leak into the ZH render
    assert "Please verify manually" not in text


# ---------------------------------------------------------------- compatibility

def test_fit_text_still_carries_all_legacy_information() -> None:
    """Every piece of information the old formatter emitted must
    survive into the Markdown version — only presentation changed."""
    instance = _MinimalSelf(is_en=False)
    fit = _make_fit_result(
        params={"a": mp.mpf("1.5")},
        stat={"a": mp.mpf("0.01")},
        extras={"weighted": True},
    )
    text = _format(
        instance, fit, expression="a*x + 0", substituted="1.5*x + 0",
    )
    # Required content carry-over
    for required in ["a*x + 0", "1.5*x + 0", "1.5", "0.01", "0.5", "12.3"]:
        assert required in text, (
            f"Required content {required!r} missing from output.\n\n"
            f"Output:\n{text}"
        )
    assert "加权" in text or "Weighted" in text
