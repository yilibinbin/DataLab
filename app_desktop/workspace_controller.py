from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from PySide6.QtWidgets import QComboBox, QTableWidget, QTableWidgetItem

from app_desktop.fitting_input_normalization import (
    normalize_constants_state,
    normalize_parameter_rows,
)
from app_desktop.workers_core import _READ_FALLBACK_ENCODINGS
from shared.update_checker import current_version
from shared.workspace_schema import compute_workspace_hash, sha256_bytes


@dataclass(frozen=True)
class WorkspaceBundle:
    manifest: dict[str, Any]
    attachments: dict[str, bytes]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _combo_data(combo: QComboBox | None, default: str = "") -> str:
    if combo is None:
        return default
    data = combo.currentData()
    return str(data if data is not None else combo.currentText())


def _normalize_fitting_model(value: Any) -> str:
    model = str(value or "custom")
    aliases = {
        "poly": "polynomial",
        "inverse": "inverse_power",
    }
    return aliases.get(model, model)


def _set_combo_data(combo: QComboBox | None, value: str) -> None:
    if combo is None:
        return
    idx = combo.findData(value)
    if idx < 0:
        idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)


def _text(obj: Any, default: str = "") -> str:
    if obj is None:
        return default
    if hasattr(obj, "toPlainText"):
        return str(obj.toPlainText())
    if hasattr(obj, "text"):
        return str(obj.text())
    return default


def _set_text(obj: Any, value: str) -> None:
    if obj is None:
        return
    if hasattr(obj, "setPlainText"):
        obj.setPlainText(value)
    elif hasattr(obj, "setText"):
        obj.setText(value)


def _checked(obj: Any, default: bool = False) -> bool:
    return bool(obj.isChecked()) if obj is not None and hasattr(obj, "isChecked") else default


def _value(obj: Any, default: Any = None) -> Any:
    return obj.value() if obj is not None and hasattr(obj, "value") else default


def _table_to_canonical(table: QTableWidget) -> dict[str, Any]:
    headers: list[str] = []
    for col in range(table.columnCount()):
        item = table.horizontalHeaderItem(col)
        headers.append(item.text() if item and item.text() else f"Column {col + 1}")
    rows: list[list[str]] = []
    for row in range(table.rowCount()):
        values: list[str] = []
        has_value = False
        for col in range(table.columnCount()):
            item = table.item(row, col)
            cell = item.text() if item else ""
            if cell:
                has_value = True
            values.append(cell)
        if has_value:
            rows.append(values)
    payload: dict[str, Any] = {"rows": rows}
    if headers:
        payload["headers"] = headers
    return payload


def _canonical_to_text(table: dict[str, Any]) -> str:
    lines: list[str] = []
    headers = table.get("headers")
    if isinstance(headers, list) and headers:
        lines.append("\t".join(str(value) for value in headers))
    for row in table.get("rows") or []:
        if isinstance(row, list):
            lines.append("\t".join(str(value) for value in row))
    return "\n".join(lines) + ("\n" if lines else "")


def _set_table_from_canonical(table: QTableWidget, canonical: dict[str, Any]) -> None:
    rows = [list(row) for row in canonical.get("rows") or [] if isinstance(row, list)]
    headers = [str(value) for value in canonical.get("headers") or []]
    row_count = max(len(rows), table.rowCount(), 1)
    col_count = max((len(row) for row in rows), default=0)
    col_count = max(col_count, len(headers), table.columnCount(), 1)
    table.setRowCount(row_count)
    table.setColumnCount(col_count)
    if headers:
        table.setHorizontalHeaderLabels(headers + [f"Column {idx + 1}" for idx in range(len(headers), col_count)])
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))


def _decode_bytes(raw: bytes) -> tuple[str, str]:
    for encoding in _READ_FALLBACK_ENCODINGS[:-1]:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    encoding = _READ_FALLBACK_ENCODINGS[-1]
    return raw.decode(encoding), encoding


def _newline_kind(text: str) -> str:
    if "\r\n" in text:
        return "crlf"
    if "\r" in text:
        return "cr"
    return "lf"


def _capture_data_section(window: Any, *, constants: bool = False) -> tuple[dict[str, Any], dict[str, bytes]]:
    attachments: dict[str, bytes] = {}
    table: QTableWidget | None
    text_edit: Any | None
    stack: Any | None
    if constants:
        editor = getattr(window, "error_constants_editor", None)
        enabled = _checked(editor)
        use_file = _checked(getattr(window, "use_constants_file_checkbox", None))
        path_text = _text(getattr(window, "constants_file_edit", None)).strip()
        table = None
        text_edit = None
        stack = None
        section_name = "constants"
    else:
        editor = None
        enabled = True
        use_file = _checked(getattr(window, "use_file_checkbox", None))
        path_text = _text(getattr(window, "data_file_edit", None)).strip()
        table = getattr(window, "manual_table", None)
        text_edit = getattr(window, "manual_data_edit", None)
        stack = getattr(window, "_data_stack", None)
        section_name = "input"

    raw_path = None
    source_path = path_text or None
    source_kind = "file" if use_file else ("manual_text" if stack is not None and stack.currentIndex() == 1 else "manual_table")
    if constants and editor is not None and not use_file:
        source_kind = "manual_text" if editor.using_text_view() else "manual_table"
    canonical: dict[str, Any]
    if use_file and path_text:
        raw = Path(path_text).read_bytes()
        decoded_text, encoding = _decode_bytes(raw)
        raw_path = f"attachments/sources/{section_name}.bin"
        attachments[raw_path] = raw
        canonical = {"rows": []}
    elif constants and editor is not None:
        rows = editor.rows()
        canonical = {"headers": ["Name", "Value"], "rows": [[row["name"], row["value"]] for row in rows]}
        decoded_text = editor.raw_text()
        encoding = "utf-8"
        raw = decoded_text.encode("utf-8")
    elif source_kind == "manual_text":
        decoded_text = _text(text_edit)
        encoding = "utf-8"
        canonical = {"rows": [line.split() for line in decoded_text.splitlines() if line.strip()]}
        raw = decoded_text.encode("utf-8")
    else:
        if table is None:
            canonical = {"rows": []}
            decoded_text = ""
            encoding = "utf-8"
            raw = b""
        else:
            canonical = _table_to_canonical(table)
            decoded_text = _canonical_to_text(canonical)
            encoding = "utf-8"
            raw = decoded_text.encode("utf-8")

    section = {
        "enabled": enabled,
        "source_kind": source_kind,
        "source_path": source_path,
        "source_path_label": source_path,
        "active_view": "text" if source_kind == "manual_text" else "table",
        "decoded_text": decoded_text,
        "numeric_mode": str(editor.numeric_mode())
        if constants and editor is not None and hasattr(editor, "numeric_mode")
        else "uncertainty",
        "encoding": encoding,
        "newline": _newline_kind(decoded_text),
        "original_bytes_sha256": sha256_bytes(raw),
        "raw_bytes_path": raw_path,
        "canonical_table": canonical,
        "sha256": sha256_bytes((decoded_text + repr(canonical)).encode("utf-8")),
    }
    return section, attachments


def _normalize_workspace_parameter_rows(raw_rows: Any) -> list[dict[str, str]]:
    if raw_rows is None:
        return []
    return cast(list[dict[str, str]], normalize_parameter_rows(
        raw_rows,
        constraints_enabled=True,
    ).persisted_rows())


def _normalize_workspace_constant_rows(raw_rows: Any) -> list[dict[str, str]]:
    if raw_rows is None:
        return []
    return cast(list[dict[str, str]], normalize_constants_state(
        enabled=True,
        rows=raw_rows,
        numeric_mode="uncertainty",
    ).persisted_rows())


def _param_rows(window: Any) -> list[dict[str, str]]:
    table = getattr(window, "custom_params_table", None)
    if table is not None and hasattr(table, "rows"):
        return _normalize_workspace_parameter_rows(table.rows())
    return []


def _param_orphans(window: Any) -> list[str]:
    table = getattr(window, "custom_params_table", None)
    if table is not None and hasattr(table, "orphan_names"):
        return sorted(str(name) for name in table.orphan_names())
    return []


def _implicit_param_rows(window: Any) -> list[dict[str, str]]:
    table = getattr(window, "implicit_params_table", None)
    if table is not None and hasattr(table, "rows"):
        return _normalize_workspace_parameter_rows(table.rows())
    return []


def _implicit_param_orphans(window: Any) -> list[str]:
    table = getattr(window, "implicit_params_table", None)
    if table is not None and hasattr(table, "orphan_names"):
        return sorted(str(name) for name in table.orphan_names())
    return []


def _constants_editor_state(editor: Any) -> dict[str, Any]:
    if editor is None:
        return {
            "enabled": False,
            "view": "table",
            "rows": [],
            "text": "",
            "numeric_mode": "uncertainty",
        }
    return {
        "enabled": _checked(editor),
        "view": "text" if editor.using_text_view() else "table",
        "rows": _normalize_workspace_constant_rows(editor.rows()),
        "text": str(editor.raw_text()),
        "numeric_mode": str(editor.numeric_mode()) if hasattr(editor, "numeric_mode") else "uncertainty",
    }


def _implicit_constants_rows(window: Any) -> list[dict[str, str]]:
    editor = getattr(window, "implicit_constants_editor", None)
    if editor is None:
        return []
    return _normalize_workspace_constant_rows(editor.rows())


def _variable_rows(window: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name, column, _widget in getattr(window, "variable_rows", []) or []:
        rows.append({"name": _text(name), "column": _text(column)})
    return rows


def _capture_implicit_config(window: Any, model: str) -> dict[str, Any]:
    equation = _text(getattr(window, "implicit_equation_edit", None))
    output_expression = _text(getattr(window, "implicit_output_edit", None))
    return {
        "schema": 2,
        "active": model == "self_consistent",
        "x_variables": tuple(
            str(row.get("name") or "")
            for row in _variable_rows(window)
            if str(row.get("name") or "").strip()
        ),
        "implicit_variable": _text(getattr(window, "implicit_variable_edit", None)),
        "equation": equation,
        "output_expression": output_expression,
        "method": _combo_data(getattr(window, "implicit_method_combo", None), "fixed_point"),
        "initial": _text(getattr(window, "implicit_initial_edit", None)),
        "tolerance": _text(getattr(window, "implicit_tolerance_edit", None)),
        "max_iterations": _value(getattr(window, "implicit_max_iterations_spin", None), 80),
        "timeout_seconds": _value(getattr(window, "implicit_timeout_spin", None), 300),
        "constraints_enabled": _checked(getattr(window, "implicit_constraints_checkbox", None)),
        "parameters": _implicit_param_rows(window),
        "parameter_orphans": _implicit_param_orphans(window),
        "constants": _implicit_constants_rows(window),
        "constants_enabled": _checked(getattr(window, "implicit_constants_editor", None)),
        "constants_view": "text"
        if getattr(window, "implicit_constants_editor", None) is not None
        and window.implicit_constants_editor.using_text_view()
        else "table",
        "constants_text": (
            window.implicit_constants_editor.raw_text()
            if getattr(window, "implicit_constants_editor", None) is not None
            else ""
        ),
        "constants_numeric_mode": (
            str(window.implicit_constants_editor.numeric_mode())
            if getattr(window, "implicit_constants_editor", None) is not None
            and hasattr(window.implicit_constants_editor, "numeric_mode")
            else "uncertainty"
        ),
    }


def _restore_variable_rows(window: Any, rows: Any) -> None:
    if not isinstance(rows, list) or not rows:
        return
    cleaned = [
        {
            "name": str(row.get("name") or ""),
            "column": str(row.get("column") or ""),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    if not cleaned:
        return
    if hasattr(window, "_reset_variable_rows"):
        first = cleaned[0]
        window._reset_variable_rows(default_var=first["name"] or "x", default_column=first["column"])
        for row in cleaned[1:]:
            if hasattr(window, "_add_variable_row"):
                window._add_variable_row(default_var=row["name"], default_column=row["column"])


def _restore_param_rows(window: Any, rows: Any, orphan_names: Any = None) -> None:
    if rows is None:
        return
    normalized_rows = _normalize_workspace_parameter_rows(rows)
    table = getattr(window, "custom_params_table", None)
    if table is not None and hasattr(table, "set_rows"):
        table.set_rows(normalized_rows)
        if isinstance(orphan_names, list) and hasattr(table, "mark_orphans"):
            active = [
                str(row.get("name") or "")
                for row in normalized_rows
                if str(row.get("name") or "") not in set(map(str, orphan_names))
            ]
            table.mark_orphans(active)


def _restore_constants_editor_state(editor: Any, state: Any) -> None:
    if editor is None or not isinstance(state, dict):
        return
    rows = state.get("rows")
    if rows is None:
        rows = state.get("constants")
    use_text_view = str(state.get("view") or "table") == "text"
    text = state.get("text")
    if "numeric_mode" in state and hasattr(editor, "set_numeric_mode"):
        editor.set_numeric_mode(str(state.get("numeric_mode") or "uncertainty"))
    editor.set_rows(rows)
    if text is not None:
        if hasattr(editor, "set_raw_text"):
            editor.set_raw_text(str(text))
        else:
            editor.set_text(str(text))
    editor.setChecked(bool(state.get("enabled")))
    editor.use_text_view(use_text_view)


def _clean_optional_string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _implicit_rows_to_config(rows: Any) -> dict[str, dict[str, str]]:
    if rows is None:
        return {}
    state = normalize_parameter_rows(rows, constraints_enabled=True)
    return cast(dict[str, dict[str, str]], state.compute_config(validate=False))


def _parameter_rows_have_constraints(rows: Any) -> bool:
    if rows is None:
        return False
    state = normalize_parameter_rows(rows, constraints_enabled=True)
    for row in state.persisted_rows():
        if any(_clean_optional_string(row.get(key)) for key in ("fixed", "min", "max")):
            return True
    return False


def _implicit_constants_to_rows(constants: Any) -> list[dict[str, str]]:
    if constants is None:
        return []
    return _normalize_workspace_constant_rows(constants)


def _is_legacy_quantum_defect_implicit(equation: str, output_expression: str) -> bool:
    return (
        equation.strip() == "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
        and output_expression.strip() == "En - R*c/(n-delta)^2"
    )


def _migrate_old_implicit_config(config: dict[str, Any], fitting: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(config)
    if migrated.get("schema") == 2:
        return migrated

    parameters = _implicit_rows_to_config(migrated.get("parameters"))
    if not parameters:
        parameters = _implicit_rows_to_config(migrated.get("parameter_rows"))
    if not parameters:
        parameters = _implicit_rows_to_config(fitting.get("parameter_rows"))
    if not parameters and isinstance(fitting.get("parameters"), list):
        parameters = _implicit_rows_to_config(fitting.get("parameters"))
    migrated["parameters"] = parameters

    constants = _implicit_constants_to_rows(migrated.get("constants"))
    equation = str(migrated.get("equation") or "")
    output_expression = str(migrated.get("output_expression") or "")
    if not constants and _is_legacy_quantum_defect_implicit(equation, output_expression):
        constants = [
            {"name": "R", "value": "10973731.568160"},
            {"name": "c", "value": "299792458"},
        ]
    migrated["constants"] = constants
    migrated.setdefault("timeout_seconds", 300)
    migrated["schema"] = 2
    return migrated


def _restore_implicit_config(window: Any, config: Any, fitting: dict[str, Any] | None = None) -> None:
    if not isinstance(config, dict) or not config:
        return
    had_constraints_flag = "constraints_enabled" in config
    config = _migrate_old_implicit_config(config, fitting or {})
    _set_text(getattr(window, "implicit_variable_edit", None), str(config.get("implicit_variable") or ""))
    _set_text(getattr(window, "implicit_equation_edit", None), str(config.get("equation") or ""))
    _set_text(getattr(window, "implicit_output_edit", None), str(config.get("output_expression") or ""))
    _set_text(getattr(window, "implicit_initial_edit", None), str(config.get("initial") or ""))
    _set_text(getattr(window, "implicit_tolerance_edit", None), str(config.get("tolerance") or ""))
    max_iterations = config.get("max_iterations")
    if max_iterations is not None and hasattr(window, "implicit_max_iterations_spin"):
        try:
            window.implicit_max_iterations_spin.setValue(int(max_iterations))
        except (TypeError, ValueError):
            pass
    timeout_seconds = config.get("timeout_seconds", 300)
    if hasattr(window, "implicit_timeout_spin"):
        try:
            window.implicit_timeout_spin.setValue(int(timeout_seconds))
        except (TypeError, ValueError):
            window.implicit_timeout_spin.setValue(300)
    method = str(config.get("method") or "")
    if method:
        _set_combo_data(getattr(window, "implicit_method_combo", None), method)
    raw_parameters = config.get("parameters")
    restore_parameters: Any = (
        raw_parameters
        if config.get("schema") == 2 and isinstance(raw_parameters, list)
        else _implicit_rows_to_config(raw_parameters)
    )
    constraints_enabled = (
        bool(config.get("constraints_enabled"))
        if had_constraints_flag
        else _parameter_rows_have_constraints(restore_parameters)
    )
    if hasattr(window, "implicit_constraints_checkbox"):
        window.implicit_constraints_checkbox.setChecked(constraints_enabled)
    if hasattr(window, "_reset_implicit_param_rows"):
        window._reset_implicit_param_rows(restore_parameters)
        table = getattr(window, "implicit_params_table", None)
        orphan_names = config.get("parameter_orphans")
        if isinstance(orphan_names, list) and table is not None and hasattr(table, "mark_orphans"):
            orphan_set = set(map(str, orphan_names))
            active = [
                str(row.get("name") or "")
                for row in table.rows()
                if isinstance(row, dict) and str(row.get("name") or "") not in orphan_set
            ]
            table.mark_orphans(active)
    constants = config.get("constants")
    editor = getattr(window, "implicit_constants_editor", None)
    if editor is not None:
        use_text_view = str(config.get("constants_view") or "table") == "text"
        if "constants_numeric_mode" in config and hasattr(editor, "set_numeric_mode"):
            editor.set_numeric_mode(str(config.get("constants_numeric_mode") or "uncertainty"))
        editor.set_rows(_implicit_constants_to_rows(constants))
        if "constants_text" in config:
            if hasattr(editor, "set_raw_text"):
                editor.set_raw_text(str(config.get("constants_text") or ""))
            else:
                editor.set_text(str(config.get("constants_text") or ""))
        editor.setChecked(bool(config.get("constants_enabled", bool(_implicit_constants_to_rows(constants)))))
        editor.use_text_view(use_text_view)
    elif hasattr(window, "_reset_implicit_constants_rows"):
        window._reset_implicit_constants_rows(_implicit_constants_to_rows(constants))


def _legacy_parameter_text_rows(parameter_text: Any) -> list[dict[str, str]]:
    if not isinstance(parameter_text, str) or not parameter_text.strip():
        return []
    try:
        payload = json.loads(parameter_text)
    except json.JSONDecodeError:
        return []
    return [
        {"name": name, **entry}
        for name, entry in _implicit_rows_to_config(payload).items()
    ]


def _capture_config(window: Any) -> dict[str, Any]:
    fitting_model = _normalize_fitting_model(_combo_data(getattr(window, "fit_model_combo", None), "custom"))
    if fitting_model == "auto":
        fitting_model = "custom"
    return {
        "common": {
            "mpmath_precision": _value(getattr(window, "mpmath_precision_spin", None), 16),
            "uncertainty_digits": _value(getattr(window, "uncertainty_digits_spin", None), 1),
            "generate_latex": _checked(getattr(window, "generate_latex_checkbox", None)),
            "generate_plots": _checked(getattr(window, "generate_plots_checkbox", None)),
            "verbose": _checked(getattr(window, "verbose_checkbox", None)),
            "display_scientific": _checked(getattr(window, "scientific_checkbox", None)),
            "display_digits": _value(getattr(window, "display_digits_spin", None), 10),
        },
        "latex": {
            "output_path": _text(getattr(window, "output_file_edit", None)),
            "input_digits": _value(getattr(window, "latex_input_precision_spin", None), 20),
            "use_dcolumn": _checked(getattr(window, "dcolumn_checkbox", None)),
            "group_size": _value(getattr(window, "latex_group_size_spin", None), 3),
            "use_caption": _checked(getattr(window, "caption_checkbox", None)),
            "caption": _text(getattr(window, "caption_edit", None)),
            "engine": _combo_data(getattr(window, "latex_engine_combo", None), "tectonic"),
        },
        "extrapolation": {
            "method": _combo_data(getattr(window, "method_combo", None), "richardson"),
            "custom_formula": _text(getattr(window, "custom_formula_edit", None)),
            "power_law": {
                "x_values": ",".join(_text(edit) for edit in getattr(window, "power_x_edits", []) or []),
                "custom_p": _text(getattr(window, "power_p_edit", None)),
                "seed_guesses": _text(getattr(window, "power_seed_guesses_edit", None)),
            },
            "levin": {
                "variant": _combo_data(getattr(window, "levin_variant_combo", None), "u"),
                "order": _value(getattr(window, "levin_order_spin", None), 2),
                "weight": _combo_data(getattr(window, "levin_weight_combo", None), "default"),
                "beta": str(_value(getattr(window, "levin_beta_spin", None), 1.0)),
            },
            "richardson": {"p": str(_value(getattr(window, "richardson_p_spin", None), 2.0))},
            "uncertainty_column": _combo_data(getattr(window, "uncertainty_combo", None), "A"),
        },
        "error": {
            "formula": _text(getattr(window, "formula_edit", None)),
            "method": _combo_data(getattr(window, "error_method_combo", None), "taylor"),
            "order": _value(getattr(window, "error_order_spin", None), 1),
            "mc_samples": _value(getattr(window, "error_mc_samples_spin", None), 5000),
            "mc_seed": _text(getattr(window, "error_mc_seed_edit", None)),
        },
        "statistics": {
            "value_column": _text(getattr(window, "stats_value_column_edit", None), "A"),
            "sigma_column": _text(getattr(window, "stats_sigma_column_edit", None)),
            "mode": _combo_data(getattr(window, "stats_mode_combo", None), "mean"),
            "sample": _checked(getattr(window, "stats_sample_checkbox", None)),
            "weighted_variance": _checked(getattr(window, "stats_weight_variance_checkbox", None)),
        },
        "fitting": {
            "model": fitting_model,
            "expression": _text(getattr(window, "fit_expr_edit", None)),
            "target_column": _text(getattr(window, "fit_target_edit", None), "B"),
            "weighted": _checked(getattr(window, "fit_weighted_checkbox", None)),
            "mcmc_refine": _checked(getattr(window, "fit_mcmc_refine", None)),
            "variables": _variable_rows(window),
            "constraints_enabled": _checked(getattr(window, "custom_constraints_checkbox", None)),
            "parameter_rows": _param_rows(window),
            "parameter_orphans": _param_orphans(window),
            "custom_constants": _constants_editor_state(getattr(window, "custom_constants_editor", None)),
            "implicit": _capture_implicit_config(window, fitting_model),
            "poly_degree": _value(getattr(window, "poly_degree_spin", None), 3),
            "inverse_power": {
                "min": _value(getattr(window, "inverse_min_spin", None), 1),
                "max": _value(getattr(window, "inverse_max_spin", None), 3),
            },
            "pade": {
                "m": _value(getattr(window, "pade_m_spin", None), 1),
                "n": _value(getattr(window, "pade_n_spin", None), 1),
            },
            "log_axes": {
                "x": _checked(getattr(window, "log_x_checkbox", None)),
                "y": _checked(getattr(window, "log_y_checkbox", None)),
            },
        },
    }


def _workspace_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    workspace = manifest.get("workspace")
    if isinstance(workspace, dict):
        return workspace
    return {
        "title": manifest.get("title") or "Untitled",
        "current_mode": manifest.get("current_mode") or "fitting",
        "ui": manifest.get("ui") or {},
        "data": (manifest.get("data") or {}).get("input") or manifest.get("data") or {},
        "constants": (manifest.get("data") or {}).get("constants") or manifest.get("constants") or {},
        "config": manifest.get("config") or {},
        "result_snapshot": manifest.get("result_snapshot") or {"present": False},
    }


def _degrade_obsolete_auto_fit_config(window: Any, fitting: dict[str, Any]) -> bool:
    has_obsolete_auto = fitting.get("model") == "auto" or "auto_fit" in fitting
    if not has_obsolete_auto:
        return False

    fitting.pop("auto_fit", None)
    if fitting.get("model") == "auto":
        fitting["model"] = "custom"

    warnings = list(getattr(window, "_workspace_migration_warnings", []) or [])
    warnings.append(
        "Automatic fitting is no longer supported; obsolete automatic fitting "
        "workspace settings were ignored."
    )
    window._workspace_migration_warnings = warnings
    return True


def _capture_ui(window: Any) -> dict[str, Any]:
    cursor = window.latex_edit.textCursor() if hasattr(window, "latex_edit") else None
    tabs = getattr(window, "tabs", None)
    result_tabs = getattr(window, "result_tabs", None)
    return {
        "main_tab": tabs.currentIndex() if tabs is not None else 0,
        "result_subtab": result_tabs.currentIndex() if result_tabs is not None else 0,
        "selected_plot_index": max(0, _value(getattr(window, "image_page_spin", None), 1) - 1),
        "plot_zoom": getattr(window, "result_plot_zoom", 1.0),
        "latex_editor": {
            "line_wrap": True,
            "cursor_line": cursor.blockNumber() + 1 if cursor is not None else 1,
            "cursor_column": cursor.positionInBlock() + 1 if cursor is not None else 1,
        },
    }


def _capture_result_snapshot(window: Any, workspace_hash: str, attachments: dict[str, bytes]) -> dict[str, Any]:
    rendered_text = _text(getattr(window, "result_edit", None))
    markdown = getattr(window, "_last_result_text", None)
    markdown_format = str(getattr(window, "_last_result_text_format", "") or "")
    cached_rendered = getattr(window, "_last_result_rendered_text", None)
    if not isinstance(markdown, str) or not markdown or cached_rendered != rendered_text:
        markdown = rendered_text
        markdown_format = "plain"
    log_text = _text(getattr(window, "log_edit", None))
    csv_rows = list(getattr(window, "_csv_rows", []) or [])
    csv_headers = list(getattr(window, "_csv_headers", []) or [])
    latex_source = _text(getattr(window, "latex_edit", None))
    plot_bytes = getattr(window, "result_plot_bytes", None)
    present = bool(markdown or log_text or csv_rows or latex_source or plot_bytes)
    if not present:
        return {"present": False}
    plots = []
    if isinstance(plot_bytes, bytes) and plot_bytes:
        plot_path = "attachments/plots/plot-001.png"
        attachments[plot_path] = plot_bytes
        plots.append(
            {
                "path": plot_path,
                "role": "primary",
                "order": 0,
                "title": "Result plot",
                "format": "png",
                "sha256": sha256_bytes(plot_bytes),
            }
        )
    return {
        "present": True,
        "kind": getattr(window, "_last_result_kind", None) or "snapshot",
        "result_of_hash": workspace_hash,
        "snapshot_only": True,
        "stale": False,
        "markdown": markdown,
        "markdown_format": markdown_format,
        "log": log_text,
        "csv": {"headers": csv_headers, "rows": csv_rows},
        "latex_source": latex_source,
        "plots": plots,
    }


def capture_workspace(window: Any, *, title: str = "Untitled") -> WorkspaceBundle:
    data, data_attachments = _capture_data_section(window, constants=False)
    constants, constants_attachments = _capture_data_section(window, constants=True)
    workspace = {
        "title": title,
        "current_mode": _combo_data(getattr(window, "mode_combo", None), "fitting"),
        "language": "auto",
        "ui": _capture_ui(window),
        "data": data,
        "constants": constants,
        "config": _capture_config(window),
        "result_snapshot": {"present": False},
    }
    attachments = {**data_attachments, **constants_attachments}
    workspace_hash = compute_workspace_hash(workspace)
    workspace["result_snapshot"] = _capture_result_snapshot(window, workspace_hash, attachments)
    now = _utc_now()
    return WorkspaceBundle(
        manifest={
            "schema": "datalab.workspace.v1",
            "schema_version": 1,
            "app": {"name": "DataLab", "version": current_version()},
            "created_at": now,
            "updated_at": now,
            "config": workspace["config"],
            "workspace": workspace,
        },
        attachments=attachments,
    )


def _restore_data_section(window: Any, section: dict[str, Any], *, constants: bool = False) -> None:
    if constants:
        editor = getattr(window, "error_constants_editor", None)
        if editor is not None:
            editor.setChecked(bool(section.get("enabled")))
        use_file_checkbox = getattr(window, "use_constants_file_checkbox", None)
        file_edit = getattr(window, "constants_file_edit", None)
        table = None
        text_edit = None
        stack = None
    else:
        editor = None
        use_file_checkbox = getattr(window, "use_file_checkbox", None)
        file_edit = getattr(window, "data_file_edit", None)
        table = getattr(window, "manual_table", None)
        text_edit = getattr(window, "manual_data_edit", None)
        stack = getattr(window, "_data_stack", None)
    source_kind = section.get("source_kind")
    if use_file_checkbox is not None:
        use_file_checkbox.setChecked(False)
    if file_edit is not None:
        file_edit.setText(str(section.get("source_path_label") or ""))
    if stack is not None:
        stack.setCurrentIndex(1 if source_kind == "manual_text" else 0)
    canonical = section.get("canonical_table") or {}
    if constants and editor is not None:
        rows = []
        if isinstance(canonical, dict):
            for row in canonical.get("rows") or []:
                if isinstance(row, list) and len(row) >= 2:
                    rows.append({"name": str(row[0]), "value": str(row[1])})
        if "numeric_mode" in section and hasattr(editor, "set_numeric_mode"):
            editor.set_numeric_mode(str(section.get("numeric_mode") or "uncertainty"))
        editor.set_rows(rows)
        if hasattr(editor, "set_raw_text"):
            editor.set_raw_text(str(section.get("decoded_text") or ""))
        else:
            editor.set_text(str(section.get("decoded_text") or ""))
        editor.use_text_view(source_kind == "manual_text")
        return
    if table is not None and isinstance(canonical, dict):
        _set_table_from_canonical(table, canonical)
    if text_edit is not None:
        text_edit.setPlainText(str(section.get("decoded_text") or _canonical_to_text(canonical)))


def restore_workspace(window: Any, manifest: dict[str, Any], attachments: dict[str, bytes]) -> None:
    workspace = _workspace_from_manifest(manifest)
    _set_combo_data(getattr(window, "mode_combo", None), str(workspace.get("current_mode") or "fitting"))
    _restore_data_section(window, workspace.get("data") or {}, constants=False)
    _restore_data_section(window, workspace.get("constants") or {}, constants=True)

    config = workspace.get("config") or {}
    fitting = config.get("fitting") or {}
    degraded = _degrade_obsolete_auto_fit_config(window, fitting)
    fitting["model"] = _normalize_fitting_model(fitting.get("model") or "custom")
    _set_combo_data(getattr(window, "fit_model_combo", None), str(fitting["model"]))
    if hasattr(window, "fit_expr_edit"):
        window.fit_expr_edit.setPlainText(str(fitting.get("expression") or ""))
    if hasattr(window, "fit_target_edit"):
        window.fit_target_edit.setText(str(fitting.get("target_column") or ""))
    _restore_variable_rows(window, fitting.get("variables"))
    parameter_rows = fitting.get("parameter_rows") or _legacy_parameter_text_rows(fitting.get("parameters"))
    if not parameter_rows and isinstance(fitting.get("parameters"), list):
        parameter_rows = fitting.get("parameters")
    if hasattr(window, "custom_constraints_checkbox"):
        custom_had_constraints_flag = "constraints_enabled" in fitting
        custom_constraints_enabled = (
            bool(fitting.get("constraints_enabled"))
            if custom_had_constraints_flag
            else _parameter_rows_have_constraints(parameter_rows)
        )
        window.custom_constraints_checkbox.setChecked(custom_constraints_enabled)
    _restore_param_rows(window, parameter_rows, fitting.get("parameter_orphans"))
    _restore_constants_editor_state(getattr(window, "custom_constants_editor", None), fitting.get("custom_constants"))
    _restore_implicit_config(window, fitting.get("implicit"), fitting)

    snapshot = workspace.get("result_snapshot") or {"present": False}
    if snapshot.get("present"):
        result_text = str(snapshot.get("markdown") or "")
        if snapshot.get("markdown_format") == "markdown" and hasattr(window, "_set_result_text"):
            window._set_result_text(result_text)
        else:
            window.result_edit.setPlainText(result_text)
            window._last_result_text = result_text
            window._last_result_text_format = "plain"
            window._last_result_rendered_text = window.result_edit.toPlainText()
        window.log_edit.setPlainText(str(snapshot.get("log") or ""))
        csv_payload = snapshot.get("csv") or {}
        window._set_csv_data(list(csv_payload.get("rows") or []), list(csv_payload.get("headers") or []))
        window.latex_edit.setPlainText(str(snapshot.get("latex_source") or ""))
        plots = snapshot.get("plots") or []
        if plots:
            first_path = plots[0].get("path")
            if first_path in attachments:
                window._update_result_plot(attachments[first_path])
    else:
        window.result_edit.clear()
        window.log_edit.clear()
        window.latex_edit.clear()
        window._reset_csv_data()
        window._last_result_text = ""
        window._last_result_text_format = "plain"
        window._last_result_rendered_text = ""
    window._last_result_kind = None
    window._last_result_payloads = {}
    window._workspace_snapshot_only = bool(snapshot.get("present"))
    window._workspace_dirty = False
    window._workspace_degraded = degraded
    if hasattr(window, "_set_snapshot_controls_enabled"):
        window._set_snapshot_controls_enabled(not window._workspace_snapshot_only)
