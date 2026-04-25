#!/usr/bin/env bash
# Regenerate all Mathematica ground-truth JSON files from the .wls
# scripts. Requires wolframscript on PATH.
#
# Run from anywhere — the script cd's to its own directory first so
# ``wolframscript -file generate.wls`` resolves the relative paths.

set -euo pipefail

# Resolve to this script's directory so the loop's relative paths
# work regardless of where the user invoked us from.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if ! command -v wolframscript >/dev/null 2>&1; then
    echo "ERROR: wolframscript not found on PATH" >&2
    echo "Install Mathematica >= 13.0, then re-run this script." >&2
    echo "" >&2
    echo "If you only want to RUN the tests (not regenerate the JSON)," >&2
    echo "the committed ground_truth.json files are sufficient." >&2
    exit 1
fi

echo "Regenerating Mathematica ground-truth JSON files..."
echo

for area in special_functions extrapolation error_propagation statistics; do
    if [[ -f "$area/generate.wls" ]]; then
        echo "  -> $area/ground_truth.json"
        wolframscript -file "$area/generate.wls" > "$area/ground_truth.json"
        # Sanity check: does the resulting JSON parse?
        python3 -c "
import json, sys
with open('$area/ground_truth.json') as f:
    data = json.load(f)
n = len(data['cases'])
print(f'     OK: {n} cases')
"
    else
        echo "  ! skipping $area: no generate.wls"
    fi
done

echo
echo "Done. Run pytest to verify DataLab matches the regenerated values:"
echo "    pytest tests/test_*_mathematica_reference.py -v"
