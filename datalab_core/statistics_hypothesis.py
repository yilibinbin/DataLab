from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import comb
from typing import Any

import mpmath as mp

from shared.bilingual import _dual_msg
from shared.unit_annotations import first_unit_annotation_text, normalize_display_only_family_units
from shared.precision import precision_guard

from ._payload import normalize_json_payload
from .results import AnalysisRow, analysis_rows_from_json, analysis_rows_to_json

HYPOTHESIS_WORKFLOW_MODE = "hypothesis_tests"
HYPOTHESIS_PAYLOAD_SCHEMA = "datalab.statistics.hypothesis_test.v1"
HYPOTHESIS_RESULT_CACHE_KIND = "statistics_hypothesis_test"
_STATISTICS_RESULT_SNAPSHOT_SCHEMA = "datalab.result_snapshot.statistics"
_STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION = 1

_SUPPORTED_TEST_KINDS = {"one_sample_t", "paired_t", "welch_t", "sign_test", "chi_square_gof"}
_SUPPORTED_ALTERNATIVES = {"two_sided", "less", "greater"}
_SUPPORTED_BACKENDS = {"mpmath", "scipy"}
_SUPPORTED_SIGN_MODES = {"one_sample"}

_PAYLOAD_KEYS = {
    "schema",
    "workflow_mode",
    "test_kind",
    "alternative",
    "alpha",
    "backend",
    "backend_version",
    "precision_used",
    "inputs",
    "result",
    "diagnostics",
    "analysis_rows",
    "units",
}
_INPUT_KEYS = {
    "value_columns",
    "source_row_ids",
    "source_row_ids_b",
    "null_parameters",
    "sign_mode",
    "expected_source",
    "fitted_parameter_count",
}
_RESULT_KEYS = {
    "statistic_name",
    "statistic",
    "degrees_of_freedom",
    "p_value",
    "reject_null",
    "effect_rows",
    "sample_size",
    "sample_size_a",
    "sample_size_b",
    "category_count",
    "total_observed",
    "expected_source",
    "probability_normalized",
    "fitted_parameter_count",
    "positive_count",
    "negative_count",
    "tie_count",
    "effective_n",
}
_EFFECT_ROW_KEYS = {"key", "value", "note"}
_DIAGNOSTIC_KEYS = {"code", "severity", "message"}
_DIAGNOSTIC_SEVERITIES = {"info", "warning", "error"}


@dataclass(frozen=True)
class _HypothesisOptions:
    test_kind: str
    alternative: str
    alpha: mp.mpf
    alpha_text: str
    null_parameter_key: str
    null_parameter_value: mp.mpf
    null_parameter_text: str
    sign_mode: str | None = None
    fitted_parameter_count: int = 0


def run_statistics_hypothesis(
    *,
    values: Sequence[mp.mpf],
    source_row_ids: Sequence[str | int] | None,
    precision_digits: int,
    inputs: Mapping[str, Any],
    value_column: str = "",
) -> dict[str, Any]:
    """Run hidden-core hypothesis tests for the statistics workflow."""

    options = _normalize_options(inputs)
    value_list = [mp.mpf(value) for value in values]
    if not value_list:
        raise ValueError(_dual_msg("假设检验数值至少需要包含一个值。", "hypothesis test values must contain at least one value."))
    if any(not mp.isfinite(value) for value in value_list):
        raise ValueError(_dual_msg("假设检验数值必须是有限值。", "hypothesis test values must be finite."))

    with precision_guard(precision_digits) as precision_used:
        if options.test_kind == "one_sample_t":
            payload = _one_sample_t_payload(
                values=value_list,
                options=options,
                precision_digits=precision_used,
                source_row_ids=source_row_ids,
                value_column=value_column,
            )
        elif options.test_kind == "paired_t":
            payload = _paired_t_payload(
                values=value_list,
                paired_values=_parse_mpf_sequence(inputs.get("paired_values"), field_name="paired_values"),
                source_row_ids_a=source_row_ids,
                source_row_ids_b=_parse_optional_source_row_ids(
                    inputs.get("source_row_ids_b"),
                    field_name="source_row_ids_b",
                ),
                options=options,
                precision_digits=precision_used,
                value_column_a=value_column,
                value_column_b=_string_option(
                    inputs.get("value_column_b", inputs.get("value_col_b")),
                    default="B",
                    field_name="value_column_b",
                ),
            )
        elif options.test_kind == "welch_t":
            payload = _welch_t_payload(
                values_a=value_list,
                values_b=_parse_mpf_sequence(inputs.get("values_b"), field_name="values_b"),
                source_row_ids_a=source_row_ids,
                source_row_ids_b=_parse_optional_source_row_ids(
                    inputs.get("source_row_ids_b"),
                    field_name="source_row_ids_b",
                ),
                options=options,
                precision_digits=precision_used,
                value_column_a=value_column,
                value_column_b=_string_option(
                    inputs.get("value_column_b", inputs.get("value_col_b")),
                    default="B",
                    field_name="value_column_b",
                ),
            )
        elif options.test_kind == "sign_test":
            payload = _sign_test_payload(
                values=value_list,
                options=options,
                precision_digits=precision_used,
                source_row_ids=source_row_ids,
                value_column=value_column,
            )
        elif options.test_kind == "chi_square_gof":
            payload = _chi_square_gof_payload(
                observed=values,
                expected_counts=_parse_optional_mpf_sequence(
                    inputs.get("expected_counts"),
                    field_name="expected_counts",
                ),
                expected_probabilities=_parse_optional_mpf_sequence(
                    inputs.get("expected_probabilities"),
                    field_name="expected_probabilities",
                ),
                options=options,
                precision_digits=precision_used,
                source_row_ids=source_row_ids,
                observed_column=value_column,
                expected_column=_string_option(
                    inputs.get("expected_column"),
                    default="expected",
                    field_name="expected_column",
                ),
            )
        else:  # Defensive guard; _normalize_options rejects this path.
            raise ValueError(_dual_msg(f"不支持的假设检验类型：{options.test_kind}。", f"Unsupported hypothesis test kind: {options.test_kind}."))

    payload["analysis_rows"] = analysis_rows_to_json(
        statistics_hypothesis_analysis_rows_from_payload(payload)
    )
    validate_statistics_hypothesis_payload(payload)
    normalized = normalize_json_payload(payload, path="statistics_hypothesis_payload")
    if not isinstance(normalized, Mapping):
        raise TypeError(_dual_msg("统计假设检验载荷必须归一化为一个映射。", "statistics hypothesis payload must normalize to a mapping."))
    return dict(normalized)


def validate_statistics_hypothesis_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypeError(_dual_msg("假设检验载荷必须是一个映射。", "hypothesis payload must be a mapping."))
    _reject_json_floats(payload, path="hypothesis_payload")
    _reject_unknown_keys(payload, _PAYLOAD_KEYS, path="hypothesis_payload")
    if "units" in payload:
        normalize_display_only_family_units(payload.get("units"), family="statistics")

    if payload.get("schema") != HYPOTHESIS_PAYLOAD_SCHEMA:
        raise ValueError(_dual_msg("假设检验载荷的 schema 不受支持。", "hypothesis payload schema is unsupported."))
    if payload.get("workflow_mode") != HYPOTHESIS_WORKFLOW_MODE:
        raise ValueError(_dual_msg("假设检验载荷的 workflow_mode 不受支持。", "hypothesis payload workflow_mode is unsupported."))
    test_kind = _choice(payload.get("test_kind"), _SUPPORTED_TEST_KINDS, "test_kind")
    _choice(payload.get("alternative"), _SUPPORTED_ALTERNATIVES, "alternative")
    alpha = _finite_numeric_string(payload.get("alpha"), field_name="alpha")
    if not (mp.mpf("0") < alpha < mp.mpf("1")):
        raise ValueError(_dual_msg("alpha 必须在 (0, 1) 区间内。", "alpha must be in (0, 1)."))
    backend = _choice(payload.get("backend"), _SUPPORTED_BACKENDS, "backend")
    if "backend_version" in payload:
        _optional_text(payload.get("backend_version"), "backend_version")
    precision_used = _positive_int(payload.get("precision_used"), field_name="precision_used")
    if backend == "scipy" and precision_used > 16:
        raise ValueError(_dual_msg("仅当 precision_used <= 16 时才允许使用 scipy 后端。", "scipy backend is allowed only when precision_used <= 16."))
    if test_kind == "sign_test" and backend != "mpmath":
        raise ValueError(_dual_msg("sign_test 载荷必须使用 mpmath 后端。", "sign_test payloads must use the mpmath backend."))

    inputs = _required_mapping(payload.get("inputs"), "inputs")
    _reject_unknown_keys(inputs, _INPUT_KEYS, path="hypothesis_payload.inputs")
    value_columns = _required_text_sequence(inputs.get("value_columns"), "inputs.value_columns")
    if test_kind in {"one_sample_t", "sign_test"} and len(value_columns) != 1:
        raise ValueError(_dual_msg(f"{test_kind} 需要且仅需要一个数值列。", f"{test_kind} requires exactly one value column."))
    if test_kind in {"paired_t", "welch_t"} and len(value_columns) != 2:
        raise ValueError(_dual_msg(f"{test_kind} 需要且仅需要两个数值列。", f"{test_kind} requires exactly two value columns."))
    if test_kind == "chi_square_gof" and not (1 <= len(value_columns) <= 2):
        raise ValueError(_dual_msg("chi_square_gof 需要一个观测列和一个可选的期望列。", "chi_square_gof requires one observed column and optional expected column."))
    if test_kind == "sign_test" and len(value_columns) != 1:
        raise ValueError(_dual_msg("单样本 sign_test 需要且仅需要一个数值列。", "one-sample sign_test requires exactly one value column."))
    source_row_ids = _source_row_ids(inputs.get("source_row_ids"), field_name="inputs.source_row_ids")
    source_row_ids_b: tuple[str | int, ...] = ()
    if "source_row_ids_b" in inputs:
        if test_kind not in {"paired_t", "welch_t"}:
            raise ValueError(_dual_msg("source_row_ids_b 仅支持 paired_t 和 welch_t。", "source_row_ids_b is supported only for paired_t and welch_t."))
        source_row_ids_b = _source_row_ids(inputs.get("source_row_ids_b"), field_name="inputs.source_row_ids_b")
    null_parameters = _required_mapping(inputs.get("null_parameters"), "inputs.null_parameters")
    for key, value in null_parameters.items():
        _required_text(key, "inputs.null_parameters.<key>")
        _finite_numeric_string(value, field_name=f"inputs.null_parameters.{key}")
    if test_kind == "one_sample_t" and set(null_parameters) != {"mu0"}:
        raise ValueError(_dual_msg("one_sample_t 需要原假设参数 mu0。", "one_sample_t requires null parameter mu0."))
    if test_kind in {"paired_t", "welch_t"} and set(null_parameters) != {"delta0"}:
        raise ValueError(_dual_msg(f"{test_kind} 需要原假设参数 delta0。", f"{test_kind} requires null parameter delta0."))
    if test_kind == "sign_test":
        if inputs.get("sign_mode") != "one_sample":
            raise ValueError(_dual_msg("sign_test 的第一个分片仅支持 sign_mode='one_sample'。", "sign_test first slice supports only sign_mode='one_sample'."))
        if set(null_parameters) != {"m0"}:
            raise ValueError(_dual_msg("sign_test 需要原假设参数 m0。", "sign_test requires null parameter m0."))
    elif "sign_mode" in inputs:
        raise ValueError(_dual_msg("sign_mode 仅支持 sign_test。", "sign_mode is supported only for sign_test."))
    if test_kind == "chi_square_gof" and set(null_parameters) != set():
        raise ValueError(_dual_msg("chi_square_gof 不接受原假设参数。", "chi_square_gof does not accept null parameters."))
    if test_kind != "chi_square_gof" and (
        "expected_source" in inputs or "fitted_parameter_count" in inputs
    ):
        raise ValueError(_dual_msg("expected_source 和 fitted_parameter_count 仅支持 chi_square_gof。", "expected_source and fitted_parameter_count are supported only for chi_square_gof."))
    if test_kind == "chi_square_gof":
        if "expected_source" not in inputs:
            raise ValueError(_dual_msg("chi_square_gof 输入需要 expected_source。", "chi_square_gof inputs require expected_source."))
        if "fitted_parameter_count" not in inputs:
            raise ValueError(_dual_msg("chi_square_gof 输入需要 fitted_parameter_count。", "chi_square_gof inputs require fitted_parameter_count."))
    if "fitted_parameter_count" in inputs:
        _nonnegative_int(inputs.get("fitted_parameter_count"), field_name="inputs.fitted_parameter_count")
    if "expected_source" in inputs:
        _choice(inputs.get("expected_source"), {"counts", "probabilities"}, "inputs.expected_source")

    result = _required_mapping(payload.get("result"), "result")
    _reject_unknown_keys(result, _RESULT_KEYS, path="hypothesis_payload.result")
    statistic_name = _required_text(result.get("statistic_name"), "result.statistic_name")
    if test_kind == "one_sample_t" and statistic_name != "t":
        raise ValueError(_dual_msg("one_sample_t 的 statistic_name 必须为 't'。", "one_sample_t statistic_name must be 't'."))
    if test_kind in {"paired_t", "welch_t"} and statistic_name != "t":
        raise ValueError(_dual_msg(f"{test_kind} 的 statistic_name 必须为 't'。", f"{test_kind} statistic_name must be 't'."))
    if test_kind == "sign_test" and statistic_name != "positive_count":
        raise ValueError(_dual_msg("sign_test 的 statistic_name 必须为 'positive_count'。", "sign_test statistic_name must be 'positive_count'."))
    if test_kind == "chi_square_gof" and statistic_name != "chi_square":
        raise ValueError(_dual_msg("chi_square_gof 的 statistic_name 必须为 'chi_square'。", "chi_square_gof statistic_name must be 'chi_square'."))
    if test_kind != "welch_t" and ("sample_size_a" in result or "sample_size_b" in result):
        raise ValueError(_dual_msg("sample_size_a/sample_size_b 仅支持 welch_t。", "sample_size_a/sample_size_b are supported only for welch_t."))
    if test_kind != "sign_test" and any(
        key in result for key in ("positive_count", "negative_count", "tie_count", "effective_n")
    ):
        raise ValueError(_dual_msg("符号计数字段仅支持 sign_test。", "sign count fields are supported only for sign_test."))
    if test_kind != "chi_square_gof" and any(
        key in result
        for key in (
            "category_count",
            "total_observed",
            "expected_source",
            "probability_normalized",
            "fitted_parameter_count",
        )
    ):
        raise ValueError(_dual_msg("卡方结果字段仅支持 chi_square_gof。", "chi-square result fields are supported only for chi_square_gof."))
    _finite_numeric_string(result.get("statistic"), field_name="result.statistic")
    if "degrees_of_freedom" in result:
        df = _finite_numeric_string(result.get("degrees_of_freedom"), field_name="result.degrees_of_freedom")
        if df <= 0:
            raise ValueError(_dual_msg("degrees_of_freedom 必须大于 0。", "degrees_of_freedom must be > 0."))
    p_value_raw = result.get("p_value")
    if p_value_raw is not None:
        p_value = _finite_numeric_string(p_value_raw, field_name="result.p_value")
        if not (mp.mpf("0") <= p_value <= mp.mpf("1")):
            raise ValueError(_dual_msg("p_value 必须在 [0, 1] 区间内。", "p_value must be in [0, 1]."))
        if "reject_null" in result and not isinstance(result.get("reject_null"), bool):
            raise TypeError(_dual_msg("存在 result.reject_null 时它必须是布尔值。", "result.reject_null must be a boolean when present."))
    elif "reject_null" in result:
        raise ValueError(_dual_msg("当 p_value 不可用时必须省略 reject_null。", "reject_null must be omitted when p_value is unavailable."))
    sample_size = _nonnegative_int(result.get("sample_size"), field_name="result.sample_size")
    if len(source_row_ids) != sample_size:
        raise ValueError(_dual_msg("inputs.source_row_ids 的长度必须与 result.sample_size 匹配。", "inputs.source_row_ids length must match result.sample_size."))
    if "sample_size_a" in result:
        _nonnegative_int(result.get("sample_size_a"), field_name="result.sample_size_a")
    if "sample_size_b" in result:
        sample_size_b = _nonnegative_int(result.get("sample_size_b"), field_name="result.sample_size_b")
        if len(source_row_ids_b) != sample_size_b:
            raise ValueError(_dual_msg("inputs.source_row_ids_b 的长度必须与 result.sample_size_b 匹配。", "inputs.source_row_ids_b length must match result.sample_size_b."))
    if test_kind == "paired_t":
        if not source_row_ids_b:
            raise ValueError(_dual_msg("paired_t 输入需要 source_row_ids_b。", "paired_t inputs require source_row_ids_b."))
        if source_row_ids_b != source_row_ids:
            raise ValueError(_dual_msg("paired_t 的 source_row_ids_b 必须与 source_row_ids 完全匹配。", "paired_t source_row_ids_b must exactly match source_row_ids."))
    if "category_count" in result:
        _nonnegative_int(result.get("category_count"), field_name="result.category_count")
    if "total_observed" in result:
        total_observed = _finite_numeric_string(result.get("total_observed"), field_name="result.total_observed")
        if total_observed <= 0:
            raise ValueError(_dual_msg("result.total_observed 必须大于 0。", "result.total_observed must be > 0."))
    if "expected_source" in result:
        _choice(result.get("expected_source"), {"counts", "probabilities"}, "result.expected_source")
    if "probability_normalized" in result and not isinstance(result.get("probability_normalized"), bool):
        raise TypeError(_dual_msg("result.probability_normalized 必须是布尔值。", "result.probability_normalized must be a boolean."))
    if "fitted_parameter_count" in result:
        _nonnegative_int(result.get("fitted_parameter_count"), field_name="result.fitted_parameter_count")
    for count_field in ("positive_count", "negative_count", "tie_count", "effective_n"):
        if count_field in result:
            _nonnegative_int(result.get(count_field), field_name=f"result.{count_field}")
    if test_kind == "sign_test":
        for count_field in ("positive_count", "negative_count", "tie_count", "effective_n"):
            if count_field not in result:
                raise ValueError(_dual_msg(f"sign_test 结果需要 {count_field}。", f"sign_test result requires {count_field}."))
        if int(result["effective_n"]) <= 0:
            raise ValueError(_dual_msg("sign_test 的 effective_n 必须为正。", "sign_test effective_n must be positive."))
        if (
            int(result["positive_count"])
            + int(result["negative_count"])
            + int(result["tie_count"])
            != sample_size
        ):
            raise ValueError(_dual_msg("sign_test 各计数之和必须等于 result.sample_size。", "sign_test counts must add up to result.sample_size."))
        if int(result["positive_count"]) + int(result["negative_count"]) != int(result["effective_n"]):
            raise ValueError(_dual_msg("sign_test 的 effective_n 必须等于 positive_count + negative_count。", "sign_test effective_n must equal positive_count + negative_count."))
    if test_kind in {"one_sample_t", "paired_t"}:
        if sample_size < 2:
            raise ValueError(_dual_msg(f"{test_kind} 的 result.sample_size 必须至少为 2。", f"{test_kind} result.sample_size must be at least 2."))
        df_raw = result.get("degrees_of_freedom")
        if df_raw is None:
            raise ValueError(_dual_msg(f"{test_kind} 结果需要 degrees_of_freedom。", f"{test_kind} result requires degrees_of_freedom."))
        df = _finite_numeric_string(df_raw, field_name="result.degrees_of_freedom")
        if df != sample_size - 1:
            raise ValueError(_dual_msg(f"{test_kind} 的 degrees_of_freedom 必须等于 sample_size - 1。", f"{test_kind} degrees_of_freedom must equal sample_size - 1."))
    if test_kind == "welch_t":
        sample_size_a = _nonnegative_int(result.get("sample_size_a"), field_name="result.sample_size_a")
        sample_size_b = _nonnegative_int(result.get("sample_size_b"), field_name="result.sample_size_b")
        if sample_size_a < 2 or sample_size_b < 2:
            raise ValueError(_dual_msg("welch_t 的两个样本量都必须至少为 2。", "welch_t sample sizes must both be at least 2."))
        if sample_size != sample_size_a:
            raise ValueError(_dual_msg("welch_t 的 result.sample_size 必须等于 sample_size_a。", "welch_t result.sample_size must equal sample_size_a."))
        df_raw = result.get("degrees_of_freedom")
        if df_raw is None or _finite_numeric_string(df_raw, field_name="result.degrees_of_freedom") <= 0:
            raise ValueError(_dual_msg("welch_t 需要正的 degrees_of_freedom。", "welch_t requires positive degrees_of_freedom."))
    if test_kind == "chi_square_gof":
        if result.get("expected_source") != inputs.get("expected_source"):
            raise ValueError(_dual_msg("chi_square_gof 结果的 expected_source 必须与 inputs 匹配。", "chi_square_gof result expected_source must match inputs."))
        if result.get("fitted_parameter_count") != inputs.get("fitted_parameter_count"):
            raise ValueError(_dual_msg("chi_square_gof 结果的 fitted_parameter_count 必须与 inputs 匹配。", "chi_square_gof result fitted_parameter_count must match inputs."))
        category_count = _nonnegative_int(result.get("category_count"), field_name="result.category_count")
        fitted_parameter_count = _nonnegative_int(
            result.get("fitted_parameter_count"),
            field_name="result.fitted_parameter_count",
        )
        if category_count < 2:
            raise ValueError(_dual_msg("chi_square_gof 的 category_count 必须至少为 2。", "chi_square_gof category_count must be at least 2."))
        if sample_size != category_count:
            raise ValueError(_dual_msg("chi_square_gof 的 result.sample_size 必须等于 category_count。", "chi_square_gof result.sample_size must equal category_count."))
        df_raw = result.get("degrees_of_freedom")
        if df_raw is None:
            raise ValueError(_dual_msg("chi_square_gof 结果需要 degrees_of_freedom。", "chi_square_gof result requires degrees_of_freedom."))
        df = _finite_numeric_string(df_raw, field_name="result.degrees_of_freedom")
        if df != category_count - 1 - fitted_parameter_count or df <= 0:
            raise ValueError(_dual_msg("chi_square_gof 的 degrees_of_freedom 必须等于 category_count - 1 - fitted_parameter_count 且大于 0。", "chi_square_gof degrees_of_freedom must equal category_count - 1 - fitted_parameter_count and be > 0."))
    _effect_rows(result.get("effect_rows"), field_name="result.effect_rows")
    _diagnostics(payload.get("diagnostics"), field_name="diagnostics")
    if "analysis_rows" in payload:
        analysis_rows_from_json(payload.get("analysis_rows"))


def statistics_hypothesis_analysis_rows_from_payload(payload: Mapping[str, Any]) -> tuple[AnalysisRow, ...]:
    validate_statistics_hypothesis_payload({key: value for key, value in payload.items() if key != "analysis_rows"})
    test_kind = str(payload["test_kind"])
    result = _required_mapping(payload.get("result"), "result")
    rows: list[AnalysisRow] = [
        AnalysisRow(
            key="test_kind",
            label_key="statistics.hypothesis.test_kind",
            value=test_kind,
            method=test_kind,
            render_group="diagnostic",
        ),
        AnalysisRow(
            key="alpha",
            label_key="statistics.hypothesis.alpha",
            value=str(payload["alpha"]),
            method=test_kind,
        ),
    ]
    for key, label_key in (
        ("statistic", "statistics.hypothesis.statistic"),
        ("degrees_of_freedom", "statistics.hypothesis.degrees_of_freedom"),
        ("p_value", "statistics.hypothesis.p_value"),
    ):
        value = result.get(key)
        if value is not None:
            rows.append(AnalysisRow(key=key, label_key=label_key, value=str(value), method=test_kind))
    if "reject_null" in result:
        rows.append(
            AnalysisRow(
                key="reject_null",
                label_key="statistics.hypothesis.reject_null",
                value="true" if result.get("reject_null") else "false",
                method=test_kind,
            )
        )
    effect_rows = result.get("effect_rows")
    if isinstance(effect_rows, Sequence) and not isinstance(effect_rows, (str, bytes, bytearray, memoryview)):
        for row in effect_rows:
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("key") or "")
            value = row.get("value")
            if key and value is not None:
                rows.append(
                    AnalysisRow(
                        key=f"effect.{key}",
                        label_key=f"statistics.hypothesis.effect.{key}",
                        value=int(value) if isinstance(value, int) else str(value),
                        method=test_kind,
                    )
                )
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview)):
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, Mapping):
                continue
            code = str(diagnostic.get("code") or "diagnostic")
            message = str(diagnostic.get("message") or code)
            severity = str(diagnostic.get("severity") or "info")
            if severity not in _DIAGNOSTIC_SEVERITIES:
                severity = "info"
            rows.append(
                AnalysisRow(
                    key=f"diagnostic.{code}",
                    label_key="statistics.hypothesis.diagnostic",
                    value=message,
                    method=test_kind,
                    severity=severity,
                    message_key=f"statistics.hypothesis.{code}",
                    render_group="diagnostic",
                )
            )
    return tuple(rows)


def render_statistics_hypothesis_payload_outputs(
    payload: Mapping[str, Any],
    *,
    units: Mapping[str, Any] | None = None,
) -> tuple[str, list[dict[str, object]], list[str]]:
    """Regenerate deterministic text and CSV from an authoritative hypothesis payload."""

    validate_statistics_hypothesis_payload(payload)
    test_kind = str(payload["test_kind"])
    alternative = str(payload["alternative"])
    result = _required_mapping(payload.get("result"), "result")
    inputs = _required_mapping(payload.get("inputs"), "inputs")
    null_parameters = _required_mapping(inputs.get("null_parameters"), "inputs.null_parameters")

    header_lines = [
        "=== Hypothesis Test ===",
        f"Test: {test_kind}",
        f"Alternative: {alternative}",
        f"Alpha: {payload['alpha']}",
        f"Backend: {payload['backend']}",
    ]
    value_columns = inputs.get("value_columns")
    if isinstance(value_columns, Sequence) and not isinstance(value_columns, (str, bytes, bytearray, memoryview)):
        header_lines.append(f"Columns: {', '.join(str(column) for column in value_columns)}")
    if null_parameters:
        header_lines.append(
            "Null parameters: "
            + ", ".join(f"{key}={value}" for key, value in sorted(null_parameters.items()))
        )

    records: list[dict[str, object]] = []

    def append_row(metric: str, value: object, note: str = "") -> None:
        text_value = _result_value_text(value)
        unit = _hypothesis_output_unit(units, metric)
        records.append(
            {
                "test": test_kind,
                "metric": metric,
                "value": text_value,
                "uncertainty": "",
                "note": note,
                "value_unit": unit,
            }
        )

    append_row("statistic_name", result.get("statistic_name", ""))
    append_row("statistic", result.get("statistic", ""))
    if result.get("degrees_of_freedom") is not None:
        append_row("degrees_of_freedom", result.get("degrees_of_freedom", ""))
    append_row("p_value", result.get("p_value", ""))
    append_row("alpha", payload.get("alpha", ""))
    if "reject_null" in result:
        append_row("reject_null", "true" if result.get("reject_null") else "false")

    effect_rows = result.get("effect_rows")
    if isinstance(effect_rows, Sequence) and not isinstance(effect_rows, (str, bytes, bytearray, memoryview)):
        for row in effect_rows:
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("key") or "")
            if not key:
                continue
            append_row(f"effect.{key}", row.get("value", ""), str(row.get("note") or ""))

    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, Sequence) and not isinstance(diagnostics, (str, bytes, bytearray, memoryview)):
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, Mapping):
                continue
            code = str(diagnostic.get("code") or "diagnostic")
            severity = str(diagnostic.get("severity") or "")
            message = str(diagnostic.get("message") or "")
            append_row(f"diagnostic.{code}", message, severity)

    include_units = any(str(row.get("value_unit") or "") for row in records)
    lines = list(header_lines)
    if include_units:
        lines.extend(["", "Metric | Value | Unit | Note", "--- | --- | --- | ---"])
    else:
        lines.extend(["", "Metric | Value | Note", "--- | --- | ---"])
    csv_rows: list[dict[str, object]] = []
    for row in records:
        metric = str(row["metric"])
        value = str(row["value"])
        note = str(row.get("note") or "")
        if include_units:
            unit = str(row.get("value_unit") or "")
            lines.append(f"{metric} | {value} | {unit} | {note}")
            csv_rows.append(dict(row))
        else:
            lines.append(f"{metric} | {value} | {note}")
            csv_rows.append({key: value for key, value in row.items() if key != "value_unit"})
    headers = ["test", "metric", "value", "uncertainty", "note"]
    if include_units:
        headers.append("value_unit")
    return "\n".join(lines), csv_rows, headers


def _hypothesis_output_unit(units: Mapping[str, Any] | None, metric: str) -> str:
    if units is None:
        return ""
    if metric == "statistic":
        return first_unit_annotation_text(units, "outputs", ("statistic", "result"))
    if metric.startswith("effect."):
        effect_key = metric.split(".", 1)[1]
        return first_unit_annotation_text(units, "outputs", (metric, effect_key, "result"))
    return ""


def validate_statistics_hypothesis_snapshot(snapshot: Mapping[str, Any]) -> None:
    if not isinstance(snapshot, Mapping):
        raise TypeError(_dual_msg("统计假设检验快照必须是一个映射。", "statistics hypothesis snapshot must be a mapping."))
    _reject_json_floats(snapshot, path="statistics_hypothesis_snapshot")
    if snapshot.get("schema") != _STATISTICS_RESULT_SNAPSHOT_SCHEMA:
        raise ValueError(_dual_msg("统计假设检验快照的 schema 不受支持。", "statistics hypothesis snapshot schema is unsupported."))
    if snapshot.get("schema_version") != _STATISTICS_RESULT_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(_dual_msg("统计假设检验快照的 schema_version 不受支持。", "statistics hypothesis snapshot schema_version is unsupported."))
    if snapshot.get("family") != "statistics":
        raise ValueError(_dual_msg("统计假设检验快照的 family 必须为 statistics。", "statistics hypothesis snapshot family must be statistics."))
    if snapshot.get("mode") != HYPOTHESIS_WORKFLOW_MODE:
        raise ValueError(_dual_msg("统计假设检验快照的 mode 不受支持。", "statistics hypothesis snapshot mode is unsupported."))
    payload = snapshot.get("hypothesis_test")
    if not isinstance(payload, Mapping):
        raise TypeError(_dual_msg("统计假设检验快照需要一个 hypothesis_test 载荷。", "statistics hypothesis snapshot requires a hypothesis_test payload."))
    validate_statistics_hypothesis_payload(payload)
    source = snapshot.get("source")
    if not isinstance(source, Mapping):
        raise TypeError(_dual_msg("统计假设检验快照的 source 必须是一个映射。", "statistics hypothesis snapshot source must be a mapping."))
    if source.get("test_kind") != payload.get("test_kind"):
        raise ValueError(_dual_msg("统计假设检验快照 source 的 test_kind 与载荷不匹配。", "statistics hypothesis snapshot source test_kind does not match payload."))
    if source.get("alternative") != payload.get("alternative"):
        raise ValueError(_dual_msg("统计假设检验快照 source 的 alternative 与载荷不匹配。", "statistics hypothesis snapshot source alternative does not match payload."))
    if source.get("alpha") != payload.get("alpha"):
        raise ValueError(_dual_msg("统计假设检验快照 source 的 alpha 与载荷不匹配。", "statistics hypothesis snapshot source alpha does not match payload."))
    if source.get("backend") != payload.get("backend"):
        raise ValueError(_dual_msg("统计假设检验快照 source 的 backend 与载荷不匹配。", "statistics hypothesis snapshot source backend does not match payload."))
    _validate_statistics_hypothesis_snapshot_source(source, payload)


def _validate_statistics_hypothesis_snapshot_source(
    source: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    inputs = _required_mapping(payload.get("inputs"), "hypothesis_test.inputs")
    result = _required_mapping(payload.get("result"), "hypothesis_test.result")
    payload_value_columns = _required_text_sequence(
        inputs.get("value_columns"),
        "hypothesis_test.inputs.value_columns",
    )
    source_value_columns = _required_text_sequence(
        source.get("value_columns"),
        "statistics_hypothesis_snapshot.source.value_columns",
    )
    if source_value_columns != payload_value_columns:
        raise ValueError(_dual_msg("统计假设检验快照 source 的 value_columns 与载荷不匹配。", "statistics hypothesis snapshot source value_columns do not match payload."))

    payload_row_ids = _source_row_ids(
        inputs.get("source_row_ids"),
        field_name="hypothesis_test.inputs.source_row_ids",
    )
    source_row_ids = _source_row_ids(
        source.get("source_row_ids"),
        field_name="statistics_hypothesis_snapshot.source.source_row_ids",
    )
    if source_row_ids != payload_row_ids:
        raise ValueError(_dual_msg("统计假设检验快照的 source_row_ids 与载荷不匹配。", "statistics hypothesis snapshot source_row_ids do not match payload."))

    row_count = _nonnegative_int(
        source.get("row_count"),
        field_name="statistics_hypothesis_snapshot.source.row_count",
    )
    sample_size = _nonnegative_int(
        result.get("sample_size"),
        field_name="hypothesis_test.result.sample_size",
    )
    if row_count != sample_size:
        raise ValueError(_dual_msg("统计假设检验快照 source 的 row_count 与载荷不匹配。", "statistics hypothesis snapshot source row_count does not match payload."))

    if "source_row_ids_b" in inputs:
        payload_row_ids_b = _source_row_ids(
            inputs.get("source_row_ids_b"),
            field_name="hypothesis_test.inputs.source_row_ids_b",
        )
        source_row_ids_b = _source_row_ids(
            source.get("source_row_ids_b"),
            field_name="statistics_hypothesis_snapshot.source.source_row_ids_b",
        )
        if source_row_ids_b != payload_row_ids_b:
            raise ValueError(_dual_msg("统计假设检验快照的 source_row_ids_b 与载荷不匹配。", "statistics hypothesis snapshot source_row_ids_b do not match payload."))
    elif "source_row_ids_b" in source:
        raise ValueError(_dual_msg("统计假设检验快照中不应出现 source_row_ids_b。", "statistics hypothesis snapshot source_row_ids_b must not be present."))


def _one_sample_t_payload(
    *,
    values: Sequence[mp.mpf],
    options: _HypothesisOptions,
    precision_digits: int,
    source_row_ids: Sequence[str | int] | None,
    value_column: str,
) -> dict[str, Any]:
    n = len(values)
    if n < 2:
        raise ValueError(_dual_msg("one_sample_t 至少需要两个值。", "one_sample_t requires at least two values."))
    mean = mp.fsum(values) / n
    centered = [value - mean for value in values]
    variance = mp.fsum([value * value for value in centered]) / (n - 1)
    if not (variance > 0) or not mp.isfinite(variance):
        raise ValueError(_dual_msg("one_sample_t 需要一个正的有限样本方差。", "one_sample_t requires a positive finite sample variance."))
    std = mp.sqrt(variance)
    standard_error = std / mp.sqrt(n)
    if not (standard_error > 0) or not mp.isfinite(standard_error):
        raise ValueError(_dual_msg("one_sample_t 需要一个正的有限标准误。", "one_sample_t requires a positive finite standard error."))
    mean_difference = mean - options.null_parameter_value
    statistic = mean_difference / standard_error
    df = mp.mpf(n - 1)
    p_value, backend, backend_version = _student_t_p_value(
        statistic,
        df,
        options.alternative,
        precision_digits=precision_digits,
    )
    return _payload(
        test_kind="one_sample_t",
        alternative=options.alternative,
        alpha=options.alpha,
        alpha_text=options.alpha_text,
        backend=backend,
        backend_version=backend_version,
        precision_digits=precision_digits,
        value_columns=(value_column or "value",),
        source_row_ids=source_row_ids,
        null_parameters={options.null_parameter_key: options.null_parameter_text},
        result={
            "statistic_name": "t",
            "statistic": _format_mpf(statistic, precision_digits),
            "degrees_of_freedom": _format_mpf(df, precision_digits),
            "p_value": _format_mpf(p_value, precision_digits),
            "reject_null": p_value <= options.alpha,
            "sample_size": n,
            "effect_rows": [
                {"key": "mean", "value": _format_mpf(mean, precision_digits)},
                {"key": "mean_difference", "value": _format_mpf(mean_difference, precision_digits)},
                {"key": "standard_error", "value": _format_mpf(standard_error, precision_digits)},
                {"key": "sample_standard_deviation", "value": _format_mpf(std, precision_digits)},
            ],
        },
        diagnostics=[],
    )


def _sign_test_payload(
    *,
    values: Sequence[mp.mpf],
    options: _HypothesisOptions,
    precision_digits: int,
    source_row_ids: Sequence[str | int] | None,
    value_column: str,
) -> dict[str, Any]:
    if options.sign_mode != "one_sample":
        raise ValueError(_dual_msg("sign_test 的第一个分片仅支持 one_sample 模式。", "sign_test first slice supports only one_sample mode."))
    positive_count = 0
    negative_count = 0
    tie_count = 0
    for value in values:
        delta = value - options.null_parameter_value
        if delta > 0:
            positive_count += 1
        elif delta < 0:
            negative_count += 1
        else:
            tie_count += 1
    effective_n = positive_count + negative_count
    if effective_n == 0:
        raise ValueError(_dual_msg("sign_test 至少需要一个非并列值。", "sign_test requires at least one non-tied value."))
    p_value = _sign_test_p_value(positive_count, effective_n, options.alternative)
    diagnostics: list[dict[str, str]] = []
    if tie_count:
        diagnostics.append(
            {
                "code": "sign_test_ties_dropped",
                "severity": "info",
                "message": f"{tie_count} tied value(s) were dropped.",
            }
        )
    return _payload(
        test_kind="sign_test",
        alternative=options.alternative,
        alpha=options.alpha,
        alpha_text=options.alpha_text,
        backend="mpmath",
        backend_version=None,
        precision_digits=precision_digits,
        value_columns=(value_column or "value",),
        source_row_ids=source_row_ids,
        null_parameters={options.null_parameter_key: options.null_parameter_text},
        result={
            "statistic_name": "positive_count",
            "statistic": _format_mpf(positive_count, precision_digits),
            "p_value": _format_mpf(p_value, precision_digits),
            "reject_null": p_value <= options.alpha,
            "sample_size": len(values),
            "positive_count": positive_count,
            "negative_count": negative_count,
            "tie_count": tie_count,
            "effective_n": effective_n,
            "effect_rows": [
                {"key": "positive_count", "value": positive_count},
                {"key": "negative_count", "value": negative_count},
                {"key": "tie_count", "value": tie_count},
                {"key": "effective_n", "value": effective_n},
            ],
        },
        diagnostics=diagnostics,
        sign_mode=options.sign_mode,
    )


def _paired_t_payload(
    *,
    values: Sequence[mp.mpf],
    paired_values: Sequence[mp.mpf],
    source_row_ids_a: Sequence[str | int] | None,
    source_row_ids_b: Sequence[str | int] | None,
    options: _HypothesisOptions,
    precision_digits: int,
    value_column_a: str,
    value_column_b: str,
) -> dict[str, Any]:
    if len(values) != len(paired_values):
        raise ValueError(_dual_msg("paired_t 需要等长的配对数值。", "paired_t requires equal-length paired values."))
    normalized_source_row_ids_a = _default_source_row_ids(source_row_ids_a, count=len(values))
    normalized_source_row_ids_b = _default_source_row_ids(source_row_ids_b, count=len(paired_values))
    if normalized_source_row_ids_a != normalized_source_row_ids_b:
        raise ValueError(_dual_msg("paired_t 需要 source_row_ids 与 source_row_ids_b 完全一致。", "paired_t requires identical source_row_ids and source_row_ids_b."))
    differences = [mp.mpf(a) - mp.mpf(b) for a, b in zip(values, paired_values)]
    payload = _one_sample_t_like_payload(
        values=differences,
        options=options,
        precision_digits=precision_digits,
        source_row_ids=normalized_source_row_ids_a,
        value_columns=(value_column_a or "A", value_column_b or "B"),
        test_kind="paired_t",
        effect_prefix_rows=[
            {"key": "mean_a", "value": _format_mpf(mp.fsum(values) / len(values), precision_digits)},
            {
                "key": "mean_b",
                "value": _format_mpf(mp.fsum(paired_values) / len(paired_values), precision_digits),
            },
        ],
    )
    payload["inputs"]["source_row_ids_b"] = list(normalized_source_row_ids_b)
    return payload


def _welch_t_payload(
    *,
    values_a: Sequence[mp.mpf],
    values_b: Sequence[mp.mpf],
    source_row_ids_a: Sequence[str | int] | None,
    source_row_ids_b: Sequence[str | int] | None,
    options: _HypothesisOptions,
    precision_digits: int,
    value_column_a: str,
    value_column_b: str,
) -> dict[str, Any]:
    if len(values_a) < 2 or len(values_b) < 2:
        raise ValueError(_dual_msg("welch_t 每组至少需要两个值。", "welch_t requires at least two values per group."))
    mean_a, variance_a = _sample_mean_variance(values_a, field_name="values", require_positive=False)
    mean_b, variance_b = _sample_mean_variance(values_b, field_name="values_b", require_positive=False)
    se2_a = variance_a / len(values_a)
    se2_b = variance_b / len(values_b)
    se2 = se2_a + se2_b
    if not (se2 > 0) or not mp.isfinite(se2):
        raise ValueError(_dual_msg("welch_t 需要一个正的有限标准误。", "welch_t requires a positive finite standard error."))
    denominator = (se2_a * se2_a) / (len(values_a) - 1) + (se2_b * se2_b) / (len(values_b) - 1)
    if not (denominator > 0) or not mp.isfinite(denominator):
        raise ValueError(_dual_msg("welch_t 的自由度未定义。", "welch_t degrees of freedom are undefined."))
    df = (se2 * se2) / denominator
    effect = mean_a - mean_b - options.null_parameter_value
    statistic = effect / mp.sqrt(se2)
    p_value, backend, backend_version = _student_t_p_value(
        statistic,
        df,
        options.alternative,
        precision_digits=precision_digits,
    )
    payload = _payload(
        test_kind="welch_t",
        alternative=options.alternative,
        alpha=options.alpha,
        alpha_text=options.alpha_text,
        backend=backend,
        backend_version=backend_version,
        precision_digits=precision_digits,
        value_columns=(value_column_a or "A", value_column_b or "B"),
        source_row_ids=source_row_ids_a,
        null_parameters={options.null_parameter_key: options.null_parameter_text},
        result={
            "statistic_name": "t",
            "statistic": _format_mpf(statistic, precision_digits),
            "degrees_of_freedom": _format_mpf(df, precision_digits),
            "p_value": _format_mpf(p_value, precision_digits),
            "reject_null": p_value <= options.alpha,
            "sample_size": len(values_a),
            "sample_size_a": len(values_a),
            "sample_size_b": len(values_b),
            "effect_rows": [
                {"key": "mean_a", "value": _format_mpf(mean_a, precision_digits)},
                {"key": "mean_b", "value": _format_mpf(mean_b, precision_digits)},
                {"key": "mean_difference_minus_delta0", "value": _format_mpf(effect, precision_digits)},
                {"key": "standard_error", "value": _format_mpf(mp.sqrt(se2), precision_digits)},
                {"key": "sample_variance_a", "value": _format_mpf(variance_a, precision_digits)},
                {"key": "sample_variance_b", "value": _format_mpf(variance_b, precision_digits)},
                {"key": "sample_size_a", "value": len(values_a)},
                {"key": "sample_size_b", "value": len(values_b)},
            ],
        },
        diagnostics=[],
    )
    if source_row_ids_b is None:
        source_row_ids_b = tuple(str(index) for index in range(1, len(values_b) + 1))
    payload["inputs"]["source_row_ids_b"] = list(source_row_ids_b)
    return payload


def _chi_square_gof_payload(
    *,
    observed: Sequence[mp.mpf],
    expected_counts: Sequence[mp.mpf] | None,
    expected_probabilities: Sequence[mp.mpf] | None,
    options: _HypothesisOptions,
    precision_digits: int,
    source_row_ids: Sequence[str | int] | None,
    observed_column: str,
    expected_column: str,
) -> dict[str, Any]:
    if expected_counts is not None and expected_probabilities is not None:
        raise ValueError(_dual_msg("chi_square_gof 只接受 expected_counts 或 expected_probabilities 之一，不能同时提供。", "chi_square_gof accepts expected_counts or expected_probabilities, not both."))
    if expected_counts is None and expected_probabilities is None:
        raise ValueError(_dual_msg("chi_square_gof 需要 expected_counts 或 expected_probabilities。", "chi_square_gof requires expected_counts or expected_probabilities."))
    observed_values = [_validate_observed_count(value, index) for index, value in enumerate(observed)]
    if len(observed_values) < 2:
        raise ValueError(_dual_msg("chi_square_gof 至少需要两个类别。", "chi_square_gof requires at least two categories."))
    total_observed = mp.fsum(observed_values)
    if not (total_observed > 0):
        raise ValueError(_dual_msg("chi_square_gof 的观测总数必须大于 0。", "chi_square_gof observed total must be > 0."))

    probability_normalized = False
    if expected_probabilities is not None:
        if len(expected_probabilities) != len(observed_values):
            raise ValueError(_dual_msg("expected_probabilities 必须与观测类别数匹配。", "expected_probabilities must match observed category count."))
        probability_sum = mp.fsum(expected_probabilities)
        if not (mp.isfinite(probability_sum) and probability_sum > 0):
            raise ValueError(_dual_msg("期望概率之和必须为一个正的有限值。", "expected probabilities must sum to a positive finite value."))
        for index, probability in enumerate(expected_probabilities):
            if not (mp.isfinite(probability) and probability >= 0):
                raise ValueError(_dual_msg(f"expected_probabilities[{index}] 必须是有限且非负的。", f"expected_probabilities[{index}] must be finite and non-negative."))
        expected = [total_observed * mp.mpf(probability) / probability_sum for probability in expected_probabilities]
        expected_source = "probabilities"
        probability_normalized = probability_sum != 1
    else:
        assert expected_counts is not None
        if len(expected_counts) != len(observed_values):
            raise ValueError(_dual_msg("expected_counts 必须与观测类别数匹配。", "expected_counts must match observed category count."))
        expected = []
        for index, count in enumerate(expected_counts):
            if not (mp.isfinite(count) and count >= 0):
                raise ValueError(_dual_msg(f"expected_counts[{index}] 必须是有限且非负的。", f"expected_counts[{index}] must be finite and non-negative."))
            expected.append(mp.mpf(count))
        expected_total = mp.fsum(expected)
        if not _same_total(expected_total, total_observed, precision_digits):
            raise ValueError(_dual_msg("expected_counts 的总数必须与观测总数匹配。", "expected_counts total must match observed total."))
        expected_source = "counts"

    statistic_terms: list[mp.mpf] = []
    diagnostics: list[dict[str, str]] = []
    if any(expected_value < 5 for expected_value in expected):
        diagnostics.append(
            {
                "code": "chi_square_expected_count_lt_5",
                "severity": "warning",
                "message": "Some expected counts are below 5; chi-square approximation may be unreliable.",
            }
        )
    for index, (observed_value, expected_value) in enumerate(zip(observed_values, expected)):
        if expected_value == 0 and observed_value > 0:
            raise ValueError(_dual_msg(f"类别 {index} 处观测计数为正，但期望计数为零。", f"expected count is zero for positive observed count at category {index}."))
        if expected_value == 0:
            continue
        statistic_terms.append(((observed_value - expected_value) ** 2) / expected_value)
    statistic = mp.fsum(statistic_terms)
    df = len(observed_values) - 1 - options.fitted_parameter_count
    if df <= 0:
        raise ValueError(_dual_msg("chi_square_gof 的自由度必须大于 0。", "chi_square_gof degrees of freedom must be > 0."))
    p_value, backend, backend_version = _chi_square_p_value(
        statistic,
        mp.mpf(df),
        precision_digits=precision_digits,
    )
    payload = _payload(
        test_kind="chi_square_gof",
        alternative="greater",
        alpha=options.alpha,
        alpha_text=options.alpha_text,
        backend=backend,
        backend_version=backend_version,
        precision_digits=precision_digits,
        value_columns=(observed_column or "observed", expected_column or expected_source),
        source_row_ids=source_row_ids,
        null_parameters={},
        result={
            "statistic_name": "chi_square",
            "statistic": _format_mpf(statistic, precision_digits),
            "degrees_of_freedom": _format_mpf(df, precision_digits),
            "p_value": _format_mpf(p_value, precision_digits),
            "reject_null": p_value <= options.alpha,
            "sample_size": len(observed_values),
            "category_count": len(observed_values),
            "total_observed": _format_mpf(total_observed, precision_digits),
            "expected_source": expected_source,
            "probability_normalized": probability_normalized,
            "fitted_parameter_count": options.fitted_parameter_count,
            "effect_rows": [
                {"key": "category_count", "value": len(observed_values)},
                {"key": "total_observed", "value": _format_mpf(total_observed, precision_digits)},
                {"key": "fitted_parameter_count", "value": options.fitted_parameter_count},
            ],
        },
        diagnostics=diagnostics,
    )
    payload["inputs"]["expected_source"] = expected_source
    payload["inputs"]["fitted_parameter_count"] = options.fitted_parameter_count
    return payload


def _one_sample_t_like_payload(
    *,
    values: Sequence[mp.mpf],
    options: _HypothesisOptions,
    precision_digits: int,
    source_row_ids: Sequence[str | int] | None,
    value_columns: Sequence[str],
    test_kind: str,
    effect_prefix_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    n = len(values)
    if n < 2:
        raise ValueError(_dual_msg(f"{test_kind} 至少需要两个值。", f"{test_kind} requires at least two values."))
    mean, variance = _sample_mean_variance(values, field_name=test_kind)
    std = mp.sqrt(variance)
    standard_error = std / mp.sqrt(n)
    if not (standard_error > 0) or not mp.isfinite(standard_error):
        raise ValueError(_dual_msg(f"{test_kind} 需要一个正的有限标准误。", f"{test_kind} requires a positive finite standard error."))
    mean_difference = mean - options.null_parameter_value
    statistic = mean_difference / standard_error
    df = mp.mpf(n - 1)
    p_value, backend, backend_version = _student_t_p_value(
        statistic,
        df,
        options.alternative,
        precision_digits=precision_digits,
    )
    return _payload(
        test_kind=test_kind,
        alternative=options.alternative,
        alpha=options.alpha,
        alpha_text=options.alpha_text,
        backend=backend,
        backend_version=backend_version,
        precision_digits=precision_digits,
        value_columns=value_columns,
        source_row_ids=source_row_ids,
        null_parameters={options.null_parameter_key: options.null_parameter_text},
        result={
            "statistic_name": "t",
            "statistic": _format_mpf(statistic, precision_digits),
            "degrees_of_freedom": _format_mpf(df, precision_digits),
            "p_value": _format_mpf(p_value, precision_digits),
            "reject_null": p_value <= options.alpha,
            "sample_size": n,
            "effect_rows": [
                *[dict(row) for row in effect_prefix_rows],
                {"key": "mean_difference_minus_delta0", "value": _format_mpf(mean_difference, precision_digits)},
                {"key": "standard_error", "value": _format_mpf(standard_error, precision_digits)},
                {"key": "sample_standard_deviation", "value": _format_mpf(std, precision_digits)},
            ],
        },
        diagnostics=[],
    )


def _payload(
    *,
    test_kind: str,
    alternative: str,
    alpha: mp.mpf,
    alpha_text: str,
    backend: str,
    backend_version: str | None,
    precision_digits: int,
    value_columns: Sequence[str],
    source_row_ids: Sequence[str | int] | None,
    null_parameters: Mapping[str, str],
    result: Mapping[str, Any],
    diagnostics: Sequence[Mapping[str, str]],
    sign_mode: str | None = None,
) -> dict[str, Any]:
    sample_size = _nonnegative_int(result.get("sample_size"), field_name="result.sample_size")
    normalized_source_row_ids = list(source_row_ids) if source_row_ids is not None else [
        str(index) for index in range(1, sample_size + 1)
    ]
    inputs: dict[str, Any] = {
        "value_columns": [str(column) for column in value_columns],
        "source_row_ids": normalized_source_row_ids,
        "null_parameters": dict(null_parameters),
    }
    if sign_mode is not None:
        inputs["sign_mode"] = sign_mode
    payload: dict[str, Any] = {
        "schema": HYPOTHESIS_PAYLOAD_SCHEMA,
        "workflow_mode": HYPOTHESIS_WORKFLOW_MODE,
        "test_kind": test_kind,
        "alternative": alternative,
        "alpha": _format_mpf(alpha, precision_digits) if alpha_text != _format_mpf(alpha, precision_digits) else alpha_text,
        "backend": backend,
        "precision_used": int(precision_digits),
        "inputs": inputs,
        "result": dict(result),
        "diagnostics": [dict(item) for item in diagnostics],
    }
    if backend_version:
        payload["backend_version"] = backend_version
    return payload


def _result_value_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _normalize_options(inputs: Mapping[str, Any]) -> _HypothesisOptions:
    test_kind = _required_string_option(inputs.get("test_kind"), field_name="test_kind")
    if test_kind not in _SUPPORTED_TEST_KINDS:
        raise ValueError(_dual_msg(f"不支持的假设检验类型：{test_kind}。", f"Unsupported hypothesis test kind: {test_kind}."))
    alternative = _string_option(inputs.get("alternative"), default="two_sided", field_name="alternative")
    if alternative not in _SUPPORTED_ALTERNATIVES:
        raise ValueError(_dual_msg("alternative 必须是以下之一：greater、less、two_sided。", "alternative must be one of: greater, less, two_sided."))
    alpha_text = _numeric_string_option(inputs.get("alpha"), default="0.05", field_name="alpha")
    alpha = _parse_probability(alpha_text, field_name="alpha")
    fitted_parameter_count = 0
    if test_kind == "one_sample_t":
        null_key = "mu0"
        null_text = _numeric_string_option(inputs.get("mu0"), default="0", field_name="mu0")
        sign_mode = None
    elif test_kind in {"paired_t", "welch_t"}:
        null_key = "delta0"
        null_text = _numeric_string_option(inputs.get("delta0"), default="0", field_name="delta0")
        sign_mode = None
    elif test_kind == "sign_test":
        null_key = "m0"
        null_text = _numeric_string_option(inputs.get("m0"), default="0", field_name="m0")
        sign_mode = _string_option(inputs.get("sign_mode"), default="one_sample", field_name="sign_mode")
        if sign_mode not in _SUPPORTED_SIGN_MODES:
            raise ValueError(_dual_msg("sign_test 的第一个分片仅支持 sign_mode='one_sample'。", "sign_test first slice supports only sign_mode='one_sample'."))
    else:
        null_key = ""
        null_text = "0"
        sign_mode = None
        alternative = "greater"
        if inputs.get("alternative") not in (None, "", "greater"):
            raise ValueError(_dual_msg("chi_square_gof 仅支持上尾备择假设。", "chi_square_gof supports only the upper-tail alternative."))
        fitted_parameter_count = _optional_nonnegative_int_option(
            inputs.get("fitted_parameter_count"),
            default=0,
            field_name="fitted_parameter_count",
        )
    null_value = _finite_numeric_string(null_text, field_name=null_key)
    return _HypothesisOptions(
        test_kind=test_kind,
        alternative=alternative,
        alpha=alpha,
        alpha_text=alpha_text,
        null_parameter_key=null_key,
        null_parameter_value=null_value,
        null_parameter_text=null_text,
        sign_mode=sign_mode,
        fitted_parameter_count=fitted_parameter_count,
    )


def _student_t_p_value(
    statistic: mp.mpf,
    df: mp.mpf,
    alternative: str,
    *,
    precision_digits: int,
) -> tuple[mp.mpf, str, str | None]:
    if precision_digits <= 16:
        scipy_result = _scipy_student_t_p_value(statistic, df, alternative)
        if scipy_result is not None:
            return scipy_result
    cdf, survival = _student_t_cdf_sf(statistic, df)
    return _tail_p_value(cdf, survival, alternative), "mpmath", None


def _chi_square_p_value(
    statistic: mp.mpf,
    df: mp.mpf,
    *,
    precision_digits: int,
) -> tuple[mp.mpf, str, str | None]:
    if precision_digits <= 16:
        scipy_result = _scipy_chi_square_p_value(statistic, df)
        if scipy_result is not None:
            return scipy_result
    return _chi_square_sf(statistic, df), "mpmath", None


def _scipy_student_t_p_value(
    statistic: mp.mpf,
    df: mp.mpf,
    alternative: str,
) -> tuple[mp.mpf, str, str | None] | None:
    try:
        import scipy  # type: ignore[import-untyped]
        from scipy import stats
    except Exception:  # pragma: no cover - exercised only when SciPy is absent.
        return None
    t_float = float(statistic)
    df_float = float(df)
    if alternative == "greater":
        value = stats.t.sf(t_float, df_float)
    elif alternative == "less":
        value = stats.t.cdf(t_float, df_float)
    else:
        value = min(1.0, 2.0 * stats.t.sf(abs(t_float), df_float))
    return mp.mpf(str(value)), "scipy", str(getattr(scipy, "__version__", ""))


def _scipy_chi_square_p_value(
    statistic: mp.mpf,
    df: mp.mpf,
) -> tuple[mp.mpf, str, str | None] | None:
    try:
        import scipy
        from scipy import stats
    except Exception:  # pragma: no cover - exercised only when SciPy is absent.
        return None
    value = stats.chi2.sf(float(statistic), float(df))
    return mp.mpf(str(value)), "scipy", str(getattr(scipy, "__version__", ""))


def _student_t_cdf_sf(statistic: mp.mpf, df: mp.mpf) -> tuple[mp.mpf, mp.mpf]:
    if not df > 0:
        raise ValueError(_dual_msg("Student-t 的自由度必须大于 0。", "Student-t degrees of freedom must be > 0."))
    if statistic == 0:
        return mp.mpf("0.5"), mp.mpf("0.5")
    x = df / (df + statistic * statistic)
    half_regularized_beta = mp.mpf("0.5") * mp.betainc(df / 2, mp.mpf("0.5"), 0, x, regularized=True)
    if statistic > 0:
        cdf = 1 - half_regularized_beta
        survival = half_regularized_beta
    else:
        cdf = half_regularized_beta
        survival = 1 - half_regularized_beta
    return _clamp_probability(cdf), _clamp_probability(survival)


def _chi_square_sf(statistic: mp.mpf, df: mp.mpf) -> mp.mpf:
    if statistic < 0:
        raise ValueError(_dual_msg("卡方统计量必须是非负的。", "chi-square statistic must be non-negative."))
    if not df > 0:
        raise ValueError(_dual_msg("卡方自由度必须大于 0。", "chi-square degrees of freedom must be > 0."))
    return _clamp_probability(mp.gammainc(df / 2, statistic / 2, mp.inf, regularized=True))


def _tail_p_value(cdf: mp.mpf, survival: mp.mpf, alternative: str) -> mp.mpf:
    if alternative == "greater":
        return _clamp_probability(survival)
    if alternative == "less":
        return _clamp_probability(cdf)
    return _clamp_probability(2 * min(cdf, survival))


def _sign_test_p_value(positive_count: int, effective_n: int, alternative: str) -> mp.mpf:
    denominator = mp.power(2, effective_n)
    lower = mp.fsum(comb(effective_n, index) for index in range(positive_count + 1)) / denominator
    upper = mp.fsum(comb(effective_n, index) for index in range(positive_count, effective_n + 1)) / denominator
    return _tail_p_value(lower, upper, alternative)


def _sample_mean_variance(
    values: Sequence[mp.mpf],
    *,
    field_name: str,
    require_positive: bool = True,
) -> tuple[mp.mpf, mp.mpf]:
    if len(values) < 2:
        raise ValueError(_dual_msg(f"{field_name} 至少需要两个值。", f"{field_name} requires at least two values."))
    mean = mp.fsum(values) / len(values)
    centered = [value - mean for value in values]
    variance = mp.fsum([value * value for value in centered]) / (len(values) - 1)
    if not mp.isfinite(variance) or variance < 0:
        raise ValueError(_dual_msg(f"{field_name} 需要一个有限的非负样本方差。", f"{field_name} requires a finite non-negative sample variance."))
    if require_positive and not variance > 0:
        raise ValueError(_dual_msg(f"{field_name} 需要一个正的有限样本方差。", f"{field_name} requires a positive finite sample variance."))
    return mean, variance


def _validate_observed_count(value: mp.mpf, index: int) -> mp.mpf:
    count = mp.mpf(value)
    if not (mp.isfinite(count) and count >= 0):
        raise ValueError(_dual_msg(f"类别 {index} 处的观测计数必须是有限且非负的。", f"observed count at category {index} must be finite and non-negative."))
    if count != mp.floor(count):
        raise ValueError(_dual_msg(f"类别 {index} 处的观测计数必须为整数值。", f"observed count at category {index} must be integer-valued."))
    return count


def _same_total(left: mp.mpf, right: mp.mpf, precision_digits: int) -> bool:
    tolerance = mp.power(10, -max(8, int(precision_digits) // 2))
    return bool(mp.fabs(left - right) <= tolerance * max(mp.mpf("1"), mp.fabs(left), mp.fabs(right)))


def _parse_probability(value: str, *, field_name: str) -> mp.mpf:
    parsed = _finite_numeric_string(value, field_name=field_name)
    if not (mp.mpf("0") < parsed < mp.mpf("1")):
        raise ValueError(_dual_msg(f"{field_name} 必须在 (0, 1) 区间内。", f"{field_name} must be in (0, 1)."))
    return parsed


def _clamp_probability(value: mp.mpf) -> mp.mpf:
    if value < 0:
        return mp.mpf("0")
    if value > 1:
        return mp.mpf("1")
    return value


def _format_mpf(value: Any, precision_digits: int) -> str:
    return str(mp.nstr(mp.mpf(value), n=max(1, int(precision_digits))))


def _reject_json_floats(value: Any, *, path: str) -> None:
    if isinstance(value, float):
        raise TypeError(_dual_msg(f"{path} 处不允许出现 JSON 浮点数；请以字符串形式传递数值。", f"JSON floats are not allowed at {path}; pass numeric values as strings."))
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, float):
                raise TypeError(_dual_msg(f"{path}.<key> 处不允许出现 JSON 浮点数。", f"JSON floats are not allowed at {path}.<key>."))
            _reject_json_floats(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        for index, item in enumerate(value):
            _reject_json_floats(item, path=f"{path}[{index}]")


def _reject_unknown_keys(mapping: Mapping[str, Any], allowed: set[str] | frozenset[str], *, path: str) -> None:
    unknown = set(mapping) - set(allowed)
    if unknown:
        names = ", ".join(sorted(str(key) for key in unknown))
        raise ValueError(_dual_msg(f"{path} 包含不受支持的字段：{names}。", f"{path} contains unsupported fields: {names}."))


def _required_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个映射。", f"{field_name} must be a mapping."))
    return value


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(_dual_msg(f"{field_name} 必须是一个非空字符串。", f"{field_name} must be a non-empty string."))
    return value


def _optional_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是字符串或 None。", f"{field_name} must be a string or None."))
    return value


def _required_string_option(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(_dual_msg(f"{field_name} 必须是一个非空字符串。", f"{field_name} must be a non-empty string."))
    return value.strip()


def _string_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(_dual_msg(f"{field_name} 必须是一个字符串。", f"{field_name} must be a string."))
    return value.strip() or default


def _numeric_string_option(value: Any, *, default: str, field_name: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(_dual_msg(f"{field_name} 必须是一个数值字符串。", f"{field_name} must be a numeric string."))
    return value


def _optional_nonnegative_int_option(value: Any, *, default: int, field_name: str) -> int:
    if value is None:
        return default
    return _nonnegative_int(value, field_name=field_name)


def _parse_mpf_sequence(value: Any, *, field_name: str) -> list[mp.mpf]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise ValueError(_dual_msg(f"{field_name} 必须是一个数值字符串列表。", f"{field_name} must be a list of numeric strings."))
    parsed = [_finite_numeric_string(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(value)]
    if not parsed:
        raise ValueError(_dual_msg(f"{field_name} 至少需要包含一个值。", f"{field_name} must contain at least one value."))
    return parsed


def _parse_optional_mpf_sequence(value: Any, *, field_name: str) -> list[mp.mpf] | None:
    if value is None:
        return None
    return _parse_mpf_sequence(value, field_name=field_name)


def _parse_optional_source_row_ids(value: Any, *, field_name: str) -> tuple[str | int, ...] | None:
    if value is None:
        return None
    return _source_row_ids(value, field_name=field_name)


def _default_source_row_ids(value: Sequence[str | int] | None, *, count: int) -> tuple[str | int, ...]:
    if value is None:
        return tuple(str(index) for index in range(1, count + 1))
    row_ids = tuple(value)
    if len(row_ids) != count:
        raise ValueError(_dual_msg("源行 ID 的数量必须与数值数量匹配。", "source row ID count must match value count."))
    return row_ids


def _finite_numeric_string(value: Any, *, field_name: str) -> mp.mpf:
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个数值字符串。", f"{field_name} must be a numeric string."))
    parsed = mp.mpf(value)
    if not mp.isfinite(parsed):
        raise ValueError(_dual_msg(f"{field_name} 必须是有限值。", f"{field_name} must be finite."))
    return parsed


def _choice(value: Any, allowed: set[str], field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个字符串。", f"{field_name} must be a string."))
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(_dual_msg(f"{field_name} 必须是以下之一：{choices}。", f"{field_name} must be one of: {choices}."))
    return value


def _positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个正整数。", f"{field_name} must be a positive integer."))
    if value <= 0:
        raise ValueError(_dual_msg(f"{field_name} 必须为正。", f"{field_name} must be positive."))
    return int(value)


def _nonnegative_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个非负整数。", f"{field_name} must be a non-negative integer."))
    if value < 0:
        raise ValueError(_dual_msg(f"{field_name} 必须是非负的。", f"{field_name} must be non-negative."))
    return int(value)


def _required_text_sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个字符串序列。", f"{field_name} must be a sequence of strings."))
    output: list[str] = []
    for index, item in enumerate(value):
        output.append(_required_text(item, f"{field_name}[{index}]"))
    return tuple(output)


def _source_row_ids(value: Any, *, field_name: str) -> tuple[str | int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个行标识符序列。", f"{field_name} must be a sequence of row identifiers."))
    output: list[str | int] = []
    for index, item in enumerate(value):
        if isinstance(item, float):
            raise TypeError(_dual_msg(f"{field_name}[{index}] 处不允许出现 JSON 浮点数。", f"JSON floats are not allowed at {field_name}[{index}]."))
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise TypeError(_dual_msg(f"{field_name}[{index}] 必须是字符串或整数。", f"{field_name}[{index}] must be a string or integer."))
        if isinstance(item, str) and not item.strip():
            raise ValueError(_dual_msg(f"{field_name}[{index}] 不能为空白。", f"{field_name}[{index}] must not be blank."))
        output.append(item)
    return tuple(output)


def _effect_rows(value: Any, *, field_name: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个映射序列。", f"{field_name} must be a sequence of mappings."))
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise TypeError(_dual_msg(f"{field_name}[{index}] 必须是一个映射。", f"{field_name}[{index}] must be a mapping."))
        _reject_unknown_keys(row, _EFFECT_ROW_KEYS, path=f"{field_name}[{index}]")
        _required_text(row.get("key"), f"{field_name}[{index}].key")
        row_value = row.get("value")
        if isinstance(row_value, int) and not isinstance(row_value, bool):
            continue
        _finite_numeric_string(row_value, field_name=f"{field_name}[{index}].value")
        if "note" in row:
            _optional_text(row.get("note"), f"{field_name}[{index}].note")


def _diagnostics(value: Any, *, field_name: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray, memoryview)):
        raise TypeError(_dual_msg(f"{field_name} 必须是一个映射序列。", f"{field_name} must be a sequence of mappings."))
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise TypeError(_dual_msg(f"{field_name}[{index}] 必须是一个映射。", f"{field_name}[{index}] must be a mapping."))
        _reject_unknown_keys(row, _DIAGNOSTIC_KEYS, path=f"{field_name}[{index}]")
        _required_text(row.get("code"), f"{field_name}[{index}].code")
        _choice(row.get("severity"), _DIAGNOSTIC_SEVERITIES, f"{field_name}[{index}].severity")
        _required_text(row.get("message"), f"{field_name}[{index}].message")
