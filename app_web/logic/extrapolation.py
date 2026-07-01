from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import mpmath as mp

from .._security_shim import (
    compile_latex_safe,
    mpmath_synchronized,
    validate_latex_engine,
)

from datalab_core.extrapolation import (
    build_extrapolation_request,
    extrapolation_payload_to_results,
    extrapolation_payload_to_rows,
)
from datalab_core.results import ResultStatus
from datalab_core.service_factory import create_core_session_service
from data_extrapolation_latex_latest import ExtrapolationOptions, _precision_guard, generate_latex_table
from extrapolation_methods import PowerLawConfig
from shared.extrapolation_engine import parse_extrapolation_string
from shared.formula_export import inline_formula_summary_or_none

from .common import (
    _core_failure_message,
    _encode_b64,
    _format_rows,
    _generate_csv_from_rows,
    _is_checked,
    _parse_float,
    _parse_int,
)
from .plots import _render_extrapolation_plot


def _formula_summary_line(formula_summary: object | None) -> str | None:
    inline_formula = inline_formula_summary_or_none(formula_summary)
    if inline_formula is None:
        return None
    return f"Formula: {inline_formula}"


def _insert_formula_summary(tex: str, formula_line: str) -> str:
    document_anchor = "\\begin{document}"
    if document_anchor in tex:
        return tex.replace(document_anchor, f"{document_anchor}\n{formula_line}\n", 1)
    table_anchor = "\\begin{table}"
    if table_anchor in tex:
        return tex.replace(table_anchor, f"{formula_line}\n\n{table_anchor}", 1)
    raise ValueError("Extrapolation LaTeX output has no document/table anchor for formula summary.")


@dataclass
class ExtrapolationResultBundle:
    headers: list[str]
    rows: list[tuple[mp.mpf, ...]]
    results: list[object]
    formatted_rows: list[dict[str, object]]
    latex_text: str
    pdf_b64: str | None
    plot_b64_list: list[str | None] | None
    csv_data: str | None
    warnings: list[str]
    method: str
    caption: str | None
    mp_precision: int | None


def _render_latex(
    headers: list[str],
    rows: list[tuple[mp.mpf, ...]],
    results: list,
    *,
    caption: str | None,
    latex_precision: int | None,
    latex_group_size: int,
    use_dcolumn: bool,
    result_digits: int | None,
    formula_summary: object | None = None,
) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "extrapolation.tex"
        generate_latex_table(
            headers,
            rows,
            results,
            tex_path,
            caption=caption,
            precision=latex_precision,
            verbose=False,
            use_dcolumn=use_dcolumn,
            table_segments=None,
            result_uncertainty_digits=result_digits,
            latex_group_size=latex_group_size,
        )
        tex = tex_path.read_text(encoding="utf-8")
    formula_line = _formula_summary_line(formula_summary)
    if formula_line is None:
        return tex
    return _insert_formula_summary(tex, formula_line)


def _build_power_config(form, mp_precision: int | None) -> PowerLawConfig:
    x1 = form.get("x1") or "1"
    x2 = form.get("x2") or "2"
    x3 = form.get("x3") or "3"
    exponent_override = form.get("power_exponent") or None
    initial_guess = form.get("power_seed") or None
    seed_guesses_raw = (form.get("power_seed_guesses") or "").strip()
    seed_guesses = None
    if seed_guesses_raw:
        seed_guesses = [token for token in re.split(r"[,\s]+", seed_guesses_raw) if token]
    return PowerLawConfig(
        x_values=[x1, x2, x3],
        precision=mp_precision or 80,
        exponent_override=exponent_override,
        initial_guess=initial_guess or 1.0,
        seed_guesses=seed_guesses,
    )


def _power_config_payload(power_config: PowerLawConfig | None) -> dict[str, object] | None:
    if power_config is None:
        return None
    payload: dict[str, object] = {
        "x_values": [str(value) for value in power_config.x_values],
        "precision": str(power_config.precision),
        "initial_guess": str(power_config.initial_guess),
    }
    if power_config.exponent_override not in (None, ""):
        payload["exponent_override"] = str(power_config.exponent_override)
    if power_config.seed_guesses:
        payload["seed_guesses"] = [str(value) for value in power_config.seed_guesses]
    return payload


def _method_options_payload(
    *,
    power_config: PowerLawConfig | None,
    reference_column: str | None,
    levin_variant: str,
    custom_formula: str | None,
    richardson_p: float,
    levin_order: int,
    levin_weight: str,
    levin_beta: float,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "levin_variant": levin_variant,
        "richardson_p": str(richardson_p),
        "levin_order": levin_order,
        "levin_weight": levin_weight,
        "levin_beta": str(levin_beta),
    }
    if reference_column:
        payload["uncertainty_column"] = reference_column
    if custom_formula:
        payload["custom_formula"] = custom_formula
    power_payload = _power_config_payload(power_config)
    if power_payload is not None:
        payload["power_law_config"] = power_payload
    return payload


@mpmath_synchronized
def _run_extrapolation(data_text: str, form, lang: str = "zh") -> ExtrapolationResultBundle:
    method = (form.get("method") or "power_law").strip()
    mp_precision = _parse_int(form.get("mp_precision"))
    latex_precision = _parse_int(form.get("latex_precision"))
    latex_group_size = _parse_int(form.get("latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    result_digits = _parse_int(form.get("result_digits"))
    if result_digits is None:
        result_digits = 1
    reference_mode = (form.get("reference_column_mode") or "").strip()
    reference_column_raw = (form.get("reference_column") or "").strip()
    reference_column = "auto_max_diff" if reference_mode.lower() == "auto_max_diff" else (reference_column_raw or None)
    caption_text = (form.get("caption") or "").strip()
    use_caption = _is_checked(form, "use_caption", default=False) if "use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    use_dcolumn = _is_checked(form, "use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "compile_pdf", default=False)
    latex_engine = (form.get("latex_engine") or "xelatex").strip() or "xelatex"
    # Dynamic (ui_specs) fields may use shorter names; keep legacy names as fallback.
    levin_variant = (form.get("variant") or form.get("levin_variant") or "u").strip() or "u"
    richardson_p = _parse_float(form.get("p"))
    if richardson_p is None:
        richardson_p = 2.0
    levin_order = _parse_int(form.get("order"))
    if levin_order is None:
        levin_order = 2
    levin_weight = (form.get("weight") or "default").strip() or "default"
    levin_beta = _parse_float(form.get("beta"))
    if levin_beta is None:
        levin_beta = 1.0
    custom_formula = (form.get("custom_formula") or "").strip() or None

    accelerators = {"richardson", "shanks", "levin_u", "wynn_epsilon"}
    if mp_precision is None and (method in accelerators or method == "power_law"):
        mp_precision = 80

    power_config = _build_power_config(form, mp_precision) if method == "power_law" else None

    options = ExtrapolationOptions(
        method=method,
        power_law_config=power_config,
        uncertainty_column=reference_column,
        mp_precision=mp_precision,
        levin_variant=levin_variant,
        custom_formula=custom_formula,
        uncertainty_digits=result_digits,
        richardson_p=richardson_p,
        levin_order=levin_order,
        levin_weight=levin_weight,
        levin_beta=levin_beta,
    )
    with _precision_guard(mp_precision) as applied_precision:
        headers, parsed_rows = parse_extrapolation_string(
            data_text,
            verbose=False,
            options=options,
        )
        method_options = _method_options_payload(
            power_config=power_config,
            reference_column=reference_column,
            levin_variant=levin_variant,
            custom_formula=custom_formula,
            richardson_p=richardson_p,
            levin_order=levin_order,
            levin_weight=levin_weight,
            levin_beta=levin_beta,
        )
        request = build_extrapolation_request(
            headers=headers,
            rows=parsed_rows,
            method=method,
            method_options=method_options,
            precision_digits=applied_precision,
            uncertainty_digits=result_digits,
            request_id="web-extrapolation",
        )
        core_result = create_core_session_service().submit(request)
        if core_result.status is not ResultStatus.SUCCEEDED:
            raise ValueError(_core_failure_message(core_result.payload, "Extrapolation failed."))
        data_rows = extrapolation_payload_to_rows(core_result.payload)
        raw_results = extrapolation_payload_to_results(core_result.payload)
        warnings = [*options.warnings, *core_result.warnings]
    latex_text = _render_latex(
        headers,
        data_rows,
        raw_results,
        caption=caption,
        latex_precision=latex_precision,
        latex_group_size=latex_group_size,
        use_dcolumn=use_dcolumn,
        result_digits=result_digits,
        formula_summary=custom_formula if method == "custom" else None,
    )
    formatted_rows = _format_rows(headers, data_rows, raw_results, digits=12, uncertainty_digits=result_digits, mp_precision=mp_precision)

    # Generate plots if requested
    generate_plots = _is_checked(form, "generate_plots", default=False)
    plot_b64_list = None
    if generate_plots and data_rows and raw_results:
        plot_b64_list = []
        for idx, (row, result) in enumerate(zip(data_rows, raw_results), 1):
            try:
                extrap_val = result.value if hasattr(result, "value") else result
                extrap_sigma = result.uncertainty if hasattr(result, "uncertainty") else mp.mpf("0")
                plot_bytes = _render_extrapolation_plot(row, extrap_val, extrap_sigma, idx, lang=lang)
                if plot_bytes:
                    plot_b64_list.append(_encode_b64(plot_bytes))
                else:
                    plot_b64_list.append(None)
            except Exception:
                plot_b64_list.append(None)

    pdf_b64 = None
    if compile_pdf:
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, warnings, "extrapolation")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    csv_data = _generate_csv_from_rows(formatted_rows) if formatted_rows else None

    return ExtrapolationResultBundle(
        headers=headers,
        rows=data_rows,
        results=raw_results,
        formatted_rows=formatted_rows,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
        plot_b64_list=plot_b64_list,
        csv_data=csv_data,
        warnings=warnings,
        method=method,
        caption=caption,
        mp_precision=mp_precision,
    )
