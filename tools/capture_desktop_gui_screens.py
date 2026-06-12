from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


_ensure_repo_root_on_path()

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

from tools.scan_desktop_gui_schema import (  # noqa: E402
    FITTING_SUBMODES,
    MODES,
    ROOT_SOLVING_SUBMODES,
    ScreenScenario,
    _apply_screen_scenario,
    _refresh_workbench_panels,
)
from app_desktop.workbench_visual_contract import (  # noqa: E402
    visual_contract_issues,
    widget_metric,
    workbench_region_metrics,
)


def _create_window() -> Any:
    from app_desktop.window import ExtrapolationWindow

    return ExtrapolationWindow()


def _capture_scenarios(*, width: int, height: int) -> list[ScreenScenario]:
    scenarios: list[ScreenScenario] = []
    for language in ("zh", "en"):
        for mode in MODES:
            if mode == "root_solving":
                for root_mode in ROOT_SOLVING_SUBMODES:
                    scenarios.append(
                        ScreenScenario(
                            key=f"{language}:{mode}:{root_mode}",
                            language=language,
                            mode=mode,
                            root_mode=root_mode,
                            result_tab="numeric",
                            width=width,
                            height=height,
                        )
                    )
            elif mode == "fitting":
                for fit_mode in FITTING_SUBMODES:
                    scenarios.append(
                        ScreenScenario(
                            key=f"{language}:{mode}:{fit_mode}",
                            language=language,
                            mode=mode,
                            root_mode=fit_mode,
                            result_tab="numeric",
                            width=width,
                            height=height,
                        )
                    )
                # The ordinary fitting/custom scenario above covers the
                # default DataLab preview syntax. These supplemental scenarios
                # exercise only the alternate render-only preview syntaxes.
                for formula_syntax in ("python", "mathematica"):
                    scenarios.append(
                        ScreenScenario(
                            key=f"{language}:{mode}:custom:{formula_syntax}",
                            language=language,
                            mode=mode,
                            root_mode="custom",
                            formula_syntax=formula_syntax,
                            result_tab="numeric",
                            width=width,
                            height=height,
                        )
                    )
            else:
                scenarios.append(
                    ScreenScenario(
                        key=f"{language}:{mode}",
                        language=language,
                        mode=mode,
                        result_tab="numeric",
                        width=width,
                        height=height,
                    )
                )
    return scenarios


def _scenario_issues(window: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    left_scroll = getattr(window, "_left_scroll", None)
    if left_scroll is not None:
        bar = left_scroll.horizontalScrollBar()
        if bar.maximum() != 0 or bar.isVisible():
            issues.append(
                {
                    "kind": "config_horizontal_scrollbar",
                    "maximum": int(bar.maximum()),
                    "visible": bool(bar.isVisible()),
                }
            )
    return issues


def _select_result_tab(window: Any, result_tab: str) -> None:
    result_tabs = getattr(window, "result_tabs", None)
    result_tab_indices = getattr(window, "result_tabs_indices", {})
    if result_tabs is None or result_tab not in result_tab_indices:
        raise AssertionError(f"missing result tab for screenshot scenario: {result_tab!r}")
    tabs = getattr(window, "tabs", None)
    result_tab_index = getattr(window, "result_tab_index", -1)
    if tabs is None or result_tab_index < 0:
        raise AssertionError("missing result tab container for screenshot scenario")
    tabs.setCurrentIndex(result_tab_index)
    result_tabs.setCurrentIndex(int(result_tab_indices[result_tab]))


def _clear_result_state_for_capture(window: Any) -> None:
    reset_csv_data = getattr(window, "_reset_csv_data", None)
    if callable(reset_csv_data):
        reset_csv_data(clear_non_tabular_result=True)


def _prepare_screenshot_scenario(window: Any, scenario: ScreenScenario) -> None:
    _apply_screen_scenario(window, scenario)
    _clear_result_state_for_capture(window)
    _select_result_tab(window, scenario.result_tab)
    _refresh_workbench_panels(window)
    QApplication.processEvents()


def _current_formula_syntax(window: Any, scenario: ScreenScenario) -> str:
    panel = getattr(window, "workbench_formula_panel", None)
    if panel is not None and not panel.isVisible():
        return ""
    combo = getattr(window, "workbench_formula_language_combo", None)
    if isinstance(combo, QComboBox):
        data = combo.currentData()
        return str(data) if data else "datalab"
    return scenario.formula_syntax or "datalab"


def capture_desktop_gui_screens(
    *,
    out: Path,
    width: int = 1440,
    height: int = 900,
) -> dict[str, Any]:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])

    out.mkdir(parents=True, exist_ok=True)
    window = _create_window()
    try:
        window.resize(width, height)
        window.show()
        QApplication.processEvents()

        screenshots: list[dict[str, Any]] = []
        for scenario in _capture_scenarios(width=width, height=height):
            _prepare_screenshot_scenario(window, scenario)
            if scenario.mode == "extrapolation" and hasattr(window, "method_combo"):
                custom_index = window.method_combo.findData("custom")
                if custom_index >= 0:
                    window.method_combo.setCurrentIndex(custom_index)
                    _refresh_workbench_panels(window)
                    QApplication.processEvents()
            image = window.grab()
            if image.size() != QSize(width, height):
                window.resize(width, height)
                QApplication.processEvents()
                image = window.grab()
            filename = f"{scenario.key.replace(':', '-')}.png"
            target = out / filename
            if not image.save(str(target), "PNG"):
                raise RuntimeError(f"failed to save screenshot: {target}")
            metrics = workbench_region_metrics(window)
            scenario_issues = _scenario_issues(window)
            contract_issues = visual_contract_issues(window)
            issues = [
                {"source": "screenshot", **issue}
                for issue in scenario_issues
            ] + [
                {"source": "visual_contract", **issue}
                for issue in contract_issues
            ]
            regions = {key: asdict(metric) for key, metric in metrics.items()}
            for object_name in (
                "manual_box",
                "workbench_formula_panel",
                "workbench_variable_panel",
                "workbench_result_overview_panel",
                "workbench_result_details_panel",
            ):
                regions[object_name] = asdict(widget_metric(window, object_name))
            screenshots.append(
                {
                    "path": str(target),
                    "width": int(image.width()),
                    "height": int(image.height()),
                    "mode": scenario.mode,
                    "root_mode": scenario.root_mode,
                    "language": scenario.language,
                    "formula_syntax": _current_formula_syntax(window, scenario),
                    # Backward-compatible summary for older release gates; ``issues`` is authoritative.
                    "issue_count": len(issues),
                    "issues": issues,
                    "regions": regions,
                }
            )

        report = {
            "out": str(out),
            "width": width,
            "height": height,
            "count": len(screenshots),
            "screenshots": screenshots,
        }
        (out / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        window.deleteLater()


def report_has_issues(report: dict[str, Any]) -> bool:
    screenshots = report.get("screenshots", [])
    if not screenshots:
        return True
    return any(int(item.get("issue_count", 0) or 0) != 0 for item in screenshots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture deterministic DataLab desktop GUI screenshots.")
    parser.add_argument("--out", type=Path, default=Path("build/gui-screenshots"))
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args(argv)

    report = capture_desktop_gui_screens(out=args.out, width=args.width, height=args.height)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report_has_issues(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
