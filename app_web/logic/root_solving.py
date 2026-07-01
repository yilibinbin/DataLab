from __future__ import annotations

from dataclasses import dataclass

from .._security_shim import mpmath_synchronized
from datalab_core.results import ResultStatus
from datalab_core.root_solving import build_root_solving_request, root_batch_payload_to_result
from datalab_core.service_factory import create_core_session_service

from data_extrapolation_latex_latest import (
    _dual_msg,
    _precision_guard,
    format_result_with_uncertainty_latex,
)

from .common import (
    _core_failure_message,
    _format_number,
    _latex_to_plain,
    _parse_int,
)


# Web MVP exposes the single-equation ("scalar") and system ("system") solves.
# The desktop's polynomial / scan_multiple modes and the units / constants /
# scan-config panels are intentionally out of scope for this subset.
_MODE_CHOICES = ("scalar", "system")
_UNCERTAINTY_METHODS = ("off", "taylor", "monte_carlo")


@dataclass
class RootRow:
    name: str
    value: str
    uncertainty: str
    latex: str


@dataclass
class RootSolvingResultBundle:
    mode: str
    backend: str
    roots: list[RootRow]
    latex_text: str
    warnings: list[str]
    failure: str | None
    mp_precision: int | None


def _parse_equations(text: str) -> list[str]:
    equations = [line.strip() for line in text.splitlines() if line.strip()]
    if not equations:
        raise ValueError(
            _dual_msg(
                "请至少输入一个方程（每行一个）。",
                "Please enter at least one equation (one per line).",
            )
        )
    return equations


def _parse_unknowns(text: str) -> list[dict[str, str]]:
    """Parse ``name = guess`` (or ``name guess``) lines into unknown rows."""
    rows: list[dict[str, str]] = []
    for line_num, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if "=" in line:
            name_part, guess_part = line.split("=", 1)
        else:
            parts = line.split()
            if len(parts) < 2:
                raise ValueError(
                    _dual_msg(
                        f"第 {line_num} 行未知量格式无效：需要 名称 = 初值。",
                        f"Invalid unknown on line {line_num}: expected name = guess.",
                    )
                )
            name_part, guess_part = parts[0], parts[1]
        name = name_part.strip()
        guess = guess_part.strip()
        if not name:
            raise ValueError(
                _dual_msg(
                    f"第 {line_num} 行未知量名称为空。",
                    f"Unknown name is empty on line {line_num}.",
                )
            )
        rows.append({"name": name, "initial": guess, "source": "manual"})
    if not rows:
        raise ValueError(
            _dual_msg(
                "请至少输入一个未知量（如 x = 1）。",
                "Please enter at least one unknown (e.g. x = 1).",
            )
        )
    return rows


def _build_uncertainty_options(form) -> dict[str, object]:
    method = (form.get("root_uncertainty_method") or "off").strip()
    if method not in _UNCERTAINTY_METHODS:
        method = "off"
    return {
        "method": method,
        "taylor_order": 1,
        "monte_carlo_samples": 2000,
        "monte_carlo_seed": "",
    }


def _root_latex(name: str, value_text: str, uncertainty, uncertainty_digits: int) -> str:
    if uncertainty is not None:
        latex = format_result_with_uncertainty_latex(value_text, uncertainty, uncertainty_digits)
        if latex:
            return _latex_to_plain(f"{name} = {latex}")
    return f"{name} = {value_text}"


@mpmath_synchronized
def _run_root_solving(form, lang: str = "zh") -> RootSolvingResultBundle:
    mp_precision = _parse_int(form.get("root_mp_precision"))
    display_digits = _parse_int(form.get("root_display_digits")) or 12
    uncertainty_digits = _parse_int(form.get("root_uncertainty_digits"))
    if uncertainty_digits is None:
        uncertainty_digits = 1
    mode = (form.get("root_mode") or "scalar").strip()
    if mode not in _MODE_CHOICES:
        mode = "scalar"

    equations = _parse_equations(form.get("root_equations") or "")
    unknown_rows = _parse_unknowns(form.get("root_unknowns") or "")
    uncertainty_options = _build_uncertainty_options(form)

    with _precision_guard(mp_precision) as applied_precision:
        try:
            request = build_root_solving_request(
                equations=equations,
                unknown_rows=unknown_rows,
                mode=mode,
                uncertainty_options=uncertainty_options,
                precision_digits=applied_precision,
                display_digits=display_digits,
                uncertainty_digits=uncertainty_digits,
                request_id="web-root-solving",
            )
        except Exception as exc:  # noqa: BLE001 - preserve the web form error boundary.
            raise ValueError(str(exc)) from exc
        try:
            core_result = create_core_session_service().submit(request)
        except Exception as exc:  # noqa: BLE001 - preserve the web form error boundary.
            raise ValueError(str(exc)) from exc
        if core_result.status is not ResultStatus.SUCCEEDED:
            raise ValueError(_core_failure_message(core_result.payload, "Root solving failed."))

        batch = root_batch_payload_to_result(core_result.payload["batch"])
        warnings = [str(value) for value in core_result.warnings]

        roots: list[RootRow] = []
        backend = ""
        failure: str | None = None
        for row in batch.rows:
            warnings.extend(str(value) for value in row.warnings)
            if row.failure is not None:
                failure = row.failure
                continue
            if row.result is None:
                continue
            backend = backend or str(row.result.backend)
            warnings.extend(str(value) for value in row.result.warnings)
            for root in row.result.roots:
                value_text = _format_number(root.value, display_digits)
                uncertainty_text = (
                    _format_number(root.uncertainty, display_digits)
                    if root.uncertainty is not None
                    else ""
                )
                roots.append(
                    RootRow(
                        name=root.name,
                        value=value_text,
                        uncertainty=uncertainty_text,
                        latex=_root_latex(root.name, value_text, root.uncertainty, uncertainty_digits),
                    )
                )

    if not roots and failure is None:
        failure = _dual_msg("未找到根。", "No roots found.")

    latex_text = "\n".join(root.latex for root in roots)

    return RootSolvingResultBundle(
        mode=mode,
        backend=backend,
        roots=roots,
        latex_text=latex_text,
        warnings=warnings,
        failure=failure,
        mp_precision=mp_precision,
    )
