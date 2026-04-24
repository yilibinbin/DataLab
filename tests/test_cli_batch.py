"""CLI batch mode — regression tests.

``datalab batch config.yml`` runs one or more DataLab operations in
non-interactive mode, producing the same artefacts (PNG, LaTeX, JSON)
that the GUI would. This is the scripting surface for labs that want
to integrate DataLab into automation pipelines.

Contract pinned here:
- ``cli.main.run_batch_file(path)`` parses a YAML config and dispatches
  per-entry to the pure-function workers from ``app_desktop.workers_core``.
- Each entry specifies an ``operation`` (``calc`` / ``fit`` /
  ``auto_fit``), input data (inline list or file path), and an
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
    """Write a batch YAML invoking a single auto-fit."""
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
    model: linear
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
