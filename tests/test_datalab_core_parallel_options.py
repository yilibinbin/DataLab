from __future__ import annotations

import mpmath as mp
import pytest


def test_core_parallel_options_normalize_high_precision_numeric_leaves() -> None:
    from datalab_core.parallel_options import normalize_parallel_options

    normalized = normalize_parallel_options(
        {
            "max_workers": 4,
            "reserved_cores": 1,
            "chunk_size": mp.mpf("2.5"),
            "nested": {"tolerance": mp.mpf("1e-30"), "enabled": True},
            "sequence": (mp.mpf("3.25"), "auto", None),
        },
        digit_hint=80,
    )

    assert normalized == {
        "max_workers": 4,
        "reserved_cores": 1,
        "chunk_size": "2.5",
        "nested": {"tolerance": "1.0e-30", "enabled": True},
        "sequence": ["3.25", "auto", None],
    }


def test_core_parallel_options_reject_binary_float_values() -> None:
    from datalab_core.parallel_options import normalize_parallel_options

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        normalize_parallel_options({"max_workers": 2.0}, digit_hint=50)


def test_core_parallel_options_requires_mapping() -> None:
    from datalab_core.parallel_options import normalize_parallel_options

    with pytest.raises(TypeError, match="parallel must be a mapping"):
        normalize_parallel_options(["max_workers"], digit_hint=50)  # type: ignore[arg-type]
