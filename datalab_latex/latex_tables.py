#!/usr/bin/env python3
"""Compatibility façade for DataLab's LaTeX/extrapolation core.

`data_extrapolation_latex_latest` historically re-exported a very large API surface
from a single module. The implementation has since been split into dedicated
modules (single source of truth), but this module remains as the stable import
target to keep existing imports working.

Implementation modules:
- `datalab_latex.latex_tables_common`
- `datalab_latex.latex_tables_extrapolation`
- `datalab_latex.latex_tables_error_propagation`
- `datalab_latex.latex_formatting`
- `datalab_latex.expression_engine`
- `datalab_latex.derivatives`
"""

from __future__ import annotations

import argparse
import os

from . import latex_tables_extrapolation as _tables_extrapolation
from . import latex_tables_error_propagation as _tables_error


def _reexport_public(module, public_names: list[str]) -> None:
    g = globals()
    for name in public_names:
        g[name] = getattr(module, name)


_reexport_public(_tables_extrapolation, list(_tables_extrapolation.__all__))
_reexport_public(_tables_error, list(_tables_error.__all__))

__all__ = list(_tables_extrapolation.__all__) + list(_tables_error.__all__)

del _reexport_public, _tables_extrapolation, _tables_error


def main() -> int:
    """Main function to handle command-line arguments and run the processing."""
    parser = argparse.ArgumentParser(
        description="Process three-column data, perform extrapolation, and generate LaTeX table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage
    python3 data_extrapolation_latex.py data.txt

    # Verbose output
    python3 data_extrapolation_latex.py --verbose data.txt

    # Custom output filename
    python3 data_extrapolation_latex.py --output results.tex data.txt

    # Control precision (6 decimal places)
    python3 data_extrapolation_latex.py --precision 6 data.txt

Input file format:
    - First line: column headers (space-separated)
    - Following lines: three numerical values per line (space-separated)
    - Scientific notation supported (e.g., 1.23E-05)

Output format:
    - LaTeX table with scientific notation using [exp] format
    - Uncertainty shown as value(uncertainty)[exp] format
    - Spaces added every three decimal digits
        """,
    )

    parser.add_argument(
        "input_file",
        metavar="INPUT_FILE",
        help="Input data file with three columns of numerical data",
    )

    parser.add_argument(
        "--output",
        "-o",
        metavar="OUTPUT_FILE",
        help="Output LaTeX file name (default: input_name.tex)",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    parser.add_argument("--caption", "-c", metavar="CAPTION", help="Custom caption for the table")

    parser.add_argument(
        "--precision",
        "-p",
        type=int,
        metavar="DIGITS",
        help="Number of decimal places for input data (default: 13 decimal places)",
    )

    parser.add_argument(
        "--extrapolate",
        action="store_true",
        help="Perform extrapolation on three-column data (original functionality)",
    )

    parser.add_argument(
        "--error-propagation",
        action="store_true",
        help="Perform error propagation using formula and constants",
    )

    parser.add_argument(
        "--formula",
        "-f",
        metavar="FORMULA",
        help='Formula for error propagation (e.g., "x1*const1 + x2/const2 + x3^2*log[const2]")',
    )

    parser.add_argument(
        "--constants",
        metavar="CONSTANTS_FILE",
        help="File containing constants with uncertainties",
    )

    parser.add_argument(
        "--dcolumn",
        action="store_true",
        help="Use dcolumn format for decimal alignment (now default)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print("Error: Input file '{0}' not found".format(args.input_file))
        return 1

    if args.output:
        output_filename = args.output
    else:
        base_name = os.path.splitext(args.input_file)[0]
        output_filename = base_name + ".tex"

    if args.verbose:
        print("Data Extrapolation and LaTeX Generator")
        print("=" * 50)
        print("Input file: {0}".format(args.input_file))
        print("Output file: {0}".format(output_filename))
        print()

    if args.error_propagation and not args.formula:
        print("Error: --formula is required when using --error-propagation")
        return 1

    if not args.extrapolate and not args.error_propagation:
        args.extrapolate = True
        if args.verbose:
            print("No mode specified, defaulting to extrapolation mode")

    try:
        if args.extrapolate:
            headers, data_rows, extrapolated_results = process_data_file(args.input_file, args.verbose)

            if not data_rows:
                print("Error: No valid data rows found in input file")
                return 1

            generate_latex_table(
                headers,
                data_rows,
                extrapolated_results,
                output_filename,
                caption=args.caption,
                precision=args.precision,
                verbose=args.verbose,
                use_dcolumn=args.dcolumn,
            )

            print("Successfully generated LaTeX table: {0}".format(output_filename))
            print("Total data points processed: {0}".format(len(data_rows)))

        elif args.error_propagation:
            constants = {}
            if args.constants:
                constants = process_constants_file(args.constants, args.verbose)

            headers, parsed_data = process_uncertainty_data_file(args.input_file, args.verbose)

            if not parsed_data:
                print("Error: No valid data rows found in input file")
                return 1

            results = apply_formula_to_data(headers, parsed_data, constants, args.formula, args.verbose)

            if args.dcolumn:
                if args.verbose:
                    print("Using dcolumn format with number spacing for LaTeX table generation")
                generate_error_propagation_table(
                    headers,
                    parsed_data,
                    results,
                    constants,
                    args.formula,
                    output_filename,
                    caption=args.caption,
                    verbose=args.verbose,
                    use_dcolumn=True,
                )
            else:
                if args.verbose:
                    print("Using regular format with spacing for LaTeX table generation")
                generate_error_propagation_table(
                    headers,
                    parsed_data,
                    results,
                    constants,
                    args.formula,
                    output_filename,
                    caption=args.caption,
                    verbose=args.verbose,
                    use_dcolumn=False,
                )

            print("Successfully generated error propagation LaTeX table: {0}".format(output_filename))
            print("Total data rows processed: {0}".format(len(parsed_data)))

    except Exception as e:  # noqa: BLE001
        print("Error: {0}".format(str(e)))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
