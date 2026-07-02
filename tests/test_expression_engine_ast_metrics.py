"""Direct tests for shared.expression_engine._ast_metrics.

_ast_metrics computes (max_depth, node_count) for an AST; it backs the
complexity guard in _parse_validated_expression.
"""

from __future__ import annotations

import ast

from shared.expression_engine import _ast_metrics


def _metrics(source: str) -> tuple[int, int]:
    return _ast_metrics(ast.parse(source, mode="eval"))


def test_single_number_literal() -> None:
    # Expression(root, depth 1) -> Constant(depth 2).
    depth, nodes = _metrics("1")
    assert depth == 2
    assert nodes == 2


def test_bare_name() -> None:
    # Expression -> Name -> Load context node.
    depth, nodes = _metrics("x")
    assert depth == 3
    assert nodes == 3


def test_flat_binop_depth() -> None:
    # a + b : Expression -> BinOp -> {Name a, Add, Name b} -> Load ctx nodes.
    depth_flat, _ = _metrics("a + b")
    depth_nested, _ = _metrics("a + b + c")
    # Left-associative chaining deepens the tree.
    assert depth_nested > depth_flat


def test_deeper_nesting_increases_depth() -> None:
    # Redundant parens are collapsed by ast.parse, so nest via real operators.
    shallow, _ = _metrics("a + b")
    deep, _ = _metrics("a + (b + (c + d))")
    assert deep > shallow


def test_node_count_grows_with_terms() -> None:
    _, few = _metrics("a + b")
    _, many = _metrics("a + b + c + d")
    assert many > few


def test_node_count_counts_all_nodes() -> None:
    # Verify against an independent walk of the same tree.
    tree = ast.parse("sin(a) + cos(b)", mode="eval")
    _, nodes = _ast_metrics(tree)
    assert nodes == sum(1 for _ in ast.walk(tree))


def test_depth_matches_manual_computation() -> None:
    tree = ast.parse("a * b", mode="eval")
    depth, _ = _ast_metrics(tree)

    def _depth(node: ast.AST, current: int = 1) -> int:
        children = list(ast.iter_child_nodes(node))
        if not children:
            return current
        return max(_depth(child, current + 1) for child in children)

    assert depth == _depth(tree)
