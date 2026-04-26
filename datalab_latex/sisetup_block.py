"""Single source of truth for ``\\sisetup{...}`` preamble generation.

DataLab emits a ``\\sisetup{...}`` block in every fit / statistics /
error-propagation document. The block lives behind a helper here so:

1. The five legacy emitters (latex_tables_common, statistics_utils [x2],
   app_desktop/fitting_latex_writer, app_web/logic/fitting) share the
   same body — adding a key in one site no longer drifts.

2. siunitx version compatibility lives in one place. siunitx v3
   (TeX Live ≥ 2020) introduced ``digit-group-size`` and renamed
   several legacy keys; siunitx v2 documents fail with
   ``LaTeX3 Error: The key 'siunitx/digit-group-size' is unknown``.
   The helper emits a ``\\@ifpackagelater`` guard so the v3-only
   override is conditional on a v3 install, while v2 falls back to
   siunitx's built-in default of "group every 3 digits".

The helper returns the formatted block as a string; callers append
it to their preamble list. Callers MUST also keep ``\\usepackage{siunitx}``
in their preamble (this helper does not touch the load order).
"""

from __future__ import annotations


def build_sisetup_block(
    *,
    group_size: int,
    include_dcolumn: bool,
) -> str:
    """Return the preamble block for siunitx number formatting.

    Parameters
    ----------
    group_size:
        Digits per group when grouping is enabled. ``3`` matches
        siunitx's built-in default and produces ``1\\,234\\,567`` style
        thousands separators. ``0`` disables grouping outright. Other
        values use the v3-only ``digit-group-size`` override (siunitx
        v2 silently uses 3 in that case — the document still compiles).
    include_dcolumn:
        When ``True`` the document uses dcolumn for alignment; siunitx
        must NOT emit grouping characters or the alignment breaks. The
        block emits the minimal "no grouping" body in that case.

    Returns
    -------
    str
        Multi-line LaTeX block including a leading comment, the
        ``\\sisetup{...}`` body, optional ``\\@ifpackagelater`` guard,
        and a trailing blank line. Already terminated with ``\\n``.
    """
    lines: list[str] = [
        "% Configure siunitx for tight number spacing (v2/v3 compatible)",
        "\\sisetup{",
    ]

    if include_dcolumn:
        # dcolumn handles alignment; siunitx must not emit group separators.
        lines.extend(
            [
                "    group-digits = false,",
                "    tight-spacing = true,",
                "    uncertainty-mode = compact,",
                "}",
                "",
            ]
        )
        return "\n".join(lines) + "\n"

    if group_size <= 0:
        lines.extend(
            [
                "    group-digits = false,",
                "    tight-spacing = true,",
                "    uncertainty-mode = compact,",
                "}",
                "",
            ]
        )
        return "\n".join(lines) + "\n"

    # group_size > 0 path: keys that work on BOTH siunitx v2 and v3.
    # ``digit-group-size`` is v3-only and goes in the @ifpackagelater
    # guard below.
    lines.extend(
        [
            "    group-digits = decimal,",
            r"    group-separator = {\,},",
            f"    group-minimum-digits = {group_size},",
            "    tight-spacing = true,",
            "    uncertainty-mode = compact,",
            "}",
        ]
    )

    if group_size != 3:
        # ``digit-group-size`` is a siunitx-v3 key but its presence in
        # the source tree predates its activation in the dispatcher:
        # siunitx 3.0.49 (date 2022-02-15) — the version Tectonic
        # currently bundles — has ``digit-group-size`` defined in
        # siunitx.sty yet still rejects ``\sisetup{digit-group-size = N}``
        # at runtime with ``LaTeX3 Error: The key 'siunitx/digit-group-
        # size' is unknown``. The key reaches a working dispatcher
        # only in later 3.x releases (verified working on 3.4.14
        # from 2025-07-09).
        #
        # The cutoff was originally pinned to 2020/01/01 (siunitx v3
        # introduction date), then 2020/02/08 (3.0.0 release). Both
        # were too early — the 2022-02-15 Tectonic siunitx slips past
        # those guards and fires the override against an installation
        # that doesn't honour the key. ``2024/01/01`` is the empirical
        # safe cutoff: confirmed Tectonic-bundled v3.0.49 evaluates as
        # earlier (override skipped, fall back to size 3 default which
        # still compiles) and TeX Live 2025 v3.4.14 evaluates as later
        # (override fires, requested size honoured).
        #
        # ``\@ifpackagelater`` is an internal LaTeX2e command, so it
        # has to live inside ``\makeatletter ... \makeatother``.
        # Previous revisions tried wrapping in ``\begingroup ... \endgroup``
        # for catcode-flip safety; that was a regression because TeX
        # groups also scope ``\sisetup``'s package-state assignments,
        # silently reverting the override. Plain
        # ``\makeatletter ... \makeatother`` is the right pattern for
        # a preamble-level package-state mutation.
        lines.append(r"\makeatletter")
        lines.append(
            r"\@ifpackagelater{siunitx}{2024/01/01}{"
            f"\\sisetup{{digit-group-size = {group_size}}}"
            "}{}"
        )
        lines.append(r"\makeatother")

    lines.append("")
    return "\n".join(lines) + "\n"
