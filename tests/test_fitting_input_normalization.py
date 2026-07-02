from __future__ import annotations

import inspect
import linecache
from typing import Any

import mpmath as mp
import pytest

from app_desktop import constants_editor, parameter_table
from app_desktop import window as desktop_window
from app_desktop import window_fitting_models_mixin
from app_desktop.fitting_input_normalization import (
    ConstantsState,
    ConstantsInput,
    FitUncertaintyState,
    ParameterInput,
    WorkerInputRequest,
    constants_rows_to_text,
    fit_uncertainty_policy,
    normalize_constants_state,
    normalize_data_uncertainty,
    normalize_fitting_input,
    normalize_parameter_rows,
    parse_constants_text,
)
from app_desktop.workers_core import FitJob, _deserialize_fit_job, _serialize_fit_job
from app_web.logic import fitting as web_fitting
from app_web.logic import statistics as web_statistics
from datalab_latex.latex_tables_error_propagation import parse_uncertainty_format as latex_parse_uncertainty
from shared import fitting_uncertainty as shared_fitting_uncertainty
from shared import input_normalization as shared_input_normalization
from shared.uncertainty import parse_uncertainty_format as shared_parse_uncertainty


def test_parameter_normalization_filters_orphans_and_constraints() -> None:
    rows = [
        {"name": "a", "initial": "1", "fixed": "2", "min": "0", "max": "3"},
        {"name": "old", "initial": "9"},
        {"name": "", "initial": "4"},
    ]

    disabled = normalize_parameter_rows(rows, constraints_enabled=False, orphan_names={"old"})
    assert disabled.compute_rows() == [
        {"name": "a", "initial": "1", "fixed": "2", "min": "0", "max": "3"},
        {"name": "", "initial": "4", "fixed": "", "min": "", "max": ""},
    ]
    with pytest.raises(ValueError, match="Parameter name"):
        disabled.compute_config(validate=True)

    without_draft = normalize_parameter_rows(rows[:2], constraints_enabled=False, orphan_names={"old"})
    assert without_draft.compute_config(validate=True) == {"a": {"initial": "1"}}

    enabled = normalize_parameter_rows(rows[:2], constraints_enabled=True, orphan_names={"old"})
    assert enabled.compute_config(validate=True) == {
        "a": {"initial": "1", "fixed": "2", "min": "0", "max": "3"}
    }


def test_parameter_normalization_preserves_zero_values_from_legacy_dict() -> None:
    state = normalize_parameter_rows(
        {"a": {"initial": 0, "fixed": 0, "min": 0, "max": 1}},
        constraints_enabled=True,
    )

    assert state.persisted_rows() == [
        {"name": "a", "initial": "0", "fixed": "0", "min": "0", "max": "1"}
    ]
    assert state.compute_config(validate=True) == {
        "a": {"initial": "0", "fixed": "0", "min": "0", "max": "1"}
    }


def test_parameter_normalization_preserves_detected_source_metadata() -> None:
    state = normalize_parameter_rows(
        [{"name": "a", "initial": "1", "source": "detected"}],
        constraints_enabled=False,
    )

    assert state.persisted_rows() == [
        {"name": "a", "initial": "1", "fixed": "", "min": "", "max": "", "source": "detected"}
    ]
    assert state.compute_config(validate=True) == {"a": {"initial": "1"}}


def test_parameter_normalization_rejects_malformed_legacy_rows() -> None:
    malformed_rows: list[Any] = [{"name": "a", "initial": "1"}, "bad-row"]

    with pytest.raises(ValueError, match="Parameter rows.*row 2|第 2 行"):
        normalize_parameter_rows(
            malformed_rows,
            constraints_enabled=False,
        )


def test_parameter_normalization_required_names() -> None:
    state = normalize_parameter_rows([{"name": "a", "initial": "1"}], constraints_enabled=False)

    with pytest.raises(ValueError, match="b"):
        state.compute_config(required_names=["a", "b"])

    assert state.compute_config(required_names=["a"]) == {"a": {"initial": "1"}}


def test_constants_text_and_rows_share_parser() -> None:
    text = "# comment\nCR = 3.2\nM 7294\nlonely\n= 3"

    rows = parse_constants_text(text)

    assert rows == [
        {"name": "CR", "value": "3.2"},
        {"name": "M", "value": "7294"},
        {"name": "lonely", "value": ""},
        {"name": "", "value": "3"},
    ]
    assert constants_rows_to_text(rows) == "CR 3.2\nM 7294\nlonely\n3"


def test_constants_normalization_disabled_preserves_and_computes_complete_rows() -> None:
    state = normalize_constants_state(
        enabled=False,
        rows=[{"name": "CR", "value": "3.2898419602500(36)[+9]"}],
        numeric_mode="uncertainty",
    )

    assert state.persisted_rows() == [{"name": "CR", "value": "3.2898419602500(36)[+9]"}]
    assert state.compute_dict(validate=True) == {"CR": "3.2898419602500(36)[+9]"}


def test_constants_normalization_uses_shared_uncertainty_parser() -> None:
    state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "CR", "value": "3.2898419602500(36)[+9]"}],
        numeric_mode="uncertainty",
    )

    assert state.compute_dict(validate=True) == {"CR": "3.2898419602500(36)[+9]"}
    assert latex_parse_uncertainty is shared_parse_uncertainty


def test_constants_normalization_mpmath_mode_accepts_uncertainty_nominal_values() -> None:
    state = normalize_constants_state(
        enabled=True,
        rows=[
            {"name": "CR", "value": "3.2898419602500(36)[+9]"},
            {"name": "M", "value": "7295.29954171(17)"},
        ],
        numeric_mode="mpmath",
    )

    assert state.compute_dict(validate=True) == {
        "CR": "3.2898419602500(36)[+9]",
        "M": "7295.29954171(17)",
    }


def test_constants_normalization_rejects_reserved_names_in_mpmath_mode() -> None:
    state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "Pi", "value": "1"}],
        numeric_mode="mpmath",
    )

    with pytest.raises(ValueError, match="reserved"):
        state.compute_dict(validate=True)


def test_constants_normalization_rejects_malformed_legacy_rows() -> None:
    malformed_rows: list[Any] = [{"name": "K", "value": "1"}, ["bad-row"]]

    with pytest.raises(ValueError, match="Constant rows.*row 2|第 2 行"):
        normalize_constants_state(
            enabled=True,
            rows=malformed_rows,
        )


def test_constants_normalization_prefers_explicit_rows_over_text_when_both_present() -> None:
    state = normalize_constants_state(
        enabled=True,
        view="text",
        rows=[{"name": "K", "value": "1"}],
        text="K 2\nR 3",
    )

    assert state.persisted_rows() == [{"name": "K", "value": "1"}]
    assert state.compute_dict(validate=True) == {"K": "1"}


def test_desktop_constants_helpers_reexport_shared_implementations() -> None:
    assert ConstantsState is shared_input_normalization.ConstantsState
    assert constants_rows_to_text is shared_input_normalization.constants_rows_to_text
    assert FitUncertaintyState is shared_fitting_uncertainty.FitUncertaintyState
    assert fit_uncertainty_policy is shared_fitting_uncertainty.fit_uncertainty_policy
    assert normalize_constants_state is shared_input_normalization.normalize_constants_state
    assert parse_constants_text is shared_input_normalization.parse_constants_text


def test_uncertainty_policy_preserves_weighted_and_unweighted_semantics() -> None:
    sigmas = [mp.mpf("0.5"), None]

    unweighted = fit_uncertainty_policy(sigmas, weighted=False)
    assert unweighted.data_sigmas == tuple(sigmas)
    assert unweighted.weights is None

    with pytest.raises(ValueError, match="第 2 行|Row 2"):
        fit_uncertainty_policy(sigmas, weighted=True)

    weighted = fit_uncertainty_policy([mp.mpf("0.5"), mp.mpf("0.25")], weighted=True)
    assert weighted.weights == (mp.mpf("4"), mp.mpf("16"))


@pytest.mark.parametrize("sigma", [mp.nan, mp.inf, -mp.mpf("0.1"), mp.mpf("0")])
def test_uncertainty_policy_rejects_non_finite_or_non_positive_sigmas(sigma: mp.mpf) -> None:
    with pytest.raises(ValueError, match="finite positive|有限正数"):
        fit_uncertainty_policy([sigma], weighted=False)

    with pytest.raises(ValueError, match="finite positive|有限正数"):
        fit_uncertainty_policy([sigma], weighted=True)


def test_data_uncertainty_normalization_prefers_embedded_then_sigma_columns() -> None:
    headers = ["x", "y", "y_sigma"]
    rows = [
        (mp.mpf("1"), mp.mpf("10"), mp.mpf("0.3")),
        (mp.mpf("2"), mp.mpf("20"), mp.mpf("0.4")),
    ]
    sigma_rows = [
        (None, shared_parse_uncertainty("10.0(2)"), None),
        (None, None, None),
    ]

    assert normalize_data_uncertainty(
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        target_column="y",
    ) == [mp.mpf("0.2"), None]
    assert normalize_data_uncertainty(
        headers=headers,
        rows=rows,
        sigma_rows=[(None, None, None), (None, None, None)],
        target_column="y",
    ) == [mp.mpf("0.3"), mp.mpf("0.4")]


def test_data_uncertainty_normalization_uses_explicit_sigma_column_first() -> None:
    headers = ["x", "y", "manual_sigma", "y_sigma"]
    rows = [
        (mp.mpf("1"), mp.mpf("10"), mp.mpf("-0.7"), mp.mpf("0.3")),
        (mp.mpf("2"), mp.mpf("20"), mp.mpf("0.8"), mp.mpf("0.4")),
    ]
    sigma_rows = [
        (None, shared_parse_uncertainty("10.0(2)"), None, None),
        (None, shared_parse_uncertainty("20.0(3)"), None, None),
    ]

    assert normalize_data_uncertainty(
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        target_column="y",
        sigma_column="manual_sigma",
    ) == [mp.mpf("0.7"), mp.mpf("0.8")]
    assert normalize_data_uncertainty(
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        target_column="y",
        sigma_column="manual_sigma",
        absolute=False,
    ) == [mp.mpf("-0.7"), mp.mpf("0.8")]


def test_data_uncertainty_normalization_explicit_sigma_column_rejects_short_rows() -> None:
    with pytest.raises(ValueError, match="第 2 行|Row 2"):
        normalize_data_uncertainty(
            headers=["x", "y", "sigma"],
            rows=[
                (mp.mpf("1"), mp.mpf("10"), mp.mpf("0.3")),
                (mp.mpf("2"), mp.mpf("20")),
            ],
            sigma_rows=[(None, None, None), (None, None)],
            target_column="y",
            sigma_column="sigma",
        )


def test_data_uncertainty_normalization_auto_sigma_column_allows_short_rows() -> None:
    assert normalize_data_uncertainty(
        headers=["x", "y", "y_sigma"],
        rows=[
            (mp.mpf("1"), mp.mpf("10"), mp.mpf("0.3")),
            (mp.mpf("2"), mp.mpf("20")),
        ],
        sigma_rows=[(None, None, None), (None, None)],
        target_column="y",
    ) == [mp.mpf("0.3"), None]


def test_data_uncertainty_normalization_returns_none_without_uncertainty_source() -> None:
    assert normalize_data_uncertainty(
        headers=["x", "y"],
        rows=[(mp.mpf("1"), mp.mpf("10")), (mp.mpf("2"), mp.mpf("20"))],
        sigma_rows=[(None, None), (None, None)],
        target_column="y",
    ) == [None, None]


def test_full_fitting_input_normalizer_combines_parameters_constants_and_uncertainty() -> None:
    normalized = normalize_fitting_input(
        model_type="custom",
        expression="a*x + CR",
        variable_names=["x"],
        target_column="y",
        parameters=ParameterInput(
            rows=[{"name": "a", "initial": "1", "min": "0"}],
            constraints_enabled=True,
        ),
        constants=ConstantsInput(
            enabled=True,
            rows=[{"name": "CR", "value": "3.2898419602500(36)[+9]"}],
        ),
        sigma_values=[mp.mpf("0.5")],
        weighted=True,
    )

    assert normalized.model_type == "custom"
    assert normalized.variable_names == ("x",)
    assert normalized.parameter_config == {"a": {"initial": "1", "min": "0"}}
    assert normalized.constants_dict == {"CR": "3.2898419602500(36)[+9]"}
    assert normalized.uncertainty is not None
    assert normalized.uncertainty.weights == (mp.mpf("4"),)


def test_full_fitting_input_normalizer_produces_worker_safe_state() -> None:
    normalized = normalize_fitting_input(
        model_type="custom",
        expression="a*x + b",
        variable_names=["x"],
        target_column="y",
        parameters=ParameterInput(rows=[{"name": "a", "initial": "1"}]),
        worker_request=WorkerInputRequest(
            headers=["x", "y", "sigma"],
            data_rows=[
                (mp.mpf("1"), mp.mpf("3"), mp.mpf("0.5")),
                (mp.mpf("2"), mp.mpf("5"), mp.mpf("0.25")),
            ],
            sigma_rows=[(None, None, None), (None, None, None)],
            variable_mapping={"x": "x"},
        ),
        weighted=True,
    )

    assert normalized.worker_input is not None
    assert normalized.worker_input.variable_map == {"x": "x"}
    assert normalized.worker_input.variable_data == {"x": (mp.mpf("1"), mp.mpf("2"))}
    assert normalized.worker_input.target_series == (mp.mpf("3"), mp.mpf("5"))
    assert normalized.worker_input.sigma_series == (mp.mpf("0.5"), mp.mpf("0.25"))
    assert normalized.worker_input.weights == (mp.mpf("4"), mp.mpf("16"))


def test_normalized_worker_state_round_trips_through_fit_job_payload() -> None:
    normalized = normalize_fitting_input(
        model_type="custom",
        expression="a*x + b",
        variable_names=["x"],
        target_column="y",
        parameters=ParameterInput(rows=[{"name": "a", "initial": "1"}, {"name": "b", "initial": "0"}]),
        worker_request=WorkerInputRequest(
            headers=["x", "y", "sigma"],
            data_rows=[
                (mp.mpf("1"), mp.mpf("3"), mp.mpf("0.5")),
                (mp.mpf("2"), mp.mpf("5"), mp.mpf("0.25")),
            ],
            sigma_rows=[(None, None, None), (None, None, None)],
            variable_mapping={"x": "x"},
        ),
        weighted=True,
    )
    assert normalized.worker_input is not None
    worker_input = normalized.worker_input
    job = FitJob(
        model_type="custom",
        headers=["x", "y", "sigma"],
        data_rows=[
            (mp.mpf("1"), mp.mpf("3"), mp.mpf("0.5")),
            (mp.mpf("2"), mp.mpf("5"), mp.mpf("0.25")),
        ],
        sigma_rows=[(None, None, None), (None, None, None)],
        x_series=list(worker_input.variable_data["x"]),
        y_series=list(worker_input.target_series),
        sigma_series=list(worker_input.sigma_series),
        weights=list(worker_input.weights) if worker_input.weights is not None else None,
        variable_map=dict(worker_input.variable_map),
        variable_data={key: list(values) for key, values in worker_input.variable_data.items()},
        target_series=list(worker_input.target_series),
        target_column=normalized.target_column,
        model_expr=normalized.expression,
        parameter_config={key: dict(value) for key, value in normalized.parameter_config.items()},
        parameter_names=list(normalized.parameter_config),
        template_expr=None,
        template_params=None,
        poly_degree=0,
        inverse_min=1,
        inverse_max=3,
        pade_m=1,
        pade_n=1,
        precision=16,
        generate_latex=False,
        output_path="",
        use_dcolumn=True,
        caption=None,
        verbose=False,
        render_plots=False,
        latex_digits=16,
        weighted=True,
        label="custom",
        is_multidim=False,
        implicit_definition=None,
        timeout_seconds=None,
        custom_constants={},
    )

    restored = _deserialize_fit_job(_serialize_fit_job(job))

    assert restored.variable_map == {"x": "x"}
    assert restored.variable_data == {"x": [mp.mpf("1"), mp.mpf("2")]}
    assert restored.target_series == [mp.mpf("3"), mp.mpf("5")]
    assert restored.sigma_series == [mp.mpf("0.5"), mp.mpf("0.25")]
    assert restored.weights == [mp.mpf("4"), mp.mpf("16")]


def test_normalized_compute_state_is_immutable() -> None:
    normalized = normalize_fitting_input(
        model_type="custom",
        expression="a*x",
        variable_names=["x"],
        parameters=ParameterInput(rows=[{"name": "a", "initial": "1"}]),
        constants=ConstantsInput(enabled=True, rows=[{"name": "K", "value": "1"}]),
    )

    with pytest.raises(TypeError):
        normalized.parameter_config["b"] = {"initial": "2"}  # type: ignore[index]
    with pytest.raises(TypeError):
        normalized.parameter_config["a"]["initial"] = "2"  # type: ignore[index]
    with pytest.raises(TypeError):
        normalized.constants_dict["K"] = "2"  # type: ignore[index]
    with pytest.raises(TypeError):
        normalized.parameters.rows[0]["initial"] = "2"  # type: ignore[index]
    with pytest.raises(TypeError):
        normalized.constants.rows[0]["value"] = "2"  # type: ignore[index]


def test_production_paths_delegate_to_shared_normalizer() -> None:
    # inspect.getsource reads through linecache; drop any stale entry a prior
    # test left (e.g. via importlib.reload of a dependency) so getsource re-reads
    # the current source instead of returning the wrong function body
    # (order-dependent flake seen in full-suite runs).
    linecache.clearcache()
    assert "normalize_parameter_rows" in inspect.getsource(parameter_table.ParameterTable._normalized_state)
    assert "normalize_constants_state" in inspect.getsource(constants_editor.ConstantsEditor.constants_dict)
    assert "normalize_fitting_input" in inspect.getsource(
        window_fitting_models_mixin.WindowFittingModelsMixin._collect_custom_fit_config
    )
    # _execute_custom_fit (and the other five synchronous fit paths) were removed
    # in P1-9 as dead code; the normalization invariant they carried is still
    # asserted on the live _collect_custom_fit_config and _prepare_fit_job paths.
    assert "normalize_fitting_input" in inspect.getsource(
        window_fitting_models_mixin.WindowFittingModelsMixin._prepare_fit_job
    )
    assert "required_parameter_names=parameter_names" in inspect.getsource(
        desktop_window.ExtrapolationWindow._collect_implicit_config
    )


def test_full_fitting_input_normalizer_preserves_implicit_draft_fields() -> None:
    normalized = normalize_fitting_input(
        model_type="self_consistent",
        expression="u - d0 - d2/(n-u)^2\nEn + R/(n-u)^2",
        variable_names=["n", "u"],
        target_column="E",
        implicit_variable="u",
        implicit_equation="u = d0 + d2/(n-u)^2",
        output_expression="En + R/(n-u)^2",
        parameters=ParameterInput(rows=[{"name": "d0", "initial": "-0.01"}]),
        constants=ConstantsInput(enabled=True, rows=[{"name": "R", "value": "1"}]),
    )

    assert normalized.implicit_variable == "u"
    assert normalized.implicit_equation == "u = d0 + d2/(n-u)^2"
    assert normalized.output_expression == "En + R/(n-u)^2"
    assert normalized.target_column == "E"


def test_web_consumers_use_shared_uncertainty_parser() -> None:
    assert getattr(web_fitting, "parse_uncertainty_format") is shared_parse_uncertainty
    assert getattr(web_statistics, "parse_uncertainty_format") is shared_parse_uncertainty
