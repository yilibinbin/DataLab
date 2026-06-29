from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHIPPING_FORMULA_DPI = 160
SHIPPING_FORMULA_COLOR = "#111827"


def test_formula_renderer_value_gate_report_defaults_to_png_only_no_go() -> None:
    from datalab_latex.formula_render_service import RenderRequest
    from tools.formula_renderer_value_gate import build_report

    report = build_report()
    defaults = RenderRequest(source="")

    assert defaults.dpi == SHIPPING_FORMULA_DPI
    assert defaults.color == SHIPPING_FORMULA_COLOR
    assert report["decision"] == "NO_GO"
    assert report["shipping_backend"] == "mathtext_png"
    assert report["webengine_enabled"] is False
    assert report["representative_formulas"]
    assert all("source" in row and "metadata_ok" in row and "png_ok" in row for row in report["representative_formulas"])
    assert all(row["metadata_ok"] and row["png_ok"] for row in report["representative_formulas"])
    assert all(row["dpi"] == defaults.dpi for row in report["representative_formulas"])
    assert all(row["color"] == defaults.color for row in report["representative_formulas"])


def test_formula_renderer_value_gate_cli_writes_json_under_requested_path(tmp_path: Path) -> None:
    out = tmp_path / "formula-renderer-value-gate.json"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/formula_renderer_value_gate.py"),
            "--out",
            str(out),
        ],
        check=True,
        cwd=ROOT,
        text=True,
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["decision"] == "NO_GO"
    assert payload["shipping_backend"] == "mathtext_png"
