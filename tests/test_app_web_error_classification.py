from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("flask")

from app_web.blueprints.pages import _error_key_for_exception

ROOT = Path(__file__).resolve().parent.parent
I18N_PATH = ROOT / "app_web" / "static" / "js" / "i18n.js"


def test_comparison_candidates_json_error_maps_to_parse_key() -> None:
    # A malformed JSON paste in the fit comparison-candidates textarea must surface a
    # parse-specific message, not the generic "Computation failed." fallback.
    try:
        json.loads("[{bad}]")
    except ValueError as exc:
        err = ValueError(f"comparison candidates must be valid JSON: {exc}")
    assert _error_key_for_exception(err) == "errors.formula_parse_failed"


def test_units_unsupported_on_web_maps_to_dedicated_key() -> None:
    err = ValueError("unit_evaluation_unsupported_on_web")
    assert _error_key_for_exception(err) == "errors.units_unsupported_on_web"


def test_unknown_error_still_falls_back_to_generic() -> None:
    assert _error_key_for_exception(ValueError("totally unrelated")) == "errors.compute_failed"


def test_new_error_keys_defined_in_both_languages() -> None:
    text = I18N_PATH.read_text(encoding="utf-8")
    occurrences = re.findall(r"'errors\.units_unsupported_on_web'\s*:", text)
    # Defined once in the zh block and once in the en block.
    assert len(occurrences) == 2


def test_fit_template_data_i18n_keys_defined_in_both_languages() -> None:
    # Every data-i18n key used in fit.html must be defined in i18n.js for BOTH languages,
    # so newly added diagnostic tables don't render hardcoded English under the zh UI.
    fit_html = (ROOT / "app_web" / "templates" / "fit.html").read_text(encoding="utf-8")
    i18n = I18N_PATH.read_text(encoding="utf-8")
    keys = set(re.findall(r'data-i18n="([^"]+)"', fit_html))
    assert keys, "expected data-i18n keys in fit.html"
    underdefined = {
        key: len(re.findall(rf"'{re.escape(key)}'\s*:", i18n))
        for key in keys
        if len(re.findall(rf"'{re.escape(key)}'\s*:", i18n)) < 2
    }
    assert not underdefined, f"data-i18n keys missing zh/en definitions: {underdefined}"
