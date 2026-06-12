from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def test_webengine_spike_contract_import_is_qt_free() -> None:
    probe = """
from __future__ import annotations

import json
import sys

import app_desktop.webengine_spike_contract

loaded = sorted(name for name in sys.modules if name == "PySide6" or name.startswith("PySide6."))
print(json.dumps(loaded))
"""
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(
        [sys.executable, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_navigation_url_contract_allows_only_custom_local_scheme() -> None:
    from app_desktop.webengine_spike_contract import (
        WEBENGINE_SPIKE_HOST,
        WEBENGINE_SPIKE_SCHEME,
        WebEngineSecurityError,
        validate_navigation_url,
    )

    assert validate_navigation_url(f"{WEBENGINE_SPIKE_SCHEME}://{WEBENGINE_SPIKE_HOST}/index.html") == "/index.html"

    for url in [
        "https://example.com/app.js",
        "http://127.0.0.1:5000/",
        "file:///Users/fanghao/private.txt",
        "data:text/html,<script>alert(1)</script>",
        f"{WEBENGINE_SPIKE_SCHEME}://evil/index.html",
        f"{WEBENGINE_SPIKE_SCHEME}://{WEBENGINE_SPIKE_HOST}/../secrets",
        f"{WEBENGINE_SPIKE_SCHEME}://{WEBENGINE_SPIKE_HOST}//double-slash",
    ]:
        with pytest.raises(WebEngineSecurityError):
            validate_navigation_url(url)


def test_content_security_policy_is_restrictive_and_offline() -> None:
    from app_desktop.webengine_spike_contract import build_content_security_policy

    csp = build_content_security_policy()

    assert "default-src 'none'" in csp
    assert "connect-src 'none'" in csp
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "http:" not in csp
    assert "https:" not in csp
    assert "file:" not in csp


def test_bridge_allowlist_contains_only_expected_non_shell_actions() -> None:
    from app_desktop.webengine_spike_contract import ALLOWED_BRIDGE_METHODS

    assert set(ALLOWED_BRIDGE_METHODS) == {
        "workspace.openDialog",
        "workspace.save",
        "workspace.saveAsDialog",
        "job.submit",
        "job.cancel",
        "job.status",
        "examples.list",
        "docs.open",
        "updates.check",
        "export.result",
    }
    forbidden_fragments = ("shell", "exec", "command", "subprocess", "file.read", "file.write")
    assert not any(fragment in method.lower() for method in ALLOWED_BRIDGE_METHODS for fragment in forbidden_fragments)


def test_bridge_payload_validation_accepts_bounded_json_objects() -> None:
    from app_desktop.webengine_spike_contract import validate_bridge_call

    payload = validate_bridge_call(
        "job.submit",
        {
            "requestId": "job-1",
            "mode": "statistics",
            "inputs": {"values": ["1", "2", "3"]},
            "options": {"precisionDigits": 30},
        },
    )

    assert payload["requestId"] == "job-1"
    assert payload["inputs"]["values"] == ["1", "2", "3"]


def test_bridge_payload_validation_rejects_unsafe_payloads() -> None:
    from app_desktop.webengine_spike_contract import WebEngineSecurityError, validate_bridge_call

    invalid_cases = [
        ("unknown.method", {}),
        ("workspace.openDialog", []),
        ("workspace.openDialog", {"path": "/Users/fanghao/private.datalab"}),
        ("job.cancel", {"requestId": "job-1", "command": "rm -rf /"}),
        ("docs.open", {"topic": "../secrets"}),
        ("export.result", {"format": "pdf", "destinationPath": "/tmp/out.pdf"}),
        ("job.status", {"requestId": "x" * 70000}),
        ("job.status", {"requestId": object()}),
    ]

    for method, payload in invalid_cases:
        with pytest.raises(WebEngineSecurityError):
            validate_bridge_call(method, payload)


def test_bridge_payload_validation_rejects_too_deep_objects() -> None:
    from app_desktop.webengine_spike_contract import WebEngineSecurityError, validate_bridge_call

    nested = {"requestId": "job-1"}
    cursor = nested
    for index in range(12):
        cursor["child"] = {"index": index}
        cursor = cursor["child"]

    with pytest.raises(WebEngineSecurityError):
        validate_bridge_call("job.status", nested)
