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

import os
import platform
import shutil
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
        raise RuntimeError(
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
    flag between chunks so a Stop click aborts within milliseconds.

    Avoids buffering the full ~30 MB archive in RAM (a real concern on
    a desktop GUI process that already hosts matplotlib + PySide6).
    """
    chunk = 8192
    with _open_url(url) as response, dest.open("wb") as out:
        while True:
            if cancel_check is not None and cancel_check():
                raise TectonicInstallCancelled("install cancelled by caller")
            buf = response.read(chunk)
            if not buf:
                break
            out.write(buf)


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
    - We do NOT pass ``--print``; Tectonic prints to stderr by default
      and the desktop mixin captures both streams already.
    """
    return [
        binary,
        "--keep-logs",
        "--outfmt",
        "pdf",
        str(tex_path),
    ]
