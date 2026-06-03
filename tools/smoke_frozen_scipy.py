from __future__ import annotations

import math
import sys

from root_solving.models import RootProblem, RootUnknown
from root_solving.solver import solve_root_problem


def main() -> int:
    result = solve_root_problem(
        RootProblem(
            equations=("x**2 - 2",),
            unknowns=(RootUnknown("x", initial="1.5"),),
            mode="scalar",
            precision=16,
        )
    )
    if result.backend != "scipy":
        print(f"expected scipy backend, got {result.backend}", file=sys.stderr)
        return 1
    if not result.roots:
        print("expected at least one root", file=sys.stderr)
        return 1
    root_value = result.roots[0].value
    if isinstance(root_value, complex):
        if abs(root_value.imag) > 1e-12:
            print(f"expected real root, got complex: {root_value!r}", file=sys.stderr)
            return 1
        root_value = root_value.real
    try:
        root = float(root_value)
    except (TypeError, ValueError) as exc:
        print(f"failed to convert root to float: {exc}", file=sys.stderr)
        return 1
    if not math.isfinite(root) or abs(root - math.sqrt(2.0)) > 1e-12:
        print(f"unexpected root: {root!r}", file=sys.stderr)
        return 1
    print(f"scipy frozen smoke OK: backend={result.backend} root={root:.14g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
