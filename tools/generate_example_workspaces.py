from __future__ import annotations

from decimal import Decimal, localcontext
import json
from pathlib import Path
import sys
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.catalog import EXAMPLE_NAMES, example_index_payload  # noqa: E402
from shared.workspace_io import write_workspace  # noqa: E402
from shared.workspace_schema import compute_workspace_hash, sha256_bytes  # noqa: E402
from app_desktop.workers_core import RootSolvingJob, _execute_root_solving_job_payload  # noqa: E402

EXAMPLE_ROOT = PROJECT_ROOT / "examples" / "workspaces"
DATASET_ROOT = PROJECT_ROOT / "examples"
APP_VERSION = "2.0.2"
GENERATED_TIMESTAMP = "2026-05-29T00:00:00Z"


def _project_relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _parse_table_text(path: Path) -> tuple[list[str], list[list[str]], str, bytes]:
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    logical_lines = [
        line.strip()
        for line in raw_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not logical_lines:
        raise ValueError(f"dataset is empty: {path}")
    headers = logical_lines[0].split()
    rows = [line.split() for line in logical_lines[1:]]
    for row in rows:
        if len(row) != len(headers):
            raise ValueError(f"dataset row has {len(row)} cells; expected {len(headers)} in {path}")
    decoded_text = "\n".join(["\t".join(headers), *("\t".join(row) for row in rows)]) + "\n"
    return headers, rows, decoded_text, raw_bytes


def _table_section_from_file(path: Path) -> dict[str, Any]:
    headers, rows, decoded_text, raw_bytes = _parse_table_text(path)
    source_label = _project_relative(path)
    canonical = {"headers": headers, "rows": rows}
    return {
        "enabled": True,
        "source_kind": "file",
        "source_path": source_label,
        "source_path_label": source_label,
        "active_view": "table",
        "decoded_text": decoded_text,
        "encoding": "utf-8",
        "newline": "lf",
        "original_bytes_sha256": sha256_bytes(raw_bytes),
        "raw_bytes_path": None,
        "canonical_table": canonical,
        "sha256": sha256_bytes((decoded_text + repr(canonical)).encode("utf-8")),
    }


def _table_section_from_rows(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    decoded_text = "\n".join(["\t".join(headers), *("\t".join(row) for row in rows)]) + "\n"
    canonical = {"headers": headers, "rows": rows}
    raw_bytes = decoded_text.encode("utf-8")
    return {
        "enabled": True,
        "source_kind": "manual_table",
        "source_path": None,
        "source_path_label": None,
        "active_view": "table",
        "decoded_text": decoded_text,
        "encoding": "utf-8",
        "newline": "lf",
        "original_bytes_sha256": sha256_bytes(raw_bytes),
        "raw_bytes_path": None,
        "canonical_table": canonical,
        "sha256": sha256_bytes((decoded_text + repr(canonical)).encode("utf-8")),
    }


def _uncertain_decimal(value: str) -> tuple[Decimal, Decimal]:
    number, uncertainty = value.strip().split("(", 1)
    uncertainty_digits = uncertainty.rstrip(")")
    decimal_places = len(number.partition(".")[2])
    return Decimal(number), Decimal(uncertainty_digits) * (Decimal(10) ** -decimal_places)


def _format_decimal(value: Decimal, places: int = 12) -> str:
    quant = Decimal(1).scaleb(-places)
    return format(value.quantize(quant), "f")


def _quantum_defect_energy_rows(delta_rows: list[list[str]]) -> list[list[str]]:
    with localcontext() as context:
        context.prec = 50
        cr = Decimal("3.2898419602500e9")
        mass_ratio = Decimal("7294.29954171")
        rydberg = cr * mass_ratio / (mass_ratio + Decimal(1))
        rows: list[list[str]] = []
        for n_text, delta_text in delta_rows:
            n_value = Decimal(n_text)
            delta_value, delta_sigma = _uncertain_decimal(delta_text)
            denominator = n_value - delta_value
            energy = rydberg / (denominator * denominator)
            sigma_energy = abs(Decimal(2) * rydberg * delta_sigma / (denominator**3))
            rows.append([n_text, _format_decimal(energy, places=8), _format_decimal(sigma_energy, places=12)])
        return rows


def _empty_constants() -> dict[str, Any]:
    return {
        "enabled": False,
        "source_kind": "manual_table",
        "source_path": None,
        "source_path_label": None,
        "active_view": "table",
        "decoded_text": "",
        "encoding": "utf-8",
        "newline": "lf",
        "original_bytes_sha256": sha256_bytes(b""),
        "raw_bytes_path": None,
        "canonical_table": {"headers": ["Name", "Value"], "rows": []},
        "sha256": sha256_bytes(repr({"headers": ["Name", "Value"], "rows": []}).encode("utf-8")),
    }


def _constants_section_from_file(path: Path) -> dict[str, Any]:
    rows: list[list[str]] = []
    raw_bytes = path.read_bytes()
    raw_text = raw_bytes.decode("utf-8")
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) == 2:
            rows.append(parts)
    headers = ["Name", "Value"]
    decoded_text = "\n".join(["\t".join(headers), *("\t".join(row) for row in rows)]) + "\n"
    source_label = _project_relative(path)
    canonical = {"headers": headers, "rows": rows}
    return {
        "enabled": True,
        "source_kind": "file",
        "source_path": source_label,
        "source_path_label": source_label,
        "active_view": "table",
        "decoded_text": decoded_text,
        "encoding": "utf-8",
        "newline": "lf",
        "original_bytes_sha256": sha256_bytes(raw_bytes),
        "raw_bytes_path": None,
        "canonical_table": canonical,
        "sha256": sha256_bytes((decoded_text + repr(canonical)).encode("utf-8")),
    }


def _base_config() -> dict[str, Any]:
    return {
        "common": {
            "mpmath_precision": 32,
            "uncertainty_digits": 1,
            "generate_latex": False,
            "generate_plots": True,
            "verbose": False,
            "display_scientific": False,
            "display_digits": 10,
        },
        "latex": {
            "output_path": "",
            "input_digits": 20,
            "use_dcolumn": False,
            "group_size": 3,
            "use_caption": True,
            "caption": "",
            "engine": "tectonic",
        },
        "extrapolation": {
            "method": "richardson",
            "custom_formula": "",
            "power_law": {"x_values": "2,3,4,5", "custom_p": "", "seed_guesses": ""},
            "levin": {"variant": "u", "order": 2, "weight": "default", "beta": "1.0"},
            "richardson": {"p": "2.0"},
            "uncertainty_column": "Value",
        },
        "error": {
            "formula": "sqrt(dx^2 + dy^2)",
            "method": "taylor",
            "order": 1,
            "mc_samples": 5000,
            "mc_seed": "12345",
        },
        "statistics": {
            "value_column": "Value",
            "sigma_column": "Sigma",
            "mode": "mean",
            "sample": True,
            "weighted_variance": True,
        },
        "fitting": {
            "model": "custom",
            "expression": "A + B*x + C*x^2",
            "target_column": "y",
            "weighted": True,
            "mcmc_refine": False,
            "variables": [{"name": "x", "column": "x"}],
            "constraints_enabled": True,
            "parameter_rows": [
                {"name": "A", "initial": "1.0", "fixed": "", "min": "", "max": ""},
                {"name": "B", "initial": "0.1", "fixed": "", "min": "-10", "max": "10"},
                {"name": "C", "initial": "0.01", "fixed": "", "min": "-10", "max": "10"},
            ],
            "parameter_orphans": [],
            "custom_constants": {"enabled": False, "view": "table", "rows": [], "text": ""},
            "implicit": {
                "schema": 2,
                "active": False,
                "x_variables": ["x"],
                "implicit_variable": "z",
                "equation": "z - (A + B*x)",
                "output_expression": "z",
                "method": "newton",
                "initial": "1.0",
                "tolerance": "1e-24",
                "max_iterations": 80,
                "timeout_seconds": 300,
                "constraints_enabled": True,
                "parameters": [
                    {"name": "A", "initial": "1.0", "fixed": "", "min": "", "max": ""},
                    {"name": "B", "initial": "0.1", "fixed": "", "min": "-10", "max": "10"},
                ],
                "parameter_orphans": [],
                "constants": [],
                "constants_enabled": False,
                "constants_view": "table",
                "constants_text": "",
            },
            "poly_degree": 2,
            "inverse_power": {"min": 1, "max": 3},
            "pade": {"m": 1, "n": 1},
            "log_axes": {"x": False, "y": False},
        },
        "root_solving": {
            "schema": 1,
            "equations": "x^2 - C",
            "mode": "scalar",
            "unknowns": [{"name": "x", "initial": "2", "lower": "", "upper": ""}],
            "constants": {
                "enabled": True,
                "view": "table",
                "rows": [{"name": "C", "value": "4.0(2)"}],
                "text": "C = 4.0(2)\n",
                "numeric_mode": "uncertainty",
            },
            "uncertainty_options": {
                "method": "taylor",
                "taylor_order": 1,
                "monte_carlo_samples": 2000,
                "monte_carlo_seed": "",
            },
        },
    }


def _manifest(
    *,
    title: str,
    mode: str,
    data: dict[str, Any],
    config: dict[str, Any],
    markdown: str,
    csv_rows: list[dict[str, str]],
    csv_headers: list[str] | None = None,
    log: str | None = None,
    constants: dict[str, Any] | None = None,
    examples: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = {
        "title": title,
        "current_mode": mode,
        "language": "auto",
        "ui": {"main_tab": 0, "result_subtab": 0, "selected_plot_index": 0, "plot_zoom": 1.0},
        "data": data,
        "constants": constants or _empty_constants(),
        "config": config,
        "result_snapshot": {"present": False},
    }
    workspace_hash = compute_workspace_hash(workspace)
    workspace["result_snapshot"] = {
        "present": True,
        "kind": mode,
        "result_of_hash": workspace_hash,
        "snapshot_only": True,
        "stale": False,
        "markdown": markdown,
        "log": log or "Generated example snapshot. Rerun from the stored data and configuration.",
        "csv": {"headers": csv_headers or (list(csv_rows[0].keys()) if csv_rows else []), "rows": csv_rows},
        "latex_source": "",
        "plots": [],
    }
    manifest = {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "app": {"name": "DataLab", "version": APP_VERSION},
        "created_at": GENERATED_TIMESTAMP,
        "updated_at": GENERATED_TIMESTAMP,
        "config": config,
        "data": data,
        "workspace": workspace,
    }
    if examples:
        manifest["examples"] = examples
    return manifest


def _root_payload(config: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    root_config = config["root_solving"]
    constants_config = root_config["constants"]
    table = data.get("canonical_table") or {}
    job = RootSolvingJob(
        equations=tuple(str(line).strip() for line in str(root_config["equations"]).splitlines() if str(line).strip()),
        unknown_rows=tuple(dict(row) for row in root_config["unknowns"]),
        data_headers=tuple(str(header) for header in table.get("headers") or ()),
        data_rows=tuple(tuple(str(cell) for cell in row) for row in table.get("rows") or ()),
        constants_enabled=bool(constants_config.get("enabled", False)),
        constants_rows=tuple(dict(row) for row in constants_config.get("rows") or ()),
        constants_view=str(constants_config.get("view") or "table"),
        constants_text=str(constants_config.get("text") or ""),
        mode=str(root_config.get("mode") or "auto"),
        scan_config={},
        precision=int(config.get("common", {}).get("mpmath_precision") or 16),
        display_digits=int(config.get("common", {}).get("display_digits") or 10),
        uncertainty_options=dict(root_config.get("uncertainty_options") or {"method": "auto"}),
    )
    return cast(dict[str, Any], _execute_root_solving_job_payload(job))


def _root_manifest(
    *,
    title: str,
    data: dict[str, Any],
    config: dict[str, Any],
    examples: dict[str, Any],
) -> dict[str, Any]:
    payload = _root_payload(config, data)
    return _manifest(
        title=title,
        mode="root_solving",
        data=data,
        config=config,
        markdown=str(payload["markdown"]),
        csv_rows=list(payload["csv_rows"]),
        csv_headers=list(payload["csv_headers"]),
        log=str(payload["log"]),
        examples=examples,
    )


def build_examples() -> dict[str, dict[str, Any]]:
    config = _base_config()
    config["extrapolation"]["uncertainty_column"] = "A"
    extrapolation = _manifest(
        title="Example - Extrapolation",
        mode="extrapolation",
        data=_table_section_from_file(DATASET_ROOT / "extrapolation_richardson.txt"),
        config=config,
        markdown="Richardson extrapolation example with a stored limit snapshot.",
        csv_rows=[{"quantity": "limit", "value": "1.0833"}, {"quantity": "order", "value": "2"}],
        examples={"category": "extrapolation", "source_files": ["examples/extrapolation_richardson.txt"]},
    )

    error_config = _base_config()
    error_config["error"]["formula"] = "V1 * V2"
    error = _manifest(
        title="Example - Error Propagation",
        mode="error",
        data=_table_section_from_file(DATASET_ROOT / "error_propagation.txt"),
        constants=_constants_section_from_file(DATASET_ROOT / "constants.txt"),
        config=error_config,
        markdown="First-order uncertainty propagation example for a product quantity.",
        csv_rows=[{"row": "1", "value": "3.000", "sigma": "0.091"}, {"row": "2", "value": "3.190", "sigma": "0.083"}],
        examples={
            "category": "error-propagation",
            "source_files": ["examples/error_propagation.txt", "examples/constants.txt"],
            "recipe_files": ["examples/recipes/error-product-basic.json"],
        },
    )

    error_units_config = _base_config()
    error_units_config["error"]["formula"] = "Distance / Time"
    error_units_config["error"]["method"] = "taylor"
    error_units_config["error"]["order"] = 1
    error_units_config["error"]["units"] = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {
            "Distance": {"unit": "m"},
            "Time": {"unit": "s"},
        },
        "constants": {},
        "parameters": {},
        "outputs": {
            "result": {"unit": "m/s"},
        },
    }
    error_units = _manifest(
        title="Example - Error Propagation With Units",
        mode="error",
        data=_table_section_from_rows(
            ["Distance", "Time"],
            [
                ["12.00(5)", "2.000(3)"],
                ["13.20(6)", "2.200(4)"],
                ["11.50(5)", "1.950(3)"],
            ],
        ),
        config=error_units_config,
        markdown=(
            "Display-only unit annotation example for speed = Distance / Time. "
            "It runs without pint; when pint is installed, switch the unit mode "
            "to validate-expression to check dimensional compatibility before evaluation."
        ),
        csv_headers=["row", "value", "sigma", "output_unit"],
        csv_rows=[
            {"row": "1", "value": "6.000", "sigma": "0.026", "output_unit": "m/s"},
            {"row": "2", "value": "6.000", "sigma": "0.029", "output_unit": "m/s"},
            {"row": "3", "value": "5.897", "sigma": "0.027", "output_unit": "m/s"},
        ],
        examples={
            "category": "error-propagation",
            "source_files": [],
            "variants": ["taylor", "units", "display_only", "validation_ready"],
        },
    )

    stats_config = _base_config()
    stats_config["statistics"]["value_column"] = "Value"
    stats_config["statistics"]["sigma_column"] = ""
    stats_config["statistics"]["mode"] = "weighted_sigma"
    statistics = _manifest(
        title="Example - Statistics",
        mode="statistics",
        data=_table_section_from_file(DATASET_ROOT / "statistics_weighted.txt"),
        config=stats_config,
        markdown="Weighted mean and sample-spread statistics example.",
        csv_rows=[{"quantity": "weighted_mean", "value": "1.232"}, {"quantity": "standard_error", "value": "0.006"}],
        examples={
            "category": "statistics",
            "source_files": ["examples/statistics_weighted.txt"],
            "recipe_files": ["examples/recipes/statistics-mean-basic.json"],
        },
    )

    stats_bootstrap_config = _base_config()
    stats_bootstrap_config["statistics"].update(
        {
            "workflow_mode": "bootstrap_confidence_intervals",
            "value_column": "Value",
            "value_columns": ["Value"],
            "sigma_column": "",
            "mode": "mean",
            "bootstrap": {
                "target_statistic": "mean",
                "confidence_level": "0.95",
                "resample_count": 100,
                "seed": "12345",
            },
        }
    )
    statistics_bootstrap = _manifest(
        title="Example - Bootstrap Confidence Interval",
        mode="statistics",
        data=_table_section_from_rows(
            ["Value"],
            [["1.02"], ["0.97"], ["1.05"], ["1.01"], ["0.99"], ["1.04"]],
        ),
        config=stats_bootstrap_config,
        markdown="Bootstrap confidence-interval example with a deterministic seed and embedded data.",
        csv_rows=[
            {"quantity": "target_statistic", "value": "mean"},
            {"quantity": "confidence_level", "value": "0.95"},
            {"quantity": "resample_count", "value": "100"},
        ],
        examples={"category": "statistics", "source_files": [], "variants": ["bootstrap", "confidence_interval", "seeded"]},
    )

    stats_hypothesis_config = _base_config()
    stats_hypothesis_config["statistics"].update(
        {
            "workflow_mode": "hypothesis_tests",
            "value_column": "A",
            "value_columns": ["A"],
            "sigma_column": "",
            "mode": "mean",
            "hypothesis": {
                "test_kind": "one_sample_t",
                "second_column": "",
                "null_parameter": "3",
                "alternative": "two_sided",
                "alpha": "0.05",
                "expected_source": "counts",
                "fitted_parameter_count": 0,
            },
        }
    )
    statistics_hypothesis = _manifest(
        title="Example - Hypothesis Test",
        mode="statistics",
        data=_table_section_from_rows(
            ["A"],
            [["2"], ["3"], ["4"], ["5"], ["6"]],
        ),
        config=stats_hypothesis_config,
        markdown="One-sample t-test example comparing column A against the null mean mu0=3.",
        csv_rows=[
            {"quantity": "test_kind", "value": "one_sample_t"},
            {"quantity": "mu0", "value": "3"},
            {"quantity": "alpha", "value": "0.05"},
        ],
        examples={"category": "statistics", "source_files": [], "variants": ["hypothesis_test", "one_sample_t"]},
    )

    stats_matrix_config = _base_config()
    stats_matrix_config["statistics"].update(
        {
            "workflow_mode": "covariance_correlation",
            "value_column": "A",
            "value_columns": ["A", "B", "C"],
            "sigma_column": "",
            "mode": "mean",
            "sample": True,
            "weighted_variance": False,
            "matrix": {"missing_policy": "listwise"},
        }
    )
    statistics_matrix = _manifest(
        title="Example - Covariance Correlation Matrix",
        mode="statistics",
        data=_table_section_from_rows(
            ["A", "B", "C"],
            [
                ["1.0", "2.0", "5.0"],
                ["2.0", "4.0", "4.0"],
                ["3.0", "6.0", "3.0"],
                ["4.0", "8.0", "2.0"],
                ["5.0", "10.0", "1.0"],
            ],
        ),
        config=stats_matrix_config,
        markdown="Covariance/correlation matrix example with three embedded numeric columns.",
        csv_rows=[
            {"quantity": "workflow_mode", "value": "covariance_correlation"},
            {"quantity": "missing_policy", "value": "listwise"},
            {"quantity": "value_columns", "value": "A, B, C"},
        ],
        examples={"category": "statistics", "source_files": [], "variants": ["covariance_correlation", "matrix", "listwise"]},
    )

    stats_grouped_config = _base_config()
    stats_grouped_config["statistics"].update(
        {
            "workflow_mode": "grouped_statistics",
            "group_column": "Group",
            "value_column": "Signal, Reference",
            "value_columns": ["Signal", "Reference"],
            "sigma_column": "Sigma",
            "mode": "weighted_sigma",
            "sample": True,
            "weighted_variance": True,
        }
    )
    statistics_grouped = _manifest(
        title="Example - Grouped Statistics",
        mode="statistics",
        data=_table_section_from_rows(
            ["Group", "Signal", "Reference", "Sigma"],
            [
                ["Control", "10.0", "9.8", "0.20"],
                ["Control", "10.4", "10.1", "0.20"],
                ["Control", "10.2", "10.0", "0.25"],
                ["Treatment", "12.5", "11.9", "0.30"],
                ["Treatment", "12.8", "12.2", "0.30"],
                ["Treatment", "13.1", "12.4", "0.35"],
            ],
        ),
        config=stats_grouped_config,
        markdown="Grouped statistics example with two numeric columns, a shared sigma column, and embedded data.",
        csv_rows=[
            {"quantity": "workflow_mode", "value": "grouped_statistics"},
            {"quantity": "group_column", "value": "Group"},
            {"quantity": "value_columns", "value": "Signal, Reference"},
        ],
        examples={"category": "statistics", "source_files": [], "variants": ["grouped_statistics", "multi_column", "weighted"]},
    )

    stats_time_series_rolling_config = _base_config()
    stats_time_series_rolling_config["statistics"].update(
        {
            "workflow_mode": "time_series_rolling",
            "value_column": "Signal",
            "value_columns": ["Signal"],
            "sigma_column": "Sigma",
            "mode": "mean",
            "time_series": {
                "series_method": "rolling_mean",
                "time_column": "Day",
                "window_size": 3,
                "min_periods": 2,
                "alignment": "right",
                "denominator": "sample",
                "ewma_parameter": "alpha",
                "ewma_value": "0.5",
                "adjust": False,
            },
        }
    )
    statistics_time_series_rolling = _manifest(
        title="Example - Time-Series Rolling Mean",
        mode="statistics",
        data=_table_section_from_rows(
            ["Day", "Signal", "Sigma"],
            [
                ["1", "10.0", "0.20"],
                ["2", "10.8", "0.20"],
                ["3", "11.4", "0.25"],
                ["4", "11.9", "0.25"],
                ["5", "12.6", "0.30"],
                ["6", "13.0", "0.30"],
            ],
        ),
        config=stats_time_series_rolling_config,
        markdown="Rolling mean example with embedded time labels and independent sigma propagation.",
        csv_rows=[
            {"quantity": "workflow_mode", "value": "time_series_rolling"},
            {"quantity": "series_method", "value": "rolling_mean"},
            {"quantity": "window_size", "value": "3"},
        ],
        examples={
            "category": "statistics",
            "source_files": [],
            "variants": ["time_series", "rolling_mean", "uncertainty"],
        },
    )

    stats_time_series_ewma_config = _base_config()
    stats_time_series_ewma_config["statistics"].update(
        {
            "workflow_mode": "time_series_rolling",
            "value_column": "Signal",
            "value_columns": ["Signal"],
            "sigma_column": "",
            "mode": "mean",
            "time_series": {
                "series_method": "ewma",
                "time_column": "Index",
                "window_size": 3,
                "min_periods": 3,
                "alignment": "right",
                "denominator": "sample",
                "ewma_parameter": "span",
                "ewma_value": "3",
                "adjust": True,
            },
        }
    )
    statistics_time_series_ewma = _manifest(
        title="Example - Time-Series EWMA",
        mode="statistics",
        data=_table_section_from_rows(
            ["Index", "Signal"],
            [
                ["1", "4.0"],
                ["2", "5.5"],
                ["3", "5.0"],
                ["4", "7.0"],
                ["5", "6.5"],
                ["6", "8.0"],
            ],
        ),
        config=stats_time_series_ewma_config,
        markdown="EWMA smoothing example with adjusted normalization and embedded data.",
        csv_rows=[
            {"quantity": "workflow_mode", "value": "time_series_rolling"},
            {"quantity": "series_method", "value": "ewma"},
            {"quantity": "span", "value": "3"},
        ],
        examples={"category": "statistics", "source_files": [], "variants": ["time_series", "ewma", "smoothing"]},
    )

    fitting_config = _base_config()
    fitting_config["common"]["mpmath_precision"] = 80
    fitting_config["fitting"]["expression"] = "A + B*x^(-C)"
    fitting = _manifest(
        title="Example - Fitting",
        mode="fitting",
        data=_table_section_from_file(DATASET_ROOT / "fitting_powerlaw.txt"),
        config=fitting_config,
        markdown=(
            "Explicit custom fitting example with weighted data, parameter constraints, "
            "high precision settings, and an implicit-model rerun context."
        ),
        csv_rows=[{"parameter": "A", "value": "1.01"}, {"parameter": "B", "value": "0.36"}, {"parameter": "C", "value": "0.08"}],
        examples={
            "category": "fitting",
            "source_files": ["examples/fitting_powerlaw.txt"],
            "recipe_files": ["examples/recipes/fitting-custom-powerlaw.json"],
            "variants": ["custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"],
        },
    )
    quantum_delta_rows = [
        ["4", "-0.01161947382(2)"],
        ["5", "-0.01182004861(4)"],
        ["6", "-0.01192302789(3)"],
        ["7", "-0.01198312684(3)"],
        ["8", "-0.01202134197(4)"],
        ["9", "-0.01204718702(6)"],
        ["10", "-0.01206549920(6)"],
        ["11", "-0.01207895610(8)"],
        ["12", "-0.0120891399(1)"],
        ["13", "-0.0120970357(1)"],
        ["14", "-0.0121032829(2)"],
        ["15", "-0.0121083122(2)"],
    ]
    quantum_rows = _quantum_defect_energy_rows(quantum_delta_rows)
    quantum_config = _base_config()
    quantum_config["common"]["mpmath_precision"] = 50
    quantum_config["fitting"].update(
        {
            "model": "self_consistent",
            "expression": "CR*M/(M+1)/(n-delta)^2",
            "target_column": "E",
            "weighted": True,
            "variables": [{"name": "n", "column": "n"}],
            "constraints_enabled": True,
            "parameter_rows": [],
            "parameter_orphans": [],
            "custom_constants": {"enabled": False, "view": "table", "rows": [], "text": ""},
            "implicit": {
                "schema": 2,
                "active": True,
                "x_variables": ["n"],
                "implicit_variable": "delta",
                "equation": "d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
                "output_expression": "CR*M/(M+1)/(n-delta)^2",
                "method": "root",
                "initial": "-0.012",
                "tolerance": "1e-28",
                "max_iterations": 80,
                "timeout_seconds": 300,
                "constraints_enabled": True,
                "parameters": [
                    {"name": "d0", "initial": "-0.01213", "fixed": "", "min": "-0.02", "max": "0"},
                    {"name": "d2", "initial": "0", "fixed": "", "min": "-1", "max": "1"},
                    {"name": "d4", "initial": "0", "fixed": "", "min": "-1", "max": "1"},
                ],
                "parameter_orphans": [],
                "constants": [
                    {"name": "CR", "value": "3.2898419602500e9"},
                    {"name": "M", "value": "7294.29954171"},
                ],
                "constants_enabled": True,
                "constants_view": "table",
                "constants_text": "CR = 3.2898419602500e9\nM = 7294.29954171\n",
            },
        }
    )
    quantum = _manifest(
        title="Example - Quantum Defect Implicit Fit",
        mode="fitting",
        data=_table_section_from_rows(["n", "E", "sigma_E"], quantum_rows),
        config=quantum_config,
        markdown=(
            "Self-consistent quantum-defect fitting example using an ionization-energy output expression. "
            "The workspace stores the data directly so it can be opened without resolving an external data-file path."
        ),
        csv_rows=[
            {"parameter": "d0", "value": "-0.01213"},
            {"parameter": "d2", "value": "0"},
            {"parameter": "d4", "value": "0"},
        ],
        examples={
            "category": "fitting",
            "source_files": [],
            "variants": ["self_consistent", "implicit", "quantum_defect", "ionization_energy", "weighted"],
        },
    )
    root_scalar_config = _base_config()
    root_scalar = _root_manifest(
        title="Example - Root Solving With Linear Uncertainty",
        data=_table_section_from_rows([], []),
        config=root_scalar_config,
        examples={"category": "root-solving", "source_files": [], "variants": ["scalar", "linear_uncertainty"]},
    )

    root_monte_carlo_config = _base_config()
    root_monte_carlo_config["root_solving"]["uncertainty_options"] = {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 2000,
        "monte_carlo_seed": "42",
    }
    root_monte_carlo = _root_manifest(
        title="Example - Root Solving With Monte Carlo Uncertainty",
        data=_table_section_from_rows([], []),
        config=root_monte_carlo_config,
        examples={"category": "root-solving", "source_files": [], "variants": ["scalar", "monte_carlo"]},
    )

    root_batch_config = _base_config()
    root_batch_config["root_solving"] = {
        "schema": 1,
        "equations": "x^2 - A",
        "mode": "scalar",
        "unknowns": [{"name": "x", "initial": "1", "lower": "", "upper": ""}],
        "constants": {
            "enabled": False,
            "view": "table",
            "rows": [],
            "text": "",
            "numeric_mode": "uncertainty",
        },
        "uncertainty_options": {
            "method": "taylor",
            "taylor_order": 1,
            "monte_carlo_samples": 2000,
            "monte_carlo_seed": "",
        },
    }
    root_batch = _root_manifest(
        title="Example - Batch Root Solving",
        data=_table_section_from_rows(["A"], [["1.0(1)"], ["4.0(2)"], ["9.0(3)"]]),
        config=root_batch_config,
        examples={
            "category": "root-solving",
            "source_files": [],
            "recipe_files": ["examples/recipes/root-batch-quadratic.json"],
            "variants": ["batch", "linear_uncertainty"],
        },
    )
    return {
        "extrapolation.datalab": extrapolation,
        "error-propagation.datalab": error,
        "error-propagation-units.datalab": error_units,
        "statistics.datalab": statistics,
        "statistics-bootstrap.datalab": statistics_bootstrap,
        "statistics-hypothesis.datalab": statistics_hypothesis,
        "statistics-matrix.datalab": statistics_matrix,
        "statistics-grouped.datalab": statistics_grouped,
        "statistics-time-series-rolling.datalab": statistics_time_series_rolling,
        "statistics-time-series-ewma.datalab": statistics_time_series_ewma,
        "fitting.datalab": fitting,
        "quantum-defect-implicit.datalab": quantum,
        "root-scalar-with-uncertainty.datalab": root_scalar,
        "root-monte-carlo-uncertainty.datalab": root_monte_carlo,
        "root-batch-quadratic.datalab": root_batch,
    }


def main() -> None:
    examples = build_examples()
    EXAMPLE_ROOT.mkdir(parents=True, exist_ok=True)
    for stale in EXAMPLE_ROOT.glob("*.datalab"):
        if stale.name not in set(EXAMPLE_NAMES):
            raise RuntimeError(f"Refusing to overwrite unexpected example workspace: {stale}")
    for name, manifest in examples.items():
        target = EXAMPLE_ROOT / name
        write_workspace(target, manifest, {})
        target.chmod(0o644)
    catalog_target = EXAMPLE_ROOT / "example_catalog.json"
    catalog_target.write_text(
        json.dumps(example_index_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    catalog_target.chmod(0o644)


if __name__ == "__main__":
    main()
