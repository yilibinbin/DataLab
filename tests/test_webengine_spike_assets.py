from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_webengine_spike_assets_import_is_qt_free() -> None:
    probe = """
from __future__ import annotations

import json
import sys

import app_desktop.webengine_spike_assets

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


def test_asset_manifest_rejects_remote_and_unsafe_paths() -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetError,
        WebEngineAssetSpec,
        validate_asset_manifest,
    )

    unsafe_paths = [
        "",
        "https://cdn.example.invalid/katex.min.js",
        "http://127.0.0.1:5000/app.js",
        "//cdn.example.invalid/katex.min.css",
        "file:///Users/fanghao/private.js",
        "data:text/javascript,alert(1)",
        "/absolute/app.js",
        "../secret.js",
        "vendor/../secret.js",
        "vendor\\katex\\katex.min.js",
        "C:/Windows/System32/calc.exe",
        "style.css?v=1",
        "style.css#fragment",
    ]
    for asset_path in unsafe_paths:
        with pytest.raises(WebEngineAssetError):
            validate_asset_manifest([WebEngineAssetSpec(asset_path)])

    with pytest.raises(WebEngineAssetError):
        validate_asset_manifest(
            [
                WebEngineAssetSpec("app/workbench.js"),
                WebEngineAssetSpec("app/workbench.js"),
            ]
        )

    assets = validate_asset_manifest(
        [WebEngineAssetSpec("vendor/katex/katex.min.js")]
    )
    assert assets[0].path == "vendor/katex/katex.min.js"


def test_offline_asset_preflight_marks_default_assets_missing(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        REQUIRED_WEBENGINE_ASSETS,
        inspect_offline_assets,
    )

    report = inspect_offline_assets(tmp_path)

    assert report["asset_root"] == "app_desktop/webengine_assets"
    assert report["runtime_network_allowed"] is False
    assert report["passed"] is False
    assert report["required_count"] == len(REQUIRED_WEBENGINE_ASSETS)
    assert report["provided_count"] == 0
    assert {row["status"] for row in report["assets"]} == {"missing"}


def test_asset_preflight_requires_integrity_for_existing_files(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetSpec,
        inspect_offline_assets,
    )

    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "app" / "workbench.js"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text("console.log('offline');\n", encoding="utf-8")

    report = inspect_offline_assets(
        tmp_path,
        specs=[WebEngineAssetSpec("app/workbench.js")],
    )

    assert report["passed"] is False
    assert report["invalid_count"] == 1
    assert report["assets"][0]["status"] == "missing_integrity"
    assert report["assets"][0]["bytes"] == asset_path.stat().st_size


def test_asset_preflight_accepts_integrity_checked_local_assets(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetSpec,
        inspect_offline_assets,
    )

    payload = b"<!doctype html><html><body>DataLab</body></html>\n"
    expected_hash = hashlib.sha256(payload).hexdigest()
    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "index.html"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(payload)

    report = inspect_offline_assets(
        tmp_path,
        specs=[
            WebEngineAssetSpec(
                "index.html",
                sha256=expected_hash,
                bytes=len(payload),
                kind="entrypoint",
            )
        ],
    )

    assert report["passed"] is True
    assert report["provided_count"] == 1
    assert report["invalid_count"] == 0
    assert report["assets"][0]["status"] == "provided"
    assert report["assets"][0]["sha256"] == expected_hash


def test_asset_evidence_template_covers_required_assets_without_fake_integrity() -> None:
    from app_desktop.webengine_spike_assets import (
        REQUIRED_WEBENGINE_ASSETS,
        WebEngineAssetSpec,
        build_asset_evidence_template,
        validate_asset_manifest,
    )

    payload = build_asset_evidence_template(generated_at="2026-06-12T00:00:00Z")

    assert payload["generated_at"] == "2026-06-12T00:00:00Z"
    assert payload["asset_root"] == "app_desktop/webengine_assets"
    assert [row["path"] for row in payload["assets"]] == [spec.path for spec in REQUIRED_WEBENGINE_ASSETS]
    assert {row["status"] for row in payload["assets"]} == {"missing"}
    assert all("sha256" not in row and "bytes" not in row for row in payload["assets"])
    specs = validate_asset_manifest(
        [
            WebEngineAssetSpec(
                row["path"],
                kind=row["kind"],
            )
            for row in payload["assets"]
        ]
    )
    assert [spec.path for spec in specs] == [spec.path for spec in REQUIRED_WEBENGINE_ASSETS]


def test_materialized_asset_manifest_records_integrity_for_existing_assets(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        build_materialized_asset_manifest,
    )

    payload = b"console.log('offline');\n"
    expected_hash = hashlib.sha256(payload).hexdigest()
    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "app" / "workbench.js"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(payload)

    manifest = build_materialized_asset_manifest(
        tmp_path,
        generated_at="2026-06-12T00:00:00Z",
    )
    rows = {row["path"]: row for row in manifest["assets"]}

    assert rows["app/workbench.js"]["status"] == "provided"
    assert rows["app/workbench.js"]["sha256"] == expected_hash
    assert rows["app/workbench.js"]["bytes"] == len(payload)
    assert rows["index.html"]["status"] == "missing"
    assert "sha256" not in rows["index.html"]


def test_load_asset_evidence_manifest_round_trips_template(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        REQUIRED_WEBENGINE_ASSETS,
        build_asset_evidence_template,
        load_asset_evidence,
    )

    path = tmp_path / "webengine-assets-template.json"
    path.write_text(
        json.dumps(build_asset_evidence_template(generated_at="2026-06-12T00:00:00Z")),
        encoding="utf-8",
    )

    evidence = load_asset_evidence(path)

    assert evidence.asset_root == "app_desktop/webengine_assets"
    assert [spec.path for spec in evidence.specs] == [spec.path for spec in REQUIRED_WEBENGINE_ASSETS]
    assert [spec.kind for spec in evidence.specs] == [spec.kind for spec in REQUIRED_WEBENGINE_ASSETS]
    assert all(spec.sha256 is None and spec.bytes is None for spec in evidence.specs)


def test_load_asset_evidence_manifest_preserves_materialized_integrity(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        build_materialized_asset_manifest,
        inspect_offline_assets,
        load_asset_evidence,
    )

    payload = b"<!doctype html><html><body>DataLab</body></html>\n"
    expected_hash = hashlib.sha256(payload).hexdigest()
    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "index.html"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(payload)
    manifest_path = tmp_path / "webengine-assets.json"
    manifest_path.write_text(json.dumps(build_materialized_asset_manifest(tmp_path)), encoding="utf-8")

    evidence = load_asset_evidence(manifest_path)
    report = inspect_offline_assets(tmp_path, specs=evidence.specs, asset_root=evidence.asset_root)
    rows = {row["path"]: row for row in report["assets"]}

    assert rows["index.html"]["status"] == "provided"
    assert rows["index.html"]["sha256"] == expected_hash
    assert report["provided_count"] == 1
    assert report["passed"] is False


def test_load_asset_evidence_manifest_rejects_drift_and_fake_integrity(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetError,
        build_asset_evidence_template,
        load_asset_evidence,
    )

    payload = build_asset_evidence_template()
    payload["assets"] = payload["assets"][:-1]
    missing_path = tmp_path / "missing-row.json"
    missing_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WebEngineAssetError, match="must cover every required"):
        load_asset_evidence(missing_path)

    payload = build_asset_evidence_template()
    payload["assets"][0]["sha256"] = "0" * 64
    fake_path = tmp_path / "fake-integrity.json"
    fake_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WebEngineAssetError, match="must not include integrity"):
        load_asset_evidence(fake_path)

    payload = build_asset_evidence_template()
    payload["assets"][0]["path"] = "app/unlisted.js"
    unknown_path = tmp_path / "unknown-row.json"
    unknown_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WebEngineAssetError, match="unknown asset"):
        load_asset_evidence(unknown_path)


def test_asset_preflight_rejects_integrity_mismatches(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetSpec,
        inspect_offline_assets,
    )

    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "app" / "workbench.css"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(".app { color: black; }\n", encoding="utf-8")

    report = inspect_offline_assets(
        tmp_path,
        specs=[
            WebEngineAssetSpec(
                "app/workbench.css",
                sha256="0" * 64,
                bytes=1,
            )
        ],
    )

    assert report["passed"] is False
    assert report["invalid_count"] == 1
    assert report["assets"][0]["status"] == "integrity_mismatch"
    assert sorted(report["assets"][0]["mismatches"]) == ["bytes", "sha256"]


def test_resolve_asset_url_accepts_only_integrity_checked_manifest_assets(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetSpec,
        resolve_asset_url,
    )

    payload = b"<!doctype html><html><body>DataLab</body></html>\n"
    expected_hash = hashlib.sha256(payload).hexdigest()
    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "index.html"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(payload)

    resolved = resolve_asset_url(
        tmp_path,
        "datalab-workbench://app/",
        specs=[
            WebEngineAssetSpec(
                "index.html",
                sha256=expected_hash,
                bytes=len(payload),
                kind="entrypoint",
            )
        ],
    )

    assert resolved["relative_path"] == "index.html"
    assert resolved["filesystem_path"] == str(asset_path.resolve())
    assert resolved["content_type"] == "text/html; charset=utf-8"
    assert resolved["sha256"] == expected_hash
    assert resolved["bytes"] == len(payload)


def test_resolve_asset_url_rejects_unlisted_and_unverified_assets(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetError,
        WebEngineAssetSpec,
        resolve_asset_url,
    )

    asset_dir = tmp_path / "app_desktop" / "webengine_assets" / "app"
    asset_dir.mkdir(parents=True)
    (asset_dir / "workbench.js").write_text("console.log('ok');\n", encoding="utf-8")
    (asset_dir / "unlisted.js").write_text("console.log('no');\n", encoding="utf-8")

    with pytest.raises(WebEngineAssetError):
        resolve_asset_url(
            tmp_path,
            "datalab-workbench://app/app/unlisted.js",
            specs=[WebEngineAssetSpec("app/workbench.js")],
        )

    with pytest.raises(WebEngineAssetError):
        resolve_asset_url(
            tmp_path,
            "datalab-workbench://app/app/workbench.js",
            specs=[WebEngineAssetSpec("app/workbench.js")],
        )

    with pytest.raises(WebEngineAssetError):
        resolve_asset_url(
            tmp_path,
            "https://example.invalid/app/workbench.js",
            specs=[WebEngineAssetSpec("app/workbench.js")],
        )


def test_resolve_asset_url_rejects_missing_and_integrity_mismatched_assets(tmp_path: Path) -> None:
    from app_desktop.webengine_spike_assets import (
        WebEngineAssetError,
        WebEngineAssetSpec,
        resolve_asset_url,
    )

    with pytest.raises(WebEngineAssetError):
        resolve_asset_url(
            tmp_path,
            "datalab-workbench://app/app/workbench.css",
            specs=[
                WebEngineAssetSpec(
                    "app/workbench.css",
                    sha256="0" * 64,
                    bytes=100,
                )
            ],
        )

    asset_path = tmp_path / "app_desktop" / "webengine_assets" / "app" / "workbench.css"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(".app { color: black; }\n", encoding="utf-8")

    with pytest.raises(WebEngineAssetError):
        resolve_asset_url(
            tmp_path,
            "datalab-workbench://app/app/workbench.css",
            specs=[
                WebEngineAssetSpec(
                    "app/workbench.css",
                    sha256="0" * 64,
                    bytes=1,
                )
            ],
        )
