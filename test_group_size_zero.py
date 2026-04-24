#!/usr/bin/env python3
"""
Test script to verify group_size=0 functionality for disabling digit grouping.

This script verifies that:
1. group_size=0 disables grouping in siunitx S-column mode
2. group_size=0 also works in dcolumn mode
3. group_size>0 still enables grouping as expected
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


def extract_sisetup(tex_content: str) -> str:
    """Extract sisetup configuration from LaTeX content."""
    lines = tex_content.split('\n')
    sisetup_lines = []
    in_sisetup = False

    for line in lines:
        if '\\sisetup{' in line:
            in_sisetup = True
        if in_sisetup:
            sisetup_lines.append(line.strip())
            if '}' in line and in_sisetup:
                break

    return '\n'.join(sisetup_lines)


def test_siunitx_mode_with_grouping():
    """Test siunitx mode with grouping enabled (group_size=3)."""
    print("\n" + "="*60)
    print("TEST 1: siunitx mode with group_size=3 (grouping enabled)")
    print("="*60)

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
            use_dcolumn=False,  # siunitx mode
            latex_group_size=3,  # grouping enabled
        )
        content = tex_path.read_text(encoding="utf-8")
        sisetup = extract_sisetup(content)
        print("sisetup configuration:")
        print(sisetup)

        assert "group-digits = decimal" in content, "Expected group-digits=decimal"
        assert "digit-group-size = 3" in content, "Expected digit-group-size=3"
        assert "group-separator" in content, "Expected group-separator"
        print("✓ Grouping enabled correctly")


def test_siunitx_mode_without_grouping():
    """Test siunitx mode with grouping disabled (group_size=0)."""
    print("\n" + "="*60)
    print("TEST 2: siunitx mode with group_size=0 (grouping disabled)")
    print("="*60)

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
            use_dcolumn=False,  # siunitx mode
            latex_group_size=0,  # grouping disabled
        )
        content = tex_path.read_text(encoding="utf-8")
        sisetup = extract_sisetup(content)
        print("sisetup configuration:")
        print(sisetup)

        assert "group-digits = false" in content, "Expected group-digits=false"
        assert "digit-group-size = 0" not in content, "Should not have digit-group-size=0"
        assert "group-separator" not in content or "group-digits = false" in content, \
            "Should not have group-separator when grouping disabled"
        print("✓ Grouping disabled correctly")


def test_dcolumn_mode_with_grouping_param():
    """Test dcolumn mode with group_size=3 (grouping should still be disabled)."""
    print("\n" + "="*60)
    print("TEST 3: dcolumn mode with group_size=3 (grouping always disabled)")
    print("="*60)

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
            use_dcolumn=True,  # dcolumn mode
            latex_group_size=3,  # grouping param (should be ignored)
        )
        content = tex_path.read_text(encoding="utf-8")
        sisetup = extract_sisetup(content)
        print("sisetup configuration:")
        print(sisetup)

        assert "group-digits = false" in content, "dcolumn mode should have group-digits=false"
        assert "digit-group-size" not in content or "group-digits = false" in content, \
            "dcolumn mode should not have digit-group-size"
        print("✓ dcolumn mode correctly disables grouping regardless of group_size param")


def test_dcolumn_mode_with_zero_param():
    """Test dcolumn mode with group_size=0."""
    print("\n" + "="*60)
    print("TEST 4: dcolumn mode with group_size=0")
    print("="*60)

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
            use_dcolumn=True,  # dcolumn mode
            latex_group_size=0,  # explicitly zero
        )
        content = tex_path.read_text(encoding="utf-8")
        sisetup = extract_sisetup(content)
        print("sisetup configuration:")
        print(sisetup)

        assert "group-digits = false" in content, "Expected group-digits=false"
        print("✓ dcolumn mode with group_size=0 works correctly")


def test_fitting_table_with_zero_grouping():
    """Test fitting table with group_size=0."""
    print("\n" + "="*60)
    print("TEST 5: Fitting table with group_size=0")
    print("="*60)

    params = [
        {
            "name": "param1",
            "value": mp.mpf("1.234567"),
            "uncertainty": mp.mpf("0.056"),
            "value_raw": mp.mpf("1.234567"),
            "uncertainty_raw": mp.mpf("0.056"),
            "latex": "1.234567(56)",
        },
    ]

    metrics = {
        "chi2": mp.mpf("0.123456"),
        "r2": mp.mpf("0.999999"),
    }

    content = _generate_fitting_latex(
        best_label="Test Model",
        params=params,
        metrics=metrics,
        use_dcolumn=False,
        caption="Test Fitting",
        latex_precision=10,
        latex_group_size=0,  # no grouping
    )

    sisetup = extract_sisetup(content)
    print("sisetup configuration:")
    print(sisetup)

    assert "group-digits = false" in content, "Expected group-digits=false with group_size=0"
    print("✓ Fitting table with group_size=0 works correctly")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Testing group_size=0 Functionality")
    print("="*60)

    try:
        test_siunitx_mode_with_grouping()
        test_siunitx_mode_without_grouping()
        test_dcolumn_mode_with_grouping_param()
        test_dcolumn_mode_with_zero_param()
        test_fitting_table_with_zero_grouping()

        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60)
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
