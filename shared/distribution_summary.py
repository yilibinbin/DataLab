from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mpmath import mp

MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA = "datalab.monte_carlo_distribution_summary"
MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA_VERSION = 1


def build_monte_carlo_distribution_summary(
    *,
    sample_count: int,
    accepted_count: int,
    rejected_count: int,
    mean: Any,
    std: Any,
    accepted_samples: Sequence[Any],
) -> dict[str, object]:
    finite_samples = [mp.mpf(sample) for sample in accepted_samples if mp.isfinite(sample)]
    bin_edges, counts = monte_carlo_histogram(finite_samples)
    percentiles = monte_carlo_percentiles(finite_samples)
    return {
        "schema": MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA,
        "schema_version": MONTE_CARLO_DISTRIBUTION_SUMMARY_SCHEMA_VERSION,
        "requested_sample_count": int(sample_count),
        "evaluated_sample_count": int(sample_count),
        "accepted_sample_count": int(accepted_count),
        "rejected_sample_count": int(rejected_count),
        "finite_sample_count": int(len(finite_samples)),
        "mean": mp.mpf(mean),
        "std": mp.mpf(std),
        "histogram": {
            "bin_edges": bin_edges,
            "counts": counts,
        },
        "percentiles": percentiles,
    }


def monte_carlo_histogram(samples: Sequence[Any]) -> tuple[list[mp.mpf], list[int]]:
    finite_samples = [mp.mpf(sample) for sample in samples if mp.isfinite(sample)]
    if not finite_samples:
        return [], []
    sample_min = min(finite_samples)
    sample_max = max(finite_samples)
    if sample_min == sample_max:
        center = mp.mpf(sample_min)
        half_width = mp.mpf("0.5") if center == 0 else max(mp.fabs(center) * mp.mpf("0.05"), mp.mpf("0.5"))
        return [center - half_width, center + half_width], [len(finite_samples)]
    bin_count = min(30, max(5, int(mp.sqrt(len(finite_samples)))))
    width = (sample_max - sample_min) / bin_count
    edges = [sample_min + width * index for index in range(bin_count)]
    edges.append(sample_max)
    counts = [0 for _ in range(bin_count)]
    for sample in finite_samples:
        if sample == sample_max:
            counts[-1] += 1
            continue
        index = int(mp.floor((sample - sample_min) / width))
        index = min(max(index, 0), bin_count - 1)
        counts[index] += 1
    return edges, counts


def monte_carlo_percentiles(samples: Sequence[Any]) -> dict[str, mp.mpf]:
    finite_samples = [mp.mpf(sample) for sample in samples if mp.isfinite(sample)]
    if not finite_samples:
        return {}
    ordered = sorted(finite_samples)
    return {
        "2.5": monte_carlo_quantile(ordered, mp.mpf("0.025")),
        "50": monte_carlo_quantile(ordered, mp.mpf("0.5")),
        "97.5": monte_carlo_quantile(ordered, mp.mpf("0.975")),
    }


def monte_carlo_quantile(ordered_samples: Sequence[Any], probability: Any) -> mp.mpf:
    samples = [mp.mpf(sample) for sample in ordered_samples]
    if not samples:
        return mp.nan
    if len(samples) == 1:
        return samples[0]
    p = mp.mpf(probability)
    position = p * (len(samples) - 1)
    lower_index = int(mp.floor(position))
    upper_index = int(mp.ceil(position))
    if lower_index == upper_index:
        return samples[lower_index]
    weight = position - lower_index
    return samples[lower_index] * (1 - weight) + samples[upper_index] * weight
