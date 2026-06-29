from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import mpmath as mp
import pytest


@dataclass(frozen=True)
class UncertainLike:
    value: object
    uncertainty: object


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_float(item) for item in value)
    return False


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
    assert request.inputs["collect_monte_carlo_distribution"] is False
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


def test_core_uncertainty_monte_carlo_cancellation_returns_cancelled_status() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    calls = 0

    def cancel_after_start() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("1",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="monte_carlo",
        mc_samples=300,
        mc_seed=7,
        precision_digits=50,
        request_id="uncertainty-mc-cancel",
    )

    result = SessionService(
        handlers={JobMode.UNCERTAINTY: run_uncertainty},
        cancellation_checker=cancel_after_start,
    ).submit(request)

    assert result.status is ResultStatus.CANCELLED
    assert calls >= 3


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
    assert result.payload["propagation"] == {
        "method": "taylor",
        "order": 1,
        "mc_samples": None,
        "mc_seed": None,
    }
    assert result.payload["results"][0]["value"].startswith("6.0000000000000000001")
    assert mp.almosteq(mp.mpf(result.payload["results"][0]["uncertainty"]), mp.sqrt(mp.mpf("0.0014")))
    assert result.payload["results"][0]["contributions"] == {
        "A": "0.0001",
        "B": "0.0004",
        "C": "0.0009",
    }


def test_core_uncertainty_taylor_payload_includes_json_safe_sensitivities() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A", "B"),
        rows=(("2", "3"),),
        uncertainty_rows=(("0.1", "0.2"),),
        constants={"C": ("4", "0.3")},
        formula="A * B + C",
        propagation_method="taylor",
        propagation_order=1,
        precision_digits=50,
    )

    result = run_uncertainty(request).payload["results"][0]

    assert result["value"] == "10.0"
    assert result["sensitivities"] == {
        "A": {
            "absolute": "3.0",
            "relative": "0.6",
            "relative_omission_reason": None,
        },
        "B": {
            "absolute": "2.0",
            "relative": "0.6",
            "relative_omission_reason": None,
        },
        "C": {
            "absolute": "1.0",
            "relative": "0.4",
            "relative_omission_reason": None,
        },
    }
    assert not _contains_float(result["sensitivities"])


def test_core_uncertainty_snapshot_maps_sensitivity_metadata_to_diagnostic_rows() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, build_uncertainty_result_snapshot, run_uncertainty

    request = build_uncertainty_request(
        headers=("A", "B"),
        rows=(("2", "3"),),
        uncertainty_rows=(("0.1", "0.2"),),
        constants={"C": ("4", "0.3")},
        formula="A * B + C",
        propagation_method="taylor",
        propagation_order=1,
        precision_digits=50,
    )
    payload = dict(run_uncertainty(request).payload)
    payload["data_rows"] = request.inputs["values"]

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert snapshot["results"][0]["sensitivities"]["C"]["relative"] == "0.4"
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["sensitivity_absolute.1.A"] == {
        "key": "sensitivity_absolute.1.A",
        "label_key": "uncertainty.diagnostic.sensitivity_absolute",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "3.0",
        "source": "A",
        "row_index": 1,
    }
    assert diagnostic_rows["sensitivity_relative.1.A"]["value"] == "0.6"
    assert diagnostic_rows["sensitivity_absolute.1.C"]["value"] == "1.0"
    assert diagnostic_rows["sensitivity_relative.1.C"]["value"] == "0.4"
    assert not any(str(row["key"]).startswith("sensitivity_relative_omitted.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_sensitivity_omits_relative_when_not_meaningful() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, build_uncertainty_result_snapshot, run_uncertainty

    request = build_uncertainty_request(
        headers=("A", "B"),
        rows=(("5", "0"),),
        uncertainty_rows=(("0.1", "0.2"),),
        formula="A + B * 2",
        propagation_method="taylor",
        propagation_order=1,
        precision_digits=50,
    )
    payload = dict(run_uncertainty(request).payload)
    payload["data_rows"] = request.inputs["values"]

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    row = snapshot["results"][0]["sensitivities"]["B"]
    assert row == {
        "absolute": "2.0",
        "relative": None,
        "relative_omission_reason": "zero_input",
    }
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["sensitivity_relative_omitted.1.B"] == {
        "key": "sensitivity_relative_omitted.1.B",
        "label_key": "uncertainty.diagnostic.sensitivity_relative_omitted",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "zero_input",
        "source": "B",
        "row_index": 1,
        "message_key": "uncertainty.diagnostic.sensitivity_relative_omitted.zero_input",
    }


def test_core_uncertainty_monte_carlo_runs_do_not_persist_sensitivities() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, build_uncertainty_result_snapshot, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="monte_carlo",
        propagation_order=1,
        mc_samples=100,
        mc_seed=29,
        precision_digits=50,
    )
    payload = dict(run_uncertainty(request).payload)
    payload["data_rows"] = request.inputs["values"]

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert "sensitivities" not in payload["results"][0]
    assert snapshot is not None
    assert "sensitivities" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("sensitivity_") for row in snapshot["diagnostic_rows"])


def test_core_uncertainty_snapshot_ignores_tampered_monte_carlo_sensitivities() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    payload = {
        "headers": ["A"],
        "formula": "A",
        "precision_used": 50,
        "propagation": {
            "method": "monte_carlo",
            "order": 1,
            "mc_samples": 100,
            "mc_seed": 29,
        },
        "results": [
            {
                "value": "2.0",
                "uncertainty": "0.1",
                "contributions": {},
                "sensitivities": {
                    "A": {
                        "absolute": "1.0",
                        "relative": "1.0",
                        "relative_omission_reason": None,
                    }
                },
            }
        ],
    }
    snapshot = build_uncertainty_result_snapshot(
        "error",
        payload,
    )

    assert snapshot is not None
    assert "sensitivities" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("sensitivity_") for row in snapshot["diagnostic_rows"])

    invalid_payload = {
        **payload,
        "propagation": {
            "method": "monte_carlo",
            "order": "invalid",
            "mc_samples": 100,
            "mc_seed": 29,
        },
    }
    invalid_config_snapshot = build_uncertainty_result_snapshot("error", invalid_payload)

    assert invalid_config_snapshot is not None
    assert "configuration" not in invalid_config_snapshot
    assert "sensitivities" not in invalid_config_snapshot["results"][0]
    assert not any(str(row["key"]).startswith("sensitivity_") for row in invalid_config_snapshot["diagnostic_rows"])


def test_core_uncertainty_propagation_metadata_matches_effective_configuration() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    monte_carlo_request = build_uncertainty_request(
        headers=("A",),
        rows=(("1",),),
        uncertainty_rows=(("0",),),
        formula="A",
        propagation_method="mc",
        propagation_order=0,
        mc_samples=100,
        mc_seed=7,
        precision_digits=40,
    )
    assert monte_carlo_request.inputs["propagation"] == {
        "method": "monte_carlo",
        "order": 1,
        "mc_samples": 100,
        "mc_seed": 7,
    }
    monte_carlo_result = run_uncertainty(monte_carlo_request)
    assert monte_carlo_result.payload["propagation"] == monte_carlo_request.inputs["propagation"]

    default_samples_request = build_uncertainty_request(
        headers=("A",),
        rows=(("1",),),
        uncertainty_rows=(("0",),),
        formula="A",
        propagation_method="monte_carlo",
        propagation_order=1,
        mc_samples=None,
        mc_seed=None,
        precision_digits=40,
    )
    assert default_samples_request.inputs["propagation"] == {
        "method": "monte_carlo",
        "order": 1,
        "mc_samples": 5000,
        "mc_seed": None,
    }
    default_samples_result = run_uncertainty(default_samples_request)
    assert default_samples_result.payload["propagation"] == default_samples_request.inputs["propagation"]

    taylor_request = build_uncertainty_request(
        headers=("A",),
        rows=(("1",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="unknown-method",
        propagation_order=0,
        mc_samples=5000,
        mc_seed=123,
        precision_digits=40,
    )
    assert taylor_request.inputs["propagation"] == {
        "method": "taylor",
        "order": 1,
        "mc_samples": None,
        "mc_seed": None,
    }
    taylor_result = run_uncertainty(taylor_request)
    assert taylor_result.payload["propagation"] == taylor_request.inputs["propagation"]


def test_core_uncertainty_monte_carlo_payload_includes_json_safe_taylor_comparison() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="monte_carlo",
        propagation_order=1,
        mc_samples=400,
        mc_seed=11,
        precision_digits=60,
    )

    envelope = run_uncertainty(request)

    result = envelope.payload["results"][0]
    comparison = result["comparison"]
    assert comparison["method"] == "taylor_vs_monte_carlo"
    assert comparison["absolute_result_tolerance"] == "1e-12"
    assert comparison["relative_result_tolerance"] == "1e-8"
    assert comparison["sample_count"] == 400
    assert comparison["taylor_order"] == 1
    assert result["value"] == comparison["monte_carlo_mean"]
    assert result["uncertainty"] == comparison["monte_carlo_std"]
    assert all(isinstance(value, str | int | bool) or value is None for value in comparison.values())
    assert not _contains_float(comparison)

    taylor_mean = mp.mpf(comparison["taylor_mean"])
    monte_carlo_mean = mp.mpf(comparison["monte_carlo_mean"])
    monte_carlo_std = mp.mpf(comparison["monte_carlo_std"])
    expected_standard_error = monte_carlo_std / mp.sqrt(400)
    expected_floor = max(
        mp.mpf("1e-12"),
        mp.mpf("1e-8") * max(abs(taylor_mean), abs(monte_carlo_mean)),
    )
    expected_threshold = max(3 * expected_standard_error, expected_floor)
    expected_difference = abs(monte_carlo_mean - taylor_mean)

    assert mp.almosteq(mp.mpf(comparison["monte_carlo_standard_error"]), expected_standard_error)
    assert mp.almosteq(mp.mpf(comparison["practical_floor"]), expected_floor)
    assert mp.almosteq(mp.mpf(comparison["absolute_mean_difference"]), expected_difference)
    assert mp.almosteq(mp.mpf(comparison["mean_disagreement_threshold"]), expected_threshold)
    assert comparison["mean_disagreement"] is (expected_difference > expected_threshold)
    assert comparison["relative_std_difference"] is not None
    assert comparison["relative_std_difference_omission_reason"] is None


def test_core_uncertainty_comparison_near_zero_means_use_absolute_tolerance_floor() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A * 0",
        propagation_method="monte_carlo",
        propagation_order=1,
        mc_samples=100,
        mc_seed=17,
        precision_digits=60,
    )

    comparison = run_uncertainty(request).payload["results"][0]["comparison"]

    assert comparison["practical_floor"] == "1e-12"
    assert comparison["mean_disagreement_threshold"] == "1e-12"
    assert comparison["mean_disagreement"] is False


def test_core_uncertainty_comparison_omits_relative_std_difference_for_zero_widths() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0",),),
        formula="A",
        propagation_method="monte_carlo",
        propagation_order=1,
        mc_samples=100,
        mc_seed=19,
        precision_digits=60,
    )

    comparison = run_uncertainty(request).payload["results"][0]["comparison"]

    assert comparison["taylor_std"] == "0.0"
    assert comparison["monte_carlo_std"] == "0.0"
    assert comparison["relative_std_difference"] is None
    assert comparison["relative_std_difference_omission_reason"] == "zero_std"


def test_core_uncertainty_snapshot_rejects_unexpected_relative_std_omission_reason_for_monte_carlo_comparison() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "absolute_result_tolerance": "1e-12",
                        "relative_result_tolerance": "1e-8",
                        "sample_count": 100,
                        "taylor_order": 1,
                        "taylor_mean": "2.0",
                        "taylor_std": "0.1",
                        "monte_carlo_mean": "2.0",
                        "monte_carlo_std": "0.1",
                        "monte_carlo_standard_error": "0.01",
                        "practical_floor": "0.00000002",
                        "absolute_mean_difference": "0.0",
                        "mean_disagreement_threshold": "0.03",
                        "mean_disagreement": False,
                        "mean_disagreement_omission_reason": None,
                        "relative_std_difference": "0.0",
                        "relative_std_difference_omission_reason": "zero_std",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_taylor_runs_do_not_persist_monte_carlo_comparison() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="taylor",
        propagation_order=1,
        mc_samples=400,
        mc_seed=11,
        precision_digits=60,
    )

    payload = run_uncertainty(request).payload

    assert payload["propagation"] == {
        "method": "taylor",
        "order": 1,
        "mc_samples": None,
        "mc_seed": None,
    }
    assert "comparison" not in payload["results"][0]


def test_core_uncertainty_monte_carlo_default_does_not_persist_distribution() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="monte_carlo",
        mc_samples=120,
        mc_seed=11,
        precision_digits=60,
    )

    payload = run_uncertainty(request).payload

    assert "monte_carlo_distribution" not in payload["results"][0]
    assert not _contains_float(payload)


def test_core_uncertainty_monte_carlo_opt_in_persists_json_safe_distribution() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="monte_carlo",
        mc_samples=120,
        mc_seed=11,
        collect_monte_carlo_distribution=True,
        precision_digits=60,
    )

    result = run_uncertainty(request).payload["results"][0]
    distribution = result["monte_carlo_distribution"]

    assert distribution["schema"] == "datalab.monte_carlo_distribution_summary"
    assert distribution["schema_version"] == 1
    assert distribution["requested_sample_count"] == 120
    assert distribution["evaluated_sample_count"] == 120
    assert distribution["accepted_sample_count"] == 120
    assert distribution["rejected_sample_count"] == 0
    assert distribution["finite_sample_count"] == 120
    assert isinstance(distribution["mean"], str)
    assert isinstance(distribution["std"], str)
    assert len(distribution["histogram"]["bin_edges"]) == len(distribution["histogram"]["counts"]) + 1
    assert set(distribution["percentiles"]) == {"2.5", "50", "97.5"}
    assert not _contains_float(distribution)


def test_core_uncertainty_taylor_opt_in_does_not_persist_monte_carlo_distribution() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="taylor",
        collect_monte_carlo_distribution=True,
        precision_digits=60,
    )

    payload = run_uncertainty(request).payload

    assert "monte_carlo_distribution" not in payload["results"][0]
    assert not _contains_float(payload)


def test_core_uncertainty_taylor_order2_payload_includes_json_safe_order_comparison() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A * A",
        propagation_method="taylor",
        propagation_order=2,
        precision_digits=60,
    )

    result = run_uncertainty(request).payload["results"][0]
    comparison = result["taylor_order_comparison"]

    assert comparison["method"] == "taylor_order_1_vs_2"
    assert comparison["order_low"] == 1
    assert comparison["order_high"] == 2
    assert comparison["order1_mean"] is not None
    assert comparison["order2_mean"] is not None
    assert comparison["absolute_mean_difference"] is not None
    assert all(isinstance(value, str | int | bool) or value is None for value in comparison.values())
    assert not _contains_float(comparison)


def test_core_uncertainty_taylor_order1_runs_do_not_persist_taylor_order_comparison() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, build_uncertainty_result_snapshot, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="taylor",
        propagation_order=1,
        precision_digits=60,
    )

    payload = dict(run_uncertainty(request).payload)
    payload["results"] = [
        dict(
            payload["results"][0],
            taylor_order_comparison={
                "method": "taylor_order_1_vs_2",
                "order_low": 1,
                "order_high": 2,
                "order1_mean": "2.0",
                "order1_std": "0.1",
                "order2_mean": "2.0",
                "order2_std": "0.1",
                "absolute_mean_difference": "0.0",
                "relative_std_difference": "0.0",
                "relative_std_difference_omission_reason": None,
            },
        )
    ]
    payload["data_rows"] = request.inputs["values"]

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert "taylor_order_comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("taylor_order_comparison.") for row in snapshot["diagnostic_rows"])


def test_core_uncertainty_monte_carlo_order2_payload_uses_deterministic_taylor_order_comparison_without_extra_monte_carlo_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core import uncertainty as uncertainty_core
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty
    from shared.error_propagation_engine import apply_formula_to_data as real_apply_formula_to_data

    calls: list[tuple[str | None, int | None]] = []

    def fake_apply_formula_to_data(*args: Any, **kwargs: Any) -> object:
        calls.append(
            (
                cast(str | None, kwargs.get("propagation_method")),
                cast(int | None, kwargs.get("propagation_order")),
            )
        )
        return real_apply_formula_to_data(*args, **kwargs)

    monkeypatch.setattr(uncertainty_core, "apply_formula_to_data", fake_apply_formula_to_data)

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A * A",
        propagation_method="monte_carlo",
        propagation_order=2,
        mc_samples=120,
        mc_seed=31,
        precision_digits=60,
    )

    result = run_uncertainty(request).payload["results"][0]

    assert result["comparison"]["method"] == "taylor_vs_monte_carlo"
    assert result["taylor_order_comparison"]["method"] == "taylor_order_1_vs_2"
    assert calls.count(("monte_carlo", 2)) == 1
    assert calls.count(("taylor", 1)) == 1
    assert calls.count(("taylor", 2)) == 2
    assert len(calls) == 4
    assert not _contains_float(result["taylor_order_comparison"])


def test_core_uncertainty_monte_carlo_records_unavailable_comparison_when_taylor_order_unsupported() -> None:
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        propagation_method="monte_carlo",
        propagation_order=3,
        mc_samples=100,
        mc_seed=23,
        precision_digits=60,
    )

    comparison = run_uncertainty(request).payload["results"][0]["comparison"]

    assert comparison == {
        "method": "taylor_vs_monte_carlo",
        "absolute_result_tolerance": "1e-12",
        "relative_result_tolerance": "1e-8",
        "sample_count": 100,
        "taylor_order": 3,
        "comparison_unavailable_reason": "taylor_unavailable",
    }
    assert not _contains_float(comparison)


def test_core_uncertainty_comparison_omits_mean_disagreement_for_nonfinite_mean_inputs() -> None:
    from datalab_core import uncertainty as uncertainty_core
    from shared.uncertainty import UncertainValue

    comparison = uncertainty_core._taylor_monte_carlo_comparison_payload(  # noqa: SLF001
        monte_carlo_result=UncertainValue(mp.nan, mp.mpf("0.1")),
        taylor_result=UncertainValue(mp.mpf("2"), mp.mpf("0.1")),
        sample_count=100,
        taylor_order=1,
        precision_digits=60,
    )

    assert comparison["mean_disagreement"] is None
    assert comparison["mean_disagreement_omission_reason"] == "nonfinite_mean"
    assert not _contains_float(comparison)


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


def test_uncertainty_payload_to_results_preserves_sensitivity_metadata_for_snapshots() -> None:
    from datalab_core.uncertainty import (
        build_uncertainty_request,
        build_uncertainty_result_snapshot,
        run_uncertainty,
        uncertainty_payload_to_results,
    )

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("1.25",),),
        uncertainty_rows=(("0.05",),),
        formula="A",
        propagation_method="taylor",
        propagation_order=1,
        precision_digits=60,
    )
    payload = run_uncertainty(request).payload
    legacy_results = uncertainty_payload_to_results(payload)

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": payload["headers"],
            "formula": payload["formula"],
            "precision_used": payload["precision_used"],
            "propagation": payload["propagation"],
            "results": legacy_results,
        },
    )

    assert legacy_results[0].sensitivities == {
        "A": {
            "absolute": "1.0",
            "relative": "1.0",
            "relative_omission_reason": None,
        }
    }
    assert snapshot is not None
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["sensitivity_absolute.1.A"]["value"] == "1.0"
    assert diagnostic_rows["sensitivity_relative.1.A"]["value"] == "1.0"


def test_core_uncertainty_snapshot_rejects_float_sensitivity_payloads() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "formula": "A",
            "precision_used": 50,
            "propagation": {
                "method": "taylor",
                "order": 1,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "sensitivities": {
                        "A": {
                            "absolute": 1.0,
                            "relative": 0.5,
                            "relative_omission_reason": None,
                        },
                        "B": {
                            "absolute": "2.0",
                            "relative": "1.0",
                            "relative_omission_reason": None,
                        }
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    assert "sensitivities" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("sensitivity_") for row in snapshot["diagnostic_rows"])


def test_uncertainty_payload_to_results_suppresses_monte_carlo_sensitivities() -> None:
    from datalab_core.uncertainty import uncertainty_payload_to_results

    results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": "invalid",
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "sensitivities": {
                        "A": {
                            "absolute": "1.0",
                            "relative": "1.0",
                            "relative_omission_reason": None,
                        }
                    },
                }
            ],
        }
    )

    assert results[0].sensitivities is None


def test_uncertainty_payload_to_results_preserves_valid_monte_carlo_distribution() -> None:
    from datalab_core.uncertainty import uncertainty_payload_to_results

    distribution = {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "2.0",
        "std": "0.1",
        "histogram": {
            "bin_edges": ["1.8", "2.0", "2.2"],
            "counts": [50, 50],
        },
        "percentiles": {
            "2.5": "1.81",
            "50": "2.0",
            "97.5": "2.19",
        },
    }

    results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": distribution,
                }
            ],
        }
    )

    assert results[0].monte_carlo_distribution == distribution


def test_uncertainty_payload_to_results_suppresses_non_monte_carlo_or_malformed_distribution() -> None:
    from datalab_core.uncertainty import uncertainty_payload_to_results

    valid_distribution = {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "2.0",
        "std": "0.1",
        "histogram": {
            "bin_edges": ["1.8", "2.0", "2.2"],
            "counts": [50, 50],
        },
        "percentiles": {
            "2.5": "1.81",
            "50": "2.0",
            "97.5": "2.19",
        },
    }
    taylor_results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {"method": "taylor", "order": 1, "mc_samples": None, "mc_seed": None},
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": valid_distribution,
                }
            ],
        }
    )
    malformed_distribution = dict(valid_distribution)
    malformed_distribution["mean"] = 2.0
    monte_carlo_results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": malformed_distribution,
                }
            ],
        }
    )

    assert taylor_results[0].monte_carlo_distribution is None
    assert monte_carlo_results[0].monte_carlo_distribution is None

    nonfinite_mean = dict(valid_distribution)
    nonfinite_mean["mean"] = "nan"
    nonfinite_mean_results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": nonfinite_mean,
                }
            ],
        }
    )
    nonfinite_edges = dict(valid_distribution)
    nonfinite_edges["histogram"] = {
        "bin_edges": ["1.8", "inf", "2.2"],
        "counts": [50, 50],
    }
    nonfinite_edge_results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": nonfinite_edges,
                }
            ],
        }
    )
    inconsistent_counts = dict(valid_distribution)
    inconsistent_counts["requested_sample_count"] = 0
    inconsistent_count_results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": inconsistent_counts,
                }
            ],
        }
    )
    inverted_percentiles = dict(valid_distribution)
    inverted_percentiles["percentiles"] = {
        "2.5": "2.19",
        "50": "2.0",
        "97.5": "1.81",
    }
    inverted_percentile_results = uncertainty_payload_to_results(
        {
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "monte_carlo_distribution": inverted_percentiles,
                }
            ],
        }
    )

    assert nonfinite_mean_results[0].monte_carlo_distribution is None
    assert nonfinite_edge_results[0].monte_carlo_distribution is None
    assert inconsistent_count_results[0].monte_carlo_distribution is None
    assert inverted_percentile_results[0].monte_carlo_distribution is None


def test_core_uncertainty_result_snapshot_is_json_safe_and_renders_outputs() -> None:
    from datalab_core.uncertainty import (
        UNCERTAINTY_RESULT_SNAPSHOT_SCHEMA,
        build_uncertainty_result_snapshot,
        render_uncertainty_snapshot_outputs,
    )
    from shared.uncertainty import UncertainValue

    results = [
        UncertainValue(
            mp.mpf("3.75"),
            mp.mpf("0.125"),
            contributions={"A": mp.mpf("0.01"), "B": mp.mpf("0.03")},
        ),
        UncertainValue(mp.mpf("4.5"), mp.mpf("0.2"), contributions={"A": mp.mpf("0.02")}),
    ]
    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A", "B"],
            "data_rows": [[mp.mpf("1.25"), mp.mpf("2.5")], [mp.mpf("2"), mp.mpf("2.5")]],
            "results": results,
            "formula": "A + B",
            "precision_used": 70,
            "propagation": {
                "method": "monte_carlo",
                "order": 2,
                "mc_samples": 4096,
                "mc_seed": 12345,
            },
        },
        overview_state="complete",
        precision={"display_digits": 12, "uncertainty_digits": 2},
    )

    assert snapshot is not None
    assert snapshot["schema"] == UNCERTAINTY_RESULT_SNAPSHOT_SCHEMA
    assert snapshot["schema_version"] == 1
    assert snapshot["family"] == "uncertainty"
    assert snapshot["mode"] == "error_propagation"
    assert snapshot["configuration"] == {
        "propagation": {
            "method": "monte_carlo",
            "order": 2,
            "mc_samples": 4096,
            "mc_seed": 12345,
        }
    }
    assert snapshot["source"] == {"row_count": 2, "source_columns": ["A", "B"]}
    assert snapshot["metric_rows"] == [
        {
            "key": "result_value.1",
            "label_key": "uncertainty.metric.result_value",
            "value": "3.75",
            "uncertainty": "0.125",
            "row_index": 1,
            "render_group": "metric",
        },
        {
            "key": "result_value.2",
            "label_key": "uncertainty.metric.result_value",
            "value": "4.5",
            "uncertainty": "0.2",
            "row_index": 2,
            "render_group": "metric",
        },
    ]
    assert snapshot["results"][0]["contributions"] == {"A": "0.01", "B": "0.03"}
    assert snapshot["diagnostic_rows"] == [
        {
            "key": "contribution.1.A",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.01",
            "source": "A",
            "row_index": 1,
        },
        {
            "key": "contribution.1.B",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.03",
            "source": "B",
            "row_index": 1,
        },
        {
            "key": "contribution.2.A",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.02",
            "source": "A",
            "row_index": 2,
        },
        {
            "key": "contribution_total.B",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.03",
            "uncertainty": "50.0%",
            "source": "B",
        },
        {
            "key": "contribution_total.A",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.03",
            "uncertainty": "50.0%",
            "source": "A",
        },
        {
            "key": "contribution_percent.B",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "50.0%",
            "source": "B",
        },
        {
            "key": "contribution_percent.A",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "50.0%",
            "source": "A",
        },
        {
            "key": "contribution_cumulative_percent.B",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "50.0%",
            "source": "B",
        },
        {
            "key": "contribution_cumulative_percent.A",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "100.0%",
            "source": "A",
        },
        {
            "key": "configuration.propagation.method",
            "label_key": "uncertainty.configuration.propagation.method",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "monte_carlo",
        },
        {
            "key": "configuration.propagation.order",
            "label_key": "uncertainty.configuration.propagation.order",
            "severity": "info",
            "render_group": "diagnostic",
            "value": 2,
        },
        {
            "key": "configuration.propagation.mc_samples",
            "label_key": "uncertainty.configuration.propagation.mc_samples",
            "severity": "info",
            "render_group": "diagnostic",
            "value": 4096,
        },
        {
            "key": "configuration.propagation.mc_seed",
            "label_key": "uncertainty.configuration.propagation.mc_seed",
            "severity": "info",
            "render_group": "diagnostic",
            "value": 12345,
        },
    ]
    assert snapshot["row_flags"] == []
    assert snapshot["precision"]["compute_digits"] == 70
    assert snapshot["compatibility"]["rendered_caches_authoritative"] is False
    assert not _contains_float(snapshot)

    rendered = render_uncertainty_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, csv_headers = rendered
    assert "## Error Propagation Results" in text
    assert "**Formula**: `A + B`" in text
    assert "**Rows**: 2" in text
    assert "| 1 | 3.75 | 0.125 | 3.75 +/- 0.125 |" in text
    assert csv_headers == ["index", "value", "uncertainty", "latex"]
    assert csv_rows == [
        {"index": 1, "value": "3.75", "uncertainty": "0.125", "latex": "3.75 +/- 0.125"},
        {"index": 2, "value": "4.5", "uncertainty": "0.2", "latex": "4.5 +/- 0.2"},
    ]


def test_core_uncertainty_snapshot_preserves_high_precision_under_low_ambient_context() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot
    from shared.precision import precision_guard
    from shared.uncertainty import UncertainValue

    with precision_guard(90):
        result = UncertainValue(
            mp.mpf("1.234567890123456789012345678901234567890123456789"),
            mp.mpf("0.00000000000000000012345678901234567890123456789"),
            contributions={"A": mp.mpf("0.0000000000000000000000000001234567890123456789")},
        )

    with precision_guard(15):
        snapshot = build_uncertainty_result_snapshot(
            "error",
            {
                "headers": ["A"],
                "data_rows": [[mp.mpf("1")]],
                "results": [result],
                "formula": "A",
                "precision_used": 80,
            },
            precision={"compute_digits": 15, "display_digits": 12},
        )

    assert snapshot is not None
    assert snapshot["precision"]["compute_digits"] == 80
    first = snapshot["results"][0]
    assert str(first["value"]).startswith("1.23456789012345678901234567890123456789")
    assert str(first["uncertainty"]).startswith("0.0000000000000000001234567890123456789")
    assert str(first["contributions"]["A"]).startswith("1.234567890123456789e-28")
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_does_not_invent_low_precision_tail_digits() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot
    from shared.precision import precision_guard
    from shared.uncertainty import UncertainValue

    with precision_guard(10):
        result = UncertainValue(
            mp.mpf("1.234567890123456789"),
            mp.mpf("0.1"),
            contributions={"A": mp.mpf("0.2")},
        )

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [[mp.mpf("1")]],
            "results": [result],
            "formula": "A",
            "precision_used": 80,
        },
        precision={"compute_digits": 15},
    )

    assert snapshot is not None
    first = snapshot["results"][0]
    assert first["value"] == "1.23456789"
    assert first["uncertainty"] == "0.1"
    assert first["contributions"] == {"A": "0.2"}
    assert "11834" not in str(first["value"])
    assert "000000000000" not in str(first["uncertainty"])


def test_core_uncertainty_snapshot_preserves_exact_large_integer_object_results() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot
    from shared.uncertainty import UncertainValue

    value = mp.mpf("123456789012345678901234567890")
    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [[mp.mpf("1")]],
            "results": [UncertainValue(value, mp.mpf("1"))],
            "formula": "A",
            "precision_used": 80,
        },
    )

    assert snapshot is not None
    first = snapshot["results"][0]
    assert first["value"] == str(int(value))
    assert first["uncertainty"] == "1"
    assert "e+" not in str(first["value"])


def test_core_uncertainty_snapshot_preserves_nonfinite_text_values() -> None:
    from datalab_core.uncertainty import (
        build_uncertainty_result_snapshot,
        render_uncertainty_snapshot_outputs,
    )
    from shared.uncertainty import UncertainValue

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [[mp.mpf("1")], [mp.mpf("2")], [mp.mpf("3")]],
            "results": [
                UncertainValue(mp.inf, mp.mpf("1")),
                UncertainValue(-mp.inf, mp.mpf("2")),
                UncertainValue(mp.nan, mp.mpf("3")),
            ],
            "formula": "A",
            "precision_used": 80,
        },
    )

    assert snapshot is not None
    assert [row["value"] for row in snapshot["results"]] == ["+inf", "-inf", "nan"]
    rendered = render_uncertainty_snapshot_outputs(snapshot)
    assert rendered is not None
    _text, csv_rows, _headers = rendered
    assert [row["value"] for row in csv_rows] == ["+inf", "-inf", "nan"]
    assert all(row["value"] != "0" for row in csv_rows)


def test_core_uncertainty_snapshot_accepts_core_payload_and_warning_string() -> None:
    from datalab_core.uncertainty import (
        build_uncertainty_request,
        build_uncertainty_result_snapshot,
        run_uncertainty,
    )

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("1.25",),),
        uncertainty_rows=(("0.05",),),
        formula="A",
        precision_digits=70,
    )
    envelope = run_uncertainty(request)
    payload = dict(envelope.payload)
    payload["warnings"] = "single warning"

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert snapshot["source"] == {"row_count": 1, "source_columns": ["A"]}
    assert snapshot["warnings"] == ["single warning"]
    assert snapshot["precision"]["compute_digits"] == 70
    assert snapshot["configuration"] == {
        "propagation": {
            "method": "taylor",
            "order": 1,
            "mc_samples": None,
            "mc_seed": None,
        }
    }
    first = snapshot["results"][0]
    assert first["value"] == "1.25"
    assert first["uncertainty"] == "0.05"
    assert first["contributions"] == {"A": "0.0025"}
    assert first["sensitivities"] == {
        "A": {
            "absolute": "1.0",
            "relative": "1.0",
            "relative_omission_reason": None,
        }
    }
    assert first["latex"] == "1.25 +/- 0.05"
    assert snapshot["diagnostic_rows"] == [
        {
            "key": "contribution.1.A",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.0025",
            "source": "A",
            "row_index": 1,
        },
        {
            "key": "contribution_total.A",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.0025",
            "uncertainty": "100.0%",
            "source": "A",
        },
        {
            "key": "contribution_percent.A",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "100.0%",
            "source": "A",
        },
        {
            "key": "contribution_cumulative_percent.A",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "100.0%",
            "source": "A",
        },
        {
            "key": "sensitivity_absolute.1.A",
            "label_key": "uncertainty.diagnostic.sensitivity_absolute",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "1.0",
            "source": "A",
            "row_index": 1,
        },
        {
            "key": "sensitivity_relative.1.A",
            "label_key": "uncertainty.diagnostic.sensitivity_relative",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "1.0",
            "source": "A",
            "row_index": 1,
        },
        {
            "key": "configuration.propagation.method",
            "label_key": "uncertainty.configuration.propagation.method",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "taylor",
        },
        {
            "key": "configuration.propagation.order",
            "label_key": "uncertainty.configuration.propagation.order",
            "severity": "info",
            "render_group": "diagnostic",
            "value": 1,
        },
        {
            "key": "configuration.propagation.mc_samples",
            "label_key": "uncertainty.configuration.propagation.mc_samples",
            "severity": "info",
            "render_group": "diagnostic",
        },
        {
            "key": "configuration.propagation.mc_seed",
            "label_key": "uncertainty.configuration.propagation.mc_seed",
            "severity": "info",
            "render_group": "diagnostic",
        },
    ]
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_normalizes_effective_taylor_metadata() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["1"]],
            "formula": "A",
            "precision_used": 50,
            "propagation": {
                "method": "unsupported-method",
                "order": 0,
                "mc_samples": 5000,
                "mc_seed": 123,
            },
            "results": [
                {
                    "value": "1",
                    "uncertainty": "0",
                    "contributions": {},
                },
            ],
        },
    )

    assert snapshot is not None
    assert snapshot["configuration"] == {
        "propagation": {
            "method": "taylor",
            "order": 1,
            "mc_samples": None,
            "mc_seed": None,
        }
    }
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["configuration.propagation.method"]["value"] == "taylor"
    assert diagnostic_rows["configuration.propagation.order"]["value"] == 1
    assert "value" not in diagnostic_rows["configuration.propagation.mc_samples"]
    assert "value" not in diagnostic_rows["configuration.propagation.mc_seed"]
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_omits_invalid_monte_carlo_metadata() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["1"]],
            "formula": "A",
            "precision_used": 50,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 1.5,
                "mc_seed": 123,
            },
            "results": [
                {
                    "value": "1",
                    "uncertainty": "0",
                    "contributions": {},
                },
            ],
        },
    )

    assert snapshot is not None
    assert "configuration" not in snapshot
    assert not any(str(row["key"]).startswith("configuration.propagation.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_fills_default_monte_carlo_sample_count() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["1"]],
            "formula": "A",
            "precision_used": 50,
            "propagation": {
                "method": "monte-carlo",
                "order": 1,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "1",
                    "uncertainty": "0",
                    "contributions": {},
                },
            ],
        },
    )

    assert snapshot is not None
    assert snapshot["configuration"] == {
        "propagation": {
            "method": "monte_carlo",
            "order": 1,
            "mc_samples": 5000,
            "mc_seed": None,
        }
    }
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["configuration.propagation.mc_samples"]["value"] == 5000
    assert "value" not in diagnostic_rows["configuration.propagation.mc_seed"]
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_maps_comparison_metadata_to_diagnostic_rows() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 400,
                "mc_seed": 11,
            },
            "results": [
                {
                    "value": "2.001",
                    "uncertainty": "0.1",
                    "contributions": {"A": "0.01"},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "absolute_result_tolerance": "1e-12",
                        "relative_result_tolerance": "1e-8",
                        "sample_count": 400,
                        "taylor_order": 1,
                        "taylor_mean": "2.0",
                        "taylor_std": "0.1",
                        "monte_carlo_mean": "2.001",
                        "monte_carlo_std": "0.1",
                        "monte_carlo_standard_error": "0.005",
                        "practical_floor": "0.00000002001",
                        "absolute_mean_difference": "0.001",
                        "mean_disagreement_threshold": "0.015",
                        "mean_disagreement": False,
                        "relative_std_difference": "0.0",
                        "relative_std_difference_omission_reason": None,
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    assert snapshot["results"][0]["comparison"]["absolute_result_tolerance"] == "1e-12"
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["contribution.1.A"]["value"] == "0.01"
    assert diagnostic_rows["configuration.propagation.method"]["value"] == "monte_carlo"
    assert diagnostic_rows["comparison.1.absolute_result_tolerance"] == {
        "key": "comparison.1.absolute_result_tolerance",
        "label_key": "uncertainty.diagnostic.comparison.absolute_result_tolerance",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "1e-12",
        "row_index": 1,
        "method": "taylor_vs_monte_carlo",
    }
    assert diagnostic_rows["comparison.1.relative_result_tolerance"]["value"] == "1e-8"
    assert diagnostic_rows["comparison.1.mean_disagreement"]["value"] == "false"
    assert diagnostic_rows["comparison.1.mean_disagreement_threshold"]["value"] == "0.015"
    assert diagnostic_rows["comparison.1.relative_std_difference"]["value"] == "0.0"
    assert "comparison.1.relative_std_difference_omitted" not in diagnostic_rows
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_emits_explicit_relative_std_omission_row() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 19,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.0",
                    "contributions": {},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "absolute_result_tolerance": "1e-12",
                        "relative_result_tolerance": "1e-8",
                        "sample_count": 100,
                        "taylor_order": 1,
                        "taylor_mean": "2.0",
                        "taylor_std": "0.0",
                        "monte_carlo_mean": "2.0",
                        "monte_carlo_std": "0.0",
                        "monte_carlo_standard_error": "0.0",
                        "practical_floor": "0.00000002",
                        "absolute_mean_difference": "0.0",
                        "mean_disagreement_threshold": "0.00000002",
                        "mean_disagreement": False,
                        "relative_std_difference": None,
                        "relative_std_difference_omission_reason": "zero_std",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert "comparison.1.relative_std_difference" not in diagnostic_rows
    assert diagnostic_rows["comparison.1.relative_std_difference_omitted"] == {
        "key": "comparison.1.relative_std_difference_omitted",
        "label_key": "uncertainty.diagnostic.comparison.relative_std_difference_omitted",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "zero_std",
        "row_index": 1,
        "method": "taylor_vs_monte_carlo",
        "message_key": "uncertainty.diagnostic.comparison.relative_std_difference_omitted.zero_std",
    }
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_tampered_or_non_monte_carlo_comparison_metadata() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    taylor_snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 1,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "comparison": {
                        "method": "anything",
                        "sample_count": -1,
                        "taylor_order": 1,
                        "taylor_mean": ["bad"],
                    },
                },
            ],
        },
    )
    assert taylor_snapshot is not None
    assert "comparison" not in taylor_snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in taylor_snapshot["diagnostic_rows"])

    monte_carlo_snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 400,
                "mc_seed": 11,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "sample_count": -1,
                        "taylor_order": 1,
                        "taylor_mean": ["bad"],
                    },
                },
            ],
        },
    )
    assert monte_carlo_snapshot is not None
    assert "comparison" not in monte_carlo_snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in monte_carlo_snapshot["diagnostic_rows"])
    assert not _contains_float(taylor_snapshot)
    assert not _contains_float(monte_carlo_snapshot)


def test_core_uncertainty_snapshot_rejects_comparison_metadata_that_conflicts_with_propagation() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    payload = {
        "headers": ["A"],
        "data_rows": [["2"]],
        "formula": "A",
        "precision_used": 60,
        "propagation": {
            "method": "monte_carlo",
            "order": 1,
            "mc_samples": 400,
            "mc_seed": 11,
        },
        "results": [
            {
                "value": "2.0",
                "uncertainty": "0.1",
                "contributions": {},
                "comparison": {
                    "method": "taylor_vs_monte_carlo",
                    "absolute_result_tolerance": "1e-12",
                    "relative_result_tolerance": "1e-8",
                    "sample_count": 999,
                    "taylor_order": 2,
                    "taylor_mean": "2.0",
                    "taylor_std": "0.1",
                    "monte_carlo_mean": "2.0",
                    "monte_carlo_std": "0.1",
                    "monte_carlo_standard_error": "0.005",
                    "practical_floor": "0.00000002",
                    "absolute_mean_difference": "0.0",
                    "mean_disagreement_threshold": "0.015",
                    "mean_disagreement": False,
                    "relative_std_difference": "0.0",
                    "relative_std_difference_omission_reason": None,
                },
            },
        ],
    }

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])

    result_payload = cast(list[dict[str, Any]], payload["results"])[0]
    comparison_payload = cast(dict[str, Any], result_payload["comparison"])
    comparison_payload["sample_count"] = 400
    comparison_payload["taylor_order"] = 1
    comparison_payload["absolute_result_tolerance"] = "0"
    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)

    comparison_payload["absolute_result_tolerance"] = "1e-12"
    comparison_payload["monte_carlo_mean"] = "888"
    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])

    comparison_payload["monte_carlo_mean"] = "2.000000000000000000000000000001"
    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])

    comparison_payload["monte_carlo_mean"] = "2.0"
    comparison_payload["monte_carlo_standard_error"] = "999"
    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_comparison_when_result_row_is_not_numeric() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    payload = {
        "headers": ["A"],
        "data_rows": [["2"]],
        "formula": "A",
        "precision_used": 60,
        "propagation": {
            "method": "monte_carlo",
            "order": 1,
            "mc_samples": 400,
            "mc_seed": 11,
        },
        "results": [
            {
                "value": "not numeric",
                "uncertainty": "0.1",
                "contributions": {},
                "comparison": {
                    "method": "taylor_vs_monte_carlo",
                    "absolute_result_tolerance": "1e-12",
                    "relative_result_tolerance": "1e-8",
                    "sample_count": 400,
                    "taylor_order": 1,
                    "taylor_mean": "2.0",
                    "taylor_std": "0.1",
                    "monte_carlo_mean": "2.0",
                    "monte_carlo_std": "0.1",
                    "monte_carlo_standard_error": "0.005",
                    "practical_floor": "0.00000002",
                    "absolute_mean_difference": "0.0",
                    "mean_disagreement_threshold": "0.015",
                    "mean_disagreement": False,
                    "relative_std_difference": "0.0",
                    "relative_std_difference_omission_reason": None,
                },
            },
        ],
    }

    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert snapshot["results"][0]["value"] == "not numeric"
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)

    result_payload = cast(list[dict[str, Any]], payload["results"])[0]
    result_payload["value"] = "2.0"
    result_payload["uncertainty"] = "not numeric"
    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert snapshot is not None
    assert snapshot["results"][0]["uncertainty"] == "not numeric"
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_maps_unavailable_comparison_to_diagnostic_row() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 3,
                "mc_samples": 100,
                "mc_seed": 23,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "absolute_result_tolerance": "1e-12",
                        "relative_result_tolerance": "1e-8",
                        "sample_count": 100,
                        "taylor_order": 3,
                        "comparison_unavailable_reason": "taylor_unavailable",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["comparison.1.unavailable"] == {
        "key": "comparison.1.unavailable",
        "label_key": "uncertainty.diagnostic.comparison.unavailable",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "taylor_unavailable",
        "row_index": 1,
        "method": "taylor_vs_monte_carlo",
        "message_key": "uncertainty.diagnostic.comparison.unavailable.taylor_unavailable",
    }
    assert "comparison.1.mean_disagreement" not in diagnostic_rows
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_unknown_comparison_unavailable_reason() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 3,
                "mc_samples": 100,
                "mc_seed": 23,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "absolute_result_tolerance": "1e-12",
                        "relative_result_tolerance": "1e-8",
                        "sample_count": 100,
                        "taylor_order": 3,
                        "comparison_unavailable_reason": "not_runtime_reason",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    assert "comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_maps_taylor_order_comparison_metadata_to_diagnostic_rows() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A * A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 2,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "4.1",
                    "uncertainty": "0.25",
                    "contributions": {},
                    "taylor_order_comparison": {
                        "method": "taylor_order_1_vs_2",
                        "order_low": 1,
                        "order_high": 2,
                        "order1_mean": "4.0",
                        "order1_std": "0.2",
                        "order2_mean": "4.1",
                        "order2_std": "0.25",
                        "absolute_mean_difference": "0.1",
                        "relative_std_difference": "0.2",
                        "relative_std_difference_omission_reason": None,
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["taylor_order_comparison.1.order_low"] == {
        "key": "taylor_order_comparison.1.order_low",
        "label_key": "uncertainty.diagnostic.taylor_order_comparison.order_low",
        "severity": "info",
        "render_group": "diagnostic",
        "value": 1,
        "row_index": 1,
        "method": "taylor_order_1_vs_2",
    }
    assert diagnostic_rows["taylor_order_comparison.1.order_high"]["value"] == 2
    assert diagnostic_rows["taylor_order_comparison.1.order1_mean"]["value"] == "4.0"
    assert diagnostic_rows["taylor_order_comparison.1.order2_std"]["value"] == "0.25"
    assert diagnostic_rows["taylor_order_comparison.1.relative_std_difference"]["value"] == "0.2"
    assert "taylor_order_comparison.1.relative_std_difference_omitted" not in diagnostic_rows
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_maps_taylor_order_comparison_relative_std_omission() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 2,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "2.0",
                    "uncertainty": "0.0",
                    "contributions": {},
                    "taylor_order_comparison": {
                        "method": "taylor_order_1_vs_2",
                        "order_low": 1,
                        "order_high": 2,
                        "order1_mean": "2.0",
                        "order1_std": "0.0",
                        "order2_mean": "2.0",
                        "order2_std": "0.0",
                        "absolute_mean_difference": "0.0",
                        "relative_std_difference": None,
                        "relative_std_difference_omission_reason": "zero_std",
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert diagnostic_rows["taylor_order_comparison.1.relative_std_difference_omitted"] == {
        "key": "taylor_order_comparison.1.relative_std_difference_omitted",
        "label_key": "uncertainty.diagnostic.taylor_order_comparison.relative_std_difference_omitted",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "zero_std",
        "row_index": 1,
        "method": "taylor_order_1_vs_2",
        "message_key": "uncertainty.diagnostic.taylor_order_comparison.relative_std_difference_omitted.zero_std",
    }
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_tampered_taylor_order_comparison_metadata() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A * A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 2,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "4.0",
                    "uncertainty": "0.2",
                    "contributions": {},
                    "taylor_order_comparison": {
                        "method": "taylor_order_1_vs_2",
                        "order_low": 1,
                        "order_high": 2,
                        "order1_mean": "4.0",
                        "order1_std": "0.2",
                        "order2_mean": "4.1",
                        "order2_std": "0.25",
                        "absolute_mean_difference": "0.1",
                        "relative_std_difference": "0.2",
                        "relative_std_difference_omission_reason": None,
                        "comparison_unavailable_reason": "not_runtime_reason",
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    assert "taylor_order_comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("taylor_order_comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_tampered_taylor_order_comparison_order_fields() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A * A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 2,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "4.0",
                    "uncertainty": "0.2",
                    "contributions": {},
                    "taylor_order_comparison": {
                        "method": "taylor_order_1_vs_2",
                        "order_low": 1,
                        "order_high": 3,
                        "order1_mean": "4.0",
                        "order1_std": "0.2",
                        "order2_mean": "4.1",
                        "order2_std": "0.25",
                        "absolute_mean_difference": "0.1",
                        "relative_std_difference": "0.2",
                        "relative_std_difference_omission_reason": None,
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    assert "taylor_order_comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("taylor_order_comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_forged_taylor_order2_row_mismatch() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A * A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 2,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "4.0",
                    "uncertainty": "0.2",
                    "contributions": {},
                    "taylor_order_comparison": {
                        "method": "taylor_order_1_vs_2",
                        "order_low": 1,
                        "order_high": 2,
                        "order1_mean": "4.0",
                        "order1_std": "0.2",
                        "order2_mean": "4.1",
                        "order2_std": "0.25",
                        "absolute_mean_difference": "0.1",
                        "relative_std_difference": "0.2",
                        "relative_std_difference_omission_reason": None,
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    assert "taylor_order_comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("taylor_order_comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_rejects_unexpected_relative_std_omission_reason_when_value_present() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A * A",
            "precision_used": 60,
            "propagation": {
                "method": "taylor",
                "order": 2,
                "mc_samples": None,
                "mc_seed": None,
            },
            "results": [
                {
                    "value": "4.0",
                    "uncertainty": "0.2",
                    "contributions": {},
                    "taylor_order_comparison": {
                        "method": "taylor_order_1_vs_2",
                        "order_low": 1,
                        "order_high": 2,
                        "order1_mean": "4.0",
                        "order1_std": "0.2",
                        "order2_mean": "4.0",
                        "order2_std": "0.2",
                        "absolute_mean_difference": "0.0",
                        "relative_std_difference": "0.0",
                        "relative_std_difference_omission_reason": "zero_std",
                    },
                }
            ],
        },
    )

    assert snapshot is not None
    assert "taylor_order_comparison" not in snapshot["results"][0]
    assert not any(str(row["key"]).startswith("taylor_order_comparison.") for row in snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_emits_explicit_mean_disagreement_omission_row() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["2"]],
            "formula": "A",
            "precision_used": 60,
            "propagation": {
                "method": "monte_carlo",
                "order": 1,
                "mc_samples": 100,
                "mc_seed": 29,
            },
            "results": [
                {
                    "value": "nan",
                    "uncertainty": "0.1",
                    "contributions": {},
                    "comparison": {
                        "method": "taylor_vs_monte_carlo",
                        "absolute_result_tolerance": "1e-12",
                        "relative_result_tolerance": "1e-8",
                        "sample_count": 100,
                        "taylor_order": 1,
                        "taylor_mean": "2.0",
                        "taylor_std": "0.1",
                        "monte_carlo_mean": "nan",
                        "monte_carlo_std": "0.1",
                        "monte_carlo_standard_error": "0.01",
                        "practical_floor": "0.00000002",
                        "absolute_mean_difference": "nan",
                        "mean_disagreement_threshold": "0.03",
                        "mean_disagreement": None,
                        "mean_disagreement_omission_reason": "nonfinite_mean",
                        "relative_std_difference": "0.0",
                        "relative_std_difference_omission_reason": None,
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    diagnostic_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert "comparison.1.mean_disagreement" not in diagnostic_rows
    assert diagnostic_rows["comparison.1.mean_disagreement_omitted"] == {
        "key": "comparison.1.mean_disagreement_omitted",
        "label_key": "uncertainty.diagnostic.comparison.mean_disagreement_omitted",
        "severity": "info",
        "render_group": "diagnostic",
        "value": "nonfinite_mean",
        "row_index": 1,
        "method": "taylor_vs_monte_carlo",
        "message_key": "uncertainty.diagnostic.comparison.mean_disagreement_omitted.nonfinite_mean",
    }
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_skips_invalid_contribution_diagnostics() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["1"]],
            "formula": "A",
            "precision_used": 50,
            "results": [
                {
                    "value": "1",
                    "uncertainty": "0.5",
                    "contributions": {
                        "bad_nan": "nan",
                        "bad_pos_inf": "+inf",
                        "bad_neg_inf": "-inf",
                        "bad_text": "not numeric",
                        "bad_negative": "-0.1",
                        "ok": "0.25",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    assert snapshot["results"][0]["contributions"] == {
        "bad_nan": "nan",
        "bad_pos_inf": "+inf",
        "bad_neg_inf": "-inf",
        "bad_text": "not numeric",
        "bad_negative": "-0.1",
        "ok": "0.25",
    }
    assert snapshot["diagnostic_rows"] == [
        {
            "key": "contribution.1.ok",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.25",
            "source": "ok",
            "row_index": 1,
        },
        {
            "key": "contribution_total.ok",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.25",
            "uncertainty": "100.0%",
            "source": "ok",
        },
        {
            "key": "contribution_percent.ok",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "100.0%",
            "source": "ok",
        },
        {
            "key": "contribution_cumulative_percent.ok",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "100.0%",
            "source": "ok",
        },
    ]
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_sanitizes_contribution_diagnostic_keys() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A"],
            "data_rows": [["1"]],
            "formula": "A",
            "precision_used": 50,
            "results": [
                {
                    "value": "1",
                    "uncertainty": "0.5",
                    "contributions": {
                        "A.B": "0.01",
                        "A B": "0.02",
                        "变量/α": "0.03",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    diagnostic_rows = snapshot["diagnostic_rows"]
    assert diagnostic_rows == [
        {
            "key": "contribution.1.A_B",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.01",
            "source": "A.B",
            "row_index": 1,
        },
        {
            "key": "contribution.1.A_B_2",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.02",
            "source": "A B",
            "row_index": 1,
        },
        {
            "key": "contribution.1.item",
            "label_key": "uncertainty.diagnostic.contribution_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.03",
            "source": "变量/α",
            "row_index": 1,
        },
        {
            "key": "contribution_total.item",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.03",
            "uncertainty": "50.0%",
            "source": "变量/α",
        },
        {
            "key": "contribution_total.A_B_2",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.02",
            "uncertainty": "33.3333333333333%",
            "source": "A B",
        },
        {
            "key": "contribution_total.A_B",
            "label_key": "uncertainty.diagnostic.contribution_total_variance",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "0.01",
            "uncertainty": "16.6666666666667%",
            "source": "A.B",
        },
        {
            "key": "contribution_percent.item",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "50.0%",
            "source": "变量/α",
        },
        {
            "key": "contribution_percent.A_B_2",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "33.3333333333333%",
            "source": "A B",
        },
        {
            "key": "contribution_percent.A_B",
            "label_key": "uncertainty.diagnostic.contribution_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "16.6666666666667%",
            "source": "A.B",
        },
        {
            "key": "contribution_cumulative_percent.item",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "50.0%",
            "source": "变量/α",
        },
        {
            "key": "contribution_cumulative_percent.A_B_2",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "83.3333333333333%",
            "source": "A B",
        },
        {
            "key": "contribution_cumulative_percent.A_B",
            "label_key": "uncertainty.diagnostic.contribution_cumulative_percent",
            "severity": "info",
            "render_group": "diagnostic",
            "value": "100.0%",
            "source": "A.B",
        },
    ]
    keys = [str(row["key"]) for row in diagnostic_rows]
    assert len(keys) == len(set(keys))
    assert all(key.replace(".", "").replace("_", "").replace("-", "").isalnum() for key in keys)
    assert not _contains_float(snapshot)


def test_core_uncertainty_snapshot_zero_total_contribution_percent_rows_are_zero() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot

    snapshot = build_uncertainty_result_snapshot(
        "error",
        {
            "headers": ["A", "B"],
            "data_rows": [["1"]],
            "formula": "A + B",
            "precision_used": 50,
            "results": [
                {
                    "value": "1",
                    "uncertainty": "0",
                    "contributions": {
                        "A": "0",
                        "B": "0",
                    },
                },
            ],
        },
    )

    assert snapshot is not None
    aggregate_rows = [
        row
        for row in snapshot["diagnostic_rows"]
        if str(row["key"]).startswith(("contribution_total.", "contribution_percent.", "contribution_cumulative_percent."))
    ]
    assert [row["key"] for row in aggregate_rows] == [
        "contribution_total.A",
        "contribution_total.B",
        "contribution_percent.A",
        "contribution_percent.B",
        "contribution_cumulative_percent.A",
        "contribution_cumulative_percent.B",
    ]
    assert [row["source"] for row in aggregate_rows] == ["A", "B", "A", "B", "A", "B"]
    assert [row.get("uncertainty") for row in aggregate_rows[:2]] == ["0%", "0%"]
    assert [row["value"] for row in aggregate_rows[2:]] == ["0%", "0%", "0%", "0%"]
    assert not _contains_float(snapshot)


def test_core_uncertainty_contribution_aggregates_use_snapshot_precision_not_ambient() -> None:
    from datalab_core.uncertainty import build_uncertainty_result_snapshot
    from shared.precision import precision_guard

    with precision_guard(10):
        snapshot = build_uncertainty_result_snapshot(
            "error",
            {
                "headers": ["A"],
                "data_rows": [["1"], ["2"]],
                "formula": "A",
                "precision_used": 80,
                "results": [
                    {
                        "value": "1",
                        "uncertainty": "0.5",
                        "contributions": {
                            "A": "1.00000000001",
                            "B": "1.00000000002",
                        },
                    },
                    {
                        "value": "2",
                        "uncertainty": "0.5",
                        "contributions": {
                            "A": "0.00000000000000000001",
                        },
                    },
                ],
            },
        )

    assert snapshot is not None
    aggregate_rows = [
        row for row in snapshot["diagnostic_rows"] if str(row["key"]).startswith("contribution_total.")
    ]
    assert [row["source"] for row in aggregate_rows] == ["B", "A"]
    assert str(aggregate_rows[1]["value"]).startswith("1.00000000001000000001")
    percent_rows = [
        row for row in snapshot["diagnostic_rows"] if str(row["key"]).startswith("contribution_percent.")
    ]
    cumulative_rows = [
        row for row in snapshot["diagnostic_rows"] if str(row["key"]).startswith("contribution_cumulative_percent.")
    ]
    assert [row["source"] for row in percent_rows] == ["B", "A"]
    assert [row["value"] for row in percent_rows] == ["50.00000000025%", "49.99999999975%"]
    assert [row["source"] for row in cumulative_rows] == ["B", "A"]
    assert [row["value"] for row in cumulative_rows] == ["50.00000000025%", "100.0%"]
    assert not _contains_float(snapshot)


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
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula="A", segments=((0.0, 1),))  # type: ignore[arg-type]


def test_core_uncertainty_display_only_units_reach_payload_and_snapshot() -> None:
    from datalab_core.uncertainty import (
        build_uncertainty_request,
        build_uncertainty_result_snapshot,
        render_uncertainty_snapshot_outputs,
        run_uncertainty,
    )

    request = build_uncertainty_request(
        headers=("A",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        formula="A",
        units={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": "m"},
            "outputs": {"result": "m"},
        },
    )

    payload = run_uncertainty(request).payload
    snapshot = build_uncertainty_result_snapshot("error", payload)

    assert payload["units"]["inputs"] == {"A": {"unit": "m"}}
    assert payload["units"]["outputs"] == {"result": {"unit": "m"}}
    assert snapshot is not None
    assert snapshot["units"] == payload["units"]
    rendered = render_uncertainty_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, csv_headers = rendered
    assert "| # | Value [m] | Uncertainty [m] | LaTeX |" in text
    assert csv_headers == ["index", "value", "uncertainty", "latex", "output_unit"]
    assert csv_rows[0]["output_unit"] == "m"
    assert snapshot["display"]["csv_headers"] == csv_headers
    assert not _contains_float(snapshot)


def test_core_uncertainty_validate_expression_requires_pint_at_request_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations
    from datalab_core.uncertainty import build_uncertainty_request

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", False)

    with pytest.raises(ValueError, match="requires pint"):
        build_uncertainty_request(
            headers=("A",),
            rows=(("1",),),
            formula="A",
            units={"enabled": True, "mode": "validate_expression", "inputs": {"A": "m"}},
        )


def test_core_uncertainty_validate_expression_requires_pint_at_run_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.uncertainty import run_uncertainty

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", False)
    request = ComputeJobRequest(
        mode=JobMode.UNCERTAINTY,
        inputs={
            "headers": ["A"],
            "values": [["1"]],
            "uncertainties": [["0"]],
            "constants": {},
            "formula": "A",
            "propagation": {"method": "taylor", "order": 1, "mc_samples": None, "mc_seed": None},
            "collect_monte_carlo_distribution": False,
            "segments": [[0, 1]],
            "units": {"enabled": True, "mode": "validate_expression", "inputs": {"A": "m"}},
        },
    )

    with pytest.raises(ValueError, match="requires pint"):
        run_uncertainty(request)


def test_core_uncertainty_validate_expression_rejects_incompatible_units_before_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datalab_core.uncertainty as uncertainty
    import shared.unit_annotations as annotations

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", True)

    def fail_if_called(*_args: object, **_kwargs: object) -> list[object]:
        raise AssertionError("unit validation must run before numeric evaluation")

    monkeypatch.setattr(uncertainty, "apply_formula_to_data", fail_if_called)
    request = uncertainty.build_uncertainty_request(
        headers=("A", "B"),
        rows=(("1", "2"),),
        formula="A + B",
        units={
            "enabled": True,
            "mode": "validate_expression",
            "inputs": {"A": "m", "B": "s"},
            "outputs": {"result": "m"},
        },
    )

    with pytest.raises(ValueError, match="unit validation failed"):
        uncertainty.run_uncertainty(request)


def test_core_uncertainty_validate_expression_accepts_aliases_constants_and_output_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shared.unit_annotations as annotations
    from datalab_core.uncertainty import build_uncertainty_request, run_uncertainty

    monkeypatch.setattr(annotations.units_backend, "HAS_PINT", True)
    request = build_uncertainty_request(
        headers=("Distance",),
        rows=(("2",),),
        uncertainty_rows=(("0.1",),),
        constants={"offset": {"value": "3", "uncertainty": "0.2"}},
        formula="x1 + offset",
        units={
            "enabled": True,
            "mode": "validate_expression",
            "inputs": {"Distance": "m"},
            "constants": {"offset": "m"},
            "outputs": {"result": "m"},
        },
    )

    payload = run_uncertainty(request).payload

    assert payload["results"][0]["value"] == "5.0"
    assert payload["units"]["mode"] == "validate_expression"


@pytest.mark.parametrize("segment", [(("0", 1),), ((True, 1),), ((0.0, 1),)])
def test_core_uncertainty_request_builder_rejects_non_integer_segment_bounds(
    segment: tuple[tuple[object, int], ...],
) -> None:
    from datalab_core.uncertainty import build_uncertainty_request

    with pytest.raises(TypeError):
        build_uncertainty_request(headers=("A",), rows=(("1",),), formula="A", segments=segment)  # type: ignore[arg-type]


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
            precision_digits=precision_digits,  # type: ignore[arg-type]
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
