#!/usr/bin/env python3
"""
Security Module for DataLab Web
================================

Provides CSRF protection, input validation, and LaTeX security hardening.

Author: Security Hardening Patch 2025-12-12
"""

import hmac
import os
import secrets
import threading
import logging
from functools import wraps
from flask import request, session, abort, current_app, has_app_context, has_request_context, render_template

from shared.bilingual import _dual_msg

# ============================================================
# CSRF Protection
# ============================================================

CSRF_TOKEN_LENGTH = 32
CSRF_HEADER_NAME = 'X-CSRF-Token'
CSRF_FORM_NAME = 'csrf_token'
CSRF_COOKIE_NAME = 'datalab_csrf'


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


def get_csrf_token() -> str:
    """Get or create the CSRF token bound to the current server-side session.

    The token is generated and stored in ``session['csrf_token']``. The
    ``datalab_csrf`` cookie is set in ``add_security_headers`` as a
    client-readable mirror for frontend convenience, but we NEVER seed the
    session from the cookie: doing so would let an attacker who can plant a
    cookie (subdomain takeover, MITM on HTTP, etc.) forge the token.
    """
    if 'csrf_token' not in session:
        session['csrf_token'] = generate_csrf_token()
    return session['csrf_token']


def validate_csrf_token(token: str) -> bool:
    """Validate a submitted CSRF token against the server-side session token.

    The authoritative value is ``session['csrf_token']``. If the session has
    no token (e.g. a POST before a GET ever established one), validation
    fails — we do NOT fall back to a cookie-to-submission comparison, because
    that collapses CSRF protection to "attacker-controlled cookie matches
    attacker-controlled submission".
    """
    if not token:
        return False

    expected = session.get('csrf_token')
    if not expected:
        return False
    return hmac.compare_digest(expected, token)


def csrf_protect(f):
    """
    Decorator to protect routes against CSRF attacks.

    Usage:
        @app.route('/submit', methods=['POST'])
        @csrf_protect
        def submit():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            # Try to get token from form data or headers
            token = request.form.get(CSRF_FORM_NAME) or request.headers.get(CSRF_HEADER_NAME)

            if not token or not validate_csrf_token(token):
                current_app.logger.warning(
                    f"CSRF validation failed for {request.endpoint} from {request.remote_addr}"
                )
                abort(400, description="CSRF验证失败。请刷新页面后重试。")

        return f(*args, **kwargs)

    return decorated


# ============================================================
# LaTeX Engine Whitelist
# ============================================================

ALLOWED_LATEX_ENGINES = {'pdflatex', 'xelatex', 'lualatex'}


def validate_latex_engine(engine: str) -> str:
    """
    Validate and sanitize LaTeX engine name.

    Args:
        engine: User-provided engine name

    Returns:
        Safe engine name from whitelist

    Raises:
        ValueError: If engine is not in whitelist
    """
    engine = (engine or '').strip().lower()

    if not engine:
        return 'pdflatex'  # Default safe choice

    if engine not in ALLOWED_LATEX_ENGINES:
        remote_addr = request.remote_addr if has_request_context() else "unknown"
        logger = current_app.logger if has_app_context() else logging.getLogger(__name__)
        logger.error("Blocked dangerous LaTeX engine: %s from %s", engine, remote_addr)
        allowed = ", ".join(sorted(ALLOWED_LATEX_ENGINES))
        raise ValueError(
            _dual_msg(
                f"不支持的 LaTeX 引擎: {engine}。允许的引擎: {allowed}。",
                f"Unsupported LaTeX engine: {engine}. Allowed engines: {allowed}.",
            )
        )

    return engine


# ============================================================
# Input Size Limits
# ============================================================

MAX_TEXT_INPUT_LENGTH = 1_000_000  # 1MB of text
MAX_TEXT_LINES = 100_000
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_text_size(text: str, field_name: str = "输入") -> str:
    """
    Validate text input size to prevent DoS.

    Args:
        text: Input text
        field_name: Field name for error messages

    Returns:
        Original text if valid

    Raises:
        ValueError: If text exceeds limits
    """
    if not text:
        return text

    if len(text) > MAX_TEXT_INPUT_LENGTH:
        raise ValueError(
            _dual_msg(
                f"{field_name}过大。最大允许 {MAX_TEXT_INPUT_LENGTH:,} 字符，"
                f"实际 {len(text):,} 字符。",
                f"{field_name} is too large. Maximum allowed is "
                f"{MAX_TEXT_INPUT_LENGTH:,} characters, got {len(text):,} characters.",
            )
        )

    lines = text.count('\n') + 1
    if lines > MAX_TEXT_LINES:
        raise ValueError(
            _dual_msg(
                f"{field_name}行数过多。最大允许 {MAX_TEXT_LINES:,} 行，"
                f"实际 {lines:,} 行。",
                f"{field_name} has too many lines. Maximum allowed is "
                f"{MAX_TEXT_LINES:,} lines, got {lines:,} lines.",
            )
        )

    return text


# ============================================================
# Concurrent mpmath Protection
# ============================================================

# Global lock for mpmath operations (mp.dps is global state)
_mpmath_lock = threading.Lock()


def mpmath_synchronized(f):
    """
    Decorator to synchronize mpmath operations.

    Since mpmath's mp.dps is global state, concurrent modifications
    can cause race conditions. This decorator ensures thread-safety.

    Usage:
        @mpmath_synchronized
        def compute_with_precision(...):
            with _precision_guard(prec):
                ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        with _mpmath_lock:
            return f(*args, **kwargs)
    return decorated


# ============================================================
# LaTeX Content Escaping
# ============================================================

LATEX_SPECIAL_CHARS = {
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
    '\\': r'\textbackslash{}',
}


def latex_escape(text: str) -> str:
    """
    Escape special LaTeX characters to prevent injection.

    Args:
        text: Raw text that may contain special chars

    Returns:
        LaTeX-safe text
    """
    if not isinstance(text, str):
        text = str(text)

    # Sort by length descending to handle multi-char sequences first
    for char, escaped in sorted(LATEX_SPECIAL_CHARS.items(), key=lambda x: -len(x[0])):
        text = text.replace(char, escaped)

    return text


# ============================================================
# Environment Configuration
# ============================================================

def get_config_value(key: str, default=None, type_=str):
    """
    Get configuration value from environment with type coercion.

    Args:
        key: Environment variable name
        default: Default value if not set
        type_: Type to coerce to (str, int, bool)

    Returns:
        Configuration value with correct type
    """
    value = os.environ.get(key)

    if value is None:
        return default

    if type_ == bool:
        return value.lower() in ('true', '1', 'yes', 'on')

    if type_ == int:
        try:
            return int(value)
        except ValueError:
            logger_obj = current_app.logger if has_app_context() else logging.getLogger(__name__)
            logger_obj.warning(f"Invalid int for {key}: {value}, using default {default}")
            return default

    return value


def configure_app_security(app):
    """
    Configure Flask app with security best practices.

    Args:
        app: Flask application instance
    """
    # Content size limits
    app.config['MAX_CONTENT_LENGTH'] = get_config_value(
        'DATALAB_MAX_CONTENT_LENGTH',
        MAX_FILE_SIZE,
        int
    )

    # Session security
    app.config['SESSION_COOKIE_SECURE'] = get_config_value(
        'DATALAB_COOKIE_SECURE',
        False,  # Default False for local dev, should be True for HTTPS
        bool
    )
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # CSRF cookie (double-submit) for robustness in environments where session cookies
        # may not persist (e.g. Secure cookie on http). This keeps form CSRF working.
        try:
            csrf_token = session.get('csrf_token')
            if csrf_token:
                forwarded_proto = (request.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip().lower()
                is_secure = bool(request.is_secure or forwarded_proto == 'https')
                response.set_cookie(
                    CSRF_COOKIE_NAME,
                    csrf_token,
                    secure=is_secure,
                    httponly=True,
                    samesite='Lax',
                    path='/',
                )
        except Exception:
            # Never block a response due to cookie-setting issues.
            pass
        return response

    # Error handlers to prevent info leakage
    def _normalize_lang(raw: str | None) -> str | None:
        if not raw:
            return None
        value = raw.strip().lower()
        if value in {"zh", "zh-cn", "zh_cn", "cn"}:
            return "zh"
        if value in {"en", "en-us", "en_us"}:
            return "en"
        return None

    def _contains_cjk(text: str) -> bool:
        # Rough check for CJK Unified Ideographs.
        return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))

    def _get_request_lang(default: str = "zh") -> str:
        # Priority: query param > cookie > Accept-Language > default.
        query_lang = _normalize_lang(request.args.get("lang"))
        if query_lang:
            return query_lang
        cookie_lang = _normalize_lang(request.cookies.get("datalab_lang"))
        if cookie_lang:
            return cookie_lang
        header = (request.headers.get("Accept-Language") or "").lower()
        if header.startswith("en"):
            return "en"
        if header.startswith("zh"):
            return "zh"
        return default

    def _prefers_json_response() -> bool:
        # API endpoints always respond with JSON.
        if (request.path or "").startswith("/api/"):
            return True
        best = request.accept_mimetypes.best_match(["text/html", "application/json"])
        return best == "application/json"

    @app.errorhandler(400)
    def bad_request(e):
        app.logger.warning(f"400 Bad Request: {e.description} from {request.remote_addr}")
        lang = _get_request_lang()
        desc = str(getattr(e, "description", "") or "")
        if "CSRF" in desc:
            message = (
                "CSRF验证失败。请刷新页面后重试。"
                if lang == "zh"
                else "CSRF validation failed. Please refresh and try again."
            )
        elif lang == "en":
            message = desc if desc and not _contains_cjk(desc) else "Bad request."
        else:
            message = desc or "请求参数错误"
        if _prefers_json_response():
            return {"error": message}, 400
        title = "请求失败" if lang == "zh" else "Request failed"
        back_text = "返回" if lang == "zh" else "Back"
        return render_template(
            "http_error.html",
            active_page=None,
            title=title,
            message=message,
            back_url=request.path or "/",
            back_text=back_text,
        ), 400

    @app.errorhandler(404)
    def not_found(e):
        lang = _get_request_lang()
        message = "未找到请求的资源" if lang == "zh" else "The requested resource was not found."
        if _prefers_json_response():
            return {"error": message}, 404
        title = "页面不存在" if lang == "zh" else "Page not found"
        back_text = "返回" if lang == "zh" else "Back"
        return render_template(
            "http_error.html",
            active_page=None,
            title=title,
            message=message,
            back_url="/",
            back_text=back_text,
        ), 404

    @app.errorhandler(413)
    def too_large(e):
        lang = _get_request_lang()
        limit_mb = MAX_FILE_SIZE // (1024 * 1024)
        message = (
            f"上传文件过大。最大允许 {limit_mb}MB。"
            if lang == "zh"
            else f"Uploaded file is too large. Maximum allowed is {limit_mb}MB."
        )
        if _prefers_json_response():
            return {"error": message}, 413
        title = "上传失败" if lang == "zh" else "Upload failed"
        back_text = "返回" if lang == "zh" else "Back"
        return render_template(
            "http_error.html",
            active_page=None,
            title=title,
            message=message,
            back_url=request.path or "/",
            back_text=back_text,
        ), 413

    @app.errorhandler(500)
    def internal_error(e):
        # Log full error server-side, but don't expose to client
        app.logger.error(f"500 Internal Error: {e}", exc_info=True)
        lang = _get_request_lang()
        message = (
            "服务器内部错误。请联系管理员。"
            if lang == "zh"
            else "Internal server error. Please contact the administrator."
        )
        if _prefers_json_response():
            return {"error": message}, 500
        title = "服务器错误" if lang == "zh" else "Server error"
        back_text = "返回" if lang == "zh" else "Back"
        return render_template(
            "http_error.html",
            active_page=None,
            title=title,
            message=message,
            back_url="/",
            back_text=back_text,
        ), 500

    app.logger.info("Security configuration applied")
