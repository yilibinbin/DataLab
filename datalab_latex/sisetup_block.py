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
    emit_digit_group_size: bool | None = None,
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
            # ``all`` groups BOTH the integer and decimal parts (thousands separators);
            # ``decimal`` grouped only the fractional digits, so integers like 12345678
            # rendered ungrouped and users saw "grouping does nothing".
            "    group-digits = all,",
            r"    group-separator = {\,},",
            f"    group-minimum-digits = {group_size},",
            "    tight-spacing = true,",
            "    uncertainty-mode = compact,",
            "}",
        ]
    )

    # ``digit-group-size`` sets the WIDTH of each group (not just the threshold). It is a
    # siunitx-v3 key that some v3 builds (Tectonic-bundled 3.0.49) still REJECT at runtime
    # with ``LaTeX3 Error: The key 'siunitx/digit-group-size' is unknown`` while newer builds
    # (TeX Live 3.4.14) honour it. Whether to emit it:
    #   emit_digit_group_size is True  -> the app PROBED the engine and knows it is honoured;
    #                                     emit UNGUARDED (probe is authoritative).
    #   emit_digit_group_size is False -> probed as NOT honoured; never emit (doc must still
    #                                     compile; app-side text grouping handles width).
    #   emit_digit_group_size is None  -> no probe result; fall back to the legacy
    #                                     \@ifpackagelater date heuristic (backward compatible
    #                                     for callers not yet probe-aware). Skipped when the
    #                                     requested size is 3 (both v2/v3 default to 3 anyway).
    if emit_digit_group_size is True:
        lines.append(f"\\sisetup{{digit-group-size = {group_size}}}")
    elif emit_digit_group_size is None and group_size != 3:
        # ``\@ifpackagelater`` is an internal LaTeX2e command, so it has to live inside
        # ``\makeatletter ... \makeatother``. NOT wrapped in ``\begingroup ... \endgroup``:
        # TeX groups scope ``\sisetup``'s package-state assignments and would silently
        # revert the override at ``\endgroup`` time. 2024/01/01 is the empirical cutoff:
        # Tectonic-bundled v3.0.49 evaluates as earlier (skipped → default size 3, still
        # compiles), TeX Live v3.4.14 as later (fires → requested size honoured).
        lines.append(r"\makeatletter")
        lines.append(
            r"\@ifpackagelater{siunitx}{2024/01/01}{"
            f"\\sisetup{{digit-group-size = {group_size}}}"
            "}{}"
        )
        lines.append(r"\makeatother")

    lines.append("")
    return "\n".join(lines) + "\n"
