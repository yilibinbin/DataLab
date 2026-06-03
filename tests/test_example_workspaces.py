from __future__ import annotations

import hashlib
from pathlib import Path


EXAMPLE_NAMES = {
    "extrapolation.datalab",
    "error-propagation.datalab",
    "statistics.datalab",
    "fitting.datalab",
    "quantum-defect-implicit.datalab",
    "root-scalar-with-uncertainty.datalab",
    "root-monte-carlo-uncertainty.datalab",
    "root-batch-quadratic.datalab",
}
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


def test_canonical_example_workspaces_exist_and_open():
    from shared.workspace_io import read_workspace

    root = Path("examples/workspaces")
    found = {path.name for path in root.glob("*.datalab")}
    assert found == EXAMPLE_NAMES

    for name in EXAMPLE_NAMES:
        loaded = read_workspace(root / name)
        assert loaded.manifest["schema_version"]
        assert loaded.manifest["config"]
        assert loaded.manifest["data"]


def test_build_examples_is_deterministic():
    from tools.generate_example_workspaces import build_examples

    assert build_examples() == build_examples()
    assert set(build_examples()) == EXAMPLE_NAMES


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


def test_example_generator_records_checked_in_source_files():
    from tools.generate_example_workspaces import build_examples

    manifests = build_examples()

    assert _source_paths(manifests["extrapolation.datalab"]) == {"examples/extrapolation_richardson.txt"}
    assert _source_paths(manifests["error-propagation.datalab"]) == {
        "examples/error_propagation.txt",
        "examples/constants.txt",
    }
    assert _source_paths(manifests["statistics.datalab"]) == {"examples/statistics_weighted.txt"}
    assert _source_paths(manifests["fitting.datalab"]) == {"examples/fitting_powerlaw.txt"}
    assert _source_paths(manifests["quantum-defect-implicit.datalab"]) == set()
    assert _source_paths(manifests["root-scalar-with-uncertainty.datalab"]) == set()
    assert _source_paths(manifests["root-monte-carlo-uncertainty.datalab"]) == set()
    assert _source_paths(manifests["root-batch-quadratic.datalab"]) == set()


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
