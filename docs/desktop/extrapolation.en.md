# Extrapolation (Desktop)

The desktop extrapolation module extrapolates multi-column sequence data and outputs the extrapolated value and uncertainty. It can also generate LaTeX tables and an optional PDF.

## Selecting a Method

Multiple methods are available (e.g., power-law, Richardson, Shanks/Wynn ε, Levin).

- After selecting a method, its parameter panel appears on the left
- Click the “?” next to the method to view the detailed method description (shared between desktop and web)

## Common Parameters

Parameters depend on the method. Common options include:

- `mp.dps` (multiprecision digits): higher precision is often required for sequence acceleration
- Result uncertainty significant digits: controls the uncertainty digits used in parentheses notation in LaTeX
- Reference column: used for uncertainty estimation in some workflows
- Max-diff column: Automatically choose the reference column with the largest deviation from the extrapolated value

## Outputs

After computation, the result area shows:

- A summary (value, uncertainty, warnings)
- Optional plots
- LaTeX table text (copy or edit)
- Optional PDF preview
