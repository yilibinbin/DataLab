from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_asset_evidence_tool_writes_template(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import REQUIRED_WEBENGINE_ASSETS
    from tools.webengine_asset_evidence import main

    output = tmp_path / "webengine-assets-template.json"

    assert main(["--repo-root", str(tmp_path), "--template", "--out", str(output), "--generated-at", "2026-06-12T00:00:00Z"]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [row["path"] for row in payload["assets"]] == [spec.path for spec in REQUIRED_WEBENGINE_ASSETS]
    assert {row["status"] for row in payload["assets"]} == {"missing"}


def test_asset_evidence_tool_writes_materialized_manifest(tmp_path: Path) -> None:
    from tools.webengine_asset_evidence import main

    payload = b"<!doctype html><html><body>DataLab</body></html>\n"
    expected_hash = hashlib.sha256(payload).hexdigest()
    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "index.html"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(payload)
    output = tmp_path / "webengine-assets.json"

    assert main(["--repo-root", str(tmp_path), "--out", str(output), "--generated-at", "2026-06-12T00:00:00Z"]) == 0

    manifest = json.loads(output.read_text(encoding="utf-8"))
    rows = {row["path"]: row for row in manifest["assets"]}
    assert rows["index.html"]["status"] == "provided"
    assert rows["index.html"]["sha256"] == expected_hash
    assert rows["index.html"]["bytes"] == len(payload)
