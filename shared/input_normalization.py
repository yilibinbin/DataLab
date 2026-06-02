from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from shared.bilingual import _dual_msg
from shared.expression_names import is_reserved_expression_name
from shared.uncertainty import parse_numeric_value, parse_uncertainty_format


__all__ = [
    "CONSTANT_FIELDS",
    "IDENTIFIER_RE",
    "ConstantsState",
    "coerce_string_rows",
    "constants_rows_to_text",
    "freeze_string_rows",
    "normalize_constants_state",
    "parse_constants_text",
    "string_value",
]


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONSTANT_FIELDS = ("name", "value")


def coerce_string_rows(
    raw_rows: Any,
    keys: Sequence[str],
    *,
    source: str = "rows",
) -> list[dict[str, str]]:
    if not isinstance(raw_rows, Iterable) or isinstance(raw_rows, (str, bytes, dict)):
        raise ValueError(
            _dual_msg(
                f"{source} 必须是行对象列表。",
                f"{source} must be a list of row objects.",
            )
        )
    rows: list[dict[str, str]] = []
    for index, raw_row in enumerate(raw_rows, 1):
        if not isinstance(raw_row, dict):
            raise ValueError(
                _dual_msg(
                    f"{source} 第 {index} 行格式无效。",
                    f"{source} row {index} is malformed.",
                )
            )
        rows.append({key: string_value(raw_row.get(key)) for key in keys})
    return rows


def string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def parse_constants_text(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            name, value = stripped.split("=", 1)
            name = name.strip()
            value = value.strip()
        else:
            parts = stripped.split(None, 1)
            if len(parts) == 1:
                name, value = parts[0].strip(), ""
            else:
                name, value = parts[0].strip(), parts[1].strip()
        if name or value:
            rows.append({"name": name, "value": value})
    return rows


def constants_rows_to_text(rows: Iterable[dict[str, str]]) -> str:
    lines: list[str] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        value = str(row.get("value") or "").strip()
        if name or value:
            lines.append(f"{name} {value}".strip())
    return "\n".join(lines)


@dataclass(frozen=True)
class ConstantsState:
    enabled: bool
    view: str
    rows: tuple[Mapping[str, str], ...]
    text: str = ""
    numeric_mode: str = "uncertainty"

    def persisted_rows(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.rows]

    def compute_dict(self, *, validate: bool = True) -> dict[str, str]:
        if not self.enabled:
            return {}
        constants: dict[str, str] = {}
        for row in self.rows:
            name = row["name"].strip()
            value = row["value"].strip()
            if not name and not value:
                continue
            if not validate and (not name or not value):
                continue
            if not name:
                raise ValueError(_dual_msg("常数名不能为空。", "Constant name cannot be empty."))
            if not IDENTIFIER_RE.fullmatch(name):
                raise ValueError(_dual_msg(f"常数名无效：{name}", f"Invalid constant name: {name}"))
            if is_reserved_expression_name(name):
                raise ValueError(_dual_msg(f"常数名是保留字：{name}", f"Constant name is reserved: {name}"))
            if not value:
                raise ValueError(_dual_msg(f"常数 {name} 需要数值。", f"Constant {name} needs a value."))
            if name in constants:
                raise ValueError(_dual_msg(f"常数名重复：{name}", f"Duplicate constant name: {name}"))
            if validate:
                try:
                    if self.numeric_mode == "mpmath":
                        parse_numeric_value(value)
                    else:
                        parse_uncertainty_format(value)
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(
                        _dual_msg(
                            f"常数 {name} 的数值无效。",
                            f"Invalid value for constant {name}.",
                        )
                    ) from exc
            constants[name] = value
        return constants


def normalize_constants_state(
    *,
    enabled: bool,
    view: str = "table",
    rows: Iterable[dict[str, Any]] | dict[str, Any] | None = None,
    text: str = "",
    numeric_mode: str = "uncertainty",
) -> ConstantsState:
    if isinstance(rows, dict):
        clean_rows = [{"name": str(name), "value": string_value(value)} for name, value in rows.items()]
    elif rows is None:
        clean_rows = parse_constants_text(text) if view == "text" else []
    else:
        clean_rows = coerce_string_rows(rows, CONSTANT_FIELDS, source="Constant rows")
    if view == "text" and text and not clean_rows:
        clean_rows = parse_constants_text(text)
    return ConstantsState(
        enabled=bool(enabled),
        view="text" if view == "text" else "table",
        rows=freeze_string_rows(clean_rows),
        text=str(text or ""),
        numeric_mode=numeric_mode,
    )


def freeze_string_rows(rows: Iterable[Mapping[str, str]]) -> tuple[Mapping[str, str], ...]:
    return tuple(MappingProxyType(dict(row)) for row in rows)


_IDENTIFIER_RE = IDENTIFIER_RE
_string_value = string_value
_freeze_rows = freeze_string_rows
