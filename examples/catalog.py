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
    recipe_files: tuple[str, ...] = ()


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
        recipe_files=("examples/recipes/error-product-basic.json",),
    ),
    ExampleSpec(
        filename="error-propagation-units.datalab",
        category="error-propagation",
        title_zh="误差传递：单位标注",
        title_en="Error propagation: unit labels",
        variants=("taylor", "units", "display_only", "validation_ready"),
    ),
    ExampleSpec(
        filename="statistics.datalab",
        category="statistics",
        title_zh="统计平均：加权均值",
        title_en="Statistics: weighted mean",
        variants=("weighted", "sample"),
        source_files=("examples/statistics_weighted.txt",),
        recipe_files=("examples/recipes/statistics-mean-basic.json",),
    ),
    ExampleSpec(
        filename="statistics-bootstrap.datalab",
        category="statistics",
        title_zh="统计平均：Bootstrap 置信区间",
        title_en="Statistics: Bootstrap confidence interval",
        variants=("bootstrap", "confidence_interval", "seeded"),
    ),
    ExampleSpec(
        filename="statistics-hypothesis.datalab",
        category="statistics",
        title_zh="统计检验：单样本 t 检验",
        title_en="Statistics: one-sample t-test",
        variants=("hypothesis_test", "one_sample_t"),
    ),
    ExampleSpec(
        filename="statistics-matrix.datalab",
        category="statistics",
        title_zh="统计矩阵：协方差与相关系数",
        title_en="Statistics matrix: covariance and correlation",
        variants=("covariance_correlation", "matrix", "listwise"),
    ),
    ExampleSpec(
        filename="statistics-grouped.datalab",
        category="statistics",
        title_zh="分组统计：多组多列均值",
        title_en="Grouped statistics: multi-group means",
        variants=("grouped_statistics", "multi_column", "weighted"),
    ),
    ExampleSpec(
        filename="statistics-time-series-rolling.datalab",
        category="statistics",
        title_zh="时间序列：滚动均值",
        title_en="Time series: rolling mean",
        variants=("time_series", "rolling_mean", "uncertainty"),
    ),
    ExampleSpec(
        filename="statistics-time-series-ewma.datalab",
        category="statistics",
        title_zh="时间序列：EWMA 平滑",
        title_en="Time series: EWMA smoothing",
        variants=("time_series", "ewma", "smoothing"),
    ),
    ExampleSpec(
        filename="fitting.datalab",
        category="fitting",
        title_zh="拟合：带约束的幂律模型",
        title_en="Fitting: constrained power law",
        variants=("custom", "implicit", "weighted", "constraints", "high_precision", "scipy_precision_16"),
        source_files=("examples/fitting_powerlaw.txt",),
        recipe_files=("examples/recipes/fitting-custom-powerlaw.json",),
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
        recipe_files=("examples/recipes/root-batch-quadratic.json",),
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
                "recipe_files": list(spec.recipe_files),
            }
            for spec in EXAMPLE_SPECS
        ],
    }
