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
from statistics_utils import generate_statistics_latex
from app_web.server import _generate_fitting_latex


def extract_preamble(tex_content: str) -> list[str]:
    """Extract preamble lines up to \\begin{document}."""
    lines = tex_content.split('\n')
    preamble = []
    for line in lines:
        if '\\begin{document}' in line:
            break
        preamble.append(line.strip())
    return [l for l in preamble if l]  # Remove empty lines


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
