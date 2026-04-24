# FAQ (Desktop)

## 1) Why does PDF compilation fail?

Check the following:

1. Make sure a TeX engine is installed (`pdflatex` / `xelatex`)
2. If the UI provides an “engine path”, ensure it points to the executable
3. Read the “Log” tab for detailed error output
4. Ensure the temporary directory is writable (the compiler creates `.tex/.aux/.log/.pdf` files)

## 2) Why does `log-y` not apply?

If your y data contains non-positive values, `log-y` is automatically disabled and the app falls back to linear scale with a log message. Ensure all y > 0.

## 3) Why is the exported CSV different from the screen display?

CSV export follows the current display formatting:

- Scientific OFF: decimal places
- Scientific ON: significant digits

Adjust the display formatting before exporting.

## 4) Why does my error propagation formula fail?

Verify:

- Use Mathematica-style functions: `Sin[x]` (not `sin(x)`)
- Variable names match headers/constants
- Brackets and operators are valid

