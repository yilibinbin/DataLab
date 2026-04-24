# Frequently Asked Questions (FAQ)

## Usage

### Formula Errors

**Q: Why does my formula fail?**

A: Check the following:
- Use Mathematica-style function names with square brackets: `Sin[x]` (not `sin(x)`)
- Column names and constant names are spelled correctly
- Use supported functions (e.g., Sin, Cos, Log, Exp, Sqrt, Abs)

### Referencing Columns

**Q: How do I reference columns in a formula?**

A: You can use:
- Header names from the first row (e.g., `E1`, `E2`)
- Positional aliases `x1`, `x2`, `x3`, ...
- In extrapolation mode, `A`, `B`, `C` for the first three columns

### Uncertainty Format

**Q: How do I represent uncertainties?**

A: Two formats are supported:
- Parentheses notation: `1.2345(67)` means 1.2345 ± 0.0067
- Separate columns: value and sigma in two columns

### Log-Scale Fitting

**Q: What are the constraints for log-scale fitting?**

A:
- `log-x` requires all x > 0
- `log-y` requires all y > 0
- `log-xy` requires all x, y > 0

## Technical

### LaTeX Compilation

**Q: PDF generation fails — what should I do?**

A:
- Ensure LaTeX is installed (e.g., texlive or MacTeX)
- Check the configured LaTeX engine path
- Review error details in the logs

### Performance

**Q: Why is high-precision computation slow?**

A: This is expected. Higher `mp.dps` means slower computation. Recommendations:
- Use high precision only when needed
- 80 digits is usually sufficient for acceleration methods
- Use default precision for routine runs

### File Upload

**Q: Upload fails — what should I check?**

A:
- File must be UTF‑8 encoded
- File size must be within the limit (default 1MB)
- Format must be valid (headers on first row, data on following rows)

## Troubleshooting

### Unexpected Results

1. Verify input format
2. Validate formula syntax
3. Check parameter settings
4. Review warnings

### Display Issues

1. Clear browser cache
2. Try another browser
3. Check the JavaScript console for errors

### Export Issues

**CSV download**:
- Ensure results are generated
- Check browser download settings

**LaTeX/PDF**:
- Copy LaTeX and compile manually
- Check your PDF viewer
