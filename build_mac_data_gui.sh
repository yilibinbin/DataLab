#!/usr/bin/env bash
set -e

# macOS packaging script for the Data Extrapolation GUI.
# This script creates an isolated virtual environment, installs every required
# dependency, and uses PyInstaller to emit a standalone .app bundle that
# contains Python and all third-party libraries. No additional downloads are
# needed on the target machine.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRY_FILE="$PROJECT_ROOT/data_extrapolation_gui.py"
APP_NAME="DataLab"
BUILD_ROOT="${DATALAB_MAC_BUILD_ROOT:-$PROJECT_ROOT/build/macos_gui_build}"
VENV_PATH="$BUILD_ROOT/venv"
REUSE_MAC_VENV="${DATALAB_REUSE_MAC_VENV:-0}"
ICON_SOURCE="$PROJECT_ROOT/DataLab.png"
ICONSET_DIR="$BUILD_ROOT/app_icon.iconset"
MAC_ICON="$BUILD_ROOT/app_icon.icns"
MAC_ICON_PLIST_NAME="$(basename "$MAC_ICON" .icns)"
DEPLOY_TARGET="$(/usr/bin/sw_vers -productVersion | awk -F. '{print $1"."$2}')"
export MACOSX_DEPLOYMENT_TARGET="$DEPLOY_TARGET"

PYTHON_BIN="${PYTHON_BIN_OVERRIDE:-}"

echo "[1/4] Preparing build workspace..."
if [[ "$REUSE_MAC_VENV" == "1" ]]; then
  if [[ ! -x "$VENV_PATH/bin/python" ]]; then
    echo "[error] DATALAB_REUSE_MAC_VENV=1 but no reusable venv exists at $VENV_PATH"
    exit 1
  fi
  echo "[info] Reusing existing build venv: $VENV_PATH"
else
  rm -rf "$BUILD_ROOT"
fi
mkdir -p "$BUILD_ROOT"

check_python_target() {
  local candidate="$1"
  if [[ ! -x "$candidate" ]]; then
    return 1
  fi
  local verdict
  verdict="$("$candidate" - <<'PY' 2>/dev/null
import platform, sys, sysconfig
target = sysconfig.get_config_var("MACOSX_DEPLOYMENT_TARGET")
current = platform.mac_ver()[0]
def parse(ver):
    parts = ver.split(".")
    return tuple(int(p) for p in parts[:2])
if sys.version_info < (3, 9):
    print("too_old_python")
elif target and parse(target) > parse(current):
    print(f"too_new:{target}")
else:
    print("ok")
PY
)"
  [[ "$verdict" == "ok" ]]
}

bootstrap_standalone_python() {
  local url="${STANDALONE_PYTHON_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20251031/cpython-3.10.19+20251031-aarch64-apple-darwin-install_only_stripped.tar.gz}"
  local tarball="$BUILD_ROOT/python-standalone.tar.gz"
  local extract_dir="$BUILD_ROOT/python-standalone"
  echo "[bootstrap] 当前系统缺少兼容的 Python，自动下载便携解释器..."
  rm -rf "$extract_dir"
  if [[ ! -f "$tarball" ]]; then
    curl -L -o "$tarball" "$url"
  fi
  mkdir -p "$extract_dir"
  tar -xzf "$tarball" -C "$extract_dir"
  PYTHON_BIN="$extract_dir/python/bin/python3"
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "[error] 便携 Python 安装失败。"
    exit 1
  fi
}

if [[ -n "$PYTHON_BIN" ]]; then
  echo "[info] 使用自定义 Python: $PYTHON_BIN"
elif check_python_target "/opt/homebrew/bin/python3"; then
  PYTHON_BIN="/opt/homebrew/bin/python3"
elif check_python_target "/usr/local/bin/python3"; then
  PYTHON_BIN="/usr/local/bin/python3"
elif check_python_target "$(command -v python3 2>/dev/null)"; then
  PYTHON_BIN="$(command -v python3)"
else
  bootstrap_standalone_python
fi

if [[ "$REUSE_MAC_VENV" != "1" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi
source "$VENV_PATH/bin/activate"

if [[ "$REUSE_MAC_VENV" == "1" ]]; then
  echo "[2/4] Reusing Python dependencies..."
  python - <<'PY'
import importlib.util
import sys

missing = [
    name
    for name in ("PyInstaller", "PySide6", "scipy", "matplotlib", "numpy")
    if importlib.util.find_spec(name) is None
]
if missing:
    raise SystemExit(f"Reusable build venv is missing: {', '.join(missing)}")
print("Reusable build venv dependency check passed.")
PY
else
  echo "[2/4] Installing Python dependencies..."
  pip install --upgrade pip wheel
  pip install -r "$PROJECT_ROOT/gui_requirements.txt"
  pip install pyinstaller
fi

ICON_FLAG=()
if [[ -f "$ICON_SOURCE" ]]; then
  echo "[2.5/4] Generating macOS icns icon..."
  rm -rf "$ICONSET_DIR"
  python "$PROJECT_ROOT/tools/prepare_macos_icon.py" "$ICON_SOURCE" "$ICONSET_DIR"
  iconutil -c icns "$ICONSET_DIR" -o "$MAC_ICON"
  ICON_FLAG=(--icon "$MAC_ICON")
else
  echo "[warn] 未找到图标文件 $ICON_SOURCE ，将使用默认图标。"
fi

QT_EXCLUDES=(
  "PySide6.Qt3DAnimation"
  "PySide6.Qt3DCore"
  "PySide6.Qt3DExtras"
  "PySide6.Qt3DInput"
  "PySide6.Qt3DLogic"
  "PySide6.Qt3DRender"
  "PySide6.QtAsyncio"
  "PySide6.QtBluetooth"
  "PySide6.QtCharts"
  "PySide6.QtConcurrent"
  "PySide6.QtDataVisualization"
  "PySide6.QtDesigner"
  "PySide6.QtGraphs"
  "PySide6.QtGraphsWidgets"
  "PySide6.QtHelp"
  "PySide6.QtHttpServer"
  "PySide6.QtLocation"
  "PySide6.QtMultimedia"
  "PySide6.QtMultimediaWidgets"
  "PySide6.QtNetworkAuth"
  "PySide6.QtNfc"
  "PySide6.QtOpenGL"
  "PySide6.QtOpenGLWidgets"
  "PySide6.QtPdf"
  "PySide6.QtPdfWidgets"
  "PySide6.QtPositioning"
  "PySide6.QtQuick"
  "PySide6.QtQuick3D"
  "PySide6.QtQuickControls2"
  "PySide6.QtQuickTest"
  "PySide6.QtQuickWidgets"
  "PySide6.QtRemoteObjects"
  "PySide6.QtScxml"
  "PySide6.QtSensors"
  "PySide6.QtSerialBus"
  "PySide6.QtSerialPort"
  "PySide6.QtSpatialAudio"
  "PySide6.QtSql"
  "PySide6.QtStateMachine"
  "PySide6.QtSvg"
  "PySide6.QtSvgWidgets"
  "PySide6.QtTest"
  "PySide6.QtTextToSpeech"
  "PySide6.QtUiTools"
  "PySide6.QtWebChannel"
  "PySide6.QtWebEngineCore"
  "PySide6.QtWebEngineQuick"
  "PySide6.QtWebEngineWidgets"
  "PySide6.QtWebSockets"
  "PySide6.QtWebView"
  "PySide6.QtXml"
  "PySide6.scripts"
  "PySide6.support"
)

EXCLUDE_FLAGS=()
for module in "${QT_EXCLUDES[@]}"; do
  EXCLUDE_FLAGS+=(--exclude-module "$module")
done

DOCS_DATA_FLAGS=()
if [[ -f "$ICON_SOURCE" ]]; then
  echo "[info] Including app icon image: $ICON_SOURCE"
  DOCS_DATA_FLAGS+=(--add-data "$ICON_SOURCE:.")
else
  echo "[warn] App icon image not found: $ICON_SOURCE"
fi

PYPROJECT_FILE="$PROJECT_ROOT/pyproject.toml"
read_project_version() {
  "$PYTHON_BIN" - "$PYPROJECT_FILE" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

pyproject = Path(sys.argv[1])
try:
    import tomllib
except ModuleNotFoundError:
    in_project = False
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("["):
            break
        if in_project and stripped.startswith("version"):
            print(stripped.split("=", 1)[1].strip().strip('"'))
            break
    else:
        raise SystemExit("project.version not found in pyproject.toml")
else:
    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    print(metadata["project"]["version"])
PY
}

if [[ -f "$PYPROJECT_FILE" ]]; then
  echo "[info] Including project metadata: $PYPROJECT_FILE"
  DOCS_DATA_FLAGS+=(--add-data "$PYPROJECT_FILE:.")
  APP_VERSION="$(read_project_version)"
  echo "[info] App version: $APP_VERSION"
else
  echo "[warn] pyproject.toml not found: $PYPROJECT_FILE"
  APP_VERSION="0.0.0"
fi

DESKTOP_DOCS_DIR="$PROJECT_ROOT/docs/desktop"
if [[ -d "$DESKTOP_DOCS_DIR" ]]; then
  echo "[info] Including desktop docs: $DESKTOP_DOCS_DIR"
  DOCS_DATA_FLAGS+=(--add-data "$DESKTOP_DOCS_DIR:docs/desktop")
else
  echo "[warn] Desktop docs directory not found: $DESKTOP_DOCS_DIR"
fi

EXAMPLE_WORKSPACES_DIR="$PROJECT_ROOT/examples/workspaces"
if [[ -d "$EXAMPLE_WORKSPACES_DIR" ]]; then
  echo "[info] Including example workspaces: $EXAMPLE_WORKSPACES_DIR"
  DOCS_DATA_FLAGS+=(--add-data "$EXAMPLE_WORKSPACES_DIR:examples/workspaces")
else
  echo "[warn] Example workspaces directory not found: $EXAMPLE_WORKSPACES_DIR"
fi

HELP_SPECS_FILE="$PROJECT_ROOT/shared/help_specs.json"
if [[ -f "$HELP_SPECS_FILE" ]]; then
  echo "[info] Including help specs: $HELP_SPECS_FILE"
  DOCS_DATA_FLAGS+=(--add-data "$HELP_SPECS_FILE:shared")
else
  echo "[warn] Help specs file not found: $HELP_SPECS_FILE"
fi

# Optional: bundle TinyTeX (~200 MB) into the .app so users without a
# local TeX Live install can compile PDFs offline. Opt-in via
# ``DATALAB_BUNDLE_TINYTEX=1`` because the bundle size impact is large.
# The runtime discovery layer (``shared.latex_engine``) looks under
# ``<app>/resources/tinytex/bin/<arch>``; the installer + --add-data
# pair below puts it exactly there.
if [[ "${DATALAB_BUNDLE_TINYTEX:-0}" == "1" ]]; then
  echo "[2.7/4] Bundling TinyTeX (DATALAB_BUNDLE_TINYTEX=1)..."
  bash "$PROJECT_ROOT/tools/install_tinytex.sh"
  TINYTEX_DIR="$PROJECT_ROOT/resources/tinytex"
  if [[ -d "$TINYTEX_DIR" ]]; then
    echo "[info] Including TinyTeX bundle: $TINYTEX_DIR"
    DOCS_DATA_FLAGS+=(--add-data "$TINYTEX_DIR:resources/tinytex")
  else
    echo "[warn] TinyTeX install reported success but $TINYTEX_DIR missing."
  fi
fi

# Hidden imports and package collections for bundled dependencies.
# certifi provides the CA bundle used by the frozen update checker.
# SymPy is collected for formula parsing, symbolic fitting, and constraints.
# SciPy is collected for precision-16 fitting and root-solving fast paths.
# emcee and corner sit behind ``HAS_EMCEE`` guards in fitting.mcmc_fitter, so
# PyInstaller's import graph won't pick them up automatically; declare them
# explicitly so the bundled .app actually ships MCMC support.
HIDDEN_IMPORT_FLAGS=(
  --hidden-import "certifi"
  --collect-all "certifi"
  --hidden-import "mpmath"
  --collect-all "mpmath"
  --hidden-import "sympy"
  --collect-all "sympy"
  --hidden-import "scipy"
  --collect-all "scipy"
  --hidden-import "emcee"
  --hidden-import "emcee.moves"
  --hidden-import "emcee.backends"
  --collect-all "emcee"
  --hidden-import "corner"
  --collect-all "corner"
)

echo "[3/4] Building macOS app bundle with PyInstaller..."
rm -rf "$PROJECT_ROOT/dist"
TARGET_ARCH_FLAG=()
if [[ -n "${PYINSTALLER_TARGET_ARCH:-}" ]]; then
  TARGET_ARCH_FLAG=(--target-arch "$PYINSTALLER_TARGET_ARCH")
fi
pyinstaller "$ENTRY_FILE" \
  --name "$APP_NAME" \
  --windowed \
  --noconfirm \
  --clean \
  "${ICON_FLAG[@]}" \
  "${TARGET_ARCH_FLAG[@]}" \
  "${DOCS_DATA_FLAGS[@]}" \
  "${HIDDEN_IMPORT_FLAGS[@]}" \
  "${EXCLUDE_FLAGS[@]}"

APP_BUNDLE="$PROJECT_ROOT/dist/${APP_NAME}.app"
INFO_PLIST_FILE="$APP_BUNDLE/Contents/Info.plist"
PLIST_BUDDY="/usr/libexec/PlistBuddy"

if [[ ! -f "$INFO_PLIST_FILE" ]]; then
  echo "[error] Missing generated Info.plist: $INFO_PLIST_FILE"
  exit 1
fi

if [[ -f "$MAC_ICON" ]]; then
  if ! "$PLIST_BUDDY" -c "Set :CFBundleIconFile $MAC_ICON_PLIST_NAME" "$INFO_PLIST_FILE" 2>/dev/null; then
    "$PLIST_BUDDY" -c "Add :CFBundleIconFile string $MAC_ICON_PLIST_NAME" "$INFO_PLIST_FILE"
  fi
fi

echo "[3.5/4] Patching macOS document type metadata..."
"$PLIST_BUDDY" -c "Delete :CFBundleDocumentTypes" "$INFO_PLIST_FILE" 2>/dev/null || true
"$PLIST_BUDDY" -c "Delete :UTExportedTypeDeclarations" "$INFO_PLIST_FILE" 2>/dev/null || true
if ! "$PLIST_BUDDY" -c "Set :CFBundleIdentifier org.datalab.desktop" "$INFO_PLIST_FILE" 2>/dev/null; then
  "$PLIST_BUDDY" -c "Add :CFBundleIdentifier string org.datalab.desktop" "$INFO_PLIST_FILE"
fi
if ! "$PLIST_BUDDY" -c "Set :CFBundleShortVersionString $APP_VERSION" "$INFO_PLIST_FILE" 2>/dev/null; then
  "$PLIST_BUDDY" -c "Add :CFBundleShortVersionString string $APP_VERSION" "$INFO_PLIST_FILE"
fi
if ! "$PLIST_BUDDY" -c "Set :CFBundleVersion $APP_VERSION" "$INFO_PLIST_FILE" 2>/dev/null; then
  "$PLIST_BUDDY" -c "Add :CFBundleVersion string $APP_VERSION" "$INFO_PLIST_FILE"
fi

"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes array" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes:0 dict" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes:0:CFBundleTypeName string DataLab Workspace" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes:0:CFBundleTypeRole string Editor" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes:0:LSHandlerRank string Owner" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes array" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes:0 string org.datalab.workspace" "$INFO_PLIST_FILE"

"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations array" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0 dict" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeIdentifier string org.datalab.workspace" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeDescription string DataLab Workspace" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeConformsTo array" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeConformsTo:0 string public.data" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification dict" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification:public.filename-extension array" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification:public.filename-extension:0 string datalab" "$INFO_PLIST_FILE"
"$PLIST_BUDDY" -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification:public.mime-type string application/vnd.datalab.workspace" "$INFO_PLIST_FILE"

STAGING_DIR="$(mktemp -d)"
STAGED_APP="$STAGING_DIR/${APP_NAME}.app"

echo "[4/4] Cleaning extended attributes and signing..."
if [[ -d "$APP_BUNDLE" ]]; then
  rm -rf "$STAGED_APP"
  cp -R "$APP_BUNDLE" "$STAGED_APP"
  if command -v xattr >/dev/null 2>&1; then
    xattr -cr "$STAGED_APP" || true
  fi
  if command -v codesign >/dev/null 2>&1; then
    if codesign --force --deep --sign - "$STAGED_APP"; then
      echo "[info] Ad-hoc signature applied."
      rm -rf "$APP_BUNDLE"
      ditto --norsrc "$STAGED_APP" "$APP_BUNDLE"
      xattr -cr "$APP_BUNDLE" || true
    else
      echo "[warn] codesign failed; bundle remains unsigned."
    fi
  else
    echo "[warn] codesign command not found; bundle remains unsigned."
  fi
  rm -rf "$STAGING_DIR"
else
  echo "[error] 未找到生成的 .app，无法签名。"
fi

if [[ -f "$MAC_ICON" && -d "$APP_BUNDLE" ]]; then
  python "$PROJECT_ROOT/tools/inspect_macos_bundle_icon.py" "$APP_BUNDLE"
fi

if [[ "${DATALAB_BUILD_PKG:-0}" == "1" ]]; then
  echo "[5/6] Building macOS installer package (DATALAB_BUILD_PKG=1)..."
  if [[ ! -d "$APP_BUNDLE" ]]; then
    echo "[error] 未找到生成的 .app，无法生成 PKG。"
    exit 1
  fi
  if ! command -v pkgbuild >/dev/null 2>&1; then
    echo "[error] pkgbuild command not found; install Xcode command line tools."
    exit 1
  fi
  if ! command -v productbuild >/dev/null 2>&1; then
    echo "[error] productbuild command not found; install Xcode command line tools."
    exit 1
  fi
  PKG_ROOT="$BUILD_ROOT/pkgroot"
  PKG_COMPONENT="$BUILD_ROOT/DataLab-component.pkg"
  PKG_COMPONENT_PLIST="$BUILD_ROOT/DataLab-components.plist"
  PKG_OUTPUT="$PROJECT_ROOT/dist/DataLab-${APP_VERSION}-macOS.pkg"
  rm -rf "$PKG_ROOT" "$PKG_COMPONENT" "$PKG_COMPONENT_PLIST" "$PKG_OUTPUT"
  mkdir -p "$PKG_ROOT"
  ditto --norsrc "$APP_BUNDLE" "$PKG_ROOT/${APP_NAME}.app"
  xattr -cr "$PKG_ROOT/${APP_NAME}.app" || true
  cat > "$PKG_COMPONENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<array>
  <dict>
    <key>RootRelativeBundlePath</key>
    <string>${APP_NAME}.app</string>
    <key>BundleIsRelocatable</key>
    <false/>
    <key>BundleIsVersionChecked</key>
    <false/>
    <key>BundleHasStrictIdentifier</key>
    <true/>
    <key>BundleOverwriteAction</key>
    <string>upgrade</string>
  </dict>
</array>
</plist>
PLIST

  PKGBUILD_ARGS=(
    --root "$PKG_ROOT"
    --component-plist "$PKG_COMPONENT_PLIST"
    --identifier org.datalab.desktop
    --version "$APP_VERSION"
    --install-location /Applications
    "$PKG_COMPONENT"
  )
  pkgbuild "${PKGBUILD_ARGS[@]}"

  PRODUCTBUILD_ARGS=(
    --package "$PKG_COMPONENT"
  )
  if [[ -n "${DATALAB_MAC_INSTALLER_IDENTITY:-}" ]]; then
    echo "[info] Signing final product package with Developer ID Installer identity: $DATALAB_MAC_INSTALLER_IDENTITY"
    PRODUCTBUILD_ARGS+=(--sign "$DATALAB_MAC_INSTALLER_IDENTITY")
  else
    echo "[warn] DATALAB_MAC_INSTALLER_IDENTITY is not set; pkg is not auto-installable on standard macOS."
    echo "[warn] Expected Developer ID Installer format: Developer ID Installer: Name (TEAMID)"
  fi
  PRODUCTBUILD_ARGS+=("$PKG_OUTPUT")

  productbuild "${PRODUCTBUILD_ARGS[@]}"
  echo "[info] Installer package: $PKG_OUTPUT"
fi

echo "[5/5] Bundling complete."
echo "Resulting app: $PROJECT_ROOT/dist/${APP_NAME}.app"
echo "You can move the .app bundle anywhere; it already embeds Python and required libraries."
