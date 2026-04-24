# Statistics

Compute (weighted or unweighted) statistical averages for data with optional uncertainties.

## Quick Workflow

1. **Input data**: provide a single-column table (uncertainty is optional)
   ```
   A
   1152842742.723(12)
   1152842742.740(18)
   1152842742.727(14)
   ```

2. **Choose statistics mode**:
   - **Simple mean**: arithmetic mean
   - **Sample variance**: enable “use sample standard deviation”
   - **Weighted variance**: enable “use weighted variance”

3. **Review results**:
    - mean ± standard error
    - min / max / standard deviation
    - effective sample size (when applicable, Kish formula)

## Mode Notes

### Simple mean
Computes the arithmetic mean and standard deviation.

### Sample variance
Uses the sample standard deviation (denominator `n-1`).

### Weighted variance
Computes weighted statistics using the provided uncertainties:

- Weight: `w = 1/σ²` (rows with missing `σ` are skipped)
- Weighted mean: `x̄_w = Σ(wᵢ xᵢ) / Σwᵢ`
- Standard error of the weighted mean: `SE(x̄_w) = sqrt(1 / Σwᵢ)`
- Weighted standard deviation (scatter): numerator uses `Σ wᵢ (xᵢ-x̄_w)²`; in sample mode the denominator is `Σwᵢ - Σwᵢ²/Σwᵢ` (in population mode it is `Σwᵢ`)

Edge cases:

- If `σ=0` exists: it is treated as an “infinite-weight anchor” (mean/uncertainty come from that point); conflicting `σ=0` values are rejected
