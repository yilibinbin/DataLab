# User Guide (Desktop)

This page describes the desktop GUI workflow, organized by the desktop window layout.

## Workbench Layout

The desktop window uses a three-zone scientific workbench:

- Top workbench bar: New/Open/Save, Examples, Run/Stop, workspace status, Docs, and Updates
- Left configuration rail: calculation mode, data source, and output settings
- Center workspace: data editor, formula/model editor, parameters, and constants
- Right result rail: an always-visible result summary/status panel above tabs for numeric results, images, log, LaTeX, and PDF preview

The splitter keeps required controls visible at supported desktop sizes. Formula
preview buttons open a rendered preview dialog without changing the formula text.
Hidden modes keep their drafts, so switching between modules does not erase
partially prepared formulas, parameters, constants, or root-solving settings.

The result rail includes:

- Numeric results: human-readable summary and tables
- Images: generated plots with zoom/export controls
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

1. Select a mode: Extrapolation / Error propagation / Fitting / Root solving / Statistics
2. Provide input data (file or paste)
3. Configure required parameters for the selected mode
4. Click Run/Start
5. Review results and export CSV or generate LaTeX/PDF if needed

## Formula Editors and Tables

Formula editors use placeholder examples only as hints; an empty formula field is
not silently replaced by the example. Use the preview button beside formula
fields to inspect the rendered expression, and use the Functions button for the
supported expression syntax.

Parameter and constants tables share the same interaction model across fitting,
self-consistent/implicit models, error propagation, and root solving:

- Detect buttons refresh automatically inferred names from the current formula
- `+ Row` and `- Row` allow manual edits when automatic detection is not enough
- Constants can be entered in table view or text view, including uncertainty
  notation such as `1.23(4)[-5]`
- Disabled constants are not substituted into the calculation

## Example Workspaces

Use the Examples button in the workbench bar or the Examples menu to open a
bundled `.datalab` workspace. Examples are opened as templates: editing them does
not modify the bundled copy, and saving requires choosing a user path. This makes
examples safe to use as starting points for your own calculations.

## Display Formatting (Decimal Places / Significant Digits)

The desktop app provides a “Display results in scientific notation” option:

- OFF: the number input means **decimal places**
- ON: the number input means **significant digits**, and values are shown in scientific notation

This rule affects the desktop display and CSV export. LaTeX formatting is controlled separately by the LaTeX export options.

## Log Axes in Fitting Plots

In fitting mode you can enable `log-x` / `log-y`:

- If the data contains non-positive values, the corresponding log axis is automatically disabled with a log message
- Check data ranges before enabling log axes
