from __future__ import annotations

import pytest


def test_web_weighted_fit_rejects_partial_embedded_uncertainties() -> None:
    from app_web.logic.fitting import _run_fit

    data_text = "\n".join(
        [
            "x y",
            "1 2.0(1)",
            "2 4.0",
            "3 6.0(1)",
        ]
    )

    with pytest.raises(ValueError, match="Row 2 is missing uncertainty|第 2 行缺少不确定度"):
        _run_fit(
            data_text,
            {
                "fit_weighted": "on",
                "fit_mode": "polynomial",
                "fit_poly_degree": "1",
                "fit_x_column": "x",
                "fit_target_column": "y",
            },
        )


def test_web_unweighted_fit_preserves_embedded_data_sigmas() -> None:
    from app_web.logic.fitting import _run_fit

    data_text = "\n".join(
        [
            "x y",
            "1 2.0(1)",
            "2 4.0",
            "3 6.0(1)",
            "4 8.0(1)",
        ]
    )

    result = _run_fit(
        data_text,
        {
            "fit_mode": "polynomial",
            "fit_poly_degree": "1",
            "fit_x_column": "x",
            "fit_target_column": "y",
        },
    )

    assert result.sigma is not None
    assert result.sigma[0] > 0
    assert result.sigma[1] is None
