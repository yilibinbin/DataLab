"""Compute-boundary inputs for fitting jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ParameterDraft:
    name: str
    initial: str = ""
    fixed: str = ""
    min: str = ""
    max: str = ""
    expression: str = ""
    orphaned: bool = False


@dataclass(frozen=True)
class ModelProblem:
    model_type: str
    expression: str
    variables: tuple[str, ...]
    target_name: str = "y"
    parameter_config: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    constants: Mapping[str, str] = field(default_factory=dict)
    constants_enabled: bool = True
    implicit_definition: object | None = None


def constants_for_compute(problem: ModelProblem) -> dict[str, str]:
    if not problem.constants_enabled:
        return {}
    return {str(name): str(value) for name, value in problem.constants.items() if str(name).strip()}


def parameters_for_compute(rows: Sequence[ParameterDraft]) -> dict[str, dict[str, str]]:
    config: dict[str, dict[str, str]] = {}
    for row in rows:
        name = row.name.strip()
        if not name or row.orphaned:
            continue
        entry: dict[str, str] = {}
        for field_name in ("initial", "fixed", "min", "max"):
            value = getattr(row, field_name).strip()
            if value:
                entry[field_name] = value
        expression = row.expression.strip()
        if expression:
            entry["expr"] = expression
        config[name] = entry
    return config
