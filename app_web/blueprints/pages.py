from __future__ import annotations

from flask import Blueprint, flash, render_template, request

from .._security_shim import csrf_protect
from ..logic.common import (
    _extract_data_text,
    _extract_named_text,
    _is_checked,
)
from .utils import get_lang


bp = Blueprint("pages", __name__)


SAMPLE_DATA = """A B C
-0.750000   -0.702321   -0.680145
-0.500000   -0.476901   -0.461822
-0.250000   -0.235440   -0.228512
0.000000    -0.010130   -0.006572
"""

SAMPLE_UNCERT_DATA = """E1 E2 E3
1.0000(5)   0.8000(4)   0.7000(2)
1.2000(5)   0.9500(4)   0.8200(3)
"""

SAMPLE_CONSTANTS = """ALPHA 7.2973525693(11)[-3]
BETA 1.0000(5)
"""

SAMPLE_FIT_DATA = """x y
1.0  2.1(5)
2.0  4.2(5)
3.0  6.0(5)
4.0  7.8(6)
5.0  10.1(8)
"""

SAMPLE_STATS_DATA = """A
1152842742.723(12)
1152842742.740(18)
1152842742.727(14)
1152842742.721(9)
"""


def _error_key_for_exception(exc: Exception) -> str:
    msg = str(exc) or ""
    msg_lower = msg.lower()
    if "utf-8" in msg_lower or "decode" in msg_lower:
        return "errors.file_parse_failed"
    if "formula" in msg_lower or "parse" in msg_lower or "解析" in msg:
        return "errors.formula_parse_failed"
    if (
        "requires all x > 0" in msg_lower
        or "requires all y > 0" in msg_lower
        or "x > 0" in msg_lower
        or "y > 0" in msg_lower
    ):
        return "errors.non_positive_log_axis"
    return "errors.compute_failed"


def _run_extrapolation(raw_text, form, *, lang: str):
    from ..logic.extrapolation import _run_extrapolation as run

    return run(raw_text, form, lang=lang)


def _run_error_propagation(data_text, const_text, form, *, lang: str):
    from ..logic.error_propagation import _run_error_propagation as run

    return run(data_text, const_text, form, lang=lang)


def _run_fit(data_text, form):
    from ..logic.fitting import _run_fit as run

    return run(data_text, form)


def _run_statistics(data_text, form, *, lang: str):
    from ..logic.statistics import _run_statistics as run

    return run(data_text, form, lang=lang)


@bp.route("/", methods=["GET", "POST"])
@csrf_protect
def index():
    selected_method = request.form.get("method", "power_law")
    use_file_checked = _is_checked(request.form, "use_file", False)
    context: dict[str, object] = {
        "sample_data": SAMPLE_DATA.strip(),
        "result": None,
        "warnings": [],
        "active_page": "extrapolation",
        "use_dcolumn_checked": _is_checked(request.form, "use_dcolumn", True),
        "use_caption_checked": _is_checked(request.form, "use_caption", False),
        "compile_pdf_checked": _is_checked(request.form, "compile_pdf", False),
        "generate_plots_checked": _is_checked(request.form, "generate_plots", False),
        "latex_engine_value": request.form.get("latex_engine", ""),
        "use_file_checked": use_file_checked,
        "selected_method": selected_method,
    }
    if request.method == "POST":
        form = request.form
        try:
            raw_text = _extract_data_text(form, request.files, allow_file=use_file_checked)
        except ValueError:
            flash("i18n:errors.file_parse_failed", "error")
            return render_template("index.html", **context)
        if not raw_text:
            flash("i18n:errors.missing_data", "error")
            return render_template("index.html", **context)
        try:
            lang = get_lang()
            result = _run_extrapolation(raw_text, form, lang=lang)
            context.update(result=result, warnings=result.warnings)
        except Exception as exc:  # pragma: no cover - defensive path for UI
            flash(f"i18n:{_error_key_for_exception(exc)}", "error")
    return render_template("index.html", **context)


@bp.route("/error", methods=["GET", "POST"])
@csrf_protect
def error():
    use_file_checked = _is_checked(request.form, "error_use_file", False)
    constants_enabled = _is_checked(request.form, "error_constants_enabled", False)
    constants_use_file = _is_checked(request.form, "constants_use_file", False)
    context: dict[str, object] = {
        "sample_data": SAMPLE_UNCERT_DATA.strip(),
        "sample_constants": SAMPLE_CONSTANTS.strip(),
        "result": None,
        "warnings": [],
        "active_page": "error",
        "use_dcolumn_checked": _is_checked(request.form, "error_use_dcolumn", True),
        "use_caption_checked": _is_checked(request.form, "error_use_caption", False),
        "compile_pdf_checked": _is_checked(request.form, "error_compile_pdf", False),
        "generate_plots_checked": _is_checked(request.form, "error_generate_plots", False),
        "latex_engine_value": request.form.get("error_latex_engine", ""),
        "use_file_checked": use_file_checked,
        "constants_enabled_checked": constants_enabled,
        "constants_use_file_checked": constants_use_file,
    }
    if request.method == "POST":
        form = request.form
        try:
            data_text = _extract_named_text(
                "uncert_data_text",
                "uncert_data_file",
                form,
                request.files,
                allow_file=use_file_checked,
            )
            const_text = _extract_named_text(
                "constants_text",
                "constants_file",
                form,
                request.files,
                allow_file=constants_enabled and constants_use_file,
            )
        except ValueError:
            flash("i18n:errors.file_parse_failed", "error")
            return render_template("error.html", **context)
        if not data_text:
            flash("i18n:errors.missing_uncertainty_data", "error")
            return render_template("error.html", **context)
        if not (form.get("error_formula") or "").strip():
            flash("i18n:errors.missing_formula", "error")
            return render_template("error.html", **context)
        try:
            lang = get_lang()
            result = _run_error_propagation(data_text, const_text, form, lang=lang)
            context.update(result=result, warnings=result.warnings)
        except Exception as exc:  # pragma: no cover - defensive path for UI
            flash(f"i18n:{_error_key_for_exception(exc)}", "error")
    return render_template("error.html", **context)


@bp.route("/fit", methods=["GET", "POST"])
@csrf_protect
def fit():
    use_file_checked = _is_checked(request.form, "fit_use_file", False)
    fit_mode = request.form.get("fit_mode", "polynomial")
    weighted_checked = _is_checked(request.form, "fit_weighted", False)
    context: dict[str, object] = {
        "sample_data": SAMPLE_FIT_DATA.strip(),
        "result": None,
        "warnings": [],
        "active_page": "fit",
        "use_file_checked": use_file_checked,
        "fit_mode": fit_mode,
        "fit_weighted": weighted_checked,
        "use_dcolumn_checked": _is_checked(request.form, "fit_use_dcolumn", True),
        "use_caption_checked": _is_checked(request.form, "fit_use_caption", False),
        "compile_pdf_checked": _is_checked(request.form, "fit_compile_pdf", False),
        "latex_engine_value": request.form.get("fit_latex_engine", ""),
        "fit_generate_plots_checked": _is_checked(request.form, "fit_generate_plots", False),
    }
    if request.method == "POST":
        form = request.form
        try:
            data_text = _extract_named_text(
                "fit_data_text",
                "fit_data_file",
                form,
                request.files,
                allow_file=use_file_checked,
            )
        except ValueError:
            flash("i18n:errors.file_parse_failed", "error")
            return render_template("fit.html", **context)
        if not data_text:
            flash("i18n:errors.missing_fit_data", "error")
            return render_template("fit.html", **context)
        try:
            result = _run_fit(data_text, form)
            context.update(result=result, warnings=result.warnings)
        except Exception as exc:  # pragma: no cover
            flash(f"i18n:{_error_key_for_exception(exc)}", "error")
    return render_template("fit.html", **context)


@bp.route("/stats", methods=["GET", "POST"])
@csrf_protect
def stats():
    use_file_checked = _is_checked(request.form, "stats_use_file", False)
    context: dict[str, object] = {
        "sample_data": SAMPLE_STATS_DATA.strip(),
        "result": None,
        "warnings": [],
        "active_page": "stats",
        "use_dcolumn_checked": _is_checked(request.form, "stats_use_dcolumn", True),
        "use_caption_checked": _is_checked(request.form, "stats_use_caption", False),
        "compile_pdf_checked": _is_checked(request.form, "stats_compile_pdf", False),
        "generate_plots_checked": _is_checked(request.form, "stats_generate_plots", False),
        "latex_engine_value": request.form.get("stats_latex_engine", ""),
        "use_file_checked": use_file_checked,
        "stats_use_sample": _is_checked(request.form, "stats_use_sample", False),
        "stats_use_weighted_variance": _is_checked(request.form, "stats_use_weighted_variance", False),
    }
    if request.method == "POST":
        form = request.form
        try:
            data_text = _extract_named_text(
                "stats_data_text",
                "stats_data_file",
                form,
                request.files,
                allow_file=use_file_checked,
            )
        except ValueError:
            flash("i18n:errors.file_parse_failed", "error")
            return render_template("stats.html", **context)
        if not data_text:
            flash("i18n:errors.missing_data", "error")
            return render_template("stats.html", **context)
        try:
            lang = get_lang()
            result = _run_statistics(data_text, form, lang=lang)
            context.update(result=result, warnings=result.warnings)
        except Exception as exc:  # pragma: no cover
            flash(f"i18n:{_error_key_for_exception(exc)}", "error")
    return render_template("stats.html", **context)
