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
        # ``digit-group-size`` is a siunitx-v3 key, introduced in
        # siunitx 3.0.0 (released **2020-02-08**). The first attempt
        # at this guard used ``\@ifpackagelater{siunitx}{2020/01/01}``
        # — a date some siunitx v2 patch releases also carry, so the
        # branch fired on v2 and produced ``LaTeX3 Error: The key
        # 'siunitx/digit-group-size' is unknown``. Pinning the cutoff
        # to siunitx 3.0's actual release date instead means:
        #
        #   * any siunitx v2 patch (date ≤ 2020/02/07): branch skipped,
        #     siunitx falls back to its built-in default of 3 (still
        #     a working compile).
        #   * any siunitx v3 (date ≥ 2020/02/08): branch fires and
        #     ``digit-group-size = N`` is honoured.
        #
        # ``\@ifpackagelater`` is an internal LaTeX2e command, so it
        # has to live inside ``\makeatletter ... \makeatother``.
        #
        # An earlier revision of this PR additionally wrapped the body
        # in ``\begingroup ... \endgroup`` to make the ``\makeatletter``
        # catcode flip locally scoped. That was a regression: ``\sisetup``
        # uses option-setting macros that take effect via package-state
        # variables, and TeX groups SCOPE those variable assignments —
        # so ``\endgroup`` reverted the override and the rendered PDF
        # silently fell back to size 3. Codex's adversarial-review probe
        # caught this. We accept the (theoretical) risk that some weird
        # surrounding preamble might already have ``\makeatletter`` open
        # — in practice no DataLab template does, and ``\makeatother``
        # at the package-loading level is the standard contract.
        lines.append(r"\makeatletter")
        lines.append(
            r"\@ifpackagelater{siunitx}{2020/02/08}{"
            f"\\sisetup{{digit-group-size = {group_size}}}"
            "}{}"
        )
        lines.append(r"\makeatother")

    lines.append("")
    return "\n".join(lines) + "\n"
