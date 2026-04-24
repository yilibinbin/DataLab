# Export & Typesetting (Web)

This page explains how to export results in the Web UI, including CSV, LaTeX, PDF, and display formatting options.

## CSV Download

After a run finishes, the result table provides a “Download CSV” button:

- Numeric columns in the CSV follow the current display format:
  - Scientific notation OFF: rounded by **decimal places**
  - Scientific notation ON: rounded by **significant digits** and shown in scientific notation
- The LaTeX column is exported as shown on the page (for direct copy into manuscripts).

## LaTeX Output

Extrapolation, error propagation, fitting, and statistics can generate LaTeX table text:

- LaTeX values use parentheses notation (e.g., `1.2345(67)`), controlled by the “result uncertainty significant digits” setting.
- Optional `dcolumn` alignment can be enabled to align numeric columns by the decimal point.

## PDF Compilation

You can enable “Try to compile PDF and provide download”:

- A TeX engine must be installed on the server (e.g., `pdflatex` or `xelatex`).
- You may provide the engine path in “LaTeX engine (optional)”; leave it empty to use the default PATH.

If PDF compilation fails:

- Verify the TeX engine works from the command line;
- Check file permissions for the runtime user and the temporary directory.

## Notes on `dcolumn`

- Enable it only if your LaTeX template includes `dcolumn` (or you plan to add it).
- If your template does not include the required package, compilation may fail; disable `dcolumn` or add the package.

## Display Formatting: Decimal Places vs Significant Digits

The display controls on the result table follow this rule:

- Scientific notation OFF: the input means **decimal places**
- Scientific notation ON: the input means **significant digits**

This affects the page display and CSV export only; it does not change the LaTeX column formatting.

