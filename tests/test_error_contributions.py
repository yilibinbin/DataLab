from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import mpmath as mp
import pytest

from shared.error_contributions import (
    aggregate_contribution_summary,
    aggregate_contribution_variances,
    contribution_summary_rows,
    render_error_contribution_plot,
)


def test_aggregate_contribution_variances_ignores_invalid_values() -> None:
    results = [
        SimpleNamespace(contributions={"B": mp.mpf("3"), "A": "1.5", "bad": object()}),
        SimpleNamespace(contributions={"A": mp.mpf("0.5"), "skip": None}),
        SimpleNamespace(contributions={}),
        SimpleNamespace(),
    ]

    variance_map = aggregate_contribution_variances(results)

    assert variance_map == {"B": mp.mpf("3"), "A": mp.mpf("2.0")}


def test_contribution_summary_rows_are_deterministic_and_complete() -> None:
    rows = contribution_summary_rows({"A": mp.mpf("1"), "B": mp.mpf("3"), "C": mp.mpf("0")})

    assert [row["name"] for row in rows] == ["B", "A", "C"]
    assert [row["variance"] for row in rows] == [mp.mpf("3"), mp.mpf("1"), mp.mpf("0")]
    assert [row["sigma"] for row in rows] == [mp.sqrt(3), mp.mpf("1"), mp.mpf("0")]
    assert [row["percent"] for row in rows] == pytest.approx([75.0, 25.0, 0.0])


def test_contribution_summary_rows_preserve_insertion_order_for_variance_ties() -> None:
    rows = contribution_summary_rows({"B": mp.mpf("1"), "A": mp.mpf("1")})

    assert [row["name"] for row in rows] == ["B", "A"]


def test_aggregate_contribution_summary_combines_variance_map_and_rows() -> None:
    rows = aggregate_contribution_summary(
        [
            SimpleNamespace(contributions={"A": mp.mpf("1"), "B": mp.mpf("1")}),
            SimpleNamespace(contributions={"B": mp.mpf("3")}),
        ]
    )

    assert [row["name"] for row in rows] == ["B", "A"]
    assert [row["percent"] for row in rows] == pytest.approx([80.0, 20.0])


def test_render_error_contribution_plot_routes_shared_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(spec: Any) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nshared-contribution"

    monkeypatch.setattr(plotting, "render_error_contribution_plot_from_spec", fake_render)

    png = render_error_contribution_plot(
        [{"name": "A", "variance": mp.mpf("1"), "sigma": mp.mpf("1"), "percent": 100.0}],
        "en-US",
        title_suffix="row 3",
        title_en="Custom title",
    )

    assert png == b"\x89PNG\r\n\x1a\nshared-contribution"
    spec = captured["spec"]
    assert spec.labels == ("A",)
    assert spec.percents == (100.0,)
    assert spec.cumulative_percents == (100.0,)
    assert spec.plot_labels.x_axis == "Uncertainty contribution (%)"
    assert spec.plot_labels.title == "Custom title"
    assert spec.plot_labels.cumulative_label == "Cumulative contribution"
    assert spec.title_suffix == "row 3"
