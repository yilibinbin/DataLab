from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_measurement_evidence_rejects_malformed_payloads(tmp_path: Path) -> None:
    from tools.webengine_measurement_evidence import MeasurementEvidenceError, load_measurement_evidence

    malformed_payloads = [
        [],
        {"measurements": {}},
        {"measurements": [{"key": "unknown", "status": "pass", "evidence": "build/unknown.json"}]},
        {
            "measurements": [
                {"key": "cold_start_time", "status": "pass", "evidence": "build/a.json"},
                {"key": "cold_start_time", "status": "pass", "evidence": "build/b.json"},
            ]
        },
        {"measurements": [{"key": "cold_start_time", "status": "ok", "evidence": "build/cold.json"}]},
        {"measurements": [{"key": "cold_start_time", "status": "pass"}]},
        {"measurements": [{"key": "cold_start_time", "status": "pass", "evidence": ""}]},
        {"measurements": [{"key": "cold_start_time", "status": "pass", "evidence": "/Users/fanghao/private.json"}]},
        {"measurements": [{"key": "cold_start_time", "status": "pass", "evidence": "file:///tmp/private.json"}]},
        {"measurements": [{"key": "cold_start_time", "status": "pass", "evidence": "../private.json"}]},
    ]

    for index, payload in enumerate(malformed_payloads):
        path = tmp_path / f"bad-{index}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(MeasurementEvidenceError):
            load_measurement_evidence(path)


def test_measurement_evidence_accepts_partial_gate_statuses(tmp_path: Path) -> None:
    from tools.webengine_measurement_evidence import load_measurement_evidence

    path = tmp_path / "webengine-measurements.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-12T00:00:00Z",
                "measurements": [
                    {
                        "key": "cold_start_time",
                        "status": "pass",
                        "evidence": "build/webengine/cold-start.json",
                        "value": 1.42,
                        "unit": "s",
                        "threshold": "<=2.00",
                    },
                    {
                        "key": "memory_usage",
                        "status": "fail",
                        "evidence": "https://github.com/yilibinbin/DataLab/actions/runs/123",
                        "value": 880,
                        "unit": "MiB",
                        "threshold": "<=600",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    evidence = load_measurement_evidence(path)

    assert set(evidence) == {"cold_start_time", "memory_usage"}
    assert evidence["cold_start_time"]["status"] == "pass"
    assert evidence["cold_start_time"]["value"] == 1.42
    assert evidence["memory_usage"]["status"] == "fail"
    assert evidence["memory_usage"]["evidence"].startswith("https://github.com/")


def test_measurement_evidence_template_covers_every_required_gate(tmp_path: Path) -> None:
    from tools.webengine_measurement_evidence import (
        REQUIRED_MEASUREMENT_GATES,
        build_measurement_evidence_template,
        load_measurement_evidence,
    )

    payload = build_measurement_evidence_template(generated_at="2026-06-12T00:00:00Z")
    path = tmp_path / "webengine-measurements-template.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert payload["generated_at"] == "2026-06-12T00:00:00Z"
    assert [row["key"] for row in payload["measurements"]] == list(REQUIRED_MEASUREMENT_GATES)
    assert {row["status"] for row in payload["measurements"]} == {"missing"}
    assert load_measurement_evidence(path).keys() == set(REQUIRED_MEASUREMENT_GATES)


def test_measurement_evidence_template_cli_writes_json(tmp_path: Path) -> None:
    from tools.webengine_measurement_evidence import REQUIRED_MEASUREMENT_GATES, main

    output = tmp_path / "webengine-measurements-template.json"

    assert main(["--template", "--out", str(output), "--generated-at", "2026-06-12T00:00:00Z"]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [row["key"] for row in payload["measurements"]] == list(REQUIRED_MEASUREMENT_GATES)
    assert all(row["status"] == "missing" for row in payload["measurements"])
