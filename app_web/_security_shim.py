from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import warnings
from pathlib import Path

_logger = logging.getLogger(__name__)


try:
    from .security import (  # type: ignore[import-not-found]
        _mpmath_lock as mpmath_lock,
        configure_app_security,
        csrf_protect,
        get_csrf_token,
        mpmath_synchronized,
        validate_latex_engine,
        validate_text_size,
    )
    from .latex_security import compile_latex_safe  # type: ignore[import-not-found]
except ImportError as _import_exc:
    # Security modules unavailable. Previously this silently installed
    # no-op stubs, which meant a typo in ``security.py`` would
    # silently disable CSRF + session hardening in production.
    #
    # New policy:
    # - In production (``DATALAB_DEBUG`` unset), raise immediately so
    #   an ops team sees the failure and knows to investigate before
    #   anyone hits an unprotected endpoint.
    # - Only when ``DATALAB_DEBUG=1`` is set do we fall back to the
    #   no-op shims so local dev isn't blocked by a missing optional
    #   dep (e.g., a contributor who hasn't installed all of
    #   ``web_requirements.txt`` yet). Even then we log at ERROR
    #   level so the degraded state is impossible to miss.
    _debug = os.environ.get("DATALAB_DEBUG", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if not _debug:
        raise RuntimeError(
            "DataLab Web cannot start: app_web.security or "
            "app_web.latex_security failed to import "
            f"({_import_exc!r}). Refusing to fall back to no-op "
            "security stubs in production. Set DATALAB_DEBUG=1 to "
            "opt into the unsafe dev fallback for local debugging only."
        ) from _import_exc

    _logger.error(
        "SECURITY MODULE IMPORT FAILED (%r) — running in DEV UNSAFE MODE. "
        "CSRF, mpmath synchronisation, and LaTeX compile sandboxing "
        "are DISABLED. NEVER run DataLab this way in production.",
        _import_exc,
    )
    warnings.warn(
        "Security modules not found. Running in UNSAFE DEV mode. "
        "CSRF + session hardening are disabled.",
        RuntimeWarning, stacklevel=2,
    )

    def csrf_protect(f):  # type: ignore[no-redef]
        """Dummy CSRF decorator when security module not available."""
        return f

    def get_csrf_token():  # type: ignore[no-redef]
        """Dummy CSRF token generator."""
        return "INSECURE_DEV_MODE"

    def configure_app_security(app):  # type: ignore[no-redef]
        """Dummy security configuration."""
        return None

    def validate_text_size(text, field_name="input"):  # type: ignore[no-redef]
        """Dummy input validation."""
        return text

    def mpmath_synchronized(f):  # type: ignore[no-redef]
        """Dummy synchronization decorator."""
        return f

    # Dev-mode fallback lock — still real, just isolated from
    # production. Without this, ``with mpmath_lock`` blows up at
    # import time in degraded dev mode.
    import threading as _threading_fallback
    mpmath_lock = _threading_fallback.Lock()  # type: ignore[no-redef]

    def validate_latex_engine(engine):  # type: ignore[no-redef]
        """Dummy LaTeX engine validation."""
        return engine or "pdflatex"

    def compile_latex_safe(tex_text, engine, warnings_list, label):  # type: ignore[no-redef]
        """Dummy safe LaTeX compilation - use insecure version."""
        engine = (engine or "pdflatex").strip() or "pdflatex"
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / f"{label}.tex"
            tex_path.write_text(tex_text, encoding="utf-8")
            # Match the primary compile_latex_safe: never trust tex to omit
            # \write18 — force shell-escape off even on the fallback path so a
            # missing security module can't quietly enable command execution.
            cmd = [
                engine,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                tex_path.name,
            ]
            try:
                subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                    text=True,
                )
                pdf_path = tex_path.with_suffix(".pdf")
                if not pdf_path.exists():
                    warnings_list.append(
                        f"{label} LaTeX 编译未生成 PDF。 / {label} LaTeX compilation did not produce a PDF."
                    )
                    return None
                return pdf_path.read_bytes()
            except FileNotFoundError:
                warnings_list.append(
                    f"未找到 LaTeX 引擎 {engine}，请确认已安装或调整引擎路径。"
                    f" / LaTeX engine not found: {engine}. Please install TeX or adjust the engine path."
                )
            except subprocess.CalledProcessError as exc:
                warnings_list.append(
                    f"{label} LaTeX 编译失败: {exc.stderr or exc.stdout} / {label} LaTeX compilation failed. Please check logs."
                )
            return None

