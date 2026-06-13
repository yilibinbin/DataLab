from __future__ import annotations

from pathlib import Path

from tools.qt_packaging_excludes import (
    REQUIRED_WEBENGINE_EXCLUDES,
    exclude_sync_status,
    packaging_qt_excludes,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_qt_exclude_lists_are_synchronized_across_packaging_entrypoints() -> None:
    """All frozen-app entry points must agree on excluded Qt modules.

    WebEngine/QtPdf decisions are packaging-critical. A future spike may change
    the list, but it must update the spec and both platform build scripts in
    lockstep.
    """
    status = exclude_sync_status(packaging_qt_excludes(REPO_ROOT))

    assert status["duplicates"] == {
        "DataLab.spec": [],
        "build_mac_data_gui.sh": [],
        "build_windows_data_gui.ps1": [],
    }
    assert status["synchronized"] is True, (
        "Qt excludes differ across packaging entrypoints; "
        f"missing={status['missing_from_reference']}, extra={status['extra_vs_reference']}"
    )


def test_qt_webengine_exclusions_are_explicit_until_spike_passes() -> None:
    status = exclude_sync_status(packaging_qt_excludes(REPO_ROOT))
    spec_excludes = set(packaging_qt_excludes(REPO_ROOT)["DataLab.spec"])

    assert set(REQUIRED_WEBENGINE_EXCLUDES).issubset(spec_excludes)
    assert status["webengine_excluded"] is True
