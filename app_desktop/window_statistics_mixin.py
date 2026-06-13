from __future__ import annotations

import io
from pathlib import Path

import mpmath as mp

from data_extrapolation_latex_latest import _dual_msg
from statistics_utils import compute_statistics, generate_statistics_latex

from .workers_core import _mp_precision_guard


class WindowStatisticsMixin:
    def _run_statistics_mode(self, generate_latex: bool, output_path: str):
        precision = self._read_precision()
        with _mp_precision_guard(precision):
            self._set_fit_output_precision(precision)
            headers, rows, sigma_rows = self._collect_fitting_dataset(precision_hint=precision)
            value_col = self.stats_value_column_edit.text().strip()
            if not value_col:
                raise ValueError(
                    _dual_msg(
                        "请在统计设置中指定数值列。",
                        "Please select the value column in statistics settings.",
                    )
                )
            values = self._column_series(headers, rows, value_col)

            n = len(values)
            if n == 0:
                raise ValueError(_dual_msg("统计列中没有数据。", "No data in the statistics column."))

            sigma_col = self.stats_sigma_column_edit.text().strip()
            sigmas = self._resolve_uncertainties(
                headers,
                rows,
                sigma_rows,
                value_col,
                sigma_col if sigma_col else None,
            )

            result = compute_statistics(
                values,
                sigmas,
                self.stats_mode_combo.currentData(),
                use_sample=self.stats_sample_checkbox.isChecked(),
                use_weighted_variance=self.stats_weight_variance_checkbox.isChecked(),
            )
        mean = result["mean"]
        std_mean = result["std_mean"]
        std = result["std"]
        v_min = result["v_min"]
        v_max = result["v_max"]
        method_label = result["method_label"]
        if result.get("dropped", 0):
            self._append_log(
                self._tr(
                    f"提示: 有 {result['dropped']} 行因缺失或非正 σ 被忽略。",
                    f"Notice: {result['dropped']} rows skipped due to missing or non-positive sigma.",
                )
            )
        eff_n = result.get("effective_n")

        mean_str = self._format_uncertainty_value(mean, std_mean)
        lines = [
            self._tr("## 统计平均结果", "## Statistics Results"),
            "",
            self._tr(f"**模式**: {method_label}", f"**Mode**: {method_label}"),
            self._tr(f"**数据点数**: n = {n}", f"**Data points**: n = {n}"),
            self._tr(f"**列名**: {value_col}", f"**Column**: {value_col}"),
            "",
            self._tr("| 指标 | 值 |", "| Metric | Value |"),
            "| --- | --- |",
            self._tr(
                f"| 平均值 (带标准误差) | {mean_str} |",
                f"| Mean (with SE) | {mean_str} |",
            ),
            self._tr(
                f"| 平均值 | {self._format_precision_value(mean)} |",
                f"| Mean | {self._format_precision_value(mean)} |",
            ),
            self._tr(
                f"| 标准误差 σ_mean | {self._format_precision_value(std_mean)} |",
                f"| Std. error σ_mean | {self._format_precision_value(std_mean)} |",
            ),
        ]
        if eff_n is not None:
            lines.append(
                self._tr(
                    f"| 加权有效点数 n_eff | {self._format_precision_value(eff_n)} |",
                    f"| Weighted effective n_eff | {self._format_precision_value(eff_n)} |",
                )
            )
        if not mp.isnan(std):
            lines.append(
                self._tr(
                    f"| 标准差 σ | {self._format_precision_value(std)} |",
                    f"| Std. dev. σ | {self._format_precision_value(std)} |",
                )
            )
        lines.extend(
            [
                self._tr(
                    f"| 最小值 min | {self._format_precision_value(v_min)} |",
                    f"| Min | {self._format_precision_value(v_min)} |",
                ),
                self._tr(
                    f"| 最大值 max | {self._format_precision_value(v_max)} |",
                    f"| Max | {self._format_precision_value(v_max)} |",
                ),
            ]
        )
        self._set_result_text("\n".join(lines), final_result=True)
        self._append_log(self._tr("统计平均计算完成。", "Statistics completed."))
        if generate_latex and output_path:
            digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
            generate_statistics_latex(
                value_col,
                rows,
                sigma_rows,
                result,
                digits,
                output_path,
                self.dcolumn_checkbox.isChecked(),
                uncertainty_digits=self._uncertainty_digits_value(),
                caption=self._caption_value(),
            )
            self._append_log(f"统计平均 LaTeX 已写入: {output_path}")
            self._load_latex_into_editor(output_path)

    def _build_stats_csv_rows(self, result: dict, batch_idx: int | None = None, row_count: int | None = None) -> list[dict[str, object]]:
        def _fmt(val) -> str:
            return self._format_display_value(val)

        batch_value = batch_idx if batch_idx is not None else 1
        rows: list[dict[str, object]] = [
            {"batch": batch_value, "metric": "method", "value": result.get("method_label", ""), "uncertainty": ""},
            {
                "batch": batch_value,
                "metric": "mean",
                "value": _fmt(result.get("mean", mp.nan)),
                "uncertainty": _fmt(result.get("std_mean", mp.nan)),
            },
        ]
        if row_count is not None:
            rows.append({"batch": batch_value, "metric": "rows", "value": row_count, "uncertainty": ""})
        std_val = result.get("std", mp.nan)
        try:
            std_is_nan = mp.isnan(mp.mpf(std_val))
        except Exception:
            std_is_nan = False
        if not std_is_nan:
            rows.append({"batch": batch_value, "metric": "std", "value": _fmt(std_val), "uncertainty": ""})
        rows.extend(
            [
                {"batch": batch_value, "metric": "min", "value": _fmt(result.get("v_min", mp.nan)), "uncertainty": ""},
                {"batch": batch_value, "metric": "max", "value": _fmt(result.get("v_max", mp.nan)), "uncertainty": ""},
            ]
        )
        eff = result.get("effective_n")
        if eff is not None:
            rows.append({"batch": batch_value, "metric": "effective_n", "value": _fmt(eff), "uncertainty": ""})
        dropped = result.get("dropped", 0)
        if dropped:
            rows.append({"batch": batch_value, "metric": "dropped", "value": dropped, "uncertainty": ""})
        if result.get("zero_sigma_anchor"):
            rows.append({"batch": batch_value, "metric": "zero_sigma_anchor", "value": "True", "uncertainty": ""})
        return rows

    def _render_statistics_text(self, result: dict, value_col: str, n: int) -> str:
        mean = result.get("mean", mp.nan)
        std_mean = result.get("std_mean", mp.nan)
        std = result.get("std", mp.nan)
        v_min = result.get("v_min", mp.nan)
        v_max = result.get("v_max", mp.nan)
        method_label = result.get("method_label", "")
        eff_n = result.get("effective_n", None)
        show_eff_n = eff_n is not None and "Weighted" in str(method_label)

        def _fmt_plain(val: mp.mpf) -> str:
            return self._format_display_value(val)

        mean_str = f"{self._format_display_value(mean)} ± {self._format_display_value(std_mean)}"
        lines = [
            self._tr("=== 统计平均结果 ===", "=== Statistics ==="),
            self._tr(f"模式: {method_label}", f"Mode: {method_label}"),
            self._tr(f"数据点数 n = {n}", f"Data points n = {n}"),
            self._tr(f"列名: {value_col}", f"Column: {value_col}"),
            "",
            self._tr(f"平均值 (带标准误差): {mean_str}", f"Mean (with SE): {mean_str}"),
            self._tr(f"平均值 = { _fmt_plain(mean)}", f"Mean = { _fmt_plain(mean)}"),
            self._tr(
                f"标准误差 σ_mean = { _fmt_plain(std_mean)}",
                f"Std. error σ_mean = { _fmt_plain(std_mean)}",
            ),
        ]
        if show_eff_n:
            lines.append(
                self._tr(
                    f"加权有效点数 n_eff = { _fmt_plain(eff_n)}",
                    f"Weighted effective n_eff = { _fmt_plain(eff_n)}",
                )
            )
        if not mp.isnan(std):
            lines.append(
                self._tr(
                    f"标准差 σ = { _fmt_plain(std)}",
                    f"Std. dev. σ = { _fmt_plain(std)}",
                )
            )
        lines.extend(
            [
                "",
                self._tr(
                    f"最小值 min = { _fmt_plain(v_min)}",
                    f"Min = { _fmt_plain(v_min)}",
                ),
                self._tr(
                    f"最大值 max = { _fmt_plain(v_max)}",
                    f"Max = { _fmt_plain(v_max)}",
                ),
            ]
        )
        dropped = result.get("dropped", 0)
        if dropped:
            lines.append(
                self._tr(
                    f"提示: 有 {dropped} 行因缺失或非正 σ 被忽略。",
                    f"Notice: {dropped} rows skipped due to missing or non-positive sigma.",
                )
            )
        return "\n".join(lines)

    def _format_statistics_display(self, result: dict, value_col: str, n: int) -> tuple[str, list[dict[str, object]]]:
        """Return formatted statistics text/CSV rows (numbers only; LaTeX unchanged elsewhere)."""
        text = self._render_statistics_text(result, value_col, n)
        csv_rows = self._build_stats_csv_rows(result, batch_idx=1, row_count=n)
        return text, csv_rows

    def _format_statistics_batches_display(self, batches: list[dict], value_col: str) -> tuple[str, list[dict[str, object]]]:
        block_texts: list[str] = []
        csv_rows: list[dict[str, object]] = []
        for entry in batches:
            idx = entry.get("index") or (len(block_texts) + 1)
            row_count = entry.get("row_count") or len(entry.get("rows", []) or [])
            body = self._render_statistics_text(entry.get("result", {}), value_col, row_count)
            body_lines = body.splitlines()
            if body_lines and body_lines[0].startswith("==="):
                body_lines = body_lines[1:]
            header = self._tr(f"=== 统计结果：批次 {idx} ===", f"=== Statistics: Batch {idx} ===")
            block_texts.append("\n".join([header, *body_lines]))
            csv_rows.extend(self._build_stats_csv_rows(entry.get("result", {}), batch_idx=idx, row_count=row_count))
        return "\n\n".join(block_texts), csv_rows

    def _display_statistics_result(
        self,
        result: dict,
        value_col: str,
        n: int,
        values: list[mp.mpf] | None = None,
        sigmas: list[mp.mpf | None] | None = None,
        render_plots: bool = True,
    ):
        text, csv_rows = self._format_statistics_display(result=result, value_col=value_col, n=n)
        if result.get("dropped", 0):
            self._append_log(
                self._tr(
                    f"提示: 有 {result['dropped']} 行因缺失或非正 σ 被忽略。",
                    f"Notice: {result['dropped']} rows skipped due to missing or non-positive sigma.",
                )
            )
        self._set_result_text(text, final_result=True)
        if csv_rows:
            self._set_csv_data(csv_rows, ["batch", "metric", "value", "uncertainty"], suggestion="statistics_results.csv")
        else:
            self._reset_csv_data()
        plot_bytes = None
        if render_plots and values:
            plot_bytes = self._render_statistics_plot(values, sigmas, result, batch_idx=None)
        if plot_bytes:
            img_path = self._save_batch_figure(plot_bytes, "", 1, prefix="stats")
            if img_path:
                self._set_image_list("stats", [img_path])
                self._image_mode = "stats"
                return
        self._image_mode = "stats"
        self._result_plot_base_pixmap = None
        self.result_plot_bytes = None
        self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
        self.current_stats_figures = []
        self.current_stats_index = 0
        self._update_image_status()
        self._remember_last_result("statistics_single", {"result": result, "value_col": value_col, "n": n})

    def _display_error_contributions(self, breakdown: list[dict[str, object]], plot_bytes: bytes | None):
        if breakdown:
            lines = [self._tr("=== 不确定度贡献分解 ===", "=== Uncertainty breakdown ===")]
            for entry in breakdown:
                name = entry.get("name", "")
                percent = entry.get("percent", 0.0)
                sigma = entry.get("sigma", mp.mpf("0"))
                try:
                    sigma_val = sigma if isinstance(sigma, mp.mpf) else mp.mpf(sigma)
                except Exception:
                    sigma_val = mp.mpf("0")
                lines.append(f"{name}: {percent:.2f}% (σ={mp.nstr(sigma_val, 8)})")
            self._append_log("\n".join(lines))
        if plot_bytes:
            self._image_mode = "error"
            self._update_result_plot(plot_bytes, final_result=True)

    def _display_statistics_batches(self, batches: list[dict], value_col: str, render_plots: bool = True):
        if not batches:
            self._set_result_text("", final_result=True)
            self._image_mode = "stats"
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._update_image_status()
            self._reset_csv_data()
            return
        figure_paths: list[Path] = []
        block_texts: list[str] = []
        csv_rows: list[dict[str, object]] = []
        for entry in batches:
            idx = entry.get("index") or (len(block_texts) + 1)
            row_count = entry.get("row_count") or len(entry.get("rows", []) or [])
            body = self._render_statistics_text(entry.get("result", {}), value_col, row_count)
            body_lines = body.splitlines()
            if body_lines and body_lines[0].startswith("==="):
                body_lines = body_lines[1:]
            header = self._tr(f"=== 统计结果：批次 {idx} ===", f"=== Statistics: Batch {idx} ===")
            block_texts.append("\n".join([header, *body_lines]))
            dropped = entry.get("result", {}).get("dropped", 0)
            if dropped:
                self._append_log(
                    self._tr(
                        f"提示: 批次 {idx} 有 {dropped} 行因缺失或非正 σ 被忽略。",
                        f"Notice: batch {idx} skipped {dropped} rows due to missing or non-positive sigma.",
                    )
                )
            headers = entry.get("headers") or []
            rows = entry.get("rows") or []
            sigma_rows = entry.get("sigma_rows") or []
            val_col = entry.get("value_col") or value_col
            values = entry.get("values")
            sigmas = entry.get("sigmas")
            if (not values) and headers and rows and val_col in headers:
                val_idx = headers.index(val_col)
                values = [row[val_idx] for row in rows]
                sigmas = []
                for sigma_row in sigma_rows:
                    if val_idx < len(sigma_row):
                        entry_sigma = sigma_row[val_idx]
                        if hasattr(entry_sigma, "uncertainty"):
                            entry_sigma = getattr(entry_sigma, "uncertainty", None)
                        try:
                            sigmas.append(mp.mpf(entry_sigma) if entry_sigma is not None else None)
                        except Exception:
                            sigmas.append(None)
                    else:
                        sigmas.append(None)
            if render_plots and values:
                plot_bytes = self._render_statistics_plot(values, sigmas, entry.get("result", {}), batch_idx=idx)
                if plot_bytes:
                    img_path = self._save_batch_figure(plot_bytes, "", idx, prefix="stats")
                    if img_path:
                        figure_paths.append(img_path)
            csv_rows.extend(self._build_stats_csv_rows(entry.get("result", {}), batch_idx=idx, row_count=row_count))
        self._set_result_text("\n\n".join(block_texts), final_result=True)
        if csv_rows:
            self._set_csv_data(csv_rows, ["batch", "metric", "value", "uncertainty"], suggestion="statistics_results.csv")
        else:
            self._reset_csv_data()
        self._image_mode = "stats"
        if figure_paths:
            self._set_image_list("stats", figure_paths)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self.current_stats_figures = []
            self.current_stats_index = 0
            self._update_image_status()
        self._remember_last_result("statistics_batches", {"batches": batches, "value_col": value_col})

    def _render_statistics_plot(
        self,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None] | None,
        stats_result: dict[str, object],
        batch_idx: int | None = None,
    ) -> bytes | None:
        if not values:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            return None
        try:
            xs = list(range(1, len(values) + 1))
            ys = [float(mp.mpf(v)) for v in values]
            yerr = None
            if sigmas and any(s is not None for s in sigmas):
                yerr = [abs(float(mp.mpf(s))) if s is not None else 0.0 for s in sigmas]
            mean_val = stats_result.get("mean", None)
            std_mean = stats_result.get("std_mean", None)
            mean_f = float(mean_val) if mean_val is not None else None
            std_mean_f = abs(float(std_mean)) if std_mean is not None else None

            fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=180)
            if yerr:
                ax.errorbar(
                    xs,
                    ys,
                    yerr=yerr,
                    fmt="o-",
                    color="#1f77b4",
                    ecolor="#555555",
                    capsize=4,
                    label=self._tr("数据", "Data"),
                )
            else:
                ax.plot(xs, ys, "o-", color="#1f77b4", label=self._tr("数据", "Data"))
            if mean_f is not None:
                ax.axhline(mean_f, color="#d62728", linestyle="--", label=self._tr("平均值", "Mean"))
                if std_mean_f is not None and std_mean_f > 0:
                    ax.fill_between(
                        [min(xs) - 0.2, max(xs) + 0.2],
                        mean_f - std_mean_f,
                        mean_f + std_mean_f,
                        color="#d62728",
                        alpha=0.15,
                        label=self._tr("平均值±标准误差", "Mean ± SE"),
                    )
            ax.set_xlabel(self._tr("点序号", "Point index"))
            ax.set_ylabel(self._tr("数值", "Value"))
            title = self._tr("统计平均", "Statistics")
            if batch_idx is not None:
                title += f" #{batch_idx}"
            ax.set_title(title)
            ax.grid(True, alpha=0.3)
            ax.legend(frameon=False)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception:
            return None
