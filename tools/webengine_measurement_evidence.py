from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ALLOWED_MEASUREMENT_STATUSES = frozenset({"missing", "provided", "pass", "fail"})

REQUIRED_MEASUREMENT_GATES = (
    "artifact_size_baseline",
    "macos_artifact_size_delta",
    "windows_artifact_size_delta",
    "cold_start_time",
    "memory_usage",
    "macos_signing_notarization_helper",
    "windows_signing_helper",
    "updater_artifact_size_install",
    "ci_display_requirements",
    "cjk_ime_input_quality",
)


class MeasurementEvidenceError(ValueError):
    """Raised when a WebEngine measurement evidence manifest is malformed."""


def build_measurement_evidence_template(generated_at: str | None = None) -> dict[str, Any]:
    timestamp = generated_at
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "generated_at": timestamp,
        "measurements": [
            {
                "key": key,
                "status": "missing",
            }
            for key in REQUIRED_MEASUREMENT_GATES
        ],
    }


def load_measurement_evidence(
    path: Path,
    *,
    allowed_keys: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise MeasurementEvidenceError("Measurement evidence payload must be a JSON object")
    measurements = payload.get("measurements")
    if not isinstance(measurements, list):
        raise MeasurementEvidenceError("Measurement evidence must contain a measurements list")

    allowed = set(allowed_keys) if allowed_keys is not None else set(REQUIRED_MEASUREMENT_GATES)
    rows: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(measurements):
        normalized = _validate_measurement_row(row, index=index, allowed_keys=allowed)
        key = normalized["key"]
        if key in rows:
            raise MeasurementEvidenceError(f"Duplicate measurement gate evidence: {key}")
        rows[key] = normalized
    return rows


def _validate_measurement_row(
    row: Any,
    *,
    index: int,
    allowed_keys: set[str] | None,
) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise MeasurementEvidenceError(f"Measurement row {index} must be a JSON object")
    key = row.get("key")
    if not isinstance(key, str) or not key:
        raise MeasurementEvidenceError(f"Measurement row {index} must have a non-empty key")
    if allowed_keys is not None and key not in allowed_keys:
        raise MeasurementEvidenceError(f"Unknown measurement gate key: {key}")

    status = row.get("status")
    if status not in ALLOWED_MEASUREMENT_STATUSES:
        raise MeasurementEvidenceError(f"Invalid measurement status for {key}: {status!r}")

    evidence = row.get("evidence")
    if status in {"provided", "pass", "fail"}:
        if not isinstance(evidence, str) or not evidence.strip():
            raise MeasurementEvidenceError(f"Measurement gate {key} requires non-empty evidence")
        _validate_evidence_reference(evidence)
    elif evidence is not None:
        if not isinstance(evidence, str):
            raise MeasurementEvidenceError(f"Measurement gate {key} evidence must be a string")
        _validate_evidence_reference(evidence)

    normalized = dict(row)
    normalized["key"] = key
    normalized["status"] = status
    if isinstance(evidence, str):
        normalized["evidence"] = evidence.strip()
    return normalized


def _validate_evidence_reference(evidence: str) -> None:
    value = evidence.strip()
    if not value:
        raise MeasurementEvidenceError("Evidence reference must be non-empty")
    if "\x00" in value or "\\" in value:
        raise MeasurementEvidenceError(f"Unsafe evidence reference: {evidence!r}")

    parsed = urlsplit(value)
    if parsed.scheme == "file":
        raise MeasurementEvidenceError("file:// evidence references are not portable")
    if parsed.scheme in {"http", "https"}:
        if not parsed.netloc:
            raise MeasurementEvidenceError(f"Invalid evidence URL: {evidence!r}")
        return
    if parsed.scheme:
        raise MeasurementEvidenceError(f"Unsupported evidence reference scheme: {parsed.scheme}")

    path = Path(value)
    if path.is_absolute() or value.startswith("../") or "/../" in value or value == "..":
        raise MeasurementEvidenceError("Evidence references must be repo-relative or public URLs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or create DataLab WebEngine measurement evidence JSON.")
    parser.add_argument("path", nargs="?", type=Path, help="Measurement evidence JSON to validate.")
    parser.add_argument("--template", action="store_true", help="Write a template covering all required gates.")
    parser.add_argument("--generated-at", help="Timestamp to use in template output.")
    parser.add_argument("--out", type=Path, help="Optional output path for template JSON.")
    args = parser.parse_args(argv)

    if args.template:
        payload = json.dumps(
            build_measurement_evidence_template(generated_at=args.generated_at),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        return 0
    if args.path is None:
        parser.error("path is required unless --template is used")
    load_measurement_evidence(args.path)
    return 0


__all__ = [
    "ALLOWED_MEASUREMENT_STATUSES",
    "MeasurementEvidenceError",
    "REQUIRED_MEASUREMENT_GATES",
    "build_measurement_evidence_template",
    "load_measurement_evidence",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
