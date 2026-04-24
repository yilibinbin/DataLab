"""Linear basis models used for automatic fitting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from mpmath import mp

from shared.numerics import noise_floor
from shared.precision import precision_guard

from .hp_fitter import FitResult, combine_error_components


@dataclass
class AutoModelDefinition:
    identifier: str
    label: str
    basis_functions: list[Callable[[mp.mpf], mp.mpf]]
    basis_texts: list[str]
    parameter_names: list[str]
    requires_positive_x: bool = False


@dataclass
class _LinearFitComputation:
    params: dict[str, mp.mpf]
    stat_errors: dict[str, mp.mpf]
    chi2: mp.mpf
    reduced_chi2: mp.mpf
    aic: mp.mpf
    bic: mp.mpf
    r2: mp.mpf
    rmse: mp.mpf
    residuals: list[mp.mpf]
    fitted_curve: list[mp.mpf]
    covariance: list[list[mp.mpf]]
    details: dict[str, object]


def _power_series_basis(max_power: int) -> tuple[list[Callable[[mp.mpf], mp.mpf]], list[str]]:
    basis = []
    texts = []
    for power in range(max_power + 1):
        if power == 0:
            basis.append(lambda x: mp.mpf("1"))
        else:
            basis.append(lambda x, p=power: mp.power(x, p))
        if power == 0:
            texts.append("1")
        elif power == 1:
            texts.append("x")
        else:
            texts.append(f"x^{power}")
    return basis, texts


def _inverse_basis():
    return (
        [lambda x: mp.mpf("1"), lambda x: mp.mpf("1") / x, lambda x: mp.mpf("1") / (x * x)],
        ["1", "1/x", "1/x^2"],
    )


def _log_basis():
    return ([lambda x: mp.mpf("1"), lambda x: mp.log(x)], ["1", "ln(x)"])


def _log_poly_basis():
    return (
        [lambda x: mp.mpf("1"), lambda x: mp.log(x), lambda x: mp.power(mp.log(x), 2)],
        ["1", "ln(x)", "ln(x)^2"],
    )


def _fractional_decay_basis():
    return (
        [lambda x: mp.power(x, -3), lambda x: mp.power(x, -4), lambda x: mp.power(x, -5)],
        ["x^{-3}", "x^{-4}", "x^{-5}"],
    )


def _exponential_combo_basis():
    return (
        [lambda x: mp.e ** (-x), lambda x: mp.e ** (-mp.mpf("0.5") * x), lambda x: mp.mpf("1")],
        ["e^{-x}", "e^{-0.5x}", "1"],
    )


def _exponential_flexible_basis():
    return (
        [lambda x: mp.e ** x, lambda x: x * (mp.e ** x), lambda x: mp.mpf("1")],
        ["e^{x}", "x e^{x}", "1"],
    )


def _spline_decay_basis():
    return (
        [lambda x: mp.mpf("1"), lambda x: mp.mpf("1") / (x**3), lambda x: mp.mpf("1") / (x**4), lambda x: mp.mpf("1") / (x**5)],
        ["1", "1/x^3", "1/x^4", "1/x^5"],
    )


basis1, texts1 = _power_series_basis(1)
basis2, texts2 = _power_series_basis(2)
basis3, texts3 = _power_series_basis(3)

AUTO_MODELS = [
    AutoModelDefinition("M1", "线性 / Linear", basis1, texts1, ["b0", "b1"]),
    AutoModelDefinition("M2", "二次多项式 / Quadratic", basis2, texts2, ["b0", "b1", "b2"]),
    AutoModelDefinition("M3", "三次多项式 / Cubic", basis3, texts3, ["b0", "b1", "b2", "b3"]),
    AutoModelDefinition("M4", "对数模型 / Log model", *_log_basis(), ["a", "b"], requires_positive_x=True),
    AutoModelDefinition("M4B", "对数多项式 / Log polynomial", *_log_poly_basis(), ["a", "b", "c"], requires_positive_x=True),
    AutoModelDefinition("M5", "x^-1 级数 / 1/x series", *_inverse_basis(), ["A", "B", "C"]),
    AutoModelDefinition("M6", "高次衰减 / High-order decay", *_fractional_decay_basis(), ["C1", "C2", "C3"], requires_positive_x=True),
    AutoModelDefinition("M7", "指数组合 / Exponential combo", *_exponential_combo_basis(), ["A", "B", "C"]),
    AutoModelDefinition("M7B", "通用指数基 / Exponential basis", *_exponential_flexible_basis(), ["A", "B", "C"]),
    AutoModelDefinition("M8", "1/x^3~1/x^5 / 1/x^3~1/x^5", *_spline_decay_basis(), ["D0", "D1", "D2", "D3"], requires_positive_x=True),
]


def _expression_text(definition: AutoModelDefinition) -> str:
    terms = [f"{name}*({text})" for name, text in zip(definition.parameter_names, definition.basis_texts)]
    joined = " + ".join(terms)
    return f"f(x) = {joined}"


def _substituted_expression(definition: AutoModelDefinition, coeffs: list[mp.mpf]) -> str:
    parts = []
    for name, coeff, text in zip(definition.parameter_names, coeffs, definition.basis_texts):
        parts.append(f"{mp.nstr(coeff, 8)}*({text})")
    return "f(x) = " + " + ".join(parts)


def build_polynomial_definition(degree: int) -> AutoModelDefinition:
    if degree < 1:
        raise ValueError("多项式阶数至少为 1。/ Polynomial degree must be at least 1.")
    basis, texts = _power_series_basis(degree)
    params = [f"b{i}" for i in range(degree + 1)]
    label = "线性 / Linear" if degree == 1 else f"{degree}阶多项式 / degree-{degree} polynomial"
    identifier = f"POLY{degree}"
    return AutoModelDefinition(identifier, label, basis, texts, params)


def build_inverse_series_definition(min_power: int, max_power: int) -> AutoModelDefinition:
    if min_power < 0 or max_power < 0:
        raise ValueError("1/x^p 展开至少需要 p ≥ 0。/ 1/x^p expansion requires p ≥ 0.")
    if min_power > max_power:
        min_power, max_power = max_power, min_power
    basis = []
    texts = []
    params = []
    for power in range(min_power, max_power + 1):
        basis.append(lambda x, p=power: mp.power(x, -p))
        texts.append(f"1/x^{power}")
        params.append(f"A{power}")
    identifier = f"INV{min_power}_{max_power}"
    label = f"1/x^{min_power}~1/x^{max_power} / 1/x^{min_power}~1/x^{max_power}"
    return AutoModelDefinition(identifier, label, basis, texts, params, requires_positive_x=True)


def fit_linear_model(
    definition: AutoModelDefinition,
    x_data: list[mp.mpf],
    y_data: list[mp.mpf],
    precision: int | None = None,
    weights: list[mp.mpf] | None = None,
    data_sigmas: list[mp.mpf | None] | None = None,
) -> FitResult:
    with precision_guard(precision):
        if len(x_data) != len(y_data):
            raise ValueError("x 与 y 数据点数量必须一致。/ x and y lengths must match.")
        if not x_data:
            raise ValueError("拟合需要至少一个数据点。/ At least one data point is required.")
        x_series = [mp.mpf(x) for x in x_data]
        y_series = [mp.mpf(y) for y in y_data]
        if definition.requires_positive_x and any(value <= 0 for value in x_series):
            raise ValueError("该模型需要所有 x 为正数。/ This model requires all x > 0.")
        rows = len(x_series)
        cols = len(definition.basis_functions)
        weight_vec = None
        if weights:
            if len(weights) != rows:
                raise ValueError("权重数量必须与数据点数量一致。/ Weight count must match number of data points.")
            weight_vec = [mp.mpf(w) for w in weights]
            if any(w <= 0 for w in weight_vec):
                raise ValueError("权重必须为正数。/ Weights must be positive.")

        def _solve(y_targets: list[mp.mpf]) -> _LinearFitComputation:
            if len(y_targets) != rows:
                raise ValueError("目标数据长度必须匹配。/ Target length must match.")
            design = mp.matrix(rows, cols)
            target = mp.matrix(rows, 1)
            for i, x in enumerate(x_series):
                for j, func in enumerate(definition.basis_functions):
                    value = mp.mpf(func(x))
                    design[i, j] = value * (mp.sqrt(weight_vec[i]) if weight_vec else mp.mpf("1"))
                target[i] = mp.mpf(y_targets[i]) * (mp.sqrt(weight_vec[i]) if weight_vec else mp.mpf("1"))
            if rows < cols:
                raise ValueError("数据点数量不足以拟合该模型。/ Not enough data points for this model.")
            try:
                Q, R = mp.qr(design)
            except ZeroDivisionError as exc:
                raise ValueError("QR 分解失败，无法拟合。/ QR decomposition failed, cannot fit.") from exc
            Qt_y = Q.T * target
            R_top = R[:cols, :cols]
            rhs = Qt_y[:cols, :]
            try:
                coeff_matrix = mp.lu_solve(R_top, rhs)
            except ZeroDivisionError as exc:
                raise ValueError("设计矩阵奇异，无法拟合。/ Design matrix is singular, cannot fit.") from exc
            coeffs_mp = [coeff_matrix[i, 0] for i in range(cols)]
            params = {name: coeff for name, coeff in zip(definition.parameter_names, coeffs_mp)}
            evaluator = build_linear_evaluator(definition, params)
            fitted = [evaluator(mp.mpf(x)) for x in x_series]
            residuals_mp = [fitted[i] - mp.mpf(y_targets[i]) for i in range(rows)]
            if weight_vec:
                chi2 = sum(w * (r * r) for w, r in zip(weight_vec, residuals_mp))
                total_weight = sum(weight_vec)
                if total_weight > 0:
                    mean_target = sum(w * y for w, y in zip(weight_vec, y_targets)) / total_weight
                else:
                    mean_target = sum(y_targets) / rows
                sst = sum(w * (y - mean_target) ** 2 for w, y in zip(weight_vec, y_targets))
                rmse = mp.sqrt(chi2 / total_weight)
            else:
                chi2 = sum(r * r for r in residuals_mp)
                mean_target = sum(y_targets) / rows
                sst = sum((y - mean_target) ** 2 for y in y_targets)
                rmse = mp.sqrt(chi2 / rows)
            n = len(y_targets)
            dof_raw = n - cols
            if dof_raw <= 0:
                dof = 0
                reduced = mp.nan
                r2 = mp.nan
                eps = noise_floor()
                noise = mp.nan
                aic = mp.nan
                bic = mp.nan
            else:
                dof = dof_raw
                reduced = chi2 / dof
                r2 = mp.mpf("1") - (chi2 / sst if sst != 0 else mp.mpf("0"))
                eps = noise_floor()
                noise = chi2 / n if chi2 > eps else eps
                aic = 2 * cols + n * mp.log(noise)
                bic = cols * mp.log(n) + n * mp.log(noise)

            jtj_mp = design.T * design
            try:
                inv = jtj_mp ** -1
            except ZeroDivisionError:
                inv = None
            covariance = []
            errors = {}
            sigma2 = chi2 / dof if dof > 0 else mp.nan
            if inv is None:
                covariance = [[mp.nan for _ in range(cols)] for _ in range(cols)]
                for name in definition.parameter_names:
                    errors[name] = mp.nan
            else:
                for i in range(cols):
                    row = []
                    for j in range(cols):
                        row.append(inv[i, j] * sigma2)
                    covariance.append(row)
                    value = row[i]
                    errors[definition.parameter_names[i]] = mp.sqrt(value) if (value >= 0 and dof > 0) else mp.nan

            expression = _expression_text(definition)
            substituted = _substituted_expression(definition, coeffs_mp)
            details = {
                "expression": expression,
                "substituted_expression": substituted,
                "label": definition.label,
                "evaluator": evaluator,
            }
            if weight_vec:
                details["weighted"] = True
            return _LinearFitComputation(
                params=params,
                stat_errors=errors,
                chi2=chi2,
                reduced_chi2=reduced,
                aic=aic,
                bic=bic,
                r2=r2,
                rmse=rmse,
                residuals=residuals_mp,
                fitted_curve=fitted,
                covariance=covariance,
                details=details,
            )

        base_fit = _solve(y_series)
        sys_errors: dict[str, mp.mpf] = {}
        sys_notes: list[str] = []
        system_sigmas = None if weight_vec else data_sigmas
        if system_sigmas is not None:
            if len(data_sigmas) != len(y_series):
                raise ValueError("不确定度列长度必须与 y 数据一致。/ Uncertainty column length must match y values.")
            sigma_vec = [mp.fabs(mp.mpf(sig)) if sig is not None else mp.mpf("0") for sig in system_sigmas]
            if any(sig > 0 for sig in sigma_vec):
                plus_targets = [y + sig for y, sig in zip(y_series, sigma_vec)]
                minus_targets = [y - sig for y, sig in zip(y_series, sigma_vec)]
                try:
                    plus_fit = _solve(plus_targets)
                except Exception as exc:
                    plus_fit = None
                    sys_notes.append(f"Systematic +σ refit failed: {exc}")
                try:
                    minus_fit = _solve(minus_targets)
                except Exception as exc:
                    minus_fit = None
                    sys_notes.append(f"Systematic -σ refit failed: {exc}")
                for name in base_fit.params:
                    deltas = []
                    if plus_fit:
                        deltas.append(mp.fabs(plus_fit.params.get(name, base_fit.params[name]) - base_fit.params[name]))
                    if minus_fit:
                        deltas.append(mp.fabs(minus_fit.params.get(name, base_fit.params[name]) - base_fit.params[name]))
                    if deltas:
                        sys_errors[name] = mp.fsum(deltas) / len(deltas)
                    elif sys_notes:
                        sys_errors[name] = mp.nan
                    else:
                        sys_errors[name] = mp.mpf("0")

        stat_errors, sys_errors, total_errors = combine_error_components(
            base_fit.params, base_fit.stat_errors, sys_errors
        )
        details = dict(base_fit.details)
        if data_sigmas is not None:
            if weight_vec:
                details.setdefault(
                    "uncertainty_note",
                    {
                        "zh": "已用数据不确定度进行加权，仅统计误差；为避免双计，未单独计算系统误差。",
                        "en": "Data uncertainties were used for weighting (statistical only); to avoid double-counting, no separate systematic error was added.",
                    },
                )
            else:
                details.setdefault(
                    "uncertainty_note",
                    {
                        "zh": "统计误差: χ²/权重协方差；系统误差: 数据列整体按 ±σ 重新做同一线性拟合；总误差为统计与系统分量二次和。",
                        "en": "Statistical errors from weighted χ² covariance; systematic errors from ±σ refits of the same linear model; total errors combined in quadrature.",
                    },
                )
        if sys_notes:
            details["systematic_warning"] = "; ".join(sys_notes)
        return FitResult(
            params=base_fit.params,
            param_errors=total_errors,
            chi2=base_fit.chi2,
            reduced_chi2=base_fit.reduced_chi2,
            aic=base_fit.aic,
            bic=base_fit.bic,
            r2=base_fit.r2,
            rmse=base_fit.rmse,
            residuals=base_fit.residuals,
            fitted_curve=base_fit.fitted_curve,
            covariance=base_fit.covariance,
            param_errors_stat=stat_errors,
            param_errors_sys=sys_errors,
            param_errors_total=total_errors,
            details=details,
        )


def build_linear_evaluator(
    definition: AutoModelDefinition, params: dict[str, mp.mpf]
) -> Callable[[mp.mpf], mp.mpf]:
    """Create a callable that evaluates the fitted linear model."""

    coefficients = [mp.mpf(params[name]) for name in definition.parameter_names]

    def _evaluate(x: mp.mpf) -> mp.mpf:
        total = mp.mpf("0")
        mp_x = mp.mpf(x)
        for coeff, basis in zip(coefficients, definition.basis_functions):
            total += coeff * mp.mpf(basis(mp_x))
        return total

    return _evaluate


AUTO_MODEL_MAP = {definition.identifier: definition for definition in AUTO_MODELS}
