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

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="$PROJECT_ROOT/resources/tinytex"

# Pin the TinyTeX bootstrap installer URL. TinyTeX's "self-installing" mode
# fetches the right TeX Live binary set for the host platform automatically.
# Bumping this URL is a routine maintenance task; the test suite only checks
# the install location, not the download endpoint.
TINYTEX_INSTALLER_URL="${TINYTEX_INSTALLER_URL:-https://yihui.org/tinytex/install-bin-unix.sh}"

if [[ -d "$INSTALL_ROOT/bin" ]]; then
  echo "[tinytex] Already installed at $INSTALL_ROOT/bin — skipping bootstrap."
  exit 0
fi

echo "[tinytex] Installing TinyTeX into $INSTALL_ROOT (~150 MB)..."
mkdir -p "$INSTALL_ROOT"

# TinyTeX's installer respects TINYTEX_DIR for the destination. The installer
# defaults to ~/.TinyTeX; we redirect it into resources/tinytex so PyInstaller
# can pick it up at bundle time. The shell-based installer covers Linux + mac
# in one path; on Windows the ps1 build script handles it via a different
# bootstrap (Scoop / direct .zip download).
TINYTEX_DIR="$INSTALL_ROOT" \
  TINYTEX_INSTALLER="TinyTeX" \
  bash -c "curl -fsSL '$TINYTEX_INSTALLER_URL' | sh -s - --admin --no-path"

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
