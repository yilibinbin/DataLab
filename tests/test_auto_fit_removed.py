from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_fitting_model_combo_contains_only_supported_explicit_models(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    values = [
        win.fit_model_combo.itemData(index)
        for index in range(win.fit_model_combo.count())
    ]
    labels = [
        win.fit_model_combo.itemText(index).lower()
        for index in range(win.fit_model_combo.count())
    ]

    assert values == [
        "custom",
        "self_consistent",
        "poly",
        "inverse",
        "pade",
        "power_limit",
    ]
    assert "auto" not in values
    assert "log_poly" not in values
    assert "exp_combo" not in values
    assert all("auto" not in label and "自动" not in label for label in labels)


def test_no_user_visible_auto_fit_backend_control(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    assert not hasattr(win, "parallel_auto_fit_backend_checkbox")

    banned = ("auto-fit", "auto fit", "自动拟合", "auto-fit backend")
    visible_text: list[str] = []
    for widget in win.findChildren(object):
        if hasattr(widget, "text"):
            try:
                text = str(widget.text())
            except RuntimeError:
                continue
            if text:
                visible_text.append(text.lower())
        if hasattr(widget, "toolTip"):
            try:
                tooltip = str(widget.toolTip())
            except RuntimeError:
                continue
            if tooltip:
                visible_text.append(tooltip.lower())

    joined = "\n".join(visible_text)
    assert all(term not in joined for term in banned)


def test_window_has_no_auto_fit_lifecycle_methods():
    from app_desktop.window import ExtrapolationWindow

    stale_methods = [
        "_on_auto_fit_finished",
        "_on_auto_fit_failed",
        "_on_auto_fit_thread_done",
        "_on_auto_fit_progress",
        "_start_auto_fit",
        "_run_auto_fit",
        "_execute_auto_fit",
        "_execute_auto_fit_async",
        "_prepare_auto_fit_job",
        "_render_auto_fit_summary",
    ]

    for name in stale_methods:
        assert not hasattr(ExtrapolationWindow, name)


def test_auto_fit_worker_is_not_exported():
    import app_desktop.workers_core as workers_core
    import app_desktop.workers_qt as workers_qt

    assert not hasattr(workers_core, "AutoFitJob")
    assert not hasattr(workers_core, "_execute_auto_fit_job_subprocess")
    assert not hasattr(workers_qt, "AutoFitWorker")


def test_fitting_package_no_longer_exports_auto_fit():
    import fitting

    assert not hasattr(fitting, "auto_fit_dataset")
