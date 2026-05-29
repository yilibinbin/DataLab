"""Planning boundary for automatic implicit fitting strategies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
from .implicit_model import ImplicitModelDefinition
from .implicit_transforms import OutputTransform, detect_output_transform

_DOUBLE_PRECISION_DPS = 16


class ImplicitPlanKind(Enum):
    OBSERVED_LINEAR = "observed_linear"
    OBSERVED_NONLINEAR = "observed_nonlinear"
    EXACT_AFFINE_OUTPUT = "exact_affine_output"
    ANALYTIC_IMPLICIT_JACOBIAN = "analytic_implicit_jacobian"
    SCIPY_IMPLICIT = "scipy_implicit"
    GENERAL = "general"


@dataclass(frozen=True)
class ImplicitPlan:
    kind: ImplicitPlanKind
    reason: str
    transform: OutputTransform | None = None
    seed_hint: Any | None = None
    use_analytic_derivatives: bool = False
    try_scipy: bool = False


def plan_implicit_fit(definition: ImplicitModelDefinition, *, precision: int) -> ImplicitPlan:
    """Classify an implicit fit without exposing strategy controls to the GUI."""

    classification = ImplicitProblemClassifier().classify(definition)
    if classification.strategy is ImplicitStrategy.OBSERVED_LINEAR:
        return ImplicitPlan(
            kind=ImplicitPlanKind.OBSERVED_LINEAR,
            reason="observed implicit variable with linear parameter equation",
        )
    if classification.strategy is ImplicitStrategy.OBSERVED_NONLINEAR:
        return ImplicitPlan(
            kind=ImplicitPlanKind.OBSERVED_NONLINEAR,
            reason="observed implicit variable with nonlinear parameter equation",
        )

    transform = detect_output_transform(definition)
    if transform is not None:
        return ImplicitPlan(
            kind=ImplicitPlanKind.EXACT_AFFINE_OUTPUT,
            reason="affine output expression can be transformed without changing the least-squares objective",
            transform=transform,
        )

    if precision <= _DOUBLE_PRECISION_DPS:
        return ImplicitPlan(
            kind=ImplicitPlanKind.SCIPY_IMPLICIT,
            reason="double precision requested; future runner task may try SciPy implicit least_squares before mpmath fallback",
            try_scipy=True,
        )

    return ImplicitPlan(
        kind=ImplicitPlanKind.ANALYTIC_IMPLICIT_JACOBIAN,
        reason="high precision implicit output fit; use analytic implicit Jacobian before numeric fallback",
        use_analytic_derivatives=True,
    )
