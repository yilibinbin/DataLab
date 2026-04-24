# Deployment, Packaging, and Release (Desktop)

This page is **desktop-only**. It does not cover web service deployment.

## Runtime Requirements

- Python: 3.10+ recommended (follow project requirements)
- Core dependencies:
  - PySide6 (GUI)
  - mpmath (multiprecision computation)
  - matplotlib (plots)
  - Pillow (images and PDF preview conversion)

### TeX Engine (Optional)

If you want PDF compilation from the desktop app:

- Install a TeX engine such as `pdflatex` / `xelatex` (TeX Live / MiKTeX)
- Ensure the desktop app can invoke the executable (PATH or a configured engine path)

## Run from Source

Use an isolated environment (Conda or venv):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r gui_requirements.txt
python data_extrapolation_gui.py
```

## Packaging (PyInstaller)

This repository provides PyInstaller configs/scripts (see the files in the repo):

- `DataLab.spec`
- `build_mac_data_gui.sh`
- `build_windows_data_gui.ps1` / `build_windows_data_gui.bat`

### Key Notes

1) Bundle resources

The desktop app loads resources at runtime (icons and offline docs). Make sure the build includes:

- `docs/desktop/` (offline desktop documentation)
- Icon assets (`DataLab.png` or `.icns/.ico`)

2) Temporary directory permissions

The app generates LaTeX/PDF intermediate files and preview images in a temporary directory:

- Windows: ensure `%TEMP%` is writable
- macOS/Linux: ensure the system temp directory is writable

3) Fonts and non-ASCII text

If you need CJK typesetting or non-ASCII UI rendering:

- Prefer `xelatex` and install appropriate fonts
- Verify fonts are available on the target machine

## Platform Notes

- Windows: use `build_windows_data_gui.ps1`; consider VC++ runtime and Qt plugins
- macOS: use `build_mac_data_gui.sh`; consider signing/notarization and `MACOSX_DEPLOYMENT_TARGET`
- Linux: build and test on the target distro; verify Qt plugins and system libs

## Common UI Settings

- Display formatting:
  - Scientific OFF: decimal places
  - Scientific ON: significant digits
- Log axes in fitting plots: `log-x` / `log-y` with automatic fallback
- Export: CSV, LaTeX, PDF (depends on TeX engine availability)

