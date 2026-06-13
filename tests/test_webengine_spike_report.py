from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.webengine_spike_report import (
    REQUIRED_MEASUREMENT_GATES,
    REQUIRED_SECURITY_GATES,
    REQUIRED_WEBENGINE_EXCLUDES,
    build_report,
    main,
)


ROOT = Path(__file__).resolve().parents[1]


def test_webengine_spike_report_defaults_to_no_go_with_all_required_gates() -> None:
    report = build_report(ROOT)

    assert report["decision"] == "NO_GO"
    assert report["shipping_runtime"]["webengine_enabled"] is False
    assert report["offline_assets"]["passed"] is False
    assert report["offline_assets"]["runtime_network_allowed"] is False
    assert report["bridge_contract"]["scheme"] == "datalab-workbench"
    assert "workspace.openDialog" in report["bridge_contract"]["allowed_methods"]
    assert "connect-src 'none'" in report["bridge_contract"]["content_security_policy"]
    assert report["asset_serving_contract"]["strict_manifest_only"] is True
    assert report["asset_serving_contract"]["entrypoint_url"] == "datalab-workbench://app/"
    assert report["asset_serving_contract"]["url_validation"] == "app_desktop.webengine_spike_contract.validate_navigation_url"
    assert "index.html" in report["asset_serving_contract"]["required_paths"]
    assert report["decision_blockers"]["packaging"] == [
        {
            "key": "webengine_excluded",
            "status": "blocked",
            "reason": "QtWebEngine remains excluded from shipping packaging entry points.",
        }
    ]
    assert report["decision_blockers"]["security"] == [
        {"key": "offline_vendored_assets", "status": "missing"}
    ]
    assert {
        row["key"]: row["status"]
        for row in report["decision_blockers"]["measurement"]
    } == {key: "missing" for key in REQUIRED_MEASUREMENT_GATES}
    assert report["decision_blockers"]["summary"] == {
        "packaging": 1,
        "security": 1,
        "measurement": len(REQUIRED_MEASUREMENT_GATES),
    }

    security_keys = {row["key"] for row in report["security_gates"]}
    measurement_keys = {row["key"] for row in report["measurement_gates"]}

    assert security_keys == set(REQUIRED_SECURITY_GATES)
    assert measurement_keys == set(REQUIRED_MEASUREMENT_GATES)
    security_by_key = {row["key"]: row for row in report["security_gates"]}
    contract_backed_security_gates = {
        "remote_url_denial",
        "content_security_policy",
        "no_file_url_access",
        "bridge_method_allowlist",
        "bridge_input_validation",
        "no_arbitrary_shell_file_bridge",
        "no_runtime_network_requirement",
        "custom_url_scheme",
    }
    for key in contract_backed_security_gates:
        assert security_by_key[key]["status"] == "pass"
        assert security_by_key[key]["evidence"]
        assert security_by_key[key]["contract_module"].startswith("app_desktop.")
    assert all(row["status"] == "missing" for row in report["measurement_gates"])

    offline_gate = security_by_key["offline_vendored_assets"]
    assert offline_gate["status"] == "missing"
    assert offline_gate["evidence"] == "offline_assets"


def test_webengine_spike_report_requires_shipping_excludes_to_remain_synced() -> None:
    report = build_report(ROOT)
    qt_excludes = report["packaging"]["qt_excludes"]

    assert qt_excludes["synchronized"] is True
    assert qt_excludes["webengine_excluded"] is True
    assert set(REQUIRED_WEBENGINE_EXCLUDES).issubset(set(qt_excludes["DataLab.spec"]))
    assert set(qt_excludes["DataLab.spec"]) == set(qt_excludes["build_mac_data_gui.sh"])
    assert set(qt_excludes["DataLab.spec"]) == set(qt_excludes["build_windows_data_gui.ps1"])


def test_webengine_spike_report_reads_optional_artifact_size_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release-artifact-sizes.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact_count": 2,
                "artifacts": [
                    {"path": "dist/DataLab.app", "bytes": 100, "human_size": "100 B"},
                    {"path": "dist/DataLab.exe", "bytes": 200, "human_size": "200 B"},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_report(ROOT, artifact_manifest_path=manifest_path)
    artifact_gate = {
        row["key"]: row for row in report["measurement_gates"]
    }["artifact_size_baseline"]

    assert artifact_gate["status"] == "provided"
    assert artifact_gate["artifact_count"] == 2
    assert artifact_gate["evidence"] == "<external>/release-artifact-sizes.json"
    assert str(tmp_path) not in json.dumps(report)
    assert report["decision"] == "NO_GO"


def test_webengine_spike_report_rejects_malformed_artifact_size_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release-artifact-sizes.json"
    manifest_path.write_text(
        json.dumps(
            {
                "artifact_count": 1,
                "artifacts": [
                    {"path": "/Users/fanghao/dist/DataLab.pkg", "bytes": 100, "human_size": "100 B"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Artifact path"):
        build_report(ROOT, artifact_manifest_path=manifest_path)


def test_webengine_spike_report_reads_optional_measurement_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "webengine-measurements.json"
    evidence_path.write_text(
        json.dumps(
            {
                "measurements": [
                    {
                        "key": "cold_start_time",
                        "status": "pass",
                        "evidence": "build/webengine/cold-start.json",
                        "value": 1.4,
                        "unit": "s",
                    },
                    {
                        "key": "memory_usage",
                        "status": "fail",
                        "evidence": "build/webengine/memory.json",
                        "value": 900,
                        "unit": "MiB",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_report(ROOT, measurement_evidence_path=evidence_path)
    measurement = {row["key"]: row for row in report["measurement_gates"]}

    assert measurement["cold_start_time"]["status"] == "pass"
    assert measurement["cold_start_time"]["value"] == 1.4
    assert measurement["cold_start_time"]["evidence_manifest"] == "<external>/webengine-measurements.json"
    assert measurement["memory_usage"]["status"] == "fail"
    assert measurement["memory_usage"]["evidence"] == "build/webengine/memory.json"
    assert measurement["macos_artifact_size_delta"]["status"] == "missing"
    assert str(tmp_path) not in json.dumps(report)
    blockers = {row["key"]: row["status"] for row in report["decision_blockers"]["measurement"]}
    assert "cold_start_time" not in blockers
    assert blockers["memory_usage"] == "fail"
    assert blockers["macos_artifact_size_delta"] == "missing"
    assert report["decision"] == "NO_GO"


def test_webengine_spike_report_missing_measurement_template_does_not_downgrade_artifacts(tmp_path: Path) -> None:
    from tools.webengine_measurement_evidence import build_measurement_evidence_template

    artifact_manifest_path = tmp_path / "release-artifact-sizes.json"
    artifact_manifest_path.write_text(
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
    measurement_path = tmp_path / "webengine-measurements.json"
    measurement_path.write_text(json.dumps(build_measurement_evidence_template()), encoding="utf-8")

    report = build_report(
        ROOT,
        artifact_manifest_path=artifact_manifest_path,
        measurement_evidence_path=measurement_path,
    )
    artifact_gate = {
        row["key"]: row for row in report["measurement_gates"]
    }["artifact_size_baseline"]

    assert artifact_gate["status"] == "provided"
    assert artifact_gate["artifact_count"] == 1
    assert artifact_gate["evidence"] == "<external>/release-artifact-sizes.json"


def test_webengine_spike_report_reads_optional_asset_manifest(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import build_asset_evidence_template

    manifest_path = tmp_path / "webengine-assets-template.json"
    manifest_path.write_text(json.dumps(build_asset_evidence_template()), encoding="utf-8")

    report = build_report(ROOT, asset_manifest_path=manifest_path)
    offline_gate = {
        row["key"]: row for row in report["security_gates"]
    }["offline_vendored_assets"]

    assert report["offline_assets"]["evidence_manifest"] == "<external>/webengine-assets-template.json"
    assert offline_gate["status"] == "missing"
    assert offline_gate["evidence_manifest"] == "<external>/webengine-assets-template.json"
    assert str(tmp_path) not in json.dumps(report)
    assert report["decision"] == "NO_GO"


def test_webengine_spike_report_cli_writes_json(tmp_path: Path) -> None:
    output = tmp_path / "webengine-spike-report.json"

    assert main(["--repo-root", str(ROOT), "--out", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["decision"] == "NO_GO"
    assert payload["packaging"]["qt_excludes"]["synchronized"] is True


def test_webengine_spike_report_cli_accepts_measurement_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "webengine-measurements.json"
    evidence_path.write_text(
        json.dumps(
            {
                "measurements": [
                    {
                        "key": "ci_display_requirements",
                        "status": "provided",
                        "evidence": "https://github.com/yilibinbin/DataLab/actions/runs/456",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "webengine-spike-report.json"

    assert main(
        [
            "--repo-root",
            str(ROOT),
            "--measurement-evidence",
            str(evidence_path),
            "--out",
            str(output),
        ]
    ) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    measurement = {row["key"]: row for row in payload["measurement_gates"]}
    assert measurement["ci_display_requirements"]["status"] == "provided"
    assert payload["decision"] == "NO_GO"


def test_webengine_spike_report_cli_accepts_asset_manifest(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import build_asset_evidence_template

    manifest_path = tmp_path / "webengine-assets-template.json"
    manifest_path.write_text(json.dumps(build_asset_evidence_template()), encoding="utf-8")
    output = tmp_path / "webengine-spike-report.json"

    assert main(
        [
            "--repo-root",
            str(ROOT),
            "--asset-manifest",
            str(manifest_path),
            "--out",
            str(output),
        ]
    ) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["offline_assets"]["evidence_manifest"] == "<external>/webengine-assets-template.json"
    assert payload["decision"] == "NO_GO"


def test_shipping_desktop_import_does_not_load_webengine_stack() -> None:
    probe = """
from __future__ import annotations

import json
import sys

import app_desktop.window

forbidden_prefixes = (
    "shared.pdf_preview",
    "shared.pdf_preview_integration",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
print(json.dumps(loaded))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
