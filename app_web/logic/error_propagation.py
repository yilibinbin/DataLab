from __future__ import annotations

import json
from collections.abc import Mapping
import tempfile
from dataclasses import dataclass
from pathlib import Path

import mpmath as mp

from .._security_shim import (
    compile_latex_safe,
    mpmath_synchronized,
    validate_latex_engine,
)

from datalab_core.results import ResultStatus
from datalab_core.service_factory import create_core_session_service
from datalab_core.uncertainty import (
    build_uncertainty_request,
    normalize_uncertainty_propagation_config,
    uncertainty_payload_to_results,
)
from data_extrapolation_latex_latest import (
    _precision_guard,
    detect_used_error_propagation_inputs,
    format_result_with_uncertainty_latex,
    generate_error_propagation_table,
    process_constants_string,
    process_uncertainty_string,
)

from .common import (
    _encode_b64,
    _format_with_precision,
    _generate_csv_from_rows,
    _is_checked,
    _latex_to_plain,
    _parse_int,
    _parse_precision,
)
from .plots import _render_contribution_plot, _render_monte_carlo_distribution_plot


@dataclass
class ErrorPropagationBundle:
    headers: list[str]
    rows: list[list[object]]
    results: list[object]
    formatted_rows: list[dict[str, object]]
    latex_text: str
    pdf_b64: str | None
    plot_b64: str | None
    plot_b64_list: list[str] | None
    csv_data: str | None
    warnings: list[str]
    formula: str
    mp_precision: int | None


def _form_text(form, name: str) -> str:
    value = form.get(name) if hasattr(form, "get") else None
    return str(value or "").strip()


def _reject_active_units_on_web(form) -> None:
    raw_config = _form_text(form, "error_units_config")
    if raw_config:
        try:
            parsed = json.loads(raw_config)
        except json.JSONDecodeError as exc:
            raise ValueError("unit_evaluation_unsupported_on_web") from exc
        if isinstance(parsed, Mapping):
            enabled = bool(parsed.get("enabled"))
            mode = str(parsed.get("mode") or "display_only").strip()
            if enabled and mode != "display_only":
                raise ValueError("unit_evaluation_unsupported_on_web")
    mode = _form_text(form, "error_units_mode")
    enabled = _is_checked(form, "error_units_enabled", default=False)
    if enabled and (mode or "display_only") != "display_only":
        raise ValueError("unit_evaluation_unsupported_on_web")


def _format_uncertain_value(uv, digits: int = 10, uncertainty_digits: int | None = None) -> str:
    """Format an UncertainValue-like object using GUI-style uncertainty notation."""
    val = getattr(uv, "value", uv)
    sigma = getattr(uv, "uncertainty", 0)
    latex = format_result_with_uncertainty_latex(val, sigma, uncertainty_digits)
    return _latex_to_plain(latex)


def _format_uncertainty_rows(
    headers: list[str],  # noqa: ARG001 - kept for backward compatibility
    rows: list[list[object]],
    results: list[object],
    digits: int = 10,  # noqa: ARG001 - kept for backward compatibility
    uncertainty_digits: int | None = None,
    mp_precision: int | None = None,
) -> list[dict[str, object]]:
    """Format error propagation results as 3-column format."""
    formatted: list[dict[str, object]] = []
    for idx, (_row, res) in enumerate(zip(rows, results), 1):
        val = getattr(res, "value", res)
        sigma = getattr(res, "uncertainty", mp.mpf("0"))
        latex = format_result_with_uncertainty_latex(val, sigma, uncertainty_digits)
        formatted.append(
            {
                "index": idx,
                "value": _format_with_precision(val, mp_precision),
                "uncertainty": _format_with_precision(sigma, mp_precision),
                "latex": _latex_to_plain(latex) if latex else "",
            }
        )
    return formatted


def _render_error_latex(
    headers: list[str],
    parsed_data: list[list[object]],
    results: list[object],
    constants: dict,
    formula: str,
    *,
    caption: str | None,
    latex_precision: int | None,
    latex_group_size: int,
    use_dcolumn: bool,
    result_digits: int | None,
    used_columns: list[str] | None,
) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "error.tex"
        generate_error_propagation_table(
            headers,
            parsed_data,
            results,
            constants,
            formula,
            tex_path,
            caption=caption,
            verbose=False,
            use_dcolumn=use_dcolumn,
            table_segments=None,
            precision=latex_precision,
            result_uncertainty_digits=result_digits,
            used_columns=used_columns,
            latex_group_size=latex_group_size,
        )
        return tex_path.read_text(encoding="utf-8")


def _should_collect_monte_carlo_distribution(
    *,
    propagation_method: str,
    propagation_order: int,
    mc_samples: int | None,
    mc_seed: int | None,
    generate_plots: bool,
) -> bool:
    if not generate_plots:
        return False
    try:
        propagation = normalize_uncertainty_propagation_config(
            method=propagation_method,
            order=propagation_order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
        )
    except Exception:
        return False
    method = propagation.get("method") if isinstance(propagation, Mapping) else None
    return method == "monte_carlo"


@mpmath_synchronized
def _run_error_propagation(data_text: str, constants_text: str, form, lang: str = "zh") -> ErrorPropagationBundle:
    _reject_active_units_on_web(form)
    mp_precision = _parse_precision(form.get("error_mp_precision"))
    latex_precision = _parse_int(form.get("error_latex_precision"))
    latex_group_size = _parse_int(form.get("error_latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    result_digits = _parse_int(form.get("error_result_digits"))
    if result_digits is None:
        result_digits = 1
    use_dcolumn = _is_checked(form, "error_use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "error_compile_pdf", default=False)
    latex_engine = (form.get("error_latex_engine") or "xelatex").strip() or "xelatex"
    constants_enabled = _is_checked(form, "error_constants_enabled", default=False)
    caption_text = (form.get("error_caption") or "").strip()
    use_caption = _is_checked(form, "error_use_caption", default=False) if "error_use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    formula = (form.get("error_formula") or "").strip()
    propagation_method = (form.get("error_propagation_method") or "taylor").strip() or "taylor"
    propagation_order = _parse_int(form.get("error_propagation_order"))
    if propagation_order is None:
        propagation_order = 1
    mc_samples = _parse_int(form.get("error_mc_samples"))
    mc_seed = _parse_int(form.get("error_mc_seed"))
    generate_plots = _is_checked(form, "error_generate_plots", default=False)

    warnings: list[str] = []
    with _precision_guard(mp_precision):
        headers, parsed_data = process_uncertainty_string(data_text, verbose=False)
        constants = {}
        if constants_enabled:
            constants = process_constants_string(constants_text, verbose=False)
        used_headers, used_constants = detect_used_error_propagation_inputs(headers, constants, formula)
        constants_used = {name: constants[name] for name in used_constants if name in constants}
        request = build_uncertainty_request(
            headers=headers,
            rows=parsed_data,
            formula=formula,
            constants=constants_used,
            propagation_method=propagation_method,
            propagation_order=propagation_order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
            collect_monte_carlo_distribution=_should_collect_monte_carlo_distribution(
                propagation_method=propagation_method,
                propagation_order=propagation_order,
                mc_samples=mc_samples,
                mc_seed=mc_seed,
                generate_plots=generate_plots,
            ),
            precision_digits=mp_precision,
            uncertainty_digits=result_digits,
            request_id="web-uncertainty",
        )
        core_result = create_core_session_service().submit(request)
        if core_result.status is not ResultStatus.SUCCEEDED:
            message = str(core_result.payload.get("message") or "Error propagation failed.")
            raise ValueError(message)
        results = uncertainty_payload_to_results(core_result.payload)
        warnings.extend(core_result.warnings)
        latex_text = _render_error_latex(
            headers,
            parsed_data,
            results,
            constants_used,
            formula,
            caption=caption,
            latex_precision=latex_precision,
            latex_group_size=latex_group_size,
            use_dcolumn=use_dcolumn,
            result_digits=result_digits,
            used_columns=used_headers,
        )
        formatted_rows = _format_uncertainty_rows(
            headers,
            parsed_data,
            results,
            digits=12,
            uncertainty_digits=result_digits,
            mp_precision=mp_precision,
        )

    plot_b64 = None
    plot_b64_list = None
    if generate_plots:
        encoded_plots: list[str] = []
        plot_bytes = _render_contribution_plot(results, lang=lang)
        if plot_bytes:
            encoded_plots.append(_encode_b64(plot_bytes))
        for idx, result in enumerate(results, 1):
            distribution_summary = getattr(result, "monte_carlo_distribution", None)
            if not distribution_summary:
                continue
            distribution_plot = _render_monte_carlo_distribution_plot(
                distribution_summary,
                lang=lang,
                row_index=idx,
            )
            if distribution_plot:
                encoded_plots.append(_encode_b64(distribution_plot))
        if encoded_plots:
            plot_b64_list = encoded_plots
            plot_b64 = encoded_plots[0]

    pdf_b64 = None
    if compile_pdf:
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, warnings, "error")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    csv_data = _generate_csv_from_rows(formatted_rows) if formatted_rows else None

    return ErrorPropagationBundle(
        headers=headers,
        rows=parsed_data,
        results=results,
        formatted_rows=formatted_rows,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
        plot_b64=plot_b64,
        plot_b64_list=plot_b64_list,
        csv_data=csv_data,
        warnings=warnings,
        formula=formula,
        mp_precision=mp_precision,
    )
