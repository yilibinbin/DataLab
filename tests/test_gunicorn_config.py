"""P1-2 (deployment root-fix): the bundled gunicorn.conf.py must size workers so
one user's long mpmath fit can never block every other user.

The load-bearing invariant is the **floor of 2 workers**: mpmath's mp.dps is
process-global and each worker serializes its fits, so a single-worker
deployment reintroduces the "one fit freezes the site" problem. These tests pin
that floor, the WEB_CONCURRENCY override, and the ceiling.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CONF = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"


def _load_conf():
    spec = importlib.util.spec_from_file_location("datalab_gunicorn_conf", _CONF)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_count_never_drops_below_two(monkeypatch):
    # Even on a single-core box the floor must hold, so a long fit cannot block
    # all users.
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.setattr("multiprocessing.cpu_count", lambda: 1)
    conf = _load_conf()
    assert conf._resolve_workers() >= 2


def test_worker_count_follows_cpu_when_reasonable(monkeypatch):
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.setattr("multiprocessing.cpu_count", lambda: 4)
    conf = _load_conf()
    # 2*4+1 = 9, under the ceiling.
    assert conf._resolve_workers() == 9


def test_worker_count_is_ceilinged(monkeypatch):
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.setattr("multiprocessing.cpu_count", lambda: 128)
    conf = _load_conf()
    assert conf._resolve_workers() == conf._MAX_WORKERS


def test_web_concurrency_env_overrides(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "5")
    conf = _load_conf()
    assert conf._resolve_workers() == 5


def test_invalid_web_concurrency_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "not-a-number")
    monkeypatch.setattr("multiprocessing.cpu_count", lambda: 2)
    conf = _load_conf()
    assert conf._resolve_workers() == 5  # 2*2+1


def test_sync_worker_class(monkeypatch):
    # mpmath fits are CPU-bound and hold the worker; async workers add nothing.
    conf = _load_conf()
    assert conf.worker_class == "sync"


@pytest.mark.parametrize("attr", ["bind", "workers", "worker_class", "timeout"])
def test_required_gunicorn_settings_present(attr):
    conf = _load_conf()
    assert hasattr(conf, attr)
