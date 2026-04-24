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
BUILD_ROOT="$PROJECT_ROOT/build/macos_gui_build"
VENV_PATH="$BUILD_ROOT/venv"
ICON_SOURCE="$PROJECT_ROOT/DataLab.png"
ICONSET_DIR="$BUILD_ROOT/app_icon.iconset"
MAC_ICON="$BUILD_ROOT/app_icon.icns"
DEPLOY_TARGET="$(/usr/bin/sw_vers -productVersion | awk -F. '{print $1"."$2}')"
export MACOSX_DEPLOYMENT_TARGET="$DEPLOY_TARGET"

PYTHON_BIN="${PYTHON_BIN_OVERRIDE:-}"

echo "[1/4] Preparing build workspace..."
rm -rf "$BUILD_ROOT"
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

"$PYTHON_BIN" -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"

echo "[2/4] Installing Python dependencies..."
pip install --upgrade pip wheel
pip install -r "$PROJECT_ROOT/gui_requirements.txt"
pip install pyinstaller

ICON_FLAG=()
if [[ -f "$ICON_SOURCE" ]]; then
  echo "[2.5/4] Generating macOS icns icon..."
  rm -rf "$ICONSET_DIR"
  mkdir -p "$ICONSET_DIR"
  for size in 16 32 64 128 256 512; do
    sips -z "$size" "$size" "$ICON_SOURCE" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$ICON_SOURCE" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
  done
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
DESKTOP_DOCS_DIR="$PROJECT_ROOT/docs/desktop"
if [[ -d "$DESKTOP_DOCS_DIR" ]]; then
  echo "[info] Including desktop docs: $DESKTOP_DOCS_DIR"
  DOCS_DATA_FLAGS+=(--add-data "$DESKTOP_DOCS_DIR:docs/desktop")
else
  echo "[warn] Desktop docs directory not found: $DESKTOP_DOCS_DIR"
fi

HELP_SPECS_FILE="$PROJECT_ROOT/shared/help_specs.json"
if [[ -f "$HELP_SPECS_FILE" ]]; then
  echo "[info] Including help specs: $HELP_SPECS_FILE"
  DOCS_DATA_FLAGS+=(--add-data "$HELP_SPECS_FILE:shared")
else
  echo "[warn] Help specs file not found: $HELP_SPECS_FILE"
fi

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
  "${EXCLUDE_FLAGS[@]}"

APP_BUNDLE="$PROJECT_ROOT/dist/${APP_NAME}.app"
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
      ditto "$STAGED_APP" "$APP_BUNDLE"
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

echo "[5/5] Bundling complete."
echo "Resulting app: $PROJECT_ROOT/dist/${APP_NAME}.app"
echo "You can move the .app bundle anywhere; it already embeds Python and required libraries."
