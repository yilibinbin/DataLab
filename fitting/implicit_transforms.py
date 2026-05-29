"""Output-transform detection for implicit fitting.

Task 1 intentionally supports only one exact affine stub. Task 2 replaces this
with the full symbolic detector.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from mpmath import mp

from .implicit_model import ImplicitModelDefinition


@dataclass(frozen=True)
class OutputTransform:
    transformed_targets: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf]], list[mp.mpf]]
    transformed_sigmas: Callable[
        [dict[str, Sequence[mp.mpf]], Sequence[mp.mpf | None] | None],
        list[mp.mpf | None] | None,
    ]
    transformed_weights: Callable[[dict[str, Sequence[mp.mpf]], list[mp.mpf] | None], list[mp.mpf] | None]
    forward_values: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf]], list[mp.mpf]]
    expression: str
    reason: str


def detect_output_transform(definition: ImplicitModelDefinition) -> OutputTransform | None:
    """Detect the Task 1 hardcoded exact affine form `2*implicit+1`."""

    text = definition.output_expression.replace(" ", "")
    implicit = definition.implicit_variable
    if text == implicit:
        return None
    if text == f"2*{implicit}+1":
        return _build_affine_transform(definition, slope=mp.mpf("2"), intercept=mp.mpf("1"))
    return None


def _build_affine_transform(
    definition: ImplicitModelDefinition,
    *,
    slope: mp.mpf,
    intercept: mp.mpf,
) -> OutputTransform | None:
    if slope == 0:
        return None

    def _targets(
        variable_data: dict[str, Sequence[mp.mpf]],
        targets: Sequence[mp.mpf],
    ) -> list[mp.mpf]:
        return [(mp.mpf(target) - intercept) / slope for target in targets]

    def _sigmas(
        variable_data: dict[str, Sequence[mp.mpf]],
        data_sigmas: Sequence[mp.mpf | None] | None,
    ) -> list[mp.mpf | None] | None:
        if data_sigmas is None:
            return None
        scale = mp.fabs(slope)
        return [None if sigma is None else mp.mpf(sigma) / scale for sigma in data_sigmas]

    def _weights(
        variable_data: dict[str, Sequence[mp.mpf]],
        weights: list[mp.mpf] | None,
    ) -> list[mp.mpf] | None:
        scale = mp.fabs(slope)
        if weights is None:
            row_count = len(next(iter(variable_data.values()))) if variable_data else 0
            return [scale * scale for _ in range(row_count)]
        return [mp.mpf(weight) * scale * scale for weight in weights]

    def _forward(
        variable_data: dict[str, Sequence[mp.mpf]],
        implicit_values: Sequence[mp.mpf],
    ) -> list[mp.mpf]:
        return [slope * mp.mpf(value) + intercept for value in implicit_values]

    return OutputTransform(
        transformed_targets=_targets,
        transformed_sigmas=_sigmas,
        transformed_weights=_weights,
        forward_values=_forward,
        expression=definition.output_expression,
        reason="exact affine output transform",
    )
