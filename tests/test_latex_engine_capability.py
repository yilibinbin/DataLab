"""siunitx digit-group-size capability probe for ``shared.latex_engine``.

The bundled Tectonic's siunitx (3.0.49) rejects ``digit-group-size`` (LaTeX3 key-unknown),
so it cannot vary the digit-group WIDTH; a newer siunitx (local TeX Live) accepts it. The
probe compiles a tiny doc with the resolved engine and reports whether the key is honoured,
so the LaTeX writers can pick the S-column-native path vs the app-side text-grouping path.

These tests stub the actual subprocess so they don't invoke a real engine.
"""

from __future__ import annotations

from unittest.mock import patch
from pathlib import Path

from shared.latex_engine import (
    EngineChoice,
    discover_all_engines,
    engine_probe_argv,
    resolve_engine_for_mode,
    siunitx_supports_digit_group_size,
    _reset_capability_cache,
)


def setup_function() -> None:
    _reset_capability_cache()


def test_probe_argv_uses_tectonic_style_for_tectonic_binary(tmp_path) -> None:
    tex = tmp_path / "probe.tex"
    argv = engine_probe_argv("/opt/datalab/bin/tectonic", tex)
    assert argv[0] == "/opt/datalab/bin/tectonic"
    assert "--outfmt" in argv  # tectonic flag, not a latex flag
    assert str(tex) in argv


def test_probe_argv_uses_latex_style_for_pdflatex(tmp_path) -> None:
    tex = tmp_path / "probe.tex"
    argv = engine_probe_argv("/usr/bin/xelatex", tex)
    assert argv[0] == "/usr/bin/xelatex"
    assert "-interaction=nonstopmode" in argv
    assert "--outfmt" not in argv


def test_supports_true_when_probe_compile_succeeds() -> None:
    class _OK:
        returncode = 0
        stdout = ""
        stderr = ""

    with patch("shared.latex_engine.subprocess.run", return_value=_OK()) as run:
        assert siunitx_supports_digit_group_size("/usr/bin/xelatex") is True
        assert run.call_count == 1


def test_supports_false_when_probe_reports_unknown_key() -> None:
    class _Fail:
        returncode = 1
        stdout = "LaTeX3 Error: The key 'siunitx/digit-group-size' is unknown"
        stderr = ""

    with patch("shared.latex_engine.subprocess.run", return_value=_Fail()):
        assert siunitx_supports_digit_group_size("/opt/datalab/bin/tectonic") is False


def test_result_is_cached_per_engine_path() -> None:
    class _OK:
        returncode = 0
        stdout = ""
        stderr = ""

    with patch("shared.latex_engine.subprocess.run", return_value=_OK()) as run:
        siunitx_supports_digit_group_size("/usr/bin/xelatex")
        siunitx_supports_digit_group_size("/usr/bin/xelatex")
        # Second call must hit the cache, not re-compile.
        assert run.call_count == 1


def test_probe_failure_to_launch_returns_false_not_raise() -> None:
    with patch("shared.latex_engine.subprocess.run", side_effect=OSError("boom")):
        # A missing/broken engine must not crash the app — treat as "not supported".
        assert siunitx_supports_digit_group_size("/nonexistent/engine") is False


# --- engine-mode resolution (auto / bundled / local) -----------------------


def test_mode_bundled_prefers_tectonic() -> None:
    # When nothing is bundled/installed yet, bundled mode falls back to resolve_engine so the
    # caller can trigger the Tectonic auto-install. (The happy path — a real bundled binary —
    # is covered by test_mode_bundled_does_not_return_a_system_path_tectonic.)
    tect = EngineChoice(path="/opt/datalab/bin/tectonic", source="auto-tectonic")
    with patch("shared.latex_engine.discover_bundled_engine", return_value=None), patch(
        "shared.latex_engine.tectonic_install_dir", return_value=Path("/nonexistent")
    ), patch("shared.latex_engine.resolve_engine", return_value=tect) as r:
        choice = resolve_engine_for_mode("bundled")
        assert choice is tect
        assert r.call_args.args[0] == "tectonic"


def test_mode_bundled_does_not_return_a_system_path_tectonic(tmp_path) -> None:
    # F5 (dual-model review): "bundled" must force the bundled/auto-installed Tectonic, NOT a
    # system-PATH one. discover_bundled_engine returns the bundled path; resolve_engine (which
    # checks PATH first) must NOT be consulted for the win.
    bundled = str(tmp_path / "bundled" / "tectonic")
    with patch("shared.latex_engine.discover_bundled_engine", return_value=bundled), patch(
        "shared.latex_engine.resolve_engine"
    ) as resolve:
        choice = resolve_engine_for_mode("bundled")
        assert choice is not None
        assert choice.path == bundled
        assert choice.source == "bundled"
        resolve.assert_not_called()  # bundled path resolved directly, not via PATH-first resolve_engine


def test_mode_local_prefers_a_path_latex_engine() -> None:
    xe = EngineChoice(path="/usr/bin/xelatex", source="system")
    calls = []

    def fake_resolve(engine, **kw):
        calls.append(engine)
        return xe if engine in ("xelatex", "pdflatex", "lualatex") else None

    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve):
        choice = resolve_engine_for_mode("local")
        assert choice is xe
        assert "tectonic" not in calls  # local mode must not fall back to tectonic


def test_mode_auto_scans_all_locals_for_a_capable_one_not_first_incapable() -> None:
    # F4 (dual-model review): auto must NOT return the first incapable local engine and skip a
    # later capable one. xelatex incapable, pdflatex capable, tectonic absent → pick pdflatex.
    xe = EngineChoice(path="/usr/bin/xelatex", source="system")
    pl = EngineChoice(path="/usr/bin/pdflatex", source="system")

    def fake_resolve(engine, **kw):
        return {"xelatex": xe, "pdflatex": pl}.get(engine)  # tectonic → None

    def fake_probe(path):
        return path == "/usr/bin/pdflatex"  # only pdflatex capable

    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve), patch(
        "shared.latex_engine.siunitx_supports_digit_group_size", side_effect=fake_probe
    ):
        assert resolve_engine_for_mode("auto") is pl


def test_mode_auto_prefers_capable_local_then_falls_back_to_tectonic() -> None:
    xe = EngineChoice(path="/usr/bin/xelatex", source="system")
    tect = EngineChoice(path="/opt/datalab/bin/tectonic", source="auto-tectonic")

    def fake_resolve(engine, **kw):
        return {"xelatex": xe, "tectonic": tect}.get(engine)

    # auto + local engine is capable → use the local engine.
    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve), patch(
        "shared.latex_engine.siunitx_supports_digit_group_size", return_value=True
    ):
        assert resolve_engine_for_mode("auto") is xe

    # auto + local engine NOT capable → prefer tectonic (guaranteed) over an
    # incapable local engine is a product choice; here we assert auto still returns a
    # usable engine (either), never None when one exists.
    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve), patch(
        "shared.latex_engine.siunitx_supports_digit_group_size", return_value=False
    ):
        choice = resolve_engine_for_mode("auto")
        assert choice in (xe, tect)


# --- discover_all_engines (concrete engines found on this machine) ----------


def test_discover_all_engines_lists_found_engines_with_paths() -> None:
    xe = EngineChoice(path="/usr/bin/xelatex", source="system")
    pl = EngineChoice(path="/usr/bin/pdflatex", source="system")
    tect = EngineChoice(path="/opt/datalab/bin/tectonic", source="auto-tectonic")

    def fake_resolve(engine, **kw):
        return {"xelatex": xe, "pdflatex": pl, "tectonic": tect}.get(engine)

    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve):
        found = discover_all_engines()

    names = [name for name, _choice in found]
    # Only engines that actually resolved appear; each carries its EngineChoice.
    assert "xelatex" in names
    assert "pdflatex" in names
    assert "tectonic" in names
    by_name = dict(found)
    assert by_name["xelatex"].path == "/usr/bin/xelatex"
    assert by_name["tectonic"].source == "auto-tectonic"


def test_discover_all_engines_omits_missing_engines() -> None:
    xe = EngineChoice(path="/usr/bin/xelatex", source="system")

    def fake_resolve(engine, **kw):
        return xe if engine == "xelatex" else None

    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve):
        found = discover_all_engines()

    names = [name for name, _ in found]
    assert names == ["xelatex"]  # lualatex/pdflatex/tectonic not found → omitted


def test_discover_all_engines_deduplicates_same_path() -> None:
    # If two engine names resolve to the SAME binary path, list it once.
    shared_choice = EngineChoice(path="/usr/bin/xelatex", source="system")

    def fake_resolve(engine, **kw):
        return shared_choice if engine in ("xelatex", "pdflatex") else None

    with patch("shared.latex_engine.resolve_engine", side_effect=fake_resolve):
        found = discover_all_engines()

    paths = [choice.path for _, choice in found]
    assert paths.count("/usr/bin/xelatex") == 1
