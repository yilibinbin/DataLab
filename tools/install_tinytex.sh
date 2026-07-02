#!/usr/bin/env bash
# Install TinyTeX into <repo>/resources/tinytex for opt-in PyInstaller bundling.
#
# Used by build_mac_data_gui.sh and build_windows_data_gui.ps1 when the user
# sets DATALAB_BUNDLE_TINYTEX=1 / passes -BundleTinyTeX. The runtime discovery
# layer (shared.latex_engine.discover_bundled_engine) looks for binaries under
# resources/tinytex/bin/<arch>/<engine>, so do not change the install root
# without updating that lookup too.
#
# TinyTeX is the R community's "minimal but expandable" TeX Live subset (~150
# MB after install, expands as documents reference more packages). It uses the
# canonical TeX Live binaries, so pdflatex / xelatex / lualatex all work the
# same as a full TeX Live install once it's bundled. Re-running this script is
# idempotent: it skips the bootstrap when the binaries already exist.
#
# Layout note: TinyTeX's upstream installer always nests the install under a
# ``TinyTeX``-named subdirectory (``$TINYTEX_DIR/TinyTeX`` on macOS,
# ``$TINYTEX_DIR/.TinyTeX`` on Linux). The runtime discovery contract puts
# binaries one level up from that, so this script flattens the inner
# directory after the installer finishes. Don't try to "simplify" by passing
# our final target as ``TINYTEX_DIR`` directly — the upstream layout convention
# makes that strictly worse than the explicit move below.

set -e
set -o pipefail  # `curl | sh` would otherwise hide curl failures

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="$PROJECT_ROOT/resources/tinytex"

# Pin the TinyTeX bootstrap installer URL. TinyTeX's "self-installing" mode
# fetches the right TeX Live binary set for the host platform automatically.
# Bumping this URL is a routine maintenance task; the test suite only checks
# the install location, not the download endpoint.
TINYTEX_INSTALLER_URL="${TINYTEX_INSTALLER_URL:-https://yihui.org/tinytex/install-bin-unix.sh}"

# Refuse to download+execute over a plain-http (MITM-able) transport. The
# installer script is run with `sh`, so a tampered download is remote code
# execution during the build (audit F9).
case "$TINYTEX_INSTALLER_URL" in
  https://*) ;;
  *)
    echo "[tinytex] ERROR: TINYTEX_INSTALLER_URL must be https:// (got: $TINYTEX_INSTALLER_URL)." >&2
    exit 2
    ;;
esac

# Optional integrity pin. Upstream regenerates install-bin-unix.sh, so a
# hard-coded hash would break routine maintenance; but a security-conscious or
# CI build can export TINYTEX_INSTALLER_SHA256=<hex> to require the download to
# match a known-good digest before it is executed (audit F9).
TINYTEX_INSTALLER_SHA256="${TINYTEX_INSTALLER_SHA256:-}"

if [[ -d "$INSTALL_ROOT/bin" ]]; then
  echo "[tinytex] Already installed at $INSTALL_ROOT/bin — skipping bootstrap."
  exit 0
fi

echo "[tinytex] Installing TinyTeX into $INSTALL_ROOT (~150 MB)..."
STAGING_PARENT="$(mktemp -d)"
trap 'rm -rf "$STAGING_PARENT"' EXIT

# Download installer to a tempfile first. ``set -o pipefail`` would catch a
# curl failure in a pipeline, but splitting the steps gives a clearer error
# message and lets a future maintainer add a SHA-256 verification step
# between the download and the execution.
INSTALLER_SCRIPT="$STAGING_PARENT/tinytex_install.sh"
echo "[tinytex] Downloading installer script..."
curl -fsSL "$TINYTEX_INSTALLER_URL" -o "$INSTALLER_SCRIPT"

# Verify the download against the optional pin before executing it. `shasum`
# ships on macOS; `sha256sum` on most Linux distros — use whichever is present.
if [[ -n "$TINYTEX_INSTALLER_SHA256" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA256="$(sha256sum "$INSTALLER_SCRIPT" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    ACTUAL_SHA256="$(shasum -a 256 "$INSTALLER_SCRIPT" | awk '{print $1}')"
  else
    echo "[tinytex] ERROR: TINYTEX_INSTALLER_SHA256 set but no sha256sum/shasum available." >&2
    exit 2
  fi
  # Compare case-insensitively: shasum/sha256sum emit lowercase, but a pin may be
  # pasted uppercase. `tr` keeps this compatible with macOS's Bash 3.2 (the ${x,,}
  # lowercase expansion is Bash 4+).
  actual_lc="$(printf '%s' "$ACTUAL_SHA256" | tr 'A-F' 'a-f')"
  expected_lc="$(printf '%s' "$TINYTEX_INSTALLER_SHA256" | tr 'A-F' 'a-f')"
  if [[ "$actual_lc" != "$expected_lc" ]]; then
    echo "[tinytex] ERROR: installer SHA-256 mismatch." >&2
    echo "[tinytex]   expected: $TINYTEX_INSTALLER_SHA256" >&2
    echo "[tinytex]   actual:   $ACTUAL_SHA256" >&2
    exit 2
  fi
  echo "[tinytex] Installer SHA-256 verified against pin."
fi

# Run the upstream installer with TINYTEX_DIR pointing at our staging
# parent. The installer creates ``$STAGING_PARENT/TinyTeX`` (macOS) or
# ``$STAGING_PARENT/.TinyTeX`` (Linux) — see the URL pinned above for the
# canonical layout convention.
echo "[tinytex] Running installer (TINYTEX_DIR=$STAGING_PARENT)..."
TINYTEX_DIR="$STAGING_PARENT" \
  TINYTEX_INSTALLER="TinyTeX" \
  sh "$INSTALLER_SCRIPT" --admin --no-path

# Locate the installer's actual output directory (handles both ``TinyTeX`` and
# ``.TinyTeX`` upstream conventions; ``find -maxdepth 2`` reaches into the
# inner ``texmf-dist`` parent without descending the whole tree).
INSTALLED_ROOT="$(find "$STAGING_PARENT" -maxdepth 1 \( -name 'TinyTeX' -o -name '.TinyTeX' \) -type d -print -quit)"
if [[ -z "$INSTALLED_ROOT" || ! -d "$INSTALLED_ROOT/bin" ]]; then
  echo "[tinytex] ERROR: upstream installer produced no recognizable layout."
  echo "[tinytex] Inspect $STAGING_PARENT for the actual contents."
  # Disconnect the cleanup trap so the diagnostic dir survives this
  # exit — otherwise ``rm -rf "$STAGING_PARENT"`` would fire on EXIT
  # and the user would have nothing to inspect.
  trap - EXIT
  exit 2
fi

# Move the installed tree to its final home. Using ``mv`` rather than ``cp``
# keeps disk usage minimal during the build; ``mkdir -p`` covers the case
# where ``resources/`` itself doesn't yet exist.
mkdir -p "$(dirname "$INSTALL_ROOT")"
mv "$INSTALLED_ROOT" "$INSTALL_ROOT"

# Sanity-check the install: the runtime discovery (shared.latex_engine) needs
# at least one engine under resources/tinytex/bin/<arch>/.
if ! find "$INSTALL_ROOT/bin" -maxdepth 2 -name pdflatex -print -quit | grep -q .; then
  echo "[tinytex] ERROR: pdflatex not present after install."
  echo "[tinytex] Inspect $INSTALL_ROOT to debug the TinyTeX bootstrap."
  exit 2
fi

# Pre-install the LaTeX packages DataLab's templates depend on so the bundled
# install can compile siunitx / dcolumn / amsmath documents offline.
echo "[tinytex] Pre-installing core LaTeX packages..."
TLMGR="$(find "$INSTALL_ROOT/bin" -maxdepth 2 -name tlmgr -print -quit)"
if [[ -x "$TLMGR" ]]; then
  "$TLMGR" install \
    siunitx dcolumn booktabs amsmath amssymb mathtools \
    geometry hyperref xcolor titlesec graphicx \
    || echo "[tinytex] Some packages failed to install; the bundled TeX may be incomplete."
fi

echo "[tinytex] Done. Bundle root: $INSTALL_ROOT"
