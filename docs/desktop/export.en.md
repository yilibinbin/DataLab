# Export & Typesetting (Desktop)

This page explains CSV export, LaTeX generation, PDF compilation, and display formatting in the desktop app.

## CSV Export

After a run finishes, click “Export CSV”:

- Exported numeric columns follow the current display format:
  - Scientific notation OFF: rounded by decimal places
  - Scientific notation ON: rounded by significant digits and shown in scientific notation

Adjust the display formatting before exporting if you need the CSV to match the screen output.

## LaTeX Output

Enable “Generate LaTeX” to produce LaTeX content:

- LaTeX values typically use parentheses notation (e.g., `1.2345(67)`) for manuscript typesetting
- You can view and edit the generated LaTeX in the “LaTeX” tab

## PDF Compilation and Preview

If PDF compilation is enabled:

- A TeX engine must be installed (e.g., `pdflatex` or `xelatex`)
- After a successful build, the “PDF preview” tab shows preview images

If compilation fails:

- Check the “Log” tab for error messages (most commonly: TeX engine missing or wrong path)
- Ensure the runtime user can write to the temporary directory

## `dcolumn` Alignment

Enable alignment only if your LaTeX template includes `dcolumn` (or you plan to add it). Otherwise compilation may fail; disable it or add the package.
