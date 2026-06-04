from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "ChoiceSpec",
    "FormFieldSpec",
    "FormSectionSpec",
    "LocalizedText",
    "PlotBudget",
    "PlotSpec",
    "ResultViewSpec",
    "VisibilityRule",
]

WidgetKind = Literal["text", "number", "select", "checkbox", "textarea"]
VisibilityOperator = Literal["equals", "in_set", "not_equals", "all"]


@dataclass(frozen=True)
class LocalizedText:
    zh: str = ""
    en: str = ""

    def for_lang(self, lang: str = "zh") -> str:
        return self.en if lang == "en" else self.zh


@dataclass(frozen=True)
class ChoiceSpec:
    value: Any
    label: LocalizedText
    tooltip: LocalizedText = field(default_factory=LocalizedText)


@dataclass(frozen=True)
class VisibilityRule:
    operator: VisibilityOperator
    key: str = ""
    expected: Any = None
    values: tuple[Any, ...] = ()
    rules: tuple[VisibilityRule, ...] = ()

    @classmethod
    def equals(cls, key: str, expected: Any) -> VisibilityRule:
        return cls(operator="equals", key=key, expected=expected)

    @classmethod
    def in_set(cls, key: str, values: Iterable[Any]) -> VisibilityRule:
        return cls(operator="in_set", key=key, values=tuple(values))

    @classmethod
    def not_equals(cls, key: str, expected: Any) -> VisibilityRule:
        return cls(operator="not_equals", key=key, expected=expected)

    @classmethod
    def all(cls, *rules: VisibilityRule) -> VisibilityRule:
        return cls(operator="all", rules=tuple(rules))

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        if self.operator == "equals":
            return bool(values.get(self.key) == self.expected)
        if self.operator == "in_set":
            return bool(values.get(self.key) in self.values)
        if self.operator == "not_equals":
            return bool(values.get(self.key) != self.expected)
        if self.operator == "all":
            return all(rule.evaluate(values) for rule in self.rules)
        raise ValueError(f"Unsupported visibility operator: {self.operator}")


@dataclass(frozen=True)
class FormFieldSpec:
    key: str
    widget_kind: WidgetKind | str
    label: LocalizedText
    placeholder: LocalizedText = field(default_factory=LocalizedText)
    tooltip: LocalizedText = field(default_factory=LocalizedText)
    required: bool = False
    default_value: Any = None
    choices: Sequence[ChoiceSpec] = ()
    visible_when: VisibilityRule | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "choices", tuple(self.choices))


@dataclass(frozen=True)
class FormSectionSpec:
    key: str
    title: LocalizedText
    fields: Sequence[FormFieldSpec] = ()
    visible_when: VisibilityRule | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))


@dataclass(frozen=True)
class ResultViewSpec:
    key: str
    title: LocalizedText
    attachment_key: str = ""


@dataclass(frozen=True)
class PlotBudget:
    max_grid_points: int = 300
    max_monte_carlo_curves: int = 100
    max_batch_rows: int = 25
    max_images_per_run: int = 25


@dataclass(frozen=True)
class PlotSpec:
    key: str
    title: LocalizedText
    plot_kind: str
    attachment_key: str
    budget: PlotBudget = field(default_factory=PlotBudget)
