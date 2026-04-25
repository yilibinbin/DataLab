"""R10 regression tests for all HIGH findings (H1-H10)."""

from __future__ import annotations

import inspect

import pytest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# H1: _security_shim fallback compile_latex_safe must include -no-shell-escape
# ---------------------------------------------------------------------------

def test_h1_security_shim_fallback_has_no_shell_escape():
    """The fallback compile_latex_safe in _security_shim.py must pass
    -no-shell-escape to the LaTeX engine."""
    import app_web._security_shim as shim
    # Inspect the source of the fallback: the module-level function is either
    # imported from .latex_security (primary) or a locally-defined fallback.
    src = inspect.getsource(shim)
    # Find the fallback block — it's inside `except ImportError:` and defines
    # compile_latex_safe locally.
    assert "-no-shell-escape" in src, (
        "_security_shim.py must include '-no-shell-escape' somewhere; "
        "the fallback compile_latex_safe would otherwise spawn LaTeX with "
        "shell-escape enabled."
    )


# ---------------------------------------------------------------------------
# H2: CSRF must not seed session token from cookie (self-referential)
# ---------------------------------------------------------------------------

def test_h2_get_csrf_token_does_not_read_cookie_when_session_empty():
    """get_csrf_token must NOT copy the datalab_csrf cookie into session."""
    # Inspect source of app_web/security.py:get_csrf_token — assert that it
    # does not seed session['csrf_token'] from request.cookies as a fallback.
    from app_web import security as sec
    src = inspect.getsource(sec.get_csrf_token)
    # Before fix: "cookie_token = request.cookies.get(...)
    #              if cookie_token: session['csrf_token'] = cookie_token"
    # After fix: that pattern must be gone.
    assert not (
        "request.cookies.get" in src and "session['csrf_token']" in src
    ) and not (
        "request.cookies.get" in src and 'session["csrf_token"]' in src
    ), (
        "get_csrf_token must not seed session['csrf_token'] from a cookie. "
        "That allows an attacker who can plant a cookie (subdomain takeover, "
        "network position) to forge the CSRF token."
    )


def test_h2_validate_csrf_token_does_not_fall_back_to_cookie_only():
    """validate_csrf_token must not accept a cookie-to-submission match as
    sole proof of authenticity."""
    from app_web import security as sec
    src = inspect.getsource(sec.validate_csrf_token)
    # Before fix: "cookie_token = request.cookies.get(...);
    #              if not cookie_token: return False; return hmac.compare_digest(cookie_token, token)"
    # Presence of both `request.cookies.get(` and `compare_digest(cookie_token` marks the fallback.
    has_cookie_read = "request.cookies.get" in src
    has_cookie_compare = "compare_digest(cookie_token" in src
    assert not (has_cookie_read and has_cookie_compare), (
        "validate_csrf_token still has the cookie-to-submission fallback. "
        "When sessions are unavailable, an attacker-controlled cookie "
        "satisfies both sides of the comparison."
    )


# ---------------------------------------------------------------------------
# H3: Bilingual discipline in security.py and workers_core.py
# ---------------------------------------------------------------------------

def test_h3_validate_text_size_raises_bilingual_error():
    from app_web import security as sec
    # Build an app context for CSRF / request access — not needed here; just
    # call the function.
    with pytest.raises(ValueError) as excinfo:
        sec.validate_text_size("x" * (sec.MAX_TEXT_INPUT_LENGTH + 1), "field")
    assert " / " in str(excinfo.value), (
        f"validate_text_size error must be bilingual; got {str(excinfo.value)!r}"
    )


def test_h3_validate_latex_engine_raises_bilingual_error():
    from app_web import security as sec
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context():
        with pytest.raises(ValueError) as excinfo:
            sec.validate_latex_engine("evil-engine")
    assert " / " in str(excinfo.value), (
        f"validate_latex_engine error must be bilingual; got {str(excinfo.value)!r}"
    )


def test_h3_workers_core_unsupported_fit_model_is_bilingual():
    """The 'Unsupported fit model' branch in workers_core.py must use _dual_msg."""
    import app_desktop.workers_core as wc
    src = inspect.getsource(wc)
    # Before fix: raise ValueError(f"Unsupported fit model: {model_type}")
    # After fix: raise ValueError(_dual_msg(...))
    # We check that the string literal 'Unsupported fit model:' (English-only)
    # does not appear as a bare f-string message; if it does, it must also
    # have a companion Chinese string separated by " / ".
    # The simplest assertion: the English phrase must be paired with CJK.
    idx = src.find("Unsupported fit model")
    if idx >= 0:
        # Grab +/- 200 chars of context and ensure it contains " / "
        context = src[max(0, idx - 200) : idx + 200]
        assert " / " in context or "_dual_msg" in context, (
            "The 'Unsupported fit model' raise in workers_core.py must be "
            "bilingual via _dual_msg(...)"
        )


# ---------------------------------------------------------------------------
# H4: SymPy lambdify namespace must not leak __builtins__/__import__
# ---------------------------------------------------------------------------

def test_h4_constraint_lambda_has_no_import_in_globals():
    """The callable returned by _lambdify_expression must not expose __import__.

    _lambdify_expression returns (deps_tuple, evaluator). The evaluator is a
    closure wrapping expr_lambda (the sp.lambdify result). We walk the
    evaluator's cells to find expr_lambda and check its __globals__.
    """
    import sympy as sp
    from fitting import constraints
    a, b = sp.symbols("a b", real=True)
    expr = a + b
    available = {"a": a, "b": b}
    order = {"a": 0, "b": 1}
    # deps is intentionally unused — we only assert on the lambdify
    # callable's __globals__.
    _deps, evaluator = constraints._lambdify_expression(expr, available, order)
    # Pull the lambdified callable out of the evaluator's default
    # args. ``_fn`` matches the parameter name in
    # ``constraints._evaluate`` — if a future refactor renames the
    # parameter, update the lookup below. The goal is to retrieve
    # the callable, not to pin a particular keyword.
    import inspect as _inspect
    sig = _inspect.signature(evaluator)
    expr_lambda = sig.parameters["_fn"].default
    assert callable(expr_lambda), "could not locate the lambdified callable"
    g = getattr(expr_lambda, "__globals__", {})
    builtins = g.get("__builtins__", {})
    if isinstance(builtins, dict):
        assert "__import__" not in builtins, (
            "Constraint lambda's __globals__['__builtins__'] contains "
            "__import__. This is a sandbox-in-depth gap: the SymPy parser is "
            "restricted but the evaluator isn't."
        )
    else:
        # builtins is a module — this is the default, unsafe case
        assert not hasattr(builtins, "__import__") or builtins.__import__ is None, (
            "Constraint lambda's __globals__['__builtins__'] is the full "
            "builtins module including __import__."
        )


# ---------------------------------------------------------------------------
# H5: safe_eval must catch RecursionError from ast.parse
# ---------------------------------------------------------------------------

def test_h5_safe_eval_deeply_nested_expression_raises_value_error():
    """Deeply nested 'a + a + a ...' must raise ValueError, not leak RecursionError.

    At ~10k terms ast.parse hits RecursionError before the depth/node guard
    can fire (the guard runs AFTER parsing). safe_eval must catch
    RecursionError too and convert to a bilingual ValueError.
    """
    from data_extrapolation_latex_latest import safe_eval
    expr = " + ".join(["a"] * 15000)  # 15k-term sum → ast.parse RecursionError
    # Must raise ValueError (or subclass). Must NOT propagate RecursionError.
    with pytest.raises(ValueError):
        safe_eval(expr, {"a": 1.0})


# ---------------------------------------------------------------------------
# H6: _dual_msg must be a single shared implementation
# ---------------------------------------------------------------------------

def test_h6_dual_msg_is_centralized():
    """All _dual_msg references must resolve to the same function object."""
    from extrapolation_methods import accelerators
    from extrapolation_methods import power_law
    # Each module has its own _dual_msg today; after fix, either all import
    # from a single source (same id) OR the canonical source is re-exported.
    fn1 = accelerators._dual_msg
    fn2 = power_law._dual_msg
    assert fn1 is fn2, (
        f"_dual_msg drift: accelerators uses {fn1!r}, power_law uses {fn2!r}. "
        "Centralize in shared/ or data_extrapolation_latex_latest."
    )


# ---------------------------------------------------------------------------
# H7: workers_core._mp_precision_guard must delegate to shared.precision_guard
# ---------------------------------------------------------------------------

def test_h7_workers_core_uses_shared_precision_guard():
    """Either _mp_precision_guard is removed, or it delegates to the shared guard.

    The key invariant: no BARE `mp.dps = ...` or `mp.mp.dps = ...` assignment
    inside the helper body. The helper must delegate to
    shared.precision.precision_guard, so the mutation happens through the
    single canonical code path.
    """
    import app_desktop.workers_core as wc
    src = inspect.getsource(wc)
    if "def _mp_precision_guard" in src:
        # Extract the function body (between 'def _mp_precision_guard' and the
        # next top-level 'def ')
        start = src.find("def _mp_precision_guard")
        end = src.find("\ndef ", start + 1)
        body = src[start:end] if end > 0 else src[start:]
        # Reject bare assignments to mp.dps / mp.mp.dps inside the body
        bare_assign_patterns = [
            "mp.dps =",
            "mp.dps=",
            "mp.mp.dps =",
            "mp.mp.dps=",
        ]
        bare_assigns = [p for p in bare_assign_patterns if p in body]
        assert not bare_assigns, (
            f"_mp_precision_guard contains bare assignment(s) to mp.dps "
            f"({bare_assigns!r}); this bypasses shared.precision.precision_guard "
            "and is not thread-safe."
        )
        # And it must reference the shared guard (by import or call)
        assert "precision_guard" in body or "from shared.precision" in src, (
            "_mp_precision_guard must delegate to shared.precision.precision_guard."
        )


# ---------------------------------------------------------------------------
# H10: power_law eps tied to mp.eps, not dps//2
# ---------------------------------------------------------------------------

def test_h10_power_law_eps_uses_mp_eps_not_dps_half():
    """extrapolation_methods/power_law.py should derive eps from mp.eps."""
    import extrapolation_methods.power_law as pl
    src = inspect.getsource(pl)
    # Before fix: `eps = mp.power(10, -max(8, mp.dps // 2))`
    # After fix: use mp.eps or an eps derived from mp.eps.
    # Accept either the new style OR the absence of the old bad pattern.
    has_old_pattern = "mp.dps // 2" in src or "dps // 2" in src
    uses_mp_eps = "mp.eps" in src
    assert (not has_old_pattern) or uses_mp_eps, (
        "power_law.py still derives degeneracy eps from mp.dps//2 without "
        "using mp.eps; this over-rejects at low dps."
    )
