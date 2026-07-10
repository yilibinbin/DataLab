from __future__ import annotations

import re
from typing import Iterable

from mpmath import mp

from shared.precision import precision_guard as _precision_guard

from .expression_engine import _mp


def _split_mantissa_exponent(value: mp.mpf) -> tuple[mp.mpf, int]:
    if value == 0:
        return mp.mpf("0"), 0
    exponent = int(mp.floor(mp.log10(mp.fabs(value))))
    mantissa = value / mp.power(10, exponent)
    return mantissa, exponent


# Extra working digits over `places` so the mp.power(10, places) product and the value*factor
# multiply never lose the requested fractional digits to the ambient mp.dps.
_FORMAT_GUARD_DIGITS = 12


def _format_workdps(places: int) -> int:
    """Working precision for formatting a value to `places` decimals.

    These formatters run at the AMBIENT ``mp.dps`` unless guarded; when the caller stashes a
    high-precision result and formats it later (e.g. on-demand TeX rebuild after the run's own
    precision_guard has closed), the ambient dps can be the process default (~15) while `places`
    is 20-200. Without a floor, the intermediate products carry only ~15 sig digits and silently
    corrupt every digit past ~16. Floor the working precision to comfortably exceed `places` and
    the value's own magnitude so the rounding is exact regardless of the caller's ambient dps.
    """
    return max(int(mp.dps), int(places) + _FORMAT_GUARD_DIGITS)


def _round_to_places(value: mp.mpf, places: int) -> mp.mpf:
    if places <= 0:
        return mp.nint(value)
    with _precision_guard(_format_workdps(places)):
        factor = mp.power(10, places)
        return mp.nint(value * factor) / factor


def _format_fixed_places(value: mp.mpf, places: int) -> str:
    rounded = _round_to_places(value, max(0, places))
    if places <= 0:
        try:
            return str(int(rounded))
        except Exception:
            text = str(mp.nstr(rounded, n=20, strip_zeros=True))
            return text[:-2] if text.endswith(".0") else text
    with _precision_guard(_format_workdps(places)):
        sign = "-" if rounded < 0 else ""
        abs_val = mp.fabs(rounded)
        integer_part = int(mp.floor(abs_val))
        fractional = abs_val - integer_part
        scaled = int(mp.nint(fractional * mp.power(10, places)))
    frac_str = f"{scaled:0{places}d}"
    return f"{sign}{integer_part}.{frac_str}"


def _shift_decimal_string(value_str: str, exponent: int) -> str:
    """Shift decimal point in a plain decimal string by 10**exponent (string-based, preserves digits)."""
    text = (value_str or "").strip()
    if not text:
        return ""
    sign = ""
    if text[0] in "+-":
        sign = "-" if text[0] == "-" else ""
        text = text[1:]
    if not text:
        return sign + "0"
    if "." in text:
        left, right = text.split(".", 1)
    else:
        left, right = text, ""
    if left == "":
        left = "0"
    digits = f"{left}{right}"
    if not digits or set(digits) <= {"0"}:
        return sign + "0"

    current_pos = len(left)
    new_pos = current_pos + int(exponent)
    if new_pos <= 0:
        zeros = "0" * (-new_pos)
        return sign + "0." + zeros + digits
    if new_pos >= len(digits):
        zeros = "0" * (new_pos - len(digits))
        return sign + digits + zeros
    int_part = digits[:new_pos]
    frac_part = digits[new_pos:]
    if not int_part:
        int_part = "0"
    return sign + int_part + ("." + frac_part if frac_part else "")


_LATEX_BRACKET_EXP_RE = re.compile(r"\[(?:\\text\{)?\s*([+-]?\d+)\s*(?:\})?\]\s*$")


def _expand_scientific_brackets_to_fixed(text: str) -> str:
    """
    Convert mantissa(unc)[\\text{exp}] into fixed decimal mantissa'(unc) without exponent.
    Used ONLY for siunitx-mode LaTeX file output (no scientific notation allowed).
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    # Strip math mode
    if raw.startswith("$") and raw.endswith("$") and len(raw) >= 2:
        raw = raw[1:-1].strip()
    # Strip \num{...} wrapper (keep the inner content)
    if raw.startswith("\\num{"):
        start = raw.find("{")
        if start >= 0:
            depth = 0
            end = -1
            for idx in range(start, len(raw)):
                ch = raw[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = idx
                        break
            if end > start:
                inner = raw[start + 1 : end]
                tail = raw[end + 1 :]
                raw = (inner + tail).strip()

    exponent = 0
    mexp = _LATEX_BRACKET_EXP_RE.search(raw)
    if mexp:
        try:
            exponent = int(mexp.group(1))
        except Exception:
            exponent = 0
        raw = raw[: mexp.start()].strip()

    unc = None
    if "(" in raw and raw.endswith(")"):
        idx = raw.find("(")
        if idx > 0:
            unc = raw[idx + 1 : -1]
            raw = raw[:idx].strip()

    fixed = _shift_decimal_string(raw, exponent) if raw else ""
    if unc is None:
        return fixed
    return f"{fixed}({unc})"


_SIUNITX_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\(\d+\))?$")


def _siunitx_number_components(number_text: str) -> tuple[int, int, int] | None:
    """
    Return (int_digits, frac_digits, unc_digits) for a siunitx-parseable decimal with optional (unc).
    Accepts: -12.345(67), 0.1(2), 123(4), .5(1)
    """
    text = (number_text or "").strip()
    if not text:
        return None
    if text.startswith("\\multicolumn"):
        return None
    if text.startswith("$") and text.endswith("$") and len(text) >= 2:
        text = text[1:-1].strip()
    if text.startswith("\\num{"):
        m = re.match(r"^\\num\{([^}]*)\}$", text)
        if m:
            text = m.group(1).strip()
    text = text.replace("\\,", "").replace(" ", "")
    if not _SIUNITX_NUMBER_RE.fullmatch(text):
        return None

    unc_digits = 0
    if "(" in text and text.endswith(")"):
        base, unc = text.split("(", 1)
        unc = unc[:-1]
        unc_digits = len(unc) if unc else 0
        text = base

    if text.startswith(("+", "-")):
        text = text[1:]

    if "." in text:
        int_part, frac_part = text.split(".", 1)
        if int_part == "":
            int_part = "0"
        int_digits = len(int_part.lstrip("0")) if int_part.lstrip("0") else 1
        frac_digits = len(frac_part) if frac_part else 0
        return int_digits, frac_digits, unc_digits

    int_part = text if text else "0"
    int_digits = len(int_part.lstrip("0")) if int_part.lstrip("0") else 1
    return int_digits, 0, unc_digits


def _siunitx_column_spec(values: list[str]) -> str:
    """Compute S column spec with table-format based on final cell strings (including optional (unc))."""
    max_int = 1
    max_frac = 0
    max_unc = 0
    for cell in values:
        comp = _siunitx_number_components(cell)
        if comp is None:
            continue
        i, f, u = comp
        max_int = max(max_int, i)
        max_frac = max(max_frac, f)
        max_unc = max(max_unc, u)
    if max_unc > 0:
        if max_frac <= 0:
            return f"S[table-format={max_int}({max_unc})]"
        return f"S[table-format={max_int}.{max_frac}({max_unc})]"
    if max_frac <= 0:
        return f"S[table-format={max_int}]"
    return f"S[table-format={max_int}.{max_frac}]"


def siunitx_column_spec(values: list[str]) -> str:
    """Public wrapper: compute S[table-format=...] from final output strings."""
    return _siunitx_column_spec(values)


def parse_plain_decimal_width(text: str) -> tuple[int, int] | None:
    """Return (int_digits, frac_digits) for a plain decimal suitable for siunitx S columns, or None."""
    comp = _siunitx_number_components(text)
    if comp is None:
        return None
    int_digits, frac_digits, unc_digits = comp
    if unc_digits:
        return None
    return int_digits, frac_digits


def parse_unc_bracket_width(text: str) -> tuple[int, int, int] | None:
    """Return (int_digits, frac_digits, unc_digits) for a decimal with (unc) suffix, or None."""
    comp = _siunitx_number_components(text)
    if comp is None:
        return None
    int_digits, frac_digits, unc_digits = comp
    if unc_digits <= 0:
        return None
    return int_digits, frac_digits, unc_digits


def build_siunitx_colspec(numeric_columns: list[list[str]], *, first_col_spec: str = "l") -> str:
    """
    Build a full tabular column spec for siunitx-mode tables.

    `first_col_spec` is the left-most non-numeric column (label/index), and every
    following column uses a computed `S[table-format=...]` spec derived from the
    final cell strings in `numeric_columns`.
    """
    specs = [first_col_spec]
    for col in numeric_columns:
        specs.append(siunitx_column_spec(col))
    return " ".join(specs)


def siunitx_safe_cell(cell: str, *, align: str = "l") -> str:
    """Wrap non-numeric content for an S column using \\multicolumn{1}{...}{...} to avoid siunitx parse errors."""
    text = "" if cell is None else str(cell)
    stripped = text.strip()
    if not stripped:
        return f"\\multicolumn{{1}}{{{align}}}{{}}"
    if stripped.startswith("\\multicolumn"):
        return text
    if _siunitx_number_components(stripped) is not None:
        return text
    return f"\\multicolumn{{1}}{{{align}}}{{{text}}}"


def _fractional_places(value: mp.mpf) -> int:
    """Count fractional digits in a plain string representation (ignores exponents)."""
    text = mp.nstr(value, 30)
    if "e" in text or "E" in text:
        return 0
    if "." in text:
        return len(text.split(".", 1)[1].rstrip("0"))
    return 0


def _sig_digits(value: mp.mpf) -> int:
    """Roughly infer significant digits from the numeric string (best-effort)."""
    text = mp.nstr(mp.fabs(value), 50, strip_zeros=False)
    if "e" in text or "E" in text:
        mantissa, _ = text.replace("E", "e").split("e", 1)
    else:
        mantissa = text
    mantissa = mantissa.replace(".", "").lstrip("0")
    return max(1, len(mantissa))


def _auto_uncertainty_digits(uncertainty: mp.mpf) -> int:
    """
    Auto-select uncertainty significant digits (1 or 2).

    Rule:
    - If the leading significant digit of |uncertainty| is 1 -> use 2 digits
    - Otherwise -> use 1 digit
    """
    try:
        s = mp.fabs(_mp(uncertainty))
    except Exception:
        return 1

    try:
        if not mp.isfinite(s):
            return 1
    except Exception:
        # Fallback for environments without mp.isfinite
        pass

    if s <= 0:
        return 1

    try:
        order = int(mp.floor(mp.log10(s)))
        leading = int(mp.floor(s / mp.power(10, order)))
    except Exception:
        return 1

    if leading < 1:
        leading = 1
    if leading > 9:
        leading = 9

    return 2 if leading == 1 else 1


def format_scientific_latex(value: object, use_brackets: bool = True) -> str:
    """
    Format a number in LaTeX scientific notation with brackets for exponents.
    """
    value = _mp(value)
    if value == 0:
        return "0"
    mantissa, exponent = _split_mantissa_exponent(value)
    mantissa_str = str(mp.nstr(mantissa, n=13, strip_zeros=False))
    if use_brackets:
        if exponent == 0:
            return mantissa_str
        exp_str = f"+{exponent}" if exponent > 0 else str(exponent)
        return f"{mantissa_str}[\\text{{{exp_str}}}]"
    return f"{mantissa_str}E{exponent:+d}"


def format_scientific_latex_decimal(value: object, use_brackets: bool = True) -> str:
    """Format a Decimal number in LaTeX scientific notation (maintains high precision)."""
    return format_scientific_latex(value, use_brackets=use_brackets)


def _uncertainty_decimal_places(unc: mp.mpf, target_digits: int) -> tuple[int, str]:
    """
    Return (decimal_places, uncertainty_str) so that uncertainty_str has `target_digits`
    significant digits and is expressed as an integer, aligning value decimals accordingly.
    """
    if unc <= 0 or target_digits <= 0:
        return 0, "0"
    s_abs = mp.fabs(unc)
    order = int(mp.floor(mp.log10(s_abs))) if s_abs != 0 else 0
    decimal_places = max(0, target_digits - 1 - order)
    scale = mp.power(10, decimal_places)
    unc_int = int(mp.nint(s_abs * scale))
    # Rounding can carry into an extra digit (e.g. 9.6 @ 1 sig fig -> nint(9.6)=10).
    # The rounded value then has target_digits+1 digits; drop the least-significant
    # one so it keeps exactly target_digits sig figs at one lower decimal place:
    # unc_int becomes 10**(target_digits-1) (10, 100, ...) — NOT unc_int/10, which
    # would understate the magnitude by 10x (audit F5).
    if unc_int >= 10**target_digits:
        # Rounding carried into an extra digit (9.6@1sf -> nint=10, 99.6@2sf ->
        # nint=100). The correct integer is 10**target_digits at the SAME decimal
        # place: its real value is int(unc_int) * 10**-decimal_places, i.e.
        # 9.6->10.0, 0.96->1.0, 99.6->100.0. The old code used unc_int//10 and
        # decremented decimal_places, understating the uncertainty 10x (audit F5).
        unc_int = 10**target_digits
    return decimal_places, str(unc_int)


# Threshold (in orders of magnitude) at which the parenthetical
# compact form switches its exponent anchor from the value to the
# uncertainty. Below this, the parenthetical integer would balloon
# to 20+ digits (e.g. ``4(1543551156637860)[\\text{-18}]``); above
# it, the form stays bounded and the value rounds to ``0`` at the
# displayed precision (the correct visual signal that the
# uncertainty dominates). Pinned by tests; bumping it is a visible
# behaviour change.
_UNCERTAINTY_DOMINATES_EXP_GAP = 2


def _select_common_exponent(val_mp: mp.mpf, unc_mp: mp.mpf) -> int:
    """Pick the exponent the parenthetical compact form anchors to.

    Default: anchor to the value's exponent so the leading digit of
    the displayed number is the value's leading significant digit
    (the most readable form when value and uncertainty are of
    comparable magnitude — ``4.0(15)[\\text{-18}]``).

    When ``unc_exp - val_exp > _UNCERTAINTY_DOMINATES_EXP_GAP`` we
    anchor to the uncertainty's exponent instead so the
    parenthetical integer stays bounded — the output stays in pure
    siunitx parenthetical syntax, so an ``S`` column accepts it
    without raising "Missing $".
    """
    # Compute the uncertainty exponent first — it's the only one
    # always needed (val_mp == 0 short-circuits to it; the dominance
    # check needs it). The value exponent is only fetched when both
    # are non-zero.
    if val_mp == 0 and unc_mp == 0:
        return 0
    if unc_mp <= 0:
        # ``unc_mp`` non-positive means no uncertainty — anchor to
        # value (or zero if the value is zero too, handled above).
        _, val_exp = _split_mantissa_exponent(val_mp)
        return val_exp
    _, unc_exp = _split_mantissa_exponent(unc_mp)
    if val_mp == 0:
        return unc_exp
    _, val_exp = _split_mantissa_exponent(val_mp)
    if unc_exp - val_exp > _UNCERTAINTY_DOMINATES_EXP_GAP:
        return unc_exp
    return val_exp


def format_uncertainty_notation(
    value: object, uncertainty: object, uncertainty_digits: int | None = None
) -> str:
    """
    Format a value and uncertainty back to the 1.23(1)[-2] notation.

    Always emits siunitx-compatible parenthetical syntax (no ``\\pm``
    or other math-mode escape) so the output works inside an ``S``
    column. When the uncertainty dominates the value by more than
    ~2 orders of magnitude the displayed exponent anchors to the
    uncertainty rather than the value — the value rounds to ``0``
    in the displayed precision but the form stays valid LaTeX.
    """
    val_mp = _mp(value)
    unc_mp = _mp(uncertainty)

    if unc_mp <= 0:
        return format_scientific_latex_decimal(val_mp)

    common_exp = _select_common_exponent(val_mp, unc_mp)

    exp_factor = mp.power(10, common_exp)
    scaled_value = val_mp / exp_factor
    scaled_uncertainty = unc_mp / exp_factor
    try:
        target_digits = int(uncertainty_digits) if uncertainty_digits is not None else None
    except Exception:
        target_digits = None
    if not target_digits or target_digits <= 0:
        target_digits = _auto_uncertainty_digits(unc_mp)
    decimal_places, uncertainty_str = _uncertainty_decimal_places(scaled_uncertainty, target_digits)

    value_str = _format_fixed_places(scaled_value, decimal_places)

    if common_exp == 0:
        return f"{value_str}({uncertainty_str})"
    exp_str = f"{common_exp}" if common_exp < 0 else f"+{common_exp}"
    return f"{value_str}({uncertainty_str})[\\text{{{exp_str}}}]"


def format_result_with_uncertainty_latex(
    value: object, uncertainty: object, uncertainty_digits: int | None = None
) -> str:
    """
    Format the result with uncertainty in LaTeX scientific notation.

    For example: 0.00012(2) becomes 1.2(2)[-4]

    Always emits siunitx-compatible parenthetical syntax (works in
    ``S`` columns). When uncertainty dominates value, anchors the
    exponent to the uncertainty so the parenthetical never balloons
    to 20+ digits (see ``_select_common_exponent``).
    """
    val_mp = _mp(value)
    unc_mp = _mp(uncertainty)

    if unc_mp <= 0:
        return format_scientific_latex_decimal(val_mp)

    common_exp = _select_common_exponent(val_mp, unc_mp)

    exp_factor = mp.power(10, common_exp)
    scaled_value = val_mp / exp_factor
    scaled_uncertainty = unc_mp / exp_factor

    try:
        target_digits = int(uncertainty_digits) if uncertainty_digits is not None else None
    except Exception:
        target_digits = None
    if not target_digits or target_digits <= 0:
        target_digits = _auto_uncertainty_digits(unc_mp)
    decimal_places, unc_str = _uncertainty_decimal_places(scaled_uncertainty, target_digits)

    value_str = _format_fixed_places(scaled_value, decimal_places)

    if common_exp == 0:
        return f"{value_str}({unc_str})"
    exp_str = f"+{common_exp}" if common_exp > 0 else str(common_exp)
    return f"{value_str}({unc_str})[\\text{{{exp_str}}}]"


def format_uncertainty_display_latex(
    value: object,
    uncertainty: object,
    *,
    mp_precision: int | None = None,
    latex_digits: int = 16,
    uncertainty_digits: int | None = None,
) -> tuple[str, bool]:
    """Format (value, uncertainty) for GUI display under a fixed precision."""
    with _precision_guard(mp_precision):
        val = _mp(value)
        sig = mp.mpf("0")
        if uncertainty is not None:
            sig = _mp(uncertainty)

        if mp.almosteq(sig, mp.mpf("0")):
            try:
                digits = int(latex_digits)
            except Exception:
                digits = 16
            return mp.nstr(val, digits), False
        return format_result_with_uncertainty_latex(val, sig, uncertainty_digits), True


def format_scientific_notation_brackets(
    value: object,
    precision: int | None = None,
    consistent_precision: int | None = None,
) -> str:
    """
    Format a number in scientific notation with [exponent] brackets.
    """
    value = _mp(value)
    if value == 0:
        if precision is not None:
            return "0.{0}".format("0" * precision)
        return "0.0"
    mantissa, exponent = _split_mantissa_exponent(value)
    actual_precision = consistent_precision if consistent_precision is not None else precision
    if actual_precision is not None:
        mantissa_str = _format_fixed_places(mantissa, actual_precision)
    else:
        mantissa_str = str(mp.nstr(mantissa, n=20, strip_zeros=False))
    if consistent_precision is None:
        mantissa_str = mantissa_str.rstrip("0").rstrip(".") if "." in mantissa_str else mantissa_str
    if exponent == 0:
        return mantissa_str
    return f"{mantissa_str}[\\text{{{exponent}}}]"


def format_scientific_notation_brackets_decimal(
    value: object,
    precision: int | None = None,
    consistent_precision: int | None = None,
) -> str:
    """
    Format numbers using plain or scientific notation compatible with siunitx S columns.
    Falls back to mantissa e exponent instead of bracket notation with \\text macros.
    """
    formatted = format_scientific_notation_brackets(
        value, precision=precision, consistent_precision=consistent_precision
    )
    if "[" not in formatted or "]" not in formatted:
        return formatted
    mantissa, exponent_part = formatted.split("[", 1)
    exponent = (
        exponent_part.replace("\\text", "")
        .replace("{", "")
        .replace("}", "")
        .replace("]", "")
        .strip()
    )
    if exponent.startswith("+"):
        exponent = exponent[1:]
    return f"{mantissa}e{exponent}"


def add_spacing_to_number(number_str: str, for_siunitx: bool = False, group_size: int = 3) -> str:
    """
    Add spaces every N digits in the decimal part of a number.
    Handles scientific notation with brackets and uncertainty notation properly.
    """
    try:
        group_size = int(group_size)
    except Exception:
        group_size = 3
    group_size = max(0, group_size)

    if group_size <= 0:
        return number_str

    space_char = "\\," if for_siunitx else " "

    if "(" in number_str and ")" in number_str:
        paren_start = number_str.find("(")
        value_part = number_str[:paren_start]
        uncertainty_part = number_str[paren_start:]
        processed_value = add_spacing_to_number(value_part, for_siunitx, group_size)
        return processed_value + uncertainty_part

    if "e" in number_str:
        e_pos = number_str.find("e")
        mantissa_part = number_str[:e_pos]
        exponent_part = number_str[e_pos:]
        if "." in mantissa_part:
            integer_part, decimal_part = mantissa_part.split(".")
            spaced_decimal = ""
            for i, digit in enumerate(decimal_part):
                if i > 0 and i % group_size == 0:
                    spaced_decimal += space_char
                spaced_decimal += digit
            processed_mantissa = integer_part + "." + spaced_decimal
        else:
            processed_mantissa = mantissa_part
        return processed_mantissa + exponent_part

    if "[" in number_str and "]" in number_str:
        bracket_start = number_str.find("[")
        mantissa_part = number_str[:bracket_start]
        exponent_part = number_str[bracket_start:]
        if "." in mantissa_part:
            integer_part, decimal_part = mantissa_part.split(".")
            spaced_decimal = ""
            for i, digit in enumerate(decimal_part):
                if i > 0 and i % group_size == 0:
                    spaced_decimal += space_char
                spaced_decimal += digit
            processed_mantissa = integer_part + "." + spaced_decimal
        else:
            processed_mantissa = mantissa_part
        return processed_mantissa + exponent_part

    if "." in number_str:
        integer_part, decimal_part = number_str.split(".")
        spaced_decimal = ""
        for i, digit in enumerate(decimal_part):
            if i > 0 and i % group_size == 0:
                spaced_decimal += space_char
            spaced_decimal += digit
        return integer_part + "." + spaced_decimal

    return number_str


def group_digits_both_sides(number_str: str, group_size: int, sep: str = "\\,") -> str:
    """Group BOTH the integer and fractional parts of a number by ``group_size`` digits.

    Unlike :func:`add_spacing_to_number` (which only spaces the fractional part), this
    inserts ``sep`` every ``group_size`` digits in the integer part (from the decimal point
    leftward, thousands-style) AND the fractional part (rightward). Any leading sign and any
    trailing suffix (uncertainty ``(NN)``, exponent) are preserved untouched.

    This is the app-side grouping path used when the LaTeX engine's siunitx cannot honour a
    variable digit-group width (the bundled Tectonic siunitx is pinned at 3): the number is
    pre-grouped here so any width renders correctly with a plain (non-S) column.

    Returns ``number_str`` unchanged when ``group_size <= 0``.
    """
    try:
        group_size = int(group_size)
    except Exception:
        group_size = 3
    if group_size <= 0:
        return number_str

    match = re.match(r"^([+\-−]?)(\d+)(?:\.(\d+))?(.*)$", number_str.strip())
    if not match:
        return number_str
    sign, int_part, frac_part, tail = match.groups()

    grouped_int_chars: list[str] = []
    for i, ch in enumerate(reversed(int_part)):
        if i > 0 and i % group_size == 0:
            grouped_int_chars.append(sep)
        grouped_int_chars.append(ch)
    grouped_int = "".join(reversed(grouped_int_chars))

    result = (sign or "") + grouped_int
    if frac_part is not None:
        grouped_frac_chars: list[str] = []
        for i, ch in enumerate(frac_part):
            if i > 0 and i % group_size == 0:
                grouped_frac_chars.append(sep)
            grouped_frac_chars.append(ch)
        result += "." + "".join(grouped_frac_chars)
    return result + (tail or "")


def add_latex_spacing_to_number(number_str: str, group_size: int = 3) -> str:
    """
    Add LaTeX thin spaces (\\\\,) every N digits in the decimal part of a number.
    Handles scientific notation with brackets and uncertainty notation properly.
    """
    return add_spacing_to_number(number_str, for_siunitx=True, group_size=group_size)


def format_uncertainty_notation_for_dcolumn(
    value: object,
    uncertainty: object,
    uncertainty_digits: int | None = None,
    *,
    group_size: int = 3,
) -> str:
    """
    Format a value and uncertainty for dcolumn with proper spacing.
    Uses LaTeX thin spaces (\\\\,) that work with dcolumn.
    """
    val_mp = _mp(value)
    unc_mp = _mp(uncertainty)

    if unc_mp <= 0:
        basic_notation = format_scientific_latex_decimal(val_mp)
        return add_latex_spacing_to_number(basic_notation, group_size=group_size)

    basic_notation = format_uncertainty_notation(val_mp, unc_mp, uncertainty_digits)
    result = add_latex_spacing_to_number(basic_notation, group_size=group_size)

    if "[" in result and "]" in result:
        bracket_start = result.find("[")
        bracket_end = result.find("]")
        exp_part = result[bracket_start + 1 : bracket_end].strip()
        if exp_part and not exp_part.startswith("+"):
            try:
                exp_value = int(exp_part)
            except Exception:
                exp_value = None
            if exp_value is not None and exp_value >= 0:
                result = result[: bracket_start + 1] + "+" + exp_part + result[bracket_end:]

    return result


def calculate_dcolumn_format_for_column(
    data_column: Iterable[object], column_name: str = ""
) -> str:
    """
    Calculate the optimal dcolumn format for a column based on the longest formatted value.
    For scientific notation: uses fixed 2 digits before decimal, dynamic after decimal.
    """
    max_integer_digits = 2
    max_decimal_digits = 0
    has_scientific_notation = False

    for item in data_column:
        try:
            if isinstance(item, str):
                formatted_str = item
            elif hasattr(item, "value"):
                value = item.value
                uncertainty = getattr(item, "uncertainty", mp.mpf("0"))
                if uncertainty > 0:
                    formatted_str = format_uncertainty_notation_for_dcolumn(value, uncertainty)
                else:
                    formatted_str = format_scientific_latex_decimal(value)
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                value = item[0]
                uncertainty = item[1] if len(item) > 1 else mp.mpf("0")
                if uncertainty > 0:
                    formatted_str = format_uncertainty_notation_for_dcolumn(value, uncertainty)
                else:
                    formatted_str = format_scientific_latex_decimal(value)
            else:
                value_decimal = _mp(item)
                formatted_str = format_scientific_latex_decimal(value_decimal)

            clean_str = formatted_str.replace("\\,", "").replace("\\text{", "").replace("}", "")

            if "[" in clean_str and "]" in clean_str:
                has_scientific_notation = True
                bracket_pos = clean_str.find("[")
                mantissa_part = clean_str[:bracket_pos]

                if "(" in mantissa_part:
                    paren_pos = mantissa_part.find("(")
                    number_part = mantissa_part[:paren_pos]
                    uncertainty_part = mantissa_part[paren_pos:]
                    unc_digits = len(uncertainty_part) - 2
                else:
                    number_part = mantissa_part
                    unc_digits = 0

                if "." in number_part:
                    _integer_part, decimal_part = number_part.split(".")
                    decimal_digits = len(decimal_part) + unc_digits + 5
                    max_decimal_digits = max(max_decimal_digits, decimal_digits)
                else:
                    max_decimal_digits = max(max_decimal_digits, unc_digits + 5)
            else:
                if "." in clean_str:
                    integer_part, decimal_part = clean_str.split(".")
                    integer_digits = len(integer_part) + 1
                    decimal_digits = len(decimal_part) + 2
                    max_integer_digits = max(max_integer_digits, integer_digits)
                    max_decimal_digits = max(max_decimal_digits, decimal_digits)
                else:
                    integer_digits = len(clean_str) + 1
                    max_integer_digits = max(max_integer_digits, integer_digits)

        except Exception as e:
            print(f"Warning: Error processing item in column {column_name}: {item}, error: {e}")
            continue

    if has_scientific_notation:
        max_integer_digits = 2

    return f"d{{{max_integer_digits}.{max_decimal_digits}}}"


def _format_zero_uncertainty_dcolumn_input(
    value: mp.mpf, decimals: int | None, *, group_size: int = 3
) -> str:
    """Format σ=0 input value for dcolumn (keeps bracket-exponent style with explicit +)."""
    val = _mp(value)
    if decimals is None:
        return format_uncertainty_notation_for_dcolumn(val, mp.mpf("0"), group_size=group_size)
    if mp.almosteq(val, mp.mpf("0")):
        mantissa_str = _format_fixed_places(mp.mpf("0"), max(0, int(decimals)))
        return add_latex_spacing_to_number(mantissa_str, group_size=group_size)
    mantissa, exponent = _split_mantissa_exponent(val)
    mantissa_str = _format_fixed_places(mantissa, max(0, int(decimals)))
    if exponent == 0:
        out = mantissa_str
    else:
        exp_str = f"{exponent}" if exponent < 0 else f"+{exponent}"
        out = f"{mantissa_str}[\\text{{{exp_str}}}]"
    return add_latex_spacing_to_number(out, group_size=group_size)


def _format_value_for_latex_file(
    *,
    value: mp.mpf,
    sigma: mp.mpf | None,
    use_dcolumn: bool,
    latex_input_decimals: int | None,
    is_input: bool,
    latex_group_size: int = 3,
    uncertainty_digits: int | None = None,
    zero_uncertainty_mantissa_decimals: int | None = None,
) -> str:
    """File-only numeric formatter: siunitx-mode uses fixed decimals; dcolumn-mode uses existing bracket style."""
    val = _mp(value)
    sig = None
    if sigma is not None:
        try:
            sig = _mp(sigma)
        except Exception:
            sig = None

    if use_dcolumn:
        if sig is not None and not mp.almosteq(sig, mp.mpf("0")):
            return format_uncertainty_notation_for_dcolumn(
                val, sig, uncertainty_digits, group_size=latex_group_size
            )
        if latex_input_decimals is not None:
            return _format_zero_uncertainty_dcolumn_input(
                val, latex_input_decimals, group_size=latex_group_size
            )
        return format_uncertainty_notation_for_dcolumn(
            val, mp.mpf("0"), uncertainty_digits, group_size=latex_group_size
        )

    if sig is None or mp.almosteq(sig, mp.mpf("0")):
        if is_input and latex_input_decimals is not None:
            return _format_fixed_places(val, int(latex_input_decimals))
        if zero_uncertainty_mantissa_decimals is not None and not mp.almosteq(val, mp.mpf("0")):
            mantissa, exponent = _split_mantissa_exponent(val)
            mantissa_str = _format_fixed_places(mantissa, int(zero_uncertainty_mantissa_decimals))
            if exponent == 0:
                return mantissa_str
            exp_str = f"{exponent}" if exponent < 0 else f"+{exponent}"
            return _expand_scientific_brackets_to_fixed(f"{mantissa_str}[\\text{{{exp_str}}}]")
        return _expand_scientific_brackets_to_fixed(format_scientific_latex_decimal(val))
    return _expand_scientific_brackets_to_fixed(
        format_result_with_uncertainty_latex(val, sig, uncertainty_digits)
    )


def format_value_for_latex_file(
    value: mp.mpf,
    sigma: mp.mpf | None,
    *,
    use_dcolumn: bool,
    latex_input_decimals: int | None,
    is_input: bool,
    latex_group_size: int = 3,
    uncertainty_digits: int | None = None,
    zero_uncertainty_mantissa_decimals: int | None = None,
) -> str:
    """Public wrapper for LaTeX file-only numeric formatting."""
    # Non-finite inputs cannot be typeset numerically — int(mp.floor(nan)) deep in
    # the fixed-place formatter raises and would discard an otherwise-successful
    # table. An undefined sigma degrades to a bare value; an undefined value
    # becomes a parse-safe literal cell (works in both S and dcolumn columns).
    if sigma is not None and not mp.isfinite(mp.mpf(sigma)):
        sigma = None
    if not mp.isfinite(mp.mpf(value)):
        return siunitx_safe_cell(str(mp.nstr(mp.mpf(value))), align="c")
    return _format_value_for_latex_file(
        value=value,
        sigma=sigma,
        use_dcolumn=use_dcolumn,
        latex_input_decimals=latex_input_decimals,
        is_input=is_input,
        latex_group_size=latex_group_size,
        uncertainty_digits=uncertainty_digits,
        zero_uncertainty_mantissa_decimals=zero_uncertainty_mantissa_decimals,
    )
