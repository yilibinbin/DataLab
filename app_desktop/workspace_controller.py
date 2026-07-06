from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
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
from datalab_core.fitting_comparison import (
    build_fitting_comparison_result_snapshot,
    render_fitting_comparison_snapshot_outputs,
)
from datalab_core.history import (
    HistoryEntry,
    HistoryPruneError,
    HistoryPruneReport,
    HistoryStore,
    HistoryValidationError,
    history_store_from_json,
)
from datalab_core.recipe_provenance import normalize_workspace_provenance
from datalab_core.root_solving import (
    build_root_result_snapshot,
    render_root_snapshot_outputs,
)
from datalab_core.statistics import (
    build_statistics_result_snapshot,
    render_statistics_snapshot_outputs,
)
from datalab_core.uncertainty import (
    build_uncertainty_result_snapshot,
    render_uncertainty_snapshot_outputs,
)
from datalab_core.workbench_model import WorkbenchModel
from shared.update_checker import current_version
from shared.workspace_schema import MAX_MANIFEST_BYTES, canonical_json, sha256_bytes


_DURABLE_RESULT_OVERVIEW_STATES = {"complete", "failed"}
_SEMANTIC_SNAPSHOT_KIND_BY_FAMILY = {
    "statistics": {
        "statistics_single",
        "statistics_batches",
        "statistics_matrix",
        "statistics_bootstrap",
        "statistics_hypothesis_test",
        "statistics_time_series",
        "statistics_grouped",
    },
    "fitting_comparison": {"fitting_comparison"},
    "root_solving": {"root_solving"},
    "uncertainty": {"error"},
}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def _normalize_root_mode(value: Any) -> str:
    mode = str(value or "scalar")
    if mode == "auto":
        return "scalar"
    return mode


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


def _set_checked_if(window: Any, attr: str, value: Any) -> None:
    widget = getattr(window, attr, None)
    if widget is not None and value is not None and hasattr(widget, "setChecked"):
        widget.setChecked(bool(value))


def _set_value(obj: Any, value: Any) -> None:
    if obj is None or value is None or not hasattr(obj, "setValue"):
        return
    try:
        obj.setValue(value)
    except (TypeError, ValueError):
        try:
            obj.setValue(type(obj.value())(value))
        except (AttributeError, TypeError, ValueError):
            pass


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
    row_count = max(len(rows), 1)
    col_count = max((len(row) for row in rows), default=0)
    col_count = max(col_count, len(headers), 1)
    from shared.parsing import _synthetic_headers

    synthetic_headers = _synthetic_headers(col_count)
    labels = [headers[idx] if idx < len(headers) else synthetic_headers[idx] for idx in range(col_count)]
    previous_blocked = table.blockSignals(True)
    try:
        table.clear()
        table.setRowCount(row_count)
        table.setColumnCount(col_count)
        table.setHorizontalHeaderLabels(labels)
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row[:col_count]):
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
    finally:
        table.blockSignals(previous_blocked)


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


def _root_unknown_rows(window: Any) -> list[dict[str, str]]:
    table = getattr(window, "root_unknowns_table", None)
    if table is None or not hasattr(table, "rows"):
        return []
    rows: list[dict[str, str]] = []
    for row in table.rows():
        if not isinstance(row, dict):
            continue
        clean = {
            "name": str(row.get("name") or ""),
            "initial": str(row.get("initial") or ""),
            "lower": str(row.get("lower") or ""),
            "upper": str(row.get("upper") or ""),
        }
        source = str(row.get("source") or "").strip()
        if source:
            clean["source"] = source
        if any(value for key, value in clean.items() if key != "source"):
            rows.append(clean)
    return rows


def _capture_display_units_config(window: Any, collect_attr: str, fallback_attr: str) -> Mapping[str, Any] | None:
    collect_units = getattr(window, collect_attr, None)
    units = collect_units() if callable(collect_units) else getattr(window, fallback_attr, None)
    return units if isinstance(units, Mapping) else None


def _capture_units_mapping(window: Any, collect_attr: str, fallback_attr: str) -> dict[str, Any]:
    units = _capture_display_units_config(window, collect_attr, fallback_attr)
    return {"units": units} if isinstance(units, Mapping) else {}


def _capture_root_config(window: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "schema": 1,
        "equations": _text(getattr(window, "root_equations_edit", None)),
        "mode": _combo_data(getattr(window, "root_mode_combo", None), "scalar"),
        "unknowns": _root_unknown_rows(window),
        "constants": _constants_editor_state(getattr(window, "root_constants_editor", None)),
        "uncertainty_options": {
            "method": _combo_data(getattr(window, "root_uncertainty_method_combo", None), "taylor"),
            "taylor_order": _value(getattr(window, "root_uncertainty_order_spin", None), 1),
            "monte_carlo_samples": _value(getattr(window, "root_monte_carlo_samples_spin", None), 2000),
            "monte_carlo_seed": _text(getattr(window, "root_monte_carlo_seed_edit", None), ""),
        },
    }
    units = _capture_display_units_config(window, "_collect_root_units_config", "root_units_config")
    if isinstance(units, Mapping):
        config["units"] = units
    return config


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
    if editor is None:
        return
    if not isinstance(state, dict):
        editor.set_rows([])
        if hasattr(editor, "set_raw_text"):
            editor.set_raw_text("")
        else:
            editor.set_text("")
        editor.setChecked(False)
        if hasattr(editor, "use_text_view"):
            editor.use_text_view(False)
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


def _constants_section_has_content(section: Any) -> bool:
    if not isinstance(section, dict):
        return False
    if str(section.get("source_path") or "").strip():
        return True
    if str(section.get("decoded_text") or "").strip():
        return True
    canonical = section.get("canonical_table")
    if isinstance(canonical, dict):
        for row in canonical.get("rows") or []:
            if isinstance(row, list) and any(str(cell or "").strip() for cell in row):
                return True
    return False


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


def _restore_implicit_config(
    window: Any,
    config: Any,
    fitting: dict[str, Any] | None = None,
    *,
    restore_constants: bool = True,
) -> None:
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
    if restore_constants and editor is not None:
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
    elif restore_constants and hasattr(window, "_reset_implicit_constants_rows"):
        window._reset_implicit_constants_rows(_implicit_constants_to_rows(constants))


def _restore_root_config(window: Any, config: Any, *, restore_constants: bool = True) -> None:
    if not isinstance(config, dict):
        setattr(window, "root_units_config", None)
        _restore_display_units_controls(window, "root", None, include_constants=True)
        _set_text(getattr(window, "root_equations_edit", None), "")
        _set_combo_data(getattr(window, "root_mode_combo", None), "scalar")
        table = getattr(window, "root_unknowns_table", None)
        if table is not None and hasattr(table, "set_rows"):
            table.set_rows([])
        if restore_constants:
            _restore_constants_editor_state(getattr(window, "root_constants_editor", None), None)
        _restore_root_uncertainty_options(window, None)
        return
    _set_text(getattr(window, "root_equations_edit", None), str(config.get("equations") or ""))
    _set_combo_data(getattr(window, "root_mode_combo", None), _normalize_root_mode(config.get("mode")))
    table = getattr(window, "root_unknowns_table", None)
    if table is not None and hasattr(table, "set_rows"):
        rows = config.get("unknowns")
        if isinstance(rows, list):
            clean_rows = [
                {
                    "name": str(row.get("name") or ""),
                    "initial": str(row.get("initial") or ""),
                    "lower": str(row.get("lower") or ""),
                    "upper": str(row.get("upper") or ""),
                    **({"source": str(row.get("source"))} if str(row.get("source") or "").strip() else {}),
                }
                for row in rows
                if isinstance(row, dict)
            ]
            table.set_rows(clean_rows)
    if restore_constants:
        _restore_constants_editor_state(getattr(window, "root_constants_editor", None), config.get("constants"))
    _restore_root_uncertainty_options(window, config.get("uncertainty_options"))
    units = config.get("units")
    setattr(window, "root_units_config", units if isinstance(units, Mapping) else None)
    _restore_display_units_controls(window, "root", units, include_constants=True)


def _set_checked_if(window: Any, attr: str, value: Any) -> None:
    widget = getattr(window, attr, None)
    if widget is not None and value is not None and hasattr(widget, "setChecked"):
        widget.setChecked(bool(value))


def _restore_common_config(window: Any, common: Any, latex: Any) -> None:
    """Restore the mode-independent common + latex settings. These are captured
    at save (config.common / config.latex) but were never read back, silently
    resetting compute-affecting precision and display options to defaults on
    reload (audit F11). mpmath_precision in particular changes the numerical
    result, so it must survive a round-trip."""
    if isinstance(common, dict):
        _set_value(getattr(window, "mpmath_precision_spin", None), common.get("mpmath_precision"))
        _set_value(getattr(window, "uncertainty_digits_spin", None), common.get("uncertainty_digits"))
        _set_value(getattr(window, "display_digits_spin", None), common.get("display_digits"))
        # generate_latex_checkbox was removed (4·4d); an old workspace's "generate_latex"
        # key in common config is simply ignored on restore.
        _set_checked_if(window, "generate_plots_checkbox", common.get("generate_plots"))
        _set_checked_if(window, "verbose_checkbox", common.get("verbose"))
        _set_checked_if(window, "scientific_checkbox", common.get("display_scientific"))
    if isinstance(latex, dict):
        _set_value(getattr(window, "latex_input_precision_spin", None), latex.get("input_digits"))
        _set_value(getattr(window, "latex_group_size_spin", None), latex.get("group_size"))
        _set_checked_if(window, "dcolumn_checkbox", latex.get("use_dcolumn"))
        _set_checked_if(window, "caption_checkbox", latex.get("use_caption"))
        _set_text(getattr(window, "output_file_edit", None), str(latex.get("output_path") or ""))
        _set_text(getattr(window, "caption_edit", None), str(latex.get("caption") or ""))
        # engine is now an engine MODE (auto/bundled/local). An old workspace that stored a
        # binary name (pdflatex/xelatex/tectonic) simply won't match a mode item and the
        # combo stays at its default (auto) — safe graceful degradation.
        _set_combo_data(getattr(window, "latex_engine_combo", None), str(latex.get("engine") or "auto"))


def _restore_extrapolation_config(window: Any, config: Any) -> None:
    if not isinstance(config, dict):
        return
    method = str(config.get("method") or "")
    if method:
        _set_combo_data(getattr(window, "method_combo", None), method)
    _set_text(getattr(window, "custom_formula_edit", None), str(config.get("custom_formula") or ""))
    power_law = config.get("power_law") or {}
    if isinstance(power_law, dict):
        x_values = str(power_law.get("x_values") or "").split(",")
        for edit, value in zip(getattr(window, "power_x_edits", []) or [], x_values):
            _set_text(edit, value.strip())
        _set_text(getattr(window, "power_p_edit", None), str(power_law.get("custom_p") or ""))
        _set_text(getattr(window, "power_seed_guesses_edit", None), str(power_law.get("seed_guesses") or ""))
    levin = config.get("levin") or {}
    if isinstance(levin, dict):
        _set_combo_data(getattr(window, "levin_variant_combo", None), str(levin.get("variant") or "u"))
    uncertainty_column = str(config.get("uncertainty_column") or "")
    if uncertainty_column:
        _set_combo_data(getattr(window, "uncertainty_combo", None), uncertainty_column)


def _restore_error_config(window: Any, config: Any) -> None:
    if not isinstance(config, dict):
        setattr(window, "error_units_config", None)
        _restore_error_units_controls(window, None)
        return
    _set_text(getattr(window, "formula_edit", None), str(config.get("formula") or ""))
    _set_combo_data(getattr(window, "error_method_combo", None), str(config.get("method") or "taylor"))
    _set_value(getattr(window, "error_order_spin", None), config.get("order"))
    _set_value(getattr(window, "error_mc_samples_spin", None), config.get("mc_samples"))
    _set_text(getattr(window, "error_mc_seed_edit", None), str(config.get("mc_seed") or ""))
    units = config.get("units")
    setattr(window, "error_units_config", units if isinstance(units, Mapping) else None)
    _restore_error_units_controls(window, units)


def _restore_error_units_controls(window: Any, units: Any) -> None:
    checkbox = getattr(window, "error_units_enabled_checkbox", None)
    if checkbox is None:
        return
    units_map = units if isinstance(units, Mapping) else {}
    checkbox.setChecked(bool(units_map.get("enabled")))
    _set_combo_data(getattr(window, "error_units_mode_combo", None), str(units_map.get("mode") or "display_only"))
    _restore_unit_editor_rows(getattr(window, "error_units_inputs_editor", None), units_map.get("inputs"))
    _restore_unit_editor_rows(getattr(window, "error_units_constants_editor", None), units_map.get("constants"))
    outputs = units_map.get("outputs")
    result_unit = ""
    if isinstance(outputs, Mapping):
        result_annotation = outputs.get("result")
        if isinstance(result_annotation, Mapping):
            result_unit = str(result_annotation.get("unit") or "")
        elif isinstance(result_annotation, str):
            result_unit = result_annotation
    _set_text(getattr(window, "error_units_output_edit", None), result_unit)
    update_controls = getattr(window, "_update_error_units_controls", None)
    if callable(update_controls):
        update_controls()


def _restore_display_units_controls(
    window: Any,
    attr_prefix: str,
    units: Any,
    *,
    include_constants: bool = False,
    include_parameters: bool = False,
) -> None:
    checkbox = getattr(window, f"{attr_prefix}_units_enabled_checkbox", None)
    if checkbox is None:
        return
    units_map = units if isinstance(units, Mapping) else {}
    checkbox.setChecked(bool(units_map.get("enabled")))
    _restore_unit_editor_rows(getattr(window, f"{attr_prefix}_units_inputs_editor", None), units_map.get("inputs"))
    if include_constants:
        _restore_unit_editor_rows(
            getattr(window, f"{attr_prefix}_units_constants_editor", None),
            units_map.get("constants"),
        )
    if include_parameters:
        _restore_unit_editor_rows(
            getattr(window, f"{attr_prefix}_units_parameters_editor", None),
            units_map.get("parameters"),
        )
    outputs = units_map.get("outputs")
    result_unit = ""
    if isinstance(outputs, Mapping):
        result_annotation = outputs.get("result")
        if isinstance(result_annotation, Mapping):
            result_unit = str(result_annotation.get("unit") or "")
        elif isinstance(result_annotation, str):
            result_unit = result_annotation
    _set_text(getattr(window, f"{attr_prefix}_units_output_edit", None), result_unit)
    update_controls = getattr(window, f"_update_{attr_prefix}_units_controls", None)
    if callable(update_controls):
        update_controls()


def _restore_unit_editor_rows(editor: Any, raw_units: Any) -> None:
    if editor is None:
        return
    rows: list[dict[str, str]] = []
    if isinstance(raw_units, Mapping):
        for name, annotation in raw_units.items():
            if isinstance(annotation, Mapping):
                unit = str(annotation.get("unit") or "")
            else:
                unit = str(annotation or "")
            rows.append({"name": str(name), "value": unit})
    editor.set_rows(rows)


def _restore_statistics_config(window: Any, config: Any) -> None:
    if not isinstance(config, dict):
        setattr(window, "stats_units_config", None)
        _restore_display_units_controls(window, "stats", None)
        return
    _set_combo_data(getattr(window, "stats_workflow_combo", None), str(config.get("workflow_mode") or "standard"))
    raw_value_columns = config.get("value_columns")
    if isinstance(raw_value_columns, list):
        value_columns = ", ".join(str(column) for column in raw_value_columns if str(column).strip())
    else:
        value_columns = str(raw_value_columns or config.get("value_column") or "A")
    _set_text(getattr(window, "stats_value_column_edit", None), value_columns)
    group_column = config.get("group_column")
    grouped = config.get("grouped")
    if group_column is None and isinstance(grouped, dict):
        group_column = grouped.get("group_column")
    _set_text(getattr(window, "stats_group_column_edit", None), str(group_column or ""))
    _set_text(getattr(window, "stats_sigma_column_edit", None), str(config.get("sigma_column") or ""))
    _set_text(getattr(window, "stats_trim_fraction_edit", None), str(config.get("trim_fraction") or ""))
    _set_combo_data(getattr(window, "stats_mode_combo", None), str(config.get("mode") or "mean"))
    checkbox = getattr(window, "stats_sample_checkbox", None)
    if checkbox is not None and hasattr(checkbox, "setChecked"):
        checkbox.setChecked(bool(config.get("sample")))
    checkbox = getattr(window, "stats_weight_variance_checkbox", None)
    if checkbox is not None and hasattr(checkbox, "setChecked"):
        checkbox.setChecked(bool(config.get("weighted_variance")))
    matrix = config.get("matrix")
    matrix_config = matrix if isinstance(matrix, dict) else {}
    _set_combo_data(
        getattr(window, "stats_matrix_missing_policy_combo", None),
        str(matrix_config.get("missing_policy") or config.get("matrix_missing_policy") or "listwise"),
    )
    bootstrap = config.get("bootstrap")
    bootstrap_config = bootstrap if isinstance(bootstrap, dict) else {}
    _set_combo_data(
        getattr(window, "stats_bootstrap_target_combo", None),
        str(bootstrap_config.get("target_statistic") or "mean"),
    )
    _set_text(
        getattr(window, "stats_bootstrap_confidence_edit", None),
        str(bootstrap_config.get("confidence_level") or "0.95"),
    )
    _set_value(getattr(window, "stats_bootstrap_resamples_spin", None), bootstrap_config.get("resample_count", 2000))
    seed_value = bootstrap_config.get("seed", "")
    _set_text(getattr(window, "stats_bootstrap_seed_edit", None), "" if seed_value is None else str(seed_value))
    hypothesis = config.get("hypothesis")
    hypothesis_config = hypothesis if isinstance(hypothesis, dict) else {}
    _set_combo_data(
        getattr(window, "stats_hypothesis_test_combo", None),
        str(hypothesis_config.get("test_kind") or "one_sample_t"),
    )
    _set_text(getattr(window, "stats_hypothesis_b_column_edit", None), str(hypothesis_config.get("second_column") or "B"))
    _set_text(getattr(window, "stats_hypothesis_null_edit", None), str(hypothesis_config.get("null_parameter") or "0"))
    _set_combo_data(
        getattr(window, "stats_hypothesis_alternative_combo", None),
        str(hypothesis_config.get("alternative") or "two_sided"),
    )
    _set_text(getattr(window, "stats_hypothesis_alpha_edit", None), str(hypothesis_config.get("alpha") or "0.05"))
    _set_combo_data(
        getattr(window, "stats_hypothesis_expected_source_combo", None),
        str(hypothesis_config.get("expected_source") or "counts"),
    )
    _set_value(
        getattr(window, "stats_hypothesis_fitted_parameters_spin", None),
        hypothesis_config.get("fitted_parameter_count", 0),
    )
    time_series = config.get("time_series")
    time_series_config = time_series if isinstance(time_series, dict) else {}
    _set_combo_data(
        getattr(window, "stats_time_series_method_combo", None),
        str(time_series_config.get("series_method") or "rolling_mean"),
    )
    _set_text(
        getattr(window, "stats_time_series_time_column_edit", None),
        str(time_series_config.get("time_column") or ""),
    )
    _set_value(getattr(window, "stats_time_series_window_size_spin", None), time_series_config.get("window_size", 3))
    _set_value(getattr(window, "stats_time_series_min_periods_spin", None), time_series_config.get("min_periods", 3))
    _set_combo_data(
        getattr(window, "stats_time_series_alignment_combo", None),
        str(time_series_config.get("alignment") or "right"),
    )
    _set_combo_data(
        getattr(window, "stats_time_series_denominator_combo", None),
        str(time_series_config.get("denominator") or "sample"),
    )
    _set_combo_data(
        getattr(window, "stats_time_series_ewma_parameter_combo", None),
        str(time_series_config.get("ewma_parameter") or "alpha"),
    )
    _set_text(
        getattr(window, "stats_time_series_ewma_value_edit", None),
        str(time_series_config.get("ewma_value") or "0.5"),
    )
    checkbox = getattr(window, "stats_time_series_ewma_adjust_checkbox", None)
    if checkbox is not None and hasattr(checkbox, "setChecked"):
        checkbox.setChecked(bool(time_series_config.get("adjust")))
    units = config.get("units")
    setattr(window, "stats_units_config", units if isinstance(units, Mapping) else None)
    _restore_display_units_controls(window, "stats", units)
    if hasattr(window, "_on_stats_mode_change"):
        window._on_stats_mode_change()


def apply_statistics_config_to_window(window: Any, config: Mapping[str, Any]) -> None:
    """Apply a validated statistics config through the existing restore path."""

    _restore_statistics_config(window, dict(config))


def apply_error_config_to_window(window: Any, config: Mapping[str, Any]) -> None:
    """Apply a validated error-propagation config through the existing restore path."""

    _restore_error_config(window, dict(config))


def apply_root_config_to_window(window: Any, config: Mapping[str, Any]) -> None:
    """Apply a validated root-solving config through the existing restore path."""

    _restore_root_config(window, dict(config))


def apply_fitting_config_to_window(window: Any, config: Mapping[str, Any]) -> None:
    """Apply a validated custom-fitting config through existing fitting controls."""

    fitting = dict(config)
    fitting["model"] = _normalize_fitting_model(fitting.get("model") or "custom")
    _set_combo_data(getattr(window, "fit_model_combo", None), str(fitting["model"]))
    _set_text(getattr(window, "fit_expr_edit", None), str(fitting.get("expression") or ""))
    _set_text(getattr(window, "fit_target_edit", None), str(fitting.get("target_column") or ""))
    _set_text(
        getattr(window, "fit_comparison_candidates_edit", None),
        str(fitting.get("comparison_candidates") or ""),
    )
    checkbox = getattr(window, "fit_weighted_checkbox", None)
    if checkbox is not None and hasattr(checkbox, "setChecked"):
        checkbox.setChecked(bool(fitting.get("weighted", False)))
    mcmc_refine = getattr(window, "fit_mcmc_refine", None)
    if mcmc_refine is not None and hasattr(mcmc_refine, "setChecked"):
        mcmc_refine.setChecked(bool(fitting.get("mcmc_refine", False)))
    _restore_variable_rows(window, fitting.get("variables"))
    if hasattr(window, "custom_constraints_checkbox"):
        window.custom_constraints_checkbox.setChecked(bool(fitting.get("constraints_enabled", False)))
    _restore_param_rows(window, fitting.get("parameter_rows"), fitting.get("parameter_orphans"))
    _restore_constants_editor_state(getattr(window, "custom_constants_editor", None), fitting.get("custom_constants"))
    units = fitting.get("units")
    setattr(window, "fit_units_config", units if isinstance(units, Mapping) else None)
    _restore_display_units_controls(window, "fit", units, include_constants=True, include_parameters=True)


def _statistics_value_columns_config(window: Any) -> list[str]:
    return [
        column.strip()
        for column in _text(getattr(window, "stats_value_column_edit", None), "A").split(",")
        if column.strip()
    ]


def _restore_root_uncertainty_options(window: Any, options: Any) -> None:
    if not isinstance(options, dict):
        options = {}
    method = str(options.get("method") or "taylor")
    if method in {"auto", "linear", "first_order", "first-order"}:
        method = "taylor"
        taylor_order = 1
    elif method in {"second_order", "second-order"}:
        method = "taylor"
        taylor_order = 2
    else:
        taylor_order = _safe_int(options.get("taylor_order", options.get("order", 1)), 1)
    combo = getattr(window, "root_uncertainty_method_combo", None)
    if combo is not None and combo.findData(method) < 0 and combo.findText(method) < 0:
        method = "taylor"
    _set_combo_data(combo, method)
    order_widget = getattr(window, "root_uncertainty_order_spin", None)
    if order_widget is not None and hasattr(order_widget, "setValue"):
        order_widget.setValue(_clamp_widget_int(order_widget, taylor_order))
    samples_widget = getattr(window, "root_monte_carlo_samples_spin", None)
    if samples_widget is not None and hasattr(samples_widget, "setValue"):
        samples_widget.setValue(_clamp_widget_int(samples_widget, _safe_int(options.get("monte_carlo_samples"), 2000)))
    _set_text(getattr(window, "root_monte_carlo_seed_edit", None), str(options.get("monte_carlo_seed") or ""))


def _clamp_widget_int(widget: Any, value: int) -> int:
    minimum = _safe_int(getattr(widget, "minimum", lambda: value)(), value)
    maximum = _safe_int(getattr(widget, "maximum", lambda: value)(), value)
    if maximum < minimum:
        return value
    return max(minimum, min(value, maximum))


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


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


def _capture_error_config(window: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "formula": _text(getattr(window, "formula_edit", None)),
        "method": _combo_data(getattr(window, "error_method_combo", None), "taylor"),
        "order": _value(getattr(window, "error_order_spin", None), 1),
        "mc_samples": _value(getattr(window, "error_mc_samples_spin", None), 5000),
        "mc_seed": _text(getattr(window, "error_mc_seed_edit", None)),
    }
    collect_units = getattr(window, "_collect_error_units_config", None)
    units = collect_units() if callable(collect_units) else getattr(window, "error_units_config", None)
    if isinstance(units, Mapping):
        config["units"] = units
    return config


def _capture_config(window: Any) -> dict[str, Any]:
    fitting_model = _normalize_fitting_model(_combo_data(getattr(window, "fit_model_combo", None), "custom"))
    if fitting_model == "auto":
        fitting_model = "custom"
    return {
        "common": {
            "mpmath_precision": _value(getattr(window, "mpmath_precision_spin", None), 16),
            "uncertainty_digits": _value(getattr(window, "uncertainty_digits_spin", None), 1),
            # generate_latex removed (4·4d — the checkbox is gone; run never writes tex).
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
            "engine": _combo_data(getattr(window, "latex_engine_combo", None), "auto"),
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
            },
            "uncertainty_column": _combo_data(getattr(window, "uncertainty_combo", None), "A"),
        },
        "error": _capture_error_config(window),
        "statistics": {
            "workflow_mode": _combo_data(getattr(window, "stats_workflow_combo", None), "standard"),
            "value_column": (_statistics_value_columns_config(window) or ["A"])[0],
            "value_columns": _statistics_value_columns_config(window),
            "group_column": _text(getattr(window, "stats_group_column_edit", None)),
            "sigma_column": _text(getattr(window, "stats_sigma_column_edit", None)),
            "mode": _combo_data(getattr(window, "stats_mode_combo", None), "mean"),
            "sample": _checked(getattr(window, "stats_sample_checkbox", None)),
            "weighted_variance": _checked(getattr(window, "stats_weight_variance_checkbox", None)),
            "trim_fraction": _text(getattr(window, "stats_trim_fraction_edit", None)),
            "matrix": {
                "missing_policy": _combo_data(getattr(window, "stats_matrix_missing_policy_combo", None), "listwise"),
            },
            "bootstrap": {
                "target_statistic": _combo_data(getattr(window, "stats_bootstrap_target_combo", None), "mean"),
                "confidence_level": _text(getattr(window, "stats_bootstrap_confidence_edit", None), "0.95"),
                "resample_count": _value(getattr(window, "stats_bootstrap_resamples_spin", None), 2000),
                "seed": _text(getattr(window, "stats_bootstrap_seed_edit", None)),
            },
            "hypothesis": {
                "test_kind": _combo_data(getattr(window, "stats_hypothesis_test_combo", None), "one_sample_t"),
                "second_column": _text(getattr(window, "stats_hypothesis_b_column_edit", None), "B"),
                "null_parameter": _text(getattr(window, "stats_hypothesis_null_edit", None), "0"),
                "alternative": _combo_data(getattr(window, "stats_hypothesis_alternative_combo", None), "two_sided"),
                "alpha": _text(getattr(window, "stats_hypothesis_alpha_edit", None), "0.05"),
                "expected_source": _combo_data(getattr(window, "stats_hypothesis_expected_source_combo", None), "counts"),
                "fitted_parameter_count": _value(getattr(window, "stats_hypothesis_fitted_parameters_spin", None), 0),
            },
            "time_series": {
                "series_method": _combo_data(getattr(window, "stats_time_series_method_combo", None), "rolling_mean"),
                "time_column": _text(getattr(window, "stats_time_series_time_column_edit", None)),
                "window_size": _value(getattr(window, "stats_time_series_window_size_spin", None), 3),
                "min_periods": _value(getattr(window, "stats_time_series_min_periods_spin", None), 3),
                "alignment": _combo_data(getattr(window, "stats_time_series_alignment_combo", None), "right"),
                "denominator": _combo_data(getattr(window, "stats_time_series_denominator_combo", None), "sample"),
                "ewma_parameter": _combo_data(getattr(window, "stats_time_series_ewma_parameter_combo", None), "alpha"),
                "ewma_value": _text(getattr(window, "stats_time_series_ewma_value_edit", None), "0.5"),
                "adjust": _checked(getattr(window, "stats_time_series_ewma_adjust_checkbox", None)),
            },
            **_capture_units_mapping(window, "_collect_statistics_units_config", "stats_units_config"),
        },
        "root_solving": _capture_root_config(window),
        "fitting": {
            "model": fitting_model,
            "expression": _text(getattr(window, "fit_expr_edit", None)),
            "comparison_candidates": _text(getattr(window, "fit_comparison_candidates_edit", None)),
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
            **_capture_units_mapping(window, "_collect_fitting_units_config", "fit_units_config"),
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


def _model_from_v1_workspace(workspace: dict[str, Any]) -> WorkbenchModel:
    return WorkbenchModel.from_v1_workspace(workspace)


def _workspace_from_model_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return WorkbenchModel.from_v1_workspace(
        _workspace_from_manifest(manifest),
        allow_legacy_floats=True,
        lenient_ui=True,
    ).to_v1_workspace()


def _history_store_from_workspace(workspace: Mapping[str, Any]) -> tuple[HistoryStore, bool]:
    if "history" not in workspace:
        return HistoryStore(), False
    history = workspace.get("history")
    if not isinstance(history, Mapping):
        raise HistoryValidationError("workspace history must be a JSON object.")
    return history_store_from_json(history), True


def _history_store_from_window(window: Any) -> HistoryStore:
    history = getattr(window, "_workspace_history_store", None)
    if history is None:
        return HistoryStore()
    if isinstance(history, HistoryStore):
        return history
    if isinstance(history, Mapping):
        return history_store_from_json(history)
    raise TypeError("_workspace_history_store must be a HistoryStore or mapping.")


def _capture_current_history_entry(
    *,
    workspace: Mapping[str, Any],
    result_snapshot: Mapping[str, Any],
    title: str,
    created_at: str,
) -> HistoryEntry | None:
    if not result_snapshot.get("present"):
        return None
    semantic = result_snapshot.get("semantic")
    if not isinstance(semantic, Mapping):
        return None
    family = str(semantic.get("family") or "")
    kind = str(result_snapshot.get("kind") or _semantic_snapshot_result_kind(semantic))
    if not family or not kind or not _semantic_snapshot_matches_kind(semantic, kind):
        return None
    semantic_hash = sha256_bytes(canonical_json(semantic))[7:23]
    rendered_cache = _history_rendered_cache_from_result_snapshot(result_snapshot)
    return HistoryEntry.from_workspace_snapshot(
        entry_id=f"current-{semantic_hash}",
        label=title or kind,
        created_at=created_at,
        workspace=workspace,
        family=family,
        kind=kind,
        result_snapshot=semantic,
        rendered_cache=rendered_cache,
    )


def _history_rendered_cache_from_result_snapshot(result_snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    plots = result_snapshot.get("plots")
    if not isinstance(plots, Sequence) or isinstance(plots, (str, bytes, bytearray, memoryview)):
        return None
    clean_plots = [dict(plot) for plot in plots if isinstance(plot, Mapping)]
    if not clean_plots:
        return None
    return {"plots": clean_plots}


def _capture_history_payload(
    window: Any,
    *,
    workspace: Mapping[str, Any],
    result_snapshot: Mapping[str, Any],
    title: str,
    created_at: str,
    include_history: bool | None,
) -> dict[str, Any] | None:
    history_enabled = bool(getattr(window, "_workspace_history_enabled", False))
    if include_history is None:
        include_history = history_enabled
    if not include_history:
        return None

    store = _history_store_from_window(window)
    current = _capture_current_history_entry(
        workspace=workspace,
        result_snapshot=result_snapshot,
        title=title,
        created_at=created_at,
    )
    if current is not None:
        store = store.with_current(current)
    elif store.current is not None:
        store = HistoryStore(current=None, entries=(store.current, *store.entries)).deduplicated()
    pruned, report = store.prune_for_save()
    window._workspace_history_store = pruned
    window._workspace_history_enabled = True
    window._workspace_history_prune_report = report
    return pruned.to_json()


def _manifest_json_size_bytes(manifest: Mapping[str, Any]) -> int:
    return len(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))


def _fit_history_to_manifest_budget(window: Any, manifest: dict[str, Any]) -> None:
    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict) or "history" not in workspace:
        return
    if _manifest_json_size_bytes(manifest) <= MAX_MANIFEST_BYTES:
        return

    store = history_store_from_json(workspace["history"])
    dropped_caches: list[str] = []
    dropped_entries: list[str] = []

    stripped_current = store.current.without_rendered_cache() if store.current is not None else None
    if stripped_current is not store.current and stripped_current is not None:
        dropped_caches.append(stripped_current.entry_id)
    stripped_entries: list[HistoryEntry] = []
    for entry in store.entries:
        stripped = entry.without_rendered_cache()
        if stripped is not entry:
            dropped_caches.append(stripped.entry_id)
        stripped_entries.append(stripped)
    store = HistoryStore(current=stripped_current, entries=tuple(stripped_entries)).deduplicated()
    workspace["history"] = store.to_json()

    entries = list(store.entries)
    while _manifest_json_size_bytes(manifest) > MAX_MANIFEST_BYTES:
        drop_index = None
        for index in range(len(entries) - 1, -1, -1):
            if not entries[index].pinned:
                drop_index = index
                break
        if drop_index is None:
            raise HistoryPruneError("workspace history cannot fit without dropping current or pinned semantic data.")
        dropped_entries.append(entries[drop_index].entry_id)
        del entries[drop_index]
        store = HistoryStore(current=store.current, entries=tuple(entries)).deduplicated()
        workspace["history"] = store.to_json()

    existing_report = getattr(window, "_workspace_history_prune_report", HistoryPruneReport())
    report = HistoryPruneReport(
        dropped_rendered_cache_entry_ids=(
            *existing_report.dropped_rendered_cache_entry_ids,
            *tuple(dropped_caches),
        ),
        dropped_entry_ids=(
            *existing_report.dropped_entry_ids,
            *tuple(dropped_entries),
        ),
    )
    window._workspace_history_store = store
    window._workspace_history_prune_report = report


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
    ui = {
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
    return ui


def _restore_ui_state(window: Any, ui: dict[str, Any]) -> None:
    if not isinstance(ui, dict):
        return
    if hasattr(window, "_workbench_formula_preview_languages"):
        delattr(window, "_workbench_formula_preview_languages")

    def _bounded_index(value: object, count: int) -> int | None:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        if 0 <= index < count:
            return index
        return None

    result_tabs = getattr(window, "result_tabs", None)
    if result_tabs is not None:
        result_index = _bounded_index(ui.get("result_subtab"), result_tabs.count())
        if result_index is not None:
            result_tabs.setCurrentIndex(result_index)

    image_page_spin = getattr(window, "image_page_spin", None)
    if image_page_spin is not None:
        plot_index = _bounded_index(ui.get("selected_plot_index"), image_page_spin.maximum())
        if plot_index is not None:
            image_page_spin.setValue(plot_index + 1)

    try:
        plot_zoom = float(ui.get("plot_zoom"))
    except (TypeError, ValueError):
        plot_zoom = 0.0
    if plot_zoom > 0 and hasattr(window, "_on_zoom_percent_changed") and hasattr(window, "zoom_percent_spin"):
        percent = int(round(plot_zoom * 100))
        percent = max(window.zoom_percent_spin.minimum(), min(window.zoom_percent_spin.maximum(), percent))
        window.zoom_percent_spin.setValue(percent)

    tabs = getattr(window, "tabs", None)
    if tabs is not None:
        main_index = _bounded_index(ui.get("main_tab"), tabs.count())
        if main_index is not None:
            tabs.setCurrentIndex(main_index)


def _snapshot_precision_settings(window: Any) -> dict[str, int]:
    return {
        "compute_digits": _safe_int(_value(getattr(window, "mpmath_precision_spin", None), 16), 16),
        "display_digits": _safe_int(_value(getattr(window, "display_digits_spin", None), 10), 10),
        "uncertainty_digits": _safe_int(_value(getattr(window, "uncertainty_digits_spin", None), 1), 1),
        "latex_input_digits": _safe_int(_value(getattr(window, "latex_input_precision_spin", None), 20), 20),
    }


def _capture_semantic_result_snapshot(
    window: Any,
    *,
    kind: str,
    overview_state: str,
    plots: list[dict[str, Any]],
) -> dict[str, Any] | None:
    payloads = getattr(window, "_last_result_payloads", {}) or {}
    if isinstance(payloads, Mapping):
        payload = payloads.get(kind)
        if isinstance(payload, Mapping):
            snapshot = build_statistics_result_snapshot(
                kind,
                payload,
                overview_state=overview_state,
                plot_metadata=plots,
                precision=_snapshot_precision_settings(window),
            )
            if snapshot is not None:
                return snapshot
            snapshot = build_fitting_comparison_result_snapshot(
                kind,
                payload,
                overview_state=overview_state,
                plot_metadata=plots,
                precision=_snapshot_precision_settings(window),
            )
            if snapshot is not None:
                return snapshot
            snapshot = build_root_result_snapshot(
                kind,
                payload,
                overview_state=overview_state,
                plot_metadata=plots,
                precision=_snapshot_precision_settings(window),
            )
            if snapshot is not None:
                return snapshot
            snapshot = build_uncertainty_result_snapshot(
                kind,
                payload,
                overview_state=overview_state,
                plot_metadata=plots,
                precision=_snapshot_precision_settings(window),
            )
            if snapshot is not None:
                return snapshot
    restored = getattr(window, "_last_result_semantic_snapshot", None)
    restored_kind = str(getattr(window, "_last_result_semantic_snapshot_kind", "") or "")
    if isinstance(restored, Mapping) and restored.get("family") in {
        "statistics",
        "fitting_comparison",
        "root_solving",
        "uncertainty",
    }:
        compatible_kind = _semantic_snapshot_result_kind(restored) or restored_kind
        if kind != compatible_kind or not _semantic_snapshot_matches_kind(restored, kind):
            return None
        return dict(restored)
    return None


def _semantic_snapshot_result_kind(snapshot: Mapping[str, Any]) -> str:
    compatibility = snapshot.get("compatibility")
    if not isinstance(compatibility, Mapping):
        return ""
    return str(compatibility.get("result_cache_kind") or "")


def _semantic_snapshot_matches_kind(snapshot: Mapping[str, Any], kind: str) -> bool:
    family = str(snapshot.get("family") or "")
    allowed = _SEMANTIC_SNAPSHOT_KIND_BY_FAMILY.get(family)
    if allowed is None or kind not in allowed:
        return False
    return _semantic_snapshot_result_kind(snapshot) == kind


def _bounded_gallery_index(value: object, count: int) -> int | None:
    try:
        index = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= index < count:
        return index
    return None


def _active_plot_gallery(window: Any) -> tuple[str, list[Path], int, list[Mapping[str, Any]]]:
    mode_attrs = {
        "stats": ("current_stats_figures", "current_stats_index", "_current_stats_plot_metadata"),
        "error": ("current_error_figures", "current_error_index", "_current_error_plot_metadata"),
        "extrap": ("current_extrap_figures", "current_extrap_index", "_current_extrap_plot_metadata"),
        "fit": ("current_fit_figures", "current_fit_index", "_current_fit_plot_metadata"),
    }
    preferred_mode = str(getattr(window, "_image_mode", "") or "")
    modes = [preferred_mode] if preferred_mode in mode_attrs else []
    modes.extend(mode for mode in ("stats", "error", "extrap", "fit") if mode not in modes)
    for mode in modes:
        figures_attr, index_attr, metadata_attr = mode_attrs[mode]
        raw_figures = getattr(window, figures_attr, []) or []
        figures = [Path(path) for path in raw_figures if path]
        if not figures:
            continue
        current_index = _bounded_gallery_index(getattr(window, index_attr, 0), len(figures))
        raw_metadata = getattr(window, metadata_attr, []) or []
        metadata = [item for item in raw_metadata if isinstance(item, Mapping)]
        return mode, figures, current_index or 0, metadata
    return "", [], 0, []


def _capture_plot_attachments(window: Any, attachments: dict[str, bytes]) -> list[dict[str, Any]]:
    mode, figures, current_index, metadata = _active_plot_gallery(window)
    plots: list[dict[str, Any]] = []
    for order, figure_path in enumerate(figures):
        try:
            plot_bytes = figure_path.read_bytes()
        except OSError:
            continue
        if not plot_bytes.startswith(_PNG_SIGNATURE):
            continue
        plot_path = f"attachments/plots/plot-{len(plots) + 1:03d}.png"
        attachments[plot_path] = plot_bytes
        raw_meta = dict(metadata[order]) if order < len(metadata) else {}
        title = str(raw_meta.get("title") or raw_meta.get("label") or f"Result plot {order + 1}")
        plot = {
            "path": plot_path,
            "role": "primary" if order == current_index else str(raw_meta.get("role") or "gallery"),
            "order": order,
            "title": title,
            "format": "png",
            "sha256": sha256_bytes(plot_bytes),
        }
        if mode:
            plot["image_mode"] = mode
        for key in ("column", "batch", "plot_index", "plot_key"):
            if raw_meta.get(key) not in (None, ""):
                plot[key] = raw_meta[key]
        plots.append(plot)
    if plots:
        return plots

    plot_bytes = getattr(window, "result_plot_bytes", None)
    if isinstance(plot_bytes, bytes) and plot_bytes:
        plot_path = "attachments/plots/plot-001.png"
        attachments[plot_path] = plot_bytes
        return [
            {
                "path": plot_path,
                "role": "primary",
                "order": 0,
                "title": "Result plot",
                "format": "png",
                "sha256": sha256_bytes(plot_bytes),
            }
        ]
    return []


def _plot_mode_from_snapshot(kind: str, plots: list[Any]) -> str:
    for plot in plots:
        if isinstance(plot, Mapping):
            image_mode = str(plot.get("image_mode") or "")
            if image_mode in {"stats", "error", "extrap", "fit"}:
                return image_mode
    if kind in {
        "statistics_single",
        "statistics_batches",
        "statistics_matrix",
        "statistics_bootstrap",
        "statistics_hypothesis_test",
        "statistics_time_series",
        "statistics_grouped",
    }:
        return "stats"
    if kind == "error":
        return "error"
    if kind == "root_solving":
        return "extrap"
    return "fit"


def _restore_plot_attachments(window: Any, plots: list[Any], attachments: Mapping[str, bytes], *, kind: str) -> bool:
    figure_paths: list[Path] = []
    for order, plot in enumerate(plots):
        if not isinstance(plot, Mapping):
            continue
        path = plot.get("path")
        if not isinstance(path, str) or path not in attachments:
            continue
        plot_bytes = attachments[path]
        if not isinstance(plot_bytes, bytes) or not plot_bytes.startswith(_PNG_SIGNATURE):
            continue
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_workspace_plot_{order + 1}.png")
        tmp.write(plot_bytes)
        tmp.flush()
        tmp.close()
        figure_path = Path(tmp.name)
        figure_paths.append(figure_path)
        if not hasattr(window, "_temp_batch_images"):
            window._temp_batch_images = []
        window._temp_batch_images.append(figure_path)
    if not figure_paths:
        return False
    if len(figure_paths) == 1 and not any(isinstance(plot, Mapping) and plot.get("image_mode") for plot in plots):
        window._update_result_plot(figure_paths[0].read_bytes())
        return True
    mode = _plot_mode_from_snapshot(kind, plots)
    if hasattr(window, "_set_image_list"):
        window._set_image_list(mode, figure_paths)
        return True
    window._update_result_plot(figure_paths[0].read_bytes())
    return True


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
    overview_state = str(getattr(window, "_workbench_result_state", "none") or "none")
    durable_overview_state = overview_state if overview_state in _DURABLE_RESULT_OVERVIEW_STATES else "none"
    plots = _capture_plot_attachments(window, attachments)
    present = bool(markdown or log_text or csv_rows or csv_headers or latex_source or plots or durable_overview_state != "none")
    if not present:
        return {"present": False}
    kind = (
        getattr(window, "_last_result_kind", None)
        or getattr(window, "_last_result_semantic_snapshot_kind", None)
        or "snapshot"
    )
    snapshot = {
        "present": True,
        "kind": kind,
        "result_of_hash": workspace_hash,
        "snapshot_only": True,
        "stale": False,
        "overview_state": durable_overview_state,
        "markdown": markdown,
        "markdown_format": markdown_format,
        "log": log_text,
        "csv": {"headers": csv_headers, "rows": csv_rows},
        "latex_source": latex_source,
        "plots": plots,
    }
    semantic = _capture_semantic_result_snapshot(
        window,
        kind=kind,
        overview_state=durable_overview_state,
        plots=plots,
    )
    if semantic is not None:
        snapshot["semantic"] = semantic
    return snapshot


def _render_semantic_snapshot_outputs(semantic_snapshot: Mapping[str, Any]) -> tuple[str, list[dict[str, object]], list[str]] | None:
    semantic_outputs = render_statistics_snapshot_outputs(semantic_snapshot)
    if semantic_outputs is None:
        semantic_outputs = render_fitting_comparison_snapshot_outputs(semantic_snapshot)
    if semantic_outputs is None:
        semantic_outputs = render_root_snapshot_outputs(semantic_snapshot)
    if semantic_outputs is None:
        semantic_outputs = render_uncertainty_snapshot_outputs(semantic_snapshot)
    if semantic_outputs is None:
        return None
    result_text, rows, headers = semantic_outputs
    return result_text, list(rows), list(headers)


def render_semantic_snapshot_outputs(semantic_snapshot: Mapping[str, Any]) -> tuple[str, list[dict[str, object]], list[str]] | None:
    """Regenerate deterministic display text and CSV rows from a semantic snapshot."""

    return _render_semantic_snapshot_outputs(semantic_snapshot)


def restore_history_entry_result(window: Any, entry: HistoryEntry) -> None:
    if not isinstance(entry, HistoryEntry):
        raise TypeError("entry must be a HistoryEntry.")
    semantic_snapshot = entry.semantic_snapshot.get("result")
    if not isinstance(semantic_snapshot, Mapping):
        raise HistoryValidationError("history entry result snapshot must be a JSON object.")
    kind = entry.kind
    if not _semantic_snapshot_matches_kind(semantic_snapshot, kind):
        raise HistoryValidationError("history entry result snapshot does not match its recorded kind.")
    semantic_outputs = _render_semantic_snapshot_outputs(semantic_snapshot)
    if semantic_outputs is None:
        raise HistoryValidationError("history entry result snapshot cannot be rendered by the semantic renderers.")

    previous_restoring = bool(getattr(window, "_workspace_restoring", False))
    window._workspace_restoring = True
    try:
        if hasattr(window, "_reset_csv_data"):
            window._reset_csv_data(clear_non_tabular_result=True, refresh_result_rail=False)
        result_text, semantic_csv_rows, semantic_csv_headers = semantic_outputs
        window.result_edit.setPlainText(result_text)
        window._last_result_text = result_text
        window._last_result_text_format = "plain"
        window._last_result_rendered_text = window.result_edit.toPlainText()
        window._last_result_semantic_snapshot = dict(semantic_snapshot)
        window._last_result_semantic_snapshot_kind = kind
        window._last_result_kind = None
        window._last_result_payloads = {}
        # Cleared alongside the display payload; 4·2 cross-restore will repopulate this from
        # the semantic snapshot so on-demand 生成 TeX works after a workspace restore.
        window._last_latex_inputs = {}
        if hasattr(window, "_set_csv_data"):
            window._set_csv_data(semantic_csv_rows, semantic_csv_headers, final_result=False)
        if hasattr(window, "log_edit"):
            window.log_edit.clear()
        if hasattr(window, "latex_edit"):
            window.latex_edit.clear()
        compatibility = semantic_snapshot.get("compatibility")
        overview_state = ""
        if isinstance(compatibility, Mapping):
            overview_state = str(compatibility.get("overview_state") or "")
        window._workbench_result_state = overview_state if overview_state in _DURABLE_RESULT_OVERVIEW_STATES else "complete"
        window._workspace_snapshot_only = True
        if hasattr(window, "_set_snapshot_controls_enabled"):
            window._set_snapshot_controls_enabled(False)
        if hasattr(window, "refresh_workbench_result_rail"):
            window.refresh_workbench_result_rail()
    finally:
        window._workspace_restoring = previous_restoring


def capture_workspace(
    window: Any,
    *,
    title: str = "Untitled",
    include_history: bool | None = None,
) -> WorkspaceBundle:
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
    provenance = normalize_workspace_provenance(getattr(window, "_workspace_provenance", {}) or {})
    if provenance:
        workspace["provenance"] = provenance
    attachments = {**data_attachments, **constants_attachments}
    model = _model_from_v1_workspace(workspace)
    workspace = model.to_v1_workspace()
    workspace_hash = model.compute_hash()
    workspace["result_snapshot"] = _capture_result_snapshot(window, workspace_hash, attachments)
    now = _utc_now()
    history_payload = _capture_history_payload(
        window,
        workspace=workspace,
        result_snapshot=workspace["result_snapshot"],
        title=title,
        created_at=now,
        include_history=include_history,
    )
    if history_payload is not None:
        workspace["history"] = history_payload
        workspace = _model_from_v1_workspace(workspace).to_v1_workspace()
    manifest = {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "app": {"name": "DataLab", "version": current_version()},
        "created_at": now,
        "updated_at": now,
        "config": workspace["config"],
        "workspace": workspace,
    }
    _fit_history_to_manifest_budget(window, manifest)
    return WorkspaceBundle(manifest=manifest, attachments=attachments)


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
        stack.setCurrentIndex(1 if source_kind in {"manual_text", "file"} else 0)
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
        editor.use_text_view(source_kind in {"manual_text", "file"})
        return
    table_restored = False
    if table is not None and isinstance(canonical, dict):
        _set_table_from_canonical(table, canonical)
        table_restored = True
    if text_edit is not None:
        text_edit.setPlainText(str(section.get("decoded_text") or _canonical_to_text(canonical)))
    if table_restored:
        refresh_summary = getattr(window, "refresh_workbench_data_summary", None)
        if callable(refresh_summary):
            refresh_summary()


def restore_workspace(window: Any, manifest: dict[str, Any], attachments: dict[str, bytes]) -> None:
    previous_restoring = bool(getattr(window, "_workspace_restoring", False))
    window._workspace_restoring = True
    try:
        _restore_workspace_contents(window, manifest, attachments)
    except Exception:
        window._workspace_dirty = True
        window._workspace_degraded = True
        raise
    finally:
        window._workspace_restoring = previous_restoring


def _restore_workspace_contents(window: Any, manifest: dict[str, Any], attachments: dict[str, bytes]) -> None:
    window._workspace_attachments = dict(attachments)
    workspace = _workspace_from_model_manifest(manifest)
    window._workspace_provenance = normalize_workspace_provenance(workspace.get("provenance") or {})
    history_store, history_enabled = _history_store_from_workspace(workspace)
    active_mode = str(workspace.get("current_mode") or "fitting")
    _set_combo_data(getattr(window, "mode_combo", None), active_mode)
    _restore_data_section(window, workspace.get("data") or {}, constants=False)
    unified_constants = workspace.get("constants") or {}
    has_unified_constants = _constants_section_has_content(unified_constants)
    _restore_data_section(window, unified_constants, constants=True)

    config = workspace.get("config") or {}
    _restore_common_config(window, config.get("common"), config.get("latex"))
    _restore_extrapolation_config(window, config.get("extrapolation"))
    _restore_error_config(window, config.get("error"))
    _restore_statistics_config(window, config.get("statistics"))
    fitting = config.get("fitting") or {}
    degraded = _degrade_obsolete_auto_fit_config(window, fitting)
    fitting["model"] = _normalize_fitting_model(fitting.get("model") or "custom")
    _set_combo_data(getattr(window, "fit_model_combo", None), str(fitting["model"]))
    if hasattr(window, "fit_expr_edit"):
        window.fit_expr_edit.setPlainText(str(fitting.get("expression") or ""))
    if hasattr(window, "fit_comparison_candidates_edit"):
        window.fit_comparison_candidates_edit.setPlainText(str(fitting.get("comparison_candidates") or ""))
    if hasattr(window, "fit_target_edit"):
        window.fit_target_edit.setText(str(fitting.get("target_column") or ""))
    units = fitting.get("units")
    setattr(window, "fit_units_config", units if isinstance(units, Mapping) else None)
    _restore_display_units_controls(window, "fit", units, include_constants=True, include_parameters=True)
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
    # log_axes (log-x / log-y plot axis selection) is captured on save but was
    # never restored, so a reloaded workspace re-ran fits with linear axes (F12).
    log_axes = fitting.get("log_axes")
    if isinstance(log_axes, dict):
        _set_checked_if(window, "log_x_checkbox", log_axes.get("x"))
        _set_checked_if(window, "log_y_checkbox", log_axes.get("y"))
    _restore_param_rows(window, parameter_rows, fitting.get("parameter_orphans"))
    restore_legacy_constants = not has_unified_constants
    restore_custom_constants = (
        restore_legacy_constants
        and active_mode == "fitting"
        and str(fitting.get("model") or "") == "custom"
    )
    if restore_custom_constants:
        _restore_constants_editor_state(getattr(window, "custom_constants_editor", None), fitting.get("custom_constants"))
    _restore_implicit_config(
        window,
        fitting.get("implicit"),
        fitting,
        restore_constants=(
            restore_legacy_constants
            and active_mode == "fitting"
            and str(fitting.get("model") or "") == "self_consistent"
        ),
    )
    _restore_root_config(
        window,
        config.get("root_solving"),
        restore_constants=restore_legacy_constants and active_mode == "root_solving",
    )

    snapshot = workspace.get("result_snapshot") or {"present": False}
    if hasattr(window, "_reset_csv_data"):
        window._reset_csv_data(clear_non_tabular_result=True, refresh_result_rail=False)
    if snapshot.get("present"):
        semantic_snapshot = snapshot.get("semantic")
        snapshot_kind = str(snapshot.get("kind") or "")
        semantic_snapshot = (
            semantic_snapshot
            if isinstance(semantic_snapshot, Mapping)
            and _semantic_snapshot_matches_kind(semantic_snapshot, snapshot_kind)
            else None
        )
        window._last_result_semantic_snapshot = dict(semantic_snapshot) if semantic_snapshot is not None else None
        window._last_result_semantic_snapshot_kind = snapshot_kind if semantic_snapshot is not None else ""
        semantic_outputs = None
        if semantic_snapshot is not None:
            semantic_outputs = _render_semantic_snapshot_outputs(semantic_snapshot)
        if semantic_outputs is not None and hasattr(window, "_set_result_text"):
            result_text, semantic_csv_rows, semantic_csv_headers = semantic_outputs
            # Route through _set_result_text so the restored result renders with
            # the same markdown display as the live run; setting plain text here
            # left toPlainText() returning raw markdown, breaking round-trip.
            window._set_result_text(result_text)
        else:
            result_text = str(snapshot.get("markdown") or "")
        if semantic_outputs is None and snapshot.get("markdown_format") == "markdown" and hasattr(window, "_set_result_text"):
            window._set_result_text(result_text)
        elif semantic_outputs is None:
            window.result_edit.setPlainText(result_text)
            window._last_result_text = result_text
            window._last_result_text_format = "plain"
            window._last_result_rendered_text = window.result_edit.toPlainText()
        window.log_edit.setPlainText(str(snapshot.get("log") or ""))
        csv_payload = snapshot.get("csv") or {}
        if semantic_outputs is not None:
            window._set_csv_data(semantic_csv_rows, semantic_csv_headers)
        else:
            window._set_csv_data(list(csv_payload.get("rows") or []), list(csv_payload.get("headers") or []))
        window.latex_edit.setPlainText(str(snapshot.get("latex_source") or ""))
        plots = snapshot.get("plots") or []
        if plots:
            _restore_plot_attachments(window, list(plots), attachments, kind=snapshot_kind)
        overview_state = str(snapshot.get("overview_state") or "none")
        if overview_state in _DURABLE_RESULT_OVERVIEW_STATES:
            window._workbench_result_state = overview_state
    else:
        window.result_edit.clear()
        window.log_edit.clear()
        window.latex_edit.clear()
        window._last_result_text = ""
        window._last_result_text_format = "plain"
        window._last_result_rendered_text = ""
        window._last_result_semantic_snapshot = None
        window._last_result_semantic_snapshot_kind = None
    window._last_result_kind = None
    window._last_result_payloads = {}
    window._last_latex_inputs = {}
    _restore_ui_state(window, workspace.get("ui") or {})
    window._workspace_snapshot_only = bool(snapshot.get("present"))
    window._workspace_history_store = history_store
    window._workspace_history_enabled = history_enabled
    if hasattr(window, "refresh_workbench_result_rail"):
        previous_autoselect_suppression = bool(getattr(window, "_suppress_result_log_autoselect", False))
        window._suppress_result_log_autoselect = True
        try:
            window.refresh_workbench_result_rail()
        finally:
            window._suppress_result_log_autoselect = previous_autoselect_suppression
    window._workspace_degraded = degraded
    if hasattr(window, "_set_snapshot_controls_enabled"):
        window._set_snapshot_controls_enabled(not window._workspace_snapshot_only)
    if hasattr(window, "refresh_workbench_formula_panel"):
        window.refresh_workbench_formula_panel()
    if hasattr(window, "refresh_workbench_variable_panel"):
        window.refresh_workbench_variable_panel()
    window._workspace_dirty = False
