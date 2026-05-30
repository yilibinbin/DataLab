from __future__ import annotations

import inspect
import os
from typing import Any

import mpmath as mp
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from shared.parallel_config import (  # noqa: E402
    NestedParallelPolicy,
    ParallelConfig,
    ParallelMode,
)


class _FakeQSettings:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def setValue(self, key: str, value: Any) -> None:  # noqa: N802
        self._data[key] = value

    def remove(self, key: str) -> None:
        self._data.pop(key, None)

    def sync(self) -> None:
        pass

    def status(self) -> Any:
        from PySide6.QtCore import QSettings

        return QSettings.Status.NoError


def test_parallel_preferences_round_trip_all_public_desktop_fields_and_drops_stale_implicit_flag() -> None:
    from app_desktop.parallel_preferences import (
        ParallelPreferencesStore,
        parallel_preferences_keys,
    )
    from shared.settings_store import SettingsStore

    fake_store = _FakeQSettings()
    settings = SettingsStore(store=fake_store)
    prefs = ParallelPreferencesStore(settings)
    config = ParallelConfig(
        mode=ParallelMode.PROCESS,
        max_workers=7,
        reserve_cores=2,
        nested_policy=NestedParallelPolicy.ALLOW,
        enable_new_auto_fit_backend=True,
        enable_new_implicit_backend=False,
    )
    settings.save_bool(
        "Preferences/Parallel/EnableNewImplicitBackend",
        False,
    )

    prefs.save(config)
    restored = prefs.load()

    assert restored.mode == ParallelMode.PROCESS
    assert restored.max_workers == 7
    assert restored.reserve_cores == 2
    assert restored.nested_policy == NestedParallelPolicy.ALLOW
    assert restored.enable_new_auto_fit_backend is True
    assert restored.enable_new_implicit_backend is True
    assert "Preferences/Parallel/EnableNewImplicitBackend" not in fake_store._data
    assert settings.load_bool(
        "Preferences/Parallel/EnableNewImplicitBackend",
        True,
    ) is True
    assert parallel_preferences_keys() == (
        "Preferences/Parallel/Mode",
        "Preferences/Parallel/MaxWorkers",
        "Preferences/Parallel/ReserveCores",
        "Preferences/Parallel/NestedPolicy",
        "Preferences/Parallel/EnableNewAutoFitBackend",
    )


def test_parallel_preferences_store_uses_zero_as_auto_workers() -> None:
    from app_desktop.parallel_preferences import ParallelPreferencesStore
    from shared.settings_store import SettingsStore

    settings = SettingsStore(store=_FakeQSettings())
    prefs = ParallelPreferencesStore(settings)

    assert prefs.load().reserve_cores == 1
    prefs.save(ParallelConfig(max_workers=None))

    assert prefs.load().max_workers is None


def test_shared_parallel_modules_do_not_import_settings_store() -> None:
    import shared.parallel_backend as parallel_backend
    import shared.parallel_config as parallel_config

    assert "settings_store" not in inspect.getsource(parallel_backend)
    assert "settings_store" not in inspect.getsource(parallel_config)


@pytest.fixture  # type: ignore[untyped-decorator]  # pytest fixture decorator is untyped under scoped mypy.
def window(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    from shared.settings_store import SettingsStore

    fake_settings = SettingsStore(store=_FakeQSettings())
    monkeypatch.setattr(
        "shared.settings_store.SettingsStore",
        lambda: fake_settings,
    )
    monkeypatch.setattr(
        "app_desktop.parallel_preferences.SettingsStore",
        lambda: fake_settings,
    )
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _dataset() -> tuple[
    list[str],
    list[tuple[mp.mpf, mp.mpf]],
    list[tuple[None, None]],
]:
    return (
        ["A", "B"],
        [(mp.mpf("1"), mp.mpf("2")), (mp.mpf("2"), mp.mpf("4"))],
        [(None, None), (None, None)],
    )


def test_desktop_parallel_controls_exist_and_save_current_config(window: Any) -> None:
    assert window.parallel_mode_combo.findData(ParallelMode.PROCESS.value) >= 0
    assert window.parallel_max_workers_spin.minimum() == 0
    assert window.parallel_nested_policy_combo.findData(NestedParallelPolicy.ALLOW.value) >= 0
    assert not hasattr(window, "parallel_auto_fit_backend_checkbox")
    assert not hasattr(window, "parallel_implicit_backend_checkbox")

    window.parallel_mode_combo.setCurrentIndex(
        window.parallel_mode_combo.findData(ParallelMode.THREAD.value)
    )
    window.parallel_max_workers_spin.setValue(3)
    window.parallel_reserve_cores_spin.setValue(2)
    window.parallel_nested_policy_combo.setCurrentIndex(
        window.parallel_nested_policy_combo.findData(NestedParallelPolicy.ALLOW.value)
    )
    config = window._current_parallel_config()

    assert config.mode == ParallelMode.THREAD
    assert config.max_workers == 3
    assert config.reserve_cores == 2
    assert config.nested_policy == NestedParallelPolicy.ALLOW
    assert config.enable_new_auto_fit_backend is ParallelConfig().enable_new_auto_fit_backend
    assert config.enable_new_implicit_backend is True


def test_prepare_jobs_receive_current_parallel_config(window: Any) -> None:
    window.parallel_mode_combo.setCurrentIndex(
        window.parallel_mode_combo.findData(ParallelMode.SERIAL.value)
    )
    window.parallel_max_workers_spin.setValue(5)
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("polynomial"))

    fit_job = window._prepare_fit_job(
        _dataset(),
        generate_latex=False,
        output_path="",
        verbose=False,
        render_plots=False,
    )

    assert fit_job.parallel_config.mode == ParallelMode.SERIAL
    assert fit_job.parallel_config.max_workers == 5
    assert fit_job.parallel_config.enable_new_auto_fit_backend is ParallelConfig().enable_new_auto_fit_backend
    assert fit_job.parallel_config.enable_new_implicit_backend is True


def test_text_to_table_preserves_parenthesized_uncertainty_tokens(window: Any) -> None:
    from app_desktop.panels import _load_text_into_table, _serialize_table

    _load_text_into_table(
        window,
        "A B\n4 -0.01161947382(2)\n5 -0.01182004861(4)",
    )

    serialized = _serialize_table(window)

    assert "-0.01161947382(2)" in serialized
    assert "-0.01182004861(4)" in serialized


def test_fitting_dataset_preserves_uncertainty_objects_from_parenthesized_tokens(window: Any) -> None:
    from app_desktop.panels import _load_text_into_table

    _load_text_into_table(
        window,
        "A B\n4 -0.01161947382(2)\n5 -0.01182004861(4)",
    )

    headers, rows, sigma_rows = window._collect_fitting_dataset()

    assert headers == ["A", "B"]
    assert rows[0][0] == mp.mpf("4")
    assert hasattr(sigma_rows[0][1], "uncertainty")
    assert mp.mpf(sigma_rows[0][1].uncertainty) > 0


def test_left_panel_minimum_width_is_not_formula_size_hint(window: Any) -> None:
    left_scroll = window._main_splitter.widget(0)

    assert left_scroll.minimumWidth() <= 360
    assert window.left_container.sizeHint().width() >= left_scroll.minimumWidth()


def test_current_parallel_config_defaults_when_controls_are_absent() -> None:
    from app_desktop.parallel_preferences import current_parallel_config_from_widgets

    assert current_parallel_config_from_widgets(object()) == ParallelConfig()


def test_global_parallel_backend_shutdown_is_idempotent() -> None:
    from shared.parallel_backend import (
        register_global_shutdown_callback,
        shutdown_global_backend,
    )

    calls: list[str] = []
    register_global_shutdown_callback(lambda: calls.append("shutdown"))

    shutdown_global_backend()
    shutdown_global_backend()

    assert calls == ["shutdown"]


def test_global_parallel_backend_shutdown_kills_active_killable_child() -> None:
    from shared.parallel_backend import (
        KillableProcessTaskRunner,
        LocalWorkerBudget,
        shutdown_global_backend,
    )

    budget = LocalWorkerBudget(total=1)
    runner = KillableProcessTaskRunner(worker_budget=budget)
    handle = runner.start_killable(_long_sleep, 10.0)

    shutdown_global_backend()
    shutdown_global_backend()

    assert not handle._process.is_alive()
    assert budget.available == 1


def _long_sleep(seconds: float) -> str:
    import time

    time.sleep(seconds)
    return "finished"
