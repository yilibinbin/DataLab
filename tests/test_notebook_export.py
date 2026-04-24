"""Jupyter Notebook export (Phase 3 #11) — regression tests.

Users fit data in DataLab, then want to continue the analysis in a
notebook. ``notebook_export.build_notebook`` emits a valid
``.ipynb`` file containing:
- A markdown cell summarising the fit (model, parameters, R²)
- A code cell that replays the fit using the public Python API so the
  notebook is reproducible offline
- An optional code cell with matplotlib plotting

The notebook must be nbformat-4-valid so it opens in Jupyter Lab
and Colab without manual edits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_build_notebook_returns_valid_ipynb_structure():
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="Test fit",
        xs=[1.0, 2.0, 3.0, 4.0, 5.0],
        ys=[2.1, 3.9, 6.2, 7.8, 9.9],
        model_label="linear",
        params={"b0": 0.02, "b1": 1.97},
    )
    # Top-level required fields per nbformat 4.x
    assert nb["nbformat"] == 4
    assert nb["nbformat_minor"] >= 0
    assert "metadata" in nb
    assert "cells" in nb
    assert isinstance(nb["cells"], list)
    assert len(nb["cells"]) >= 2, "Must have at least summary + code cells"


def test_build_notebook_cells_are_well_formed():
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="Test",
        xs=[1.0, 2.0],
        ys=[1.0, 2.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
    )
    for cell in nb["cells"]:
        assert "cell_type" in cell
        assert cell["cell_type"] in ("markdown", "code")
        assert "source" in cell
        if cell["cell_type"] == "code":
            assert "execution_count" in cell
            assert "outputs" in cell
            assert "metadata" in cell


def test_build_notebook_has_markdown_summary_cell():
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="My Beautiful Fit",
        xs=[1.0, 2.0],
        ys=[1.0, 2.0],
        model_label="linear",
        params={"b0": 0.5, "b1": 0.75},
    )
    markdowns = [c for c in nb["cells"] if c["cell_type"] == "markdown"]
    assert markdowns, "Need at least one markdown cell"
    md_text = "".join(markdowns[0]["source"])
    assert "My Beautiful Fit" in md_text
    assert "linear" in md_text
    assert "b0" in md_text and "b1" in md_text


def test_build_notebook_code_cell_is_executable_python():
    """The code cell must be syntactically-valid Python — basic smoke
    test via ``compile``."""
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="T",
        xs=[1.0, 2.0, 3.0],
        ys=[1.0, 2.0, 3.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
    )
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code_cells
    for cell in code_cells:
        source = "".join(cell["source"])
        # Must not raise SyntaxError
        compile(source, "<notebook>", "exec")


def test_write_notebook_to_file(tmp_path: Path):
    from datalab_latex.notebook_export import build_notebook, write_notebook

    nb = build_notebook(
        title="File test",
        xs=[1.0],
        ys=[1.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
    )
    out = tmp_path / "out.ipynb"
    write_notebook(nb, out)
    assert out.exists()
    # Must be valid JSON
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["nbformat"] == 4


def test_build_notebook_escapes_special_chars_in_title():
    """A user-provided title must not corrupt the JSON."""
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title='Fit with "quotes" and \\ backslashes',
        xs=[1.0],
        ys=[1.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
    )
    # Round-trip through JSON
    text = json.dumps(nb)
    reloaded = json.loads(text)
    assert reloaded == nb


def test_build_notebook_kernelspec_is_python3():
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="K",
        xs=[1.0],
        ys=[1.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
    )
    ks = nb["metadata"].get("kernelspec", {})
    assert ks.get("name") in ("python3", "python")
    assert ks.get("language") == "python"


def test_build_notebook_rejects_empty_data():
    from datalab_latex.notebook_export import build_notebook

    with pytest.raises(ValueError):
        build_notebook(
            title="t", xs=[], ys=[], model_label="linear", params={}
        )


def test_build_notebook_rejects_mismatched_lengths():
    from datalab_latex.notebook_export import build_notebook

    with pytest.raises(ValueError):
        build_notebook(
            title="t",
            xs=[1.0, 2.0, 3.0],
            ys=[1.0, 2.0],  # wrong length
            model_label="linear",
            params={"b0": 0.0, "b1": 1.0},
        )


def test_build_notebook_includes_plot_cell_when_requested():
    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="P",
        xs=[1.0, 2.0, 3.0],
        ys=[1.0, 2.0, 3.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
        include_plot=True,
    )
    code_sources = "".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"
    )
    assert "matplotlib" in code_sources or "plt" in code_sources


def test_nbformat_validates_when_available(tmp_path: Path):
    """If ``nbformat`` is installed, use it for authoritative validation."""
    nbformat = pytest.importorskip("nbformat")

    from datalab_latex.notebook_export import build_notebook

    nb = build_notebook(
        title="Validation test",
        xs=[1.0, 2.0],
        ys=[1.0, 2.0],
        model_label="linear",
        params={"b0": 0.0, "b1": 1.0},
    )
    # nbformat.validate raises on invalid structure
    nbformat.validate(nb)
