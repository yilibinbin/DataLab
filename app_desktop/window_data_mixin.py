from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mpmath as mp

from PySide6.QtWidgets import QMessageBox

from data_extrapolation_latex_latest import _dual_msg, parse_uncertainty_format
from app_desktop.fitting_input_normalization import (
    fit_uncertainty_policy,
    normalize_data_uncertainty,
)
from extrapolation_methods import PowerLawConfig
from shared.input_normalization import normalize_constants_state, parse_constants_text, parse_input_sections
from shared.parsing import parse_clipboard_tabular
from shared.uncertainty import has_explicit_uncertainty

from .panels import (
    _REFCOL_AUTO_MAX_DIFF_EN,
    _REFCOL_AUTO_MAX_DIFF_KEY,
    _REFCOL_AUTO_MAX_DIFF_ZH,
)
from .workers_core import _mp_precision_guard, _safe_read_text, _safe_resolve_path


@dataclass(frozen=True)
class InputBundle:
    data_path: Path | None
    data_text: str
    constants_text: str
    constants_rows: tuple[dict[str, str], ...]
    source_kind: str
    explicit_sections: bool
    constants_view: str = "table"
    constants_numeric_mode: str = "uncertainty"


@dataclass(frozen=True)
class InputConstantsSource:
    rows_value: tuple[dict[str, str], ...]
    text_value: str
    view_value: str
    numeric_mode_value: str

    def isChecked(self) -> bool:  # noqa: N802 - Qt-style adapter API
        return bool(self.rows_value or self.text_value.strip())

    def using_text_view(self) -> bool:
        return self.view_value == "text"

    def rows(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.rows_value]

    def raw_text(self) -> str:
        return self.text_value

    def text(self) -> str:
        if self.text_value.strip():
            return self.text_value
        return "\n".join(
            f"{row.get('name', '')} {row.get('value', '')}".strip()
            for row in self.rows_value
            if row.get("name") or row.get("value")
        )

    def numeric_mode(self) -> str:
        return self.numeric_mode_value

    def constants_dict(self, *, validate: bool = True) -> dict[str, str]:
        return normalize_constants_state(
            enabled=True,
            view=self.view_value,
            rows=self.rows_value,
            text=self.text_value,
            numeric_mode=self.numeric_mode_value,
        ).compute_dict(validate=validate)


class WindowDataMixin:
    # ------------------------------------------------------------- Utilities --
    def _read_precision(self) -> int:
        if not hasattr(self, "mpmath_precision_spin"):
            raise ValueError("多精度位数控件缺失。 / Multiprecision digits control missing.")
        value = int(self.mpmath_precision_spin.value())
        self._current_precision = value
        return value

    def _build_power_law_config(self, precision: int | None) -> PowerLawConfig:
        x_values = []
        for idx, edit in enumerate(self.power_x_edits, start=1):
            text = edit.text().strip()
            if not text:
                raise ValueError(_dual_msg(f"x{idx} 不能为空。", f"x{idx} must not be empty."))
            try:
                x_values.append(mp.mpf(text))
            except ValueError:
                raise ValueError(_dual_msg(f"x{idx} 需要填写数字。", f"x{idx} must be a number."))
        override_text = self.power_p_edit.text().strip()
        exponent_override = None
        if override_text:
            try:
                exponent_override = mp.mpf(override_text)
            except ValueError:
                raise ValueError(_dual_msg("自定义 p 必须为数字。", "Custom p must be a number."))
        seed_guesses = None
        if hasattr(self, "power_seed_guesses_edit"):
            raw = self.power_seed_guesses_edit.text().strip()
            if raw:
                tokens = [token for token in re.split(r"[,\s]+", raw) if token]
                if tokens:
                    seed_guesses = tokens
        return PowerLawConfig(
            x_values=tuple(x_values),
            precision=precision or 50,
            exponent_override=exponent_override,
            seed_guesses=seed_guesses,
        )

    def _segment_lengths_from_text(self, text: str, expected_rows: int) -> list[int]:
        if not text or not text.strip():
            return []
        lengths: list[int] = []
        header_seen = False
        current = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if header_seen and current > 0:
                    lengths.append(current)
                    current = 0
                continue
            if not header_seen:
                header_seen = True
                continue
            current += 1
        if header_seen and current > 0:
            lengths.append(current)
        total = sum(lengths)
        if expected_rows <= 0:
            return lengths
        if not lengths:
            return [expected_rows]
        if total == expected_rows:
            return lengths
        # 调整分段长度以匹配实际解析到的数据行数（可能有行被跳过）
        adjusted: list[int] = []
        used = 0
        for seg_len in lengths:
            if used >= expected_rows:
                break
            remaining = expected_rows - used
            clipped = min(max(seg_len, 0), remaining)
            if clipped > 0:
                adjusted.append(clipped)
                used += clipped
        if used < expected_rows:
            adjusted.append(expected_rows - used)
        return adjusted

    def _table_segments_from_lengths(self, total_rows: int, lengths: list[int]) -> list[tuple[int, int]]:
        if total_rows <= 0:
            return []
        segments: list[tuple[int, int]] = []
        start = 0
        for length in lengths:
            if length <= 0:
                continue
            end = start + length
            segments.append((start, min(end, total_rows)))
            start = end
        if not segments or segments[-1][1] != total_rows:
            if hasattr(self, "_append_log") and segments:
                self._append_log("Warning: segment boundaries do not cover all rows; using full range.")
            return [(0, total_rows)]
        normalized: list[tuple[int, int]] = []
        last_end = 0
        for segment_start, segment_end in segments:
            if segment_start != last_end:
                return [(0, total_rows)]
            normalized.append((segment_start, segment_end))
            last_end = segment_end
        return normalized

    def _build_batches_from_segments(
        self,
        headers: list[str],
        rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[object | None, ...]],
        segments: list[tuple[int, int]] | None,
    ) -> list[dict]:
        normalized = segments or [(0, len(rows))]
        batches: list[dict] = []
        for idx, (start, end) in enumerate(normalized, 1):
            start = max(0, start)
            end = min(len(rows), max(start, end))
            subset_rows = rows[start:end]
            if not subset_rows:
                continue
            subset_sigma = sigma_rows[start:end] if sigma_rows else []
            batches.append(
                {
                    "index": idx,
                    "headers": headers,
                    "rows": subset_rows,
                    "sigma_rows": subset_sigma,
                    "segment": (start, end),
                }
            )
        return batches

    def _refresh_uncertainty_selector(self, headers: list[str], rows: list[tuple[mp.mpf, ...]] | None = None):
        if not headers:
            return
        max_cols = len(headers)
        if rows:
            try:
                max_cols = max(max_cols, max(len(r) for r in rows))
            except Exception:
                pass
        full_headers = list(headers)
        if max_cols > len(full_headers):
            for idx in range(len(full_headers), max_cols):
                full_headers.append(f"col{idx + 1}")
        previous: object | None = None
        if hasattr(self, "uncertainty_combo") and self.uncertainty_combo.count() > 0:
            previous = self.uncertainty_combo.currentData()
            if previous is None:
                previous = self.uncertainty_combo.currentText().strip()
        self.uncertainty_combo.blockSignals(True)
        self.uncertainty_combo.clear()
        self.uncertainty_combo.addItem(
            self._tr(_REFCOL_AUTO_MAX_DIFF_ZH, _REFCOL_AUTO_MAX_DIFF_EN),
            _REFCOL_AUTO_MAX_DIFF_KEY,
        )
        self.uncertainty_combo.insertSeparator(1)
        for header in full_headers:
            self.uncertainty_combo.addItem(header, header)
        if previous:
            idx = self.uncertainty_combo.findData(previous)
            if idx < 0 and isinstance(previous, str) and previous.strip():
                idx = self.uncertainty_combo.findText(previous.strip())
            if idx >= 0:
                self.uncertainty_combo.setCurrentIndex(idx)
        self.uncertainty_combo.blockSignals(False)

    def _refresh_reference_auto_label(self):
        if not hasattr(self, "uncertainty_combo"):
            return
        combo = self.uncertainty_combo
        idx = combo.findData(_REFCOL_AUTO_MAX_DIFF_KEY)
        if idx < 0:
            return
        combo.setItemText(idx, self._tr(_REFCOL_AUTO_MAX_DIFF_ZH, _REFCOL_AUTO_MAX_DIFF_EN))

    def _refresh_uncertainty_from_source(self):
        """Reload uncertainty reference options from current data source."""
        data_path, manual_content = self._active_data_source()
        text = ""
        source_desc = ""
        if data_path and data_path.exists():
            try:
                text = _safe_read_text(data_path)
                source_desc = str(data_path)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, self._tr("读取失败", "Load failed"), str(exc))
                return
        elif manual_content:
            text = manual_content
            source_desc = self._tr("手动输入", "manual input")
        else:
            QMessageBox.information(
                self,
                self._tr("提示", "Notice"),
                self._tr("没有可用于刷新参考列的数据。", "No data available to refresh reference columns."),
            )
            return
        try:
            if self._statistics_grouped_workflow_active():
                parsed = parse_clipboard_tabular(text, has_headers=True)
                headers = parsed.headers
                rows: list[tuple[mp.mpf, ...]] = []
                if not headers:
                    raise ValueError(_dual_msg("表头至少需要一列。", "Header must contain at least one column."))
            else:
                headers, rows, _ = self._parse_generic_table(text)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                self._tr("刷新失败", "Refresh failed"),
                str(exc),
            )
            self._append_log(self._tr(f"刷新参考列失败: {exc}", f"Failed to refresh reference columns: {exc}"))
            return
        self._refresh_uncertainty_selector(headers, rows)
        note = self._tr("已刷新不确定度参考列。", "Uncertainty reference columns refreshed.")
        self._append_log(f"{note} {source_desc}".strip())

    def _statistics_grouped_workflow_active(self) -> bool:
        mode_combo = getattr(self, "mode_combo", None)
        workflow_combo = getattr(self, "stats_workflow_combo", None)
        if mode_combo is None or workflow_combo is None:
            return False
        try:
            mode = str(mode_combo.currentData() or "")
            workflow = str(workflow_combo.currentData() or "")
        except Exception:
            return False
        return mode == "statistics" and workflow == "grouped_statistics"

    def _parse_generic_table(
        self, text: str
    ) -> tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[object | None, ...]]]:
        """Parse whitespace separated table text into numeric rows with optional sigmas."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            raise ValueError(
                _dual_msg(
                    "输入内容需要至少包含表头和一行数据。",
                    "Input must include a header and at least one data row.",
                )
            )
        headers = lines[0].split()
        if len(headers) < 1:
            raise ValueError(_dual_msg("表头至少需要一列。", "Header must contain at least one column."))
        rows: list[tuple[mp.mpf, ...]] = []
        sigma_rows: list[tuple[object | None, ...]] = []
        for line_num, line in enumerate(lines[1:], 2):
            parts = line.split()
            if len(parts) != len(headers):
                raise ValueError(
                    _dual_msg(
                        f"第 {line_num} 行列数与表头不匹配（期望 {len(headers)} 列，实际 {len(parts)} 列）。",
                        f"Column count mismatch on line {line_num} (expected {len(headers)}, got {len(parts)}).",
                    )
                )
            values: list[mp.mpf] = []
            sigmas: list[object | None] = []
            lang = "en" if self._is_en() else "zh"
            for token in parts:
                try:
                    uncertain = parse_uncertainty_format(token, lang=lang)
                except (ValueError, TypeError, AttributeError) as exc:
                    raise ValueError(
                        _dual_msg(
                            f"第 {line_num} 行存在无法解析的数字: {token} ({exc})",
                            f"Cannot parse value on line {line_num}: {token} ({exc})",
                        )
                    ) from exc
                try:
                    values.append(mp.mpf(uncertain.value))
                    _ = mp.mpf(uncertain.uncertainty)
                except Exception as exc:
                    raise ValueError(
                        _dual_msg(
                            f"第 {line_num} 行包含无效数字: {exc}",
                            f"Invalid numeric value on line {line_num}: {exc}",
                        )
                    ) from exc
                # 保留原始不确定度位数信息，后续格式化使用；加权等计算再转为 mp.mpf
                sigmas.append(uncertain if has_explicit_uncertainty(token) else None)
            rows.append(tuple(values))
            sigma_rows.append(tuple(sigmas))
        return headers, rows, sigma_rows

    def _peek_user_precision(self) -> int:
        try:
            return int(self.mpmath_precision_spin.value()) if hasattr(self, "mpmath_precision_spin") else mp.mp.dps
        except Exception:
            return mp.mp.dps

    def _caption_value(self, require: bool = False) -> str | None:
        if hasattr(self, "caption_checkbox") and not self.caption_checkbox.isChecked():
            return None
        if not hasattr(self, "caption_edit"):
            return None
        text = self.caption_edit.text().strip()
        if require and hasattr(self, "caption_checkbox") and self.caption_checkbox.isChecked() and not text:
            raise ValueError(self._tr("已勾选标题但未填写。", "Caption is enabled but empty."))
        return text or None

    def _constants_editor_has_content(self, editor: Any | None) -> bool:
        if editor is None:
            return False
        if getattr(editor, "using_text_view", lambda: False)():
            return bool(str(getattr(editor, "raw_text", lambda: "")()).strip())
        for row in getattr(editor, "rows", lambda: [])():
            if not isinstance(row, dict):
                continue
            if str(row.get("name") or "").strip() or str(row.get("value") or "").strip():
                return True
        return False

    def _input_bundle_from_source(
        self,
        *,
        data_path: Path | None,
        manual_content: str,
        source_kind: str,
    ) -> InputBundle:
        source_text = ""
        if data_path and data_path.exists() and not data_path.is_dir():
            source_text = _safe_read_text(data_path)
        elif manual_content:
            source_text = manual_content
        sections = parse_input_sections(source_text)

        effective_data_path = data_path if data_path and not sections.explicit_sections else None
        data_text = sections.data_text.strip() if (manual_content or sections.explicit_sections) else ""

        editor = getattr(self, "input_constants_editor", None)
        numeric_mode = (
            str(editor.numeric_mode())
            if editor is not None and hasattr(editor, "numeric_mode")
            else "uncertainty"
        )
        if self._constants_editor_has_content(editor):
            view = "text" if editor.using_text_view() else "table"
            rows = tuple(dict(row) for row in editor.rows())
            text = editor.raw_text().strip() if view == "text" else editor.text().strip()
        else:
            text = sections.constants_text.strip()
            rows = tuple(parse_constants_text(text)) if text else ()
            view = "text" if text else "table"
        return InputBundle(
            data_path=effective_data_path,
            data_text=data_text,
            constants_text=text,
            constants_rows=rows,
            source_kind=source_kind,
            explicit_sections=sections.explicit_sections,
            constants_view=view,
            constants_numeric_mode=numeric_mode,
        )

    def _active_input_bundle(
        self,
        *,
        data_path: Path | None = None,
        manual_content: str | None = None,
        source_kind: str | None = None,
    ) -> InputBundle:
        # No checkbox any more: a non-empty data-file path takes PRECEDENCE over the manual input
        # (user request — fill the file field and the manual table/text below is ignored).
        _file_edit = getattr(self, "data_file_edit", None)
        _file_path_text = _file_edit.text().strip() if _file_edit is not None else ""
        use_file = bool(_file_path_text)
        if data_path is not None or manual_content is not None:
            return self._input_bundle_from_source(
                data_path=data_path,
                manual_content=manual_content or "",
                source_kind=source_kind or ("file" if data_path else "manual_text"),
            )

        active_data_path = None
        active_manual_content = ""
        active_source_kind = "manual_table"
        if use_file:
            active_data_path = _safe_resolve_path(_file_path_text)
            active_source_kind = "file"
        else:
            # Read from table view if active, otherwise from text view
            from app_desktop.panels import _serialize_table
            stack = getattr(self, "_data_stack", None)
            if stack is not None and stack.currentIndex() == 0:
                has_table_content = getattr(self, "_manual_table_has_content", None)
                if callable(has_table_content) and not has_table_content():
                    active_manual_content = ""
                else:
                    serialized = _serialize_table(self).strip()
                    active_manual_content = serialized if len(serialized.splitlines()) > 1 else ""
            else:
                active_manual_content = self.manual_data_edit.toPlainText().strip()
                active_source_kind = "manual_text"
        return self._input_bundle_from_source(
            data_path=active_data_path,
            manual_content=active_manual_content,
            source_kind=active_source_kind,
        )

    def _active_constants_source(
        self,
        *,
        data_path: Path | None = None,
        manual_content: str | None = None,
        source_kind: str | None = None,
    ) -> InputConstantsSource:
        bundle = self._active_input_bundle(
            data_path=data_path,
            manual_content=manual_content,
            source_kind=source_kind,
        )
        return InputConstantsSource(
            rows_value=bundle.constants_rows,
            text_value=bundle.constants_text,
            view_value=bundle.constants_view,
            numeric_mode_value=bundle.constants_numeric_mode,
        )

    def _active_data_source(self) -> tuple[Path | None, str]:
        bundle = self._active_input_bundle()
        return bundle.data_path, bundle.data_text

    def _collect_batched_fitting_dataset(
        self,
        precision_hint: int | None = None,
    ) -> tuple[
        list[str],
        list[tuple[mp.mpf, ...]],
        list[tuple[object | None, ...]],
        list[tuple[int, int]],
        str,
    ]:
        data_path, manual_content = self._active_data_source()
        source_text = ""
        if data_path:
            if not data_path.exists():
                raise ValueError(
                    _dual_msg(
                        "请选择有效的数据文件路径。",
                        "Please select a valid data file path.",
                    )
                )
            source_text = _safe_read_text(data_path)
        elif manual_content:
            source_text = manual_content
        else:
            raise ValueError(_dual_msg("没有可用于拟合的数据。", "No data available for fitting."))
        with _mp_precision_guard(precision_hint):
            headers, rows, sigma_rows = self._parse_generic_table(source_text)
        lengths = self._segment_lengths_from_text(source_text, len(rows))
        segments = self._table_segments_from_lengths(len(rows), lengths)
        return headers, rows, sigma_rows, segments, source_text

    def _collect_fitting_dataset(
        self,
        precision_hint: int | None = None,
    ) -> tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[object | None, ...]]]:
        headers, rows, sigma_rows, _, _ = self._collect_batched_fitting_dataset(precision_hint=precision_hint)
        return headers, rows, sigma_rows

    def _prepare_linear_fit_inputs(
        self,
        headers: list[str],
        data_rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[object | None, ...]],
    ) -> tuple[
        list[str],
        list[tuple[mp.mpf, ...]],
        list[tuple[object | None, ...]],
        list[mp.mpf],
        list[mp.mpf],
        list[mp.mpf | None],
        list[mp.mpf] | None,
    ]:
        target_column = self.fit_target_edit.text().strip()
        variable_map = self._collect_variable_mapping(headers)
        x_column = variable_map.get("x")
        if not x_column and variable_map:
            x_column = next(iter(variable_map.values()))
        if not target_column or not x_column:
            raise ValueError(
                _dual_msg(
                    "请指定模板拟合模型所需的列。",
                    "Please specify the columns required for template fitting models.",
                )
            )
        x_series = self._column_series(headers, data_rows, x_column)
        y_series = self._column_series(headers, data_rows, target_column)
        sigma_series = self._resolve_uncertainties(
            headers,
            data_rows,
            sigma_rows,
            target_column,
            None,
        )
        weights = None
        if self.fit_weighted_checkbox.isChecked():
            weights = self._build_weight_vector(sigma_series)
        return headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights

    # --------------------------------------------------------- Statistics --
    def _ordered_variable_pairs(self, headers: list[str]) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        seen_vars: set[str] = set()
        for var_edit, col_edit, *_ in getattr(self, "variable_rows", []):
            var = var_edit.text().strip()
            column = col_edit.text().strip()
            if not var or not column:
                continue
            if column not in headers:
                raise ValueError(self._tr(f"列 {column} 不存在。", f"Column {column} not found."))
            if var in seen_vars:
                raise ValueError(self._tr(f"变量名 {var} 重复。", f"Variable name {var} is duplicated."))
            seen_vars.add(var)
            pairs.append((var, column))
        if not pairs:
            raise ValueError(self._tr("请至少指定一个变量映射。", "Please specify at least one variable mapping."))
        return pairs

    def _collect_variable_mapping(self, headers: list[str]) -> dict[str, str]:
        pairs = self._ordered_variable_pairs(headers)
        return {var: col for var, col in pairs}

    def _column_series(
        self, headers: list[str], rows: list[tuple[mp.mpf, ...]], column: str
    ) -> list[mp.mpf]:
        if column not in headers:
            raise ValueError(_dual_msg(f"未找到列 {column}。", f"Column not found: {column}."))
        idx = headers.index(column)
        return [row[idx] for row in rows]

    def _inverse_power_range(self) -> tuple[int, int]:
        if not hasattr(self, "inverse_min_spin"):
            return 1, 3
        min_power = self.inverse_min_spin.value()
        max_power = self.inverse_max_spin.value()
        if min_power > max_power:
            min_power, max_power = max_power, min_power
        return min_power, max_power

    def _resolve_uncertainties(
        self,
        headers: list[str],
        rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[object | None, ...]],
        target_column: str,
        sigma_column: str | None = None,
        *,
        absolute: bool = True,
    ) -> list[mp.mpf | None]:
        return normalize_data_uncertainty(
            headers=headers,
            rows=rows,
            sigma_rows=sigma_rows,
            target_column=target_column,
            sigma_column=sigma_column,
            absolute=absolute,
        )

    def _build_weight_vector(self, sigma_values: list[mp.mpf | None]) -> list[mp.mpf]:
        state = fit_uncertainty_policy(sigma_values, weighted=True)
        if state.weights is None:
            raise ValueError(_dual_msg("未提供不确定度数据，无法执行加权拟合。", "No uncertainty data provided; cannot perform weighted fitting."))
        return list(state.weights)
