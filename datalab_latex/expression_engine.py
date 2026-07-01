"""LaTeX-facing view over the single shared safe-eval engine.

Historically this module carried a byte-for-byte copy of
``shared.expression_engine`` so LaTeX callers could import ``safe_eval`` and its
whitelist without depending on the shared package.  The duplication meant a
math function added to one allowlist silently drifted from the other (P0-3).

There is now exactly one implementation: everything is re-exported from
``shared.expression_engine`` so the two modules resolve to the *same* objects
(the allowlists are identical by identity, verified by an engine-parity test).
The only LaTeX-specific behavior — ``format_latex_formula`` actually rendering a
display string — is overridden below to route through the render service, which
the LaTeX-independent shared engine deliberately leaves as a passthrough.
"""

from __future__ import annotations

from datalab_latex import formula_render_service

# Bilingual helpers re-exported for backward compatibility (data_extrapolation_
# latex_latest auto-re-exports this module's public symbols). Import from their
# origin so mypy --strict sees them as explicit exports.
from shared.bilingual import _dual_msg, _split_dual  # noqa: F401  (re-export)

# The single source of truth. Re-export the full public + private surface so
# existing callers (fitting.symbolic_export imports _ALLOWED_FUNCTIONS,
# _ALLOWED_CONSTANTS, _ast_metrics, _normalize_expression; several tests reach
# for other underscore-prefixed helpers) keep resolving to the same objects.
from shared.expression_engine import (  # noqa: F401  (re-export)
    MAX_AST_DEPTH,
    MAX_AST_NODES,
    _ALLOWED_CONSTANTS,
    _ALLOWED_FUNCTIONS,
    _ast_metrics,
    _detect_lowercase_allowed_function_calls,
    _evaluate_ast,
    _mp,
    _mp_numeric_literal,
    _normalize_expression,
    _resolve_callable,
    _resolve_name,
    list_allowed_functions,
    safe_eval,
)

# Explicit re-export list so mypy --strict treats these names as exported
# attributes of this module (consumers import several of them by name).
__all__ = [
    "MAX_AST_DEPTH",
    "MAX_AST_NODES",
    "_ALLOWED_CONSTANTS",
    "_ALLOWED_FUNCTIONS",
    "_ast_metrics",
    "_detect_lowercase_allowed_function_calls",
    "_dual_msg",
    "_evaluate_ast",
    "_mp",
    "_mp_numeric_literal",
    "_normalize_expression",
    "_resolve_callable",
    "_resolve_name",
    "_split_dual",
    "format_latex_formula",
    "list_allowed_functions",
    "safe_eval",
]


def format_latex_formula(formula_str: str) -> str:
    """Format a formula string for LaTeX display through the shared render service."""
    return formula_render_service.format_formula_latex(formula_str)
