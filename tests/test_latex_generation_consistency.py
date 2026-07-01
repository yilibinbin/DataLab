#!/usr/bin/env python3
"""
Consistency test for LaTeX generation across Web and Desktop implementations.

This script verifies that:
1. Extrapolation tables generate consistent LaTeX preamble
2. Error propagation tables generate consistent LaTeX preamble
3. Fitting tables generate consistent LaTeX preamble
4. Statistical tables generate consistent LaTeX preamble
5. siunitx and dcolumn configurations are aligned
"""

import sys
import tempfile
from pathlib import Path

import mpmath as mp
from data_extrapolation_latex_latest import (
    generate_latex_table,
    generate_error_propagation_table,
    parse_uncertainty_format,
)
from statistics_utils import (
    generate_statistics_bootstrap_latex,
    generate_statistics_latex,
    generate_statistics_latex_batches,
    generate_statistics_time_series_latex,
)
from app_web.server import _generate_fitting_latex
from datalab_latex.latex_tables_common import (
    build_statistics_latex_diagnostic_rows,
    build_statistics_latex_summary_rows,
)


def extract_preamble(tex_content: str) -> list[str]:
    """Extract preamble lines up to \\begin{document}."""
    lines = tex_content.split('\n')
    preamble = []
    for line in lines:
        if '\\begin{document}' in line:
            break
        preamble.append(line.strip())
    return [line for line in preamble if line]  # Remove empty lines


def check_preamble_packages(preamble: list[str], label: str):
    """Check that required packages are in preamble."""
    packages = [
        'amsmath',
        'array',
        'booktabs',
        'threeparttable',
        'siunitx',
        'dcolumn',  # When use_dcolumn=True
    ]

    found = {}
    for pkg in packages:
        found[pkg] = any(pkg in line for line in preamble)

    print(f"\n[{label}] Package check:")
    for pkg, present in found.items():
        status = "✓" if present else "✗"
        print(f"  {status} {pkg}")

    return found


def check_sisetup_config(tex_content: str, label: str):
    """Check sisetup configuration."""
    lines = tex_content.split('\n')
    sisetup_found = False
    sisetup_lines = []

    for i, line in enumerate(lines):
        if '\\sisetup{' in line:
            sisetup_found = True
            j = i
            while j < len(lines) and '}' not in lines[j]:
                sisetup_lines.append(lines[j].strip())
                j += 1
            sisetup_lines.append(lines[j].strip())
            break

    print(f"\n[{label}] sisetup configuration:")
    if sisetup_found:
        for line in sisetup_lines:
            print(f"  {line}")
    else:
        print("  ✗ sisetup not found")

    return '\n'.join(sisetup_lines)


def check_dcolumn_definition(tex_content: str, label: str):
    """Check dcolumn column type definition."""
    lines = tex_content.split('\n')
    for line in lines:
        if '\\newcolumntype{d}' in line:
            print(f"\n[{label}] dcolumn definition:")
            print(f"  {line.strip()}")
            return line.strip()

    print(f"\n[{label}] dcolumn definition: ✗ not found")
    return None


def _build_extrapolation_latex_content() -> str:
    """Generate an extrapolation LaTeX file and return its content."""

    headers = ["A", "B", "C"]
    data_rows = [
        (mp.mpf("1.0"), mp.mpf("1.1"), mp.mpf("1.2")),
        (mp.mpf("2.0"), mp.mpf("2.1"), mp.mpf("2.2")),
    ]
    extrapolated_results = [
        (mp.mpf("0.9"), mp.mpf("0.05")),
        (mp.mpf("1.9"), mp.mpf("0.05")),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "extrap.tex"

        generate_latex_table(
            headers,
            data_rows,
            extrapolated_results,
            tex_path,
            caption="Test Extrapolation",
            precision=10,
            use_dcolumn=True,
            latex_group_size=3,
        )

        content = tex_path.read_text(encoding="utf-8")
        return content


def test_extrapolation_latex():
    """Test extrapolation table LaTeX generation."""
    content = _build_extrapolation_latex_content()
    preamble = extract_preamble(content)
    found = check_preamble_packages(preamble, "Extrapolation")
    assert found["amsmath"]
    assert found["booktabs"]
    assert found["threeparttable"]
    assert found["siunitx"]
    assert found["dcolumn"]
    assert check_dcolumn_definition(content, "Extrapolation") is not None


def _build_error_propagation_latex_content() -> str:
    """Generate an error propagation LaTeX file and return its content."""

    headers = ["A", "B"]
    parsed_data = [
        [parse_uncertainty_format("1.0"), parse_uncertainty_format("1.1")],
        [parse_uncertainty_format("2.0"), parse_uncertainty_format("2.1")],
    ]
    results = [
        parse_uncertainty_format("2.1(5)"),
        parse_uncertainty_format("4.1(5)"),
    ]
    constants = {}
    formula_str = "A + B"

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "error.tex"

        generate_error_propagation_table(
            headers,
            parsed_data,
            results,
            constants,
            formula_str,
            tex_path,
            caption="Test Error Propagation",
            use_dcolumn=True,
            precision=10,
            latex_group_size=3,
        )

        content = tex_path.read_text(encoding="utf-8")
        return content


def test_error_propagation_latex():
    """Test error propagation table LaTeX generation."""
    content = _build_error_propagation_latex_content()
    preamble = extract_preamble(content)
    found = check_preamble_packages(preamble, "Error Propagation")
    assert found["amsmath"]
    assert found["booktabs"]
    assert found["threeparttable"]
    assert found["siunitx"]
    assert found["dcolumn"]
    assert check_dcolumn_definition(content, "Error Propagation") is not None


def _build_fitting_latex_content() -> str:
    """Generate fitting LaTeX content and return it."""

    params = [
        {
            "name": "param1",
            "value": mp.mpf("1.234"),
            "uncertainty": mp.mpf("0.056"),
            "value_raw": mp.mpf("1.234"),
            "uncertainty_raw": mp.mpf("0.056"),
            "latex": "1.234(56)",
        },
        {
            "name": "param2",
            "value": mp.mpf("2.345"),
            "uncertainty": mp.mpf("0.067"),
            "value_raw": mp.mpf("2.345"),
            "uncertainty_raw": mp.mpf("0.067"),
            "latex": "2.345(67)",
        },
    ]

    metrics = {
        "chi2": mp.mpf("0.123"),
        "r2": mp.mpf("0.999"),
    }

    content = _generate_fitting_latex(
        best_label="Linear fit",
        params=params,
        metrics=metrics,
        use_dcolumn=True,
        caption="Test Fitting",
        latex_precision=10,
        latex_group_size=3,
    )
    return content


def test_fitting_latex():
    """Test fitting table LaTeX generation."""
    content = _build_fitting_latex_content()
    preamble = extract_preamble(content)
    found = check_preamble_packages(preamble, "Fitting")
    assert found["amsmath"]
    assert found["booktabs"]
    assert found["threeparttable"]
    assert found["siunitx"]
    assert found["dcolumn"]
    assert check_dcolumn_definition(content, "Fitting") is not None


def _build_statistics_latex_content() -> str:
    """Generate statistics LaTeX content and return it."""

    data_rows = [
        (mp.mpf("1.0"), mp.mpf("1.1")),
        (mp.mpf("2.0"), mp.mpf("2.1")),
    ]
    sigma_rows = [
        (mp.mpf("0.05"), mp.mpf("0.06")),
        (mp.mpf("0.05"), mp.mpf("0.06")),
    ]
    result = {
        "mean": mp.mpf("1.5"),
        "std_mean": mp.mpf("0.5"),
        "std": mp.mpf("0.7071"),
        "v_min": mp.mpf("1.0"),
        "v_max": mp.mpf("2.0"),
        "method_label": "Test",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "stats.tex"

        generate_statistics_latex(
            value_col="Data",
            data_rows=data_rows,
            sigma_rows=sigma_rows,
            result=result,
            digits=10,
            tex_path=tex_path,
            use_dcolumn=True,
            caption="Test Statistics",
            latex_group_size=3,
        )

        content = tex_path.read_text(encoding="utf-8")
        return content


def test_statistics_latex():
    """Test statistics table LaTeX generation."""
    content = _build_statistics_latex_content()
    preamble = extract_preamble(content)
    found = check_preamble_packages(preamble, "Statistics")
    assert found["amsmath"]
    assert found["booktabs"]
    assert found["threeparttable"]
    assert found["siunitx"]
    assert found["dcolumn"]
    assert check_dcolumn_definition(content, "Statistics") is not None


def test_statistics_latex_escape_title_and_caption_once(tmp_path: Path):
    tex_path = tmp_path / "stats-single-escaped.tex"
    result = {
        "mean": mp.mpf("1.5"),
        "std_mean": mp.mpf("0.5"),
        "std": mp.mpf("0.7071067811865475"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("2"),
        "method_label": "Method_with_underscore",
    }

    generate_statistics_latex(
        value_col="A_value",
        data_rows=[(mp.mpf("1"),), (mp.mpf("2"),)],
        sigma_rows=[(None,), (None,)],
        result=result,
        digits=10,
        tex_path=str(tex_path),
        use_dcolumn=True,
        caption=None,
        uncertainty_digits=2,
        latex_group_size=3,
    )
    content = tex_path.read_text(encoding="utf-8")
    assert "Method\\_with\\_underscore" in content
    assert "Statistical summary for A\\_value" in content
    assert "Statistical summary for A_value" not in content
    assert "\\textbackslash{}\\_value" not in content

    tex_path_with_caption = tmp_path / "stats-single-custom-caption.tex"
    generate_statistics_latex(
        value_col="A_value",
        data_rows=[(mp.mpf("1"),), (mp.mpf("2"),)],
        sigma_rows=[(None,), (None,)],
        result=result,
        digits=10,
        tex_path=str(tex_path_with_caption),
        use_dcolumn=True,
        caption="Caption_with_underscore",
        uncertainty_digits=2,
        latex_group_size=3,
    )
    custom_content = tex_path_with_caption.read_text(encoding="utf-8")
    assert "Caption\\_with\\_underscore" in custom_content
    assert "Caption_with_underscore" not in custom_content
    assert "\\textbackslash{}\\_with" not in custom_content


def test_statistics_latex_units_use_text_headers_and_summary_unit_column(tmp_path: Path):
    tex_path = tmp_path / "stats-units.tex"
    units = {
        "enabled": True,
        "mode": "display_only",
        "inputs": {"Data": {"unit": "m"}},
        "outputs": {
            "mean": {"unit": "m"},
            "std_mean": {"unit": "cm"},
            "std": {"unit": "m"},
            "min": {"unit": "m"},
            "max": {"unit": "m"},
        },
    }

    generate_statistics_latex(
        value_col="Data",
        data_rows=[(mp.mpf("1.0"),), (mp.mpf("2.0"),)],
        sigma_rows=[(mp.mpf("0.1"),), (mp.mpf("0.2"),)],
        result={
            "mean": mp.mpf("1.5"),
            "std_mean": mp.mpf("0.15"),
            "std": mp.mpf("0.7071067811865475"),
            "v_min": mp.mpf("1.0"),
            "v_max": mp.mpf("2.0"),
            "method_label": "Arithmetic mean",
        },
        digits=10,
        tex_path=str(tex_path),
        use_dcolumn=True,
        uncertainty_digits=2,
        latex_group_size=3,
        units=units,
    )

    content = tex_path.read_text(encoding="utf-8")

    assert "\\multicolumn{1}{c}{Data (m)}" in content
    assert "Entry & Unit & \\multicolumn{1}{c}{Value}" in content
    assert "Mean & m; uncertainty cm &" in content
    assert "Std. error & cm &" in content
    assert "Std. dev. & m &" in content
    assert "\\begin{tabular}{l l d" in content


def test_statistics_latex_batches_use_per_batch_units(tmp_path: Path):
    tex_path = tmp_path / "stats-batch-units.tex"
    generate_statistics_latex_batches(
        "Signal",
        [
            {
                "index": 1,
                "value_col": "Signal",
                "values": [mp.mpf("1.0"), mp.mpf("2.0")],
                "sigmas": [None, None],
                "result": {
                    "mean": mp.mpf("1.5"),
                    "std_mean": mp.mpf("0.5"),
                    "std": mp.mpf("0.7071067811865475"),
                    "v_min": mp.mpf("1.0"),
                    "v_max": mp.mpf("2.0"),
                    "method_label": "Arithmetic mean",
                },
                "units": {
                    "enabled": True,
                    "mode": "display_only",
                    "inputs": {"Signal": {"unit": "V"}},
                    "outputs": {"mean": {"unit": "V"}, "std_mean": {"unit": "V"}},
                },
            }
        ],
        digits=10,
        tex_path=str(tex_path),
        use_dcolumn=False,
        caption="Statistics with units",
        uncertainty_digits=2,
        latex_group_size=3,
    )

    content = tex_path.read_text(encoding="utf-8")

    assert "\\multicolumn{1}{c}{Signal (V)}" in content
    assert "Entry & Unit & \\multicolumn{1}{c}{Value}" in content
    assert "Mean & V &" in content
    assert "\\begin{tabular}{l l S" in content


def test_statistics_bootstrap_latex_uses_shared_number_formatting(tmp_path: Path):
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    envelope = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "source_row_ids": ["1", "2", "3", "4"],
                "value_column": "A_value",
                "column_index": 1,
                "target_statistic": "mean",
                "confidence_level": "0.95",
                "resample_count": 100,
                "seed": 42,
                "sample_mode": "sample",
            },
            options=JobOptions(precision_digits=40),
            request_id="bootstrap-latex",
        )
    )
    assert envelope.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(
        "statistics_bootstrap",
        envelope.payload,
        precision={"compute_digits": 40, "uncertainty_digits": 2},
    )
    assert snapshot is not None

    tex_path = tmp_path / "bootstrap.tex"
    generate_statistics_bootstrap_latex(
        snapshot,
        str(tex_path),
        use_dcolumn=True,
        digits=10,
        caption="Bootstrap summary",
        uncertainty_digits=2,
        latex_group_size=3,
    )

    content = tex_path.read_text(encoding="utf-8")
    preamble = extract_preamble(content)
    found = check_preamble_packages(preamble, "Statistics Bootstrap")
    assert found["booktabs"]
    assert found["siunitx"]
    assert found["dcolumn"]
    assert check_dcolumn_definition(content, "Statistics Bootstrap") is not None
    assert "Bootstrap CI lower" in content
    assert "Bootstrap mean" in content
    assert "Value column: \\texttt{A\\_value}" in content
    assert "bootstrap\\_confidence\\_intervals" in content


def test_statistics_bootstrap_latex_renders_unit_column_when_units_exist(tmp_path: Path):
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    envelope = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "source_row_ids": ["1", "2", "3", "4"],
                "value_column": "A_value",
                "target_statistic": "mean",
                "confidence_level": "0.95",
                "resample_count": 100,
                "seed": 42,
                "sample_mode": "sample",
                "units": {
                    "enabled": True,
                    "mode": "display_only",
                    "outputs": {"bootstrap_ci_lower": {"unit": "m"}, "result": {"unit": "m"}},
                },
            },
            options=JobOptions(precision_digits=40),
            request_id="bootstrap-latex-units",
        )
    )
    assert envelope.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot("statistics_bootstrap", envelope.payload)
    assert snapshot is not None

    tex_path = tmp_path / "bootstrap-units.tex"
    generate_statistics_bootstrap_latex(snapshot, str(tex_path), use_dcolumn=True, digits=10)

    content = tex_path.read_text(encoding="utf-8")
    assert "Metric & Unit &" in content
    assert "Bootstrap CI lower & m &" in content


def test_statistics_time_series_latex_uses_shared_number_formatting(tmp_path: Path):
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    envelope = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "time_series_rolling",
                "series_method": "rolling_mean",
                "values": ["1.00", "2.00", "4.00"],
                "sigmas": ["0.10", "0.20", "0.30"],
                "source_row_ids": ["1", "2", "3"],
                "time_labels": ["day_1", "day_2", "day_3"],
                "value_column": "A_value",
                "sigma_column": "A_sigma",
                "time_column": "t_label",
                "window_size": 2,
                "min_periods": 2,
                "alignment": "right",
            },
            options=JobOptions(precision_digits=40),
            request_id="time-series-latex",
        )
    )
    assert envelope.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(
        "statistics_time_series",
        envelope.payload,
        precision={"compute_digits": 40, "uncertainty_digits": 2},
    )
    assert snapshot is not None

    tex_path = tmp_path / "time-series.tex"
    generate_statistics_time_series_latex(
        snapshot,
        str(tex_path),
        use_dcolumn=True,
        digits=10,
        caption="Time_series_summary",
        uncertainty_digits=2,
        latex_group_size=3,
    )

    content = tex_path.read_text(encoding="utf-8")
    preamble = extract_preamble(content)
    found = check_preamble_packages(preamble, "Statistics Time Series")
    assert found["booktabs"]
    assert found["siunitx"]
    assert found["dcolumn"]
    assert check_dcolumn_definition(content, "Statistics Time Series") is not None
    assert "Time-Series Statistics" in content
    assert "Time\\_series\\_summary" in content
    assert "A\\_value" in content
    assert "day\\_2" in content


def test_statistics_time_series_latex_renders_units_in_text_column(tmp_path: Path):
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    envelope = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "time_series_rolling",
                "series_method": "rolling_mean",
                "values": ["1.00", "2.00", "4.00"],
                "source_row_ids": ["1", "2", "3"],
                "value_column": "A_value",
                "window_size": 2,
                "min_periods": 2,
                "units": {
                    "enabled": True,
                    "mode": "display_only",
                    "outputs": {"A_value": {"unit": "m"}},
                },
            },
            options=JobOptions(precision_digits=40),
            request_id="time-series-latex-units",
        )
    )
    assert envelope.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot("statistics_time_series", envelope.payload)
    assert snapshot is not None

    tex_path = tmp_path / "time-series-units.tex"
    generate_statistics_time_series_latex(snapshot, str(tex_path), use_dcolumn=True, digits=10)

    content = tex_path.read_text(encoding="utf-8")
    assert "Column & Unit & Row & Time" in content
    assert "A\\_value & m &" in content
    assert "insufficient\\_window" in content


def test_statistics_time_series_latex_multicolumn_rows_match_table_width(tmp_path: Path):
    from copy import deepcopy

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    payloads = []
    for column, values in (("A", ["1", "2", "3"]), ("B", ["10", "20", "40"])):
        envelope = service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs={
                    "workflow_mode": "time_series_rolling",
                    "series_method": "rolling_median",
                    "values": values,
                    "source_row_ids": ["1", "2", "3"],
                    "time_labels": ["1", "2", "3"],
                    "value_column": column,
                    "column_index": len(payloads) + 1,
                    "time_column": "t",
                    "window_size": 2,
                    "min_periods": 1,
                    "alignment": "right",
                },
                options=JobOptions(precision_digits=40),
                request_id=f"time-series-latex-{column}",
            )
        )
        assert envelope.status is ResultStatus.SUCCEEDED
        payloads.append(deepcopy(envelope.payload))

    combined = dict(payloads[0])
    combined["value_columns"] = ["A", "B"]
    combined["columns"] = [column for payload in payloads for column in payload["columns"]]
    snapshot = build_statistics_result_snapshot(
        "statistics_time_series",
        combined,
        precision={"compute_digits": 40, "uncertainty_digits": 2},
    )
    assert snapshot is not None

    tex_path = tmp_path / "time-series-multi.tex"
    generate_statistics_time_series_latex(
        snapshot,
        str(tex_path),
        use_dcolumn=False,
        digits=8,
        caption="Time series multi",
        uncertainty_digits=2,
        latex_group_size=0,
    )

    content = tex_path.read_text(encoding="utf-8")
    assert "A & 1 & 1" in content
    assert "B & 1 & 1" in content
    data_lines = [
        line
        for line in content.splitlines()
        if (line.startswith("A & ") or line.startswith("B & ")) and line.endswith(r"\\")
    ]
    assert len(data_lines) == 6
    assert all(line.count("&") == 7 for line in data_lines)


def test_statistics_latex_batches_use_per_column_values_and_shared_formatting(tmp_path: Path):
    batches = [
        {
            "index": 1,
            "value_col": "B",
            "values": [mp.mpf("10"), mp.mpf("20")],
            "sigmas": [mp.mpf("0.1"), mp.mpf("0.2")],
            "rows": [(mp.mpf("1"), mp.mpf("10")), (mp.mpf("2"), mp.mpf("20"))],
            "sigma_rows": [(None, mp.mpf("0.1")), (None, mp.mpf("0.2"))],
            "result": {
                "mean": mp.mpf("15"),
                "std_mean": mp.mpf("5"),
                "std": mp.mpf("7.0710678118654755"),
                "v_min": mp.mpf("10"),
                "v_max": mp.mpf("20"),
                "method_label": "Arithmetic mean (sample)",
            },
        },
        {
            "index": 2,
            "value_col": "A",
            "values": [mp.mpf("1"), mp.mpf("2")],
            "sigmas": [mp.mpf("0.01"), mp.mpf("0.02")],
            "rows": [(mp.mpf("1"), mp.mpf("10")), (mp.mpf("2"), mp.mpf("20"))],
            "sigma_rows": [(mp.mpf("0.01"), None), (mp.mpf("0.02"), None)],
            "result": {
                "mean": mp.mpf("1.5"),
                "std_mean": mp.mpf("0.5"),
                "std": mp.mpf("0.7071067811865475"),
                "v_min": mp.mpf("1"),
                "v_max": mp.mpf("2"),
                "method_label": "Arithmetic mean (sample)",
            },
        },
    ]

    for use_dcolumn in (False, True):
        tex_path = tmp_path / f"stats-multi-{'dcolumn' if use_dcolumn else 'siunitx'}.tex"
        generate_statistics_latex_batches(
            "B, A",
            batches,
            digits=10,
            tex_path=str(tex_path),
            use_dcolumn=use_dcolumn,
            caption="Multi-column statistics",
            uncertainty_digits=2,
            latex_group_size=0,
        )
        content = tex_path.read_text(encoding="utf-8")

        assert "Value column: \\texttt{B}" in content
        assert "Value column: \\texttt{A}" in content
        assert "\\multicolumn{1}{c}{B}" in content
        assert "\\multicolumn{1}{c}{A}" in content
        assert "Col 2" not in content
        assert "\\usepackage{dcolumn}" in content if use_dcolumn else "\\usepackage{dcolumn}" not in content
        assert "\\usepackage{siunitx}" in content


def test_statistics_latex_batches_escape_title_and_caption_once(tmp_path: Path):
    tex_path = tmp_path / "stats-batch-escaped.tex"
    generate_statistics_latex_batches(
        "A_value",
        [
            {
                "index": 1,
                "value_col": "A_value",
                "values": [mp.mpf("1"), mp.mpf("2")],
                "sigmas": [None, None],
                "result": {
                    "mean": mp.mpf("1.5"),
                    "std_mean": mp.mpf("0.5"),
                    "std": mp.mpf("0.7071067811865475"),
                    "v_min": mp.mpf("1"),
                    "v_max": mp.mpf("2"),
                    "method_label": "Arithmetic mean (sample)",
                },
            }
        ],
        digits=10,
        tex_path=str(tex_path),
        use_dcolumn=True,
        caption="Caption_with_underscore",
        uncertainty_digits=2,
        latex_group_size=3,
    )

    content = tex_path.read_text(encoding="utf-8")

    assert "Statistical Summary (A\\_value)" in content
    assert "Caption\\_with\\_underscore: A\\_value" in content
    assert "Caption_with_underscore: A_value" not in content
    assert "\\textbackslash{}\\_value" not in content


def test_statistics_latex_summary_rows_use_shared_non_ui_builder():
    result = {
        "mean": mp.mpf("1.5"),
        "std_mean": mp.mpf("0.25"),
        "std": mp.mpf("0.5"),
        "v_min": mp.mpf("1.0"),
        "v_max": mp.mpf("2.0"),
    }
    calls = []

    def format_value(value, sigma, is_input):
        calls.append((value, sigma, is_input))
        suffix = "" if sigma is None else f"±{sigma}"
        return f"{value}{suffix}"

    rows = build_statistics_latex_summary_rows(result, format_value=format_value)

    assert rows == [
        ("Mean", "1.5±0.25"),
        ("Std. error", "0.25"),
        ("Min", "1.0"),
        ("Max", "2.0"),
        ("Std. dev.", "0.5"),
    ]
    assert calls[0] == (result["mean"], result["std_mean"], False)
    assert all(call[2] is True for call in calls[1:])


def test_statistics_latex_summary_rows_missing_mean_does_not_raise():
    rows = build_statistics_latex_summary_rows({}, format_value=lambda value, sigma, is_input: str(value))

    assert rows == []


def test_statistics_latex_summary_rows_include_warning_diagnostics():
    result = {
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "analysis_rows": [
            {
                "key": "warning.zero_sigma_anchor",
                "label_key": "statistics.warning",
                "value": "Detected zero sigma.",
                "severity": "warning",
                "render_group": "diagnostic",
                "message_key": "statistics.warning.zero_sigma_anchor",
            },
            {
                "key": "plot.mean_band_annotation",
                "label_key": "statistics.plot.mean_band_annotation",
                "severity": "warning",
                "render_group": "plot_annotation",
                "message_key": "statistics.plot.mean_band_annotation",
            },
        ],
    }

    diagnostic_rows = build_statistics_latex_diagnostic_rows(
        result,
        format_text=lambda text: text.replace("_", r"\_"),
    )
    summary_rows = build_statistics_latex_summary_rows(
        result,
        format_value=lambda value, sigma, is_input: str(value),
        format_text=lambda text: text.replace("_", r"\_"),
    )

    assert diagnostic_rows == [
        ("Warning", r"\multicolumn{1}{l}{Detected zero sigma.}")
    ]
    assert summary_rows[-1] == diagnostic_rows[0]
    assert "mean_band_annotation" not in repr(diagnostic_rows)
    assert "mean_band_annotation" not in repr(summary_rows)
    assert "statistics.warning.zero" not in repr(summary_rows)


def test_statistics_latex_summary_rows_include_outlier_row_flags():
    result = {
        "mean": mp.mpf("3.3333333333333333333"),
        "std_mean": mp.mpf("3.3333333333333333333"),
        "std": mp.mpf("5.7735026918962576451"),
        "v_min": mp.mpf("0"),
        "v_max": mp.mpf("10"),
        "analysis_rows": [
            {
                "key": "outlier.sigma.1",
                "label_key": "statistics.flag.outlier.sigma",
                "value": "10.0",
                "source": "sigma",
                "row_index": "r3",
                "severity": "info",
                "render_group": "row_flag",
                "message_key": "statistics.flag.outlier_sigma.residual_gt_3sigma",
            }
        ],
    }

    rows = build_statistics_latex_diagnostic_rows(result)

    assert rows == [
        (
            "Outlier flag",
            r"\multicolumn{1}{l}{value 10.0; source row r3; metric sigma; absolute residual exceeds 3 sigma}",
        )
    ]


def test_statistics_latex_summary_rows_include_descriptive_metrics():
    result = {
        "mean": mp.mpf("2.5"),
        "std_mean": mp.mpf("0.6454972243679028142"),
        "std": mp.mpf("1.2909944487358056284"),
        "variance": mp.mpf("1.6666666666666666667"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("4"),
        "count": 4,
        "trimmed_mean": mp.mpf("2.5"),
        "median": mp.mpf("2.5"),
        "q1": mp.mpf("1.75"),
        "q3": mp.mpf("3.25"),
        "iqr": mp.mpf("1.5"),
        "mad": mp.mpf("1"),
        "skewness": mp.mpf("0"),
        "excess_kurtosis": mp.mpf("-1.2"),
    }

    rows = build_statistics_latex_summary_rows(
        result,
        format_value=lambda value, sigma, is_input: str(value) if sigma is None else f"{value}±{sigma}",
    )

    labels = [label for label, _value in rows]
    assert labels == [
        "Mean",
        "Trimmed mean",
        "Std. error",
        "Min",
        "Max",
        "Std. dev.",
        "Count",
        "Variance",
        "Median",
        "Q1",
        "Q3",
        "IQR",
        "MAD",
        "Skewness",
        "Excess kurtosis",
    ]
    assert ("Median", "2.5") in rows
    assert ("Trimmed mean", "2.5") in rows
    assert ("Excess kurtosis", "-1.2") in rows


def test_statistics_latex_summary_rows_include_weighted_consistency_metrics():
    result = {
        "mean": mp.mpf(16) / 9,
        "std_mean": mp.mpf("0.6666666666666666667"),
        "std": mp.mpf("1.3333333333333333333"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("4"),
        "effective_n": mp.mpf(81) / 33,
        "weighted_chi_square": mp.mpf(17) / 9,
        "weighted_consistency_dof": 2,
        "weighted_reduced_chi_square": mp.mpf(17) / 18,
        "birge_ratio": mp.sqrt(mp.mpf(17) / 18),
    }

    rows = build_statistics_latex_summary_rows(
        result,
        format_value=lambda value, sigma, is_input: str(value) if sigma is None else f"{value}±{sigma}",
    )
    rows_by_label = {label: value for label, value in rows}

    assert rows_by_label["Weighted chi-square"] == str(mp.mpf(17) / 9)
    assert rows_by_label["Weighted consistency dof"] == "2"
    assert rows_by_label["Weighted reduced chi-square"] == str(mp.mpf(17) / 18)
    assert rows_by_label["Birge ratio"] == str(mp.sqrt(mp.mpf(17) / 18))


def test_statistics_latex_summary_rows_include_confidence_interval_metrics():
    result = {
        "mean": mp.mpf("2.5"),
        "std_mean": mp.mpf("0.5590169943749475"),
        "std": mp.mpf("1.118033988749895"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("4"),
        "mean_ci_lower": mp.mpf("0.445739743239121"),
        "mean_ci_upper": mp.mpf("4.554260256760879"),
        "mean_ci_margin": mp.mpf("2.054260256760879"),
        "mean_ci_confidence_level": mp.mpf("0.95"),
        "mean_sample_se_for_ci": mp.mpf("0.6454972243679028"),
        "mean_ci_dof": 3,
        "mean_ci_critical_value": mp.mpf("3.182446305284263"),
        "mean_ci_method_label": "Student-t mean CI (sample standard deviation)",
    }

    # str(mpf) truncates to mp.dps digits, so pin the precision — otherwise a
    # prior test leaking a higher mp.dps (it is process-global) changes the
    # rendered digit count and this assertion becomes order-dependent.
    with mp.workdps(15):
        rows = build_statistics_latex_summary_rows(
            result,
            format_value=lambda value, sigma, is_input: str(value) if sigma is None else f"{value}±{sigma}",
        )
    rows_by_label = {label: value for label, value in rows}

    assert rows_by_label["Mean CI lower"] == "0.445739743239121"
    assert rows_by_label["Mean CI upper"] == "4.55426025676088"
    assert rows_by_label["Sample SE for CI"] == "0.645497224367903"
    assert rows_by_label["CI method"] == (
        r"\multicolumn{1}{l}{Student-t mean CI (sample standard deviation)}"
    )


def test_statistics_latex_summary_rows_render_descriptive_warning_text_not_message_key():
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics, statistics_payload_to_compute_result

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["7"], "stats_mode": "descriptive", "use_sample": True},
            options=JobOptions(precision_digits=60),
            request_id="latex-descriptive-warning-text",
        )
    )
    stats_result = statistics_payload_to_compute_result(result.payload, result.warnings)

    rows = build_statistics_latex_summary_rows(
        stats_result,
        format_value=lambda value, sigma, is_input: str(value) if sigma is None else f"{value}±{sigma}",
        format_text=lambda text: text.replace("_", r"\_"),
    )
    rendered = "\n".join(value for _label, value in rows)

    assert "Sample descriptive statistics require n>=2" in rendered
    assert "Zero variance" in rendered
    assert "statistics.warning.descriptive" not in rendered


def test_statistics_latex_group_size_zero_keeps_no_grouping_setup_and_diagnostic_row():
    result = {
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "method_label": "Weighted mean (sigma=0 anchor)",
        "warning_codes": ["zero_sigma_anchor"],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "stats-no-grouping.tex"
        generate_statistics_latex(
            value_col="Data",
            data_rows=[(mp.mpf("1.25"),), (mp.mpf("2.5"),)],
            sigma_rows=[(mp.mpf("0"),), (mp.mpf("0.1"),)],
            result=result,
            digits=10,
            tex_path=tex_path,
            use_dcolumn=False,
            caption="Statistics",
            latex_group_size=0,
        )
        content = tex_path.read_text(encoding="utf-8")

    assert "group-digits = false" in content
    assert "group-minimum-digits" not in content
    assert "Detected" in content
    assert r"statistics.warning.zero\_sigma\_anchor" not in content
    assert "statistics.warning.zero_sigma_anchor" not in content


def main():
    """Run all consistency tests."""
    print("\n" + "="*60)
    print("LaTeX Generation Consistency Test Suite")
    print("="*60)

    try:
        extrap_tex = _build_extrapolation_latex_content()
        error_tex = _build_error_propagation_latex_content()
        fitting_tex = _build_fitting_latex_content()
        stats_tex = _build_statistics_latex_content()

        print("\n" + "="*60)
        print("CONSISTENCY SUMMARY")
        print("="*60)

        # Extract sisetup from each
        extrap_sisetup = check_sisetup_config(extrap_tex, "Extrapolation")
        error_sisetup = check_sisetup_config(error_tex, "Error Propagation")
        fitting_sisetup = check_sisetup_config(fitting_tex, "Fitting")
        stats_sisetup = check_sisetup_config(stats_tex, "Statistics")

        if extrap_sisetup == error_sisetup == fitting_sisetup == stats_sisetup:
            print("\n✓ All sisetup configurations are identical")
        else:
            print("\n✗ sisetup configurations differ")

        print("\n✓ All tests completed successfully")

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
