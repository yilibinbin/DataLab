from __future__ import annotations

import re

from mpmath import mp


def _mp(value: object) -> mp.mpf:
    if isinstance(value, mp.mpf):
        return value
    if isinstance(value, (int, float)):
        return mp.mpf(value)
    try:
        return mp.mpf(value)
    except Exception:
        return mp.mpf(str(value))


class UncertainValue:
    """Numeric value with an absolute uncertainty."""

    def __init__(
        self,
        value: mp.mpf | int | float | str,
        uncertainty: mp.mpf | int | float | str,
        uncertainty_digits: int | None = None,
        contributions: dict[str, mp.mpf] | None = None,
    ) -> None:
        self.value: mp.mpf = _mp(value)
        self.uncertainty: mp.mpf = _mp(uncertainty)
        self.uncertainty_digits: int | None = uncertainty_digits
        self.contributions: dict[str, mp.mpf] | None = contributions or None

    def __str__(self) -> str:
        return f"{self.value} ± {self.uncertainty}"

    def __repr__(self) -> str:
        return f"UncertainValue({self.value}, {self.uncertainty}, digits={self.uncertainty_digits})"


def parse_uncertainty_format(number_str: str, lang: str = "en") -> UncertainValue:
    """Parse a number in format 1.23(1)[-2] to value and uncertainty."""
    number_str = number_str.strip()
    number_str = number_str.replace("−", "-")

    pattern = (
        r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:\([+-]?(?:\d+(?:\.\d*)?|\.\d+)\))?"
        r"(?:[eE][+-]?\d+)?"
        r"(?:\[[+-]?\d+\])?$"
    )

    def _err(msg_en: str, msg_zh: str) -> str:
        return msg_zh if lang == "zh" else msg_en

    if not re.fullmatch(pattern, number_str):
        raise ValueError(
            _err(
                f"Unrecognized uncertainty format: {number_str}",
                f"无法识别的不确定度格式: {number_str}",
            )
        )

    exponent = 0
    if "[" in number_str and "]" in number_str:
        bracket_match = re.search(r"\[([+-]?\d+)\]", number_str)
        if bracket_match:
            exponent = int(bracket_match.group(1))
            number_str = number_str[: bracket_match.start()] + number_str[bracket_match.end() :]

    uncertainty_digits: int | None = None

    def _sig_digits_from_text(text: str) -> int:
        raw = (text or "").strip()
        if not raw:
            return 1
        if raw.startswith(("+", "-")):
            raw = raw[1:]
        if "e" in raw.lower():
            mantissa, _exp = raw.lower().split("e", 1)
        else:
            mantissa = raw
        mantissa = mantissa.replace(".", "").lstrip("0")
        return max(1, len(mantissa))

    def _decimal_exponent_factor(exp: int) -> mp.mpf:
        return mp.mpf(f"1e{exp}")

    def _mp_with_extra_decimal_exponent(text: str, exp: int) -> mp.mpf:
        if exp == 0:
            return _mp(text)
        sci_match = re.search(r"[eE]([+-]?\d+)$", text)
        if sci_match:
            mantissa = text[: sci_match.start()]
            exp += int(sci_match.group(1))
            return mp.mpf(f"{mantissa}e{exp}")
        return mp.mpf(f"{text}e{exp}")

    uncertainty = mp.mpf("0")
    uncertainty_includes_outer_exponent = False
    if "(" in number_str and ")" in number_str:
        paren_match = re.search(r"\(([+-]?(?:\d+(?:\.\d*)?|\.\d+))\)", number_str)
        if paren_match:
            paren_text = paren_match.group(1)
            uncertainty_digits = _sig_digits_from_text(paren_text)
            mantissa_str = number_str[: paren_match.start()]
            suffix = number_str[paren_match.end() :]
            scientific_exponent = 0
            sci_match = re.search(r"[eE]([+-]?\d+)$", suffix)
            if sci_match:
                scientific_exponent = int(sci_match.group(1))

            combined_exponent = scientific_exponent + exponent
            if "." in paren_text or "e" in paren_text.lower():
                uncertainty = mp.mpf(f"{paren_text}e{combined_exponent}")
            else:
                if "." in mantissa_str:
                    decimal_pos = mantissa_str.find(".")
                    digits_after_decimal = len(mantissa_str) - decimal_pos - 1
                    combined_exponent -= digits_after_decimal
                uncertainty = mp.mpf(f"{paren_text}e{combined_exponent}")
            uncertainty_includes_outer_exponent = True

            number_str = mantissa_str + suffix

    value = _mp_with_extra_decimal_exponent(number_str, exponent)

    if exponent != 0:
        if not uncertainty_includes_outer_exponent:
            factor = _decimal_exponent_factor(exponent)
            uncertainty *= factor

    return UncertainValue(value, uncertainty, uncertainty_digits=uncertainty_digits)


def parse_numeric_value(value: object, lang: str = "en") -> mp.mpf:
    """Return the nominal numeric value from a plain or uncertain literal.

    Constants used by fitting expressions are deterministic inputs, so their
    uncertainty component is intentionally ignored here. This accepts the same
    compact notation used by data and error-propagation inputs, including
    ``3.2898419602500(36)[+9]`` and ``1.23(4)e-2``.
    """

    if isinstance(value, mp.mpf):
        return value
    if isinstance(value, (int, float)):
        return mp.mpf(value)
    try:
        return parse_uncertainty_format(str(value), lang=lang).value
    except Exception:
        return mp.mpf(value)
