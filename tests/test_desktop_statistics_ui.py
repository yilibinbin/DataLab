from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from mpmath import mp

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QSizePolicy, QWidget

from app_desktop.ui_schema_binder import find_unbound_required_widgets


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    # Pin the language so assertions are deterministic regardless of the runner's
    # system locale (CI defaults to English, local dev often to Chinese).
    win._apply_language("zh")
    qtbot.addWidget(win)
    return win


def _combo_data(combo: Any) -> list[object]:
    return [combo.itemData(index) for index in range(combo.count())]


def test_statistics_inputs_have_schema_metadata(window: Any) -> None:
    assert window.stats_box.property("datalab_view_module") == "app_desktop.views.statistics"
    assert window.stats_value_column_edit.property("datalab_schema_key") == "statistics.value_columns"
    assert window.stats_value_column_edit.property("datalab_schema_required") is True
    assert window.stats_value_column_edit.placeholderText()
    assert window.stats_value_column_edit.toolTip()

    assert window.stats_sigma_column_edit.property("datalab_schema_key") == "statistics.sigma_column"
    assert window.stats_sigma_column_edit.property("datalab_schema_required") is False
    assert window.stats_sigma_column_edit.placeholderText()
    assert window.stats_sigma_column_edit.toolTip()

    assert window.stats_group_column_edit.property("datalab_schema_key") == "statistics.group_column"
    assert window.stats_group_column_edit.property("datalab_schema_required") is False
    assert window.stats_group_column_edit.placeholderText()
    assert window.stats_group_column_edit.toolTip()

    assert window.stats_trim_fraction_edit.property("datalab_schema_key") == "statistics.trim_fraction"
    assert window.stats_trim_fraction_edit.property("datalab_schema_required") is False
    assert window.stats_trim_fraction_edit.placeholderText()
    assert window.stats_trim_fraction_edit.toolTip()


def test_statistics_mode_and_options_have_schema_metadata(window: Any) -> None:
    assert window.stats_workflow_combo.property("datalab_schema_key") == "statistics.workflow_mode"
    assert window.stats_workflow_combo.property("datalab_schema_required") is True
    assert window.stats_workflow_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_workflow_combo) == [
        "standard",
        "covariance_correlation",
        "grouped_statistics",
        "bootstrap_confidence_intervals",
        "hypothesis_tests",
        "time_series_rolling",
    ]
    assert window.stats_workflow_combo.toolTip()

    assert window.stats_mode_combo.property("datalab_schema_key") == "statistics.mode"
    assert window.stats_mode_combo.property("datalab_schema_required") is True
    assert window.stats_mode_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_mode_combo) == ["mean", "descriptive", "weighted_sigma"]
    assert window.stats_mode_combo.toolTip()

    assert window.stats_time_series_method_combo.property("datalab_schema_key") == (
        "statistics.time_series.series_method"
    )
    assert window.stats_time_series_method_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_time_series_method_combo) == [
        "rolling_mean",
        "rolling_median",
        "rolling_std",
        "ewma",
    ]
    assert window.stats_time_series_time_column_edit.property("datalab_schema_key") == (
        "statistics.time_series.time_column"
    )
    assert window.stats_time_series_time_column_edit.toolTip()
    assert window.stats_time_series_window_size_spin.property("datalab_schema_key") == (
        "statistics.time_series.window_size"
    )
    assert window.stats_time_series_min_periods_spin.property("datalab_schema_key") == (
        "statistics.time_series.min_periods"
    )
    assert window.stats_time_series_alignment_combo.property("datalab_schema_key") == (
        "statistics.time_series.alignment"
    )
    assert window.stats_time_series_alignment_combo.property("datalab_schema_choices") is True
    assert window.stats_time_series_denominator_combo.property("datalab_schema_key") == (
        "statistics.time_series.denominator"
    )
    assert window.stats_time_series_denominator_combo.property("datalab_schema_choices") is True
    assert window.stats_time_series_ewma_parameter_combo.property("datalab_schema_key") == (
        "statistics.time_series.ewma_parameter"
    )
    assert window.stats_time_series_ewma_parameter_combo.property("datalab_schema_choices") is True
    assert window.stats_time_series_ewma_value_edit.property("datalab_schema_key") == (
        "statistics.time_series.ewma_value"
    )
    assert window.stats_time_series_ewma_adjust_checkbox.property("datalab_schema_key") == (
        "statistics.time_series.adjust"
    )
    assert window.stats_matrix_missing_policy_combo.property("datalab_schema_key") == (
        "statistics.matrix.missing_policy"
    )
    assert window.stats_matrix_missing_policy_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_matrix_missing_policy_combo) == ["listwise", "pairwise"]
    assert window.stats_matrix_missing_policy_combo.toolTip()

    assert window.stats_weight_variance_checkbox.property("datalab_schema_key") == (
        "statistics.weight_variance"
    )
    assert window.stats_weight_variance_checkbox.property("datalab_schema_required") is False
    assert window.stats_weight_variance_checkbox.toolTip()

    assert window.stats_sample_checkbox.property("datalab_schema_key") == "statistics.sample_mode"
    assert window.stats_sample_checkbox.toolTip()


def test_statistics_hypothesis_controls_have_schema_metadata(window: Any) -> None:
    assert window.stats_hypothesis_test_combo.property("datalab_schema_key") == (
        "statistics.hypothesis.test_kind"
    )
    assert window.stats_hypothesis_test_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_hypothesis_test_combo) == [
        "one_sample_t",
        "paired_t",
        "welch_t",
        "sign_test",
        "chi_square_gof",
    ]
    assert window.stats_hypothesis_test_combo.toolTip()
    assert window.stats_hypothesis_b_column_edit.property("datalab_schema_key") == (
        "statistics.hypothesis.second_column"
    )
    assert window.stats_hypothesis_b_column_edit.toolTip()
    assert window.stats_hypothesis_null_edit.property("datalab_schema_key") == (
        "statistics.hypothesis.null_parameter"
    )
    assert window.stats_hypothesis_null_edit.toolTip()
    assert window.stats_hypothesis_alternative_combo.property("datalab_schema_key") == (
        "statistics.hypothesis.alternative"
    )
    assert _combo_data(window.stats_hypothesis_alternative_combo) == ["two_sided", "less", "greater"]
    assert window.stats_hypothesis_alpha_edit.property("datalab_schema_key") == (
        "statistics.hypothesis.alpha"
    )
    assert window.stats_hypothesis_expected_source_combo.property("datalab_schema_key") == (
        "statistics.hypothesis.expected_source"
    )
    assert _combo_data(window.stats_hypothesis_expected_source_combo) == ["counts", "probabilities"]
    assert window.stats_hypothesis_fitted_parameters_spin.property("datalab_schema_key") == (
        "statistics.hypothesis.fitted_parameter_count"
    )


def test_statistics_bootstrap_controls_have_schema_metadata(window: Any) -> None:
    assert window.stats_bootstrap_target_combo.property("datalab_schema_key") == (
        "statistics.bootstrap.target_statistic"
    )
    assert window.stats_bootstrap_target_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_bootstrap_target_combo) == [
        "mean",
        "median",
        "trimmed_mean",
        "std",
        "variance",
    ]
    assert window.stats_bootstrap_target_combo.toolTip()

    assert window.stats_bootstrap_confidence_edit.property("datalab_schema_key") == (
        "statistics.bootstrap.confidence_level"
    )
    assert window.stats_bootstrap_confidence_edit.text() == "0.95"
    assert window.stats_bootstrap_confidence_edit.isReadOnly()
    assert window.stats_bootstrap_confidence_edit.toolTip()

    assert window.stats_bootstrap_resamples_spin.property("datalab_schema_key") == (
        "statistics.bootstrap.resample_count"
    )
    assert window.stats_bootstrap_resamples_spin.value() == 2000
    assert window.stats_bootstrap_resamples_spin.toolTip()

    assert window.stats_bootstrap_seed_edit.property("datalab_schema_key") == "statistics.bootstrap.seed"
    assert window.stats_bootstrap_seed_edit.toolTip()


def test_statistics_schema_tooltips_and_choices_refresh_with_language(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("bootstrap_confidence_intervals"))
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))
    window.stats_bootstrap_target_combo.setCurrentIndex(window.stats_bootstrap_target_combo.findData("median"))

    window._apply_language("en")

    assert window.stats_workflow_combo.currentData() == "bootstrap_confidence_intervals"
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("standard")) == "Standard statistics"
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("covariance_correlation")) == (
        "Covariance/correlation matrix"
    )
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("grouped_statistics")) == (
        "Grouped statistics"
    )
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("bootstrap_confidence_intervals")) == (
        "Bootstrap confidence intervals"
    )
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("hypothesis_tests")) == (
        "Hypothesis tests"
    )
    assert window.stats_mode_combo.currentData() == "weighted_sigma"
    assert window.stats_mode_combo.itemText(window.stats_mode_combo.findData("mean")) == "Arithmetic mean"
    assert window.stats_mode_combo.itemText(window.stats_mode_combo.findData("descriptive")) == "Descriptive statistics"
    assert window.stats_bootstrap_target_combo.currentData() == "median"
    assert window.stats_bootstrap_target_combo.itemText(window.stats_bootstrap_target_combo.findData("median")) == "Median"
    assert "Columns containing measured values" in window.stats_value_column_edit.toolTip()
    assert "matrix workflow computes covariance and correlation" in window.stats_value_column_edit.toolTip()
    assert "first appearance" in window.stats_group_column_edit.toolTip()
    assert "Optional uncertainty column" in window.stats_sigma_column_edit.toolTip()
    assert "floor(n * trim fraction)" in window.stats_trim_fraction_edit.toolTip()
    assert "descriptive statistics" in window.stats_mode_combo.toolTip()
    assert "Use sigma values" in window.stats_mode_combo.toolTip()
    assert "fixed 95% confidence interval" in window.stats_workflow_combo.toolTip()
    assert "Hypothesis tests report test statistics" in window.stats_workflow_combo.toolTip()
    assert "percentile bootstrap" in window.stats_bootstrap_target_combo.toolTip()

    window._apply_language("zh")

    assert window.stats_workflow_combo.currentData() == "bootstrap_confidence_intervals"
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("standard")) == "常规统计"
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("covariance_correlation")) == (
        "协方差/相关矩阵"
    )
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("grouped_statistics")) == "分组统计"
    assert window.stats_workflow_combo.itemText(window.stats_workflow_combo.findData("hypothesis_tests")) == "假设检验"
    assert window.stats_mode_combo.currentData() == "weighted_sigma"
    assert window.stats_mode_combo.itemText(window.stats_mode_combo.findData("mean")) == "算术平均"
    assert window.stats_mode_combo.itemText(window.stats_mode_combo.findData("descriptive")) == "描述统计"
    assert window.stats_bootstrap_target_combo.currentData() == "median"
    assert window.stats_bootstrap_target_combo.itemText(window.stats_bootstrap_target_combo.findData("median")) == "中位数"
    assert "矩阵工作流会计算" in window.stats_value_column_edit.toolTip()
    assert "首次出现顺序" in window.stats_group_column_edit.toolTip()
    assert "可选的不确定度列" in window.stats_sigma_column_edit.toolTip()
    assert "修剪比例" in window.stats_trim_fraction_edit.toolTip()
    assert "独立重采样" in window.stats_workflow_combo.toolTip()


def test_statistics_trim_fraction_control_visible_only_for_descriptive(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("standard"))
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("mean"))
    window._on_stats_mode_change()
    assert window.stats_trim_fraction_edit.isHidden()

    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("descriptive"))
    window._on_stats_mode_change()
    assert not window.stats_trim_fraction_edit.isHidden()

    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))
    window._on_stats_mode_change()
    assert window.stats_trim_fraction_edit.isHidden()


def test_statistics_bootstrap_visibility_replaces_regular_mode_controls(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("standard"))
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("mean"))
    window._on_stats_mode_change()

    assert not window.stats_mode_combo.isHidden()
    assert not window.stats_sigma_column_edit.isHidden()
    assert window.stats_bootstrap_target_combo.isHidden()
    assert window.stats_bootstrap_resamples_spin.isHidden()
    assert window.stats_trim_fraction_edit.isHidden()

    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("bootstrap_confidence_intervals"))
    window.stats_bootstrap_target_combo.setCurrentIndex(window.stats_bootstrap_target_combo.findData("mean"))
    window._on_stats_mode_change()

    assert window.stats_mode_combo.isHidden()
    assert window.stats_sigma_column_edit.isHidden()
    assert not window.stats_bootstrap_target_combo.isHidden()
    assert not window.stats_bootstrap_resamples_spin.isHidden()
    assert window.stats_weight_variance_checkbox.isHidden()
    assert window.stats_trim_fraction_edit.isHidden()

    window.stats_bootstrap_target_combo.setCurrentIndex(window.stats_bootstrap_target_combo.findData("trimmed_mean"))
    window._on_stats_mode_change()

    assert not window.stats_trim_fraction_edit.isHidden()


def test_statistics_hypothesis_visibility_tracks_test_kind(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("hypothesis_tests"))
    window.stats_hypothesis_test_combo.setCurrentIndex(window.stats_hypothesis_test_combo.findData("one_sample_t"))
    window._on_stats_mode_change()

    assert window.stats_mode_combo.isHidden()
    assert window.stats_sigma_column_edit.isHidden()
    assert window.stats_bootstrap_target_combo.isHidden()
    assert not window.stats_hypothesis_test_combo.isHidden()
    assert window.stats_hypothesis_b_column_edit.isHidden()
    assert not window.stats_hypothesis_null_edit.isHidden()
    assert not window.stats_hypothesis_alternative_combo.isHidden()
    assert not window.stats_hypothesis_alpha_edit.isHidden()
    assert window.stats_hypothesis_expected_source_combo.isHidden()
    assert window.stats_sample_checkbox.isHidden()

    window.stats_hypothesis_test_combo.setCurrentIndex(window.stats_hypothesis_test_combo.findData("chi_square_gof"))
    window._on_stats_mode_change()

    assert not window.stats_hypothesis_b_column_edit.isHidden()
    assert window.stats_hypothesis_null_edit.isHidden()
    assert window.stats_hypothesis_alternative_combo.isHidden()
    assert not window.stats_hypothesis_expected_source_combo.isHidden()
    assert not window.stats_hypothesis_fitted_parameters_spin.isHidden()


def test_statistics_time_series_visibility_tracks_method(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("time_series_rolling"))
    window.stats_time_series_method_combo.setCurrentIndex(
        window.stats_time_series_method_combo.findData("rolling_mean")
    )
    window._on_stats_mode_change()

    assert window.stats_mode_combo.isHidden()
    assert not window.stats_sigma_column_edit.isHidden()
    assert not window.stats_time_series_method_combo.isHidden()
    assert not window.stats_time_series_time_column_edit.isHidden()
    assert not window.stats_time_series_window_size_spin.isHidden()
    assert not window.stats_time_series_min_periods_spin.isHidden()
    assert not window.stats_time_series_alignment_combo.isHidden()
    assert window.stats_time_series_denominator_combo.isHidden()
    assert window.stats_time_series_ewma_value_edit.isHidden()
    assert window.stats_sample_checkbox.isHidden()
    assert window.stats_trim_fraction_edit.isHidden()

    window.stats_time_series_method_combo.setCurrentIndex(
        window.stats_time_series_method_combo.findData("rolling_std")
    )
    window._on_stats_mode_change()

    assert window.stats_sigma_column_edit.isHidden()
    assert not window.stats_time_series_denominator_combo.isHidden()

    window.stats_time_series_method_combo.setCurrentIndex(window.stats_time_series_method_combo.findData("ewma"))
    window._on_stats_mode_change()

    assert window.stats_time_series_window_size_spin.isHidden()
    assert window.stats_time_series_min_periods_spin.isHidden()
    assert window.stats_time_series_alignment_combo.isHidden()
    assert window.stats_time_series_denominator_combo.isHidden()
    assert not window.stats_time_series_ewma_parameter_combo.isHidden()
    assert not window.stats_time_series_ewma_value_edit.isHidden()
    assert not window.stats_time_series_ewma_adjust_checkbox.isHidden()


def test_statistics_matrix_visibility_replaces_scalar_controls(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("covariance_correlation"))
    window._on_stats_mode_change()

    assert window.stats_mode_combo.isHidden()
    assert window.stats_group_column_edit.isHidden()
    assert window.stats_sigma_column_edit.isHidden()
    assert window.stats_weight_variance_checkbox.isHidden()
    assert window.stats_trim_fraction_edit.isHidden()
    assert not window.stats_sample_checkbox.isHidden()
    assert not window.stats_matrix_missing_policy_combo.isHidden()
    assert window.stats_bootstrap_target_combo.isHidden()
    assert window.stats_hypothesis_test_combo.isHidden()
    assert window.stats_time_series_method_combo.isHidden()


def test_statistics_grouped_visibility_reuses_scalar_controls(window: Any) -> None:
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("grouped_statistics"))
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))
    window._on_stats_mode_change()

    assert not window.stats_group_column_edit.isHidden()
    assert not window.stats_mode_combo.isHidden()
    assert not window.stats_sigma_column_edit.isHidden()
    assert not window.stats_weight_variance_checkbox.isHidden()
    assert not window.stats_sample_checkbox.isHidden()
    assert window.stats_matrix_missing_policy_combo.isHidden()
    assert window.stats_bootstrap_target_combo.isHidden()
    assert window.stats_hypothesis_test_combo.isHidden()
    assert window.stats_time_series_method_combo.isHidden()

    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("descriptive"))
    window._on_stats_mode_change()
    assert not window.stats_trim_fraction_edit.isHidden()


def test_statistics_panel_has_no_unbound_required_schema_widgets(window: Any) -> None:
    assert find_unbound_required_widgets(window.stats_box) == []


def test_statistics_table_preserves_explicit_zero_uncertainty(window: Any) -> None:
    headers, rows, sigma_rows = window._parse_generic_table("A\n1.25(0)\n2.50\n")

    assert headers == ["A"]
    assert rows == [(mp.mpf("1.25"),), (mp.mpf("2.50"),)]
    explicit_zero = sigma_rows[0][0]
    assert explicit_zero is not None
    assert mp.mpf(getattr(explicit_zero, "uncertainty")) == mp.mpf("0")
    assert sigma_rows[1][0] is None


def test_statistics_direct_sigma_column_rejects_negative_sigma(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A sigma\n1 -0.1\n2 0.2\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_value_column_edit.setText("A")
    window.stats_sigma_column_edit.setText("sigma")
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))

    with pytest.raises(ValueError, match="Negative uncertainty"):
        window._run_statistics_mode(False, "")


def test_statistics_run_accepts_comma_separated_value_columns(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A B sigma\n1 10 0.1\n2 20 0.2\n3 30 0.3\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("standard"))
    window.stats_value_column_edit.setText("B, A")
    window.stats_sigma_column_edit.setText("sigma")
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_batches"
    payload = window._last_result_payloads["statistics_batches"]
    assert payload["value_col"] == "B, A"
    assert payload["value_columns"] == ["B", "A"]
    assert [(batch["value_col"], batch["column_index"]) for batch in payload["batches"]] == [
        ("B", 1),
        ("A", 2),
    ]
    csv_means = [row for row in window._csv_rows if row["metric"] == "mean"]
    assert [row["column"] for row in csv_means] == ["B", "A"]
    assert "=== Statistics: Column B ===" in window.result_edit.toPlainText()


def test_statistics_matrix_run_accepts_delimited_data_with_blank_cells(window: Any) -> None:
    # Matrix/time-series parsing must preserve delimited cells like the grouped path,
    # so CSV/TSV exports with blank (missing) cells reach the matrix missing policies
    # instead of failing as a column-count mismatch before any policy runs.
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A,B\n1,\n2,3\n4,5\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(
        window.stats_workflow_combo.findData("covariance_correlation")
    )
    window.stats_value_column_edit.setText("A, B")
    window.stats_matrix_missing_policy_combo.setCurrentIndex(
        window.stats_matrix_missing_policy_combo.findData("pairwise")
    )

    # Must not raise a column-count mismatch on the blank cell in row "1,".
    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_matrix"


def test_statistics_bootstrap_direct_run_uses_semantic_snapshot(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A\n1\n2\n3\n4\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("bootstrap_confidence_intervals"))
    window.stats_value_column_edit.setText("A")
    window.stats_bootstrap_target_combo.setCurrentIndex(window.stats_bootstrap_target_combo.findData("mean"))
    window.stats_bootstrap_resamples_spin.setValue(100)
    window.stats_bootstrap_seed_edit.setText("42")

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_bootstrap"
    assert window._last_result_semantic_snapshot_kind == "statistics_bootstrap"
    assert window._last_result_semantic_snapshot["mode"] == "bootstrap_confidence_intervals"
    assert window._last_result_semantic_snapshot["bootstrap"]["resample_count"] == 100
    assert window._last_result_semantic_snapshot["bootstrap"]["seed"] == 42
    assert any(row["metric"] == "bootstrap_ci_lower" for row in window._csv_rows)
    assert "Bootstrap CI lower" in window.result_edit.toPlainText()


def test_statistics_hypothesis_direct_run_uses_semantic_snapshot(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A\n2\n3\n4\n5\n6\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("hypothesis_tests"))
    window.stats_hypothesis_test_combo.setCurrentIndex(window.stats_hypothesis_test_combo.findData("one_sample_t"))
    window.stats_value_column_edit.setText("A")
    window.stats_hypothesis_null_edit.setText("3")
    window.stats_hypothesis_alpha_edit.setText("0.05")

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_hypothesis_test"
    assert window._last_result_semantic_snapshot_kind == "statistics_hypothesis_test"
    snapshot = window._last_result_semantic_snapshot
    assert snapshot["mode"] == "hypothesis_tests"
    assert snapshot["hypothesis_test"]["test_kind"] == "one_sample_t"
    assert "Hypothesis Test" in window.result_edit.toPlainText()
    assert any(row["metric"] == "p_value" for row in window._csv_rows)


def test_statistics_time_series_direct_run_uses_semantic_snapshot_with_text_time_labels(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("t A sigma\np1 1.0 0.1\np2 3.0 0.2\np3 5.0 0.3\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("time_series_rolling"))
    window.stats_time_series_method_combo.setCurrentIndex(
        window.stats_time_series_method_combo.findData("rolling_mean")
    )
    window.stats_value_column_edit.setText("A")
    window.stats_sigma_column_edit.setText("sigma")
    window.stats_time_series_time_column_edit.setText("t")
    window.stats_time_series_window_size_spin.setValue(2)
    window.stats_time_series_min_periods_spin.setValue(2)
    window.stats_time_series_alignment_combo.setCurrentIndex(
        window.stats_time_series_alignment_combo.findData("right")
    )

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_time_series"
    assert window._last_result_semantic_snapshot_kind == "statistics_time_series"
    snapshot = window._last_result_semantic_snapshot
    assert snapshot["mode"] == "time_series_rolling"
    assert snapshot["source"]["time_column"] == "t"
    assert snapshot["time_series"][0]["value_column"] == "A"
    assert window._last_result_payloads["statistics_time_series"]["time_column"] == "t"
    assert "Time-Series Statistics" in window.result_edit.toPlainText()
    assert any(row["time"] == "p2" and row["uncertainty"] for row in window._csv_rows)


def test_statistics_matrix_direct_run_uses_semantic_snapshot(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A B\n1 2\n2 4\n3 6\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("covariance_correlation"))
    window.stats_value_column_edit.setText("A, B")
    window.stats_sample_checkbox.setChecked(True)
    window.stats_matrix_missing_policy_combo.setCurrentIndex(
        window.stats_matrix_missing_policy_combo.findData("listwise")
    )

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_matrix"
    assert window._last_result_semantic_snapshot_kind == "statistics_matrix"
    snapshot = window._last_result_semantic_snapshot
    assert snapshot["mode"] == "covariance_correlation"
    assert snapshot["statistics_matrix"]["missing_policy"] == "listwise"
    assert snapshot["statistics_matrix"]["columns"] == ["A", "B"]
    assert any(row["matrix"] == "correlation" and row["row_column"] == "A" for row in window._csv_rows)
    assert "Covariance/correlation matrix" in window.result_edit.toPlainText()


def test_statistics_matrix_pairwise_run_preserves_missing_markers(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A B\n1 10\nNA 20\n3 30\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("covariance_correlation"))
    window.stats_value_column_edit.setText("A, B")
    window.stats_matrix_missing_policy_combo.setCurrentIndex(
        window.stats_matrix_missing_policy_combo.findData("pairwise")
    )

    window._run_statistics_mode(False, "")

    payload = window._last_result_payloads["statistics_matrix"]
    assert payload["missing_policy"] == "pairwise"
    assert payload["matrices"]["covariance"]["counts"] == [[2, 2], [2, 3]]
    assert payload["correlation_metadata"]["budget_eligible"] is False


def test_statistics_grouped_direct_run_uses_semantic_snapshot(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("Group\tA\tB\ncontrol\t1\t10\ntreated\t2\t20\ncontrol\t3\t30\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("grouped_statistics"))
    window.stats_group_column_edit.setText("Group")
    window.stats_value_column_edit.setText("A, B")
    window.stats_sample_checkbox.setChecked(True)

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_grouped"
    assert window._last_result_semantic_snapshot_kind == "statistics_grouped"
    snapshot = window._last_result_semantic_snapshot
    assert snapshot["mode"] == "grouped_statistics"
    assert snapshot["statistics_grouped"]["group_order"] == ["control", "treated"]
    assert snapshot["statistics_grouped"]["value_columns"] == ["A", "B"]
    assert any(row["group"] == "control" and row["column"] == "A" and row["metric"] == "mean" for row in window._csv_rows)
    assert "Grouped statistics" in window.result_edit.toPlainText()
    assert "Group 1: control" in window.result_edit.toPlainText()

    window._refresh_display_format()

    assert window._csv_headers == ["group", "column", "batch", "metric", "value", "uncertainty"]
    assert "Group 1: control" in window.result_edit.toPlainText()


def test_statistics_grouped_preserves_delimited_blank_value_cells(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("Group\tA\tB\ncontrol\t1\t\ncontrol\t\t2\ntreated\t3\t4\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("grouped_statistics"))
    window.stats_group_column_edit.setText("Group")
    window.stats_value_column_edit.setText("A, B")

    window._run_statistics_mode(False, "")

    payload = window._last_result_payloads["statistics_grouped"]
    diagnostics = payload["diagnostics"]
    assert any(item["code"] == "blank_value" and item["column"] == "B" for item in diagnostics)
    assert any(item["code"] == "blank_value" and item["column"] == "A" for item in diagnostics)


def test_statistics_grouped_raw_table_uses_header_delimiter_only() -> None:
    from app_desktop.window_statistics_mixin import _statistics_raw_table_preserving_cells

    headers, rows = _statistics_raw_table_preserving_cells("Group A\ng 1,000\n")

    assert headers == ["Group", "A"]
    assert rows == [["g", "1,000"]]


def test_statistics_grouped_direct_run_exports_latex_and_plot(window: Any, tmp_path: Path) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("Group A\ncontrol 1\ncontrol 3\ntreated 2\ntreated 4\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("grouped_statistics"))
    window.stats_group_column_edit.setText("Group")
    window.stats_value_column_edit.setText("A")
    window.stats_sample_checkbox.setChecked(True)
    window.generate_plots_checkbox.setChecked(True)
    window.dcolumn_checkbox.setChecked(True)
    tex_path = tmp_path / "statistics-grouped.tex"

    window._run_statistics_mode(True, str(tex_path))

    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")
    assert "control" in content
    assert "treated" in content
    assert "mean" in content
    assert "\\usepackage{dcolumn}" in content
    assert window.current_stats_figures
    assert window._current_stats_plot_metadata[0]["plot_key"] == "statistics.grouped_mean_overview"
    assert Path(window.current_stats_figures[0]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_time_series_direct_run_exports_latex_and_plot(window: Any, tmp_path: Path) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("t A S\nday_1 1.0 0.1\nday_2 2.0 0.2\nday_3 4.0 0.3\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("time_series_rolling"))
    window.stats_time_series_method_combo.setCurrentIndex(
        window.stats_time_series_method_combo.findData("rolling_mean")
    )
    window.stats_value_column_edit.setText("A")
    window.stats_sigma_column_edit.setText("S")
    window.stats_time_series_time_column_edit.setText("t")
    window.stats_time_series_window_size_spin.setValue(2)
    window.stats_time_series_min_periods_spin.setValue(2)
    window.generate_plots_checkbox.setChecked(True)
    window.dcolumn_checkbox.setChecked(True)
    tex_path = tmp_path / "time-series.tex"

    window._run_statistics_mode(True, str(tex_path))

    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")
    assert "Time-Series Statistics" in content
    assert "A" in content
    assert "day\\_2" in content
    assert "\\usepackage{dcolumn}" in content
    assert window.current_stats_figures
    assert window._current_stats_plot_metadata[0]["plot_key"] == "statistics.time_series"
    assert Path(window.current_stats_figures[0]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_matrix_direct_run_exports_latex_and_heatmap(window: Any, tmp_path: Path) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A B\n1 2\n2 4\n3 6\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("covariance_correlation"))
    window.stats_value_column_edit.setText("A, B")
    window.stats_sample_checkbox.setChecked(True)
    window.stats_matrix_missing_policy_combo.setCurrentIndex(
        window.stats_matrix_missing_policy_combo.findData("listwise")
    )
    window.generate_plots_checkbox.setChecked(True)
    window.dcolumn_checkbox.setChecked(True)
    tex_path = tmp_path / "statistics-matrix.tex"

    window._run_statistics_mode(True, str(tex_path))

    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")
    assert "Covariance" in content
    assert "Correlation" in content
    assert "\\usepackage{dcolumn}" in content
    assert window.current_stats_figures
    assert window._current_stats_plot_metadata[0]["plot_key"] == "statistics.correlation_heatmap"
    assert Path(window.current_stats_figures[0]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_time_series_hidden_sigma_field_does_not_affect_non_mean_methods(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A\n1.0\n3.0\n5.0\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("time_series_rolling"))
    window.stats_time_series_method_combo.setCurrentIndex(
        window.stats_time_series_method_combo.findData("rolling_std")
    )
    window.stats_value_column_edit.setText("A")
    window.stats_sigma_column_edit.setText("missing_sigma")
    window.stats_time_series_window_size_spin.setValue(2)
    window.stats_time_series_min_periods_spin.setValue(2)

    window._run_statistics_mode(False, "")

    payload = window._last_result_payloads["statistics_time_series"]
    assert payload["series_method"] == "rolling_std"
    assert payload["sigma_columns"] == {}


def test_statistics_time_series_rejects_embedded_uncertainty_until_supported(window: Any) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A\n1.0(1)\n3.0\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("time_series_rolling"))
    window.stats_time_series_method_combo.setCurrentIndex(
        window.stats_time_series_method_combo.findData("rolling_mean")
    )
    window.stats_value_column_edit.setText("A")
    window.stats_time_series_window_size_spin.setValue(2)
    window.stats_time_series_min_periods_spin.setValue(2)

    with pytest.raises(ValueError, match="embedded uncertainty"):
        window._run_statistics_mode(False, "")


@pytest.mark.parametrize(
    ("test_kind", "data_text", "second_column", "null_value", "alternative", "metric"),
    [
        (
            "paired_t",
            "A B\n10 8\n12 9\n9 10\n11 10\n",
            "B",
            "0",
            "greater",
            "effect.mean_difference_minus_delta0",
        ),
        ("welch_t", "A B\n1 2\n2 2\n3 5\n4 6\n", "B", "0", "less", "effect.mean_a"),
        ("sign_test", "A\n1\n2\n3\n-1\n0\n", "", "0", "two_sided", "effect.effective_n"),
    ],
)
def test_statistics_hypothesis_direct_run_covers_visible_test_kinds(
    window: Any,
    test_kind: str,
    data_text: str,
    second_column: str,
    null_value: str,
    alternative: str,
    metric: str,
) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText(data_text)
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("hypothesis_tests"))
    window.stats_hypothesis_test_combo.setCurrentIndex(window.stats_hypothesis_test_combo.findData(test_kind))
    window.stats_value_column_edit.setText("A")
    if second_column:
        window.stats_hypothesis_b_column_edit.setText(second_column)
    window.stats_hypothesis_null_edit.setText(null_value)
    window.stats_hypothesis_alternative_combo.setCurrentIndex(
        window.stats_hypothesis_alternative_combo.findData(alternative)
    )

    window._run_statistics_mode(False, "")

    assert window._last_result_kind == "statistics_hypothesis_test"
    assert window._last_result_semantic_snapshot["hypothesis_test"]["test_kind"] == test_kind
    metrics = {str(row["metric"]) for row in window._csv_rows}
    assert "p_value" in metrics
    assert metric in metrics


def test_statistics_hypothesis_chi_square_exports_latex(window: Any, tmp_path: Path) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A B\n12 10\n18 20\n20 20\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("hypothesis_tests"))
    window.stats_hypothesis_test_combo.setCurrentIndex(window.stats_hypothesis_test_combo.findData("chi_square_gof"))
    window.stats_value_column_edit.setText("A")
    window.stats_hypothesis_b_column_edit.setText("B")
    window.stats_hypothesis_expected_source_combo.setCurrentIndex(
        window.stats_hypothesis_expected_source_combo.findData("counts")
    )
    tex_path = tmp_path / "hypothesis.tex"

    window._run_statistics_mode(True, str(tex_path))

    assert window._last_result_kind == "statistics_hypothesis_test"
    assert any(row["metric"] == "p_value" for row in window._csv_rows)
    content = tex_path.read_text(encoding="utf-8")
    assert "Hypothesis Test" in content
    assert "Metadata" in content
    assert "chi\\_square\\_gof" in content
    assert "Value columns & A, B" in content


def test_statistics_bootstrap_direct_run_exports_latex_and_distribution_plot(
    window: Any,
    tmp_path: Path,
) -> None:
    window._apply_language("en")
    window.manual_data_edit.setPlainText("A\n1\n2\n3\n4\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("bootstrap_confidence_intervals"))
    window.stats_value_column_edit.setText("A")
    window.stats_bootstrap_target_combo.setCurrentIndex(window.stats_bootstrap_target_combo.findData("mean"))
    window.stats_bootstrap_resamples_spin.setValue(100)
    window.stats_bootstrap_seed_edit.setText("42")
    window.generate_plots_checkbox.setChecked(True)
    window.dcolumn_checkbox.setChecked(True)
    tex_path = tmp_path / "bootstrap.tex"

    window._run_statistics_mode(True, str(tex_path))

    assert tex_path.exists()
    content = tex_path.read_text(encoding="utf-8")
    assert "Bootstrap CI lower" in content
    assert "Bootstrap mean" in content
    assert "\\usepackage{dcolumn}" in content
    assert window.current_stats_figures
    assert window._current_stats_plot_metadata[0]["plot_key"] == "statistics.bootstrap_distribution"
    assert Path(window.current_stats_figures[0]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_statistics_direct_run_preserves_display_values_above_compute_dps(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value_text = "1.12345678901234567890123456789012345678901234567890123456789"
    captured: dict[str, object] = {}

    def fake_display_statistics_result(*_args: object, **kwargs: object) -> None:
        captured["values"] = kwargs["values"]

    with mp.workdps(90):
        rows = [(mp.mpf(value_text),), (mp.mpf("2.0"),)]

    monkeypatch.setattr(window, "_display_statistics_result", fake_display_statistics_result)
    monkeypatch.setattr(window, "_read_precision", lambda: 50)
    monkeypatch.setattr(window, "_collect_fitting_dataset", lambda precision_hint=None: (["A"], rows, [(None,), (None,)]))
    window._apply_language("en")
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("standard"))
    window.stats_value_column_edit.setText("A")
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("mean"))

    window._run_statistics_mode(False, "")

    values = captured["values"]
    assert isinstance(values, list)
    assert mp.nstr(values[0], 80) == value_text


def test_statistics_display_includes_compact_outlier_flags(window: Any) -> None:
    window._apply_language("en")
    result = {
        "mode": "mean_sample",
        "mean": mp.mpf("3.3333333333333333333"),
        "std_mean": mp.mpf("3.3333333333333333333"),
        "std": mp.mpf("5.7735026918962576451"),
        "v_min": mp.mpf("0"),
        "v_max": mp.mpf("10"),
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
        "source_row_ids": ("r1", "r2", "r3"),
        "outlier_flags": [
            {
                "source_row_id": "r3",
                "value": "10.0",
                "metric": "sigma",
                "reason": "statistics.flag.outlier_sigma.residual_gt_3sigma",
            }
        ],
    }

    text, csv_rows = window._format_statistics_display(result, "A", 3)
    rows_by_metric = {str(row["metric"]): row for row in csv_rows}

    assert "Outlier flags:" in text
    assert "value 10.0; source row r3; metric sigma; absolute residual exceeds 3 sigma" in text
    assert rows_by_metric["outlier.sigma.1"]["uncertainty"] == (
        "source row r3; metric sigma; absolute residual exceeds 3 sigma"
    )


def test_statistics_display_includes_trimmed_mean(window: Any) -> None:
    window._apply_language("en")
    result = {
        "mode": "descriptive",
        "mean": mp.mpf("22"),
        "trimmed_mean": mp.mpf("3"),
        "std_mean": mp.mpf("19.50640920313116"),
        "std": mp.mpf("43.617656975128774"),
        "variance": mp.mpf("1902.5"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("100"),
        "method_label": "Descriptive statistics (sample)",
        "dropped": 0,
    }

    text, csv_rows = window._format_statistics_display(result, "A", 5)
    rows_by_metric = {str(row["metric"]): row for row in csv_rows}

    assert "Trimmed mean = 3.0" in text
    assert rows_by_metric["trimmed_mean"]["value"] == "3.0"


def test_statistics_display_units_reach_text_csv_and_batch_headers(window: Any) -> None:
    window._apply_language("en")
    result = {
        "mode": "mean_sample",
        "mean": mp.mpf("2"),
        "std_mean": mp.mpf("0.5"),
        "std": mp.mpf("1"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("3"),
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
    }
    units = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"A": {"unit": "m"}},
        "outputs": {"mean": {"unit": "m"}, "std_mean": {"unit": "m"}},
    }

    text, csv_rows = window._format_statistics_display(result, "A", 3, units=units)
    rows_by_metric = {str(row["metric"]): row for row in csv_rows}

    assert "Unit: m" in text
    assert rows_by_metric["mean"]["value_unit"] == "m"
    assert rows_by_metric["mean"]["uncertainty_unit"] == "m"

    window._display_statistics_batches(
        [
            {
                "index": 1,
                "batch_index": 1,
                "value_col": "A",
                "row_count": 3,
                "result": result,
                "units": units,
            }
        ],
        "A",
        render_plots=False,
    )

    assert window._csv_headers == ["batch", "metric", "value", "uncertainty", "value_unit", "uncertainty_unit"]


def test_statistics_single_plot_fallback_applies_value_unit(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import shared.plotting as plotting

    window._apply_language("en")
    captured: dict[str, object] = {}

    def fake_render(spec: object) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nunit"

    monkeypatch.setattr(plotting, "render_statistics_plot_from_spec", fake_render)

    png = window._render_statistics_plot(
        [mp.mpf("1"), mp.mpf("2")],
        None,
        {"mean": mp.mpf("1.5"), "std_mean": mp.mpf("0.5"), "std": mp.mpf("0.7")},
        value_unit="m",
    )

    spec = captured["spec"]
    assert png == b"\x89PNG\r\n\x1a\nunit"
    assert spec.labels.y_axis == "Value [m]"  # type: ignore[attr-defined]


def test_statistics_single_column_batch_with_column_index_is_not_column_scoped(window: Any) -> None:
    window._apply_language("en")
    result = {
        "mode": "mean_sample",
        "mean": mp.mpf("2"),
        "std_mean": mp.mpf("0.5773502691896258"),
        "std": mp.mpf("1"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("3"),
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
    }
    batch = {
        "index": 1,
        "column_index": 1,
        "batch_index": 1,
        "value_col": "A",
        "row_count": 3,
        "result": result,
    }

    window._display_statistics_batches([batch], "A", render_plots=False)

    assert window._csv_headers == ["batch", "metric", "value", "uncertainty"]
    assert all("column" not in row for row in window._csv_rows)
    text = window.result_edit.toPlainText()
    assert "=== Statistics: Batch 1 ===" in text
    assert "Column A" not in text


def test_statistics_panel_uses_compact_workbench_card(window: Any) -> None:
    assert window.stats_box.objectName() == "statistics_mode_view"
    assert window.stats_box.property("datalab_statistics_panel") is True
    assert window.stats_box.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
    uncapped_widget = QWidget()
    assert window.stats_box.maximumHeight() == uncapped_widget.maximumHeight()

    card = window.stats_box.findChild(QFrame, "statistics_settings_card")

    assert card is not None
    assert card.property("datalab_workbench_section_role") == "statistics"
    card_children = card.findChildren(QWidget)
    assert window.stats_value_column_edit.parentWidget() is card or (
        window.stats_value_column_edit.parentWidget() in card_children
    )
    assert window.stats_mode_combo.parentWidget() is card or (
        window.stats_mode_combo.parentWidget() in card_children
    )


def test_workbench_section_card_helper_builds_localized_host(window: Any, qtbot: Any) -> None:
    from app_desktop.views import helpers as view_helpers

    section = view_helpers.make_workbench_section_card_view(
        window,
        object_name="test_mode_view",
        view_module="test.module",
        card_object_name="test_settings_card",
        role="test",
        title_zh="测试设置",
        title_en="Test settings",
        description_zh="选择测试参数。",
        description_en="Choose test parameters.",
        maximum_height=220,
    )
    qtbot.addWidget(section.host)

    assert section.host.objectName() == "test_mode_view"
    assert section.host.property("datalab_view_module") == "test.module"
    assert section.host.property("datalab_workbench_section_host") is True
    assert section.host.maximumHeight() == 220
    assert section.card.objectName() == "test_settings_card"
    assert section.card.property("datalab_workbench_section_role") == "test"
    assert section.title_label.text() == "测试设置"
    assert section.description_label.text() == "选择测试参数。"

    window._apply_language("en")

    assert section.title_label.text() == "Test settings"
    assert section.description_label.text() == "Choose test parameters."
