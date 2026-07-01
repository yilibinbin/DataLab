#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

import mpmath as mp

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_desktop.fitting_latex_writer import build_fit_latex_block, build_fit_latex_preamble  # noqa: E402
from app_desktop.root_latex_writer import write_root_latex  # noqa: E402
from data_extrapolation_latex_latest import (
    ExtrapolationOptions,
    apply_formula_to_data,
    generate_error_propagation_table,
    generate_latex_table,
    parse_uncertainty_format,
    process_data_string,
)  # noqa: E402
from fitting.hp_fitter import FitResult  # noqa: E402
from shared.latex_engine import tectonic_compile_argv  # noqa: E402
from statistics_utils import compute_statistics, generate_statistics_latex_batches  # noqa: E402


MATRIX_MODULES = (
    "error_propagation",
    "statistics",
    "fitting",
    "root_solving",
    "extrapolation",
)


@dataclass(frozen=True)
class CompileResult:
    module: str
    use_dcolumn: bool
    group_size: int
    caption_kind: str
    engine: str | None
    engine_path: str | None
    returncode: int | None
    tex_path: str
    pdf_path: str
    status: str
    first_error_excerpt: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def skipped_missing_engine(self) -> bool:
        return self.status == "skipped_missing_engine"


def build_desktop_generated_tex(
    out_dir: Path | str,
    *,
    module: str,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    tex_path = out_path / f"{module}-{_option_slug(use_dcolumn, group_size, caption)}.tex"
    if module == "error_propagation":
        return _build_error_propagation_tex(tex_path, use_dcolumn=use_dcolumn, group_size=group_size, caption=caption)
    if module == "statistics":
        return _build_statistics_tex(tex_path, use_dcolumn=use_dcolumn, group_size=group_size, caption=caption)
    if module == "fitting":
        return _build_fitting_tex(tex_path, use_dcolumn=use_dcolumn, group_size=group_size, caption=caption)
    if module == "root_solving":
        return _build_root_solving_tex(tex_path, use_dcolumn=use_dcolumn, group_size=group_size, caption=caption)
    if module == "extrapolation":
        return _build_extrapolation_tex(tex_path, use_dcolumn=use_dcolumn, group_size=group_size, caption=caption)
    raise ValueError(f"Unknown LaTeX matrix module: {module}")


def compile_latex_with_available_engine(
    tex_path: Path | str,
    *,
    module: str = "",
    use_dcolumn: bool = False,
    group_size: int = 3,
    caption_kind: str = "",
    engine_candidates: Iterable[tuple[str, str]] | None = None,
) -> CompileResult:
    tex = Path(tex_path)
    discovered = list(_discover_engines() if engine_candidates is None else engine_candidates)
    if not discovered:
        return CompileResult(
            module=module,
            use_dcolumn=use_dcolumn,
            group_size=group_size,
            caption_kind=caption_kind,
            engine=None,
            engine_path=None,
            returncode=None,
            tex_path=str(tex),
            pdf_path=str(tex.with_suffix(".pdf")),
            status="skipped_missing_engine",
            first_error_excerpt="No LaTeX engine found. Checked DATALAB_LATEX_ENGINE, xelatex, pdflatex, tectonic.",
        )
    return _compile_latex_with_engine(
        tex,
        engine=discovered[0][0],
        engine_path=discovered[0][1],
        module=module,
        use_dcolumn=use_dcolumn,
        group_size=group_size,
        caption_kind=caption_kind,
    )


def compile_latex_with_engines(
    tex_path: Path | str,
    *,
    module: str = "",
    use_dcolumn: bool = False,
    group_size: int = 3,
    caption_kind: str = "",
    engine_candidates: Iterable[tuple[str, str]] | None = None,
) -> list[CompileResult]:
    tex = Path(tex_path)
    discovered = list(_discover_engines() if engine_candidates is None else engine_candidates)
    if not discovered:
        return [
            CompileResult(
                module=module,
                use_dcolumn=use_dcolumn,
                group_size=group_size,
                caption_kind=caption_kind,
                engine=None,
                engine_path=None,
                returncode=None,
                tex_path=str(tex),
                pdf_path=str(tex.with_suffix(".pdf")),
                status="skipped_missing_engine",
                first_error_excerpt="No LaTeX engine found. Checked DATALAB_LATEX_ENGINE, xelatex, pdflatex, tectonic.",
            )
        ]
    return [
        _compile_latex_with_engine(
            tex,
            engine=engine,
            engine_path=engine_path,
            module=module,
            use_dcolumn=use_dcolumn,
            group_size=group_size,
            caption_kind=caption_kind,
        )
        for engine, engine_path in discovered
    ]


def _compile_latex_with_engine(
    tex: Path,
    *,
    engine: str,
    engine_path: str,
    module: str,
    use_dcolumn: bool,
    group_size: int,
    caption_kind: str,
) -> CompileResult:
    pdf = tex.with_suffix(".pdf")
    command = _compile_command(engine, engine_path, tex)
    try:
        completed = subprocess.run(
            command,
            cwd=str(tex.parent),
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = _engine_output(completed.stdout, completed.stderr, tex)
        status = "ok" if completed.returncode == 0 and pdf.exists() else "failed"
        return CompileResult(
            module=module,
            use_dcolumn=use_dcolumn,
            group_size=group_size,
            caption_kind=caption_kind,
            engine=engine,
            engine_path=engine_path,
            returncode=completed.returncode,
            tex_path=str(tex),
            pdf_path=str(pdf),
            status=status,
            first_error_excerpt="" if status == "ok" else _first_error_excerpt(output),
        )
    except subprocess.TimeoutExpired as exc:
        output = _engine_output(exc.stdout, exc.stderr, tex)
        return CompileResult(
            module=module,
            use_dcolumn=use_dcolumn,
            group_size=group_size,
            caption_kind=caption_kind,
            engine=engine,
            engine_path=engine_path,
            returncode=None,
            tex_path=str(tex),
            pdf_path=str(pdf),
            status="timeout",
            first_error_excerpt=_first_error_excerpt(output or "LaTeX engine timed out."),
        )
    except OSError as exc:
        return CompileResult(
            module=module,
            use_dcolumn=use_dcolumn,
            group_size=group_size,
            caption_kind=caption_kind,
            engine=engine,
            engine_path=engine_path,
            returncode=None,
            tex_path=str(tex),
            pdf_path=str(pdf),
            status="failed",
            first_error_excerpt=f"Unable to start LaTeX engine {engine} at {engine_path}: {exc}",
        )


def run_matrix(out_dir: Path | str) -> list[CompileResult]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results: list[CompileResult] = []
    for module in MATRIX_MODULES:
        for use_dcolumn in (False, True):
            for group_size in (0, 3, 4):
                for caption in ("", "中文标题", "English caption"):
                    tex_path = build_desktop_generated_tex(
                        out / module,
                        module=module,
                        use_dcolumn=use_dcolumn,
                        group_size=group_size,
                        caption=caption,
                    )
                    results.extend(
                        compile_latex_with_engines(
                            tex_path,
                            module=module,
                            use_dcolumn=use_dcolumn,
                            group_size=group_size,
                            caption_kind=_caption_kind(caption),
                        )
                    )
    _write_manifest(out / "manifest.json", results)
    return results


def _build_error_propagation_tex(
    tex_path: Path,
    *,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> Path:
    headers = ["x", "y"]
    parsed_data = [
        [parse_uncertainty_format("1.234(12)", lang="zh"), parse_uncertainty_format("2.0[3]", lang="zh")],
        [parse_uncertainty_format("1.456(15)", lang="zh"), parse_uncertainty_format("2.2[4]", lang="zh")],
    ]
    constants = {"c": parse_uncertainty_format("0.50(2)", lang="zh")}
    formula = "x*y + c"
    results = apply_formula_to_data(headers, parsed_data, constants, formula, verbose=False, return_components=True)
    generate_error_propagation_table(
        headers,
        parsed_data,
        results,
        constants,
        formula,
        str(tex_path),
        caption=caption or None,
        verbose=False,
        use_dcolumn=use_dcolumn,
        precision=12,
        result_uncertainty_digits=2,
        used_columns=headers,
        latex_group_size=group_size,
    )
    return tex_path


def _build_statistics_tex(
    tex_path: Path,
    *,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> Path:
    uncertain = [
        parse_uncertainty_format("1.000(12)[0]", lang="zh"),
        parse_uncertainty_format("1.050(14)[0]", lang="zh"),
        parse_uncertainty_format("0.980(11)[0]", lang="zh"),
    ]
    values = [entry.value for entry in uncertain]
    sigmas = [entry.uncertainty for entry in uncertain]
    result = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)
    batches = [
        {
            "index": 1,
            "headers": ["Value"],
            "value_col": "Value",
            "rows": [(entry.value,) for entry in uncertain],
            "sigma_rows": [(entry,) for entry in uncertain],
            "values": values,
            "sigmas": sigmas,
            "result": result,
            "row_count": len(uncertain),
        }
    ]
    generate_statistics_latex_batches(
        "Value",
        batches,
        12,
        str(tex_path),
        use_dcolumn,
        caption=caption or None,
        uncertainty_digits=2,
        latex_group_size=group_size,
    )
    return tex_path


def _build_fitting_tex(
    tex_path: Path,
    *,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> Path:
    fit_result = FitResult(
        params={"A": mp.mpf("1.25"), "B": mp.mpf("0.50")},
        param_errors={"A": mp.mpf("0.02"), "B": mp.mpf("0.01")},
        chi2=mp.mpf("1.1"),
        reduced_chi2=mp.mpf("0.55"),
        aic=mp.mpf("2.0"),
        bic=mp.mpf("2.5"),
        r2=mp.mpf("0.99"),
        rmse=mp.mpf("0.001"),
        residuals=[mp.mpf("0.0"), mp.mpf("0.0")],
        fitted_curve=[mp.mpf("1.75"), mp.mpf("3.0")],
        covariance=[[mp.mpf("0.0004"), mp.mpf("0")], [mp.mpf("0"), mp.mpf("0.0001")]],
        param_errors_total={"A": mp.mpf("0.02"), "B": mp.mpf("0.01")},
    )
    lines = build_fit_latex_preamble(use_dcolumn=use_dcolumn, digits=12, latex_group_size=group_size)
    lines.extend(
        build_fit_latex_block(
            headers=["x", "y"],
            rows=[(mp.mpf("1.0"), mp.mpf("1.75")), (mp.mpf("2.0"), mp.mpf("3.0"))],
            sigma_rows=[(None, parse_uncertainty_format("0.10(2)", lang="zh")), (None, parse_uncertainty_format("0.12(2)", lang="zh"))],
            fit_result=fit_result,
            expression="A*x + B",
            substituted="1.25*x + 0.50",
            image_path=None,
            use_dcolumn=use_dcolumn,
            digits=12,
            latex_group_size=group_size,
            batch_index=None,
            target_column="y",
            variable_pairs=[("x", "x")],
            caption_text=caption or None,
            default_uncertainty_digits=2,
            cleaned_substituted="1.25*x + 0.50",
        )
    )
    lines.append("\\end{document}")
    tex_path.write_text("\n".join(lines), encoding="utf-8")
    return tex_path


def _build_root_solving_tex(
    tex_path: Path,
    *,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> Path:
    write_root_latex(
        output_path=str(tex_path),
        rows=[
            {
                "input_row_index": "1",
                "root_index": "1",
                "name": "x",
                "value": "1.4142135623730950488",
                "uncertainty": "0.0000000000000032",
                "backend": "mpmath",
                "mode": "scalar",
            }
        ],
        caption=caption or None,
        digits=16,
        uncertainty_digits=2,
        group_size=group_size,
        include_dcolumn=use_dcolumn,
        language="zh" if _caption_kind(caption) == "cjk" else "en",
    )
    return tex_path


def _build_extrapolation_tex(
    tex_path: Path,
    *,
    use_dcolumn: bool,
    group_size: int,
    caption: str,
) -> Path:
    data_text = "A B C\n1.00 1.10 1.20\n0.90 1.00 1.08\n1.20 1.28 1.35\n1.30 1.37 1.43\n"
    headers, rows, results = process_data_string(
        data_text,
        verbose=False,
        options=ExtrapolationOptions(mp_precision=60),
    )
    generate_latex_table(
        headers,
        rows,
        results,
        str(tex_path),
        caption=caption or None,
        precision=12,
        verbose=False,
        use_dcolumn=use_dcolumn,
        table_segments=[(0, 2), (2, 4)],
        result_uncertainty_digits=2,
        latex_group_size=group_size,
    )
    return tex_path


def _option_slug(use_dcolumn: bool, group_size: int, caption: str) -> str:
    return f"{'dcolumn' if use_dcolumn else 'siunitx'}-g{group_size}-{_caption_kind(caption)}"


def _caption_kind(caption: str) -> str:
    if not caption:
        return "none"
    return "cjk" if any(ord(ch) > 127 for ch in caption) else "english"


def _discover_engines() -> Sequence[tuple[str, str]]:
    _augment_common_tex_paths()
    candidates: list[tuple[str, str]] = []
    env_engine = os.environ.get("DATALAB_LATEX_ENGINE", "").strip()
    if env_engine:
        resolved = _resolve_engine_candidate(env_engine)
        if resolved is not None:
            candidates.append(resolved)
    for name in ("xelatex", "pdflatex", "tectonic"):
        resolved = _resolve_engine_candidate(name)
        if resolved is not None and resolved not in candidates:
            candidates.append(resolved)
    return tuple(candidates)


def _resolve_engine_candidate(candidate: str) -> tuple[str, str] | None:
    path_candidate = Path(candidate).expanduser()
    if path_candidate.exists():
        if path_candidate.is_file() and os.access(path_candidate, os.X_OK):
            return path_candidate.stem, str(path_candidate)
        return None
    found = shutil.which(candidate)
    if found:
        return candidate, found
    return None


def _augment_common_tex_paths() -> None:
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    for extra in ("/opt/homebrew/bin", "/usr/local/bin", "/Library/TeX/texbin"):
        if extra not in path_entries and Path(extra).exists():
            path_entries.append(extra)
    os.environ["PATH"] = os.pathsep.join(entry for entry in path_entries if entry)


def _compile_command(engine: str, engine_path: str, tex_path: Path) -> list[str]:
    if "tectonic" in Path(engine_path).name.lower() or engine.lower() == "tectonic":
        return list(tectonic_compile_argv(engine_path, tex_path))
    return [engine_path, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _engine_output(stdout: str | bytes | None, stderr: str | bytes | None, tex_path: Path) -> str:
    parts = [_output_text(stdout), _output_text(stderr)]
    log_path = tex_path.with_suffix(".log")
    if log_path.exists():
        try:
            parts.append(log_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return "\n".join(part for part in parts if part)


def _first_error_excerpt(output: str) -> str:
    if not output:
        return ""
    lines = output.splitlines()
    for idx, line in enumerate(lines):
        lower = line.lower()
        if line.startswith("!") or "error" in lower or "fatal" in lower:
            start = max(0, idx - 2)
            end = min(len(lines), idx + 18)
            return "\n".join(lines[start:end])[:8000]
    return output[:8000]


def _write_manifest(path: Path, results: Sequence[CompileResult]) -> None:
    path.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and compile GUI-style DataLab LaTeX option matrix.")
    parser.add_argument("--out", default="build/latex-option-matrix", help="Output directory for .tex/.pdf files.")
    parser.add_argument("--json", action="store_true", help="Print the manifest JSON to stdout after writing it.")
    args = parser.parse_args(argv)

    out = Path(args.out)
    results = run_matrix(out)
    manifest_path = out / "manifest.json"
    if args.json:
        print(manifest_path.read_text(encoding="utf-8"), end="")
    return 1 if any(result.status not in {"ok", "skipped_missing_engine"} for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
