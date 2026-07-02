"""CLI batch mode — regression tests.

``datalab batch config.yml`` runs one or more DataLab operations in
non-interactive mode, producing the same artefacts (PNG, LaTeX, JSON)
that the GUI would. This is the scripting surface for labs that want
to integrate DataLab into automation pipelines.

Contract pinned here:
- ``cli.main.run_batch_file(path)`` parses a YAML config and dispatches
  per-entry to the pure-function workers from ``app_desktop.workers_core``.
- Each entry specifies an ``operation`` (``calc`` / ``fit``),
  input data (inline list or file path), and an
  ``output`` directory.
- The batch never touches PySide6; the CLI is import-safe from headless
  contexts (CI, SSH, containers).
- Unknown operations raise at validation time, not mid-batch.
- Invalid paths / malformed YAML return a non-zero exit code from the
  ``datalab`` entry point.
- The entry point is exposed as ``python -m cli`` for packaging that
  doesn't install the console script.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def _data_csv(tmp_path: Path) -> Path:
    """Write a minimal 2-column CSV — linear y = 2x."""
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n2,4\n3,6\n4,8\n5,10\n", encoding="utf-8")
    return path


@pytest.fixture
def _batch_config(_data_csv: Path, tmp_path: Path) -> Path:
    """Write a batch YAML invoking a single explicit fit."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    config = f"""
jobs:
  - name: linear-fit
    operation: fit
    data_path: {_data_csv}
    model: linear
    output_dir: {out_dir}
""".strip()
    path = tmp_path / "batch.yml"
    path.write_text(config, encoding="utf-8")
    return path


def test_run_calc_preserves_requested_high_precision_in_limit(tmp_path: Path):
    """CLI batch `calc` must serialize the extrapolated limit at the requested
    precision, not truncate it to the ambient mp.dps via bare str(mpf) outside a
    precision_guard (audit finding F6)."""
    from mpmath import mp

    from cli.batch_config import BatchJob
    from cli.main import _run_calc

    # A geometric series 1 + 1/2 + 1/4 + ... whose Wynn-eps limit is exactly 2,
    # but we assert the SIGNIFICANT-DIGIT COUNT of the serialized limit, which is
    # what truncation to dps=15 would cap. Use a slowly-varying convergent whose
    # accelerated value carries many digits: partial sums of sum 6/k^2 -> pi^2.
    data = tmp_path / "seq.csv"
    rows = ["n,y"]
    total = mp.mpf(0)
    with mp.workdps(80):
        for n in range(1, 40):
            total += mp.mpf(6) / mp.mpf(n) ** 2
            rows.append(f"{n},{mp.nstr(total, 60)}")
    data.write_text("\n".join(rows), encoding="utf-8")

    # mp.dps is process-global; set a low ambient precision to simulate the CLI
    # before the per-job guard, then restore it so this mutation can't leak into
    # later tests (the per-job precision_guard is exactly what we're asserting).
    original_dps = mp.dps
    try:
        mp.dps = 15  # simulate the ambient CLI precision before per-job guard
        job = BatchJob(
            name="hp-calc", operation="calc", data_path=data,
            output_dir=tmp_path, model=None, precision=50,
        )
        result = _run_calc(job)
    finally:
        mp.dps = original_dps

    limit = str(result["limit"])
    digits = len(limit.replace(".", "").replace("-", "").lstrip("0"))
    assert digits > 20, f"limit truncated to ambient dps: {limit!r} ({digits} digits)"


def test_load_batch_config_round_trips(_batch_config: Path):
    """Parse a batch YAML into a BatchConfig dataclass."""
    from cli.batch_config import load_batch_config

    config = load_batch_config(_batch_config)
    assert len(config.jobs) == 1
    job = config.jobs[0]
    assert job.name == "linear-fit"
    assert job.operation == "fit"
    assert job.model == "linear"


def test_load_batch_config_rejects_unknown_operation(tmp_path: Path):
    path = tmp_path / "bad.yml"
    path.write_text(
        """
jobs:
  - name: x
    operation: frobnicate
    data_path: /nonexistent
    output_dir: /tmp
""",
        encoding="utf-8",
    )
    from cli.batch_config import load_batch_config

    with pytest.raises(ValueError, match="operation"):
        load_batch_config(path)


def test_load_batch_config_rejects_missing_data_path(tmp_path: Path):
    path = tmp_path / "bad.yml"
    path.write_text(
        """
jobs:
  - name: x
    operation: fit
    data_path: /definitely/does/not/exist.csv
    output_dir: /tmp
    model: polynomial
""",
        encoding="utf-8",
    )
    from cli.batch_config import load_batch_config

    with pytest.raises((FileNotFoundError, ValueError)):
        load_batch_config(path)


def test_load_batch_config_rejects_malformed_yaml(tmp_path: Path):
    path = tmp_path / "bad.yml"
    path.write_text("this is not:\n  - well: {formed", encoding="utf-8")
    from cli.batch_config import load_batch_config

    with pytest.raises(ValueError):
        load_batch_config(path)


def test_load_batch_config_empty_jobs_list_rejected(tmp_path: Path):
    """A ``jobs: []`` config is a user mistake — fail loud."""
    path = tmp_path / "empty.yml"
    path.write_text("jobs: []\n", encoding="utf-8")
    from cli.batch_config import load_batch_config

    with pytest.raises(ValueError, match="empty|no jobs"):
        load_batch_config(path)


def test_run_batch_produces_json_artefact(_batch_config: Path, tmp_path: Path):
    """End-to-end: the CLI produces a result JSON for each job."""
    from cli.main import run_batch_file

    exit_code = run_batch_file(_batch_config)
    assert exit_code == 0

    out_dir = tmp_path / "out"
    json_files = list(out_dir.glob("*.json"))
    assert json_files, f"Expected result JSON in {out_dir}"
    # The JSON must be real JSON with at least a `model` field
    data = json.loads(json_files[0].read_text())
    assert "model" in data or "fit" in data or "params" in data


def test_load_batch_config_allows_calc_without_model(_data_csv: Path, tmp_path: Path):
    out_dir = tmp_path / "calc-out"
    cfg = tmp_path / "calc.yml"
    cfg.write_text(
        f"""
jobs:
  - name: calc-job
    operation: calc
    data_path: {_data_csv}
    output_dir: {out_dir}
""",
        encoding="utf-8",
    )
    from cli.batch_config import load_batch_config

    job = load_batch_config(cfg).jobs[0]

    assert job.operation == "calc"
    assert job.model == ""


@pytest.mark.parametrize(
    ("model", "expected_model"),
    [
        ("poly", "polynomial"),
        ("linear", "polynomial"),
        ("inverse", "inverse_power"),
    ],
)
def test_run_batch_maps_legacy_explicit_model_aliases(
    _data_csv: Path,
    tmp_path: Path,
    model: str,
    expected_model: str,
):
    from cli.main import run_batch_file

    out_dir = tmp_path / f"out-{model}"
    cfg = tmp_path / f"{model}.yml"
    cfg.write_text(
        f"""
jobs:
  - name: alias-fit
    operation: fit
    data_path: {_data_csv}
    model: {model}
    output_dir: {out_dir}
""",
        encoding="utf-8",
    )

    assert run_batch_file(cfg) == 0
    payload = json.loads((out_dir / "alias-fit.json").read_text(encoding="utf-8"))
    assert payload["model"] == expected_model


def test_load_batch_config_requires_explicit_fit_model(_data_csv: Path, tmp_path: Path):
    cfg = tmp_path / "missing-model.yml"
    cfg.write_text(
        f"""
jobs:
  - name: missing-model
    operation: fit
    data_path: {_data_csv}
    output_dir: {tmp_path / "out"}
""",
        encoding="utf-8",
    )
    from cli.batch_config import load_batch_config

    with pytest.raises(ValueError, match="model"):
        load_batch_config(cfg)


def test_run_batch_rejects_ambiguous_polynomial_model(_data_csv: Path, tmp_path: Path):
    from cli.main import run_batch_file

    out_dir = tmp_path / "out-polynomial"
    cfg = tmp_path / "polynomial.yml"
    cfg.write_text(
        f"""
jobs:
  - name: ambiguous-fit
    operation: fit
    data_path: {_data_csv}
    model: polynomial
    output_dir: {out_dir}
""",
        encoding="utf-8",
    )

    assert run_batch_file(cfg) != 0
    assert not (out_dir / "ambiguous-fit.json").exists()


@pytest.mark.parametrize("model", ["log_poly", "exp_combo", "auto"])
def test_run_batch_rejects_removed_fit_models_without_output(
    _data_csv: Path,
    tmp_path: Path,
    model: str,
):
    from cli.main import run_batch_file

    out_dir = tmp_path / f"out-{model}"
    cfg = tmp_path / f"{model}.yml"
    cfg.write_text(
        f"""
jobs:
  - name: removed-fit
    operation: fit
    data_path: {_data_csv}
    model: {model}
    output_dir: {out_dir}
""",
        encoding="utf-8",
    )

    assert run_batch_file(cfg) != 0
    assert not (out_dir / "removed-fit.json").exists()


@pytest.mark.parametrize("model", ["pade", "power_limit", "custom"])
def test_run_batch_rejects_models_not_supported_by_cli_runner(
    _data_csv: Path,
    tmp_path: Path,
    model: str,
):
    from cli.main import run_batch_file

    out_dir = tmp_path / f"out-{model}"
    cfg = tmp_path / f"{model}.yml"
    cfg.write_text(
        f"""
jobs:
  - name: unsupported-fit
    operation: fit
    data_path: {_data_csv}
    model: {model}
    output_dir: {out_dir}
""",
        encoding="utf-8",
    )

    assert run_batch_file(cfg) != 0
    assert not (out_dir / "unsupported-fit.json").exists()


def test_run_batch_rejects_removed_auto_fit_operation_without_output(
    _data_csv: Path,
    tmp_path: Path,
):
    from cli.main import run_batch_file

    out_dir = tmp_path / "out-auto-fit"
    cfg = tmp_path / "auto_fit.yml"
    cfg.write_text(
        f"""
jobs:
  - name: removed-operation
    operation: auto_fit
    data_path: {_data_csv}
    output_dir: {out_dir}
""",
        encoding="utf-8",
    )

    assert run_batch_file(cfg) != 0
    assert not (out_dir / "removed-operation.json").exists()


def test_run_batch_returns_nonzero_on_error(tmp_path: Path):
    """Malformed config → non-zero exit code."""
    bad = tmp_path / "bad.yml"
    bad.write_text("jobs: [{operation: frobnicate}]", encoding="utf-8")
    from cli.main import run_batch_file

    assert run_batch_file(bad) != 0


def test_cli_entrypoint_via_python_dash_m(tmp_path: Path, _batch_config: Path):
    """``python -m cli batch config.yml`` is the documented entry point."""
    result = subprocess.run(
        [sys.executable, "-m", "cli", "batch", str(_batch_config)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        timeout=60,
    )
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"


def test_cli_help_shows_usage():
    """``python -m cli --help`` prints usage with 'batch' subcommand."""
    result = subprocess.run(
        [sys.executable, "-m", "cli", "--help"],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "batch" in result.stdout


def test_cli_no_args_returns_nonzero():
    """Empty args → print usage, exit non-zero."""
    result = subprocess.run(
        [sys.executable, "-m", "cli"],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
