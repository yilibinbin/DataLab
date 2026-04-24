"""DataLab performance benchmarks (Phase 4 #24).

Run with::

    pip install -e ".[bench]"
    pytest benchmarks/ -v

pytest-benchmark records timings and prints a summary. CI wires
the JSON output into the performance dashboard so regressions are
visible PR-by-PR. Benchmarks intentionally live outside ``tests/``
so they don't slow down the default ``pytest`` run.
"""
