#!/usr/bin/env python3
"""
Secure LaTeX Compilation Module
================================

Provides hardened LaTeX compilation with:
- Engine whitelist enforcement
- Resource limits (CPU, memory, file size)
- Timeout protection
- Shell escape prevention

Author: Security Hardening Patch 2025-12-12
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

# Resource limits (POSIX only)
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False


# Configuration
LATEX_TIMEOUT = int(os.environ.get('DATALAB_LATEX_TIMEOUT', '30'))  # seconds
LATEX_MAX_CPU_TIME = int(os.environ.get('DATALAB_LATEX_MAX_CPU', '60'))  # seconds
LATEX_MAX_MEMORY = int(os.environ.get('DATALAB_LATEX_MAX_MEM', '512')) * 1024 * 1024  # bytes
LATEX_MAX_FILE_SIZE = int(os.environ.get('DATALAB_LATEX_MAX_FILE', '50')) * 1024 * 1024  # bytes
# NOTE:
# RLIMIT_NPROC limits the total number of processes for the user.
# A too-small value can break XeLaTeX/LuaLaTeX on desktop machines where the user
# already has many running processes, leading to errors like:
#   "! I can't write on file `fitting.pdf'."
# Keep a conservative default that still prevents runaway forking but avoids
# breaking normal GUI usage. Users can override via DATALAB_LATEX_MAX_PROC.
LATEX_MAX_PROCESSES = int(os.environ.get('DATALAB_LATEX_MAX_PROC', '2048'))


# Patterns for the ``validate_latex_content`` shell-escape pre-filter. Compiled
# once at import time so the per-request cost is a list iteration over already-
# compiled regexes. The TeX tokenizer accepts arbitrary whitespace between
# control-sequence names and their arguments, so a literal substring match on
# ``\write18`` would miss ``\write 18``, ``\write\n18``, ``\immediate \write 18``,
# etc. Each entry is ``(label, compiled_pattern)`` where ``label`` is the
# canonical short form used in warning messages.
_DANGEROUS_LATEX_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    (r"\immediate\write18", re.compile(r"\\immediate\s*\\write\s*18\b")),
    (r"\write18", re.compile(r"\\write\s*18\b")),
    (r"\openout", re.compile(r"\\openout\b")),
    (r"\input{|", re.compile(r"\\input\s*\{\s*\|")),
)


def _preexec_limit_resources():
    """
    Set resource limits for LaTeX subprocess (POSIX only).

    This prevents:
    - Infinite loops (CPU time limit)
    - Memory bombs (memory limit)
    - Fork bombs (process limit)
    - Large file writes (file size limit)
    """
    if not HAS_RESOURCE:
        return

    def _set_soft_limit(resource_name, soft_limit: int):
        """Best-effort soft limit clamp; never writes to stderr (runs in child pre-exec)."""
        try:
            _current_soft, current_hard = resource.getrlimit(resource_name)
            if current_hard != resource.RLIM_INFINITY:
                soft_limit = min(int(soft_limit), int(current_hard))
            resource.setrlimit(resource_name, (int(soft_limit), current_hard))
        except Exception:
            # Some systems do not support all limits (or disallow changes); ignore silently.
            return

    _set_soft_limit(resource.RLIMIT_CPU, LATEX_MAX_CPU_TIME)
    _set_soft_limit(resource.RLIMIT_AS, LATEX_MAX_MEMORY)
    _set_soft_limit(resource.RLIMIT_FSIZE, LATEX_MAX_FILE_SIZE)
    _set_soft_limit(resource.RLIMIT_NPROC, LATEX_MAX_PROCESSES)


def compile_latex_safe(
    tex_text: str,
    engine: str,
    warnings: list[str],
    label: str = "document"
) -> bytes | None:
    """
    Safely compile LaTeX to PDF with hardened security.

    Security measures:
    1. Engine whitelist validation (done before calling this)
    2. Explicit -no-shell-escape to prevent command execution
    3. Timeout to prevent hanging
    4. Resource limits (CPU, memory, processes) on POSIX
    5. Temporary directory isolation

    Args:
        tex_text: LaTeX source code
        engine: LaTeX engine (must be pre-validated)
        warnings: List to append warnings to
        label: Document label for error messages

    Returns:
        PDF bytes on success, None on failure
    """
    from .security import validate_latex_engine

    # Double-check engine whitelist (defense in depth)
    try:
        engine = validate_latex_engine(engine)
    except ValueError as e:
        # Keep warnings bilingual so the UI can switch without falling back to Chinese in EN mode.
        msg = str(e) or ""
        en = msg if msg and not _contains_cjk(msg) else f"Unsupported LaTeX engine: {engine}."
        zh = msg if msg else f"不支持的 LaTeX 引擎: {engine}。"
        warnings.append(f"{zh} / {en}")
        return None

    # Pre-subprocess content filter (defense-in-depth alongside -no-shell-escape).
    # Blocks \write18 and path-traversal \input before we ever spawn the LaTeX
    # engine. If this returns not safe, we refuse to compile.
    is_safe, content_warnings = validate_latex_content(tex_text)
    if content_warnings:
        warnings.extend(content_warnings)
    if not is_safe:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / f"{label}.tex"
        tex_path.write_text(tex_text, encoding="utf-8")

        # Build command with security flags
        cmd = [
            engine,
            "-interaction=nonstopmode",  # Don't stop for user input
            "-halt-on-error",             # Stop on first error
            "-no-shell-escape",           # CRITICAL: Disable \write18 and shell commands
            tex_path.name
        ]

        try:
            # Prepare subprocess kwargs
            proc_kwargs = {
                'cwd': tmpdir,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'timeout': LATEX_TIMEOUT,
                'text': True,
            }

            # Add resource limits on POSIX systems
            if HAS_RESOURCE and hasattr(subprocess, 'Popen'):
                proc_kwargs['preexec_fn'] = _preexec_limit_resources

            subprocess.run(cmd, check=True, **proc_kwargs)

            pdf_path = tex_path.with_suffix(".pdf")
            if not pdf_path.exists():
                warnings.append(
                    f"{label} LaTeX 编译未生成 PDF。 / {label} LaTeX compilation did not produce a PDF."
                )
                return None

            return pdf_path.read_bytes()

        except subprocess.TimeoutExpired:
            warnings.append(
                f"{label} LaTeX 编译超时（>{LATEX_TIMEOUT}秒）。可能是无限循环或过于复杂的文档。"
                f" / {label} LaTeX compilation timed out (>{LATEX_TIMEOUT}s). The document may be too complex or stuck in a loop."
            )
            return None

        except FileNotFoundError:
            warnings.append(
                f"未找到 LaTeX 引擎 {engine}。请确认已安装 TeX Live 或 MiKTeX。"
                f" / LaTeX engine not found: {engine}. Please make sure TeX Live or MiKTeX is installed."
            )
            return None

        except subprocess.CalledProcessError as exc:
            # Extract meaningful error from LaTeX log
            error_msg = _extract_latex_error(exc.stderr or exc.stdout)
            en_detail = error_msg if error_msg and not _contains_cjk(error_msg) else "See logs for details."
            warnings.append(
                f"{label} LaTeX 编译失败: {error_msg} / {label} LaTeX compilation failed: {en_detail}"
            )
            return None

        except Exception as exc:
            msg = str(exc) or ""
            en_detail = msg if msg and not _contains_cjk(msg) else "See logs for details."
            zh_detail = msg or "未知错误"
            warnings.append(f"{label} LaTeX 编译失败: {zh_detail} / {label} LaTeX compilation failed: {en_detail}")
            return None


def _extract_latex_error(log: str) -> str:
    """
    Extract meaningful error message from LaTeX log.

    Args:
        log: LaTeX compilation log

    Returns:
        Cleaned error message
    """
    if not log:
        return "Unknown error"

    # Look for common error patterns
    lines = log.splitlines()

    for i, line in enumerate(lines):
        if line.startswith("!"):
            # LaTeX error line, get next few lines for context
            error_lines = [line] + lines[i+1:min(i+4, len(lines))]
            return " ".join(error_lines)[:200]

    # Fallback: return last few lines
    return " ".join(lines[-5:])[:200]


def validate_latex_content(tex_text: str) -> tuple[bool, list[str]]:
    """
    Validate LaTeX content for suspicious patterns.

    This is a heuristic check for obviously malicious content.
    Not a substitute for -no-shell-escape!

    Args:
        tex_text: LaTeX source code

    Returns:
        (is_safe, warnings) tuple
    """
    warnings = []

    for label, pattern in _DANGEROUS_LATEX_PATTERNS:
        if pattern.search(tex_text):
            warnings.append(
                f"检测到危险的 LaTeX 命令: {label}，已阻止。"
                f" / Dangerous LaTeX command detected: {label}. Blocked."
            )
            return False, warnings

    # Check for suspicious file operations (path traversal / absolute paths /
    # any path separator). Each document compiles in its own isolated temp
    # directory, so legitimate TeX needs only same-directory includes —
    # subdirectory references in web input are treated as unsafe to avoid
    # sneaky traversal patterns (e.g. "foo/../../etc/passwd" that collapse
    # after normalization). See compile_latex_safe() for the temp-dir setup.
    for raw in re.findall(r"\\(?:input|include)\s*\{([^}]*)\}", tex_text):
        candidate = (raw or "").strip()
        if not candidate:
            continue
        if (
            candidate.startswith(("/", "\\"))  # absolute paths
            or ":" in candidate  # Windows drive letters / URL-like
            or ".." in candidate  # parent traversal
            or "/" in candidate  # any path separator (subdir includes disallowed)
            or "\\" in candidate  # any path separator (subdir includes disallowed)
        ):
            warnings.append(
                "检测到不安全的文件包含路径（仅允许同目录下的纯文件名包含）。"
                " / Unsafe file-include path detected "
                "(only same-directory, bare-filename includes are permitted in the web sandbox)."
            )
            return False, warnings

    return True, warnings


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")
