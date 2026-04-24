from __future__ import annotations

from desktop_doc_loader import _is_valid_doc_slug


def test_doc_slug_length_limit():
    assert _is_valid_doc_slug("a" * 128)
    assert not _is_valid_doc_slug("a" * 129)
