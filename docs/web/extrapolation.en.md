# Extrapolation

Extrapolation is used to estimate the limit of a numerical sequence or to predict its trend.

## Quick Workflow

1. **Input data**: paste a multi-column table or upload a text file
2. **Choose an extrapolation method** (see below)
3. **Set options**:
   - Reference column: used to estimate the uncertainty
   - Max-diff column: automatically choose the reference column with the largest deviation from the extrapolated value (more conservative)
   - Multi-precision `mp.dps`: numerical precision
   - Result uncertainty significant digits
4. **Run**: click “Run Extrapolation & Generate LaTeX”

## Methods

### Power-law extrapolation (3-point)
Suitable for sequences of the form `f(x) = A*x^(-p) + C`.

**Parameters**:
- `x1`, `x2`, `x3`: x coordinates of the three points
- `power_exponent`: fixed power exponent `p` (optional)
- `power_seed`: initial guess for `p`

**Use cases**: basis-set extrapolation in quantum chemistry, precision extrapolation for numerical integration, etc.

### Richardson extrapolation
Suitable for asymptotic expansion sequences.

**Use cases**: numerical differentiation/integration, finite-difference methods.

### Shanks transform / Wynn ε algorithm
General-purpose sequence acceleration.

**Use cases**: series summation, accelerating iterative methods.

### Levin u-transform
Specialized for oscillating or alternating series.

**Parameters**:
- `levin_variant`: Levin variant (default `'u'`)

### Custom formula
Use a custom mathematical formula for extrapolation.

**Formula syntax**:
- Use `A`, `B`, `C` or column names to reference data columns
- Use `x1`, `x2`, `x3` as column aliases by order
- Supported functions/constants: same whitelist as error propagation and custom fit models (use the in-app “Formula Help” as the source of truth; see the [Theory](theory.md) page for the full list)
- Example: `(C - B)^2/(B - A) + C`
