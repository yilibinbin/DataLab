#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app_desktop.webengine_spike_assets import build_asset_evidence_template  # noqa: E402
from tools.webengine_measurement_evidence import build_measurement_evidence_template  # noqa: E402
from tools.webengine_spike_report import build_report  # noqa: E402


ASSET_TEMPLATE_NAME = "webengine-assets-template.json"
MEASUREMENT_TEMPLATE_NAME = "webengine-measurements.json"
REPORT_NAME = "webengine-spike-report.json"


def build_evidence_bundle(
    repo_root: Path,
    out_dir: Path,
    *,
    generated_at: str | None = None,
    artifact_manifest_path: Path | None = None,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    asset_manifest_path = out_dir / ASSET_TEMPLATE_NAME
    measurement_evidence_path = out_dir / MEASUREMENT_TEMPLATE_NAME
    report_path = out_dir / REPORT_NAME

    _write_json(
        asset_manifest_path,
        build_asset_evidence_template(generated_at=generated_at),
    )
    _write_json(
        measurement_evidence_path,
        build_measurement_evidence_template(generated_at=generated_at),
    )
    _write_json(
        report_path,
        build_report(
            repo_root,
            artifact_manifest_path=artifact_manifest_path,
            measurement_evidence_path=measurement_evidence_path,
            asset_manifest_path=asset_manifest_path,
        ),
    )
    return {
        "asset_manifest": asset_manifest_path,
        "measurement_evidence": measurement_evidence_path,
        "report": report_path,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write DataLab WebEngine spike evidence files as one bundle.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--out-dir", type=Path, default=Path("build/webengine-evidence"), help="Bundle output directory.")
    parser.add_argument("--artifact-manifest", type=Path, help="Optional release-artifact size manifest JSON.")
    parser.add_argument("--generated-at", help="Timestamp to use in generated evidence templates.")
    args = parser.parse_args(argv)

    outputs = build_evidence_bundle(
        args.repo_root,
        args.out_dir,
        generated_at=args.generated_at,
        artifact_manifest_path=args.artifact_manifest,
    )
    print(json.dumps({key: str(path) for key, path in outputs.items()}, ensure_ascii=False, sort_keys=True))
    return 0


__all__ = [
    "ASSET_TEMPLATE_NAME",
    "MEASUREMENT_TEMPLATE_NAME",
    "REPORT_NAME",
    "build_evidence_bundle",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
