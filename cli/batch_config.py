"""Parse + validate DataLab batch YAML configs.

Schema:

    jobs:
      - name: str                # human-readable (required, safe basename)
        operation: str           # "fit" | "calc" (required)
        data_path: str           # path to 2-column CSV or .dat (required)
        output_dir: str          # where to write artefacts (required)
        model: str               # for fit (default "polynomial")
        precision: int           # mpmath dps, default 50
        log_scale: str | null    # None / "x" / "y" / "xy"

No Qt / PySide6 imports — this module is import-safe from CI / SSH /
container contexts. YAML parsed via stdlib-adjacent PyYAML (already
listed in the desktop/web requirements).

We deliberately do NOT use pydantic: the schema is small, stable,
and the CLI surface area is intentionally narrow. A bespoke
dataclass validator with clear error messages is cheaper to maintain
and gives better error locality for end users debugging their YAML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__all__ = [
    "ALLOWED_OPERATIONS",
    "BatchConfig",
    "BatchJob",
    "load_batch_config",
]


# Whitelist — adding a new entry requires a conscious decision to
# expose the operation via the CLI surface.
ALLOWED_OPERATIONS = frozenset({"fit", "calc"})

# Defensive caps. A batch YAML claiming 10 000 jobs is almost always
# a user mistake; cap so we don't spawn a runaway process.
MAX_JOBS_PER_BATCH = 1_000

# Known-safe ranges for precision values at the CLI boundary. Matches
# the ``shared.precision`` clamp so a scripted caller can't request
# a billion-digit mpmath computation.
MIN_PRECISION = 10
MAX_PRECISION = 1_000

# Job ``name`` is later used as the JSON output filename
# (``output_dir / f"{name}.json"`` in cli/main.py). Without this
# regex, a YAML containing ``name: "../etc/cron.d/evil"`` would write
# the JSON to an arbitrary path reachable from output_dir. The YAML
# is operator-controlled (defence-in-depth — a CI pipeline that
# accepts user-contributed batch configs is a realistic abuse path),
# so we whitelist a conservative basename grammar:
# - first char must be alphanumeric
# - remainder may include letters, digits, dot, dash, underscore
# - max 128 chars
# - no slash, backslash, null, leading dot
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,127}$")


@dataclass(frozen=True)
class BatchJob:
    """One operation to run in a batch."""

    name: str
    operation: str
    data_path: Path
    output_dir: Path
    model: str = "polynomial"
    precision: int = 50
    log_scale: Optional[str] = None


@dataclass(frozen=True)
class BatchConfig:
    """Parsed batch YAML contents."""

    jobs: list[BatchJob] = field(default_factory=list)


def _require_str(obj: object, field_name: str, job_label: str) -> str:
    if not isinstance(obj, str) or not obj.strip():
        raise ValueError(
            f"Job {job_label!r}: field {field_name!r} must be a non-empty string"
        )
    return obj.strip()


def _require_int(
    obj: object,
    field_name: str,
    job_label: str,
    default: int,
    min_val: int,
    max_val: int,
) -> int:
    if obj is None:
        return default
    try:
        value = int(obj)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Job {job_label!r}: field {field_name!r} must be an integer"
        ) from exc
    if not (min_val <= value <= max_val):
        raise ValueError(
            f"Job {job_label!r}: {field_name}={value} outside "
            f"allowed range [{min_val}, {max_val}]"
        )
    return value


def _coerce_job(raw: dict, index: int) -> BatchJob:
    if not isinstance(raw, dict):
        raise ValueError(
            f"Job #{index}: entry must be a mapping, got {type(raw).__name__}"
        )
    name = _require_str(raw.get("name"), "name", f"#{index}")
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"Job #{index}: 'name' must be a safe basename "
            f"(alphanumeric / dot / dash / underscore, no slashes "
            f"or leading dot, ≤128 chars). Got: {name!r}"
        )
    operation = _require_str(raw.get("operation"), "operation", name)
    if operation not in ALLOWED_OPERATIONS:
        allowed = ", ".join(sorted(ALLOWED_OPERATIONS))
        raise ValueError(
            f"Job {name!r}: unknown operation {operation!r}. "
            f"Allowed: {allowed}"
        )
    data_path_str = _require_str(raw.get("data_path"), "data_path", name)
    data_path = Path(data_path_str).expanduser()
    if not data_path.exists():
        raise FileNotFoundError(
            f"Job {name!r}: data_path does not exist: {data_path}"
        )
    if not data_path.is_file():
        raise ValueError(
            f"Job {name!r}: data_path is not a regular file: {data_path}"
        )
    output_dir_str = _require_str(raw.get("output_dir"), "output_dir", name)
    output_dir = Path(output_dir_str).expanduser()
    # output_dir doesn't need to exist yet — runner creates it — but
    # we do reject nonsense like output_dir pointing to an existing file.
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(
            f"Job {name!r}: output_dir exists but is not a directory: "
            f"{output_dir}"
        )

    model_raw = raw.get("model")
    if model_raw is None:
        model = "polynomial"
    else:
        model = _require_str(model_raw, "model", name)

    precision = _require_int(
        raw.get("precision"), "precision", name,
        default=50, min_val=MIN_PRECISION, max_val=MAX_PRECISION,
    )

    log_scale = raw.get("log_scale")
    if log_scale is not None and not isinstance(log_scale, str):
        raise ValueError(
            f"Job {name!r}: log_scale must be string or null, got "
            f"{type(log_scale).__name__}"
        )

    return BatchJob(
        name=name,
        operation=operation,
        data_path=data_path,
        output_dir=output_dir,
        model=model,
        precision=precision,
        log_scale=log_scale,
    )


def load_batch_config(path: Path) -> BatchConfig:
    """Load + validate a YAML batch file into a ``BatchConfig``.

    Raises
    ------
    FileNotFoundError
        If a job's ``data_path`` does not exist.
    ValueError
        For malformed YAML, unknown operations, out-of-range precision,
        empty job lists, or missing required fields. The error message
        names the offending job so end users can locate the problem
        without line numbers.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "cli.batch_config requires PyYAML; install via "
            "'pip install pyyaml' (already in gui_requirements.txt and "
            "web_requirements.txt)"
        ) from exc

    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Batch config not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read batch config {path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Malformed YAML in {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Batch config {path}: top-level must be a mapping with a "
            "'jobs' key"
        )

    jobs_raw = data.get("jobs")
    if jobs_raw is None:
        raise ValueError(f"Batch config {path}: missing 'jobs' key")
    if not isinstance(jobs_raw, list):
        raise ValueError(
            f"Batch config {path}: 'jobs' must be a list, got "
            f"{type(jobs_raw).__name__}"
        )
    if not jobs_raw:
        raise ValueError(
            f"Batch config {path}: 'jobs' list is empty — nothing to do"
        )
    if len(jobs_raw) > MAX_JOBS_PER_BATCH:
        raise ValueError(
            f"Batch config {path}: {len(jobs_raw)} jobs exceeds cap of "
            f"{MAX_JOBS_PER_BATCH}"
        )

    jobs = [_coerce_job(j, i) for i, j in enumerate(jobs_raw)]
    return BatchConfig(jobs=jobs)
