from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[1]


def _fake_response(payload: dict[str, object]) -> MagicMock:
    response = MagicMock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_repository_metadata_points_at_public_datalab_repo() -> None:
    from shared import update_checker

    assert update_checker.REPOSITORY_URL == "https://github.com/yilibinbin/DataLab"
    assert update_checker.RELEASES_URL == "https://github.com/yilibinbin/DataLab/releases"
    assert (
        update_checker.LATEST_RELEASE_API_URL
        == "https://api.github.com/repos/yilibinbin/DataLab/releases/latest"
    )


def test_version_comparison_handles_v_tags_and_dev_versions() -> None:
    from shared.update_checker import is_newer_version

    assert is_newer_version("v2.1.0", "2.0.0")
    assert is_newer_version("v2.0.0", "2.0.0.dev0")
    assert not is_newer_version("v2.0.0", "2.0.0")
    assert not is_newer_version("v1.9.9", "2.0.0")


def test_fetch_latest_release_parses_github_payload(monkeypatch) -> None:
    from shared import update_checker

    seen: dict[str, object] = {}

    def fake_urlopen(request, *, timeout):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["user_agent"] = request.headers.get("User-agent")
        return _fake_response(
            {
                "tag_name": "v2.1.0",
                "name": "DataLab v2.1.0",
                "html_url": "https://github.com/yilibinbin/DataLab/releases/tag/v2.1.0",
                "body": "Release notes",
                "published_at": "2026-05-02T00:00:00Z",
                "assets": [
                    {
                        "name": "DataLab-macOS.dmg",
                        "browser_download_url": "https://example.invalid/DataLab-macOS.dmg",
                    }
                ],
            }
        )

    monkeypatch.setattr(update_checker, "_urlopen", fake_urlopen)

    release = update_checker.fetch_latest_release(timeout=7)

    assert seen == {
        "url": update_checker.LATEST_RELEASE_API_URL,
        "timeout": 7,
        "user_agent": "DataLab Update Checker",
    }
    assert release.tag_name == "v2.1.0"
    assert release.version == "2.1.0"
    assert release.html_url.endswith("/v2.1.0")
    assert release.assets[0].name == "DataLab-macOS.dmg"


def test_fetch_latest_release_parses_asset_size(monkeypatch) -> None:
    from shared import update_checker

    def fake_urlopen(request, *, timeout):
        return _fake_response(
            {
                "tag_name": "v2.3.0",
                "name": "DataLab v2.3.0",
                "html_url": "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
                "body": "Release notes",
                "published_at": "2026-05-26T00:00:00Z",
                "assets": [
                    {
                        "name": "updates.json",
                        "browser_download_url": "https://example.invalid/updates.json",
                        "size": 1024,
                    }
                ],
            }
        )

    monkeypatch.setattr(update_checker, "_urlopen", fake_urlopen)

    release = update_checker.fetch_latest_release(timeout=3)

    assert release.assets[0].name == "updates.json"
    assert release.assets[0].size == 1024


def test_format_release_notes_for_dialog_plain_text_and_truncates() -> None:
    from shared.update_checker import format_release_notes_for_dialog

    body = "# Changes\n<script>alert(1)</script>\nFixed <b>updates</b>\n" + ("x" * 5000)

    formatted = format_release_notes_for_dialog(body, max_chars=80)

    assert "<script>" not in formatted
    assert "<b>" not in formatted
    assert "Fixed updates" in formatted
    assert len(formatted) <= 80
    assert formatted.endswith("...")


def test_check_for_updates_reports_available_release(monkeypatch) -> None:
    from shared import update_checker

    release = update_checker.ReleaseInfo(
        tag_name="v2.1.0",
        name="DataLab v2.1.0",
        version="2.1.0",
        html_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.1.0",
        body="",
        published_at="2026-05-02T00:00:00Z",
        assets=(),
    )
    monkeypatch.setattr(update_checker, "fetch_latest_release", lambda **_: release)

    result = update_checker.check_for_updates(current_version="2.0.0")

    assert result.status == "update-available"
    assert result.update_available is True
    assert result.release == release
    assert result.latest_version == "2.1.0"


def test_check_for_updates_reports_up_to_date(monkeypatch) -> None:
    from shared import update_checker

    release = update_checker.ReleaseInfo(
        tag_name="v2.0.0",
        name="DataLab v2.0.0",
        version="2.0.0",
        html_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.0.0",
        body="",
        published_at="2026-04-26T00:00:00Z",
        assets=(),
    )
    monkeypatch.setattr(update_checker, "fetch_latest_release", lambda **_: release)

    result = update_checker.check_for_updates(current_version="2.0.0")

    assert result.status == "up-to-date"
    assert result.update_available is False
    assert result.release == release


def test_check_for_updates_converts_network_errors_to_unavailable(monkeypatch) -> None:
    from shared import update_checker

    def raise_offline(**_):
        raise OSError("offline")

    monkeypatch.setattr(update_checker, "fetch_latest_release", raise_offline)

    result = update_checker.check_for_updates(current_version="2.0.0")

    assert result.status == "unavailable"
    assert result.update_available is False
    assert "offline" in (result.error or "")


def test_current_version_reads_pyproject_from_pyinstaller_meipass(tmp_path, monkeypatch) -> None:
    from shared import update_checker

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "datalab"\nversion = "9.8.7"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(update_checker.metadata, "version", lambda _name: "1.0.0")
    monkeypatch.setattr(update_checker.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert update_checker.current_version() == "9.8.7"


def test_current_version_prefers_source_pyproject_over_stale_editable_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    from shared import update_checker

    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    fake_module = shared_dir / "update_checker.py"
    fake_module.write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "datalab"\nversion = "9.9.1"\n',
        encoding="utf-8",
    )

    monkeypatch.delattr(update_checker.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(update_checker, "__file__", str(fake_module))
    monkeypatch.setattr(update_checker.metadata, "version", lambda _name: "2.0.0.dev0")

    assert update_checker.current_version() == "9.9.1"


def test_pyinstaller_builds_bundle_pyproject_for_frozen_version_fallback() -> None:
    spec_text = (ROOT / "DataLab.spec").read_text(encoding="utf-8")
    mac_text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")
    win_text = (ROOT / "build_windows_data_gui.ps1").read_text(encoding="utf-8")

    assert '(_rel("pyproject.toml"), ".")' in spec_text
    assert 'PYPROJECT_FILE="$PROJECT_ROOT/pyproject.toml"' in mac_text
    assert 'DOCS_DATA_FLAGS+=(--add-data "$PYPROJECT_FILE:.")' in mac_text
    assert '$pyprojectFile = Join-Path $projectRoot "pyproject.toml"' in win_text
    assert '$dataArgs += @("--add-data", ("{0};." -f $pyprojectAbs))' in win_text
