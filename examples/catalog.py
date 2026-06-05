from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExampleSpec:
    filename: str
    category: str
    title_zh: str
    title_en: str
    variants: tuple[str, ...] = ()
    source_files: tuple[str, ...] = ()


EXAMPLE_SPECS: tuple[ExampleSpec, ...] = (
    ExampleSpec(
        filename="extrapolation.datalab",
        category="extrapolation",
        title_zh="序列外推：Richardson 极限",
        title_en="Extrapolation: Richardson limit",
        variants=("richardson",),
        source_files=("examples/extrapolation_richardson.txt",),
    ),
    ExampleSpec(
        filename="error-propagation.datalab",
        category="error-propagation",
        title_zh="误差传递：乘积量",
        title_en="Error propagation: product quantity",
        variants=("taylor", "constants"),
        source_files=("examples/error_propagation.txt", "examples/constants.txt"),
    ),
    ExampleSpec(
        filename="statistics.datalab",
        category="statistics",
        title_zh="统计平均：加权均值",
        title_en="Statistics: weighted mean",
        variants=("weighted", "sample"),
        source_files=("examples/statistics_weighted.txt",),
    ),
    ExampleSpec(
        filename="fitting.datalab",
        category="fitting",
        title_zh="拟合：带约束的幂律模型",
        title_en="Fitting: constrained power law",
        variants=("custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"),
        source_files=("examples/fitting_powerlaw.txt",),
    ),
    ExampleSpec(
        filename="quantum-defect-implicit.datalab",
        category="fitting",
        title_zh="拟合：自洽量子亏损示例",
        title_en="Fitting: self-consistent quantum defect",
        variants=("self_consistent", "implicit", "quantum_defect", "ionization_energy", "weighted"),
    ),
    ExampleSpec(
        filename="root-scalar-with-uncertainty.datalab",
        category="root-solving",
        title_zh="求根：带不确定度的标量根",
        title_en="Root solving: scalar uncertainty",
        variants=("scalar", "linear_uncertainty"),
    ),
    ExampleSpec(
        filename="root-monte-carlo-uncertainty.datalab",
        category="root-solving",
        title_zh="求根：Monte Carlo 不确定度",
        title_en="Root solving: Monte Carlo uncertainty",
        variants=("scalar", "monte_carlo"),
    ),
    ExampleSpec(
        filename="root-batch-quadratic.datalab",
        category="root-solving",
        title_zh="求根：批量二次方程",
        title_en="Root solving: batch quadratic",
        variants=("batch", "linear_uncertainty"),
    ),
)

EXAMPLE_NAMES: tuple[str, ...] = tuple(spec.filename for spec in EXAMPLE_SPECS)


def examples_by_category() -> dict[str, tuple[ExampleSpec, ...]]:
    categories: dict[str, list[ExampleSpec]] = {}
    for spec in EXAMPLE_SPECS:
        categories.setdefault(spec.category, []).append(spec)
    return {category: tuple(specs) for category, specs in categories.items()}


def example_index_payload() -> dict[str, object]:
    return {
        "schema": "datalab.example_catalog.v1",
        "examples": [
            {
                "filename": spec.filename,
                "category": spec.category,
                "title_zh": spec.title_zh,
                "title_en": spec.title_en,
                "variants": list(spec.variants),
                "source_files": list(spec.source_files),
            }
            for spec in EXAMPLE_SPECS
        ],
    }
