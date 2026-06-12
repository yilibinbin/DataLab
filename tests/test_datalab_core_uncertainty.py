from __future__ import annotations

from dataclasses import dataclass

import mpmath as mp
import pytest


@dataclass(frozen=True)
class UncertainLike:
    value: object
    uncertainty: object


def test_core_uncertainty_request_builder_creates_string_payload() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.uncertainty import build_uncertainty_request

    request = build_uncertainty_request(
        headers=("A", "B"),
        rows=(
            (UncertainLike("1.0000000000000000001", "0.01"), "2"),
            (mp.mpf("3.5"), 4),
        ),
        uncertainty_rows=(
            (None, "0.2"),
            ("0.3", None),
        ),
        constants={
            "C": UncertainLike("10", "0.5"),
            "D": {"value": mp.mpf("2.25"), "uncertainty": "0.125"},
        },
        formula="A + B + C",
        propagation_method="monte_carlo",
        propagation_order=2,
        mc_samples=5000,
        mc_seed=123,
        precision_digits=80,
        uncertainty_digits=2,
        segments=((-5, 1), (1, 99), (2, 2)),
        request_id="uncertainty-core",
    )

    assert request.mode is JobMode.UNCERTAINTY
    assert request.request_id == "uncertainty-core"
    assert request.options.precision_digits == 80
    assert request.options.uncertainty_digits == 2
    assert request.inputs["headers"] == ["A", "B"]
    assert request.inputs["values"] == [
        ["1.0000000000000000001", "2"],
        ["3.5", "4"],
    ]
    assert request.inputs["uncertainties"] == [
        ["0.01", "0.2"],
        ["0.3", "0"],
    ]
    assert request.inputs["constants"] == {
        "C": {"value": "10", "uncertainty": "0.5"},
        "D": {"value": "2.25", "uncertainty": "0.125"},
    }
    assert request.inputs["formula"] == "A + B + C"
    assert request.inputs["propagation"] == {
        "method": "monte_carlo",
        "order": 2,
        "mc_samples": 5000,
        "mc_seed": 123,
    }
    assert request.inputs["segments"] == [[0, 1], [1, 2]]


def test_core_uncertainty_request_builder_preserves_preparsed_mpf_precision() -> None:
    from datalab_core.uncertainty import build_uncertainty_request
    from shared.precision import precision_guard

    value_text = "1.12345678901234567890123456789012345678901234567890123456789"
    sigma_text = "0.12345678901234567890123456789012345678901234567890123456789"
    with precision_guard(90):
        value = mp.mpf(value_text)
        sigma = mp.mpf(sigma_text)

    request = build_uncertainty_request(
        headers=("A",),
        rows=((UncertainLike(value, sigma),),),
        constants={"C": (value, sigma)},
        formula="A + C",
    )

    assert request.inputs["values"] == [[value_text]]
    assert request.inputs["uncertainties"] == [[sigma_text]]
    assert request.inputs["constants"]["C"] == {"value": value_text, "uncertainty": sigma_text}


def test_core_uncertainty_handler_runs_taylor_and_restores_precision() -> None:
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    previous = mp.mp.dps
    mp.mp.dps = 23
    try:
        request = build_uncertainty_request(
            headers=("A", "B"),
            rows=((UncertainLike("1.0000000000000000001", "0.01"), UncertainLike("2", "0.02")),),
            constants={"C": ("3", "0.03")},
            formula="A + B + C",
            propagation_method="taylor",
            propagation_order=1,
            precision_digits=80,
            uncertainty_digits=2,
            request_id="uncertainty-run",
        )
        result = SessionService(handlers={request.mode: run_uncertainty}).submit(request)
        observed_after = mp.mp.dps
    finally:
        mp.mp.dps = previous

    assert observed_after == 23
    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["precision_used"] == 80
    assert result.payload["formula"] == "A + B + C"
    assert result.payload["results"][0]["value"].startswith("6.0000000000000000001")
    assert mp.almosteq(mp.mpf(result.payload["results"][0]["uncertainty"]), mp.sqrt(mp.mpf("0.0014")))
    assert result.payload["results"][0]["contributions"] == {
        "A": "0.0001",
        "B": "0.0004",
        "C": "0.0009",
    }


def test_uncertainty_payload_to_results_rehydrates_legacy_uncertain_values() -> None:
    from datalab_core.uncertainty import uncertainty_payload_to_results

    results = uncertainty_payload_to_results(
        {
            "results": [
                {
                    "value": "1.25",
                    "uncertainty": "0.05",
                    "contributions": {"A": "0.0025"},
                }
            ]
        }
    )

    assert len(results) == 1
    assert results[0].value == mp.mpf("1.25")
    assert results[0].uncertainty == mp.mpf("0.05")
    assert results[0].contributions == {"A": mp.mpf("0.0025")}


def test_core_uncertainty_request_builder_rejects_binary_float_inputs() -> None:
    from datalab_core.uncertainty import build_uncertainty_request

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_uncertainty_request(headers=("A",), rows=((1.25,),), formula="A")

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_uncertainty_request(
            headers=("A",),
            rows=(("1",),),
            uncertainty_rows=((0.1,),),
            formula="A",
        )

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_uncertainty_request(
            headers=("A",),
            rows=(("1",),),
            constants={"C": {"value": "1", "uncertainty": 0.2}},
            formula="A + C",
        )

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula="A", segments=((0.0, 1),))


@pytest.mark.parametrize("segment", [(("0", 1),), ((True, 1),), ((0.0, 1),)])
def test_core_uncertainty_request_builder_rejects_non_integer_segment_bounds(
    segment: tuple[tuple[object, int], ...],
) -> None:
    from datalab_core.uncertainty import build_uncertainty_request

    with pytest.raises(TypeError):
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula="A", segments=segment)


@pytest.mark.parametrize("precision_digits", [80.0, True])
def test_core_uncertainty_request_builder_rejects_malformed_precision_before_payload_formatting(
    monkeypatch: pytest.MonkeyPatch,
    precision_digits: object,
) -> None:
    from datalab_core import uncertainty

    def fail_if_called(*_args: object, **_kwargs: object) -> tuple[list[list[str]], list[list[str]]]:
        raise AssertionError("payload formatting should not run before precision validation")

    monkeypatch.setattr(uncertainty, "_normalize_uncertainty_rows", fail_if_called)

    with pytest.raises(TypeError):
        uncertainty.build_uncertainty_request(
            headers=("A",),
            rows=(("1",),),
            formula="A",
            precision_digits=precision_digits,
        )


def test_core_uncertainty_request_builder_validates_inputs() -> None:
    from datalab_core.uncertainty import build_uncertainty_request

    with pytest.raises(ValueError, match="headers must contain at least one column"):
        build_uncertainty_request(headers=(), rows=(("1",),), formula="A")

    with pytest.raises(ValueError, match="must contain at least one row"):
        build_uncertainty_request(headers=("A",), rows=(), formula="A")

    with pytest.raises(ValueError, match="formula must not be empty"):
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula=" ")

    with pytest.raises(ValueError, match="Row 1 is missing column B"):
        build_uncertainty_request(headers=("A", "B"), rows=(("1",),), formula="A + B")

    with pytest.raises(ValueError, match="uncertainty_rows must have the same length"):
        build_uncertainty_request(
            headers=("A",),
            rows=(("1",),),
            uncertainty_rows=(("0.1",), ("0.2",)),
            formula="A",
        )

    with pytest.raises(TypeError, match="propagation.order must be an integer"):
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula="A", propagation_order=True)

    with pytest.raises(ValueError, match="segments must include at least one row"):
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula="A", segments=((1, 1),))
