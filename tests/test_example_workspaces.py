from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path


from examples.catalog import EXAMPLE_NAMES
from examples.catalog import example_index_payload


EXAMPLE_NAME_SET = set(EXAMPLE_NAMES)
FORBIDDEN_STRATEGY_KEYS = {
    "implicit_strategy",
    "implicit_backend_strategy",
    "backend_strategy",
    "backend_selector",
    "enable_new_implicit_backend",
}


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key)
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


def _source_paths(manifest: dict) -> set[str]:
    paths = set(manifest.get("examples", {}).get("source_files", []))
    workspace = manifest["workspace"]
    for section_name in ("data", "constants"):
        section = workspace.get(section_name) or {}
        source_path = section.get("source_path")
        if source_path:
            paths.add(source_path)
    return paths


def _recipe_paths(manifest: dict) -> set[str]:
    return set(manifest.get("examples", {}).get("recipe_files", []))


def test_canonical_example_workspaces_exist_and_open():
    from shared.workspace_io import read_workspace

    root = Path("examples/workspaces")
    found = {path.name for path in root.glob("*.datalab")}
    assert found == EXAMPLE_NAME_SET

    for name in EXAMPLE_NAMES:
        loaded = read_workspace(root / name)
        assert loaded.manifest["schema_version"]
        assert loaded.manifest["config"]
        assert loaded.manifest["data"]


def test_build_examples_is_deterministic():
    from tools.generate_example_workspaces import build_examples

    assert build_examples() == build_examples()
    assert set(build_examples()) == EXAMPLE_NAME_SET


def test_generated_example_archives_are_byte_deterministic(tmp_path):
    from shared.workspace_io import write_workspace
    from tools.generate_example_workspaces import build_examples

    manifests = build_examples()
    output_a = tmp_path / "a"
    output_b = tmp_path / "b"

    for output_dir in (output_a, output_b):
        for name, manifest in manifests.items():
            write_workspace(output_dir / name, manifest, {})

    hashes_a = {
        name: hashlib.sha256((output_a / name).read_bytes()).hexdigest()
        for name in EXAMPLE_NAMES
    }
    hashes_b = {
        name: hashlib.sha256((output_b / name).read_bytes()).hexdigest()
        for name in EXAMPLE_NAMES
    }

    assert hashes_a == hashes_b


def test_checked_in_example_archives_match_generator(tmp_path):
    from shared.workspace_io import write_workspace
    from tools.generate_example_workspaces import build_examples

    for name, manifest in build_examples().items():
        generated = tmp_path / name
        write_workspace(generated, manifest, {})
        assert generated.read_bytes() == (Path("examples/workspaces") / name).read_bytes(), name


def test_checked_in_example_catalog_matches_generator() -> None:
    checked_in = json.loads(Path("examples/workspaces/example_catalog.json").read_text(encoding="utf-8"))

    assert checked_in == example_index_payload()
    assert [item["filename"] for item in checked_in["examples"]] == list(EXAMPLE_NAMES)
    for item in checked_in["examples"]:
        for recipe_file in item["recipe_files"]:
            assert Path(recipe_file).is_file(), recipe_file


def test_example_generator_records_checked_in_source_files():
    from tools.generate_example_workspaces import build_examples

    manifests = build_examples()

    assert _source_paths(manifests["extrapolation.datalab"]) == {"examples/extrapolation_richardson.txt"}
    assert _source_paths(manifests["error-propagation.datalab"]) == {
        "examples/error_propagation.txt",
        "examples/constants.txt",
    }
    assert _source_paths(manifests["error-propagation-units.datalab"]) == set()
    assert _source_paths(manifests["statistics.datalab"]) == {"examples/statistics_weighted.txt"}
    assert _source_paths(manifests["statistics-bootstrap.datalab"]) == set()
    assert _source_paths(manifests["statistics-hypothesis.datalab"]) == set()
    assert _source_paths(manifests["statistics-matrix.datalab"]) == set()
    assert _source_paths(manifests["statistics-grouped.datalab"]) == set()
    assert _source_paths(manifests["statistics-time-series-rolling.datalab"]) == set()
    assert _source_paths(manifests["statistics-time-series-ewma.datalab"]) == set()
    assert _source_paths(manifests["fitting.datalab"]) == {"examples/fitting_powerlaw.txt"}
    assert _source_paths(manifests["quantum-defect-implicit.datalab"]) == set()
    assert _source_paths(manifests["root-scalar-with-uncertainty.datalab"]) == set()
    assert _source_paths(manifests["root-monte-carlo-uncertainty.datalab"]) == set()
    assert _source_paths(manifests["root-batch-quadratic.datalab"]) == set()


def test_example_generator_records_checked_in_recipe_files():
    from tools.generate_example_workspaces import build_examples

    manifests = build_examples()
    expected = {
        "error-propagation.datalab": {"examples/recipes/error-product-basic.json"},
        "statistics.datalab": {"examples/recipes/statistics-mean-basic.json"},
        "fitting.datalab": {"examples/recipes/fitting-custom-powerlaw.json"},
        "root-batch-quadratic.datalab": {"examples/recipes/root-batch-quadratic.json"},
    }

    for name, manifest in manifests.items():
        assert _recipe_paths(manifest) == expected.get(name, set())


def test_root_uncertainty_example_workspaces_load() -> None:
    from shared.workspace_io import read_workspace

    names = {
        "root-scalar-with-uncertainty.datalab",
        "root-monte-carlo-uncertainty.datalab",
        "root-batch-quadratic.datalab",
    }
    for name in names:
        loaded = read_workspace(Path("examples/workspaces") / name)
        workspace = loaded.manifest["workspace"]
        assert workspace["current_mode"] == "root_solving"
        assert "root_solving" in workspace["config"]


def test_error_propagation_units_example_is_display_only_and_validation_ready() -> None:
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/error-propagation-units.datalab"))
    workspace = loaded.manifest["workspace"]
    units = workspace["config"]["error"]["units"]
    variants = loaded.manifest.get("examples", {}).get("variants", [])

    assert workspace["current_mode"] == "error"
    assert workspace["config"]["error"]["formula"] == "Distance / Time"
    assert units["enabled"] is True
    assert units["mode"] == "display_only"
    assert units["inputs"] == {
        "Distance": {"unit": "m"},
        "Time": {"unit": "s"},
    }
    assert units["outputs"] == {"result": {"unit": "m/s"}}
    assert {"units", "display_only", "validation_ready"} <= set(variants)


def test_root_uncertainty_examples_store_expected_options() -> None:
    from shared.workspace_io import read_workspace

    scalar = read_workspace(Path("examples/workspaces/root-scalar-with-uncertainty.datalab")).manifest["workspace"]
    monte_carlo = read_workspace(Path("examples/workspaces/root-monte-carlo-uncertainty.datalab")).manifest["workspace"]
    batch = read_workspace(Path("examples/workspaces/root-batch-quadratic.datalab")).manifest["workspace"]

    assert scalar["config"]["root_solving"]["uncertainty_options"] == {
        "method": "taylor",
        "taylor_order": 1,
        "monte_carlo_samples": 2000,
        "monte_carlo_seed": "",
    }
    assert monte_carlo["config"]["root_solving"]["uncertainty_options"] == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 2000,
        "monte_carlo_seed": "42",
    }
    assert batch["data"]["canonical_table"]["headers"] == ["A"]
    assert batch["config"]["root_solving"]["equations"] == "x^2 - A"


def test_root_uncertainty_example_snapshots_match_worker_payload() -> None:
    from app_desktop.workers_core import RootSolvingJob, _execute_root_solving_job_payload
    from shared.workspace_io import read_workspace

    names = {
        "root-scalar-with-uncertainty.datalab",
        "root-monte-carlo-uncertainty.datalab",
        "root-batch-quadratic.datalab",
    }
    for name in names:
        workspace = read_workspace(Path("examples/workspaces") / name).manifest["workspace"]
        root_config = workspace["config"]["root_solving"]
        constants_config = root_config["constants"]
        data_table = workspace["data"]["canonical_table"]
        job = RootSolvingJob(
            equations=tuple(
                line.strip()
                for line in str(root_config["equations"]).splitlines()
                if line.strip()
            ),
            unknown_rows=tuple(dict(row) for row in root_config["unknowns"]),
            data_headers=tuple(str(header) for header in data_table.get("headers") or ()),
            data_rows=tuple(tuple(str(cell) for cell in row) for row in data_table.get("rows") or ()),
            constants_enabled=bool(constants_config["enabled"]),
            constants_rows=tuple(dict(row) for row in constants_config["rows"]),
            constants_view=str(constants_config["view"]),
            constants_text=str(constants_config["text"]),
            mode=str(root_config["mode"]),
            scan_config={},
            precision=int(workspace["config"]["common"]["mpmath_precision"]),
            display_digits=int(workspace["config"]["common"]["display_digits"]),
            uncertainty_options=dict(root_config["uncertainty_options"]),
        )

        payload = _execute_root_solving_job_payload(job)
        snapshot = workspace["result_snapshot"]
        assert snapshot["markdown"] == payload["markdown"], name
        assert snapshot["csv"]["headers"] == payload["csv_headers"], name
        assert snapshot["csv"]["rows"] == payload["csv_rows"], name
        assert snapshot["log"] == payload["log"], name


def test_fitting_example_contains_required_variants():
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/fitting.datalab"))
    variants = loaded.manifest.get("examples", {}).get("variants", [])

    assert {"custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"} <= set(variants)


def test_quantum_defect_example_uses_ionization_energy_output_space():
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/quantum-defect-implicit.datalab"))
    workspace = loaded.manifest["workspace"]
    fitting = workspace["config"]["fitting"]
    implicit = fitting["implicit"]
    headers = workspace["data"]["canonical_table"]["headers"]
    variants = loaded.manifest.get("examples", {}).get("variants", [])

    assert headers == ["n", "E", "sigma_E"]
    assert fitting["model"] == "self_consistent"
    assert fitting["target_column"] == "E"
    assert fitting["weighted"] is True
    assert implicit["implicit_variable"] == "delta"
    assert implicit["equation"] == "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
    assert implicit["output_expression"] == "CR*M/(M+1)/(n-delta)^2"
    assert implicit["constants_enabled"] is True
    assert implicit["constants"] == [
        {"name": "CR", "value": "3.2898419602500e9"},
        {"name": "M", "value": "7294.29954171"},
    ]
    assert {"self_consistent", "implicit", "quantum_defect", "ionization_energy", "weighted"} <= set(variants)


def test_quantum_defect_example_configuration_runs_weighted_output_space_fit():
    import mpmath as mp

    from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/quantum-defect-implicit.datalab"))
    workspace = loaded.manifest["workspace"]
    fitting = workspace["config"]["fitting"]
    implicit = fitting["implicit"]
    rows = workspace["data"]["canonical_table"]["rows"]
    n_values = [mp.mpf(row[0]) for row in rows]
    targets = [mp.mpf(row[1]) for row in rows]
    sigmas = [mp.mpf(row[2]) for row in rows]
    parameter_config = {
        row["name"]: {key: value for key, value in row.items() if key != "name" and value}
        for row in implicit["parameters"]
    }
    constants = {row["name"]: row["value"] for row in implicit["constants"]}
    problem = ModelProblem(
        model_type="self_consistent",
        expression=fitting["expression"],
        variables=("n",),
        target_name=fitting["target_column"],
        parameter_config=parameter_config,
        constants=constants,
        implicit_definition=ImplicitModelDefinition(
            x_variables=tuple(implicit["x_variables"]),
            implicit_variable=implicit["implicit_variable"],
            equation=implicit["equation"],
            output_expression=implicit["output_expression"],
            parameters=tuple(row["name"] for row in implicit["parameters"]),
            constants=constants,
            solve_options=ImplicitSolveOptions(
                method=implicit["method"],
                initial=implicit["initial"],
                tolerance=implicit["tolerance"],
                max_iterations=implicit["max_iterations"],
            ),
        ),
    )

    result = FitRunner().fit(
        problem,
        {"n": n_values},
        targets,
        precision=50,
        weights=[1 / (sigma * sigma) for sigma in sigmas],
        data_sigmas=sigmas,
    )

    assert result.details["implicit_strategy"] == "general_output_space_with_inversion_seed"
    assert result.details["output_inversion"] == "validated symbolic output inversion"
    assert result.details["weighted"] is True
    assert all(mp.isfinite(result.params[name]) for name in ("d0", "d2", "d4"))
    assert all(
        mp.almosteq(residual, fit - target, rel_eps=mp.mpf("1e-30"), abs_eps=mp.mpf("1e-15"))
        for residual, fit, target in zip(result.residuals, result.fitted_curve, targets, strict=True)
    )


def test_statistics_bootstrap_example_configuration_runs_seeded_bootstrap() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.service_factory import create_core_session_service
    from datalab_core.session import ResultStatus
    from datalab_core.statistics import build_statistics_requests
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/statistics-bootstrap.datalab"))
    workspace = loaded.manifest["workspace"]
    statistics = workspace["config"]["statistics"]
    table = workspace["data"]["canonical_table"]

    assert statistics["workflow_mode"] == "bootstrap_confidence_intervals"
    assert statistics["bootstrap"] == {
        "target_statistic": "mean",
        "confidence_level": "0.95",
        "resample_count": 100,
        "seed": "12345",
    }

    requests = build_statistics_requests(
        headers=tuple(table["headers"]),
        rows=tuple(tuple(row) for row in table["rows"]),
        value_col=statistics["value_column"],
        precision_digits=int(workspace["config"]["common"]["mpmath_precision"]),
        request_id_prefix="example-statistics-bootstrap",
    )
    request = requests[0].request
    bootstrap_options = dict(statistics["bootstrap"])
    bootstrap_request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "workflow_mode": statistics["workflow_mode"],
            "values": tuple(request.inputs["values"]),
            "source_row_ids": tuple(requests[0].source_row_ids),
            "value_column": requests[0].value_col,
            "column_index": 1,
            "target_statistic": bootstrap_options["target_statistic"],
            "confidence_level": bootstrap_options["confidence_level"],
            "resample_count": bootstrap_options["resample_count"],
            "sample_mode": "sample" if statistics["sample"] else "population",
            "seed": bootstrap_options["seed"],
        },
        options=JobOptions(precision_digits=request.options.precision_digits),
        request_id=request.request_id,
    )

    service = create_core_session_service()
    envelope = service.submit(bootstrap_request)

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert isinstance(payload, Mapping)
    assert payload["workflow_mode"] == "bootstrap_confidence_intervals"
    assert payload["resample_count"] == 100
    assert payload["seed"] == 12345
    assert payload["columns"][0]["value_column"] == "Value"


def test_statistics_hypothesis_example_configuration_runs_one_sample_t() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.service_factory import create_core_session_service
    from datalab_core.session import ResultStatus
    from datalab_core.statistics import build_statistics_requests
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/statistics-hypothesis.datalab"))
    workspace = loaded.manifest["workspace"]
    statistics = workspace["config"]["statistics"]
    table = workspace["data"]["canonical_table"]
    hypothesis = statistics["hypothesis"]

    assert statistics["workflow_mode"] == "hypothesis_tests"
    assert hypothesis["test_kind"] == "one_sample_t"
    assert hypothesis["null_parameter"] == "3"

    requests = build_statistics_requests(
        headers=tuple(table["headers"]),
        rows=tuple(tuple(row) for row in table["rows"]),
        value_col=statistics["value_column"],
        precision_digits=int(workspace["config"]["common"]["mpmath_precision"]),
        request_id_prefix="example-statistics-hypothesis",
    )
    request = requests[0].request
    hypothesis_request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "workflow_mode": statistics["workflow_mode"],
            "test_kind": hypothesis["test_kind"],
            "values": tuple(request.inputs["values"]),
            "source_row_ids": tuple(requests[0].source_row_ids),
            "value_column": requests[0].value_col,
            "mu0": hypothesis["null_parameter"],
            "alternative": hypothesis["alternative"],
            "alpha": hypothesis["alpha"],
        },
        options=JobOptions(precision_digits=request.options.precision_digits),
        request_id=request.request_id,
    )

    service = create_core_session_service()
    envelope = service.submit(hypothesis_request)

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert isinstance(payload, Mapping)
    assert payload["workflow_mode"] == "hypothesis_tests"
    assert payload["test_kind"] == "one_sample_t"
    assert payload["inputs"]["value_columns"] == ["A"]
    assert payload["result"]["statistic_name"] == "t"


def test_statistics_matrix_example_configuration_runs_covariance_correlation() -> None:
    import mpmath as mp

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.service_factory import create_core_session_service
    from datalab_core.session import ResultStatus
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/statistics-matrix.datalab"))
    workspace = loaded.manifest["workspace"]
    statistics = workspace["config"]["statistics"]
    table = workspace["data"]["canonical_table"]

    assert statistics["workflow_mode"] == "covariance_correlation"
    assert statistics["value_columns"] == ["A", "B", "C"]
    assert statistics["matrix"]["missing_policy"] == "listwise"

    service = create_core_session_service()
    envelope = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": statistics["workflow_mode"],
                "headers": tuple(table["headers"]),
                "rows": tuple(tuple(row) for row in table["rows"]),
                "value_columns": tuple(statistics["value_columns"]),
                "missing_policy": statistics["matrix"]["missing_policy"],
                "use_sample": statistics["sample"],
                "source_row_ids": tuple(str(index + 1) for index in range(len(table["rows"]))),
            },
            options=JobOptions(precision_digits=int(workspace["config"]["common"]["mpmath_precision"])),
            request_id="example-statistics-matrix",
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert isinstance(payload, Mapping)
    assert payload["workflow_mode"] == "covariance_correlation"
    assert payload["columns"] == ["A", "B", "C"]
    assert payload["missing_policy"] == "listwise"
    assert payload["correlation_metadata"]["budget_eligible"] is True
    correlation = payload["matrices"]["correlation"]["values"]
    assert mp.almosteq(mp.mpf(correlation[0][1]), mp.mpf("1"))
    assert mp.almosteq(mp.mpf(correlation[0][2]), mp.mpf("-1"))


def test_statistics_grouped_example_configuration_runs_grouped_statistics() -> None:
    import mpmath as mp

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.service_factory import create_core_session_service
    from datalab_core.session import ResultStatus
    from shared.workspace_io import read_workspace

    loaded = read_workspace(Path("examples/workspaces/statistics-grouped.datalab"))
    workspace = loaded.manifest["workspace"]
    statistics = workspace["config"]["statistics"]
    table = workspace["data"]["canonical_table"]

    assert statistics["workflow_mode"] == "grouped_statistics"
    assert statistics["group_column"] == "Group"
    assert statistics["value_columns"] == ["Signal", "Reference"]
    assert statistics["sigma_column"] == "Sigma"
    assert {"grouped_statistics", "multi_column", "weighted"} <= set(loaded.manifest.get("examples", {}).get("variants", []))

    service = create_core_session_service()
    envelope = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": statistics["workflow_mode"],
                "headers": tuple(table["headers"]),
                "rows": tuple(tuple(row) for row in table["rows"]),
                "group_column": statistics["group_column"],
                "value_columns": tuple(statistics["value_columns"]),
                "sigma_column": statistics["sigma_column"],
                "stats_mode": statistics["mode"],
                "use_sample": statistics["sample"],
                "use_weighted_variance": statistics["weighted_variance"],
                "source_row_ids": tuple(str(index + 1) for index in range(len(table["rows"]))),
            },
            options=JobOptions(precision_digits=int(workspace["config"]["common"]["mpmath_precision"]), uncertainty_digits=1),
            request_id="example-statistics-grouped",
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert isinstance(payload, Mapping)
    assert payload["workflow_mode"] == "grouped_statistics"
    assert payload["group_order"] == ["Control", "Treatment"]
    control_signal = payload["groups"][0]["columns"][0]["result"]
    assert mp.almosteq(mp.mpf(control_signal["mean"]), mp.mpf("10.2"))
    assert control_signal["dropped"] == 0


def test_statistics_time_series_examples_run_through_core_service() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.service_factory import create_core_session_service
    from datalab_core.session import ResultStatus
    from shared.workspace_io import read_workspace

    service = create_core_session_service()
    cases = {
        "statistics-time-series-rolling.datalab": ("rolling_mean", "12.5"),
        "statistics-time-series-ewma.datalab": ("ewma", None),
    }
    for name, (expected_method, expected_last_value) in cases.items():
        workspace = read_workspace(Path("examples/workspaces") / name).manifest["workspace"]
        statistics = workspace["config"]["statistics"]
        time_series = statistics["time_series"]
        table = workspace["data"]["canonical_table"]
        headers = list(table["headers"])
        rows = list(table["rows"])
        value_column = statistics["value_column"]
        value_index = headers.index(value_column)
        time_column = time_series["time_column"]
        time_index = headers.index(time_column)
        sigma_column = str(statistics.get("sigma_column") or "")
        inputs = {
            "workflow_mode": statistics["workflow_mode"],
            "series_method": time_series["series_method"],
            "values": tuple(row[value_index] for row in rows),
            "source_row_ids": tuple(str(index + 1) for index in range(len(rows))),
            "value_column": value_column,
            "column_index": 1,
            "time_labels": tuple(row[time_index] for row in rows),
            "time_column": time_column,
            "window_size": time_series["window_size"],
            "min_periods": time_series["min_periods"],
            "alignment": time_series["alignment"],
            "denominator": time_series["denominator"],
            "adjust": time_series["adjust"],
        }
        if sigma_column:
            sigma_index = headers.index(sigma_column)
            inputs["sigmas"] = tuple(row[sigma_index] for row in rows)
            inputs["sigma_column"] = sigma_column
        if time_series["series_method"] == "ewma":
            inputs[time_series["ewma_parameter"]] = time_series["ewma_value"]

        envelope = service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs=inputs,
                options=JobOptions(precision_digits=int(workspace["config"]["common"]["mpmath_precision"])),
                request_id=f"example-{name}",
            )
        )

        assert envelope.status is ResultStatus.SUCCEEDED
        payload = envelope.payload
        assert isinstance(payload, Mapping)
        assert payload["workflow_mode"] == "time_series_rolling"
        assert payload["series_method"] == expected_method
        final_point = payload["columns"][0]["points"][-1]
        assert final_point["status"] == "ok"
        if expected_last_value is not None:
            assert final_point["value"] == expected_last_value
            assert final_point["uncertainty"] is not None


def test_example_workspaces_do_not_persist_backend_strategy_fields():
    from shared.workspace_io import read_workspace
    from tools.generate_example_workspaces import build_examples

    generated = build_examples()
    for name, manifest in generated.items():
        forbidden = FORBIDDEN_STRATEGY_KEYS & set(_walk_keys(manifest))
        assert forbidden == set(), name

    for name in EXAMPLE_NAMES:
        loaded = read_workspace(Path("examples/workspaces") / name)
        forbidden = FORBIDDEN_STRATEGY_KEYS & set(_walk_keys(loaded.manifest))
        assert forbidden == set(), name
