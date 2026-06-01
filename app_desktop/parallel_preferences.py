from __future__ import annotations

from typing import Any

from shared.parallel_config import NestedParallelPolicy, ParallelConfig, ParallelMode
from shared.settings_store import SettingsStore

KEY_PARALLEL_MODE = "Preferences/Parallel/Mode"
KEY_PARALLEL_MAX_WORKERS = "Preferences/Parallel/MaxWorkers"
KEY_PARALLEL_RESERVE_CORES = "Preferences/Parallel/ReserveCores"
KEY_PARALLEL_NESTED_POLICY = "Preferences/Parallel/NestedPolicy"
_STALE_PARALLEL_ENABLE_IMPLICIT_BACKEND = "Preferences/Parallel/EnableNewImplicitBackend"
_STALE_PARALLEL_ENABLE_AUTO_FIT_BACKEND = "Preferences/Parallel/EnableNewAutoFitBackend"


def parallel_preferences_keys() -> tuple[str, ...]:
    return (
        KEY_PARALLEL_MODE,
        KEY_PARALLEL_MAX_WORKERS,
        KEY_PARALLEL_RESERVE_CORES,
        KEY_PARALLEL_NESTED_POLICY,
    )


class ParallelPreferencesStore:
    def __init__(self, settings: SettingsStore | None = None) -> None:
        self.settings = settings or SettingsStore()

    def load(self) -> ParallelConfig:
        default = ParallelConfig()
        mode = _load_parallel_mode(
            self.settings.load_string(KEY_PARALLEL_MODE, default.mode.value),
            default.mode,
        )
        raw_workers = self.settings.load_int(
            KEY_PARALLEL_MAX_WORKERS,
            default=0 if default.max_workers is None else default.max_workers,
            min_val=0,
            max_val=1024,
        )
        nested_policy = _load_nested_policy(
            self.settings.load_string(
                KEY_PARALLEL_NESTED_POLICY,
                default.nested_policy.value,
            ),
            default.nested_policy,
        )
        config = ParallelConfig(
            mode=mode,
            max_workers=None if raw_workers <= 0 else raw_workers,
            reserve_cores=self.settings.load_int(
                KEY_PARALLEL_RESERVE_CORES,
                default=default.reserve_cores,
                min_val=0,
                max_val=1024,
            ),
            default_worker_cap=default.default_worker_cap,
            min_process_tasks=default.min_process_tasks,
            nested_policy=nested_policy,
            process_start_method=default.process_start_method,
        )
        self.settings.remove(_STALE_PARALLEL_ENABLE_IMPLICIT_BACKEND)
        self.settings.remove(_STALE_PARALLEL_ENABLE_AUTO_FIT_BACKEND)
        return config

    def save(self, config: ParallelConfig) -> None:
        self.settings.save_string(KEY_PARALLEL_MODE, config.mode.value)
        self.settings.save_int(
            KEY_PARALLEL_MAX_WORKERS,
            0 if config.max_workers is None else int(config.max_workers),
        )
        self.settings.save_int(KEY_PARALLEL_RESERVE_CORES, config.reserve_cores)
        self.settings.save_string(
            KEY_PARALLEL_NESTED_POLICY,
            config.nested_policy.value,
        )
        self.settings.remove(_STALE_PARALLEL_ENABLE_IMPLICIT_BACKEND)
        self.settings.remove(_STALE_PARALLEL_ENABLE_AUTO_FIT_BACKEND)


def current_parallel_config_from_widgets(owner: object) -> ParallelConfig:
    if not hasattr(owner, "parallel_mode_combo"):
        return ParallelConfig()

    mode = _load_parallel_mode(
        _combo_data(getattr(owner, "parallel_mode_combo")),
        ParallelConfig().mode,
    )
    nested_policy = _load_nested_policy(
        _combo_data(getattr(owner, "parallel_nested_policy_combo", None)),
        ParallelConfig().nested_policy,
    )
    max_workers_value = _spin_value(getattr(owner, "parallel_max_workers_spin", None), 0)
    return ParallelConfig(
        mode=mode,
        max_workers=None if max_workers_value <= 0 else max_workers_value,
        reserve_cores=max(
            0,
            _spin_value(
                getattr(owner, "parallel_reserve_cores_spin", None),
                ParallelConfig().reserve_cores,
            ),
        ),
        nested_policy=nested_policy,
    )


def apply_parallel_config_to_widgets(owner: object, config: ParallelConfig) -> None:
    _set_combo_data(getattr(owner, "parallel_mode_combo", None), config.mode.value)
    _set_spin_value(
        getattr(owner, "parallel_max_workers_spin", None),
        0 if config.max_workers is None else config.max_workers,
    )
    _set_spin_value(getattr(owner, "parallel_reserve_cores_spin", None), config.reserve_cores)
    _set_combo_data(
        getattr(owner, "parallel_nested_policy_combo", None),
        config.nested_policy.value,
    )


def save_current_parallel_config(owner: object) -> None:
    settings = getattr(owner, "_settings_store", None)
    if settings is None:
        settings = SettingsStore()
        setattr(owner, "_settings_store", settings)
    ParallelPreferencesStore(settings).save(current_parallel_config_from_widgets(owner))


def _load_parallel_mode(value: object, default: ParallelMode) -> ParallelMode:
    try:
        return ParallelMode(str(value))
    except ValueError:
        return default


def _load_nested_policy(
    value: object,
    default: NestedParallelPolicy,
) -> NestedParallelPolicy:
    try:
        return NestedParallelPolicy(str(value))
    except ValueError:
        return default


def _combo_data(combo: Any) -> object:
    if combo is None:
        return ""
    data = combo.currentData()
    return data if data is not None else ""


def _spin_value(spin: Any, default: int) -> int:
    if spin is None:
        return default
    try:
        return int(spin.value())
    except Exception:  # noqa: BLE001
        return default


def _set_combo_data(combo: Any, data: object) -> None:
    if combo is None:
        return
    index = combo.findData(data)
    if index >= 0:
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)


def _set_spin_value(spin: Any, value: int) -> None:
    if spin is None:
        return
    spin.blockSignals(True)
    spin.setValue(int(value))
    spin.blockSignals(False)
