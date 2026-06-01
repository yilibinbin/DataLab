from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_implicit_detectors_use_shared_symbolic_parser_boundary() -> None:
    source = (REPO_ROOT / "fitting" / "output_inversion.py").read_text(encoding="utf-8")

    assert "from shared.symbolic_math import parse_symbolic_expression" in source
    assert "parse_symbolic_expression(" in source


def test_obsolete_implicit_strategy_modules_are_absent() -> None:
    assert not (REPO_ROOT / "fitting" / "implicit_transforms.py").exists()
    assert not (REPO_ROOT / "fitting" / "implicit_seed_hints.py").exists()


def test_obsolete_implicit_strategy_exports_are_absent() -> None:
    public_source = (REPO_ROOT / "fitting" / "__init__.py").read_text(encoding="utf-8")

    for name in (
        "OutputTransform",
        "detect_output_transform",
        "ImplicitSeedHint",
        "detect_seed_hint",
    ):
        assert name not in public_source
