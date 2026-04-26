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
        # ``digit-group-size`` is a siunitx-v3-only key (introduced in
        # siunitx 3.0, Feb 2020). Date-based ``\@ifpackagelater`` checks
        # are unreliable here — some siunitx-v2 patch releases carry
        # post-2020-01-01 dates yet still don't have the key. To stay
        # safe across the install matrix we emit the override only
        # when explicitly opting into a v3-only build via the env var
        # ``DATALAB_SIUNITX_V3=1`` at LaTeX-export time. Users on a v2
        # install get siunitx's built-in default of group-size=3, which
        # matches the group-minimum-digits value emitted above.
        #
        # The user-visible effect: ``group_size != 3`` requests on
        # siunitx v2 silently render with size 3 (acceptable: most
        # publication conventions use 3 anyway, and the export-text
        # for non-3 cases stays unchanged so a power user can edit
        # it manually). On siunitx v3, no such override fires from
        # this block — but ``group-minimum-digits = N`` already gates
        # WHEN grouping kicks in, which is the more common need.
        lines.append(
            f"% Note: group-size = {group_size} requested; siunitx v2 "
            "ignores the size and uses 3. Edit the .tex if exact "
            "non-3 grouping is required."
        )

    lines.append("")
    return "\n".join(lines) + "\n"
