from __future__ import annotations

import hashlib
import random
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.distribution_summary import (
    MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA,
    MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA_VERSION,
    build_monte_carlo_distribution_summary,
)
from shared.parallel_backend import ParallelMapExecutor
from shared.parallel_config import ParallelConfig, ParallelWorkload
from shared.precision import precision_guard
from shared.unit_annotations import normalize_display_only_family_units

from .results import AnalysisRow
from .session import check_cancelled
from .statistics_compute import compute_statistics

BOOTSTRAP_PAYLOAD_SCHEMA = "datalab.statistics.bootstrap.v1"
BOOTSTRAP_WORKFLOW_MODE = "bootstrap_confidence_intervals"
BOOTSTRAP_CONFIDENCE_LEVEL = "0.95"
BOOTSTRAP_METHOD = "percentile"
BOOTSTRAP_RNG_ALGORITHM = "python_random_v1"
BOOTSTRAP_RNG_SCHEDULE = "per_replicate_seed_v1"

BOOTSTRAP_TARGETS = frozenset({"mean", "median", "trimmed_mean", "std", "variance"})
BOOTSTRAP_MIN_RESAMPLE_COUNT = 100
BOOTSTRAP_MAX_RESAMPLE_COUNT = 100000
_BOOTSTRAP_CHUNK_SIZE = 64
_BOOTSTRAP_CHUNKS_PER_MAP = 16
_BOOTSTRAP_OPTION_KEYS = frozenset(
    {
        "target_statistic",
        "confidence_level",
        "resample_count",
        "seed",
        "sample_mode",
        "trim_fraction",
        "method",
    }
)
_BOOTSTRAP_PAYLOAD_KEYS = frozenset(
    {
        "schema",
        "workflow_mode",
        "target_statistic",
        "confidence_level",
        "resample_count",
        "seed",
        "seeded",
        "rng_algorithm",
        "rng_schedule",
        "sample_mode",
        "trim_fraction",
        "method",
        "columns",
        "diagnostics",
        "units",
    }
)
_BOOTSTRAP_COLUMN_KEYS = frozenset(
    {
        "value_column",
        "column_index",
        "row_count",
        "source_row_ids",
        "original_statistic",
        "distribution",
        "diagnostics",
    }
)
_DISTRIBUTION_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "requested_sample_count",
        "evaluated_sample_count",
        "accepted_sample_count",
        "rejected_sample_count",
        "finite_sample_count",
        "mean",
        "std",
        "histogram",
        "percentiles",
    }
)


@dataclass(frozen=True)
class StatisticsBootstrapOptions:
    target_statistic: str
    confidence_level: str
    resample_count: int
    seed: int | None
    sample_mode: str
    trim_fraction: str | None


@dataclass(frozen=True)
class _BootstrapChunkTask:
    start_index: int
    count: int
    values: tuple[str, ...]
    target_statistic: str
    sample_mode: str
    trim_fraction: str | None
    precision_digits: int
    run_seed: int


def normalize_statistics_bootstrap_options(inputs: Mapping[str, Any]) -> StatisticsBootstrapOptions:
    option_inputs = _bootstrap_option_inputs(inputs)
    method = _text_option(option_inputs.get("method"), default=BOOTSTRAP_METHOD, field_name="method")
    if method != BOOTSTRAP_METHOD:
        raise ValueError(_dual_msg("首个版本中 Bootstrap method 固定为 percentile。", "Bootstrap method is fixed to percentile in the first release."))

    target = _text_option(option_inputs.get("target_statistic"), default="mean", field_name="target_statistic")
    if target not in BOOTSTRAP_TARGETS:
        raise ValueError(_dual_msg(f"不支持的 bootstrap 目标统计量：{target}。", f"Unsupported bootstrap target statistic: {target}."))

    confidence_level = _text_option(
        option_inputs.get("confidence_level"),
        default=BOOTSTRAP_CONFIDENCE_LEVEL,
        field_name="confidence_level",
    )
    if mp.mpf(confidence_level) != mp.mpf(BOOTSTRAP_CONFIDENCE_LEVEL):
        raise ValueError(_dual_msg("首个版本中 Bootstrap confidence_level 固定为 0.95。", "Bootstrap confidence_level is fixed to 0.95 in the first release."))

    resample_count = _int_option(
        option_inputs.get("resample_count"),
        default=2000,
        field_name="resample_count",
    )
    if resample_count < BOOTSTRAP_MIN_RESAMPLE_COUNT:
        raise ValueError(_dual_msg(f"resample_count 至少为 {BOOTSTRAP_MIN_RESAMPLE_COUNT}。", f"resample_count must be at least {BOOTSTRAP_MIN_RESAMPLE_COUNT}."))
    if resample_count > BOOTSTRAP_MAX_RESAMPLE_COUNT:
        raise ValueError(_dual_msg(f"resample_count 至多为 {BOOTSTRAP_MAX_RESAMPLE_COUNT}。", f"resample_count must be at most {BOOTSTRAP_MAX_RESAMPLE_COUNT}."))

    seed = _optional_seed(option_inputs.get("seed"))
    sample_mode = _text_option(option_inputs.get("sample_mode"), default="sample", field_name="sample_mode")
    if sample_mode not in {"sample", "population"}:
        raise ValueError(_dual_msg("sample_mode 必须为 'sample' 或 'population'。", "sample_mode must be 'sample' or 'population'."))

    trim_fraction = _optional_numeric_text(option_inputs.get("trim_fraction"), field_name="trim_fraction")
    if target == "trimmed_mean" and trim_fraction is None:
        trim_fraction = "0.1"
    if target != "trimmed_mean":
        trim_fraction = None

    return StatisticsBootstrapOptions(
        target_statistic=target,
        confidence_level=BOOTSTRAP_CONFIDENCE_LEVEL,
        resample_count=resample_count,
        seed=seed,
        sample_mode=sample_mode,
        trim_fraction=trim_fraction,
    )


def run_statistics_bootstrap(
    *,
    values: Sequence[mp.mpf],
    source_row_ids: Sequence[str | int] | None,
    precision_digits: int,
    options: StatisticsBootstrapOptions,
    parallel_config: ParallelConfig | None = None,
    value_column: str = "",
    column_index: int | None = None,
) -> dict[str, object]:
    if not values:
        raise ValueError(_dual_msg("values 必须至少包含一个值。", "values must contain at least one value."))
    values_mp = [mp.mpf(value) for value in values]
    if any(not mp.isfinite(value) for value in values_mp):
        raise ValueError(_dual_msg("Bootstrap 统计需要有限的数值。", "Bootstrap statistics requires finite numeric values."))
    if options.target_statistic in {"std", "variance"} and options.sample_mode == "sample" and len(values_mp) < 2:
        raise ValueError(_dual_msg("样本 std/variance 的 bootstrap 至少需要两个值。", "Sample std/variance bootstrap requires at least two values."))

    row_ids = tuple(source_row_ids or tuple(str(index + 1) for index in range(len(values_mp))))
    if len(row_ids) != len(values_mp):
        raise ValueError(_dual_msg("source_row_ids 的长度必须与 values 相同。", "source_row_ids must have the same length as values."))

    original = _evaluate_target(
        values_mp,
        target_statistic=options.target_statistic,
        sample_mode=options.sample_mode,
        trim_fraction=options.trim_fraction,
    )
    if not mp.isfinite(original):
        raise ValueError(_dual_msg("原始 bootstrap 统计量不是有限值。", "Original bootstrap statistic is not finite."))

    value_texts = tuple(_format_mpf(value, precision_digits) for value in values_mp)
    run_seed = options.seed if options.seed is not None else secrets.randbits(128)
    tasks = tuple(
        _BootstrapChunkTask(
            start_index=start,
            count=min(_BOOTSTRAP_CHUNK_SIZE, options.resample_count - start),
            values=value_texts,
            target_statistic=options.target_statistic,
            sample_mode=options.sample_mode,
            trim_fraction=options.trim_fraction,
            precision_digits=precision_digits,
            run_seed=run_seed,
        )
        for start in range(0, options.resample_count, _BOOTSTRAP_CHUNK_SIZE)
    )
    executor = ParallelMapExecutor(parallel_config)
    chunk_results: list[tuple[tuple[int, str], ...]] = []
    for task_batch in _batched(tasks, _BOOTSTRAP_CHUNKS_PER_MAP):
        check_cancelled()
        chunk_results.extend(
            executor.map_pure(
                _evaluate_bootstrap_chunk,
                task_batch,
                workload=ParallelWorkload.CPU_MPMATH,
            )
        )
        check_cancelled()
    replicate_values_by_index = {
        replicate_index: mp.mpf(value)
        for chunk in chunk_results
        for replicate_index, value in chunk
    }
    replicate_values = [replicate_values_by_index[index] for index in range(options.resample_count)]
    finite_values = [value for value in replicate_values if mp.isfinite(value)]
    rejected_count = options.resample_count - len(finite_values)
    if not finite_values:
        raise ValueError(_dual_msg("未产生任何有限的 bootstrap 重采样结果。", "No finite bootstrap replicates were produced."))
    mean = mp.fsum(finite_values) / len(finite_values)
    std = _sample_std(finite_values)
    distribution = build_monte_carlo_distribution_summary(
        sample_count=options.resample_count,
        accepted_count=len(finite_values),
        rejected_count=rejected_count,
        mean=mean,
        std=std,
        accepted_samples=finite_values,
    )

    column: dict[str, object] = {
        "value_column": value_column,
        "row_count": len(values_mp),
        "source_row_ids": list(row_ids),
        "original_statistic": _format_mpf(original, precision_digits),
        "distribution": _distribution_summary_to_payload(distribution, precision_digits),
        "diagnostics": [],
    }
    if column_index is not None:
        column["column_index"] = column_index

    diagnostics = [] if options.seed is not None else ["bootstrap_seed_not_provided"]
    payload: dict[str, object] = {
        "schema": BOOTSTRAP_PAYLOAD_SCHEMA,
        "workflow_mode": BOOTSTRAP_WORKFLOW_MODE,
        "target_statistic": options.target_statistic,
        "confidence_level": options.confidence_level,
        "resample_count": options.resample_count,
        "seed": options.seed,
        "seeded": options.seed is not None,
        "rng_algorithm": BOOTSTRAP_RNG_ALGORITHM,
        "rng_schedule": BOOTSTRAP_RNG_SCHEDULE,
        "sample_mode": options.sample_mode,
        "trim_fraction": options.trim_fraction,
        "method": BOOTSTRAP_METHOD,
        "columns": [column],
        "diagnostics": diagnostics,
    }
    validate_statistics_bootstrap_payload(payload)
    return payload


def validate_statistics_bootstrap_payload(payload: Mapping[str, Any]) -> None:
    _reject_json_floats(payload, path="payload")
    _reject_unknown_keys(payload, _BOOTSTRAP_PAYLOAD_KEYS, path="payload")
    if "units" in payload:
        normalize_display_only_family_units(payload.get("units"), family="statistics")
    if payload.get("schema") != BOOTSTRAP_PAYLOAD_SCHEMA:
        raise ValueError(_dual_msg("无效的 bootstrap payload schema。", "Invalid bootstrap payload schema."))
    if payload.get("workflow_mode") != BOOTSTRAP_WORKFLOW_MODE:
        raise ValueError(_dual_msg("无效的 bootstrap workflow mode。", "Invalid bootstrap workflow mode."))
    if payload.get("target_statistic") not in BOOTSTRAP_TARGETS:
        raise ValueError(_dual_msg("无效的 bootstrap 目标统计量。", "Invalid bootstrap target statistic."))
    if payload.get("confidence_level") != BOOTSTRAP_CONFIDENCE_LEVEL:
        raise ValueError(_dual_msg("无效的 bootstrap 置信水平。", "Invalid bootstrap confidence level."))
    if payload.get("method") != BOOTSTRAP_METHOD:
        raise ValueError(_dual_msg("无效的 bootstrap method。", "Invalid bootstrap method."))
    if payload.get("rng_algorithm") != BOOTSTRAP_RNG_ALGORITHM:
        raise ValueError(_dual_msg("无效的 bootstrap RNG 算法。", "Invalid bootstrap RNG algorithm."))
    if payload.get("rng_schedule") != BOOTSTRAP_RNG_SCHEDULE:
        raise ValueError(_dual_msg("无效的 bootstrap RNG 调度。", "Invalid bootstrap RNG schedule."))
    resample_count = payload.get("resample_count")
    if isinstance(resample_count, bool) or not isinstance(resample_count, int):
        raise TypeError(_dual_msg("resample_count 必须是整数。", "resample_count must be an integer."))
    if resample_count < BOOTSTRAP_MIN_RESAMPLE_COUNT or resample_count > BOOTSTRAP_MAX_RESAMPLE_COUNT:
        raise ValueError(_dual_msg("无效的 bootstrap resample_count。", "Invalid bootstrap resample_count."))
    seed = payload.get("seed")
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise TypeError(_dual_msg("seed 必须是整数或 null。", "seed must be an integer or null."))
    seeded = payload.get("seeded")
    if not isinstance(seeded, bool):
        raise TypeError(_dual_msg("seeded 必须是布尔值。", "seeded must be a boolean."))
    if seeded != (seed is not None):
        raise ValueError(_dual_msg("seeded 必须与是否存在 seed 保持一致。", "seeded must match whether seed is present."))
    if payload.get("sample_mode") not in {"sample", "population"}:
        raise ValueError(_dual_msg("无效的 bootstrap 采样模式。", "Invalid bootstrap sample mode."))
    trim_fraction = payload.get("trim_fraction")
    if trim_fraction is not None:
        _require_numeric_string(trim_fraction, "trim_fraction")
    diagnostics = payload.get("diagnostics")
    if not _is_text_sequence(diagnostics):
        raise TypeError(_dual_msg("diagnostics 必须是字符串序列。", "diagnostics must be a sequence of strings."))
    columns = payload.get("columns")
    if not isinstance(columns, Sequence) or isinstance(columns, (str, bytes, bytearray, memoryview)) or not columns:
        raise TypeError(_dual_msg("columns 必须是非空序列。", "columns must be a non-empty sequence."))
    for index, column in enumerate(columns):
        if not isinstance(column, Mapping):
            raise TypeError(_dual_msg("bootstrap columns 必须是映射。", "bootstrap columns must be mappings."))
        _validate_bootstrap_column(column, resample_count=resample_count, index=index)


def statistics_bootstrap_analysis_rows_from_column(
    payload: Mapping[str, Any],
    column: Mapping[str, Any],
) -> tuple[AnalysisRow, ...]:
    validate_statistics_bootstrap_payload(payload)
    resample_count = int(payload["resample_count"])
    _validate_bootstrap_column(column, resample_count=resample_count, index=0)

    method = BOOTSTRAP_WORKFLOW_MODE
    distribution = column["distribution"]
    if not isinstance(distribution, Mapping):
        raise TypeError(_dual_msg("bootstrap column distribution 必须是映射。", "bootstrap column distribution must be a mapping."))
    percentiles = distribution["percentiles"]
    if not isinstance(percentiles, Mapping):
        raise TypeError(_dual_msg("bootstrap distribution percentiles 必须是映射。", "bootstrap distribution percentiles must be a mapping."))

    rows: list[AnalysisRow] = [
        AnalysisRow(
            key="method",
            label_key="statistics.method",
            value=BOOTSTRAP_WORKFLOW_MODE,
            method=method,
            render_group="diagnostic",
        ),
        AnalysisRow(
            key="row_count",
            label_key="statistics.metric.row_count",
            value=int(column["row_count"]),
            method=method,
        ),
        AnalysisRow(
            key="bootstrap_original_statistic",
            label_key="statistics.bootstrap.original_statistic",
            value=str(column["original_statistic"]),
            method=method,
        ),
        AnalysisRow(
            key="bootstrap_ci_lower",
            label_key="statistics.bootstrap.ci_lower",
            value=str(percentiles["2.5"]),
            method=method,
        ),
        AnalysisRow(
            key="bootstrap_ci_median",
            label_key="statistics.bootstrap.ci_median",
            value=str(percentiles["50"]),
            method=method,
        ),
        AnalysisRow(
            key="bootstrap_ci_upper",
            label_key="statistics.bootstrap.ci_upper",
            value=str(percentiles["97.5"]),
            method=method,
        ),
        AnalysisRow(
            key="bootstrap_mean",
            label_key="statistics.bootstrap.mean",
            value=str(distribution["mean"]),
            method=method,
        ),
        AnalysisRow(
            key="bootstrap_std",
            label_key="statistics.bootstrap.std",
            value=str(distribution["std"]),
            method=method,
        ),
    ]

    diagnostic_specs: tuple[tuple[str, str, object], ...] = (
        ("bootstrap_target_statistic", "statistics.bootstrap.target_statistic", payload["target_statistic"]),
        ("bootstrap_confidence_level", "statistics.bootstrap.confidence_level", payload["confidence_level"]),
        ("bootstrap_resample_count", "statistics.bootstrap.resample_count", resample_count),
        ("bootstrap_method", "statistics.bootstrap.method", payload["method"]),
        ("bootstrap_sample_mode", "statistics.bootstrap.sample_mode", payload["sample_mode"]),
        ("bootstrap_seeded", "statistics.bootstrap.seeded", "true" if payload["seeded"] else "false"),
        ("bootstrap_rng_algorithm", "statistics.bootstrap.rng_algorithm", payload["rng_algorithm"]),
        ("bootstrap_rng_schedule", "statistics.bootstrap.rng_schedule", payload["rng_schedule"]),
        (
            "bootstrap_requested_sample_count",
            "statistics.bootstrap.requested_sample_count",
            distribution["requested_sample_count"],
        ),
        (
            "bootstrap_accepted_sample_count",
            "statistics.bootstrap.accepted_sample_count",
            distribution["accepted_sample_count"],
        ),
        (
            "bootstrap_rejected_sample_count",
            "statistics.bootstrap.rejected_sample_count",
            distribution["rejected_sample_count"],
        ),
        (
            "bootstrap_finite_sample_count",
            "statistics.bootstrap.finite_sample_count",
            distribution["finite_sample_count"],
        ),
    )
    for key, label_key, value in diagnostic_specs:
        rows.append(
            AnalysisRow(
                key=key,
                label_key=label_key,
                value=value if isinstance(value, int) else str(value),
                method=method,
                render_group="diagnostic",
            )
        )

    if payload.get("seed") is not None:
        rows.append(
            AnalysisRow(
                key="bootstrap_seed",
                label_key="statistics.bootstrap.seed",
                value=int(payload["seed"]),
                method=method,
                render_group="diagnostic",
            )
        )
    if payload.get("trim_fraction") is not None:
        rows.append(
            AnalysisRow(
                key="bootstrap_trim_fraction",
                label_key="statistics.bootstrap.trim_fraction",
                value=str(payload["trim_fraction"]),
                method=method,
                render_group="diagnostic",
            )
        )

    diagnostics = list(payload.get("diagnostics", ())) + list(column.get("diagnostics", ()))
    for index, diagnostic in enumerate(diagnostics, 1):
        rows.append(
            AnalysisRow(
                key=f"bootstrap_warning.{index}",
                label_key="statistics.warning",
                value=str(diagnostic),
                method=method,
                severity="warning",
                render_group="diagnostic",
            )
        )
    return tuple(rows)


def _evaluate_bootstrap_chunk(task: _BootstrapChunkTask) -> tuple[tuple[int, str], ...]:
    with precision_guard(task.precision_digits):
        values = [mp.mpf(value) for value in task.values]
        output: list[tuple[int, str]] = []
        for offset in range(task.count):
            if offset % 16 == 0:
                check_cancelled()
            replicate_index = task.start_index + offset
            rng = random.Random(_replicate_seed(task.run_seed, replicate_index))
            sample = [values[rng.randrange(len(values))] for _ in values]
            statistic = _evaluate_target(
                sample,
                target_statistic=task.target_statistic,
                sample_mode=task.sample_mode,
                trim_fraction=task.trim_fraction,
            )
            output.append((replicate_index, _format_mpf(statistic, task.precision_digits)))
        return tuple(output)


def _evaluate_target(
    values: Sequence[mp.mpf],
    *,
    target_statistic: str,
    sample_mode: str,
    trim_fraction: str | None,
) -> mp.mpf:
    sample_based = sample_mode == "sample"
    descriptive_mode = "descriptive_sample" if sample_based else "descriptive_population"
    if target_statistic == "mean":
        mode = "mean_sample" if sample_based else "mean_population"
        result = compute_statistics(values, [None] * len(values), mode, use_sample=sample_based)
        return mp.mpf(result["mean"])
    result = compute_statistics(
        values,
        [None] * len(values),
        descriptive_mode,
        use_sample=sample_based,
        trim_fraction=trim_fraction,
    )
    if target_statistic == "median":
        return mp.mpf(result["median"])
    if target_statistic == "trimmed_mean":
        trimmed = result.get("trimmed_mean")
        if trimmed is None:
            raise ValueError(_dual_msg("trimmed_mean 需要 trim_fraction。", "trimmed_mean requires trim_fraction."))
        return mp.mpf(trimmed)
    if target_statistic == "std":
        return mp.mpf(result["std"])
    if target_statistic == "variance":
        return mp.mpf(result["variance"])
    raise ValueError(_dual_msg(f"不支持的 bootstrap 目标统计量：{target_statistic}。", f"Unsupported bootstrap target statistic: {target_statistic}."))


def _distribution_summary_to_payload(summary: Mapping[str, Any], precision_digits: int) -> dict[str, object]:
    histogram = summary.get("histogram")
    if not isinstance(histogram, Mapping):
        raise ValueError(_dual_msg("distribution histogram 必须是映射。", "distribution histogram must be a mapping."))
    percentiles = summary.get("percentiles")
    if not isinstance(percentiles, Mapping):
        raise ValueError(_dual_msg("distribution percentiles 必须是映射。", "distribution percentiles must be a mapping."))
    return {
        "schema": str(summary.get("schema") or ""),
        "schema_version": int(summary.get("schema_version") or 0),
        "requested_sample_count": int(summary.get("requested_sample_count") or 0),
        "evaluated_sample_count": int(summary.get("evaluated_sample_count") or 0),
        "accepted_sample_count": int(summary.get("accepted_sample_count") or 0),
        "rejected_sample_count": int(summary.get("rejected_sample_count") or 0),
        "finite_sample_count": int(summary.get("finite_sample_count") or 0),
        "mean": _format_mpf(summary.get("mean"), precision_digits),
        "std": _format_mpf(summary.get("std"), precision_digits),
        "histogram": {
            "bin_edges": [_format_mpf(edge, precision_digits) for edge in histogram.get("bin_edges", ())],
            "counts": [int(count) for count in histogram.get("counts", ())],
        },
        "percentiles": {
            str(key): _format_mpf(value, precision_digits) for key, value in percentiles.items()
        },
    }


def _validate_bootstrap_column(column: Mapping[str, Any], *, resample_count: int, index: int) -> None:
    _reject_unknown_keys(column, _BOOTSTRAP_COLUMN_KEYS, path=f"columns[{index}]")
    value_column = column.get("value_column")
    if not isinstance(value_column, str):
        raise TypeError(_dual_msg("bootstrap column value_column 必须是字符串。", "bootstrap column value_column must be a string."))
    column_index = column.get("column_index")
    if column_index is not None and (isinstance(column_index, bool) or not isinstance(column_index, int) or column_index < 1):
        raise TypeError(_dual_msg("bootstrap column column_index 必须是正整数。", "bootstrap column column_index must be a positive integer."))
    row_count = column.get("row_count")
    if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 1:
        raise TypeError(_dual_msg("bootstrap column row_count 必须是正整数。", "bootstrap column row_count must be a positive integer."))
    source_row_ids = column.get("source_row_ids")
    if (
        not isinstance(source_row_ids, Sequence)
        or isinstance(source_row_ids, (str, bytes, bytearray, memoryview))
        or len(source_row_ids) != row_count
    ):
        raise ValueError(_dual_msg("source_row_ids 必须与 row_count 匹配。", "source_row_ids must match row_count."))
    for row_index, row_id in enumerate(source_row_ids):
        _validate_source_row_id(row_id, field_name=f"columns[{index}].source_row_ids[{row_index}]")
    _require_numeric_string(column.get("original_statistic"), f"columns[{index}].original_statistic")
    distribution = column.get("distribution")
    if not isinstance(distribution, Mapping):
        raise TypeError(_dual_msg("bootstrap column distribution 必须是映射。", "bootstrap column distribution must be a mapping."))
    _validate_distribution_summary_payload(distribution, resample_count=resample_count)
    for duplicate_key in ("mean", "std", "ci_lower", "ci_upper", "finite_sample_count"):
        if duplicate_key in column:
            raise ValueError(_dual_msg(f"bootstrap column 重复了 distribution 字段：{duplicate_key}。", f"bootstrap column duplicates distribution field: {duplicate_key}."))
    diagnostics = column.get("diagnostics")
    if not _is_text_sequence(diagnostics):
        raise TypeError(_dual_msg("bootstrap column diagnostics 必须是字符串序列。", "bootstrap column diagnostics must be a sequence of strings."))


def _validate_distribution_summary_payload(summary: Mapping[str, Any], *, resample_count: int) -> None:
    _reject_unknown_keys(summary, _DISTRIBUTION_KEYS, path="distribution")
    if summary.get("schema") != MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA:
        raise ValueError(_dual_msg("无效的 distribution summary schema。", "Invalid distribution summary schema."))
    if summary.get("schema_version") != MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA_VERSION:
        raise ValueError(_dual_msg("无效的 distribution summary schema 版本。", "Invalid distribution summary schema version."))
    requested_count = _nonnegative_int(summary.get("requested_sample_count"), "requested_sample_count")
    evaluated_count = _nonnegative_int(summary.get("evaluated_sample_count"), "evaluated_sample_count")
    accepted_count = _nonnegative_int(summary.get("accepted_sample_count"), "accepted_sample_count")
    rejected_count = _nonnegative_int(summary.get("rejected_sample_count"), "rejected_sample_count")
    finite_count = _nonnegative_int(summary.get("finite_sample_count"), "finite_sample_count")
    if requested_count != resample_count:
        raise ValueError(_dual_msg("distribution requested_sample_count 必须与 resample_count 匹配。", "distribution requested_sample_count must match resample_count."))
    if evaluated_count != resample_count:
        raise ValueError(_dual_msg("distribution evaluated_sample_count 必须与 resample_count 匹配。", "distribution evaluated_sample_count must match resample_count."))
    if accepted_count != finite_count:
        raise ValueError(_dual_msg("distribution accepted_sample_count 必须等于 finite_sample_count。", "distribution accepted_sample_count must equal finite_sample_count."))
    if accepted_count + rejected_count != resample_count:
        raise ValueError(_dual_msg("distribution 的 accepted/rejected 计数之和必须与 resample_count 匹配。", "distribution accepted/rejected counts must match resample_count."))
    if accepted_count <= 0:
        raise ValueError(_dual_msg("distribution 必须至少包含一个已接受的样本。", "distribution must contain at least one accepted sample."))
    _require_numeric_string(summary.get("mean"), "distribution.mean")
    _require_numeric_string(summary.get("std"), "distribution.std")
    histogram = summary.get("histogram")
    if not isinstance(histogram, Mapping):
        raise TypeError(_dual_msg("distribution histogram 必须是映射。", "distribution histogram must be a mapping."))
    _reject_unknown_keys(histogram, {"bin_edges", "counts"}, path="distribution.histogram")
    edges = histogram.get("bin_edges")
    counts = histogram.get("counts")
    if not isinstance(edges, Sequence) or isinstance(edges, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg("distribution histogram bin_edges 必须是序列。", "distribution histogram bin_edges must be a sequence."))
    if not isinstance(counts, Sequence) or isinstance(counts, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg("distribution histogram counts 必须是序列。", "distribution histogram counts must be a sequence."))
    for edge in edges:
        _require_numeric_string(edge, "distribution.histogram.bin_edges[]")
    for count in counts:
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TypeError(_dual_msg("distribution histogram counts 必须是非负整数。", "distribution histogram counts must be non-negative integers."))
    if counts:
        if len(edges) != len(counts) + 1:
            raise ValueError(_dual_msg("distribution histogram 的边数必须比计数多一个。", "distribution histogram must have one more edge than count."))
    elif edges:
        raise ValueError(_dual_msg("distribution histogram 的边需要计数。", "distribution histogram edges require counts."))
    if sum(int(count) for count in counts) != finite_count:
        raise ValueError(_dual_msg("distribution histogram counts 之和必须等于 finite_sample_count。", "distribution histogram counts must sum to finite_sample_count."))
    percentiles = summary.get("percentiles")
    if not isinstance(percentiles, Mapping):
        raise TypeError(_dual_msg("distribution percentiles 必须是映射。", "distribution percentiles must be a mapping."))
    _reject_unknown_keys(percentiles, {"2.5", "50", "97.5"}, path="distribution.percentiles")
    for key in ("2.5", "50", "97.5"):
        _require_numeric_string(percentiles.get(key), f"distribution.percentiles.{key}")
    lower = mp.mpf(str(percentiles["2.5"]))
    median = mp.mpf(str(percentiles["50"]))
    upper = mp.mpf(str(percentiles["97.5"]))
    if lower > median or median > upper:
        raise ValueError(_dual_msg("distribution percentiles 必须有序。", "distribution percentiles must be ordered."))


def _sample_std(values: Sequence[mp.mpf]) -> mp.mpf:
    if len(values) < 2:
        return mp.mpf("0")
    mean = mp.fsum(values) / len(values)
    variance = mp.fsum([(value - mean) ** 2 for value in values]) / (len(values) - 1)
    return mp.sqrt(variance)


def _batched(items: Sequence[_BootstrapChunkTask], size: int) -> tuple[tuple[_BootstrapChunkTask, ...], ...]:
    return tuple(tuple(items[start : start + size]) for start in range(0, len(items), size))


def _replicate_seed(run_seed: int, replicate_index: int) -> int:
    digest = hashlib.blake2b(
        f"datalab-bootstrap-v1:{run_seed}:{replicate_index}".encode("utf-8"),
        digest_size=16,
    ).digest()
    return int.from_bytes(digest, "big")


def _bootstrap_option_inputs(inputs: Mapping[str, Any]) -> dict[str, Any]:
    raw_bootstrap = inputs.get("bootstrap")
    nested: Mapping[str, Any] = {}
    if raw_bootstrap is not None:
        if not isinstance(raw_bootstrap, Mapping):
            raise TypeError(_dual_msg("bootstrap 必须是映射。", "bootstrap must be a mapping."))
        _reject_unknown_keys(raw_bootstrap, _BOOTSTRAP_OPTION_KEYS, path="bootstrap")
        nested = raw_bootstrap
    output: dict[str, Any] = {}
    for key in _BOOTSTRAP_OPTION_KEYS:
        has_nested = key in nested
        has_top_level = key in inputs
        if has_nested and has_top_level and nested[key] != inputs[key]:
            raise ValueError(_dual_msg(f"冲突的 bootstrap 选项：{key}。", f"Conflicting bootstrap option: {key}."))
        if has_nested:
            output[key] = nested[key]
        elif has_top_level:
            output[key] = inputs[key]
    return output


def _text_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(_dual_msg(f"{field_name} 必须是字符串。", f"{field_name} must be a string."))
    return value.strip() or default


def _optional_numeric_text(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(_dual_msg(f"{field_name} 必须是数值字符串。", f"{field_name} must be a numeric string."))
    text = value.strip()
    if not text:
        return None
    parsed = mp.mpf(text)
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限数。", f"{field_name} must be finite."))
    if parsed < 0:
        raise ValueError(_dual_msg(f"{field_name} 必须是非负数。", f"{field_name} must be non-negative."))
    return text


def _int_option(value: Any, *, default: int, field_name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是整数。", f"{field_name} must be an integer."))
    return int(value)


def _optional_seed(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        value = int(text)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg("seed 必须是整数或 null。", "seed must be an integer or null."))
    return int(value)


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _require_numeric_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是数值字符串。", f"{field_name} must be a numeric string."))
    parsed = mp.mpf(value)
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限数。", f"{field_name} must be finite."))


def _nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(_dual_msg(f"distribution {field_name} 必须是非负整数。", f"distribution {field_name} must be a non-negative integer."))
    return int(value)


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{path} 处不允许 JSON 浮点数；请将数值以字符串形式传入。", f"JSON floats are not allowed at {path}; pass numeric values as strings."))
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, float):
                raise TypeError(_dual_msg(f"{path}.<key> 处不允许 JSON 浮点数。", f"JSON floats are not allowed at {path}.<key>."))
            _reject_json_floats(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, item in enumerate(value):
            _reject_json_floats(item, path=f"{path}[{index}]")


def _reject_unknown_keys(mapping: Mapping[str, Any], allowed: set[str] | frozenset[str], *, path: str) -> None:
    unknown = set(mapping) - set(allowed)
    if unknown:
        names = ", ".join(sorted(str(key) for key in unknown))
        raise ValueError(_dual_msg(f"{path} 包含不支持的字段：{names}。", f"{path} contains unsupported fields: {names}."))


def _validate_source_row_id(value: Any, *, field_name: str) -> None:
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{field_name} 处不允许 JSON 浮点数。", f"JSON floats are not allowed at {field_name}."))
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise TypeError(_dual_msg(f"{field_name} 必须是字符串或整数。", f"{field_name} must be a string or integer."))
    if isinstance(value, str) and not value.strip():
        raise ValueError(_dual_msg(f"{field_name} 不能为空白。", f"{field_name} must not be blank."))


def _is_text_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray, memoryview))
        and all(isinstance(item, str) for item in value)
    )
