"""Phase 4 #24 — pin the benchmark scaffolding structure.

Ensures the ``benchmarks/`` dir exists and declares the expected
files, so a refactor can't silently drop performance baselines.
"""

from __future__ import annotations

from pathlib import Path


_BENCHMARKS = Path(__file__).resolve().parent.parent / "benchmarks"


def test_benchmarks_dir_exists():
    assert _BENCHMARKS.is_dir(), (
        "benchmarks/ must exist at the repo root for pytest-benchmark "
        "baselines (Phase 4 #24)"
    )


def test_benchmarks_package_is_importable():
    assert (_BENCHMARKS / "__init__.py").is_file()


def test_benchmark_files_are_present():
    assert (_BENCHMARKS / "test_sampling_performance.py").is_file()
    assert (_BENCHMARKS / "test_fit_performance.py").is_file()


def test_benchmark_sampling_covers_expected_workloads():
    text = (_BENCHMARKS / "test_sampling_performance.py").read_text(encoding="utf-8")
    # Three benchmark cases: serial-cold, cached, parallel
    assert "test_serial_sample" in text
    assert "test_cached_sample" in text
    assert "test_parallel_sample" in text


def test_benchmark_fit_covers_expected_workloads():
    text = (_BENCHMARKS / "test_fit_performance.py").read_text(encoding="utf-8")
    # Fit + auto-fit + render cached/uncached
    assert "test_linear_model_fit" in text
    assert "test_auto_fit" in text
    assert "test_render_fitting_overview_uncached" in text
    assert "test_render_fitting_overview_cached" in text


def test_benchmarks_skip_gracefully_without_pytest_benchmark():
    """When pytest-benchmark isn't installed, the benchmark modules
    must ``pytest.importorskip`` at the top — CI without the bench
    extra must not crash on collection."""
    for filename in ("test_sampling_performance.py", "test_fit_performance.py"):
        text = (_BENCHMARKS / filename).read_text(encoding="utf-8")
        assert 'importorskip("pytest_benchmark")' in text, (
            f"{filename} must skip when pytest-benchmark is absent"
        )
