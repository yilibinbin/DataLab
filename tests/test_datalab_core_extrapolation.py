from __future__ import annotations

import mpmath as mp
import pytest


def test_core_extrapolation_request_builder_creates_string_payload() -> None:
    from datalab_core.extrapolation import build_extrapolation_request
    from datalab_core.jobs import JobMode

    request = build_extrapolation_request(
        headers=("A", "B"),
        rows=(
            ("1.0000000000000000001", "2"),
            (mp.mpf("3.5"), 4),
        ),
        method="richardson",
        method_options={"p": "2", "reference_column": "A"},
        precision_digits=80,
        uncertainty_digits=2,
        segments=((-5, 1), (1, 99), (2, 2)),
        request_id="extrapolation-core",
    )

    assert request.mode is JobMode.EXTRAPOLATION
    assert request.request_id == "extrapolation-core"
    assert request.options.precision_digits == 80
    assert request.options.uncertainty_digits == 2
    assert request.inputs["headers"] == ["A", "B"]
    assert request.inputs["rows"] == [
        ["1.0000000000000000001", "2"],
        ["3.5", "4"],
    ]
    assert request.inputs["method"] == "richardson"
    assert request.inputs["method_options"] == {"p": "2", "reference_column": "A"}
    assert request.inputs["segments"] == [[0, 1], [1, 2]]


def test_core_extrapolation_request_builder_preserves_preparsed_mpf_precision() -> None:
    from datalab_core.extrapolation import build_extrapolation_request
    from shared.precision import precision_guard

    text = "1.12345678901234567890123456789012345678901234567890123456789"
    with precision_guard(90):
        value = mp.mpf(text)

    request = build_extrapolation_request(
        headers=("A",),
        rows=((value,),),
    )

    assert request.inputs["rows"] == [[text]]


def test_core_extrapolation_request_builder_rejects_binary_float_inputs() -> None:
    from datalab_core.extrapolation import build_extrapolation_request

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_extrapolation_request(headers=("A",), rows=((1.25,),))

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_extrapolation_request(headers=("A",), rows=(("1",),), method_options={"p": 2.0})

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_extrapolation_request(headers=("A",), rows=(("1",),), segments=((0.0, 1),))


@pytest.mark.parametrize("segment", [(("0", 1),), ((True, 1),), ((0.0, 1),)])
def test_core_extrapolation_request_builder_rejects_non_integer_segment_bounds(
    segment: tuple[tuple[object, int], ...],
) -> None:
    from datalab_core.extrapolation import build_extrapolation_request

    with pytest.raises(TypeError):
        build_extrapolation_request(headers=("A",), rows=(("1",),), segments=segment)


@pytest.mark.parametrize("precision_digits", [80.0, True])
def test_core_extrapolation_request_builder_rejects_malformed_precision_before_payload_formatting(
    monkeypatch: pytest.MonkeyPatch,
    precision_digits: object,
) -> None:
    from datalab_core import extrapolation

    def fail_if_called(*_args: object, **_kwargs: object) -> list[list[str]]:
        raise AssertionError("payload formatting should not run before precision validation")

    monkeypatch.setattr(extrapolation, "normalize_numeric_rows", fail_if_called)

    with pytest.raises(TypeError):
        extrapolation.build_extrapolation_request(
            headers=("A",),
            rows=(("1",),),
            precision_digits=precision_digits,
        )


def test_core_extrapolation_request_builder_validates_headers_rows_and_segments() -> None:
    from datalab_core.extrapolation import build_extrapolation_request

    with pytest.raises(ValueError, match="headers must contain at least one column"):
        build_extrapolation_request(headers=(), rows=(("1",),))

    with pytest.raises(ValueError, match="must contain at least one row"):
        build_extrapolation_request(headers=("A",), rows=())

    with pytest.raises(ValueError, match="Row 1 is missing column B"):
        build_extrapolation_request(headers=("A", "B"), rows=(("1",),))

    with pytest.raises(ValueError, match="at least one row"):
        build_extrapolation_request(headers=("A",), rows=(("1",),), segments=((1, 1),))


def test_core_extrapolation_handler_runs_quadratic_request() -> None:
    from datalab_core.extrapolation import build_extrapolation_request, extrapolation_payload_to_results, run_extrapolation
    from datalab_core.results import ResultStatus

    request = build_extrapolation_request(
        headers=("A", "B", "C"),
        rows=(("1", "1.5", "1.75"),),
        method="quadratic",
        precision_digits=80,
        uncertainty_digits=2,
        segments=((0, 1),),
        request_id="extrapolation-handler",
    )

    result = run_extrapolation(request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["headers"] == ["A", "B", "C"]
    assert result.payload["precision_used"] == 80
    assert result.payload["segments"] == [[0, 1]]
    legacy_results = extrapolation_payload_to_results(result.payload)
    assert len(legacy_results) == 1
    assert legacy_results[0].method == "quadratic"
    assert mp.nstr(legacy_results[0].value, 30) == "1.875"
    assert mp.nstr(legacy_results[0].uncertainty, 30) == "0.875"


def test_core_extrapolation_handler_runs_custom_formula_without_latex_imports() -> None:
    from datalab_core.extrapolation import build_extrapolation_request, run_extrapolation
    from datalab_core.results import ResultStatus

    request = build_extrapolation_request(
        headers=("A", "B", "C"),
        rows=(("1.0000000000000000001", "2", "3"),),
        method="custom",
        method_options={"custom_formula": "A + B + C"},
        precision_digits=80,
        uncertainty_digits=2,
    )

    result = run_extrapolation(request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["results"][0]["value"].startswith("6.0000000000000000001")
    assert result.payload["results"][0]["details"]["formula"] == "A + B + C"


def test_core_extrapolation_handler_preserves_power_law_payload_options(monkeypatch: pytest.MonkeyPatch) -> None:
    import datalab_core.extrapolation as core_extrapolation
    from datalab_core.extrapolation import build_extrapolation_request, run_extrapolation
    from shared.extrapolation_engine import ExtrapolationResult

    observed: dict[str, object] = {}

    def fake_process(headers, rows, *, verbose=False, options=None):
        observed["headers"] = tuple(headers)
        observed["rows"] = tuple(tuple(str(value) for value in row) for row in rows)
        observed["verbose"] = verbose
        observed["config"] = options.power_law_config
        return [tuple(row) for row in rows], [
            ExtrapolationResult(
                value=mp.mpf("0"),
                uncertainty=mp.mpf("0"),
                method="power_law",
            )
        ]

    monkeypatch.setattr(core_extrapolation, "process_extrapolation_rows", fake_process)

    request = build_extrapolation_request(
        headers=("A", "B", "C"),
        rows=(("1", "2", "3"),),
        method="power_law",
        method_options={
            "power_law_config": {
                "x_values": ("4", "5", "6"),
                "precision": "90",
                "initial_guess": "1.25",
                "exponent_override": "3.5",
                "seed_guesses": ("0.5", "1.0", "2.0"),
            }
        },
        precision_digits=80,
    )

    run_extrapolation(request)

    config = observed["config"]
    assert config.x_values == ("4", "5", "6")
    assert config.precision == 90
    assert config.initial_guess == "1.25"
    assert config.exponent_override == "3.5"
    assert config.seed_guesses == ("0.5", "1.0", "2.0")
