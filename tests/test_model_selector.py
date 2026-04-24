from __future__ import annotations

import mpmath as mp

from fitting.model_selector import auto_fit_dataset


def test_auto_fit_dataset_includes_sequence_model_and_selects_linear_for_linear_data():
    old_dps = mp.mp.dps
    try:
        mp.mp.dps = 80
        x_series = [mp.mpf(v) for v in ["1", "2", "3", "4"]]
        y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]

        summary = auto_fit_dataset(x_series, y_series, precision=80)
        assert any(result.identifier == "SEQ" for result in summary.results)
        assert summary.best_model == "M1"
    finally:
        mp.mp.dps = old_dps
