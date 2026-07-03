from __future__ import annotations

import re
from pathlib import Path


_LITERAL_ZH_FILEDIALOG_TITLE_RE = re.compile(
    r"""QFileDialog\.get(?:Open|Save)FileName\(\s*self\s*,\s*(?:f)?["'](?:选择|保存)""",
    re.MULTILINE,
)


def _read(rel_path: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / rel_path).read_text(encoding="utf-8")


def test_window_file_dialog_titles_use_tr():
    text = _read("app_desktop/window.py")

    assert _LITERAL_ZH_FILEDIALOG_TITLE_RE.search(text) is None
    assert 'self._tr("选择数据文件", "Select Data File")' in text
    assert 'self._tr("保存 LaTeX", "Save LaTeX")' in text
    assert 'self._tr("选择常数文件", "Select Constants File")' in text


def test_window_latex_pdf_file_dialog_titles_use_tr():
    # Batch-10 Stage 3: the LaTeX/PDF mixin was split into a compile mixin (the
    # QFileDialog + engine strings) and a PDF-preview mixin (the preview
    # strings); assert against the file that now owns each string.
    compile_text = _read("app_desktop/window_latex_compile_mixin.py")
    preview_text = _read("app_desktop/window_pdf_preview_mixin.py")

    assert _LITERAL_ZH_FILEDIALOG_TITLE_RE.search(compile_text) is None
    assert _LITERAL_ZH_FILEDIALOG_TITLE_RE.search(preview_text) is None
    assert 'self._tr("选择 LaTeX 文件", "Select LaTeX File")' in compile_text
    assert 'self._tr("保存 LaTeX 文件", "Save LaTeX File")' in compile_text
    assert 'self._tr(f"选择 {engine} 可执行文件", f"Select {engine} Executable")' in compile_text
    assert 'self._tr("缺少 pdftoppm/gs，无法生成预览", "Missing pdftoppm/gs; cannot generate preview")' in preview_text
    assert 'self._tr("PDF 预览转换超时。", "PDF preview conversion timed out.")' in preview_text
    assert 'QLabel(self._tr(f"页 {idx}", f"Page {idx}"))' in preview_text
    assert 'self._tr(f"PDF 预览工具缺失: {exc}", f"PDF preview tool missing: {exc}")' in preview_text
    assert 'self._tr(f"PDF 预览生成异常: {exc}", f"PDF preview generation error: {exc}")' in preview_text


def test_window_images_status_and_log_texts_use_tr():
    text = _read("app_desktop/window_images_mixin.py")

    assert 'self._tr("无法生成拟合图像。", "Unable to render fitting image.")' in text
    assert 'self._tr(f"读取图片失败 {path}: {exc}", f"Failed to read image {path}: {exc}")' in text
    assert 'self._tr(f"写入批次图像失败: {exc}", f"Failed to write batch image: {exc}")' in text
