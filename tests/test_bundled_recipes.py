from __future__ import annotations

import json
from pathlib import Path

from datalab_core.recipes import (
    build_recipe_fitting_request,
    build_recipe_root_solving_request,
    build_recipe_statistics_requests,
    build_recipe_uncertainty_request,
    build_recipe_workspace_patch,
    loads_recipe_json,
    resolve_recipe_bindings,
)
from datalab_core.fitting import build_fitting_request
from datalab_core.fitting import run_fitting
from datalab_core.results import ResultStatus
from datalab_core.root_solving import build_root_solving_request
from datalab_core.root_solving import run_root_solving
from datalab_core.statistics import build_multi_column_statistics_requests
from datalab_core.statistics import run_statistics
from datalab_core.uncertainty import build_uncertainty_request
from datalab_core.uncertainty import run_uncertainty
from examples.catalog import example_index_payload
from shared.uncertainty import parse_uncertainty_format
from shared.workspace_io import read_workspace


EXPECTED_RECIPE_IDS = {
    "error-product-basic",
    "fitting-custom-powerlaw",
    "root-batch-quadratic",
    "statistics-mean-basic",
}

EXPECTED_RECIPE_FILES = {
    "examples/recipes/error-product-basic.json",
    "examples/recipes/fitting-custom-powerlaw.json",
    "examples/recipes/root-batch-quadratic.json",
    "examples/recipes/statistics-mean-basic.json",
}


def test_bundled_recipe_files_validate_and_are_catalog_linked() -> None:
    recipe_root = Path("examples/recipes")
    recipe_paths = sorted(recipe_root.glob("*.json"))
    assert recipe_paths

    recipe_ids = {
        loads_recipe_json(path.read_text(encoding="utf-8"))["id"]
        for path in recipe_paths
    }
    catalog_links = {
        recipe_file
        for entry in example_index_payload()["examples"]
        for recipe_file in entry["recipe_files"]
    }

    assert recipe_ids == EXPECTED_RECIPE_IDS
    assert catalog_links == EXPECTED_RECIPE_FILES
    for recipe_file in catalog_links:
        assert Path(recipe_file).is_file()


def test_statistics_bundled_recipe_applies_to_linked_example_workspace() -> None:
    recipe_path = Path("examples/recipes/statistics-mean-basic.json")
    recipe = loads_recipe_json(recipe_path.read_text(encoding="utf-8"))
    headers, raw_rows = _workspace_table("statistics.datalab")
    rows, sigma_rows = _split_uncertainty_rows(raw_rows)

    resolution = resolve_recipe_bindings(recipe, data_columns=headers)
    assert resolution.is_complete
    assert resolution.apply_request is not None

    patch = build_recipe_workspace_patch(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=32,
        uncertainty_digits=1,
    )
    requests = build_recipe_statistics_requests(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=32,
        uncertainty_digits=1,
    )
    manual = build_multi_column_statistics_requests(
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        value_columns="Value",
        sigma_col=None,
        stats_mode="mean",
        use_sample=True,
        use_weighted_variance=True,
        precision_digits=32,
        uncertainty_digits=1,
        request_id_prefix="recipe-statistics-mean-basic",
    )

    assert patch["current_mode"] == "statistics"
    assert patch["config"]["statistics"]["mode"] == "mean"
    assert requests == manual
    for column_batches in requests:
        for batch in column_batches.batches:
            assert run_statistics(batch.request).status is ResultStatus.SUCCEEDED


def test_error_bundled_recipe_applies_to_linked_example_workspace() -> None:
    recipe = _load_recipe("error-product-basic.json")
    headers, raw_rows = _workspace_table("error-propagation.datalab")
    rows, sigma_rows = _split_uncertainty_rows(raw_rows)

    resolution = resolve_recipe_bindings(recipe, data_columns=headers)
    assert resolution.is_complete
    assert resolution.apply_request is not None

    patch = build_recipe_workspace_patch(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=32,
        uncertainty_digits=1,
    )
    request = build_recipe_uncertainty_request(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=32,
        uncertainty_digits=1,
    )
    manual = build_uncertainty_request(
        headers=headers,
        rows=rows,
        uncertainty_rows=sigma_rows,
        formula="V1 * V2",
        propagation_method="taylor",
        propagation_order=1,
        mc_samples=5000,
        mc_seed=12345,
        collect_monte_carlo_distribution=False,
        precision_digits=32,
        uncertainty_digits=1,
        request_id="recipe-error-product-basic",
    )

    assert patch["current_mode"] == "error"
    assert patch["config"]["error"]["formula"] == "V1 * V2"
    assert request == manual
    assert run_uncertainty(request).status is ResultStatus.SUCCEEDED


def test_fitting_bundled_recipe_applies_to_linked_example_workspace() -> None:
    recipe = _load_recipe("fitting-custom-powerlaw.json")
    headers, raw_rows = _workspace_table("fitting.datalab")
    rows, sigma_rows = _split_uncertainty_rows(raw_rows)

    resolution = resolve_recipe_bindings(recipe, data_columns=headers)
    assert resolution.is_complete
    assert resolution.apply_request is not None

    patch = build_recipe_workspace_patch(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=80,
        uncertainty_digits=1,
    )
    request = build_recipe_fitting_request(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        sigma_rows=sigma_rows,
        precision_digits=80,
        uncertainty_digits=1,
    )
    manual = build_fitting_request(
        model_type="custom",
        headers=headers,
        data_rows=rows,
        sigma_rows=sigma_rows,
        variable_map={"x": "x"},
        target_column="y",
        model_expr="A + B*x^(-C)",
        parameter_config={
            "A": {"initial": "1.0"},
            "B": {"initial": "0.1", "min": "-10", "max": "10"},
            "C": {"initial": "0.01", "min": "-10", "max": "10"},
        },
        parameter_names=("A", "B", "C"),
        weighted=True,
        precision_digits=80,
        uncertainty_digits=1,
        request_id="recipe-fitting-custom-powerlaw",
    )

    assert patch["current_mode"] == "fitting"
    assert patch["config"]["fitting"]["expression"] == "A + B*x^(-C)"
    assert patch["config"]["fitting"]["constraints_enabled"] is True
    assert request == manual
    assert run_fitting(request).status is ResultStatus.SUCCEEDED


def test_root_bundled_recipe_applies_to_linked_example_workspace() -> None:
    recipe = _load_recipe("root-batch-quadratic.json")
    headers, rows = _workspace_table("root-batch-quadratic.datalab")

    resolution = resolve_recipe_bindings(recipe, data_columns=headers)
    assert resolution.is_complete
    assert resolution.apply_request is not None

    patch = build_recipe_workspace_patch(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        precision_digits=32,
        uncertainty_digits=1,
    )
    request = build_recipe_root_solving_request(
        recipe,
        resolution.apply_request,
        headers=headers,
        rows=rows,
        precision_digits=32,
        uncertainty_digits=1,
    )
    manual = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=(
            {
                "name": "x",
                "initial": "1",
                "lower": "",
                "upper": "",
                "source": "manual",
            },
        ),
        data_headers=headers,
        data_rows=rows,
        constants_enabled=False,
        constants_rows=(),
        mode="scalar",
        scan_config={},
        uncertainty_options={
            "method": "taylor",
            "taylor_order": 1,
            "monte_carlo_samples": 2000,
            "monte_carlo_seed": "",
        },
        precision_digits=32,
        uncertainty_digits=1,
        request_id="recipe-root-batch-quadratic",
    )

    assert patch["current_mode"] == "root_solving"
    assert patch["config"]["root_solving"]["equations"] == "x^2 - A"
    assert request == manual
    assert run_root_solving(request).status is ResultStatus.SUCCEEDED


def test_checked_in_recipe_json_is_canonical() -> None:
    for path in sorted(Path("examples/recipes").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        canonical = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        assert path.read_text(encoding="utf-8") == canonical


def _load_recipe(filename: str) -> dict[str, object]:
    path = Path("examples/recipes") / filename
    return loads_recipe_json(path.read_text(encoding="utf-8"))


def _workspace_table(filename: str) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    workspace = read_workspace(Path("examples/workspaces") / filename).manifest["workspace"]
    table = workspace["data"]["canonical_table"]
    headers = tuple(str(header) for header in table["headers"])
    rows = tuple(tuple(str(cell) for cell in row) for row in table["rows"])
    return headers, rows


def _split_uncertainty_rows(
    rows: tuple[tuple[str, ...], ...],
) -> tuple[tuple[tuple[str, ...], ...], tuple[tuple[str, ...], ...]]:
    value_rows: list[tuple[str, ...]] = []
    sigma_rows: list[tuple[str, ...]] = []
    for row in rows:
        values: list[str] = []
        sigmas: list[str] = []
        for cell in row:
            parsed = parse_uncertainty_format(cell, precision=80)
            values.append(str(parsed.value))
            sigmas.append(str(parsed.uncertainty))
        value_rows.append(tuple(values))
        sigma_rows.append(tuple(sigmas))
    return tuple(value_rows), tuple(sigma_rows)
