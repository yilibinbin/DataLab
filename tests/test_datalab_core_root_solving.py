from __future__ import annotations

import mpmath as mp
import pytest


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
    assert request.inputs["display_digits"] == 12


def test_core_root_solving_handler_runs_scalar_batch_request() -> None:
    from datalab_core.results import ResultStatus
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
            precision_digits=precision_digits,
        )


def test_core_root_solving_request_builder_validates_inputs() -> None:
    from datalab_core.root_solving import build_root_solving_request

    with pytest.raises(ValueError, match="equations must contain at least one equation"):
        build_root_solving_request(equations=(), unknown_rows=({"name": "x"},))

    with pytest.raises(ValueError, match="unknown_rows must contain at least one row"):
        build_root_solving_request(equations=("x - 1",), unknown_rows=())

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
            constants_rows=object(),
        )
