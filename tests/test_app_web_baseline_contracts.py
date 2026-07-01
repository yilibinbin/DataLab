from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("flask")

from app_web.blueprints import pages
from app_web.security import generate_csrf_token
from app_web.server import create_app

ROOT = Path(__file__).resolve().parents[1]
WEB_FORBIDDEN_ADAPTER_IMPORTS = ("app_desktop", "PySide6")


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _csrf_token(client) -> str:
    token = generate_csrf_token()
    with client.session_transaction() as session:
        session["csrf_token"] = token
    return token


def _post(client, path: str, data: dict[str, str]):
    payload = {"csrf_token": _csrf_token(client)}
    payload.update(data)
    return client.post(path, data=payload)


def _web_production_files() -> list[Path]:
    return sorted(
        path
        for path in (ROOT / "app_web").rglob("*.py")
        if not path.name.startswith("test_")
    )


def _is_forbidden_web_import(module_name: str) -> bool:
    return any(
        module_name == forbidden or module_name.startswith(forbidden + ".")
        for forbidden in WEB_FORBIDDEN_ADAPTER_IMPORTS
    )


def test_web_adapter_static_imports_do_not_depend_on_desktop_or_qt():
    violations: list[str] = []
    for path in _web_production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_web_import(alias.name):
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if _is_forbidden_web_import(node.module):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.module}")

    assert violations == []


def test_plain_web_app_startup_does_not_eagerly_import_pyplot_or_qt() -> None:
    script = """
import sys
from app_web.server import create_app

app = create_app()
if app is None:
    raise SystemExit("create_app returned None")
forbidden = [
    name
    for name in (
        "matplotlib.pyplot",
        "PySide6",
        "PySide6.QtWidgets",
        "app_desktop",
    )
    if name in sys.modules
]
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""
    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "web-startup-import-test-secret"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_plain_web_app_startup_does_not_eagerly_import_compute_logic() -> None:
    script = """
import sys
from app_web.server import create_app

app = create_app()
if app is None:
    raise SystemExit("create_app returned None")
forbidden = [
    name
    for name in (
        "app_web.logic.extrapolation",
        "app_web.logic.error_propagation",
        "app_web.logic.fitting",
        "app_web.logic.root_solving",
        "app_web.logic.statistics",
        "fitting",
        "fitting.plot_fitting",
    )
    if name in sys.modules
]
if forbidden:
    raise SystemExit("forbidden compute imports: " + ", ".join(forbidden))
print("ok")
"""
    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "web-startup-compute-import-test-secret"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


@pytest.mark.parametrize(
    ("path", "active_page"),
    [
        ("/", "extrapolation"),
        ("/error", "error"),
        ("/fit", "fit"),
        ("/stats", "stats"),
    ],
)
def test_web_get_routes_render_current_pages(client, path, active_page):
    response = client.get(path)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    nav_key = {
        "extrapolation": "nav.extrapolation",
        "error": "nav.uncertainty",
        "fit": "nav.fitting",
        "stats": "nav.statistics",
    }[active_page]
    assert "DataLab Web" in html
    assert f"window.DATALAB_PAGE_PATH = \"{path}\";" in html
    assert f'class="active" data-i18n="{nav_key}"' in html
    assert 'name="csrf_token"' in html


def test_web_get_routes_do_not_import_compute_or_desktop_stacks() -> None:
    script = """
import sys
from app_web.server import create_app

app = create_app()
app.config["TESTING"] = True
client = app.test_client()
for path in ("/", "/error", "/fit", "/stats"):
    response = client.get(path)
    if response.status_code != 200:
        raise SystemExit(f"{path} returned {response.status_code}")
    response.get_data()

forbidden = [
    name
    for name in (
        "matplotlib.pyplot",
        "PySide6",
        "PySide6.QtWidgets",
        "app_desktop",
        "app_web.logic.extrapolation",
        "app_web.logic.error_propagation",
        "app_web.logic.fitting",
        "app_web.logic.root_solving",
        "app_web.logic.statistics",
        "fitting",
        "fitting.plot_fitting",
    )
    if name in sys.modules
]
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""
    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "web-get-no-compute-import-test-secret"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_web_post_validation_errors_do_not_import_compute_or_desktop_stacks() -> None:
    script = """
import sys

from app_web.security import generate_csrf_token
from app_web.server import create_app

app = create_app()
app.config["TESTING"] = True
client = app.test_client()

def csrf_token():
    token = generate_csrf_token()
    with client.session_transaction() as session:
        session["csrf_token"] = token
    return token

cases = (
    ("/", {"data_text": "", "method": "richardson"}, "errors.missing_data"),
    (
        "/error",
        {"uncert_data_text": "", "error_formula": "x1"},
        "errors.missing_uncertainty_data",
    ),
    ("/fit", {"fit_data_text": ""}, "errors.missing_fit_data"),
    ("/stats", {"stats_data_text": ""}, "errors.missing_data"),
)
for path, data, expected_i18n_key in cases:
    payload = {"csrf_token": csrf_token()}
    payload.update(data)
    response = client.post(path, data=payload)
    if response.status_code != 200:
        raise SystemExit(f"{path} returned {response.status_code}")
    html = response.get_data(as_text=True)
    if f'data-i18n="{expected_i18n_key}"' not in html:
        raise SystemExit(f"{path} missing {expected_i18n_key}")
    if '<section class="results">' in html:
        raise SystemExit(f"{path} rendered results")

forbidden_prefixes = (
    "matplotlib.pyplot",
    "PySide6",
    "PySide6.QtWidgets",
    "app_desktop",
    "app_web.logic.extrapolation",
    "app_web.logic.error_propagation",
    "app_web.logic.fitting",
    "app_web.logic.root_solving",
    "app_web.logic.statistics",
    "fitting",
    "fitting.plot_fitting",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""
    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "web-post-validation-no-compute-import-test-secret"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


@pytest.mark.parametrize(
    ("path", "data", "expected_i18n_key"),
    [
        ("/", {"data_text": "", "method": "richardson"}, "errors.missing_data"),
        (
            "/error",
            {"uncert_data_text": "", "error_formula": "x1"},
            "errors.missing_uncertainty_data",
        ),
        ("/fit", {"fit_data_text": ""}, "errors.missing_fit_data"),
        ("/stats", {"stats_data_text": ""}, "errors.missing_data"),
    ],
)
def test_web_post_routes_return_page_level_validation_errors(
    client, path, data, expected_i18n_key
):
    response = _post(client, path, data)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'data-i18n="{expected_i18n_key}"' in html
    assert "<section class=\"results\">" not in html


def test_web_post_extrapolation_route_renders_result_bundle(client, monkeypatch):
    received: dict[str, object] = {}

    def fake_run(data_text, form, *, lang):
        received["data_text"] = data_text
        received["method"] = form.get("method")
        received["lang"] = lang
        return SimpleNamespace(
            method=form.get("method"),
            mp_precision=42,
            formatted_rows=[
                {"index": 1, "value": "1.0", "uncertainty": "0", "latex": "1.0"}
            ],
            warnings=[],
            csv_data="",
            plot_b64_list=None,
            latex_text="EXTRAPOLATION_LATEX",
            pdf_b64=None,
        )

    monkeypatch.setattr(pages, "_run_extrapolation", fake_run)

    response = _post(
        client,
        "/",
        {"data_text": pages.SAMPLE_DATA.strip(), "method": "richardson"},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<section class=\"results\">" in html
    assert "EXTRAPOLATION_LATEX" in html
    assert received == {
        "data_text": pages.SAMPLE_DATA.strip(),
        "method": "richardson",
        "lang": "zh",
    }


def test_web_post_error_route_renders_result_bundle(client, monkeypatch):
    received: dict[str, object] = {}

    def fake_run(data_text, constants_text, form, *, lang):
        received["data_text"] = data_text
        received["constants_text"] = constants_text
        received["formula"] = form.get("error_formula")
        received["lang"] = lang
        return SimpleNamespace(
            mp_precision=33,
            formatted_rows=[
                {"index": 1, "value": "2.0", "uncertainty": "0.1", "latex": "2.0(1)"}
            ],
            warnings=[],
            csv_data="",
            plot_b64=None,
            latex_text="ERROR_LATEX",
            pdf_b64=None,
        )

    monkeypatch.setattr(pages, "_run_error_propagation", fake_run)

    response = _post(
        client,
        "/error",
        {
            "uncert_data_text": pages.SAMPLE_UNCERT_DATA.strip(),
            "error_formula": "E1 + E2",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<section class=\"results\">" in html
    assert "ERROR_LATEX" in html
    assert received == {
        "data_text": pages.SAMPLE_UNCERT_DATA.strip(),
        "constants_text": "",
        "formula": "E1 + E2",
        "lang": "zh",
    }


def test_web_post_fit_route_renders_result_bundle(client, monkeypatch):
    received: dict[str, object] = {}

    def fake_run(data_text, form):
        received["data_text"] = data_text
        received["fit_mode"] = form.get("fit_mode")
        return SimpleNamespace(
            best_label="Linear / Linear",
            mp_precision=80,
            x=[1, 2],
            params=[
                {
                    "name": "a",
                    "value": "2.0",
                    "uncertainty": "0.1",
                    "latex": "2.0(1)",
                }
            ],
            metrics={
                "chi2": "0",
                "reduced_chi2": "0",
                "aic": "0",
                "bic": "0",
                "r2": "1",
                "rmse": "0",
            },
            warnings=[],
            csv_data="",
            plot_b64=None,
            summary_text="FIT_SUMMARY",
            latex_text="FIT_LATEX",
            pdf_b64=None,
        )

    monkeypatch.setattr(pages, "_run_fit", fake_run)

    response = _post(
        client,
        "/fit",
        {"fit_data_text": pages.SAMPLE_FIT_DATA.strip(), "fit_mode": "polynomial"},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<section class=\"results\">" in html
    assert "FIT_SUMMARY" in html
    assert "FIT_LATEX" in html
    assert received == {
        "data_text": pages.SAMPLE_FIT_DATA.strip(),
        "fit_mode": "polynomial",
    }


def test_web_post_fit_route_renders_comparison_table_without_single_fit_cards(client, monkeypatch):
    received: dict[str, object] = {}

    def fake_run(data_text, form):
        received["data_text"] = data_text
        received["fit_mode"] = form.get("fit_mode")
        received["candidates"] = form.get("fit_comparison_candidates")
        return SimpleNamespace(
            best_label="Selected fit comparison",
            mp_precision=60,
            x=[1, 2],
            params=[],
            metrics={},
            diagnostic_correlations=[],
            diagnostic_residuals=[],
            comparison_rows=[
                {
                    "candidate_id": "linear",
                    "order": 1,
                    "model_label": "Linear",
                    "status": "success",
                    "free_parameters": 2,
                    "chi2": "0",
                    "reduced_chi2": "0",
                    "aic": "4",
                    "bic": "5",
                    "rmse": "0",
                    "r2": "1",
                    "warnings": "",
                    "error": "",
                }
            ],
            warnings=[],
            csv_data="candidate_id,order\nlinear,1\n",
            plot_b64=None,
            summary_text="=== Selected Fit Comparison ===\nLinear | success",
            latex_text="COMPARISON_LATEX",
            pdf_b64=None,
        )

    monkeypatch.setattr(pages, "_run_fit", fake_run)

    response = _post(
        client,
        "/fit",
        {
            "fit_data_text": pages.SAMPLE_FIT_DATA.strip(),
            "fit_mode": "comparison",
            "fit_comparison_candidates": '[{"candidate_id":"linear","label":"Linear","model_type":"polynomial","poly_degree":1}]',
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Selected Fit Comparison" in html
    assert "Linear" in html
    assert "COMPARISON_LATEX" in html
    assert 'serverFitCsvData = "candidate_id,order\\nlinear,1\\n";' in html
    # The template resolves the CSV filename client-side: fitCsvIsComparison is
    # rendered true for a comparison result, and the ternary then selects the
    # comparison filename. Assert both halves rather than a server-side literal.
    assert "const fitCsvIsComparison = true;" in html
    assert "fitCsvIsComparison ? 'fitting_comparison_results.csv' : 'fit_results.csv'" in html
    assert 'data-i18n="fit.paramsLabel"' not in html
    assert 'data-i18n="fit.metricsLabel"' not in html
    assert "winner" not in html.lower()
    assert "best_model" not in html
    assert received["fit_mode"] == "comparison"
    assert "linear" in str(received["candidates"])


def test_web_post_stats_route_renders_result_bundle(client, monkeypatch):
    received: dict[str, object] = {}

    def fake_run(data_text, form, *, lang):
        received["data_text"] = data_text
        received["lang"] = lang
        return SimpleNamespace(
            mp_precision=50,
            rows=[("1",), ("2",)],
            result={
                "method_label": "Mean",
                "mean": "1.5",
                "std_mean": "0.1",
                "std": "0.2",
                "v_min": "1",
                "v_max": "2",
                "effective_n": None,
                "dropped": 0,
                "mean_latex": "1.5(1)",
            },
            warnings=[],
            csv_data="",
            raw_csv_data="",
            plot_b64=None,
            latex_text="STATS_LATEX",
            pdf_b64=None,
        )

    monkeypatch.setattr(pages, "_run_statistics", fake_run)

    response = _post(
        client,
        "/stats",
        {"stats_data_text": pages.SAMPLE_STATS_DATA.strip()},
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<section class=\"results\">" in html
    assert "STATS_LATEX" in html
    assert received == {
        "data_text": pages.SAMPLE_STATS_DATA.strip(),
        "lang": "zh",
    }
