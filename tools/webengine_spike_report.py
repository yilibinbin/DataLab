#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.qt_packaging_excludes import (  # noqa: E402
    REQUIRED_WEBENGINE_EXCLUDES,
    exclude_sync_status,
    packaging_qt_excludes,
)
from tools.record_release_artifact_sizes import validate_artifact_size_manifest  # noqa: E402
from tools.webengine_measurement_evidence import (  # noqa: E402
    REQUIRED_MEASUREMENT_GATES,
    load_measurement_evidence,
)
from app_desktop.webengine_spike_contract import (  # noqa: E402
    ALLOWED_BRIDGE_METHODS,
    MAX_BRIDGE_PAYLOAD_BYTES,
    MAX_BRIDGE_PAYLOAD_DEPTH,
    WEBENGINE_SPIKE_HOST,
    WEBENGINE_SPIKE_SCHEME,
    build_content_security_policy,
)
from app_desktop.webengine_spike_assets import (  # noqa: E402
    WEBENGINE_ASSET_ROOT,
    build_asset_serving_contract_summary,
    inspect_offline_assets,
    load_asset_evidence,
)


REQUIRED_SECURITY_GATES = (
    "remote_url_denial",
    "content_security_policy",
    "no_file_url_access",
    "bridge_method_allowlist",
    "bridge_input_validation",
    "no_arbitrary_shell_file_bridge",
    "offline_vendored_assets",
    "no_runtime_network_requirement",
    "custom_url_scheme",
)


CONTRACT_SECURITY_EVIDENCE: dict[str, dict[str, Any]] = {
    "remote_url_denial": {
        "evidence": "tests/test_webengine_spike_contract.py::test_navigation_url_contract_allows_only_custom_local_scheme",
        "contract_module": "app_desktop.webengine_spike_contract",
    },
    "content_security_policy": {
        "evidence": "tests/test_webengine_spike_contract.py::test_content_security_policy_is_restrictive_and_offline",
        "contract_module": "app_desktop.webengine_spike_contract",
    },
    "no_file_url_access": {
        "evidence": "tests/test_webengine_spike_contract.py::test_navigation_url_contract_allows_only_custom_local_scheme",
        "contract_module": "app_desktop.webengine_spike_contract",
    },
    "bridge_method_allowlist": {
        "evidence": "tests/test_webengine_spike_contract.py::test_bridge_allowlist_contains_only_expected_non_shell_actions",
        "contract_module": "app_desktop.webengine_spike_contract",
    },
    "bridge_input_validation": {
        "evidence": "tests/test_webengine_spike_contract.py::test_bridge_payload_validation_rejects_unsafe_payloads",
        "contract_module": "app_desktop.webengine_spike_contract",
    },
    "no_arbitrary_shell_file_bridge": {
        "evidence": "tests/test_webengine_spike_contract.py::test_bridge_payload_validation_rejects_unsafe_payloads",
        "contract_module": "app_desktop.webengine_spike_contract",
    },
    "no_runtime_network_requirement": {
        "evidence": "app_desktop.webengine_spike_assets.inspect_offline_assets",
        "contract_module": "app_desktop.webengine_spike_assets",
    },
    "custom_url_scheme": {
        "evidence": "tests/test_webengine_spike_assets.py::test_resolve_asset_url_accepts_only_integrity_checked_manifest_assets",
        "contract_module": "app_desktop.webengine_spike_assets",
    },
}


def build_report(
    repo_root: Path,
    artifact_manifest_path: Path | None = None,
    measurement_evidence_path: Path | None = None,
    asset_manifest_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    excludes = packaging_qt_excludes(repo_root)
    exclude_status = exclude_sync_status(excludes)
    asset_specs = None
    asset_root = WEBENGINE_ASSET_ROOT
    asset_manifest_ref = None
    if asset_manifest_path is not None:
        asset_evidence = load_asset_evidence(asset_manifest_path)
        asset_specs = asset_evidence.specs
        asset_root = asset_evidence.asset_root
        asset_manifest_ref = _portable_report_path(Path(asset_manifest_path), repo_root)

    if asset_specs is None:
        offline_assets = inspect_offline_assets(repo_root)
        asset_serving_contract = build_asset_serving_contract_summary()
    else:
        offline_assets = inspect_offline_assets(repo_root, specs=asset_specs, asset_root=asset_root)
        asset_serving_contract = build_asset_serving_contract_summary(specs=asset_specs, asset_root=asset_root)
    if asset_manifest_ref is not None:
        offline_assets["evidence_manifest"] = asset_manifest_ref
    security_gates = [_missing_gate(key) for key in REQUIRED_SECURITY_GATES]
    measurement_gates = [_measurement_gate(key) for key in REQUIRED_MEASUREMENT_GATES]
    _apply_contract_security_evidence(security_gates)
    _apply_offline_asset_evidence(security_gates, offline_assets)
    _apply_artifact_manifest(measurement_gates, artifact_manifest_path, repo_root=repo_root)
    _apply_measurement_evidence(measurement_gates, measurement_evidence_path, repo_root=repo_root)

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "decision": "NO_GO",
        "decision_reason": (
            "QtWebEngine remains disabled for shipping builds until every "
            "security, offline, measurement, packaging, and platform gate has evidence."
        ),
        "shipping_runtime": {
            "webengine_enabled": not bool(exclude_status["webengine_excluded"]),
            "webengine_import_policy": "not imported by the shipping Qt Widgets runtime",
        },
        "bridge_contract": {
            "scheme": WEBENGINE_SPIKE_SCHEME,
            "host": WEBENGINE_SPIKE_HOST,
            "content_security_policy": build_content_security_policy(),
            "allowed_methods": sorted(ALLOWED_BRIDGE_METHODS),
            "max_payload_bytes": MAX_BRIDGE_PAYLOAD_BYTES,
            "max_payload_depth": MAX_BRIDGE_PAYLOAD_DEPTH,
        },
        "asset_serving_contract": asset_serving_contract,
        "offline_assets": offline_assets,
        "packaging": {
            "qt_excludes": {
                **excludes,
                **exclude_status,
                "required_webengine_excludes": list(REQUIRED_WEBENGINE_EXCLUDES),
            }
        },
        "security_gates": security_gates,
        "measurement_gates": measurement_gates,
    }
    report["decision_blockers"] = _decision_blockers(report)
    if _all_gates_passed(report):
        report["decision"] = "GO"
        report["decision_reason"] = "All QtWebEngine spike gates have explicit passing evidence."
        report["decision_blockers"] = _empty_decision_blockers()
    return report


def _missing_gate(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "status": "missing",
        "evidence": None,
    }


def _measurement_gate(key: str) -> dict[str, Any]:
    gate = _missing_gate(key)
    if key == "artifact_size_baseline":
        gate["expected_source"] = "tools/record_release_artifact_sizes.py output"
    return gate


def _apply_contract_security_evidence(security_gates: list[dict[str, Any]]) -> None:
    gate_by_key = {gate["key"]: gate for gate in security_gates}
    for key, evidence in CONTRACT_SECURITY_EVIDENCE.items():
        gate_by_key[key].update({"status": "pass", **evidence})


def _apply_offline_asset_evidence(
    security_gates: list[dict[str, Any]],
    offline_assets: dict[str, Any],
) -> None:
    gate_by_key = {gate["key"]: gate for gate in security_gates}
    offline_status = "pass" if offline_assets["passed"] else "missing"
    gate_by_key["offline_vendored_assets"].update(
        {
            "status": offline_status,
            "evidence": "offline_assets",
            "provided_count": offline_assets["provided_count"],
            "required_count": offline_assets["required_count"],
            "invalid_count": offline_assets["invalid_count"],
        }
    )
    if "evidence_manifest" in offline_assets:
        gate_by_key["offline_vendored_assets"]["evidence_manifest"] = offline_assets["evidence_manifest"]
    gate_by_key["no_runtime_network_requirement"].update(
        {
            "status": "pass" if not offline_assets["runtime_network_allowed"] else "fail",
            "evidence": "offline_assets.runtime_network_allowed",
        }
    )


def _apply_artifact_manifest(
    measurement_gates: list[dict[str, Any]],
    artifact_manifest_path: Path | None,
    *,
    repo_root: Path,
) -> None:
    if artifact_manifest_path is None:
        return
    path = Path(artifact_manifest_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifacts = validate_artifact_size_manifest(payload)
    artifact_gate = next(gate for gate in measurement_gates if gate["key"] == "artifact_size_baseline")
    artifact_gate.update(
        {
            "status": "provided",
            "evidence": _portable_report_path(path, repo_root),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }
    )


def _apply_measurement_evidence(
    measurement_gates: list[dict[str, Any]],
    measurement_evidence_path: Path | None,
    *,
    repo_root: Path,
) -> None:
    if measurement_evidence_path is None:
        return
    path = Path(measurement_evidence_path)
    evidence_rows = load_measurement_evidence(
        path,
        allowed_keys=[gate["key"] for gate in measurement_gates],
    )
    gate_by_key = {gate["key"]: gate for gate in measurement_gates}
    for key, row in evidence_rows.items():
        if row["status"] == "missing" and gate_by_key[key]["status"] != "missing":
            continue
        gate_by_key[key].update(row)
        gate_by_key[key]["evidence_manifest"] = _portable_report_path(path, repo_root)


def _portable_report_path(path: Path, repo_root: Path) -> str:
    resolved = Path(path).resolve()
    root = Path(repo_root).resolve()
    if resolved.is_relative_to(root):
        return resolved.relative_to(root).as_posix()
    return f"<external>/{resolved.name}"


def _all_gates_passed(report: dict[str, Any]) -> bool:
    qt_excludes = report["packaging"]["qt_excludes"]
    if not qt_excludes["synchronized"]:
        return False
    if qt_excludes["webengine_excluded"]:
        return False
    security_ok = all(row["status"] == "pass" for row in report["security_gates"])
    measurement_ok = all(row["status"] == "pass" for row in report["measurement_gates"])
    return security_ok and measurement_ok


def _decision_blockers(report: dict[str, Any]) -> dict[str, Any]:
    packaging = []
    qt_excludes = report["packaging"]["qt_excludes"]
    if not qt_excludes["synchronized"]:
        packaging.append(
            {
                "key": "qt_excludes_synchronized",
                "status": "blocked",
                "reason": "Qt packaging exclude lists are not synchronized across build entry points.",
            }
        )
    if qt_excludes["webengine_excluded"]:
        packaging.append(
            {
                "key": "webengine_excluded",
                "status": "blocked",
                "reason": "QtWebEngine remains excluded from shipping packaging entry points.",
            }
        )

    security = [
        {"key": row["key"], "status": row["status"]}
        for row in report["security_gates"]
        if row["status"] != "pass"
    ]
    measurement = [
        {"key": row["key"], "status": row["status"]}
        for row in report["measurement_gates"]
        if row["status"] != "pass"
    ]
    return {
        "packaging": packaging,
        "security": security,
        "measurement": measurement,
        "summary": {
            "packaging": len(packaging),
            "security": len(security),
            "measurement": len(measurement),
        },
    }


def _empty_decision_blockers() -> dict[str, Any]:
    return {
        "packaging": [],
        "security": [],
        "measurement": [],
        "summary": {"packaging": 0, "security": 0, "measurement": 0},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the DataLab QtWebEngine spike evidence report.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root.")
    parser.add_argument("--artifact-manifest", type=Path, help="Optional release-artifact size manifest JSON.")
    parser.add_argument("--asset-manifest", type=Path, help="Optional offline WebEngine asset evidence JSON.")
    parser.add_argument("--measurement-evidence", type=Path, help="Optional WebEngine measurement evidence JSON.")
    parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    report = build_report(
        args.repo_root,
        artifact_manifest_path=args.artifact_manifest,
        measurement_evidence_path=args.measurement_evidence,
        asset_manifest_path=args.asset_manifest,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
