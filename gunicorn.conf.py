"""Gunicorn configuration for the DataLab web app (production).

Run with:  gunicorn -c gunicorn.conf.py 'app_web.server:create_app()'

Why this file exists — the concurrency root-fix (P1-2)
------------------------------------------------------
DataLab's numerical core uses mpmath, whose precision (``mp.dps``) is
*process-global*. Each request runs under a per-worker lock so concurrent
requests in one worker can't corrupt each other's precision — which means a
single worker processes at most one fit at a time. The correct way to serve
multiple users during a long fit is therefore **multiple worker processes**
(each an independent OS process with its own ``mp.dps``), not threads.

This config makes that the default instead of relying on the operator to pass
``-w N``: workers are derived from the CPU count and, critically, **floored at
2** so one user's long high-precision fit can never block every other user.
Override with the ``WEB_CONCURRENCY`` env var (the gunicorn-standard name).

Because the app is CPU-bound, the usual ``2 * cores + 1`` guidance applies; we
clamp it to a sane ceiling so a many-core box doesn't spawn a runaway number of
mpmath processes.
"""

from __future__ import annotations

import multiprocessing
import os

_MAX_WORKERS = 16


def _int_env(name: str, default: int) -> int:
    """Read an int env var, falling back to the default on empty/invalid input
    so a typo can't crash gunicorn config load and prevent startup."""
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _resolve_workers() -> int:
    explicit = os.environ.get("WEB_CONCURRENCY", "").strip()
    if explicit:
        try:
            # Keep the floor of 2 even on an explicit override: the whole point of
            # this file (P1-2) is that a single worker lets one long fit block all
            # users. Set WEB_CONCURRENCY=1 only knowingly for local debugging.
            return max(2, int(explicit))
        except ValueError:
            pass
    try:
        cores = multiprocessing.cpu_count()
    except NotImplementedError:
        cores = 1
    # 2*cores+1 is the standard CPU-bound sizing; floor at 2 so a long fit never
    # blocks all users (the P1-2 concurrency fix), ceiling to bound memory.
    return max(2, min(_MAX_WORKERS, 2 * cores + 1))


# --- gunicorn settings (module-level names are read by gunicorn) -----------
bind = os.environ.get("DATALAB_BIND", "127.0.0.1:8000")
workers = _resolve_workers()
# Sync worker: each mpmath fit is CPU-bound and holds the worker for its whole
# duration, so async workers buy nothing here. Concurrency comes from `workers`.
worker_class = "sync"
# A generous timeout: high-precision fits at large dps can legitimately run for
# tens of seconds. Override with DATALAB_WORKER_TIMEOUT if your workloads differ.
timeout = _int_env("DATALAB_WORKER_TIMEOUT", 120)
# Recycle workers periodically so any mpmath/memory growth is bounded.
max_requests = _int_env("DATALAB_MAX_REQUESTS", 1000)
max_requests_jitter = 100
