from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_about_dialog_uses_reduce3j_style_message_box_with_icon_and_links() -> None:
    about_path = ROOT / "app_desktop" / "about_dialog.py"

    assert about_path.is_file(), "About dialog must live in its own module."

    text = about_path.read_text(encoding="utf-8")
    assert "QMessageBox" in text
    assert "QDialog" not in text
    assert "setStyleSheet" not in text
    assert "setIconPixmap" in text
    assert "setTextFormat(Qt.TextFormat.RichText)" in text
    assert "setOpenExternalLinks(True)" in text
    assert "setStandardButtons(QMessageBox.StandardButton.Ok)" in text
    assert "_locate_icon_file" in text
    assert "QPixmap" in text
    assert "REPOSITORY_URL" in text
    assert "LICENSE_URL" in text
    assert "DOCS_URL" in text


def test_window_show_about_uses_custom_about_dialog() -> None:
    text = (ROOT / "app_desktop" / "window.py").read_text(encoding="utf-8")
    start = text.index("    def _show_about(self):")
    end = text.index("    def _toggle_latex_options", start)
    show_about = text[start:end]

    assert "from .about_dialog import show_about_dialog" in text
    assert "show_about_dialog(" in show_about
    assert "QMessageBox.information" not in show_about


def test_packagers_include_app_icon_image_for_about_dialog() -> None:
    spec_text = (ROOT / "DataLab.spec").read_text(encoding="utf-8")
    mac_text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")
    win_text = (ROOT / "build_windows_data_gui.ps1").read_text(encoding="utf-8")

    assert '(_rel("DataLab.png"), ".")' in spec_text
    assert 'DOCS_DATA_FLAGS+=(--add-data "$ICON_SOURCE:.")' in mac_text
    assert '$dataArgs += @("--add-data", ("{0};." -f $iconTargetPng))' in win_text
