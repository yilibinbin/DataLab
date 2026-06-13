from __future__ import annotations

import json
from pathlib import Path

from tools.webengine_measurement_evidence import REQUIRED_MEASUREMENT_GATES


ROOT = Path(__file__).resolve().parents[1]


def test_webengine_evidence_bundle_writes_templates_and_report(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import REQUIRED_WEBENGINE_ASSETS
    from tools.webengine_evidence_bundle import main

    out_dir = tmp_path / "webengine-evidence"

    assert main(["--repo-root", str(ROOT), "--out-dir", str(out_dir), "--generated-at", "2026-06-12T00:00:00Z"]) == 0

    asset_payload = json.loads((out_dir / "webengine-assets-template.json").read_text(encoding="utf-8"))
    measurement_payload = json.loads((out_dir / "webengine-measurements.json").read_text(encoding="utf-8"))
    report_payload = json.loads((out_dir / "webengine-spike-report.json").read_text(encoding="utf-8"))

    assert [row["path"] for row in asset_payload["assets"]] == [spec.path for spec in REQUIRED_WEBENGINE_ASSETS]
    assert {row["status"] for row in asset_payload["assets"]} == {"missing"}
    assert [row["key"] for row in measurement_payload["measurements"]] == list(REQUIRED_MEASUREMENT_GATES)
    assert {row["status"] for row in measurement_payload["measurements"]} == {"missing"}
    assert report_payload["decision"] == "NO_GO"
    assert report_payload["offline_assets"]["evidence_manifest"] == "<external>/webengine-assets-template.json"
    measurement = {row["key"]: row for row in report_payload["measurement_gates"]}
    assert measurement["cold_start_time"]["evidence_manifest"] == "<external>/webengine-measurements.json"


def test_webengine_evidence_bundle_accepts_artifact_manifest(tmp_path: Path) -> None:
    from tools.webengine_evidence_bundle import main

    artifact_manifest = tmp_path / "release-artifact-sizes.json"
    artifact_manifest.write_text(
        json.dumps(
            {
                "artifact_count": 1,
                "artifacts": [
                    {"path": "dist/DataLab.pkg", "bytes": 123, "human_size": "123 B"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "webengine-evidence"

    assert main(
        [
            "--repo-root",
            str(ROOT),
            "--out-dir",
            str(out_dir),
            "--artifact-manifest",
            str(artifact_manifest),
        ]
    ) == 0

    report_payload = json.loads((out_dir / "webengine-spike-report.json").read_text(encoding="utf-8"))
    artifact_gate = {
        row["key"]: row for row in report_payload["measurement_gates"]
    }["artifact_size_baseline"]

    assert artifact_gate["status"] == "provided"
    assert artifact_gate["artifact_count"] == 1
    assert artifact_gate["evidence"] == "<external>/release-artifact-sizes.json"
