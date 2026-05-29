from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.workspace_io import write_workspace  # noqa: E402
from shared.workspace_schema import compute_workspace_hash, sha256_bytes  # noqa: E402

EXAMPLE_ROOT = PROJECT_ROOT / "examples" / "workspaces"
APP_VERSION = "2.0.2"
EXAMPLE_NAMES = {
    "extrapolation.datalab",
    "error-propagation.datalab",
    "statistics.datalab",
    "fitting.datalab",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_section(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
    decoded_text = "\n".join(["\t".join(headers), *("\t".join(row) for row in rows)]) + "\n"
    canonical = {"headers": headers, "rows": rows}
    return {
        "enabled": True,
        "source_kind": "manual_table",
        "source_path": None,
        "source_path_label": None,
        "active_view": "table",
        "decoded_text": decoded_text,
        "encoding": "utf-8",
        "newline": "lf",
        "original_bytes_sha256": sha256_bytes(decoded_text.encode("utf-8")),
        "raw_bytes_path": None,
        "canonical_table": canonical,
        "sha256": sha256_bytes((decoded_text + repr(canonical)).encode("utf-8")),
    }


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
                "x_variables": ("x",),
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
    }


def _manifest(
    *,
    title: str,
    mode: str,
    data: dict[str, Any],
    config: dict[str, Any],
    markdown: str,
    csv_rows: list[dict[str, str]],
    examples: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = {
        "title": title,
        "current_mode": mode,
        "language": "auto",
        "ui": {"main_tab": 0, "result_subtab": 0, "selected_plot_index": 0, "plot_zoom": 1.0},
        "data": data,
        "constants": _empty_constants(),
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
        "log": "Generated example snapshot. Rerun from the stored data and configuration.",
        "csv": {"headers": list(csv_rows[0].keys()) if csv_rows else [], "rows": csv_rows},
        "latex_source": "",
        "plots": [],
    }
    now = _now()
    manifest = {
        "schema": "datalab.workspace.v1",
        "schema_version": 1,
        "app": {"name": "DataLab", "version": APP_VERSION},
        "created_at": now,
        "updated_at": now,
        "config": config,
        "data": data,
        "workspace": workspace,
    }
    if examples:
        manifest["examples"] = examples
    return manifest


def build_examples() -> dict[str, dict[str, Any]]:
    config = _base_config()
    extrapolation = _manifest(
        title="Example - Extrapolation",
        mode="extrapolation",
        data=_data_section(
            ["n", "Value"],
            [["2", "1.2541"], ["3", "1.1806"], ["4", "1.1428"], ["5", "1.1217"], ["6", "1.1089"]],
        ),
        config=config,
        markdown="Richardson extrapolation example with a stored limit snapshot.",
        csv_rows=[{"quantity": "limit", "value": "1.0833"}, {"quantity": "order", "value": "2"}],
        examples={"category": "extrapolation"},
    )

    error_config = _base_config()
    error_config["error"]["formula"] = "sqrt((x*dy)^2 + (y*dx)^2)"
    error = _manifest(
        title="Example - Error Propagation",
        mode="error",
        data=_data_section(
            ["x", "dx", "y", "dy"],
            [["1.20", "0.03", "2.50", "0.04"], ["1.45", "0.02", "2.20", "0.05"]],
        ),
        config=error_config,
        markdown="First-order uncertainty propagation example for a product quantity.",
        csv_rows=[{"row": "1", "value": "3.000", "sigma": "0.091"}, {"row": "2", "value": "3.190", "sigma": "0.083"}],
        examples={"category": "error-propagation"},
    )

    stats_config = _base_config()
    stats_config["statistics"]["value_column"] = "Value"
    stats_config["statistics"]["sigma_column"] = "Sigma"
    statistics = _manifest(
        title="Example - Statistics",
        mode="statistics",
        data=_data_section(
            ["Value", "Sigma"],
            [["1.234", "0.012"], ["1.219", "0.015"], ["1.241", "0.011"], ["1.228", "0.014"]],
        ),
        config=stats_config,
        markdown="Weighted mean and sample-spread statistics example.",
        csv_rows=[{"quantity": "weighted_mean", "value": "1.232"}, {"quantity": "standard_error", "value": "0.006"}],
        examples={"category": "statistics"},
    )

    fitting_config = _base_config()
    fitting_config["common"]["mpmath_precision"] = 80
    fitting = _manifest(
        title="Example - Fitting",
        mode="fitting",
        data=_data_section(
            ["x", "y", "sigma_y"],
            [["0.0", "1.02", "0.05"], ["1.0", "1.43", "0.04"], ["2.0", "2.04", "0.05"], ["3.0", "2.84", "0.06"]],
        ),
        config=fitting_config,
        markdown=(
            "Explicit custom fitting example with weighted data, parameter constraints, "
            "high precision settings, and an implicit-model rerun context."
        ),
        csv_rows=[{"parameter": "A", "value": "1.01"}, {"parameter": "B", "value": "0.36"}, {"parameter": "C", "value": "0.08"}],
        examples={
            "category": "fitting",
            "variants": ["custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"],
        },
    )
    return {
        "extrapolation.datalab": extrapolation,
        "error-propagation.datalab": error,
        "statistics.datalab": statistics,
        "fitting.datalab": fitting,
    }


def main() -> None:
    examples = build_examples()
    EXAMPLE_ROOT.mkdir(parents=True, exist_ok=True)
    for stale in EXAMPLE_ROOT.glob("*.datalab"):
        if stale.name not in EXAMPLE_NAMES:
            raise RuntimeError(f"Refusing to overwrite unexpected example workspace: {stale}")
    for name, manifest in examples.items():
        target = EXAMPLE_ROOT / name
        write_workspace(target, manifest, {})
        target.chmod(0o644)


if __name__ == "__main__":
    main()
