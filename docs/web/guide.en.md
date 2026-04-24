# DataLab Web User Guide

This guide explains how to use DataLab Web for high‑precision numerical workflows.

## Data Input

### Paste Text

1. Paste your data into the input box
2. The first row is treated as headers (column names)
3. Columns are separated by spaces or tabs

**Example**:
```
A B C
-0.750000   -0.702321   -0.680145
-0.500000   -0.476901   -0.461822
-0.250000   -0.235440   -0.228512
```

### Upload a File

1. Enable the “Use file input” checkbox
2. Click the “Upload UTF‑8 text file” button
3. Choose a `.txt`, `.dat`, or `.csv` file
4. The file format is the same as pasted text (headers on the first row)

### Uncertainty Notation

DataLab Web supports two uncertainty representations:

**Method 1: Parentheses notation** — `value(uncertainty)[10^exponent]`
```
1.2345(67)       # means 1.2345 ± 0.0067
1.2345(67)[-2]   # means 1.2345 ± 0.0067 × 10^-2
```

**Method 2: Separate columns** — value and sigma in two columns
```
value    sigma
1.2345   0.0067
2.3456   0.0089
```

## Outputs

### Result Table
- **Extrapolated / computed value**: the resulting numeric value
- **Uncertainty**: propagated uncertainty or standard deviation
- **LaTeX format**: formatted output using parentheses notation

### Formatting Controls
- **Scientific notation**: when ON, values are shown in scientific notation
- **Digits**: OFF → decimal places; ON → significant digits

### Export Options
- **CSV download**: export table data
- **LaTeX text**: copy into your manuscript
- **PDF download**: download a PDF if PDF compilation is enabled and LaTeX is available

## FAQ

### Q1: Why does my formula fail?

A: Check the following:
- Functions must use Mathematica-style capitalization and square brackets: `Sin[x]` (not `sin(x)`)
- Column names and constant names are spelled correctly
- Only supported functions are used (e.g., Sin, Cos, Log, Exp, Sqrt, Abs)

### Q2: How do I reference columns?

A: You can reference columns in three ways:
- **Header name**: directly use the column name from the header row
- **x1, x2, x3**: positional aliases (x1 = 1st column, x2 = 2nd column)
- **A, B, C**: special aliases for the first three columns in extrapolation mode

### Q3: What are the constraints for log-scale fitting?

A: For log-scale axes:
- `log-x` requires all x > 0
- `log-y` requires all y > 0
- `log-xy` requires all x, y > 0

### Q4: How to interpret the uncertainty contribution plot?

A: It shows the percentage contribution of each input variable to the total uncertainty, which helps identify dominant sources.

### Q5: When should I increase mp.dps?

A: Consider increasing `mp.dps` when:
- Running power-law extrapolation (default is 80 digits)
- Using Richardson or Shanks acceleration (default is 80 digits)
- Your data requires very high precision
