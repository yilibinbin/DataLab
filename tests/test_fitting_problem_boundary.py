from __future__ import annotations


def test_model_problem_filters_disabled_constants_and_orphan_params():
    from fitting.problem import ModelProblem, ParameterDraft, constants_for_compute, parameters_for_compute

    problem = ModelProblem(
        model_type="custom",
        expression="a*x + c0",
        variables=("x",),
        target_name="y",
        constants={"c0": "2", "draft_only": "9"},
        constants_enabled=False,
    )
    drafts = [
        ParameterDraft(name="a", initial="1"),
        ParameterDraft(name="old", initial="5", orphaned=True),
    ]

    assert constants_for_compute(problem) == {}
    assert parameters_for_compute(drafts) == {"a": {"initial": "1"}}


def test_implicit_classifier_records_observed_linear_case():
    from fitting.implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d8/(n-delta)^8",
        output_expression="delta",
        parameters=("d0", "d2", "d4", "d8"),
    )

    classification = ImplicitProblemClassifier().classify(definition)

    assert classification.strategy is ImplicitStrategy.OBSERVED_LINEAR
    assert "observed implicit variable" in classification.reason.lower()


def test_implicit_classifier_accepts_datalab_function_bracket_syntax():
    from fitting.implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
    )

    classification = ImplicitProblemClassifier().classify(definition)

    assert classification.strategy is ImplicitStrategy.OBSERVED_LINEAR


def test_implicit_classifier_uses_general_for_uncertain_parse():
    from fitting.implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
    from fitting.implicit_model import ImplicitModelDefinition

    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a +",
        output_expression="u",
        parameters=("a",),
    )

    classification = ImplicitProblemClassifier().classify(definition)

    assert classification.strategy is ImplicitStrategy.GENERAL
    assert any(word in classification.reason.lower() for word in ("parse", "uncertain", "conservative"))


def test_implicit_classifier_does_not_execute_malicious_equation(tmp_path):
    from fitting.implicit_classifier import ImplicitProblemClassifier, ImplicitStrategy
    from fitting.implicit_model import ImplicitModelDefinition

    sentinel = tmp_path / "datalab_unsafe_classifier"
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation=f'__import__("os").system("touch {sentinel}")',
        output_expression="u",
        parameters=("a",),
    )

    classification = ImplicitProblemClassifier().classify(definition)

    assert classification.strategy is ImplicitStrategy.GENERAL
    assert not sentinel.exists()
