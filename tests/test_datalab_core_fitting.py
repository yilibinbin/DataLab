from __future__ import annotations

from dataclasses import dataclass

import mpmath as mp
import pytest


@dataclass(frozen=True)
class UncertainLike:
    value: object
    uncertainty: object
    uncertainty_digits: int | None = None


def test_core_fitting_request_builder_creates_string_payload() -> None:
    from datalab_core.fitting import build_fitting_request
    from datalab_core.jobs import JobMode

    request = build_fitting_request(
        model_type="custom",
        headers=("x", "y", "z"),
        data_rows=(
            ("1.0000000000000000001", "2.5", "10"),
            (mp.mpf("2.25"), 5, "20"),
        ),
        sigma_rows=(
            (None, UncertainLike("0.02", "0.001", uncertainty_digits=2), None),
            (None, "0.04", None),
        ),
        variable_map={"x": "x", "z": "z"},
        target_column="y",
        model_expr="a*x + b*z + C",
        parameter_config={
            "a": {"initial": mp.mpf("1.25"), "min": "0", "max": "10", "fixed": "", "expr": ""},
            "b": {"initial": "0.5"},
        },
        parameter_names=("a", "b"),
        custom_constants={"C": mp.mpf("3.5")},
        weighted=True,
        label="Custom",
        is_multidim=True,
        template_expr="a*x + b*z",
        template_params={"a0": mp.mpf("1.125"), "orders": (1, "2")},
        poly_degree=3,
        inverse_min=1,
        inverse_max=4,
        pade_m=2,
        pade_n=3,
        auto_identifier="fit-1",
        timeout_seconds="120",
        precision_digits=80,
        uncertainty_digits=2,
        parallel={"max_workers": 4, "reserve_cores": 1},
        request_id="fit-core",
    )

    assert request.mode is JobMode.FITTING
    assert request.request_id == "fit-core"
    assert request.options.precision_digits == 80
    assert request.options.uncertainty_digits == 2
    assert request.options.parallel == {"max_workers": 4, "reserve_cores": 1}
    assert request.inputs["model_type"] == "custom"
    assert request.inputs["headers"] == ["x", "y", "z"]
    assert request.inputs["data_rows"] == [
        ["1.0000000000000000001", "2.5", "10"],
        ["2.25", "5", "20"],
    ]
    assert request.inputs["sigma_rows"] == [
        [None, {"kind": "uncertain", "value": "0.02", "uncertainty": "0.001", "uncertainty_digits": 2}, None],
        [None, "0.04", None],
    ]
    assert request.inputs["variable_map"] == {"x": "x", "z": "z"}
    assert request.inputs["variable_data"] == {"x": ["1.0000000000000000001", "2.25"], "z": ["10", "20"]}
    assert request.inputs["x_series"] == ["1.0000000000000000001", "2.25"]
    assert request.inputs["target_column"] == "y"
    assert request.inputs["target_series"] == ["2.5", "5"]
    assert request.inputs["y_series"] == ["2.5", "5"]
    assert request.inputs["sigma_series"] == ["0.02", "0.04"]
    assert request.inputs["weights"] is None
    assert request.inputs["model_expr"] == "a*x + b*z + C"
    assert request.inputs["parameter_config"] == {
        "a": {"initial": "1.25", "min": "0", "max": "10"},
        "b": {"initial": "0.5"},
    }
    assert request.inputs["parameter_names"] == ["a", "b"]
    assert request.inputs["custom_constants"] == {"C": "3.5"}
    assert request.inputs["template_expr"] == "a*x + b*z"
    assert request.inputs["template_params"] == {"a0": "1.125", "orders": ["1", "2"]}
    assert request.inputs["poly_degree"] == 3
    assert request.inputs["inverse_min"] == 1
    assert request.inputs["inverse_max"] == 4
    assert request.inputs["pade_m"] == 2
    assert request.inputs["pade_n"] == 3
    assert request.inputs["auto_identifier"] == "fit-1"
    assert request.inputs["weighted"] is True
    assert request.inputs["label"] == "Custom"
    assert request.inputs["is_multidim"] is True
    assert request.inputs["timeout_seconds"] == "120"


def test_core_fitting_handler_runs_polynomial_direct_request() -> None:
    from datalab_core.fitting import build_fitting_request, fitting_payload_to_fit_result, run_fitting
    from datalab_core.results import ResultStatus

    request = build_fitting_request(
        model_type="polynomial",
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        poly_degree=1,
        precision_digits=80,
        request_id="fit-polynomial-core",
    )

    result = run_fitting(request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["model_type"] == "polynomial"
    assert result.payload["expression"]
    fit = fitting_payload_to_fit_result(result.payload["fit_result"])
    assert mp.almosteq(fit.params["b0"], mp.mpf("1"), abs_eps=mp.mpf("1e-50"))
    assert mp.almosteq(fit.params["b1"], mp.mpf("2"), abs_eps=mp.mpf("1e-50"))


def test_core_fitting_handler_rejects_self_consistent_direct_service_path() -> None:
    from datalab_core.fitting import build_fitting_request, run_fitting

    request = build_fitting_request(
        model_type="self_consistent",
        headers=("x", "u"),
        data_rows=(("0", "1"), ("1", "2")),
        variable_map={"x": "x"},
        target_column="u",
        model_expr="u",
        parameter_config={"a": {"initial": "1"}},
        parameter_names=("a",),
        implicit_definition={
            "x_variables": ("x",),
            "implicit_variable": "u",
            "equation": "a + x",
            "output_expression": "u",
            "parameters": ("a",),
            "solve_options": {"method": "root", "initial": "1", "tolerance": "1e-30", "max_iterations": 50},
        },
        precision_digits=80,
    )

    with pytest.raises(ValueError, match="self_consistent.*subprocess"):
        run_fitting(request)


def test_core_fitting_request_builder_serializes_implicit_definition() -> None:
    from datalab_core.fitting import build_fitting_request

    request = build_fitting_request(
        model_type="self_consistent",
        headers=("n", "delta"),
        data_rows=(("4", "-0.0116"), ("5", "-0.0118")),
        variable_map={"n": "n"},
        target_column="delta",
        model_expr="delta",
        parameter_config={"d0": {"initial": "-0.012"}, "d2": {"initial": "0"}},
        implicit_definition={
            "x_variables": ("n",),
            "implicit_variable": "delta",
            "equation": "d0 + d2/(n-delta)^2",
            "output_expression": "delta",
            "parameters": ("d0", "d2"),
            "constants": {"CR": mp.mpf("3289841960.2500")},
            "solve_options": {
                "method": "root",
                "initial": "-0.01",
                "tolerance": mp.mpf("1e-40"),
                "max_iterations": 120,
            },
        },
        timeout_seconds=300,
        precision_digits=90,
    )

    assert request.inputs["implicit_definition"] == {
        "x_variables": ["n"],
        "implicit_variable": "delta",
        "equation": "d0 + d2/(n-delta)^2",
        "output_expression": "delta",
        "parameters": ["d0", "d2"],
        "constants": {"CR": "3289841960.25"},
        "solve_options": {
            "method": "root",
            "initial": "-0.01",
            "tolerance": "1.0e-40",
            "max_iterations": 120,
        },
    }
    assert request.inputs["timeout_seconds"] == "300"


def test_core_fitting_request_builder_preserves_preparsed_mpf_precision() -> None:
    from datalab_core.fitting import build_fitting_request
    from shared.precision import precision_guard

    text = "1.12345678901234567890123456789012345678901234567890123456789"
    with precision_guard(90):
        value = mp.mpf(text)

    request = build_fitting_request(
        model_type="custom",
        headers=("x", "y"),
        data_rows=((value, value),),
        variable_map={"x": "x"},
        target_column="y",
        model_expr="a*x",
        parameter_config={"a": {"initial": value}},
        custom_constants={"C": value},
        template_params={"p": value},
    )

    assert request.inputs["data_rows"] == [[text, text]]
    assert request.inputs["target_series"] == [text]
    assert request.inputs["parameter_config"]["a"]["initial"] == text
    assert request.inputs["custom_constants"]["C"] == text
    assert request.inputs["template_params"]["p"] == text


def test_core_fitting_request_builder_rejects_binary_float_inputs() -> None:
    from datalab_core.fitting import build_fitting_request

    kwargs = {
        "model_type": "custom",
        "headers": ("x", "y"),
        "data_rows": (("1", "2"),),
        "variable_map": {"x": "x"},
        "target_column": "y",
        "model_expr": "a*x",
    }

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "data_rows": ((1.25, "2"),)})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "sigma_rows": ((None, 0.1),)})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "parameter_config": {"a": {"initial": 1.25}}})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "custom_constants": {"C": 1.25}})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "template_params": {"p": 1.25}})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "timeout_seconds": 300.0})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_fitting_request(**{**kwargs, "parallel": {"max_workers": 2.0}})


@pytest.mark.parametrize("precision_digits", [80.0, True])
def test_core_fitting_request_builder_rejects_malformed_precision_before_payload_formatting(
    monkeypatch: pytest.MonkeyPatch,
    precision_digits: object,
) -> None:
    from datalab_core import fitting

    def fail_if_called(*_args: object, **_kwargs: object) -> list[list[str]]:
        raise AssertionError("payload formatting should not run before precision validation")

    monkeypatch.setattr(fitting, "normalize_numeric_rows", fail_if_called)

    with pytest.raises(TypeError):
        fitting.build_fitting_request(
            model_type="custom",
            headers=("x", "y"),
            data_rows=(("1", "2"),),
            variable_map={"x": "x"},
            target_column="y",
            model_expr="a*x",
            precision_digits=precision_digits,
        )


def test_core_fitting_request_builder_validates_inputs() -> None:
    from datalab_core.fitting import build_fitting_request

    with pytest.raises(ValueError, match="model_type must not be empty"):
        build_fitting_request(
            model_type=" ",
            headers=("x", "y"),
            data_rows=(("1", "2"),),
            variable_map={"x": "x"},
            target_column="y",
            model_expr="a*x",
        )

    with pytest.raises(ValueError, match="Row 1 is missing column y"):
        build_fitting_request(
            model_type="custom",
            headers=("x", "y"),
            data_rows=(("1",),),
            variable_map={"x": "x"},
            target_column="y",
            model_expr="a*x",
        )

    with pytest.raises(ValueError, match="variable_map\\.x missing is not in headers"):
        build_fitting_request(
            model_type="custom",
            headers=("x", "y"),
            data_rows=(("1", "2"),),
            variable_map={"x": "missing"},
            target_column="y",
            model_expr="a*x",
        )

    with pytest.raises(ValueError, match="target_column z is not in headers"):
        build_fitting_request(
            model_type="custom",
            headers=("x", "y"),
            data_rows=(("1", "2"),),
            variable_map={"x": "x"},
            target_column="z",
            model_expr="a*x",
        )

    with pytest.raises(TypeError, match="parameter_config.a must be a mapping"):
        build_fitting_request(
            model_type="custom",
            headers=("x", "y"),
            data_rows=(("1", "2"),),
            variable_map={"x": "x"},
            target_column="y",
            model_expr="a*x",
            parameter_config={"a": "1"},
        )

    with pytest.raises(ValueError, match="weights must have the same length as data_rows"):
        build_fitting_request(
            model_type="custom",
            headers=("x", "y"),
            data_rows=(("1", "2"), ("2", "3")),
            variable_map={"x": "x"},
            target_column="y",
            model_expr="a*x",
            weights=("1",),
        )

    with pytest.raises(TypeError, match="implicit_definition.solve_options must be a mapping or object"):
        build_fitting_request(
            model_type="self_consistent",
            headers=("x", "y"),
            data_rows=(("1", "2"),),
            variable_map={"x": "x"},
            target_column="y",
            model_expr="u",
            implicit_definition={
                "x_variables": ("x",),
                "implicit_variable": "u",
                "equation": "a*x",
                "output_expression": "u",
                "parameters": ("a",),
                "solve_options": ("root",),
            },
        )
