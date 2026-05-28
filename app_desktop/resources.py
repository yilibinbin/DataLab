from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

ICON_CANDIDATES = ("DataLab.ico", "DataLab.png")

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False
    Image = object  # type: ignore[assignment]


def _augment_default_path() -> None:
    """Expose common package-manager paths when launched from Finder."""
    extra_dirs: list[str] = []
    if sys.platform == "darwin":
        prefixes = []
        brew_prefix = os.environ.get("HOMEBREW_PREFIX")
        if brew_prefix:
            prefixes.append(brew_prefix)
        prefixes.extend(["/opt/homebrew", "/usr/local"])
        for prefix in prefixes:
            extra_dirs.append(str(Path(prefix) / "bin"))
            extra_dirs.append(str(Path(prefix) / "sbin"))
        extra_dirs.extend(
            [
                "/opt/local/bin",
                "/opt/local/sbin",
                "/Library/TeX/texbin",
            ]
        )
    elif sys.platform.startswith("linux"):
        extra_dirs.extend(["/usr/local/bin", "/usr/local/sbin"])
    if not extra_dirs:
        return
    original = os.environ.get("PATH", "")
    parts = [segment for segment in original.split(os.pathsep) if segment]
    seen = set(parts)
    additions = []
    for candidate in extra_dirs:
        if candidate and candidate not in seen and Path(candidate).exists():
            additions.append(candidate)
            seen.add(candidate)
    if additions:
        os.environ["PATH"] = os.pathsep.join(additions + parts)


_DEFAULT_PATH_AUGMENTED = False


def _ensure_default_path_augmented() -> None:
    global _DEFAULT_PATH_AUGMENTED
    if _DEFAULT_PATH_AUGMENTED:
        return
    _augment_default_path()
    _DEFAULT_PATH_AUGMENTED = True


def _compute_default_pdf_dpi() -> int:
    try:
        screen = QApplication.primaryScreen()
        if screen:
            dpi = screen.logicalDotsPerInch()
            boosted = int(round(dpi * 1.5))
            return max(150, min(boosted, 300))
    except Exception:
        pass
    return 220


def _detect_windows_light_mode() -> bool | None:
    if os.name != "nt":
        return None
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return True if value == 1 else False
    except Exception:
        return None


def _build_palette(dark: bool) -> QPalette:
    palette = QPalette()
    if not dark:
        window = QColor("#f4f6fb")
        base = QColor("#ffffff")
        alt = QColor("#eef1f5")
        text = QColor("#202124")
        accent = QColor("#4f6bed")  # Win11-lite blue
        palette.setColor(QPalette.ColorRole.Window, window)
        palette.setColor(QPalette.ColorRole.Base, base)
        palette.setColor(QPalette.ColorRole.AlternateBase, alt)
        palette.setColor(QPalette.ColorRole.ToolTipBase, base)
        palette.setColor(QPalette.ColorRole.ToolTipText, text)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Text, text)
        palette.setColor(QPalette.ColorRole.Button, base)
        palette.setColor(QPalette.ColorRole.ButtonText, text)
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        return palette
    base = QColor("#1d1f21")
    alt = QColor("#25282b")
    text = QColor("#e8e8e8")
    accent = QColor("#5d9cec")
    palette.setColor(QPalette.ColorRole.Window, base)
    palette.setColor(QPalette.ColorRole.Base, alt)
    palette.setColor(QPalette.ColorRole.AlternateBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipBase, alt)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, alt)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0d1117"))
    return palette


def _apply_system_theme(app: QApplication, prefer_light: bool | None = None):
    prefer_light = _detect_windows_light_mode() if prefer_light is None else prefer_light
    dark = prefer_light is not None and not prefer_light
    palette = _build_palette(dark=dark)
    try:
        app.setPalette(palette)
    except Exception:
        pass
    return prefer_light


def _resource_search_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        path = Path(meipass)
        roots.append(path)
        roots.append(path / "_internal")
    module_root = Path(__file__).resolve().parent
    roots.append(module_root)
    roots.append(module_root.parent)
    roots.append(module_root / "windows")
    roots.append(module_root / "_internal")
    roots.append(Path.cwd())
    return roots


def resolve_resource_path(relative: str | Path) -> Path | None:
    rel = Path(relative)
    seen: set[Path] = set()
    for root in _resource_search_roots():
        try:
            root = root.resolve()
        except Exception:
            continue
        if root in seen or not root.exists():
            continue
        seen.add(root)
        candidates = [
            root / rel,
            root / rel.name,
            root / rel / rel.name,
            root / rel.name / rel.name,
        ]
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                continue
    return None


def _locate_icon_file() -> Path | None:
    for name in ICON_CANDIDATES:
        resolved = resolve_resource_path(name)
        if resolved and resolved.exists():
            return resolved
    for root in _resource_search_roots():
        try:
            root = root.resolve()
        except Exception:
            continue
        if not root.exists():
            continue
        try:
            pngs = sorted(root.glob("*.png"), key=lambda p: p.name.lower())
            for png in pngs:
                if png.is_file():
                    return png
        except OSError:
            continue
    return None


def _pil_to_qpixmap(image: Image.Image) -> QPixmap:
    if not PIL_AVAILABLE:
        raise RuntimeError("PIL not available")
    if getattr(image, "mode", "") not in ("RGBA", "BGRA"):
        working = image.convert("RGBA")
    else:
        working = image
    data = working.tobytes("raw", "RGBA")
    qimage = QImage(data, working.width, working.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage)


def _is_running_inside_macos_app_bundle() -> bool:
    if sys.platform != "darwin":
        return False
    executable = Path(sys.executable).resolve()
    macos_dir = executable.parent
    contents_dir = macos_dir.parent
    app_dir = contents_dir.parent
    info_plist = contents_dir / "Info.plist"
    return (
        macos_dir.name == "MacOS"
        and contents_dir.name == "Contents"
        and app_dir.name.endswith(".app")
        and app_dir.is_dir()
        and contents_dir.is_dir()
        and macos_dir.is_dir()
        and info_plist.is_file()
    )


def should_set_runtime_app_icon() -> bool:
    if (
        sys.platform == "darwin"
        and getattr(sys, "frozen", False)
        and _is_running_inside_macos_app_bundle()
    ):
        return False
    return True


__all__ = [
    "ICON_CANDIDATES",
    "PIL_AVAILABLE",
    "_apply_system_theme",
    "_compute_default_pdf_dpi",
    "_detect_windows_light_mode",
    "_ensure_default_path_augmented",
    "_is_running_inside_macos_app_bundle",
    "_locate_icon_file",
    "_pil_to_qpixmap",
    "resolve_resource_path",
    "should_set_runtime_app_icon",
]
