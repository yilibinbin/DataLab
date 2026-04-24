#!/usr/bin/env python3
"""
Security Patches for server.py
===============================

This file contains the modified sections of server.py with security hardening.
Apply these changes to the original server.py file.

CRITICAL CHANGES:
1. Import security modules
2. Add CSRF protection to all POST routes
3. Replace _compile_latex with compile_latex_safe
4. Add mpmath synchronization
5. Add input size validation
6. Configure app security
7. Fix debug=True issue

Author: Security Hardening Patch 2025-12-12
"""

# ============================================================
# CHANGE 1: Add imports at the top (after line 66)
# ============================================================

# ADD THESE IMPORTS:
"""
from .security import (
    csrf_protect,
    get_csrf_token,
    configure_app_security,
    validate_text_size,
    mpmath_synchronized,
    validate_latex_engine,
)
from .latex_security import compile_latex_safe
"""

# ============================================================
# CHANGE 2: Modify create_app() function (after line 108)
# ============================================================

# REPLACE:
"""
def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    # Simple secret for flash messaging; override via env in production.
    app.config["SECRET_KEY"] = os.environ.get("DATALAB_WEB_SECRET", "datalab-web-dev")
"""

# WITH:
"""
def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Security: Strong secret key (required for session/CSRF)
    secret_key = os.environ.get("DATALAB_WEB_SECRET")
    if not secret_key:
        import secrets
        secret_key = secrets.token_hex(32)
        app.logger.warning(
            "⚠️ DATALAB_WEB_SECRET not set! Using random key. "
            "Sessions will not persist across restarts!"
        )
    app.config["SECRET_KEY"] = secret_key

    # Apply security configuration
    configure_app_security(app)

    # Register CSRF token in Jinja context
    @app.context_processor
    def inject_csrf_token():
        return {'csrf_token': get_csrf_token}
"""

# ============================================================
# CHANGE 3: Add CSRF protection to all POST routes
# ============================================================

# CHANGE index() route (line 110):
"""
@app.route("/", methods=["GET", "POST"])
@csrf_protect  # ADD THIS LINE
def index():
    ...
"""

# CHANGE error() route (line 139):
"""
@app.route("/error", methods=["GET", "POST"])
@csrf_protect  # ADD THIS LINE
def error():
    ...
"""

# CHANGE fit() route (line 175):
"""
@app.route("/fit", methods=["GET", "POST"])
@csrf_protect  # ADD THIS LINE
def fit():
    ...
"""

# CHANGE stats() route (line 207):
"""
@app.route("/stats", methods=["GET", "POST"])
@csrf_protect  # ADD THIS LINE
def stats():
    ...
"""

# ============================================================
# CHANGE 4: Add input size validation to _extract_data_text
# ============================================================

# REPLACE function _extract_data_text (line 423):
"""
def _extract_data_text(form, files, allow_file: bool = True) -> str:
    if allow_file and "data_file" in files and files["data_file"]:
        file = files["data_file"]
        if getattr(file, "filename", ""):
            try:
                return file.read().decode("utf-8")
            except Exception as exc:
                raise ValueError(f"上传文件无法读取为 UTF-8 文本: {exc}") from exc
    return (form.get("data_text") or "").strip()
"""

# WITH:
"""
def _extract_data_text(form, files, allow_file: bool = True) -> str:
    if allow_file and "data_file" in files and files["data_file"]:
        file = files["data_file"]
        if getattr(file, "filename", ""):
            try:
                content = file.read().decode("utf-8")
                return validate_text_size(content, "上传文件")
            except UnicodeDecodeError as exc:
                raise ValueError(f"上传文件无法读取为 UTF-8 文本: {exc}") from exc
    text = (form.get("data_text") or "").strip()
    return validate_text_size(text, "数据输入")
"""

# ============================================================
# CHANGE 5: Same for _extract_named_text (line 435)
# ============================================================

# REPLACE:
"""
def _extract_named_text(text_field: str, file_field: str, form, files, allow_file: bool = True) -> str:
    if allow_file and file_field in files and files[file_field]:
        file = files[file_field]
        if getattr(file, "filename", ""):
            try:
                return file.read().decode("utf-8")
            except Exception as exc:
                raise ValueError(f"上传文件无法读取为 UTF-8 文本: {exc}") from exc
    return (form.get(text_field) or "").strip()
"""

# WITH:
"""
def _extract_named_text(text_field: str, file_field: str, form, files, allow_file: bool = True) -> str:
    if allow_file and file_field in files and files[file_field]:
        file = files[file_field]
        if getattr(file, "filename", ""):
            try:
                content = file.read().decode("utf-8")
                return validate_text_size(content, f"{file_field} 文件")
            except UnicodeDecodeError as exc:
                raise ValueError(f"上传文件无法读取为 UTF-8 文本: {exc}") from exc
    text = (form.get(text_field) or "").strip()
    return validate_text_size(text, text_field)
"""

# ============================================================
# CHANGE 6: DELETE _compile_latex function entirely (line 775-803)
# It is replaced by compile_latex_safe in latex_security.py
# ============================================================

# DELETE this function:
"""
def _compile_latex(tex_text: str, engine: str, warnings: list[str], label: str) -> bytes | None:
    ...  # DELETE ALL 29 LINES
"""

# ============================================================
# CHANGE 7: Update all calls to _compile_latex
# ============================================================

# IN _run_extrapolation (line 958):
# REPLACE:
"""
pdf_bytes = _compile_latex(latex_text, latex_engine, options.warnings, "extrapolation")
"""
# WITH:
"""
# Validate engine before compiling
try:
    latex_engine = validate_latex_engine(latex_engine)
except ValueError as e:
    options.warnings.append(str(e))
    pdf_bytes = None
else:
    pdf_bytes = compile_latex_safe(latex_text, latex_engine, options.warnings, "extrapolation")
"""

# IN _run_error_propagation (line 1034):
# REPLACE:
"""
pdf_bytes = _compile_latex(latex_text, latex_engine, warnings, "error")
"""
# WITH:
"""
try:
    latex_engine = validate_latex_engine(latex_engine)
except ValueError as e:
    warnings.append(str(e))
    pdf_bytes = None
else:
    pdf_bytes = compile_latex_safe(latex_text, latex_engine, warnings, "error")
"""

# IN _run_statistics (line 1783):
# REPLACE:
"""
pdf_bytes = _compile_latex(latex_text, latex_engine, warnings, "stats")
"""
# WITH:
"""
try:
    latex_engine = validate_latex_engine(latex_engine)
except ValueError as e:
    warnings.append(str(e))
    pdf_bytes = None
else:
    pdf_bytes = compile_latex_safe(latex_text, latex_engine, warnings, "stats")
"""

# ============================================================
# CHANGE 8: Add mpmath synchronization to all _run_* functions
# ============================================================

# WRAP these functions with @mpmath_synchronized:

# BEFORE (line 893):
"""
def _run_extrapolation(data_text: str, form) -> ExtrapolationResultBundle:
"""
# AFTER:
"""
@mpmath_synchronized
def _run_extrapolation(data_text: str, form) -> ExtrapolationResultBundle:
"""

# BEFORE (line 981):
"""
def _run_error_propagation(data_text: str, constants_text: str, form) -> ErrorPropagationBundle:
"""
# AFTER:
"""
@mpmath_synchronized
def _run_error_propagation(data_text: str, constants_text: str, form) -> ErrorPropagationBundle:
"""

# BEFORE (line 1171):
"""
def _run_fit(data_text: str, form) -> FitResultBundle:
"""
# AFTER:
"""
@mpmath_synchronized
def _run_fit(data_text: str, form) -> FitResultBundle:
"""

# BEFORE (line 1742):
"""
def _run_statistics(data_text: str, form) -> StatsResultBundle:
"""
# AFTER:
"""
@mpmath_synchronized
def _run_statistics(data_text: str, form) -> StatsResultBundle:
"""

# ============================================================
# CHANGE 9: Fix debug=True security issue (line 1846-1848)
# ============================================================

# REPLACE:
"""
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
"""

# WITH:
"""
if __name__ == "__main__":
    # Read configuration from environment
    host = os.environ.get("DATALAB_HOST", "127.0.0.1")
    port = int(os.environ.get("DATALAB_PORT", "8000"))
    debug = os.environ.get("DATALAB_DEBUG", "").lower() in ("1", "true", "yes")

    if debug:
        app.logger.warning("⚠️ DEBUG模式已开启！仅用于开发环境，生产部署请使用 gunicorn。")

    # threaded=False: Avoid mpmath mp.dps race conditions in multi-threaded mode
    # For production, use gunicorn with sync workers instead
    app.run(
        host=host,
        port=port,
        debug=debug,
        threaded=False  # Important for mpmath safety
    )
"""

# ============================================================
# END OF PATCHES
# ============================================================

"""
APPLYING THE PATCHES:

Option 1: Manual application
- Open server.py in editor
- Find each section by line numbers
- Copy-paste the WITH code

Option 2: Use patch file (if created)
- Save diff as server.patch
- Apply: patch -p1 < server.patch

Option 3: Automated script
- See apply_security_patches.py

VERIFICATION:
After applying, run:
  python3 -m py_compile app_web/server.py  # Check syntax
  pytest app_web/test_security.py          # Run security tests
  python3 app_web/server.py                # Start and test manually
"""
