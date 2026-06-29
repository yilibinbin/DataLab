from __future__ import annotations

import json
from collections.abc import Callable, Mapping

import mpmath as mp
import pytest
from typing import Any, cast


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(item) for item in value)
    return False


def test_root_solving_number_payload_rejects_json_float_inputs() -> None:
    from shared.root_solving_engine import _deserialize_root_value
    from shared.root_solving_engine import _number_from_payload

    with pytest.raises(TypeError, match="JSON floats"):
        _number_from_payload(1.25)
    with pytest.raises(TypeError, match="JSON floats"):
        _number_from_payload({"kind": "real", "value": 1.25})
    with pytest.raises(TypeError, match="JSON floats"):
        _number_from_payload({"kind": "complex", "real": "1", "imag": 0.25})
    with pytest.raises(TypeError, match="JSON floats"):
        _deserialize_root_value(
            {
                "name": "x",
                "value": {"kind": "real", "value": "1"},
                "contributions": {"A": 1.25},
            }
        )


def test_core_root_solving_request_builder_creates_string_payload() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.root_solving import build_root_solving_request

    request = build_root_solving_request(
        equations=("x^2 - A", "y - C"),
        unknown_rows=(
            {"name": "x", "initial": mp.mpf("2.5"), "lower": "0", "upper": "10", "source": "manual"},
            {"name": "y", "initial": "1.0", "lower": "", "upper": "", "source": "detected"},
            {"source": "detected"},
        ),
        data_headers=("A",),
        data_rows=(("4.00000000000000000001(2)",),),
        constants_enabled=True,
        constants_rows={"C": "1.0(1)"},
        constants_view="text",
        constants_text="C 1.0(1)",
        mode="system",
        scan_config={
            "enabled": True,
            "max_roots": 20,
            "sample_count": 200,
            "residual_tolerance": "1e-30",
            "cluster_tolerance": "",
        },
        uncertainty_options={
            "method": "taylor",
            "taylor_order": 2,
            "monte_carlo_samples": 3000,
            "monte_carlo_seed": "42",
        },
        units={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": "J"},
            "constants": {"C": "J"},
            "outputs": {"x": "m", "y": "s"},
        },
        precision_digits=80,
        display_digits=12,
        uncertainty_digits=2,
        parallel={"max_workers": 4, "reserved_cores": 1, "chunk_size": mp.mpf("2.5")},
        request_id="root-core",
    )

    assert request.mode is JobMode.ROOT_SOLVING
    assert request.request_id == "root-core"
    assert request.options.precision_digits == 80
    assert request.options.uncertainty_digits == 2
    assert request.options.parallel == {"max_workers": 4, "reserved_cores": 1, "chunk_size": "2.5"}
    assert request.inputs["equations"] == ["x^2 - A", "y - C"]
    assert request.inputs["unknown_rows"] == [
        {"name": "x", "initial": "2.5", "lower": "0", "upper": "10", "source": "manual"},
        {"name": "y", "initial": "1.0", "lower": "", "upper": "", "source": "detected"},
    ]
    assert request.inputs["data_headers"] == ["A"]
    assert request.inputs["data_rows"] == [["4.00000000000000000001(2)"]]
    assert request.inputs["constants_enabled"] is True
    assert request.inputs["constants_rows"] == [{"name": "C", "value": "1.0(1)"}]
    assert request.inputs["constants_view"] == "text"
    assert request.inputs["constants_text"] == "C 1.0(1)"
    assert request.inputs["mode"] == "system"
    assert request.inputs["scan_config"] == {
        "enabled": True,
        "max_roots": 20,
        "sample_count": 200,
        "residual_tolerance": "1e-30",
        "cluster_tolerance": "",
    }
    assert request.inputs["uncertainty_options"] == {
        "method": "taylor",
        "taylor_order": 2,
        "monte_carlo_samples": 3000,
        "monte_carlo_seed": "42",
    }
    assert request.inputs["units"] == {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"A": {"unit": "J"}},
        "constants": {"C": {"unit": "J"}},
        "parameters": {},
        "outputs": {"x": {"unit": "m"}, "y": {"unit": "s"}},
    }
    assert request.inputs["display_digits"] == 12


def test_core_root_solving_rejects_active_unit_modes() -> None:
    from datalab_core.root_solving import build_root_solving_request

    with pytest.raises(ValueError, match="root_solving units only support display_only"):
        build_root_solving_request(
            equations=("x^2 - A",),
            unknown_rows=({"name": "x", "initial": "2"},),
            data_headers=("A",),
            data_rows=(("4",),),
            units={"enabled": True, "mode": "validate_expression"},
        )


def test_core_root_solving_handler_runs_scalar_batch_request() -> None:
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.root_solving import (
        build_root_solving_request,
        root_batch_payload_to_result,
        run_root_solving,
    )

    request = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=("A",),
        data_rows=(("4",),),
        mode="scalar",
        units={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": "J"},
            "outputs": {"x": "m"},
        },
        precision_digits=50,
        display_digits=12,
        request_id="root-core-run",
    )

    result = run_root_solving(request)

    assert result.status is ResultStatus.SUCCEEDED
    batch = root_batch_payload_to_result(result.payload["batch"])
    assert batch.headers == ("A",)
    assert len(batch.rows) == 1
    assert batch.rows[0].result is not None
    assert mp.almosteq(batch.rows[0].result.roots[0].value, mp.mpf("2"), abs_eps=mp.mpf("1e-30"))
    rows = analysis_rows_from_json(result.payload["analysis_rows"])
    rows_by_key = {row.key: row for row in rows}
    assert rows_by_key["root_input_row_count"].value == 1
    assert rows_by_key["roots_count"].value == 1
    assert rows_by_key["requested_mode"].value == "scalar"
    assert rows_by_key["resolved_mode.0"].value == "scalar"
    assert rows_by_key["backend.0"].value in {"mpmath", "scipy"}
    assert rows_by_key["residual_norm.0"].value == "0.0"
    assert rows_by_key["residual_norm.0"].render_group == "diagnostic"
    assert rows_by_key["solver_status.0"].value == "converged"
    assert rows_by_key["initial_guess_summary.0"].value == "x initial=2 lower=0 upper=10"
    assert not _contains_float(result.payload["analysis_rows"])
    assert result.payload["units"]["outputs"] == {"x": {"unit": "m"}}


def test_core_root_snapshot_renders_from_semantic_batch_payload() -> None:
    from datalab_core.root_solving import (
        build_root_result_snapshot,
        build_root_solving_request,
        render_root_snapshot_outputs,
        run_root_solving,
    )

    request = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=("A",),
        data_rows=(("4",),),
        mode="scalar",
        precision_digits=50,
        display_digits=12,
        uncertainty_digits=2,
    )
    envelope = run_root_solving(request)
    payload = {
        "batch": envelope.payload["batch"],
        "display_digits": 12,
        "uncertainty_digits": 2,
        "language": "en",
        "units": {
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": "J"},
            "outputs": {"x": "m"},
        },
        "markdown": "stale rendered cache must not be reused",
        "csv_rows": [{"name": "stale"}],
        "csv_headers": ["stale"],
    }

    snapshot = build_root_result_snapshot(
        "root_solving",
        payload,
        overview_state="complete",
        precision={"display_digits": 12, "compute_digits": 50},
    )

    assert snapshot is not None
    assert snapshot["schema"] == "datalab.result_snapshot.root_solving"
    assert snapshot["schema_version"] == 1
    assert snapshot["family"] == "root_solving"
    assert snapshot["compatibility"]["result_cache_kind"] == "root_solving"
    assert snapshot["compatibility"]["rendered_caches_authoritative"] is False
    assert snapshot["display"]["display_digits"] == 12
    assert snapshot["display"]["uncertainty_digits"] == 2
    assert snapshot["display"]["language"] == "en"
    assert snapshot["source"]["row_count"] == 1
    assert snapshot["source"]["roots_count"] == 1
    assert snapshot["units"]["outputs"] == {"x": {"unit": "m"}}
    assert {row["key"] for row in snapshot["metric_rows"]} >= {"root_input_row_count", "roots_count"}
    assert {row["key"] for row in snapshot["diagnostic_rows"]} >= {
        "requested_mode",
        "resolved_mode.0",
        "backend.0",
        "residual_norm.0",
        "solver_status.0",
        "initial_guess_summary.0",
    }
    assert not _contains_float(snapshot["diagnostic_rows"])
    assert snapshot["row_flags"] == []

    rendered = render_root_snapshot_outputs(snapshot)

    assert rendered is not None
    text, csv_rows, csv_headers = rendered
    assert "stale rendered cache" not in text
    assert csv_headers[:3] == ["input_row_index", "root_index", "A"]
    assert "name" in csv_headers
    assert "root_unit" in csv_headers
    assert "value" in csv_headers
    assert "failure" in csv_headers
    assert csv_rows[0]["name"] == "x"
    assert csv_rows[0]["root_unit"] == "m"
    assert csv_rows[0]["A"] == "4"
    assert csv_rows[0]["value"].startswith("2")
    assert "| input_row_index | root_index | A | name | unit | value | classification_tags | backend |" in text


def test_core_root_snapshot_deserializes_batch_under_snapshot_precision() -> None:
    from datalab_core.root_solving import build_root_result_snapshot, render_root_snapshot_outputs
    from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue
    from shared.root_solving_engine import serialize_root_batch_result

    value_text = "1.234567890123456789012345678901234567890123456789"
    with mp.mp.workdps(90):
        batch = RootBatchResult(
            rows=(
                RootBatchRowResult(
                    row_index=None,
                    source_values={},
                    result=RootResult(
                        roots=(RootValue(name="x", value=mp.mpf(value_text)),),
                        backend="mpmath",
                        mode="scalar",
                        residual_norm=mp.mpf("0"),
                        details={"root_classification_tags": {"0": ["unclassified"]}},
                    ),
                ),
            ),
        )
        batch_payload = serialize_root_batch_result(batch, digits=80)

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": batch_payload,
            "display_digits": 45,
            "uncertainty_digits": 1,
            "language": "en",
        },
        precision={"compute_digits": 90},
    )
    assert snapshot is not None

    previous_dps = mp.mp.dps
    try:
        mp.mp.dps = 15
        rendered = render_root_snapshot_outputs(snapshot)
    finally:
        mp.mp.dps = previous_dps

    assert rendered is not None
    text, csv_rows, csv_headers = rendered
    assert "classification_tags" in csv_headers
    assert csv_rows[0]["value"].startswith("1.23456789012345678901234567890123456789012")
    assert csv_rows[0]["classification_tags"] == "unclassified"
    assert "| unclassified | mpmath | scalar |" in text
    assert snapshot["diagnostic_rows"]
    assert any(
        row["key"] == "classification_tags.0.0" and row["value"] == "unclassified"
        for row in snapshot["diagnostic_rows"]
    )


def test_core_root_snapshot_rebuilds_analysis_rows_from_legacy_batch_payload() -> None:
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    request = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=("A",),
        data_rows=(("4",),),
        mode="scalar",
        precision_digits=50,
    )
    envelope = run_root_solving(request)
    legacy_payload = {
        "batch": envelope.payload["batch"],
        "display_digits": 12,
        "uncertainty_digits": 2,
        "language": "en",
        "analysis_rows": [{"key": "broken", "label_key": "root.bad", "value": 1.25}],
    }

    snapshot = build_root_result_snapshot(
        "root_solving",
        legacy_payload,
        precision={"compute_digits": 50},
    )

    assert snapshot is not None
    assert {row["key"] for row in snapshot["metric_rows"]} >= {"root_input_row_count", "roots_count"}
    assert any(row["key"] == "residual_norm.0" for row in snapshot["diagnostic_rows"])
    assert not any(row["key"] == "broken" for row in snapshot["metric_rows"])


def test_core_root_snapshot_rebuilds_foreign_valid_analysis_rows() -> None:
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    request = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=("A",),
        data_rows=(("4",),),
        mode="scalar",
        precision_digits=50,
    )
    envelope = run_root_solving(request)

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": envelope.payload["batch"],
            "analysis_rows": [
                {
                    "key": "row_count",
                    "label_key": "statistics.metric.row_count",
                    "value": 999,
                    "severity": "info",
                    "render_group": "metric",
                }
            ],
            "compute_digits": 50,
        },
        precision={"compute_digits": 50},
    )

    assert snapshot is not None
    metric_rows = {row["key"]: row for row in snapshot["metric_rows"]}
    assert metric_rows["root_input_row_count"]["value"] == 1
    assert metric_rows["roots_count"]["value"] == 1
    assert "row_count" not in metric_rows
    assert any(row["key"] == "residual_norm.0" for row in snapshot["diagnostic_rows"])


def test_core_root_snapshot_rebuilds_malformed_root_like_analysis_rows() -> None:
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    request = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=("A",),
        data_rows=(("4",),),
        mode="scalar",
        precision_digits=50,
    )
    envelope = run_root_solving(request)

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": envelope.payload["batch"],
            "analysis_rows": [
                {
                    "key": "root_input_row_count",
                    "label_key": "root_solving.diagnostic.backend",
                    "value": 1,
                    "severity": "info",
                    "render_group": "metric",
                },
                {
                    "key": "roots_count",
                    "label_key": "root_solving.diagnostic.backend",
                    "value": 1,
                    "severity": "info",
                    "render_group": "metric",
                },
            ],
            "compute_digits": 50,
        },
        precision={"compute_digits": 50},
    )

    assert snapshot is not None
    metric_rows = {row["key"]: row for row in snapshot["metric_rows"]}
    assert metric_rows["root_input_row_count"]["label_key"] == "root_solving.metric.input_row_count"
    assert metric_rows["roots_count"]["label_key"] == "root_solving.metric.roots_count"
    assert {row["key"] for row in snapshot["diagnostic_rows"]} >= {
        "requested_mode",
        "resolved_mode.0",
        "backend.0",
        "residual_norm.0",
    }


def test_core_root_snapshot_preserves_auto_requested_mode_and_rebuilds_tampered_rows() -> None:
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    cases = (
        build_root_solving_request(
            equations=("x^2 - A",),
            unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
            data_headers=("A",),
            data_rows=(("4",),),
            mode="auto",
            precision_digits=50,
        ),
        build_root_solving_request(
            equations=("x + y - 3", "x - y - 1"),
            unknown_rows=({"name": "x", "initial": "1"}, {"name": "y", "initial": "1"}),
            mode="auto",
            precision_digits=16,
        ),
    )
    for request in cases:
        envelope = run_root_solving(request)
        assert envelope.payload["mode"] == "auto"

        snapshot = build_root_result_snapshot(
            "root_solving",
            envelope.payload,
            precision={"compute_digits": envelope.payload["precision_used"]},
        )

        assert snapshot is not None
        rows_by_key = {row["key"]: row for row in snapshot["diagnostic_rows"]}
        assert rows_by_key["requested_mode"]["value"] == "auto"

        tampered_rows = [
            {**row, "value": "scalar"}
            if row.get("key") == "requested_mode"
            else dict(row)
            for row in envelope.payload["analysis_rows"]
        ]
        tampered_payload = {**envelope.payload, "analysis_rows": tampered_rows}
        tampered_snapshot = build_root_result_snapshot(
            "root_solving",
            tampered_payload,
            precision={"compute_digits": envelope.payload["precision_used"]},
        )

        assert tampered_snapshot is not None
        tampered_rows_by_key = {row["key"]: row for row in tampered_snapshot["diagnostic_rows"]}
        assert tampered_rows_by_key["requested_mode"]["value"] == "auto"


def test_core_root_snapshot_rebuilds_warning_rows_with_unstable_message_keys() -> None:
    from datalab_core.results import analysis_rows_to_json
    from datalab_core.root_solving import build_root_result_snapshot, root_analysis_rows_from_batch
    from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue
    from shared.root_solving_engine import serialize_root_batch_result

    batch = RootBatchResult(
        warnings=("batch warning",),
        rows=(
            RootBatchRowResult(
                row_index=0,
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("1")),),
                    backend="mpmath",
                    mode="scalar",
                    warnings=("result warning",),
                ),
                warnings=("row warning",),
            ),
        ),
    )
    row_payload = analysis_rows_to_json(root_analysis_rows_from_batch(batch, requested_mode="scalar"))
    unstable_payload = [
        {
            **row,
            "message_key": str(row.get("value")),
        }
        if str(row.get("key", "")).startswith(("batch_warning.", "row_warning.", "result_warning."))
        else row
        for row in row_payload
    ]

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": serialize_root_batch_result(batch, digits=50),
            "analysis_rows": unstable_payload,
            "compute_digits": 50,
        },
        precision={"compute_digits": 50},
    )

    assert snapshot is not None
    rows_by_key = {row["key"]: row for row in snapshot["row_flags"]}
    assert rows_by_key["batch_warning.0"]["message_key"] == "root_solving.warning.batch"
    assert rows_by_key["batch_warning.0"]["value"] == "batch warning"
    assert rows_by_key["row_warning.0.0"]["message_key"] == "root_solving.warning.row"
    assert rows_by_key["row_warning.0.0"]["value"] == "row warning"
    assert rows_by_key["result_warning.0.0"]["message_key"] == "root_solving.warning.result"
    assert rows_by_key["result_warning.0.0"]["value"] == "result warning"


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, None),
        (True, None),
        (False, None),
        (float("nan"), None),
        (float("inf"), None),
        (-1, None),
        ("-1", None),
        (1.2, None),
        ("1.2", None),
        (0, 0),
        ("0", 0),
        (3, 3),
        ("3", 3),
    ),
)
def test_root_detail_int_accepts_only_nonnegative_exact_integer_counts(
    value: object,
    expected: int | None,
) -> None:
    from datalab_core.root_solving import _root_detail_int
    from root_solving.models import RootResult

    result = RootResult(roots=(), backend="scipy", mode="scalar", details={"count": value})

    assert _root_detail_int(result, "count") == expected


def test_root_analysis_rows_filter_invalid_scipy_counts_without_json_floats() -> None:
    from datalab_core.results import analysis_rows_to_json
    from datalab_core.root_solving import root_analysis_rows_from_batch
    from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue

    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("1")),),
                    backend="scipy",
                    mode="scalar",
                    details={"scipy_iterations": "-1", "scipy_function_evaluations": "1.2"},
                ),
            ),
            RootBatchRowResult(
                row_index=1,
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("1")),),
                    backend="scipy",
                    mode="scalar",
                    details={"scipy_iterations": 0, "scipy_function_evaluations": "3"},
                ),
            ),
        )
    )

    row_payload = analysis_rows_to_json(root_analysis_rows_from_batch(batch, requested_mode="scalar"))

    assert not _contains_float(row_payload)
    rows_by_key = {row["key"]: row for row in row_payload}
    assert "scipy_iterations.0" not in rows_by_key
    assert "scipy_function_evaluations.0" not in rows_by_key
    assert rows_by_key["scipy_iterations.1"]["value"] == 0
    assert rows_by_key["scipy_function_evaluations.1"]["value"] == 3


def test_root_analysis_rows_include_failure_and_warning_flags_without_json_floats() -> None:
    from datalab_core.results import analysis_rows_to_json
    from datalab_core.root_solving import build_root_result_snapshot, root_analysis_rows_from_batch
    from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue
    from shared.root_solving_engine import serialize_root_batch_result

    batch = RootBatchResult(
        headers=("A",),
        warnings=("batch warning",),
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("2")),),
                    backend="mpmath",
                    mode="scalar",
                    residual_norm=mp.mpf("1.0e-40"),
                    warnings=("result warning",),
                    details={"root_classification_tags": {"0": ["bracketed_sign_change"]}},
                ),
                warnings=("row warning",),
            ),
            RootBatchRowResult(
                row_index=1,
                source_values={"A": "bad"},
                failure="could not solve row",
            ),
        ),
    )

    row_payload = analysis_rows_to_json(root_analysis_rows_from_batch(batch, requested_mode="auto"))
    assert json.dumps(row_payload)
    assert not _contains_float(row_payload)
    rows_by_key = {row["key"]: row for row in row_payload}
    assert rows_by_key["residual_norm.0"]["value"] == "1.0e-40"
    assert rows_by_key["failed_input_row.1"]["severity"] == "error"
    assert rows_by_key["row_warning.0.0"]["value"] == "row warning"
    assert rows_by_key["row_warning.0.0"]["message_key"] == "root_solving.warning.row"
    assert rows_by_key["result_warning.0.0"]["value"] == "result warning"
    assert rows_by_key["result_warning.0.0"]["message_key"] == "root_solving.warning.result"
    assert rows_by_key["batch_warning.0"]["value"] == "batch warning"
    assert rows_by_key["batch_warning.0"]["message_key"] == "root_solving.warning.batch"
    assert rows_by_key["classification_tags.0.0"]["value"] == "bracketed_sign_change"

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": serialize_root_batch_result(batch, digits=80),
            "analysis_rows": row_payload,
            "compute_digits": 80,
        },
        precision={"compute_digits": 80},
    )

    assert snapshot is not None
    assert not _contains_float(snapshot["metric_rows"])
    assert not _contains_float(snapshot["diagnostic_rows"])
    assert not _contains_float(snapshot["row_flags"])
    assert {row["key"] for row in snapshot["row_flags"]} >= {
        "failed_input_row.1",
        "row_warning.0.0",
        "result_warning.0.0",
        "batch_warning.0",
    }


def test_root_analysis_rows_include_quality_diagnostics_without_json_floats() -> None:
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    request = build_root_solving_request(
        equations=("x + y - 3", "x - y - 1"),
        unknown_rows=({"name": "x", "initial": "1"}, {"name": "y", "initial": "1"}),
        mode="system",
        precision_digits=16,
    )
    envelope = run_root_solving(request)

    assert not _contains_float(envelope.payload)
    rows = analysis_rows_from_json(envelope.payload["analysis_rows"])
    rows_by_key = {row.key: row for row in rows}
    assert rows_by_key["solver_status.0"].value == "converged"
    assert rows_by_key["initial_guess_summary.0"].value == "x initial=1 lower= upper=; y initial=1 lower= upper="
    assert isinstance(rows_by_key["scipy_function_evaluations.0"].value, int)
    assert isinstance(rows_by_key["jacobian_condition.0"].value, str)
    assert rows_by_key["per_equation_residual.0.0"].value == "0.0"
    assert rows_by_key["per_equation_residual.0.1"].value == "0.0"
    assert rows_by_key["per_equation_residual.0.0"].render_group == "diagnostic"

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": envelope.payload["batch"],
            "analysis_rows": envelope.payload["analysis_rows"],
            "compute_digits": 16,
        },
        precision={"compute_digits": 16},
    )

    assert snapshot is not None
    snapshot_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    assert snapshot_rows["solver_status.0"]["value"] == "converged"
    assert isinstance(snapshot_rows["jacobian_condition.0"]["value"], str)
    assert snapshot_rows["per_equation_residual.0.0"]["value"] == "0.0"
    assert not _contains_float(snapshot["diagnostic_rows"])


def test_root_analysis_rows_include_scan_summary_in_payload_and_snapshot_without_json_floats() -> None:
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    request = build_root_solving_request(
        equations=("x**2 - 4",),
        unknown_rows=({"name": "x", "initial": "0", "lower": "-3", "upper": "3"},),
        mode="scan_multiple",
        scan_config={"sample_count": 8, "max_roots": 5},
        precision_digits=16,
    )
    envelope = run_root_solving(request)

    assert not _contains_float(envelope.payload)
    rows = analysis_rows_from_json(envelope.payload["analysis_rows"])
    rows_by_key = {row.key: row for row in rows}
    for key in (
        "scan_summary.0.lower",
        "scan_summary.0.upper",
        "scan_summary.0.sample_count",
        "scan_summary.0.max_roots",
        "scan_summary.0.accepted_roots_count",
    ):
        assert key in rows_by_key
        assert rows_by_key[key].render_group == "diagnostic"
    assert isinstance(rows_by_key["scan_summary.0.lower"].value, str)
    assert isinstance(rows_by_key["scan_summary.0.upper"].value, str)
    assert rows_by_key["scan_summary.0.sample_count"].value == 8
    assert rows_by_key["scan_summary.0.max_roots"].value == 5
    assert rows_by_key["scan_summary.0.accepted_roots_count"].value == 2

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": envelope.payload["batch"],
            "analysis_rows": envelope.payload["analysis_rows"],
            "compute_digits": 16,
        },
        precision={"compute_digits": 16},
    )

    assert snapshot is not None
    snapshot_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    for key in (
        "scan_summary.0.lower",
        "scan_summary.0.upper",
        "scan_summary.0.sample_count",
        "scan_summary.0.max_roots",
        "scan_summary.0.accepted_roots_count",
    ):
        assert key in snapshot_rows
    assert isinstance(snapshot_rows["scan_summary.0.lower"]["value"], str)
    assert isinstance(snapshot_rows["scan_summary.0.upper"]["value"], str)
    assert snapshot_rows["scan_summary.0.sample_count"]["value"] == 8
    assert snapshot_rows["scan_summary.0.max_roots"]["value"] == 5
    assert snapshot_rows["scan_summary.0.accepted_roots_count"]["value"] == 2
    assert not _contains_float(snapshot["diagnostic_rows"])


def test_root_analysis_rows_include_scan_evidence_in_payload_and_snapshot_without_json_floats() -> None:
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.root_solving import build_root_result_snapshot, build_root_solving_request, run_root_solving

    request = build_root_solving_request(
        equations=("x - 0.3",),
        unknown_rows=({"name": "x", "lower": "-1", "upper": "1"},),
        mode="scan_multiple",
        scan_config={"sample_count": 8, "max_roots": 5},
        precision_digits=16,
    )
    envelope = run_root_solving(request)

    assert not _contains_float(envelope.payload)
    rows = analysis_rows_from_json(envelope.payload["analysis_rows"])
    rows_by_key = {row.key: row for row in rows}
    expected = {
        "scan_evidence.0.0.kind": "bracketed_sign_change",
        "scan_evidence.0.0.left": "0.25",
        "scan_evidence.0.0.right": "0.5",
        "scan_evidence.0.0.left_value": "-0.05",
        "scan_evidence.0.0.right_value": "0.2",
    }
    for key, value in expected.items():
        assert rows_by_key[key].value == value
        assert rows_by_key[key].render_group == "diagnostic"

    snapshot = build_root_result_snapshot(
        "root_solving",
        {
            "batch": envelope.payload["batch"],
            "analysis_rows": envelope.payload["analysis_rows"],
            "compute_digits": 16,
        },
        precision={"compute_digits": 16},
    )

    assert snapshot is not None
    snapshot_rows = {row["key"]: row for row in snapshot["diagnostic_rows"]}
    for key, value in expected.items():
        assert snapshot_rows[key]["value"] == value
    assert not _contains_float(snapshot["diagnostic_rows"])


def test_scan_evidence_analysis_rows_filter_bool_and_float_values() -> None:
    from datalab_core.root_solving import root_analysis_rows_from_batch
    from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue

    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("0")),),
                    backend="scipy",
                    mode="scan_multiple",
                    details={
                        "scan_root_evidence": {
                            "0": {
                                "kind": "exact_sample",
                                "sample": "0.0",
                                "left": 0.0,
                                "right": True,
                                "left_value": 0,
                                "merged_candidates": 2,
                            },
                            "1": {"kind": "exact_sample", "sample": "1.0"},
                            "-1": {"kind": "exact_sample", "sample": "-1.0"},
                            "bad": {"kind": "exact_sample", "sample": "bad"},
                            "0.5": {"kind": "exact_sample", "sample": "0.5"},
                            "2": {"kind": "unknown", "sample": "2.0"},
                        }
                    },
                ),
            ),
            RootBatchRowResult(
                row_index=1,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("0")),),
                    backend="mpmath",
                    mode="scalar",
                    details={"scan_root_evidence": {"0": {"kind": "exact_sample", "sample": "0.0"}}},
                ),
            ),
            RootBatchRowResult(
                row_index=2,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("0")), RootValue("x", mp.mpf("1"))),
                    backend="scipy",
                    mode="scan_multiple",
                    details={"scan_root_evidence": {"1": {"kind": "unknown", "sample": "1.0"}}},
                ),
            ),
            RootBatchRowResult(
                row_index=3,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("0")), RootValue("x", mp.mpf("1"))),
                    backend="scipy",
                    mode="scan_multiple",
                    details={
                        "scan_root_evidence": {
                            0.5: {"kind": "exact_sample", "sample": "0.5"},
                            True: {"kind": "exact_sample", "sample": "1.0"},
                            "01": {"kind": "exact_sample", "sample": "01"},
                            " 0": {"kind": "exact_sample", "sample": "leading"},
                            "0 ": {"kind": "exact_sample", "sample": "trailing"},
                        }
                    },
                ),
            ),
            RootBatchRowResult(
                row_index=4,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("0")),),
                    backend="scipy",
                    mode="scan_multiple",
                    details={
                        "scan_root_evidence": {
                            "0": {"kind": "exact_sample", "sample": "0.0", "merged_candidates": "2"}
                        }
                    },
                ),
            ),
        )
    )

    rows_by_key = {row.key: row for row in root_analysis_rows_from_batch(batch, requested_mode="scan_multiple")}

    assert rows_by_key["scan_evidence.0.0.kind"].value == "exact_sample"
    assert rows_by_key["scan_evidence.0.0.sample"].value == "0.0"
    assert rows_by_key["scan_evidence.0.0.merged_candidates"].value == 2
    assert "scan_evidence.0.0.left" not in rows_by_key
    assert "scan_evidence.0.0.right" not in rows_by_key
    assert "scan_evidence.0.0.left_value" not in rows_by_key
    assert "scan_evidence.0.1.kind" not in rows_by_key
    assert "scan_evidence.0.-1.kind" not in rows_by_key
    assert "scan_evidence.0.2.kind" not in rows_by_key
    assert "scan_evidence.1.0.kind" not in rows_by_key
    assert "scan_evidence.2.1.kind" not in rows_by_key
    assert "scan_evidence.3.0.kind" not in rows_by_key
    assert "scan_evidence.3.1.kind" not in rows_by_key
    assert rows_by_key["scan_evidence.4.0.kind"].value == "exact_sample"
    assert rows_by_key["scan_evidence.4.0.sample"].value == "0.0"
    assert "scan_evidence.4.0.merged_candidates" not in rows_by_key


def test_core_root_snapshot_build_deserializes_metadata_under_snapshot_precision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datalab_core.root_solving as root_solving

    observed_dps: list[int] = []
    real_deserialize = cast(
        Callable[[Mapping[str, Any]], Any],
        getattr(root_solving, "deserialize_root_batch_result"),
    )

    def observing_deserialize(payload: Mapping[str, Any]) -> Any:
        observed_dps.append(mp.mp.dps)
        return real_deserialize(payload)

    monkeypatch.setattr(root_solving, "deserialize_root_batch_result", observing_deserialize)

    request = root_solving.build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2"},),
        data_headers=("A",),
        data_rows=(("4",),),
        precision_digits=80,
    )
    envelope = root_solving.run_root_solving(request)
    previous_dps = mp.mp.dps
    try:
        mp.mp.dps = 15
        snapshot = root_solving.build_root_result_snapshot(
            "root_solving",
            {
                "batch": envelope.payload["batch"],
                "compute_digits": 80,
                "display_digits": 40,
                "uncertainty_digits": 1,
                "language": "en",
            },
            precision={"compute_digits": 16},
        )
    finally:
        mp.mp.dps = previous_dps

    assert snapshot is not None
    assert snapshot["precision"]["compute_digits"] == 80
    assert observed_dps
    assert observed_dps[0] >= 80


def test_core_root_solving_request_builder_preserves_preparsed_mpf_precision() -> None:
    from datalab_core.root_solving import build_root_solving_request
    from shared.precision import precision_guard

    text = "1.12345678901234567890123456789012345678901234567890123456789"
    with precision_guard(90):
        value = mp.mpf(text)

    request = build_root_solving_request(
        equations=("x - A",),
        unknown_rows=({"name": "x", "initial": value},),
        data_headers=("A",),
        data_rows=((value,),),
        precision_digits=90,
    )

    assert request.inputs["unknown_rows"][0]["initial"] == text
    assert request.inputs["data_rows"] == [[text]]


def test_core_root_solving_request_builder_rejects_binary_float_inputs() -> None:
    from datalab_core.root_solving import build_root_solving_request

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_root_solving_request(equations=("x - A",), unknown_rows=({"name": "x", "initial": 1.25},))

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_root_solving_request(
            equations=("x - A",),
            unknown_rows=({"name": "x", "initial": "1"},),
            data_headers=("A",),
            data_rows=((1.25,),),
        )

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_root_solving_request(
            equations=("x - C",),
            unknown_rows=({"name": "x", "initial": "1"},),
            constants_enabled=True,
            constants_rows={"C": 1.25},
        )

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_root_solving_request(
            equations=("x - 1",),
            unknown_rows=({"name": "x", "initial": "1"},),
            scan_config={"sample_count": 200.0},
        )

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_root_solving_request(
            equations=("x - 1",),
            unknown_rows=({"name": "x", "initial": "1"},),
            parallel={"max_workers": 2.0},
        )


@pytest.mark.parametrize("precision_digits", [80.0, True])
def test_core_root_solving_request_builder_rejects_malformed_precision_before_payload_formatting(
    monkeypatch: pytest.MonkeyPatch,
    precision_digits: object,
) -> None:
    from datalab_core import root_solving

    def fail_if_called(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        raise AssertionError("payload formatting should not run before precision validation")

    monkeypatch.setattr(root_solving, "_normalize_unknown_rows", fail_if_called)

    with pytest.raises(TypeError):
        root_solving.build_root_solving_request(
            equations=("x - 1",),
            unknown_rows=({"name": "x", "initial": "1"},),
            precision_digits=cast(Any, precision_digits),
        )


def test_core_root_solving_request_builder_validates_inputs() -> None:
    from datalab_core.root_solving import build_root_solving_request

    with pytest.raises(ValueError, match="equations must contain at least one equation"):
        build_root_solving_request(equations=(), unknown_rows=({"name": "x"},))

    with pytest.raises(ValueError, match="unknown_rows must contain at least one row"):
        build_root_solving_request(equations=("x - 1",), unknown_rows=())

    with pytest.raises(ValueError, match="unknown_rows must contain at least one row with meaningful data"):
        build_root_solving_request(equations=("x - 1",), unknown_rows=({"source": "detected"},))

    with pytest.raises(ValueError, match="Root data row 1 is missing column B"):
        build_root_solving_request(
            equations=("x - A",),
            unknown_rows=({"name": "x", "initial": "1"},),
            data_headers=("A", "B"),
            data_rows=(("1",),),
        )

    with pytest.raises(TypeError, match="display_digits must be an integer"):
        build_root_solving_request(
            equations=("x - 1",),
            unknown_rows=({"name": "x", "initial": "1"},),
            display_digits=True,
        )

    with pytest.raises(TypeError, match="constants_rows must be a mapping or sequence"):
        build_root_solving_request(
            equations=("x - 1",),
            unknown_rows=({"name": "x", "initial": "1"},),
            constants_enabled=True,
            constants_rows=cast(Any, object()),
        )
