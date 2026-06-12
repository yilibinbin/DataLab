"""UI-neutral service/model boundary for DataLab.

This package intentionally stays free of Qt and side-effect-heavy shared
modules. Desktop and web adapters can depend on it; it must not depend on
them.
"""

from __future__ import annotations

from . import (
    extrapolation,
    fitting,
    jobs,
    parallel_options,
    results,
    root_solving,
    service_factory,
    session,
    statistics,
    uncertainty,
    workbench_model,
    workspace_v2,
)

__all__ = [
    "extrapolation",
    "fitting",
    "jobs",
    "parallel_options",
    "results",
    "root_solving",
    "service_factory",
    "session",
    "statistics",
    "uncertainty",
    "workbench_model",
    "workspace_v2",
]
