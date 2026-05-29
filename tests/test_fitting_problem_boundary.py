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
