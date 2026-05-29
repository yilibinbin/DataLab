from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def test_auto_fit_is_not_in_fitting_model_combo(qtbot):
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

    assert "auto" not in values
    assert all("auto" not in label and "自动" not in label for label in labels)


def test_auto_fit_worker_is_not_exported():
    import app_desktop.workers_core as workers_core
    import app_desktop.workers_qt as workers_qt

    assert not hasattr(workers_core, "AutoFitJob")
    assert not hasattr(workers_core, "_execute_auto_fit_job_subprocess")
    assert not hasattr(workers_qt, "AutoFitWorker")


def test_fitting_package_no_longer_exports_auto_fit():
    import fitting

    assert not hasattr(fitting, "auto_fit_dataset")
