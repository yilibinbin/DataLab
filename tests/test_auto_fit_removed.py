from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _current_changelog_text(path: Path) -> str:
    """Return Unreleased plus the newest release notes, excluding history."""
    lines = path.read_text(encoding="utf-8").splitlines()
    version_heading_count = 0
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("## [") and not line.startswith("## [Unreleased]"):
            version_heading_count += 1
            if version_heading_count > 1:
                break
        current_lines.append(line)
    return "\n".join(current_lines)


def _markdown_section(text: str, heading: str, *, label: str) -> str:
    marker = f"## {heading}"
    assert marker in text, f"{label} is missing section {heading!r}"
    start = text.index(marker)
    next_heading = text.find("\n## ", start + len(marker))
    return text[start:] if next_heading == -1 else text[start:next_heading]


def _candidate_json_fence(section: str, *, label: str) -> list[dict[str, object]]:
    marker = "```json"
    assert marker in section, f"{label} comparison section is missing a JSON fence"
    start = section.index(marker) + len(marker)
    end = section.find("```", start)
    assert end != -1, f"{label} comparison JSON fence is not closed"
    try:
        payload = json.loads(section[start:end].strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{label} comparison JSON is malformed: {exc}") from exc
    assert isinstance(payload, list), f"{label} comparison JSON must be a list"
    assert all(isinstance(item, dict) for item in payload), (
        f"{label} comparison JSON entries must be objects"
    )
    return payload


def _assert_desktop_comparison_candidate_schema(
    payload: list[dict[str, object]],
    *,
    label: str,
) -> None:
    by_type = {str(candidate.get("model_type")): candidate for candidate in payload}
    assert set(by_type) == {"polynomial", "inverse_power", "custom"}, (
        f"{label} comparison candidates should document the supported families"
    )
    for candidate in payload:
        assert candidate.get("candidate_id"), (
            f"{label} comparison candidate is missing candidate_id"
        )
        assert candidate.get("label"), f"{label} comparison candidate is missing label"
    assert by_type["polynomial"]["poly_degree"] == 1
    assert by_type["inverse_power"]["inverse_min"] == 1
    assert by_type["inverse_power"]["inverse_max"] == 2
    assert "power" not in by_type["inverse_power"]
    assert by_type["custom"]["model_expr"] == "a*x+b"
    assert "expression" not in by_type["custom"]


def test_fitting_model_combo_contains_only_supported_explicit_models(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    values = [
        win.fit_model_combo.itemData(index)
        for index in range(win.fit_model_combo.count())
    ]
    labels = [
        win.fit_model_combo.itemText(index).lower()
        for index in range(win.fit_model_combo.count())
    ]

    assert values == [
        "custom",
        "self_consistent",
        "polynomial",
        "inverse_power",
        "pade",
        "power_limit",
        "comparison",
    ]
    assert "auto" not in values
    assert "log_poly" not in values
    assert "exp_combo" not in values
    assert all("auto" not in label and "自动" not in label for label in labels)


def test_no_user_visible_auto_fit_backend_control(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)

    assert not hasattr(win, "parallel_auto_fit_backend_checkbox")

    banned = ("auto-fit", "auto fit", "自动拟合", "auto-fit backend")
    visible_text: list[str] = []
    for widget in win.findChildren(object):
        if hasattr(widget, "text"):
            try:
                text = str(widget.text())
            except RuntimeError:
                continue
            if text:
                visible_text.append(text.lower())
        if hasattr(widget, "toolTip"):
            try:
                tooltip = str(widget.toolTip())
            except RuntimeError:
                continue
            if tooltip:
                visible_text.append(tooltip.lower())

    joined = "\n".join(visible_text)
    assert all(term not in joined for term in banned)


def test_window_has_no_auto_fit_lifecycle_methods():
    from app_desktop.window import ExtrapolationWindow

    stale_methods = [
        "_on_auto_fit_finished",
        "_on_auto_fit_failed",
        "_on_auto_fit_thread_done",
        "_on_auto_fit_progress",
        "_start_auto_fit",
        "_run_auto_fit",
        "_execute_auto_fit",
        "_execute_auto_fit_async",
        "_prepare_auto_fit_job",
        "_render_auto_fit_summary",
    ]

    for name in stale_methods:
        assert not hasattr(ExtrapolationWindow, name)


def test_auto_fit_worker_is_not_exported():
    import app_desktop.workers_core as workers_core
    import app_desktop.workers_qt as workers_qt

    assert not hasattr(workers_core, "AutoFitJob")
    assert not hasattr(workers_core, "_execute_auto_fit_job_subprocess")
    assert not hasattr(workers_qt, "AutoFitWorker")
    assert importlib.util.find_spec("app_desktop.auto_fit_subprocess") is None


def test_auto_fit_backend_toggle_is_not_in_parallel_config():
    from shared.parallel_config import ParallelConfig

    assert not hasattr(ParallelConfig, "enable_new_auto_fit_backend")
    assert not hasattr(ParallelConfig(), "enable_new_auto_fit_backend")


def test_tests_do_not_import_removed_auto_fit_job():
    tests_dir = Path(__file__).resolve().parent
    removed_import = "from app_desktop.workers_core import " + "AutoFitJob"
    offenders = [
        path
        for path in tests_dir.glob("test_*.py")
        if removed_import in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_docs_do_not_advertise_automatic_fitting_as_current_feature():
    root = Path(__file__).resolve().parents[1]
    checked_paths = [
        root / "CHANGELOG.md",
        root / "README.md",
        root / "docs" / "ARCHITECTURE.md",
        root / "docs" / "PROGRAM_FRAMEWORK.en.tex",
        root / "docs" / "PROGRAM_FRAMEWORK.tex",
        root / "docs" / "DATALAB_WEB_GUIDE.md",
        root / "docs" / "DATALAB_WEB_GUIDE.en.md",
        root / "docs" / "web" / "fitting.en.md",
        root / "docs" / "web" / "fitting.zh.md",
        root / "docs" / "web" / "index.en.md",
        root / "docs" / "web" / "index.zh.md",
        root / "docs" / "web" / "roadmap.en.md",
        root / "docs" / "web" / "roadmap.zh.md",
        root / "docs" / "web" / "theory.en.md",
        root / "docs" / "web" / "theory.zh.md",
        root / "extrapolation_methods" / "Data Extrapolation GUI.md",
        root / "app_web" / "README_UPDATES.md",
        root / "app_desktop" / "window_data_mixin.py",
        root / "app_desktop" / "window_i18n_mixin.py",
        root / "app_web" / "templates" / "fit.html",
        root / "app_web" / "static" / "js" / "i18n.js",
        root / "app_web" / "openapi.py",
        root / "cli" / "batch_config.py",
        root / "cli" / "main.py",
        *sorted((root / "docs" / "desktop").glob("*.md")),
    ]
    banned_claims = (
        "auto models",
        "automatic model selection",
        "auto model selection",
        "auto-fit",
        "automatic fitting",
        "自动模型",
        "自动拟合",
        "auto selection",
        "auto model selection",
        "tries multiple candidate",
        "preset/log",
        "auto/custom",
        "auto-fit subprocess execution paths",
    )
    user_facing_doc_paths = {
        root / "docs" / "DATALAB_WEB_GUIDE.md",
        root / "docs" / "DATALAB_WEB_GUIDE.en.md",
        root / "docs" / "web" / "fitting.en.md",
        root / "docs" / "web" / "fitting.zh.md",
        root / "docs" / "web" / "index.en.md",
        root / "docs" / "web" / "index.zh.md",
        root / "docs" / "web" / "roadmap.en.md",
        root / "docs" / "web" / "roadmap.zh.md",
        root / "docs" / "web" / "theory.en.md",
        root / "docs" / "web" / "theory.zh.md",
        root / "extrapolation_methods" / "Data Extrapolation GUI.md",
        root / "app_web" / "README_UPDATES.md",
    }
    user_facing_doc_claims = (
        "preset",
        "preset model library",
        "built-in model library",
        "predefined models",
        "log models",
        "exponential models",
        "m4b",
        "m7b",
        "auto model selector",
        "fit_auto",
        "candidate models",
        "choose model with minimum aic",
        "auto-model selection",
        "log/exp combinations",
        "预设模型库",
        "对数、指数",
    )
    offenders: list[str] = []
    for path in checked_paths:
        raw_text = (
            _current_changelog_text(path)
            if path.name == "CHANGELOG.md"
            else path.read_text(encoding="utf-8")
        )
        text = raw_text.lower()
        for claim in banned_claims:
            if claim in text:
                offenders.append(f"{path.relative_to(root)}: {claim}")
        if path in user_facing_doc_paths:
            if "AUTO_MODELS" in raw_text:
                offenders.append(f"{path.relative_to(root)}: AUTO_MODELS")
            for claim in user_facing_doc_claims:
                if claim in text:
                    offenders.append(f"{path.relative_to(root)}: {claim}")

    assert offenders == []

    architecture_text = (root / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "AutoFitJob" not in architecture_text


def test_web_fitting_logic_imports_without_public_auto_fit_export():
    import app_web.logic.fitting as web_fitting

    assert hasattr(web_fitting, "_run_fit")
    assert not hasattr(web_fitting, "auto_fit_dataset")


def test_web_fitting_template_exposes_only_explicit_supported_choices():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app_web" / "templates" / "fit.html").read_text(encoding="utf-8")

    for disallowed in (
        'value="auto"',
        'value="preset"',
        'value="log_poly"',
        'value="exp_combo"',
        "automatic model selection",
        "auto model selection",
        "自动模型",
        "自动拟合",
    ):
        assert disallowed not in text

    for allowed in (
        'value="polynomial"',
        'value="inverse_power"',
        'value="pade"',
        'value="power_limit"',
        'value="custom"',
        'value="comparison"',
    ):
        assert allowed in text

    assert 'name="fit_comparison_candidates"' in text

    # The exact six-model Task 1 set applies to desktop. The current web
    # flow has no self-consistent/implicit input fields, so it exposes only
    # the supported explicit subset and does not pretend to route it.
    assert 'value="self_consistent"' not in text


def test_web_fitting_docs_describe_explicit_selected_fit_comparison():
    root = Path(__file__).resolve().parents[1]
    zh_text = (root / "docs" / "web" / "fitting.zh.md").read_text(encoding="utf-8")
    en_text = (root / "docs" / "web" / "fitting.en.md").read_text(encoding="utf-8")

    assert "选定拟合比较" in zh_text
    assert "显式列出" in zh_text
    assert "fit_comparison_candidates" in zh_text
    assert "selected-fit comparison" in en_text
    assert "explicitly list" in en_text
    assert "fit_comparison_candidates" in en_text


def test_desktop_fitting_docs_describe_explicit_selected_fit_comparison():
    root = Path(__file__).resolve().parents[1]
    zh_text = (root / "docs" / "desktop" / "fitting.zh.md").read_text(
        encoding="utf-8"
    )
    en_text = (root / "docs" / "desktop" / "fitting.en.md").read_text(
        encoding="utf-8"
    )
    zh_section = _markdown_section(
        zh_text,
        "显式选择的拟合比较",
        label="Chinese desktop fitting docs",
    )
    en_section = _markdown_section(
        en_text,
        "Explicit Selected-Fit Comparison",
        label="English desktop fitting docs",
    )
    section_combined = f"{zh_section}\n{en_section}".lower()
    combined = f"{zh_text}\n{en_text}".lower()

    assert "显式选择的拟合比较" in zh_text
    assert "候选项 JSON" in zh_section
    assert "config.fitting.comparison_candidates" in zh_section
    assert "explicit selected-fit comparison" in en_text
    assert "candidate JSON" in en_section
    assert "config.fitting.comparison_candidates" in en_section
    assert "comparison table" in en_section
    assert "比较表格" in zh_section
    for supported in ("polynomial", "inverse_power", "custom"):
        assert supported in section_combined
    for output in ("csv", "latex"):
        assert output in section_combined

    _assert_desktop_comparison_candidate_schema(
        _candidate_json_fence(en_section, label="English desktop fitting docs"),
        label="English desktop fitting docs",
    )
    _assert_desktop_comparison_candidate_schema(
        _candidate_json_fence(zh_section, label="Chinese desktop fitting docs"),
        label="Chinese desktop fitting docs",
    )

    forbidden = (
        "auto-fit",
        "automatic model selection",
        "automatic fitting",
        "best model",
        "winner",
        "recommendation",
        "自动拟合",
        "最佳",
        "推荐",
    )
    assert all(term not in combined for term in forbidden)


def test_cli_batch_config_no_longer_advertises_auto_fit(tmp_path):
    from cli.batch_config import ALLOWED_OPERATIONS, load_batch_config

    assert "auto_fit" not in ALLOWED_OPERATIONS

    data_path = tmp_path / "data.csv"
    data_path.write_text("x,y\n1,2\n2,4\n", encoding="utf-8")
    cfg_path = tmp_path / "batch.yml"
    cfg_path.write_text(
        "\n".join(
            [
                "jobs:",
                "  - name: legacy",
                "    operation: auto_fit",
                f"    data_path: {data_path}",
                f"    output_dir: {tmp_path / 'out'}",
            ]
        ),
        encoding="utf-8",
    )

    try:
        load_batch_config(cfg_path)
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - assertion path
        raise AssertionError("legacy auto_fit operation should be rejected")

    assert "unknown operation" in message
    assert "auto_fit" in message


def test_fitting_package_no_longer_exports_auto_fit():
    import fitting

    assert not hasattr(fitting, "auto_fit_dataset")
