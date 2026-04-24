from __future__ import annotations

import pytest

from statistics_utils import compute_statistics


def test_statistics_errors_are_bilingual():
    with pytest.raises(ValueError) as excinfo:
        compute_statistics([], [], "mean")
    assert " / " in str(excinfo.value)


def test_web_parse_errors_are_bilingual():
    from app_web.logic import _parse_fit_data, _parse_stats_data

    with pytest.raises(ValueError) as excinfo:
        _parse_fit_data("A\n")  # header-only
    assert " / " in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        _parse_stats_data("A\n")  # header-only
    assert " / " in str(excinfo.value)
