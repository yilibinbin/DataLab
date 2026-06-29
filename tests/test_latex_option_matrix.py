from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.latex_option_matrix import (
    MATRIX_MODULES,
    _engine_output,
    _resolve_engine_candidate,
    build_desktop_generated_tex,
    compile_latex_with_available_engine,
    run_matrix,
)


@pytest.mark.parametrize("module", MATRIX_MODULES)
@pytest.mark.parametrize("use_dcolumn", [False, True])
@pytest.mark.parametrize("group_size", [0, 3, 4])
@pytest.mark.parametrize("caption", ["", "中文标题", "English caption"])
def test_gui_generated_latex_options_compile(
    tmp_path: Path,
    module: str,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> None:
    tex_path = build_desktop_generated_tex(
        tmp_path,
        module=module,
        use_dcolumn=use_dcolumn,
        group_size=group_size,
        caption=caption,
    )

    assert tex_path.exists()
    assert tex_path.read_text(encoding="utf-8").startswith("\\documentclass")

    result = compile_latex_with_available_engine(tex_path)

    if result.skipped_missing_engine:
        pytest.skip(result.first_error_excerpt)
    assert result.ok, result.first_error_excerpt


def test_latex_option_matrix_reports_missing_engine_distinctly(
    tmp_path: Path,
) -> None:
    tex_path = build_desktop_generated_tex(
        tmp_path,
        module="root_solving",
        use_dcolumn=False,
        group_size=3,
        caption="Engine missing",
    )

    result = compile_latex_with_available_engine(tex_path, engine_candidates=())

    assert result.status == "skipped_missing_engine"
    assert result.skipped_missing_engine is True
    assert result.ok is False
    assert result.engine is None
    assert result.engine_path is None


def test_latex_option_matrix_rejects_non_executable_path_candidates(tmp_path: Path) -> None:
    directory = tmp_path / "engine-dir"
    directory.mkdir()
    plain_file = tmp_path / "xelatex"
    plain_file.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable_file = tmp_path / "pdflatex"
    executable_file.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable_file.chmod(0o755)

    assert _resolve_engine_candidate(str(directory)) is None
    assert _resolve_engine_candidate(str(plain_file)) is None
    assert _resolve_engine_candidate(str(executable_file)) == ("pdflatex", str(executable_file))


def test_latex_option_matrix_records_engine_start_oserror(tmp_path: Path) -> None:
    tex_path = build_desktop_generated_tex(
        tmp_path,
        module="root_solving",
        use_dcolumn=False,
        group_size=3,
        caption="Bad engine",
    )

    result = compile_latex_with_available_engine(
        tex_path,
        engine_candidates=(("missing-engine", str(tmp_path / "missing-engine")),),
    )

    assert result.status == "failed"
    assert result.returncode is None
    assert result.engine == "missing-engine"
    assert "Unable to start LaTeX engine" in result.first_error_excerpt


def test_latex_option_matrix_engine_output_normalizes_bytes(tmp_path: Path) -> None:
    tex_path = tmp_path / "report.tex"

    output = _engine_output(b"stdout bytes", b"stderr bytes", tex_path)

    assert "stdout bytes" in output
    assert "stderr bytes" in output


def test_gui_generated_latex_option_text_reflects_controls(tmp_path: Path) -> None:
    ungrouped_siunitx = build_desktop_generated_tex(
        tmp_path / "ungrouped",
        module="statistics",
        use_dcolumn=False,
        group_size=0,
        caption="English caption",
    ).read_text(encoding="utf-8")
    grouped_siunitx = build_desktop_generated_tex(
        tmp_path / "without",
        module="statistics",
        use_dcolumn=False,
        group_size=4,
        caption="English caption",
    ).read_text(encoding="utf-8")
    with_dcolumn = build_desktop_generated_tex(
        tmp_path / "with",
        module="statistics",
        use_dcolumn=True,
        group_size=4,
        caption="中文标题",
    ).read_text(encoding="utf-8")

    assert "group-digits = false" in ungrouped_siunitx
    assert "group-minimum-digits" not in ungrouped_siunitx
    assert "English caption" in grouped_siunitx
    assert "中文标题" in with_dcolumn
    assert "\\usepackage{dcolumn}" not in grouped_siunitx
    assert "\\usepackage{dcolumn}" in with_dcolumn
    assert "group-minimum-digits = 4" in grouped_siunitx


def test_latex_option_matrix_records_all_fake_engines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tools.latex_option_matrix as option_matrix

    first_engine = _fake_engine(tmp_path / "fake-xelatex", "first")
    second_engine = _fake_engine(tmp_path / "fake-pdflatex", "second")
    monkeypatch.setattr(option_matrix, "MATRIX_MODULES", ("statistics",))
    monkeypatch.setattr(
        option_matrix,
        "_discover_engines",
        lambda: (("fake-xelatex", str(first_engine)), ("fake-pdflatex", str(second_engine))),
    )

    results = run_matrix(tmp_path / "matrix")
    manifest = json.loads((tmp_path / "matrix" / "manifest.json").read_text(encoding="utf-8"))

    assert len(results) == 36
    assert len(manifest) == 36
    assert {result.engine for result in results} == {"fake-xelatex", "fake-pdflatex"}
    assert all(result.ok for result in results)


def _fake_engine(path: Path, marker: str) -> Path:
    path.write_text(
        "#!/bin/sh\n"
        "tex=\"$3\"\n"
        "pdf=\"${tex%.tex}.pdf\"\n"
        "printf '%s\\n' '%PDF-1.4' > \"$pdf\"\n"
        f"printf '%s\\n' '{marker}'\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path
