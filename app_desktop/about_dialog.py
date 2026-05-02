"""Reduce3j-style rich About dialog for the desktop GUI."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QLabel, QMessageBox, QWidget

from shared.update_checker import REPOSITORY_URL, current_version

from .resources import _locate_icon_file


LICENSE_URL = f"{REPOSITORY_URL}/blob/main/LICENSE"
DOCS_URL = f"{REPOSITORY_URL}/tree/main/docs/desktop"


def _about_html(*, lang: str, version: str) -> str:
    repo = escape(REPOSITORY_URL, quote=True)
    license_url = escape(LICENSE_URL, quote=True)
    docs_url = escape(DOCS_URL, quote=True)
    version_text = escape(version)
    if lang == "en":
        return (
            f"<h3>DataLab {version_text}</h3>"
            "<p>High-precision scientific toolkit for sequence extrapolation, "
            "curve fitting, uncertainty propagation, statistics, and LaTeX export.</p>"
            f"<p><b>Repository:</b> <a href='{repo}'>{repo}</a></p>"
            f"<p><b>License:</b> MIT — see <a href='{license_url}'>LICENSE</a> "
            "in the source distribution.</p>"
            f"<p><b>Documentation:</b> <a href='{docs_url}'>docs/desktop</a></p>"
            "<p><b>Author:</b> Fang Hao, CAS WIPM External Field Theory Group.</p>"
        )
    return (
        f"<h3>DataLab {version_text}</h3>"
        "<p>高精度科学数据处理工具，支持序列外推、曲线拟合、不确定度传播、"
        "统计分析与 LaTeX 导出。</p>"
        f"<p><b>项目主页：</b><a href='{repo}'>{repo}</a></p>"
        f"<p><b>许可证：</b>MIT — 详见源码中的 <a href='{license_url}'>LICENSE</a>。</p>"
        f"<p><b>文档：</b><a href='{docs_url}'>docs/desktop</a></p>"
        "<p><b>作者：</b>中国科学院精密测量院外场理论组 · 方昊。</p>"
    )


def _about_icon(parent: QWidget | None) -> QPixmap:
    if parent is not None:
        icon: QIcon = parent.windowIcon()
        if not icon.isNull():
            pixmap = icon.pixmap(72, 72)
            if not pixmap.isNull():
                return pixmap

    icon_path = _locate_icon_file()
    if icon_path:
        pixmap = QPixmap(str(icon_path))
        if not pixmap.isNull():
            return pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return QPixmap()


def _enable_external_links(msg: QMessageBox) -> None:
    if hasattr(msg, "setTextInteractionFlags"):
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    for label in msg.findChildren(QLabel):
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)


def show_about_dialog(*, parent: QWidget, lang: str) -> None:
    msg = QMessageBox(parent)
    msg.setWindowTitle("About DataLab" if lang == "en" else "关于 DataLab")
    pixmap = _about_icon(parent)
    if not pixmap.isNull():
        msg.setIconPixmap(pixmap)
    msg.setTextFormat(Qt.TextFormat.RichText)
    msg.setText(_about_html(lang=lang, version=current_version()))
    msg.setStandardButtons(QMessageBox.StandardButton.Ok)
    ok_button = msg.button(QMessageBox.StandardButton.Ok)
    if ok_button is not None:
        ok_button.setText("OK" if lang == "en" else "确定")
    _enable_external_links(msg)
    msg.exec()
