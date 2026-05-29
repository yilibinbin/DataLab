"""DataLab CLI main entry point.

Exposes ``datalab batch config.yml`` (installed console script) and
``python -m cli batch config.yml`` (module-run form for packaging
that skips console-script installation).

Pattern: argparse dispatch to sub-command handlers. Each handler
returns a non-zero exit code on failure so scripts can cascade.
"""

from __future__ import annotations

import argparse
import json
import logging
import traceback
from pathlib import Path
from typing import Optional, Sequence

__all__ = ["main", "run_batch_file"]

_logger = logging.getLogger(__name__)


_REMOVED_FIT_MODELS = frozenset({"auto", "auto_fit", "log_poly", "exp_combo"})
_CLI_MODEL_ALIASES = {
    "poly": "polynomial",
    "polynomial": "polynomial",
    "linear": "polynomial",
    "quadratic": "polynomial",
    "cubic": "polynomial",
    "inverse": "inverse_power",
    "inverse_power": "inverse_power",
}
_POLYNOMIAL_DEGREES = {
    "linear": 1,
    "poly": 1,
    "polynomial": 1,
    "quadratic": 2,
    "cubic": 3,
}
_PUBLIC_CLI_MODELS = frozenset(
    {"polynomial", "inverse_power", "pade", "power_limit", "custom"}
)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _read_xy_csv(path: Path) -> tuple[list[float], list[float]]:
    """Minimal CSV reader for the CLI: expects an ``x,y`` header and
    2 numeric columns. Uses ``shared.parsing.parse_clipboard_tabular``
    so the CSV parsing is shared with the desktop's paste flow — one
    parser to maintain.
    """
    text = path.read_text(encoding="utf-8")
    from shared.parsing import parse_clipboard_tabular

    result = parse_clipboard_tabular(text)
    if len(result.rows) == 0:
        raise ValueError(f"No data rows found in {path}")
    # Accept first two numeric columns; ignore extras.
    xs: list[float] = []
    ys: list[float] = []
    for row in result.rows:
        if len(row) < 2:
            continue
        x_val, y_val = row[0], row[1]
        if x_val is None or y_val is None:
            continue
        xs.append(float(x_val))
        ys.append(float(y_val))
    if len(xs) < 2:
        raise ValueError(
            f"{path}: need at least 2 data rows with both x and y numeric"
        )
    return xs, ys


def _run_fit(job) -> dict:
    """Execute a single explicit CLI fit."""
    from fitting import build_inverse_series_definition, build_polynomial_definition
    from fitting.auto_models import (
        fit_linear_model,
    )
    from shared.precision import precision_guard

    raw_model = (job.model or "polynomial").strip()
    model_key = raw_model.lower()
    if model_key in _REMOVED_FIT_MODELS:
        raise ValueError(
            f"Job {job.name!r}: model {raw_model!r} has been removed. "
            "Choose an explicit model: polynomial, inverse_power, "
            "pade, power_limit, or custom."
        )

    canonical_model = _CLI_MODEL_ALIASES.get(model_key, model_key)
    if canonical_model not in _PUBLIC_CLI_MODELS:
        available = ", ".join(sorted(_PUBLIC_CLI_MODELS))
        raise ValueError(
            f"Job {job.name!r}: unknown model {job.model!r}. "
            f"Available models: {available}"
        )
    if canonical_model == "polynomial":
        definition = build_polynomial_definition(_POLYNOMIAL_DEGREES.get(model_key, 1))
    elif canonical_model == "inverse_power":
        definition = build_inverse_series_definition(1, 3)
    else:
        raise ValueError(
            f"Job {job.name!r}: model {canonical_model!r} is an explicit "
            "DataLab model, but this CLI batch runner currently supports "
            "only polynomial and inverse_power fits. Use the desktop or web "
            "UI for this model."
        )

    xs, ys = _read_xy_csv(job.data_path)
    with precision_guard(job.precision):
        fit_result = fit_linear_model(
            definition, xs, ys, precision=job.precision
        )

    params = {k: float(v) for k, v in (fit_result.params or {}).items()}
    errors = {
        k: float(v) for k, v in (fit_result.param_errors_stat or {}).items()
    }
    return {
        "job_name": job.name,
        "operation": "fit",
        "model": canonical_model,
        "model_label": definition.label,
        "data_path": str(job.data_path),
        "n_points": len(xs),
        "precision": job.precision,
        "params": params,
        "param_errors_stat": errors,
    }


def _run_calc(job) -> dict:
    """Execute a sequence-extrapolation calc via the Wynn-ε accelerator.

    For the CLI we keep this minimal — richer options (Richardson,
    Levin, power-law) are available through the desktop GUI. The
    method hard-defaults to ``wynn_epsilon``; future iterations can
    expose ``method`` via the YAML schema.
    """
    from extrapolation_methods.accelerators import (
        SequenceAcceleratorConfig,
        apply_sequence_accelerator,
    )

    xs, ys = _read_xy_csv(job.data_path)
    if len(ys) < 3:
        raise ValueError(
            f"Job {job.name!r}: calc needs at least 3 points, got {len(ys)}"
        )
    config = SequenceAcceleratorConfig(precision=job.precision)
    result = apply_sequence_accelerator("wynn_epsilon", ys, config)
    return {
        "job_name": job.name,
        "operation": "calc",
        "method": "wynn_epsilon",
        "data_path": str(job.data_path),
        "precision": job.precision,
        "limit": str(result.value),
        "metadata": {
            k: (str(v) if hasattr(v, "_mpf_") else v)
            for k, v in (result.metadata or {}).items()
        },
    }


def _dispatch(job) -> dict:
    """Route to the operation-specific runner."""
    if job.operation == "fit":
        return _run_fit(job)
    if job.operation == "calc":
        return _run_calc(job)
    # load_batch_config already rejects unknown operations, but
    # defense-in-depth:
    raise ValueError(f"Unhandled operation: {job.operation!r}")


def run_batch_file(config_path: Path) -> int:
    """Execute all jobs in a batch YAML. Returns 0 on success,
    non-zero on any job failure (first failure stops the batch)."""
    from cli.batch_config import load_batch_config

    try:
        config = load_batch_config(Path(config_path))
    except (FileNotFoundError, ValueError, ImportError) as exc:
        _logger.error("Failed to load batch config: %s", exc)
        return 2

    failures = 0
    for job in config.jobs:
        _logger.info("Running job %r (%s)", job.name, job.operation)
        try:
            result = _dispatch(job)
        except Exception as exc:  # noqa: BLE001
            _logger.error("Job %r failed: %s", job.name, exc)
            _logger.debug("Traceback:\n%s", traceback.format_exc())
            failures += 1
            continue

        job.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = job.output_dir / f"{job.name}.json"
        out_path.write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        _logger.info("  → wrote %s", out_path)

    return 0 if failures == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datalab",
        description=(
            "DataLab command-line interface — headless batch mode for "
            "the GUI's computation flows. See docs/web/deploy.md for "
            "usage examples."
        ),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable DEBUG-level logging",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    batch_p = subparsers.add_parser(
        "batch",
        help="Run all jobs in a YAML config non-interactively",
    )
    batch_p.add_argument(
        "config", type=Path,
        help="Path to batch YAML config file",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns the exit code; ``cli.__main__`` calls
    ``sys.exit(main())``."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits directly on --help
        return int(exc.code or 0)

    _configure_logging(args.verbose)

    if args.command == "batch":
        return run_batch_file(args.config)

    parser.print_help()
    return 2
