"""Phase 7 #19 split — shared formatters used by Params / Models /
Residuals mixins.

These methods produce DISPLAY artefacts (text, CSV rows, LaTeX
preamble + table blocks, parameter-substituted expression strings)
from a ``FitResult``. They are intentionally cross-cutting:

- ``_build_substituted_expression`` — used by both models (LaTeX
  output) and residuals (result panel "with-params" line)
- ``_infer_parameter_names`` — thin wrapper over
  ``fitting.infer_parameter_names``; called by params + models
- ``_format_fit_result_text`` / ``_format_fit_display`` — text
  rendering for the result panel
- ``_build_fit_csv_rows`` — CSV export rows
- ``_latex_escape`` / ``_fit_latex_preamble`` / ``_fit_latex_block``
  — LaTeX output thin wrappers over ``fitting_latex_writer``

All methods are extracted VERBATIM from the original
``window_fitting_mixin.py``. No behavior change. They reference
``self.*`` attributes/methods (``self._tr``, ``self.fit_target_edit``,
``self._format_uncertainty_value``, etc.) provided by sibling
mixins or the host ``ExtrapolationWindow`` — Python MRO resolves
those at call time.

Methods MOVED here from window_fitting_mixin.py (line numbers
refer to the pre-Phase-7 monolith and are frozen as one-time
migration context — they will NOT be kept in sync with future
changes; see ``git log`` for canonical history):
- _build_substituted_expression       (was line 161)
- _infer_parameter_names              (was line 180)
- _format_fit_result_text             (was line 185)
- _format_fit_display                 (was line 244)
- _build_fit_csv_rows                 (was line 308)
- _latex_escape                       (was line 428)
- _fit_latex_preamble                 (was line 431)
- _fit_latex_block                    (was line 438)
"""
from __future__ import annotations

import re
from pathlib import Path

import mpmath as mp

from fitting import infer_parameter_names
from fitting.hp_fitter import FitResult

from . import fitting_latex_writer as _fit_latex_writer


class WindowFittingFormattersMixin:
    def _build_substituted_expression(self, expression: str, params: dict[str, mp.mpf], digits: int | None = None) -> str:
        if not expression:
            return ""

        parameter_names = set(params.keys())
        # Use specified digits for LaTeX output, or fall back to fit output digits
        precision = digits if digits is not None else getattr(self, "_fit_output_digits", 12)

        def repl(match: re.Match[str]) -> str:
            name = match.group(0)
            if name in parameter_names:
                mp_value = mp.mpf(params[name])
                if mp.isnan(mp_value) or mp.isinf(mp_value):
                    return str(mp_value)
                return mp.nstr(mp_value, precision)
            return name

        return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", repl, expression)

    def _infer_parameter_names(
        self,
        expression: str,
        variable_names: list[str],
        config_keys: list[str],
        constants: list[str] | None = None,
    ) -> list[str]:
        return infer_parameter_names(
            expression,
            variable_names,
            config_keys,
            constants=constants,
        )

    def _format_fit_result_text(
        self, fit_result: FitResult, expression: str | None, substituted: str | None
    ) -> str:
        """Render a fit result as Markdown for ``setMarkdown`` display.

        The format mirrors the extrapolation / error-propagation /
        statistics formatters: an ``## H2`` heading, ``**bold**``
        metadata lines, then one or two Markdown tables. The previous
        ``=== 拟合结果 ===`` plain-text form rendered acceptably under
        ``setMarkdown`` but was visually inconsistent with the three
        sibling features. Aligning it removes a long-standing UI
        wart without changing what information is shown.

        Three structural tables are produced:
        1. **Parameters** — name | value ± total | stat σ | sys σ
           (the ``stat σ`` and ``sys σ`` columns appear only when
           any parameter has a non-zero systematic error, mirroring
           the legacy formatter's "show only when present" rule).
        2. **Goodness of fit** — chi-square stats, AIC/BIC, R², RMSE.
        3. (No third table — warnings render as bold metadata below.)
        """
        params_dict = fit_result.params
        total_errors = fit_result.param_errors_total or fit_result.param_errors
        stat_errors = fit_result.param_errors_stat or {}
        sys_errors = fit_result.param_errors_sys or {}

        # Show systematic-error columns only when at least one parameter
        # actually has a non-zero systematic error — keeps the table
        # compact for the common (statistics-only) case.
        # Use an explicit absolute threshold rather than ``mp.almosteq``
        # so the guard's behaviour is independent of the active
        # ``mp.dps`` (which makes ``almosteq``'s default tolerance
        # vary by ~1e-77 at dps=80) — production ``sys_errors`` dicts
        # contain exact ``mp.mpf("0")`` for unrefitted parameters, but
        # a future near-zero refit residual must still collapse to
        # the 2-column table for visual parity with the legacy form.
        _SYS_THRESHOLD = mp.mpf("1e-30")
        has_systematic = any(
            mp.fabs(err) > _SYS_THRESHOLD
            for err in sys_errors.values()
            if err is not None
        )

        lines: list[str] = [self._tr("## 拟合结果", "## Fit Results"), ""]

        # ---- metadata block (model + substituted) -----------------
        if expression:
            lines.append(
                self._tr(f"**模型**: `{expression}`", f"**Model**: `{expression}`")
            )
        if substituted:
            lines.append(
                self._tr(
                    f"**代入参数**: `{substituted}`",
                    f"**With params**: `{substituted}`",
                )
            )
        lines.append("")

        # ---- parameters table ------------------------------------
        if has_systematic:
            header_cells = self._tr(
                "| 参数 | 值 ± 总误差 | 统计 σ | 系统 σ |",
                "| Parameter | Value ± Total | Stat σ | Sys σ |",
            )
            sep_cells = "| --- | --- | --- | --- |"
        else:
            header_cells = self._tr(
                "| 参数 | 值 ± 误差 |",
                "| Parameter | Value ± Error |",
            )
            sep_cells = "| --- | --- |"
        lines.append(header_cells)
        lines.append(sep_cells)
        for name, value in params_dict.items():
            total_err = total_errors.get(name, mp.mpf("0"))
            stat_err = stat_errors.get(name, total_err)
            sys_err = sys_errors.get(name, mp.mpf("0"))
            value_cell = self._format_uncertainty_value(value, total_err)
            if has_systematic:
                stat_cell = self._format_precision_value(stat_err)
                sys_cell = self._format_precision_value(sys_err)
                lines.append(
                    f"| {name} | {value_cell} | {stat_cell} | {sys_cell} |"
                )
            else:
                lines.append(f"| {name} | {value_cell} |")
        lines.append("")

        # ---- goodness-of-fit metrics table -----------------------
        lines.append(self._tr("| 指标 | 值 |", "| Metric | Value |"))
        lines.append("| --- | --- |")
        metrics: list[tuple[str, mp.mpf]] = [
            ("χ²", fit_result.chi2),
            (self._tr("Reduced χ²", "Reduced χ²"), fit_result.reduced_chi2),
            ("AIC", fit_result.aic),
            ("BIC", fit_result.bic),
            ("R²", fit_result.r2),
            ("RMSE", fit_result.rmse),
        ]
        for label, value in metrics:
            lines.append(f"| {label} | {self._format_precision_value(value)} |")
        lines.append("")

        # ---- weighted-fit note + uncertainty note + warnings -----
        # Each renders as a bold metadata line (matching the sibling
        # formatters' ``**说明**`` / ``**警告**`` convention).
        if fit_result.details.get("weighted"):
            lines.append(
                self._tr(
                    "**说明**: 使用测量不确定度加权拟合。",
                    "**Note**: Weighted by measurement uncertainty.",
                )
            )
        note = fit_result.details.get("uncertainty_note")
        if isinstance(note, dict):
            zh_note = note.get("zh", "")
            en_note = note.get("en", "")
            if zh_note or en_note:
                lines.append(
                    self._tr(f"**说明**: {zh_note}", f"**Note**: {en_note}")
                )
        elif note:
            localized_note = self._localize_text(str(note))
            lines.append(
                self._tr(
                    f"**说明**: {localized_note}",
                    f"**Note**: {localized_note}",
                )
            )
        sys_warning = fit_result.details.get("systematic_warning")
        if sys_warning:
            localized = self._localize_text(str(sys_warning))
            lines.append(
                self._tr(f"**警告**: {localized}", f"**Warning**: {localized}")
            )
        warning = fit_result.details.get("boundary_warning")
        if warning:
            localized = self._localize_text(str(warning))
            lines.append(
                self._tr(f"**警告**: {localized}", f"**Warning**: {localized}")
            )
        return "\n".join(lines)

    def _format_fit_display(self, fit_result: FitResult, expression: str | None, substituted: str | None, batch_idx: int = 1, **_ignored) -> tuple[str, list[dict[str, object]]]:
        """Return formatted fit summary text/CSV rows (numbers only; LaTeX unaffected)."""
        text = self._format_fit_result_text(fit_result, expression, substituted)
        csv_rows = self._build_fit_csv_rows(fit_result, expression or "", batch_idx=batch_idx)
        return text, csv_rows

    def _build_fit_csv_rows(self, fit_result: FitResult, expression: str | None, batch_idx: int | None = None) -> list[dict[str, object]]:
        def _fmt(val) -> str:
            return self._format_display_value(val)

        batch_value = batch_idx if batch_idx is not None else 1
        rows: list[dict[str, object]] = []
        if expression:
            rows.append(
                {
                    "batch": batch_value,
                    "section": "model",
                    "name": "expression",
                    "value": expression,
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        for name, value in fit_result.params.items():
            total_err = (fit_result.param_errors_total or fit_result.param_errors).get(name, mp.mpf("0"))
            stat_err = (fit_result.param_errors_stat or {}).get(name)
            sys_err = (fit_result.param_errors_sys or {}).get(name)
            rows.append(
                {
                    "batch": batch_value,
                    "section": "parameter",
                    "name": name,
                    "value": _fmt(value),
                    "uncertainty": _fmt(total_err),
                    "stat_error": _fmt(stat_err) if stat_err is not None else "",
                    "sys_error": _fmt(sys_err) if sys_err is not None else "",
                    "note": "",
                }
            )
        metrics = [
            ("chi2", fit_result.chi2),
            ("reduced_chi2", fit_result.reduced_chi2),
            ("aic", fit_result.aic),
            ("bic", fit_result.bic),
            ("r2", fit_result.r2),
            ("rmse", fit_result.rmse),
        ]
        for name, value in metrics:
            rows.append(
                {
                    "batch": batch_value,
                    "section": "metric",
                    "name": name,
                    "value": _fmt(value),
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        cov = getattr(fit_result, "covariance", None)
        if cov:
            for i, cov_row in enumerate(cov):
                for j, cov_val in enumerate(cov_row):
                    rows.append(
                        {
                            "batch": batch_value,
                            "section": "covariance",
                            "name": f"cov[{i + 1},{j + 1}]",
                            "value": _fmt(cov_val),
                            "uncertainty": "",
                            "stat_error": "",
                            "sys_error": "",
                            "note": "",
                        }
                    )
        if fit_result.details.get("weighted"):
            rows.append(
                {
                    "batch": batch_value,
                    "section": "note",
                    "name": "weighted",
                    "value": "True",
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        note = fit_result.details.get("uncertainty_note")
        if note:
            localized = ""
            if isinstance(note, dict):
                localized = note.get("en" if self._is_en() else "zh", "") or str(note)
            else:
                localized = self._localize_text(str(note))
            rows.append(
                {
                    "batch": batch_value,
                    "section": "note",
                    "name": "uncertainty_note",
                    "value": localized,
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        sys_warning = fit_result.details.get("systematic_warning")
        if sys_warning:
            rows.append(
                {
                    "batch": batch_value,
                    "section": "note",
                    "name": "systematic_warning",
                    "value": self._localize_text(str(sys_warning)),
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        return rows

    def _latex_escape(self, text: str) -> str:
        return _fit_latex_writer.latex_escape(text)

    def _fit_latex_preamble(self, use_dcolumn: bool, digits: int, latex_group_size: int) -> list[str]:
        return _fit_latex_writer.build_fit_latex_preamble(
            use_dcolumn=use_dcolumn,
            digits=digits,
            latex_group_size=latex_group_size,
        )

    def _fit_latex_block(
        self,
        headers: list[str],
        rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[mp.mpf | None, ...]],
        fit_result: FitResult,
        expression: str,
        substituted: str,
        image_path: Path | None,
        use_dcolumn: bool,
        digits: int,
        *,
        latex_group_size: int = 3,
        batch_index: int | None = None,
    ) -> list[str]:
        default_unc_digits = self._uncertainty_digits_value()
        target_column = self.fit_target_edit.text().strip()
        try:
            variable_pairs = self._ordered_variable_pairs(headers)
        except Exception:
            variable_pairs = []
        caption_base = self._caption_value() if hasattr(self, "_caption_value") else None

        if expression and fit_result.params:
            cleaned_sub = (
                self._build_substituted_expression(expression, fit_result.params, digits).strip().replace("**", "^")
            )
        else:
            cleaned_sub = (substituted or "").strip().replace("**", "^")

        return _fit_latex_writer.build_fit_latex_block(
            headers=headers,
            rows=rows,
            sigma_rows=sigma_rows,
            fit_result=fit_result,
            expression=expression,
            substituted=substituted,
            image_path=image_path,
            use_dcolumn=use_dcolumn,
            digits=digits,
            latex_group_size=latex_group_size,
            batch_index=batch_index,
            target_column=target_column,
            variable_pairs=variable_pairs,
            caption_text=caption_base,
            default_uncertainty_digits=default_unc_digits,
            cleaned_substituted=cleaned_sub,
        )
