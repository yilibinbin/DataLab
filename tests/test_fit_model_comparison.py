from __future__ import annotations

import inspect
from collections.abc import Iterator, Sequence
from typing import Any, cast

import mpmath as mp
import pytest

from fitting.auto_models import AutoModelDefinition
from fitting.hp_fitter import FitResult
from fitting.problem import ModelProblem


def _fit_result(
    *,
    chi2: str,
    reduced_chi2: str,
    aic: str,
    bic: str,
    rmse: str,
    r2: str,
    params: dict[str, str] | None = None,
    warnings: list[str] | None = None,
) -> FitResult:
    mp_params = {key: mp.mpf(value) for key, value in (params or {"a": "1"}).items()}
    return FitResult(
        params=mp_params,
        param_errors={key: mp.mpf("0.1") for key in mp_params},
        chi2=mp.mpf(chi2),
        reduced_chi2=mp.mpf(reduced_chi2),
        aic=mp.mpf(aic),
        bic=mp.mpf(bic),
        r2=mp.mpf(r2),
        rmse=mp.mpf(rmse),
        residuals=[mp.mpf("999")],
        fitted_curve=[mp.mpf("-999")],
        covariance=[[mp.mpf("1")]],
        details={"diagnostic_warnings": warnings or []},
    )


def _linear_definition(identifier: str, label: str) -> AutoModelDefinition:
    return AutoModelDefinition(
        identifier=identifier,
        label=label,
        basis_functions=[lambda _x: mp.mpf("1")],
        basis_texts=["1"],
        parameter_names=["a"],
    )


class _PoisonAutoModels:
    def __iter__(self) -> Iterator[object]:
        pytest.fail("P2.2 must not iterate AUTO_MODELS")

    def __len__(self) -> int:
        pytest.fail("P2.2 must not read AUTO_MODELS")

    def __bool__(self) -> bool:
        pytest.fail("P2.2 must not inspect AUTO_MODELS")


def test_compare_selected_fits_preserves_user_order_and_one_result_per_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting import model_comparison
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    calls: list[str] = []
    results_by_identifier = {
        "linear": _fit_result(
            chi2="101",
            reduced_chi2="10.1",
            aic="1001",
            bic="2001",
            rmse="0.101",
            r2="0.901",
            params={"a": "1"},
        ),
        "quadratic": _fit_result(
            chi2="202",
            reduced_chi2="20.2",
            aic="1002",
            bic="2002",
            rmse="0.202",
            r2="0.902",
            params={"a": "1", "b": "2"},
        ),
    }

    def fake_fit_linear_model(
        definition: AutoModelDefinition,
        x_data: Any,
        y_data: Any,
        *,
        precision: Any = None,
        weights: Any = None,
        data_sigmas: Any = None,
    ) -> FitResult:
        del x_data, y_data, precision, weights, data_sigmas
        calls.append(definition.identifier)
        return results_by_identifier[definition.identifier]

    monkeypatch.setattr(model_comparison, "fit_linear_model", fake_fit_linear_model)

    candidates = [
        FitComparisonCandidate.linear(
            candidate_id="cand-b",
            label="Quadratic candidate",
            definition=_linear_definition("quadratic", "Quadratic"),
        ),
        FitComparisonCandidate.linear(
            candidate_id="cand-a",
            label="Linear candidate",
            definition=_linear_definition("linear", "Linear"),
        ),
    ]

    result = compare_selected_fits(
        candidates,
        x_data=[mp.mpf("1"), mp.mpf("2")],
        y_data=[mp.mpf("3"), mp.mpf("4")],
        precision=50,
    )

    assert calls == ["quadratic", "linear"]
    assert [entry.candidate_id for entry in result.entries] == ["cand-b", "cand-a"]
    assert [entry.fit_result for entry in result.entries] == [
        results_by_identifier["quadratic"],
        results_by_identifier["linear"],
    ]
    assert [row.order for row in result.rows] == [1, 2]
    assert [row.model_label for row in result.rows] == [
        "Quadratic candidate",
        "Linear candidate",
    ]


def test_compare_selected_fits_reads_stored_metrics_without_recomputing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting import model_comparison
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    sentinel = _fit_result(
        chi2="123456789",
        reduced_chi2="987654321",
        aic="-12345.5",
        bic="67890.25",
        rmse="0.0000001234",
        r2="-42.5",
        params={"a": "1", "b": "2", "c": "3"},
    )

    monkeypatch.setattr(
        model_comparison,
        "fit_linear_model",
        lambda *_args, **_kwargs: sentinel,
    )

    result = compare_selected_fits(
        [
            FitComparisonCandidate.linear(
                candidate_id="sentinel",
                label="Sentinel",
                definition=_linear_definition("sentinel", "Sentinel"),
            )
        ],
        x_data=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        y_data=[mp.mpf("10"), mp.mpf("20"), mp.mpf("30")],
    )

    row = result.rows[0]
    assert row.free_parameter_count == 1
    assert row.chi2 == sentinel.chi2
    assert row.reduced_chi2 == sentinel.reduced_chi2
    assert row.aic == sentinel.aic
    assert row.bic == sentinel.bic
    assert row.rmse == sentinel.rmse
    assert row.r2 == sentinel.r2


def test_compare_selected_fits_records_failure_rows_without_aborting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fitting import model_comparison
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    successful = _fit_result(
        chi2="1",
        reduced_chi2="0.5",
        aic="2",
        bic="3",
        rmse="0.1",
        r2="0.9",
        warnings=["diagnostic warning"],
    )

    def fake_fit_linear_model(
        definition: AutoModelDefinition,
        *_args: Any,
        **_kwargs: Any,
    ) -> FitResult:
        if definition.identifier == "bad":
            raise ValueError("singular design")
        return successful

    monkeypatch.setattr(model_comparison, "fit_linear_model", fake_fit_linear_model)

    result = compare_selected_fits(
        [
            FitComparisonCandidate.linear(
                candidate_id="bad",
                label="Bad model",
                definition=_linear_definition("bad", "Bad"),
            ),
            FitComparisonCandidate.linear(
                candidate_id="good",
                label="Good model",
                definition=_linear_definition("good", "Good"),
            ),
        ],
        x_data=[mp.mpf("1"), mp.mpf("2")],
        y_data=[mp.mpf("3"), mp.mpf("4")],
    )

    bad, good = result.rows
    assert bad.status == "failed"
    assert bad.error == "singular design"
    assert bad.chi2 is None
    assert bad.free_parameter_count == 1
    assert result.entries[0].fit_result is None

    assert good.status == "success"
    assert good.error is None
    assert good.warnings == ("diagnostic warning",)
    assert result.entries[1].fit_result is successful


def test_compare_selected_fits_can_use_explicit_runner_for_custom_problem() -> None:
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    expected = _fit_result(
        chi2="7",
        reduced_chi2="3.5",
        aic="8",
        bic="9",
        rmse="0.7",
        r2="0.77",
        params={"p": "1", "q": "2"},
    )
    calls: list[tuple[ModelProblem, dict[str, Sequence[mp.mpf]], list[mp.mpf], int]] = []

    class FakeRunner:
        def fit(
            self,
            problem: ModelProblem,
            variable_data: dict[str, Sequence[mp.mpf]],
            target_data: Sequence[mp.mpf],
            *,
            precision: int = 80,
            weights: list[mp.mpf] | None = None,
            data_sigmas: list[mp.mpf | None] | None = None,
        ) -> FitResult:
            del weights, data_sigmas
            calls.append((problem, variable_data, list(target_data), precision))
            return expected

    problem = ModelProblem(
        model_type="custom",
        expression="p*x+q",
        variables=("x",),
        parameter_config={"p": {"initial": "1"}, "q": {"fixed": "2"}},
    )

    result = compare_selected_fits(
        [
            FitComparisonCandidate.runner(
                candidate_id="custom",
                label="Custom model",
                problem=problem,
            )
        ],
        x_data=[mp.mpf("1"), mp.mpf("2")],
        y_data=[mp.mpf("3"), mp.mpf("5")],
        variable_data={"x": [mp.mpf("1"), mp.mpf("2")]},
        runner=FakeRunner(),
        precision=70,
    )

    assert calls == [(problem, {"x": [mp.mpf("1"), mp.mpf("2")]}, [mp.mpf("3"), mp.mpf("5")], 70)]
    assert result.rows[0].free_parameter_count == 1
    assert result.entries[0].fit_result is expected


def test_runner_candidate_infers_free_parameters_from_custom_expression() -> None:
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    expected = _fit_result(
        chi2="7",
        reduced_chi2="3.5",
        aic="8",
        bic="9",
        rmse="0.7",
        r2="0.77",
        params={"a": "1", "b": "2"},
    )

    class FakeRunner:
        def fit(self, *_args: Any, **_kwargs: Any) -> FitResult:
            return expected

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b",
        variables=("x",),
        parameter_config={},
    )

    result = compare_selected_fits(
        [
            FitComparisonCandidate.runner(
                candidate_id="custom",
                label="Custom model",
                problem=problem,
            )
        ],
        x_data=[mp.mpf("1"), mp.mpf("2")],
        y_data=[mp.mpf("3"), mp.mpf("5")],
        runner=FakeRunner(),
    )

    assert result.rows[0].free_parameter_count == 2


def test_runner_candidate_excludes_dependent_parameters_from_free_count() -> None:
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    expected = _fit_result(
        chi2="7",
        reduced_chi2="3.5",
        aic="8",
        bic="9",
        rmse="0.7",
        r2="0.77",
        params={"a": "1", "b": "2", "c": "3"},
    )

    class FakeRunner:
        def fit(self, *_args: Any, **_kwargs: Any) -> FitResult:
            return expected

    problem = ModelProblem(
        model_type="custom",
        expression="a*x+b+c",
        variables=("x",),
        parameter_config={"b": {"expr": "2*a"}, "c": {"fixed": "3"}},
    )

    result = compare_selected_fits(
        [
            FitComparisonCandidate.runner(
                candidate_id="custom",
                label="Custom model",
                problem=problem,
            )
        ],
        x_data=[mp.mpf("1"), mp.mpf("2")],
        y_data=[mp.mpf("3"), mp.mpf("5")],
        runner=FakeRunner(),
    )

    assert result.rows[0].free_parameter_count == 1


def test_explicit_free_parameter_count_override_is_validated() -> None:
    from fitting.model_comparison import FitComparisonCandidate

    definition = _linear_definition("linear", "Linear")

    assert (
        FitComparisonCandidate.linear(
            candidate_id="linear",
            label="Linear",
            definition=definition,
            free_parameter_count=0,
        ).free_parameter_count
        == 0
    )
    with pytest.raises(ValueError, match="non-negative integer"):
        FitComparisonCandidate.linear(
            candidate_id="bad",
            label="Bad",
            definition=definition,
            free_parameter_count=-1,
        )
    with pytest.raises(ValueError, match="non-negative integer"):
        FitComparisonCandidate.linear(
            candidate_id="bad",
            label="Bad",
            definition=definition,
            free_parameter_count=cast(Any, 1.5),
        )


def test_compare_selected_fits_propagates_unexpected_programmer_errors() -> None:
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    class BuggyRunner:
        def fit(self, *_args: Any, **_kwargs: Any) -> FitResult:
            raise AttributeError("adapter bug")

    problem = ModelProblem(model_type="custom", expression="a*x", variables=("x",))

    with pytest.raises(AttributeError, match="adapter bug"):
        compare_selected_fits(
            [
                FitComparisonCandidate.runner(
                    candidate_id="bug",
                    label="Bug",
                    problem=problem,
                )
            ],
            x_data=[mp.mpf("1")],
            y_data=[mp.mpf("2")],
            runner=BuggyRunner(),
        )


def test_compare_selected_fits_propagates_unexpected_runner_value_errors() -> None:
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    class BuggyRunner:
        def fit(self, *_args: Any, **_kwargs: Any) -> FitResult:
            raise ValueError("adapter value bug")

    problem = ModelProblem(model_type="custom", expression="a*x", variables=("x",))

    with pytest.raises(ValueError, match="adapter value bug"):
        compare_selected_fits(
            [
                FitComparisonCandidate.runner(
                    candidate_id="bug",
                    label="Bug",
                    problem=problem,
                )
            ],
            x_data=[mp.mpf("1")],
            y_data=[mp.mpf("2")],
            runner=BuggyRunner(),
        )


def test_compare_selected_fits_does_not_reference_auto_fit_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fitting.auto_models as auto_models
    import fitting.model_selector as model_selector
    from fitting import model_comparison
    from fitting.model_comparison import FitComparisonCandidate, compare_selected_fits

    monkeypatch.setattr(
        model_selector,
        "auto_fit_dataset",
        lambda *_args, **_kwargs: pytest.fail("P2.2 must not call auto_fit_dataset"),
    )
    monkeypatch.setattr(
        model_selector,
        "_sequence_model",
        lambda *_args, **_kwargs: pytest.fail("P2.2 must not call _sequence_model"),
    )
    monkeypatch.setattr(model_selector, "AUTO_MODELS", _PoisonAutoModels())
    monkeypatch.setattr(auto_models, "AUTO_MODELS", _PoisonAutoModels())
    monkeypatch.setattr(
        model_comparison,
        "fit_linear_model",
        lambda *_args, **_kwargs: _fit_result(
            chi2="1",
            reduced_chi2="1",
            aic="1",
            bic="1",
            rmse="1",
            r2="1",
        ),
    )

    result = compare_selected_fits(
        [
            FitComparisonCandidate.linear(
                candidate_id="safe",
                label="Safe explicit model",
                definition=_linear_definition("safe", "Safe"),
            )
        ],
        x_data=[mp.mpf("1")],
        y_data=[mp.mpf("2")],
    )

    assert result.rows[0].status == "success"
    source = inspect.getsource(model_comparison)
    assert "auto_fit_dataset" not in source
    assert "_sequence_model" not in source
    assert "best_model" not in source


def test_comparison_formatting_builds_shared_rows_from_comparison_result() -> None:
    from fitting.comparison_formatting import build_comparison_table_rows
    from fitting.model_comparison import FitComparisonRow, FitComparisonResult

    result = FitComparisonResult(
        entries=[],
        rows=[
            FitComparisonRow(
                candidate_id="m1",
                order=1,
                model_label="Model 1",
                status="success",
                free_parameter_count=2,
                chi2=mp.mpf("1.25"),
                reduced_chi2=mp.mpf("0.625"),
                aic=mp.mpf("10"),
                bic=mp.mpf("11"),
                rmse=mp.mpf("0.5"),
                r2=mp.mpf("0.99"),
                warnings=("careful",),
                error=None,
            )
        ],
    )

    rows = build_comparison_table_rows(result, format_value=lambda value: f"V({value})")

    assert rows == [
        {
            "candidate_id": "m1",
            "order": 1,
            "model_label": "Model 1",
            "status": "success",
            "free_parameters": 2,
            "chi2": "V(1.25)",
            "reduced_chi2": "V(0.625)",
            "aic": "V(10.0)",
            "bic": "V(11.0)",
            "rmse": "V(0.5)",
            "r2": "V(0.99)",
            "warnings": "careful",
            "error": "",
        }
    ]


def test_comparison_formatting_builds_payload_rows_and_headers() -> None:
    from fitting.comparison_formatting import (
        COMPARISON_TABLE_HEADERS,
        build_comparison_table_rows_from_payload,
    )

    payload = {
        "rows": [
            {
                "candidate_id": "m1",
                "order": 1,
                "model_label": "Model 1",
                "status": "success",
                "free_parameter_count": 2,
                "chi2": "1.25",
                "reduced_chi2": "0.625",
                "aic": "10.0",
                "bic": "11.0",
                "rmse": "0.5",
                "r2": "0.99",
                "warnings": [None, "", "  ", "careful"],
                "error": None,
            }
        ]
    }

    assert COMPARISON_TABLE_HEADERS == [
        "candidate_id",
        "order",
        "model_label",
        "status",
        "free_parameters",
        "chi2",
        "reduced_chi2",
        "aic",
        "bic",
        "rmse",
        "r2",
        "warnings",
        "error",
    ]
    assert build_comparison_table_rows_from_payload(payload) == [
        {
            "candidate_id": "m1",
            "order": 1,
            "model_label": "Model 1",
            "status": "success",
            "free_parameters": 2,
            "chi2": "1.25",
            "reduced_chi2": "0.625",
            "aic": "10.0",
            "bic": "11.0",
            "rmse": "0.5",
            "r2": "0.99",
            "warnings": "careful",
            "error": "",
        }
    ]


def test_fitting_comparison_latex_block_uses_shared_rows_without_winner_language() -> None:
    from datalab_latex.latex_tables_fitting import build_fitting_comparison_latex_block
    from fitting.comparison_formatting import build_comparison_table_rows_from_payload

    payload = {
        "rows": [
            {
                "candidate_id": "m1",
                "order": 1,
                "model_label": "Linear & safe",
                "status": "success",
                "free_parameter_count": 2,
                "chi2": "1.25",
                "reduced_chi2": "0.625",
                "aic": "10.0",
                "bic": "11.0",
                "rmse": "0.5",
                "r2": "0.99",
                "warnings": [],
                "error": None,
            },
            {
                "candidate_id": "m2",
                "order": 2,
                "model_label": "Bad",
                "status": "failed",
                "free_parameter_count": 0,
                "chi2": None,
                "reduced_chi2": None,
                "aic": None,
                "bic": None,
                "rmse": None,
                "r2": None,
                "warnings": [],
                "error": "singular design",
            },
        ]
    }
    rows = build_comparison_table_rows_from_payload(payload)

    lines = build_fitting_comparison_latex_block(
        rows,
        use_dcolumn=False,
        caption_text="Selected model comparison",
    )
    text = "\n".join(lines)

    assert "Selected model comparison" in text
    assert "Linear \\& safe" in text
    assert "singular design" in text
    assert "winner" not in text.lower()
    assert "best" not in text.lower()


@pytest.mark.parametrize("use_dcolumn", [False, True])
def test_fitting_comparison_latex_wraps_non_numeric_metric_cells(use_dcolumn: bool) -> None:
    from datalab_latex.latex_tables_fitting import build_fitting_comparison_latex_block

    rows = [
        {
            "candidate_id": "m1",
            "order": 1,
            "model_label": "Linear",
            "status": "success",
            "free_parameters": 2,
            "chi2": "not & numeric",
            "reduced_chi2": "",
            "aic": "10.0",
            "bic": "11.0",
            "rmse": "0.5",
            "r2": "0.99",
            "warnings": "",
            "error": "",
        }
    ]

    text = "\n".join(
        build_fitting_comparison_latex_block(
            rows,
            use_dcolumn=use_dcolumn,
        )
    )

    assert "\\multicolumn{1}{c}{not \\& numeric}" in text
    assert "not & numeric" not in text
