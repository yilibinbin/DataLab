from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datalab_latex.formula_render_service import RenderRequest, render_formula_metadata  # noqa: E402
from shared.formula_mathtext_png import render_mathtext_png  # noqa: E402


REPRESENTATIVE_FORMULAS = (
    "d0 + d2/(n-delta)^2",
    "Sqrt[A] + Sin[x]",
    "a*(b+c)",
    "a/(b/c)",
    "Exp[-x] + Log[Pi*x]",
)


def build_report() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for source in REPRESENTATIVE_FORMULAS:
        request = RenderRequest(source=source)
        metadata = render_formula_metadata(request)
        png_ok = False
        png_error = ""
        if metadata.ok:
            try:
                png_ok = render_mathtext_png(
                    metadata.mathtext,
                    dpi=request.dpi,
                    color=request.color,
                ).startswith(
                    b"\x89PNG"
                )
            except Exception as exc:  # noqa: BLE001 - evidence should record renderer failures.
                png_error = str(exc) or exc.__class__.__name__
        rows.append(
            {
                "source": source,
                "metadata_ok": metadata.ok,
                "latex": metadata.latex,
                "png_ok": png_ok,
                "png_error": png_error,
                "dpi": request.dpi,
                "color": request.color,
            }
        )
    return {
        "decision": "NO_GO",
        "decision_reason": (
            "WebEngine/MathJax shipping remains disabled. Current formula preview evidence "
            "covers the mathtext PNG backend only."
        ),
        "shipping_backend": "mathtext_png",
        "webengine_enabled": False,
        "representative_formulas": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write DataLab formula renderer value-gate evidence JSON.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
