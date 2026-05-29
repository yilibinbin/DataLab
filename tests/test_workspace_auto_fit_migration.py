from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_opening_old_auto_fit_workspace_ignores_auto_state_once(qtbot):
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import restore_workspace

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    manifest = {
        "schema_version": "1.0",
        "config": {
            "fitting": {
                "model": "auto",
                "auto_fit": {"enabled": True, "candidate_models": ["poly2"]},
                "custom": {"expression": "a*x+b"},
            }
        },
        "data": {"input": {"canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]}}},
    }

    restore_workspace(win, manifest, {})

    assert win.fit_model_combo.currentData() != "auto"
    assert getattr(win, "_workspace_degraded", False) is True
    assert "automatic" in " ".join(getattr(win, "_workspace_migration_warnings", [])).lower()


def test_saving_after_old_auto_fit_migration_strips_obsolete_fields(qtbot):
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    manifest = {
        "schema_version": "1.0",
        "config": {
            "fitting": {
                "model": "auto",
                "auto_fit": {"enabled": True},
            }
        },
        "data": {"input": {"canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]}}},
    }

    restore_workspace(win, manifest, {})
    saved = capture_workspace(win, title="migrated").manifest
    fitting = saved["config"]["fitting"]

    assert fitting.get("model") != "auto"
    assert "auto_fit" not in fitting
