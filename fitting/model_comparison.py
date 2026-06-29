from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import mpmath as mp

from .auto_models import AutoModelDefinition, fit_linear_model
from .hp_fitter import FitResult
from .model_parser import infer_parameter_names
from .problem import ModelProblem, constants_for_compute
from .runner import FitRunner

FitComparisonStatus = Literal["success", "failed"]
_CandidateKind = Literal["linear", "runner"]
_EXPECTED_CANDIDATE_FAILURES = (ValueError, ArithmeticError)


class _RunnerLike(Protocol):
    def fit(
        self,
        problem: ModelProblem,
        variable_data: dict[str, Sequence[mp.mpf]],
        target_data: Sequence[mp.mpf],
        *,
        precision: int = 80,
        weights: list[mp.mpf] | None = None,
        data_sigmas: list[mp.mpf | None] | None = None,
    ) -> FitResult: ...


@dataclass(frozen=True)
class FitComparisonCandidate:
    candidate_id: str
    label: str
    kind: _CandidateKind
    linear_definition: AutoModelDefinition | None = None
    problem: ModelProblem | None = None
    free_parameter_count: int | None = None

    @classmethod
    def linear(
        cls,
        *,
        candidate_id: str,
        label: str,
        definition: AutoModelDefinition,
        free_parameter_count: int | None = None,
    ) -> FitComparisonCandidate:
        return cls(
            candidate_id=candidate_id,
            label=label,
            kind="linear",
            linear_definition=definition,
            free_parameter_count=(
                len(definition.parameter_names)
                if free_parameter_count is None
                else _validate_free_parameter_count(free_parameter_count)
            ),
        )

    @classmethod
    def runner(
        cls,
        *,
        candidate_id: str,
        label: str,
        problem: ModelProblem,
        free_parameter_count: int | None = None,
    ) -> FitComparisonCandidate:
        return cls(
            candidate_id=candidate_id,
            label=label,
            kind="runner",
            problem=problem,
            free_parameter_count=(
                _free_parameter_count_from_problem(problem)
                if free_parameter_count is None
                else _validate_free_parameter_count(free_parameter_count)
            ),
        )


@dataclass(frozen=True)
class FitComparisonEntry:
    candidate_id: str
    order: int
    label: str
    candidate: FitComparisonCandidate
    fit_result: FitResult | None
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.fit_result is not None and self.error is None


@dataclass(frozen=True)
class FitComparisonRow:
    candidate_id: str
    order: int
    model_label: str
    status: FitComparisonStatus
    free_parameter_count: int
    chi2: mp.mpf | None
    reduced_chi2: mp.mpf | None
    aic: mp.mpf | None
    bic: mp.mpf | None
    rmse: mp.mpf | None
    r2: mp.mpf | None
    warnings: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class FitComparisonResult:
    entries: list[FitComparisonEntry]
    rows: list[FitComparisonRow]


def compare_selected_fits(
    candidates: Sequence[FitComparisonCandidate],
    *,
    x_data: Sequence[mp.mpf],
    y_data: Sequence[mp.mpf],
    precision: int = 80,
    weights: Sequence[mp.mpf] | None = None,
    data_sigmas: Sequence[mp.mpf | None] | None = None,
    variable_data: Mapping[str, Sequence[mp.mpf]] | None = None,
    runner: _RunnerLike | None = None,
) -> FitComparisonResult:
    entries: list[FitComparisonEntry] = []
    rows: list[FitComparisonRow] = []
    x_series = [mp.mpf(value) for value in x_data]
    y_series = [mp.mpf(value) for value in y_data]
    weight_list = None if weights is None else [mp.mpf(value) for value in weights]
    sigma_list = None if data_sigmas is None else [_optional_mpf(value) for value in data_sigmas]
    variable_series = _normalize_variable_data(variable_data, fallback_x=x_series)
    fit_runner: _RunnerLike = FitRunner() if runner is None else runner
    catch_runner_value_errors = runner is None

    for index, candidate in enumerate(candidates, start=1):
        fit_result: FitResult | None = None
        error: str | None = None
        try:
            fit_result = _run_candidate(
                candidate,
                x_data=x_series,
                y_data=y_series,
                precision=precision,
                weights=weight_list,
                data_sigmas=sigma_list,
                variable_data=variable_series,
                runner=fit_runner,
            )
        except ValueError as exc:
            if candidate.kind == "runner" and not catch_runner_value_errors:
                raise
            error = str(exc)
        except _EXPECTED_CANDIDATE_FAILURES as exc:
            error = str(exc)
        entry = FitComparisonEntry(
            candidate_id=candidate.candidate_id,
            order=index,
            label=candidate.label,
            candidate=candidate,
            fit_result=fit_result,
            error=error,
        )
        entries.append(entry)
        rows.append(_row_from_entry(entry))
    return FitComparisonResult(entries=entries, rows=rows)


def _run_candidate(
    candidate: FitComparisonCandidate,
    *,
    x_data: Sequence[mp.mpf],
    y_data: Sequence[mp.mpf],
    precision: int,
    weights: list[mp.mpf] | None,
    data_sigmas: list[mp.mpf | None] | None,
    variable_data: dict[str, Sequence[mp.mpf]],
    runner: _RunnerLike,
) -> FitResult:
    if candidate.kind == "linear":
        if candidate.linear_definition is None:
            raise ValueError("Linear comparison candidate is missing a model definition.")
        return fit_linear_model(
            candidate.linear_definition,
            list(x_data),
            list(y_data),
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
    if candidate.kind == "runner":
        if candidate.problem is None:
            raise ValueError("Runner comparison candidate is missing a model problem.")
        return runner.fit(
            candidate.problem,
            variable_data,
            list(y_data),
            precision=precision,
            weights=weights,
            data_sigmas=data_sigmas,
        )
    raise ValueError(f"Unsupported comparison candidate kind: {candidate.kind}.")


def _row_from_entry(entry: FitComparisonEntry) -> FitComparisonRow:
    fit_result = entry.fit_result
    if fit_result is None:
        return FitComparisonRow(
            candidate_id=entry.candidate_id,
            order=entry.order,
            model_label=entry.label,
            status="failed",
            free_parameter_count=_candidate_parameter_count(entry.candidate),
            chi2=None,
            reduced_chi2=None,
            aic=None,
            bic=None,
            rmse=None,
            r2=None,
            warnings=(),
            error=entry.error or "Comparison candidate failed.",
        )
    return FitComparisonRow(
        candidate_id=entry.candidate_id,
        order=entry.order,
        model_label=entry.label,
        status="success",
        free_parameter_count=_candidate_parameter_count(entry.candidate),
        chi2=fit_result.chi2,
        reduced_chi2=fit_result.reduced_chi2,
        aic=fit_result.aic,
        bic=fit_result.bic,
        rmse=fit_result.rmse,
        r2=fit_result.r2,
        warnings=_fit_warnings(fit_result),
        error=None,
    )


def _candidate_parameter_count(candidate: FitComparisonCandidate) -> int:
    if candidate.free_parameter_count is not None:
        return candidate.free_parameter_count
    if candidate.linear_definition is not None:
        return len(candidate.linear_definition.parameter_names)
    if candidate.problem is not None:
        return _free_parameter_count_from_problem(candidate.problem)
    return 0


def _free_parameter_count_from_problem(problem: ModelProblem) -> int:
    parameter_names = _parameter_names_for_problem(problem)
    count = 0
    for name in parameter_names:
        config = problem.parameter_config.get(name, {})
        if config.get("fixed") is not None or config.get("expr"):
            continue
        count += 1
    return count


def _parameter_names_for_problem(problem: ModelProblem) -> list[str]:
    config_keys = list(problem.parameter_config.keys())
    if problem.model_type == "custom":
        return infer_parameter_names(
            problem.expression,
            problem.variables,
            config_keys,
            constants=list(constants_for_compute(problem)),
        )
    definition = problem.implicit_definition
    parameters = getattr(definition, "parameters", None)
    if parameters is not None:
        return list(parameters)
    return config_keys


def _validate_free_parameter_count(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("free_parameter_count must be a non-negative integer.")
    if isinstance(value, int):
        count = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError("free_parameter_count must be a non-negative integer.")
        count = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped.isdecimal():
            raise ValueError("free_parameter_count must be a non-negative integer.")
        count = int(stripped)
    else:
        raise ValueError("free_parameter_count must be a non-negative integer.")
    if count < 0:
        raise ValueError("free_parameter_count must be a non-negative integer.")
    return count


def _fit_warnings(result: FitResult) -> tuple[str, ...]:
    details = result.details if isinstance(result.details, dict) else {}
    warnings: list[str] = []
    for key in ("diagnostic_warnings", "warnings"):
        value = details.get(key)
        if isinstance(value, str):
            _append_warning(warnings, value)
        elif isinstance(value, Sequence):
            for item in value:
                _append_warning(warnings, item)
    for key in ("systematic_warning", "uncertainty_note"):
        value = details.get(key)
        if isinstance(value, str) and value:
            warnings.append(value)
        elif isinstance(value, Mapping):
            text = value.get("zh") or value.get("en")
            if text:
                warnings.append(str(text))
    return tuple(dict.fromkeys(warnings))


def _append_warning(warnings: list[str], value: object) -> None:
    if value is None:
        return
    text = value.decode(errors="replace") if isinstance(value, bytes) else str(value)
    if text:
        warnings.append(text)


def _normalize_variable_data(
    variable_data: Mapping[str, Sequence[mp.mpf]] | None,
    *,
    fallback_x: Sequence[mp.mpf],
) -> dict[str, Sequence[mp.mpf]]:
    if variable_data is None:
        return {"x": list(fallback_x)}
    return {
        str(name): [mp.mpf(value) for value in values]
        for name, values in variable_data.items()
    }


def _optional_mpf(value: mp.mpf | None) -> mp.mpf | None:
    if value is None:
        return None
    return mp.mpf(value)
