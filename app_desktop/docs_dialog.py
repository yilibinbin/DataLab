from __future__ import annotations

from desktop_doc_loader import load_desktop_doc, load_desktop_manifest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class DocsDialog(QDialog):
    def __init__(self, lang: str, parent=None):
        super().__init__(parent)
        self._lang = "en" if str(lang).lower().startswith("en") else "zh"

        self.setWindowTitle("文档" if self._lang == "zh" else "Documentation")
        self.resize(1040, 720)

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)

        self.page_list = QListWidget()
        self.page_list.setMinimumWidth(240)
        splitter.addWidget(self.page_list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索…" if self._lang == "zh" else "Search…")
        self.search_edit.returnPressed.connect(self._find_next)
        search_row.addWidget(self.search_edit)
        self.find_btn = QPushButton("查找" if self._lang == "zh" else "Find")
        self.find_btn.clicked.connect(self._find_next)
        search_row.addWidget(self.find_btn)
        right_layout.addLayout(search_row)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        right_layout.addWidget(self.browser, stretch=1)

        manifest = load_desktop_manifest()
        for entry in manifest:
            slug = str(entry.get("slug") or "").strip()
            if not slug:
                continue
            title = str(entry.get("title_zh") or slug) if self._lang == "zh" else str(entry.get("title_en") or slug)
            item = QListWidgetItem(title or slug)
            item.setData(Qt.UserRole, slug)
            self.page_list.addItem(item)

        self.page_list.currentItemChanged.connect(self._on_page_changed)
        if self.page_list.count() > 0:
            self.page_list.setCurrentRow(0)
        else:
            self._render_message("未找到文档页面。", "No documentation pages found.")

    def _render_message(self, zh: str, en: str):
        message = zh if self._lang == "zh" else en
        try:
            self.browser.setPlainText(message)
        except Exception:
            self.browser.setHtml(f"<pre>{message}</pre>")

    def _load_markdown(self, text: str):
        if hasattr(self.browser, "setMarkdown"):
            self.browser.setMarkdown(text)
            return
        self.browser.setPlainText(text)

    def _on_page_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None):
        if not current:
            return
        slug = current.data(Qt.UserRole)
        if not isinstance(slug, str) or not slug:
            return
        content = load_desktop_doc(slug, "en" if self._lang == "en" else "zh")
        self._load_markdown(content)
        try:
            self.browser.moveCursor(QTextCursor.Start)
        except Exception:
            pass

    def _find_next(self):
        query = (self.search_edit.text() if hasattr(self, "search_edit") else "").strip()
        if not query:
            return
        if self.browser.find(query):
            return
        try:
            self.browser.moveCursor(QTextCursor.Start)
        except Exception:
            pass
        self.browser.find(query)


__all__ = ["DocsDialog"]

