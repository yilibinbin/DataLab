from __future__ import annotations

import pytest

from data_extrapolation_latex_latest import safe_eval


def test_safe_eval_limits_ast_nodes(monkeypatch) -> None:
    # datalab_latex.expression_engine is a shim; the constant lives on the shared
    # implementation module that safe_eval actually reads from (P0-3 collapse).
    import shared.expression_engine as engine

    monkeypatch.setattr(engine, "MAX_AST_NODES", 50)

    expr = "+".join(["1"] * 200)
    with pytest.raises(ValueError) as excinfo:
        safe_eval(expr, {})

    message = str(excinfo.value)
    assert ("过于复杂" in message) or ("too complex" in message)

