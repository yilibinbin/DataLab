# Independent DataLab Statistics Feature Enrichment Plan

## Goal
Expand the existing DataLab statistics module beyond its current "weighted mean" focus to a comprehensive descriptive statistics toolkit. This plan introduces new statistical metrics while strictly adhering to the constraint of reusing the existing shared input bundle, constants handling, result envelopes, and LaTeX/plotting infrastructure.

## Constraints
- **No new subsystems**: All feature additions must build upon the current `datalab_core/statistics_compute.py` and `app_desktop/views/statistics.py` architecture.
- **Backwards Compatibility**: Existing `mean_sample`, `mean_population`, and `weighted_sigma` modes must remain unchanged.
- **Univariate Focus**: Stick to a single value column (with optional sigma) as dictated by the current GUI layout, avoiding complex multi-column correlation for now to prevent deep GUI rearchitecture.

## Proposed Features
Add a new `stats_mode` called `"descriptive"` that computes:
- Median
- Variance
- Skewness
- Kurtosis
- Quartiles (Q1, Q3) and Interquartile Range (IQR)

## Implementation Steps

### Phase 1: Core Computation
**Files**: `datalab_core/statistics_compute.py`
1. Expand `compute_statistics()` to accept `stats_mode = "descriptive"`.
2. Sort `valid_values` and compute the Median, Q1, and Q3 using standard quantile interpolation (e.g., `method='linear'`). Compute IQR = Q3 - Q1.
3. Compute Variance, Skewness (3rd standardized moment), and Kurtosis (4th standardized moment).
4. Return these new metrics in the result dictionary (e.g., `median`, `variance`, `skewness`, `kurtosis`, `q1`, `q3`, `iqr`). For backwards compatibility with the envelope, ensure basic `mean`, `std`, `v_min`, and `v_max` are still provided.

### Phase 2: Payload and Service Adapters
**Files**: `datalab_core/statistics.py`
1. Update `run_statistics()` to extract the new metrics from the result of `compute_statistics` and serialize them into the JSON-safe `payload` dictionary using `_format_mpf()` or `_format_optional_mpf()`.
2. Update `statistics_payload_to_compute_result()` to deserialize these new keys back into `mp.mpf` instances for the legacy desktop/web adapters.

### Phase 3: Desktop UI Updates
**Files**: `app_desktop/views/statistics.py`
1. Update `build_statistics_mode_view()`:
   - Append `("描述性统计", "Descriptive statistics", "descriptive")` to `stats_items`.
   - Update tooltip descriptions if necessary to explain that descriptive mode computes quantiles and moments.

### Phase 4: Output Rendering (UI and LaTeX)
**Files**: `app_desktop/workbench_results.py` (or relevant result formatter), `statistics_utils.py`
1. **UI Presentation**: Update the result stringification/markdown logic to conditionally append rows for Median, Variance, Skewness, Kurtosis, Q1, Q3, and IQR if they are present in the computation result and the mode is `descriptive`.
2. **LaTeX Writer**: Update `generate_statistics_latex_batches()` to handle the `descriptive` mode. Create an expanded summary block or a multi-column property table that cleanly renders these additional values without breaking existing table structures.

### Phase 5: Testing and Documentation
**Files**: `tests/test_statistics_compute.py`, `tests/test_desktop_statistics_ui.py`, `docs/desktop/guide.*.md`, `examples/catalog.py`
1. Add RED tests in `test_statistics_compute.py` verifying the exact outputs of the new metrics against known `scipy.stats` or standard math references (especially checking n-1 sample definitions for variance/skewness/kurtosis).
2. Add GUI layout tests in `test_desktop_statistics_ui.py` to ensure the new dropdown option is available and dispatches correctly.
3. Add LaTeX compilation tests to ensure `descriptive` mode PDF generation does not fail.
4. Add a `descriptive-statistics.datalab` example workspace and update documentation guides.
