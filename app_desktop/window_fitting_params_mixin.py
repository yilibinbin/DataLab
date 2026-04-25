"""Phase 7 #19 split — parameter table editing concern.

Methods extracted VERBATIM from the original ``window_fitting_mixin.py``.
This mixin owns the dynamic parameter-row UI (name / initial value /
min / max bounds), the constraints-checkbox visibility logic, and
the helpers that turn the live row state into a ``{name: {initial, min, max}}``
config dict for the fitter.

Methods MOVED here from window_fitting_mixin.py (line numbers
refer to the pre-Phase-7 monolith and are frozen as one-time
migration context — they will NOT be kept in sync; see ``git log``
for canonical history):
- _next_param_name           (was line 52)
- _add_param_row             (was line 64)
- _remove_param_row          (was line 86)
- _on_constraints_toggle     (was line 99)
- _reset_param_rows          (was line 113)
- _extract_param_rows        (was line 125)
- _collect_parameter_config  (was line 151)

State variables READ/WRITTEN (must be initialised by parent or
sibling mixin):
- ``self.param_rows`` (list of ``(name, init, min, max, container)``
  tuples of QLineEdit + QWidget)
- ``self.param_rows_layout`` (QVBoxLayout)
- ``self.param_header_widget``, ``self.param_rows_container``
  (visibility wrappers)
- ``self.enable_constraints_checkbox`` (QCheckBox)
- ``self.fit_model_combo`` (QComboBox; only ``currentData`` accessed)
- ``self.add_param_btn``, ``self.remove_param_btn`` (QPushButton)

Methods provided by sibling mixins (resolved via Python MRO):
- ``self._tr(zh, en)`` — bilingual string helper (host class)
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class WindowFittingParamsMixin:
    def _next_param_name(self) -> str:
        existing = {row[0].text().strip() for row in getattr(self, "param_rows", []) if row[0].text().strip()}
        for candidate in ["A", "B", "C", "p", "k", "C0"]:
            if candidate not in existing:
                return candidate
        idx = 1
        while True:
            name = f"P{idx}"
            if name not in existing:
                return name
            idx += 1

    def _add_param_row(self, default_name: str | None = None, init: str = "", min_val: str = "", max_val: str = ""):
        if not hasattr(self, "param_rows_layout"):
            return
        name = default_name or self._next_param_name()
        row_layout = QHBoxLayout()
        name_edit = QLineEdit(name)
        init_edit = QLineEdit(init)
        min_edit = QLineEdit(min_val)
        max_edit = QLineEdit(max_val)
        lbl_name = QLabel(self._tr("名称", "Name"))
        lbl_init = QLabel(self._tr("初值", "Init"))
        lbl_min = QLabel(self._tr("下界", "Min"))
        lbl_max = QLabel(self._tr("上界", "Max"))
        for widget in (lbl_name, name_edit, lbl_init, init_edit, lbl_min, min_edit, lbl_max, max_edit):
            row_layout.addWidget(widget)
        container = QWidget()
        container.setLayout(row_layout)
        self.param_rows_layout.addWidget(container)
        if not hasattr(self, "param_rows"):
            self.param_rows = []
        self.param_rows.append((name_edit, init_edit, min_edit, max_edit, container))

    def _remove_param_row(self):
        if not hasattr(self, "param_rows") or not self.param_rows:
            return
        if hasattr(self, "enable_constraints_checkbox") and self.enable_constraints_checkbox.isChecked():
            if len(self.param_rows) <= 1:
                return
        _, _, _, _, container = self.param_rows.pop()
        try:
            container.setParent(None)
            container.deleteLater()
        except Exception:
            pass

    def _on_constraints_toggle(self, checked: bool):
        mode = self.fit_model_combo.currentData() if hasattr(self, "fit_model_combo") else None
        show_params = checked and mode != "auto"
        if show_params and (not getattr(self, "param_rows", None)):
            self._add_param_row()
        if hasattr(self, "param_header_widget"):
            self.param_header_widget.setVisible(show_params)
        if hasattr(self, "param_rows_container"):
            self.param_rows_container.setVisible(show_params)
        if hasattr(self, "add_param_btn"):
            self.add_param_btn.setVisible(show_params)
        if hasattr(self, "remove_param_btn"):
            self.remove_param_btn.setVisible(show_params)

    def _reset_param_rows(self):
        if not hasattr(self, "param_rows_layout"):
            return
        for _, _, _, _, container in getattr(self, "param_rows", []):
            try:
                container.setParent(None)
                container.deleteLater()
            except Exception:
                pass
        self.param_rows = []
        # start empty; user can add constraints as needed

    def _extract_param_rows(self) -> dict:
        config: dict[str, dict[str, float]] = {}
        for name_edit, init_edit, min_edit, max_edit, _ in getattr(self, "param_rows", []):
            name = name_edit.text().strip()
            init_text = init_edit.text().strip()
            if not name and not init_text:
                continue
            if not name:
                raise ValueError(self._tr("参数名称不能为空。", "Parameter name cannot be empty."))
            if not init_text:
                raise ValueError(self._tr(f"参数 {name} 需要初值。", f"Parameter {name} needs an initial value."))
            try:
                init_val = float(init_text)
            except ValueError as exc:
                raise ValueError(self._tr(f"参数 {name} 的初值无效。", f"Invalid initial value for parameter {name}.")) from exc
            entry: dict[str, float] = {"initial": init_val}
            for key, edit in (("min", min_edit), ("max", max_edit)):
                text = edit.text().strip()
                if text:
                    try:
                        entry[key] = float(text)
                    except ValueError as exc:
                        raise ValueError(self._tr(f"参数 {name} 的 {key} 无效。", f"Invalid {key} for parameter {name}."))
            # Stage 2 review fix: was indented inside the for-loop above,
            # causing the same dict to be re-assigned twice per parameter.
            # Now executes once after both bounds are read. Behaviour is
            # equivalent (same `entry` reference) but the code now matches
            # the obvious intent.
            config[name] = entry
        return config

    def _collect_parameter_config(self, allow_empty: bool = True) -> dict:
        if hasattr(self, "enable_constraints_checkbox") and not self.enable_constraints_checkbox.isChecked():
            return {}
        from_rows = self._extract_param_rows()
        if from_rows:
            return from_rows
        if allow_empty:
            return {}
        raise ValueError(self._tr("请在参数列表中添加参数。", "Please add at least one parameter."))

