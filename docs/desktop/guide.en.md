# User Guide (Desktop)

This page describes the desktop GUI workflow, organized by the desktop window layout.

## Window Layout

The main window is typically split into:

- Left: inputs and parameters (mode selection, data input, options)
- Right: result area (tabs to view outputs)

The result area includes:

- Values: human-readable summary
- Log: detailed steps and warnings (check this first when something fails)
- LaTeX: generated LaTeX text (editable before compiling)
- PDF Preview: preview images after successful PDF compilation

## Data Input

Two input methods are available:

1) File input: load a local data file (UTF-8 text; first row = headers)
2) Manual input: paste the same text format (first row = headers)

Common uncertainty formats:

- Parentheses notation: `1.2345(67)[-2]`
- Separate columns: value + uncertainty columns (or a recognized sigma header)

## Basic Workflow

1. Select a mode: Extrapolation / Error propagation / Fitting / Statistics
2. Provide input data (file or paste)
3. Configure required parameters for the selected mode
4. Click Run/Start
5. Review results and export CSV or generate LaTeX/PDF if needed

## Display Formatting (Decimal Places / Significant Digits)

The desktop app provides a “Display results in scientific notation” option:

- OFF: the number input means **decimal places**
- ON: the number input means **significant digits**, and values are shown in scientific notation

This rule affects the desktop display and CSV export. LaTeX formatting is controlled separately by the LaTeX export options.

## Log Axes in Fitting Plots

In fitting mode you can enable `log-x` / `log-y`:

- If the data contains non-positive values, the corresponding log axis is automatically disabled with a log message
- Check data ranges before enabling log axes

