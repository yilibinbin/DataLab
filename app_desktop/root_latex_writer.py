from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from datalab_latex.latex_tables_root import build_root_latex_document as build_root_latex_document

__all__ = ["build_root_latex_document", "write_root_latex"]


def write_root_latex(
    *,
    output_path: str,
    rows: Sequence[Mapping[str, object]],
    caption: str | None = None,
    digits: int = 16,
    uncertainty_digits: int = 1,
    group_size: int = 3,
    include_dcolumn: bool = False,
    language: str = "zh",
    root_units: Mapping[str, str] | None = None,
    native_group_width: bool = True,
) -> Path:
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        build_root_latex_document(
            rows=rows,
            caption=caption,
            digits=digits,
            uncertainty_digits=uncertainty_digits,
            group_size=group_size,
            include_dcolumn=include_dcolumn,
            language=language,
            root_units=root_units,
            native_group_width=native_group_width,
        ),
        encoding="utf-8",
    )
    return path
