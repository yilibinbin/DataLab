"""LaTeX engine discovery + auto-install for the desktop GUI.

DataLab compiles LaTeX out-of-process via ``pdflatex`` / ``xelatex`` /
``lualatex`` / ``tectonic``. Historically that meant the user had to
install a multi-gigabyte TeX Live distribution before "Export LaTeX →
Compile" worked. This module replaces the bare ``shutil.which`` path
with a tiered discovery + auto-install strategy:

1. **System** — ``shutil.which(engine)``. Fastest, no extra disk; works
   when the user already has TeX Live / MiKTeX installed. The rest of
   this module exists exactly so we don't *require* it.

2. **Bundled TinyTeX** — under
   ``<bundle_root>/resources/tinytex/bin/<arch>/<engine>``. Populated
   by an opt-in step in the build script (~200 MB, see
   ``tools/install_tinytex.sh``). Zero network at runtime.

3. **Auto-Tectonic** — single 30 MB binary downloaded on first use to
   ``~/.datalab/bin/tectonic``. Tectonic resolves missing LaTeX
   packages over the net per-document and caches them in the OS-level
   cache directory.

The desktop mixin's ``_ensure_latex_engine`` calls ``resolve_engine``
to find a working binary across all three tiers; if none exists and
the engine choice is ``tectonic``, ``ensure_tectonic_installed`` will
download it. The download path is deliberately a separate function
from discovery so callers can show a progress dialog around it.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal


__all__ = [
    "EngineChoice",
    "MissingHomeDirectoryError",
    "TectonicChecksumError",
    "TectonicInstallCancelled",
    "UnsupportedPlatformError",
    "discover_bundled_engine",
    "discover_system_engine",
    "ensure_tectonic_installed",
    "find_app_root",
    "resolve_engine",
    "tectonic_compile_argv",
    "tectonic_download_url",
    "tectonic_executable_name",
    "tectonic_install_dir",
]


class UnsupportedPlatformError(RuntimeError):
    """Raised when no Tectonic binary release matches the current
    (platform.system(), platform.machine()) tuple."""


class MissingHomeDirectoryError(RuntimeError):
    """Raised when neither ``HOME`` nor ``USERPROFILE`` is set so the
    auto-Tectonic installer cannot pick a stable install location.
    Lets the GUI dispatch a localized error message via ``isinstance``
    instead of stringly-matching the message text."""


EngineSource = Literal["system", "bundled", "auto-tectonic"]


@dataclass(frozen=True)
class EngineChoice:
    """A resolved LaTeX engine: where it came from + the absolute path."""
    path: str
    source: EngineSource


# ---------------------------------------------------------------------------
# Tier 1: system PATH lookup
# ---------------------------------------------------------------------------


def discover_system_engine(engine: str) -> str | None:
    """Return the absolute path of ``engine`` on PATH, or ``None``.

    Thin wrapper over ``shutil.which`` — exists so the desktop mixin
    can iterate the three tiers via one consistent API.
    """
    return shutil.which(engine)


# ---------------------------------------------------------------------------
# Tier 2: bundled TinyTeX inside the .app / installer
# ---------------------------------------------------------------------------


def discover_bundled_engine(bundle_root: Path | str, engine: str) -> str | None:
    """Look under ``<bundle_root>/resources/tinytex/bin/<arch>/<engine>``.

    The ``<arch>`` directory is whatever TinyTeX's
    ``install-tl-unx.tar.gz`` / ``tlmgr`` produces for the host
    platform — historically it's been ``x86_64-darwin``, ``aarch64-darwin``,
    ``win32``, ``x86_64-linux``, etc. We don't try to predict the name
    here; instead we accept any subdirectory with a binary of the
    requested name. That keeps this discovery resilient when the
    upstream naming changes.
    """
    bin_root = Path(bundle_root) / "resources" / "tinytex" / "bin"
    if not bin_root.is_dir():
        return None
    # iterate arch dirs in stable lexicographic order so the tests are
    # deterministic and so a user inspecting the bundle finds the same
    # binary the runtime found
    for arch_dir in sorted(bin_root.iterdir()):
        if not arch_dir.is_dir():
            continue
        candidate = arch_dir / engine
        # Windows TinyTeX uses .exe; the bundled tree may carry either
        # form depending on the install script.
        if candidate.is_file() or candidate.with_suffix(".exe").is_file():
            return str(candidate if candidate.is_file() else candidate.with_suffix(".exe"))
    return None


def find_app_root() -> Path:
    """Return the bundle root for ``discover_bundled_engine``.

    PyInstaller sets ``sys._MEIPASS`` to the unpacked-resources dir at
    runtime; outside a frozen build the project root is the right
    answer. Falling back to the project root keeps dev-mode and frozen
    behaviour symmetric.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Tier 3: auto-installed Tectonic (single binary, runtime-downloaded)
# ---------------------------------------------------------------------------


def tectonic_executable_name() -> str:
    return "tectonic.exe" if platform.system() == "Windows" else "tectonic"


def tectonic_install_dir() -> Path:
    """``~/.datalab/bin`` (cross-platform, respects ``$HOME`` /
    ``$USERPROFILE``).

    Raises ``RuntimeError`` if neither environment variable is set —
    falling back to ``cwd`` would silently install the binary into
    whatever directory the user happened to launch from, which is
    surprising and makes the binary impossible for ``resolve_engine``
    to locate on subsequent runs.
    """
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        raise MissingHomeDirectoryError(
            "Cannot determine the user's home directory: neither HOME "
            "nor USERPROFILE is set. Tectonic auto-install requires a "
            "stable home path so subsequent runs can locate the binary."
        )
    return Path(home) / ".datalab" / "bin"


# Tectonic GitHub release URLs, pinned to a known-good version. Bumping
# this version is a routine maintenance task; the regression test
# only checks the URL **shape** so version churn doesn't break CI.
_TECTONIC_VERSION = "0.15.0"
_TECTONIC_RELEASE_BASE = (
    f"https://github.com/tectonic-typesetting/tectonic/releases/download/"
    f"tectonic%40{_TECTONIC_VERSION}"
)

# SHA-256 of every Tectonic release archive this module can download, keyed by
# asset filename. GitHub release assets are immutable once published, so these
# digests — computed from the canonical HTTPS release for tectonic@0.15.0 — pin
# the exact bytes we execute and block a tampered mirror or MITM from delivering
# a swapped binary. When bumping _TECTONIC_VERSION, recompute every entry (this
# release does not ship an upstream SHA256SUMS file to fetch at runtime).
_TECTONIC_SHA256: dict[str, str] = {
    "tectonic-0.15.0-aarch64-apple-darwin.tar.gz": (
        "24bd46566fa30d41101848405e9cbc4645edb92d8f857c9d21262174fb70cd33"
    ),
    "tectonic-0.15.0-x86_64-apple-darwin.tar.gz": (
        "dd42576eaa4c0df58c243dd78b7b864d9deb405ffdfcdadd1b79a31faceab747"
    ),
    "tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz": (
        "dfb82876f2986862996e564fa507a9e576e0c1e3bee63c2c1bd677c2543e6407"
    ),
    "tectonic-0.15.0-aarch64-unknown-linux-musl.tar.gz": (
        "1f59f9fb8eb65e8ba18658fc9016767e7d3e12488ded8b8fffa34254e51ce42c"
    ),
    "tectonic-0.15.0-x86_64-pc-windows-msvc.zip": (
        "1d6bb76f049c8a3774f6e9d66e4b04e1a8c3dcb37527b6b41b7e894328e7bf29"
    ),
}


def tectonic_download_url() -> str:
    """Pick the right Tectonic asset URL for the current platform.

    Tectonic ships pre-built binaries for the common targets; mapping
    Python's ``platform.system()`` / ``platform.machine()`` to those
    target triples is straightforward but tedious — keep it in one
    place so we can bump the version without hunting through
    callers.
    """
    sysname = platform.system()
    machine = platform.machine()

    if sysname == "Darwin":
        if machine in ("arm64", "aarch64"):
            triple = "aarch64-apple-darwin"
        elif machine in ("x86_64", "amd64", "AMD64"):
            triple = "x86_64-apple-darwin"
        else:
            raise UnsupportedPlatformError(
                f"No Tectonic binary release for Darwin/{machine}"
            )
        return f"{_TECTONIC_RELEASE_BASE}/tectonic-{_TECTONIC_VERSION}-{triple}.tar.gz"

    if sysname == "Linux":
        if machine in ("x86_64", "amd64", "AMD64"):
            triple = "x86_64-unknown-linux-musl"
        elif machine in ("aarch64", "arm64"):
            triple = "aarch64-unknown-linux-musl"
        else:
            raise UnsupportedPlatformError(
                f"No Tectonic binary release for Linux/{machine}"
            )
        return f"{_TECTONIC_RELEASE_BASE}/tectonic-{_TECTONIC_VERSION}-{triple}.tar.gz"

    if sysname == "Windows":
        if machine in ("AMD64", "x86_64", "amd64"):
            triple = "x86_64-pc-windows-msvc"
        else:
            raise UnsupportedPlatformError(
                f"No Tectonic binary release for Windows/{machine}"
            )
        return f"{_TECTONIC_RELEASE_BASE}/tectonic-{_TECTONIC_VERSION}-{triple}.zip"

    raise UnsupportedPlatformError(
        f"No Tectonic binary release for {sysname}/{machine}"
    )


# ---------------------------------------------------------------------------
# Combined resolver — what the desktop mixin actually calls
# ---------------------------------------------------------------------------


def resolve_engine(
    engine: str,
    *,
    bundle_root: Path | str | None = None,
) -> EngineChoice | None:
    """Look up ``engine`` across the three tiers and return the first hit.

    Order: system → bundled → (caller-driven) auto-tectonic.
    The auto-Tectonic tier requires a network round-trip the first
    time, so this resolver only *returns* the path if the binary is
    already installed; the desktop mixin's "Install Tectonic" button
    runs ``ensure_tectonic_installed`` itself with progress feedback.
    """
    if not engine:
        return None

    sys_path = discover_system_engine(engine)
    if sys_path:
        return EngineChoice(path=sys_path, source="system")

    if bundle_root is None:
        bundle_root = find_app_root()
    bun_path = discover_bundled_engine(bundle_root, engine)
    if bun_path:
        return EngineChoice(path=bun_path, source="bundled")

    # Auto-installed Tectonic — only count it as resolved if the binary
    # is already on disk. Asking for a download here would block the
    # caller without UI feedback.
    if engine == "tectonic":
        candidate = tectonic_install_dir() / tectonic_executable_name()
        if candidate.is_file():
            return EngineChoice(path=str(candidate), source="auto-tectonic")

    return None


# ---------------------------------------------------------------------------
# Tectonic auto-installer (downloads ~30 MB on first use)
# ---------------------------------------------------------------------------


ProgressCallback = Callable[[str], None]


def _open_url(url: str) -> Any:
    """Indirection so tests can patch network access.

    Returns the ``urllib.request.urlopen`` HTTP response object — typed
    ``Any`` because both the real return type and the ``MagicMock`` the
    install tests use have to satisfy the same call sites.
    """
    return urllib.request.urlopen(url, timeout=60)  # noqa: S310 — pinned URL


class TectonicInstallCancelled(RuntimeError):
    """Raised when ``cancel_check`` returns True during install."""


class TectonicChecksumError(RuntimeError):
    """Raised when a downloaded Tectonic archive fails SHA-256 verification.

    A mismatch means the bytes on disk are not the pinned release — a
    tampered mirror, a corrupted transfer, or an unrecognized asset — so
    the archive must never be extracted or executed.
    """


def ensure_tectonic_installed(
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> EngineChoice:
    """Download + extract Tectonic to ``~/.datalab/bin``.

    Idempotent: if the binary is already present, returns the existing
    path without hitting the network. Raises ``UnsupportedPlatformError``
    when no release matches the current platform, or
    ``TectonicInstallCancelled`` when ``cancel_check`` reports True
    during the download/extract — the half-installed staging tree is
    cleaned up before the exception propagates.

    Streams the archive to disk via ``shutil.copyfileobj`` (chunked,
    8 KiB per loop) so the full ~30 MB never lands in RAM and the
    cancel check fires within ~10 ms of the user clicking Stop.

    Atomicity: the binary lands in a sibling staging dir on the same
    filesystem and is published with ``os.replace``. A killed process
    can leave the staging dir behind but never a truncated
    ``tectonic`` binary that the next ``resolve_engine`` call would
    mistakenly treat as installed.
    """
    install_dir = tectonic_install_dir()
    binary = install_dir / tectonic_executable_name()
    if binary.is_file():
        if progress_callback:
            progress_callback("already-installed")
        return EngineChoice(path=str(binary), source="auto-tectonic")

    url = tectonic_download_url()  # raises UnsupportedPlatformError if needed
    install_dir.mkdir(parents=True, exist_ok=True)

    stage_dir = Path(tempfile.mkdtemp(prefix=".tectonic-install-", dir=install_dir))
    try:
        if progress_callback:
            progress_callback("downloading")
        archive_path = stage_dir / ("archive.zip" if url.endswith(".zip") else "archive.tar.gz")
        _stream_url_to_file(url, archive_path, cancel_check)

        # Verify the downloaded bytes against the pinned SHA-256 before we
        # extract or execute anything — a swapped mirror or MITM must not be
        # able to hand us a different binary. Any mismatch aborts here, and the
        # finally block wipes the staging tree so nothing tampered survives.
        _verify_archive_sha256(url, archive_path)

        if progress_callback:
            progress_callback("extracting")
        if url.endswith(".zip"):
            _extract_tectonic_from_zip(archive_path, stage_dir)
        else:
            _extract_tectonic_from_tar(archive_path, stage_dir)

        staged_binary = stage_dir / tectonic_executable_name()
        if not staged_binary.is_file():
            raise RuntimeError(
                f"Tectonic archive at {url} did not contain a "
                f"{tectonic_executable_name()} binary at the expected path"
            )
        if platform.system() != "Windows":
            staged_binary.chmod(staged_binary.stat().st_mode | 0o755)

        # Atomic publish — concurrent installers race here, but
        # whichever ``replace`` runs last wins and leaves a complete
        # binary either way. No truncated half-write is observable
        # to a subsequent ``resolve_engine`` call.
        os.replace(staged_binary, binary)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    if progress_callback:
        progress_callback("installed")
    return EngineChoice(path=str(binary), source="auto-tectonic")


def _stream_url_to_file(
    url: str,
    dest: Path,
    cancel_check: Callable[[], bool] | None,
) -> None:
    """Stream ``url`` into ``dest`` 8 KiB at a time, polling the cancel
    flag after each chunk so a Stop click aborts within one chunk's
    worth of network read.

    The poll fires AFTER ``response.read`` returns, not before, because
    the read itself can block for the urlopen timeout (60 s) on a
    stalled connection — checking pre-read alone leaves the abort
    latency dominated by that timeout. Worst-case cancellation latency
    is therefore one stalled-chunk window; typical-case is well under
    100 ms because chunk reads on a healthy connection complete in
    microseconds.

    Avoids buffering the full ~30 MB archive in RAM (a real concern on
    a desktop GUI process that already hosts matplotlib + PySide6).
    """
    chunk = 8192
    with _open_url(url) as response, dest.open("wb") as out:
        while True:
            buf = response.read(chunk)
            if not buf:
                break
            out.write(buf)
            # Poll AFTER write: the just-finished ``read()`` may have
            # blocked up to the urlopen timeout (60 s) — pre-read
            # polling cannot shorten that window. Post-write polling
            # caps cancel latency at one chunk's worth of network
            # read (typically <100 ms on a healthy connection).
            if cancel_check is not None and cancel_check():
                raise TectonicInstallCancelled("install cancelled by caller")


def _verify_archive_sha256(url: str, archive_path: Path) -> None:
    """Verify ``archive_path`` matches the SHA-256 pinned for ``url``'s asset.

    The asset filename is the last path segment of the download URL; it keys
    into ``_TECTONIC_SHA256``. An unknown asset (URL we never intended to
    download) or a digest mismatch both raise ``TectonicChecksumError`` so the
    caller never extracts unverified bytes.
    """
    asset_name = url.rsplit("/", 1)[-1]
    expected = _TECTONIC_SHA256.get(asset_name)
    if expected is None:
        raise TectonicChecksumError(
            f"No pinned SHA-256 for Tectonic asset {asset_name!r}; refusing to "
            f"install an unverified download from {url}"
        )
    digest = hashlib.sha256()
    with archive_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise TectonicChecksumError(
            f"Tectonic archive {asset_name} failed SHA-256 verification: "
            f"expected {expected}, got {actual}. The download may be corrupted "
            f"or tampered with; not installing."
        )


def _extract_tectonic_from_tar(archive_path: Path, dest_dir: Path) -> None:
    """Pull the ``tectonic`` binary out of a .tar.gz release archive.

    Tectonic's tarballs vary across versions: some are flat (the
    binary at the root) and some have an inner directory. Search the
    whole archive for any member whose basename is ``tectonic`` and
    write it to ``dest_dir/tectonic``.
    """
    with tarfile.open(archive_path, mode="r:*") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if Path(member.name).name == "tectonic":
                fobj = tar.extractfile(member)
                if fobj is None:
                    continue
                target = dest_dir / "tectonic"
                with target.open("wb") as out:
                    shutil.copyfileobj(fobj, out)
                return
    raise RuntimeError("tectonic binary not found in tar archive")


def _extract_tectonic_from_zip(archive_path: Path, dest_dir: Path) -> None:
    """Pull ``tectonic.exe`` out of a Windows zip release."""
    with zipfile.ZipFile(archive_path) as zf:
        for name in zf.namelist():
            if Path(name).name.lower() == "tectonic.exe":
                with zf.open(name) as src:
                    target = dest_dir / "tectonic.exe"
                    with target.open("wb") as out:
                        shutil.copyfileobj(src, out)
                return
    raise RuntimeError("tectonic.exe not found in zip archive")


# ---------------------------------------------------------------------------
# Tectonic compile invocation
# ---------------------------------------------------------------------------


def tectonic_compile_argv(binary: str, tex_path: Path | str) -> list[str]:
    """Build the argv list for compiling ``tex_path`` with Tectonic.

    Tectonic's compile flags differ from pdflatex/xelatex enough that
    we want a single helper rather than open-coding the call site:

    - ``--keep-logs``: drop the ``.log`` next to the .tex so the GUI's
      existing log-tail viewer keeps working.
    - ``--outfmt pdf``: explicit format, never assume default.
    - ``--`` separator before the input path: defense-in-depth so a
      relative input like ``-V.tex`` cannot be parsed as an option.
      In practice the desktop mixin always passes an absolute path,
      but the helper is reachable from CLI / batch callers too.
    - We do NOT pass ``--print``; Tectonic prints to stderr by default
      and the desktop mixin captures both streams already.
    """
    return [
        binary,
        "--keep-logs",
        "--outfmt",
        "pdf",
        "--",
        str(tex_path),
    ]


# ---------------------------------------------------------------------------
# siunitx capability probe (does the engine's siunitx honour digit-group-size?)
# ---------------------------------------------------------------------------

# A minimal document that FAILS to compile iff siunitx rejects ``digit-group-size``
# (LaTeX3 key-unknown). Newer siunitx (>= ~3.1, local TeX Live) compiles it; the
# Tectonic-bundled 3.0.49 errors out. Kept tiny so the probe is fast.
_DIGIT_GROUP_SIZE_PROBE_TEX = (
    "\\documentclass{article}\n"
    "\\usepackage{siunitx}\n"
    "\\sisetup{group-digits = all, digit-group-size = 4}\n"
    "\\begin{document}\\num{12345678}\\end{document}\n"
)

# Cache: engine binary path -> supports digit-group-size (bool). Populated on first probe.
_capability_cache: dict[str, bool] = {}


def _reset_capability_cache() -> None:
    """Clear the probe cache (tests + when the engine selection changes)."""
    _capability_cache.clear()


def engine_probe_argv(binary: str, tex_path: Path | str) -> list[str]:
    """Argv to compile ``tex_path`` with ``binary`` for a NON-interactive one-shot probe.

    Tectonic and the LaTeX engines take different flags; the stem decides which (matching
    the compile worker's own dispatch)."""
    if Path(binary).stem.lower().endswith("tectonic"):
        return tectonic_compile_argv(binary, tex_path)
    return [
        binary,
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        str(tex_path),
    ]


def siunitx_supports_digit_group_size(engine_path: str) -> bool:
    """Return True iff ``engine_path``'s siunitx honours ``digit-group-size``.

    Compiles a tiny probe doc once per engine path (cached). Any launch failure, timeout,
    or non-zero exit → False (treated as "not supported"), so a broken/missing engine never
    crashes the caller — the app falls back to app-side text grouping.
    """
    if not engine_path:
        return False
    if engine_path in _capability_cache:
        return _capability_cache[engine_path]

    supported = False
    try:
        with tempfile.TemporaryDirectory(prefix="datalab_siprobe_") as tmp:
            tex = Path(tmp) / "siprobe.tex"
            tex.write_text(_DIGIT_GROUP_SIZE_PROBE_TEX, encoding="utf-8")
            argv = engine_probe_argv(engine_path, tex)
            proc = subprocess.run(
                argv,
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=120,
            )
            supported = proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        supported = False

    _capability_cache[engine_path] = supported
    return supported


# Ordered preference of PATH LaTeX engines to try in local/auto modes.
_LOCAL_ENGINE_PREFERENCE = ("xelatex", "pdflatex", "lualatex")


def resolve_engine_for_mode(
    mode: str, *, bundle_root: Path | str | None = None
) -> EngineChoice | None:
    """Resolve a compile engine per the user's engine MODE.

    - ``"bundled"`` → the internal Tectonic only (guaranteed, network-installable). Group
      WIDTH is fixed at 3 (its siunitx lacks digit-group-size); the writers fall back to
      app-side text grouping.
    - ``"local"`` → a PATH LaTeX engine (xelatex/pdflatex/lualatex) only; no Tectonic
      fallback. Returns None if the user has no local TeX.
    - ``"auto"`` (default) → prefer a PATH engine whose siunitx honours digit-group-size
      (so S-column native variable-width grouping works); otherwise fall back to Tectonic.

    Returns an :class:`EngineChoice` (with a resolved ``path``) or None when nothing usable
    is found for the mode.
    """
    if mode == "bundled":
        return resolve_engine("tectonic", bundle_root=bundle_root)

    def _first_local() -> EngineChoice | None:
        for name in _LOCAL_ENGINE_PREFERENCE:
            choice = resolve_engine(name, bundle_root=bundle_root)
            if choice is not None:
                return choice
        return None

    if mode == "local":
        return _first_local()

    # auto: a capable local engine wins; else fall back to Tectonic (always available once
    # installed). An incapable local engine is not preferred over Tectonic because the whole
    # point of auto is to get the best grouping — but both produce correct PDFs, so if
    # Tectonic is missing we still return the local engine rather than nothing.
    tectonic = resolve_engine("tectonic", bundle_root=bundle_root)
    for name in _LOCAL_ENGINE_PREFERENCE:
        choice = resolve_engine(name, bundle_root=bundle_root)
        if choice is None:
            continue
        if siunitx_supports_digit_group_size(choice.path):
            return choice
        # Remember the first usable-but-incapable local engine as a last resort.
        if tectonic is None:
            return choice
    return tectonic or _first_local()
