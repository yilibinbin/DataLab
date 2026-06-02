from __future__ import annotations

import pytest

from shared.computation_inputs import (
    ComputationInputContext,
    SymbolCategories,
    build_data_rows,
    classify_expression_symbols,
    extract_uncertainties,
    merge_scope,
    validate_symbol_classification,
)
from shared.input_normalization import normalize_constants_state
from shared.uncertainty import parse_uncertainty_format


def test_classification_rejects_data_constant_collision() -> None:
    classification = classify_expression_symbols(
        ["x**2 - A"],
        SymbolCategories(
            unknowns=("x",),
            data_columns=("A",),
            constants=("A",),
        ),
    )

    with pytest.raises(ValueError, match=r"collision|冲突"):
        validate_symbol_classification(classification)


def test_classification_reports_missing_symbols() -> None:
    classification = classify_expression_symbols(
        ["x**2 - A"],
        SymbolCategories(unknowns=("x",), data_columns=(), constants=()),
    )

    assert classification.missing_symbols == ("A",)
    with pytest.raises(ValueError, match=r"A"):
        validate_symbol_classification(classification)


def test_classification_recognizes_parameters_and_targets() -> None:
    classification = classify_expression_symbols(
        ["a*x - y"],
        SymbolCategories(
            unknowns=("x",),
            parameters=("a",),
            targets=("y",),
        ),
    )

    assert classification.used_symbols == ("a", "x", "y")
    assert classification.missing_symbols == ()
    validate_symbol_classification(classification)


def test_classification_rejects_all_category_collisions() -> None:
    for categories in (
        SymbolCategories(unknowns=("A",), data_columns=("A",)),
        SymbolCategories(unknowns=("A",), constants=("A",)),
        SymbolCategories(unknowns=("A",), parameters=("A",)),
        SymbolCategories(unknowns=("A",), targets=("A",)),
        SymbolCategories(data_columns=("A",), constants=("A",)),
        SymbolCategories(data_columns=("A",), parameters=("A",)),
        SymbolCategories(data_columns=("A",), targets=("A",)),
        SymbolCategories(constants=("A",), parameters=("A",)),
        SymbolCategories(constants=("A",), targets=("A",)),
        SymbolCategories(parameters=("A",), targets=("A",)),
    ):
        classification = classify_expression_symbols(["A"], categories)

        with pytest.raises(ValueError, match=r"collision|冲突"):
            validate_symbol_classification(classification)


def test_symbol_categories_normalize_and_dedupe_names() -> None:
    categories = SymbolCategories(
        unknowns=(" x ", "x", ""),
        data_columns=(" A ", "A"),
        constants=(" C ", "C"),
        parameters=(" p ", "p"),
        targets=(" y ", "y"),
    )

    assert categories.unknowns == ("x",)
    assert categories.data_columns == ("A",)
    assert categories.constants == ("C",)
    assert categories.parameters == ("p",)
    assert categories.targets == ("y",)


def test_build_data_rows_preserves_nominal_values_and_uncertainties() -> None:
    rows = build_data_rows(
        ("A", "B"),
        ((parse_uncertainty_format("4.0(2)"), parse_uncertainty_format("5.0")),),
    )

    assert rows[0].index == 0
    assert str(rows[0].values["A"]) == "4.0"
    assert str(rows[0].uncertainties["A"].uncertainty) == "0.2"
    assert str(rows[0].values["B"]) == "5.0"


def test_build_data_rows_rejects_non_identifier_headers() -> None:
    with pytest.raises(ValueError, match=r"Invalid data column name|数据列名无效"):
        build_data_rows(("mass (kg)",), ((parse_uncertainty_format("1.0"),),))


def test_computation_input_context_exposes_spec_fields() -> None:
    rows = build_data_rows(("A",), ((parse_uncertainty_format("4.0"),),))
    constants_state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "C", "value": "3.0"}],
        numeric_mode="uncertainty",
    )
    categories = SymbolCategories(data_columns=("A",), constants=("C",))

    context = ComputationInputContext(
        data_rows=rows,
        constants_state=constants_state,
        categories=categories,
    )

    assert context.data_rows == rows
    assert context.constants_state is constants_state
    assert context.categories == categories


def test_merge_scope_rejects_unvalidated_shadowing() -> None:
    rows = build_data_rows(("A",), ((parse_uncertainty_format("4.0"),),))

    with pytest.raises(ValueError, match=r"collision|冲突"):
        merge_scope(rows[0], {"A": "3.0"}, {"x": "2.0"})


def test_merge_scope_without_row_combines_constants_and_unknowns() -> None:
    scope = merge_scope(None, {"A": "3.0"}, {"x": "2.0"})

    assert str(scope["A"]) == "3.0"
    assert str(scope["x"]) == "2.0"


def test_merge_scope_without_row_rejects_constant_unknown_collision() -> None:
    with pytest.raises(ValueError, match=r"collision|冲突"):
        merge_scope(None, {"A": "3.0"}, {"A": "2.0"})


def test_extract_uncertainties_combines_row_and_constants_state() -> None:
    rows = build_data_rows(("A",), ((parse_uncertainty_format("4.0(2)"),),))
    constants_state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "C", "value": "3.0(1)"}],
        numeric_mode="uncertainty",
    )

    uncertainties = extract_uncertainties(rows[0], constants_state)

    assert set(uncertainties) == {"A", "C"}
    assert str(uncertainties["A"].uncertainty) == "0.2"
    assert str(uncertainties["C"].uncertainty) == "0.1"


def test_extract_uncertainties_without_row_returns_constants_only() -> None:
    constants_state = normalize_constants_state(
        enabled=True,
        rows=[{"name": "C", "value": "3.0(1)"}],
        numeric_mode="uncertainty",
    )

    uncertainties = extract_uncertainties(None, constants_state)

    assert set(uncertainties) == {"C"}
    assert str(uncertainties["C"].uncertainty) == "0.1"
