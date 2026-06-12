from __future__ import annotations

from typing import Any

from root_solving.batch import solve_root_batch
from root_solving.models import (
    RootBatchResult,
    RootBatchRowResult,
    RootInputValue,
    RootProblem,
    RootResult,
    RootScanConfig,
    RootUncertaintyOptions,
    RootUnknown,
    RootValue,
)
from root_solving.normalization import normalize_root_problem
from root_solving.solver import solve_root_problem
from root_solving.uncertainty import attach_linear_uncertainty


def __getattr__(name: str) -> Any:
    if name == "render_root_result":
        from root_solving.formatting import render_root_result

        return render_root_result
    raise AttributeError(name)

__all__ = [
    "RootBatchResult",
    "RootBatchRowResult",
    "RootInputValue",
    "RootProblem",
    "RootResult",
    "RootScanConfig",
    "RootUncertaintyOptions",
    "RootUnknown",
    "RootValue",
    "attach_linear_uncertainty",
    "normalize_root_problem",
    "render_root_result",
    "solve_root_batch",
    "solve_root_problem",
]
