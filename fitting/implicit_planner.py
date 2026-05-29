"""Planning boundary for automatic implicit fitting strategies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
from .implicit_model import ImplicitModelDefinition
from .implicit_seed_hints import ImplicitSeedHint, detect_seed_hint
from .implicit_transforms import OutputTransform, detect_output_transform


class ImplicitPlanKind(Enum):
    OBSERVED_LINEAR = "observed_linear"
    OBSERVED_NONLINEAR = "observed_nonlinear"
    EXACT_AFFINE_OUTPUT = "exact_affine_output"
    ANALYTIC_IMPLICIT_JACOBIAN = "analytic_implicit_jacobian"
    GENERAL = "general"


@dataclass(frozen=True)
class ImplicitPlan:
    kind: ImplicitPlanKind
    reason: str
    transform: OutputTransform | None = None
    seed_hint: ImplicitSeedHint | None = None
    use_analytic_derivatives: bool = False


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

    transform = detect_output_transform(definition, precision=precision)
    if transform is not None:
        return ImplicitPlan(
            kind=ImplicitPlanKind.EXACT_AFFINE_OUTPUT,
            reason="affine output expression can be transformed without changing the least-squares objective",
            transform=transform,
        )

    seed_hint = detect_seed_hint(definition, precision=precision)

    return ImplicitPlan(
        kind=ImplicitPlanKind.ANALYTIC_IMPLICIT_JACOBIAN,
        reason="general implicit output fit; use analytic implicit Jacobian when preflight succeeds",
        seed_hint=seed_hint,
        use_analytic_derivatives=True,
    )
