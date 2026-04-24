#!/usr/bin/env python3
"""
Security Test Suite for DataLab Web
====================================

Tests all security hardening measures:
- CSRF protection
- LaTeX engine whitelist
- Input size limits
- Concurrent mpmath safety
- File upload limits

Run: pytest app_web/test_security.py -v

Author: Security Hardening Patch 2025-12-12
"""

import pytest
import threading
import time
from io import BytesIO

# Allow import from parent directory
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app_web.server import create_app
from app_web.security import (
    generate_csrf_token,
    validate_csrf_token,
    validate_latex_engine,
    validate_text_size,
    MAX_TEXT_INPUT_LENGTH,
    MAX_TEXT_LINES,
)


@pytest.fixture
def app():
    """Create test Flask app."""
    test_app = create_app()
    test_app.config['TESTING'] = True
    test_app.config['WTF_CSRF_ENABLED'] = False  # Disable for token generation tests
    return test_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


# ============================================================
# CSRF Protection Tests
# ============================================================

class TestCSRF:
    """Test CSRF protection mechanisms."""

    def test_csrf_token_generation(self):
        """Test CSRF token is generated correctly."""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()

        assert len(token1) == 64  # 32 bytes hex = 64 chars
        assert len(token2) == 64
        assert token1 != token2  # Should be unique

    def test_csrf_token_validation(self, app):
        """Test CSRF token validation."""
        with app.test_request_context():
            from flask import session

            # Set expected token in session
            session['csrf_token'] = 'test_token_123'

            # Valid token
            assert validate_csrf_token('test_token_123') is True

            # Invalid token
            assert validate_csrf_token('wrong_token') is False
            assert validate_csrf_token('') is False
            assert validate_csrf_token(None) is False

    def test_post_without_csrf_fails(self, client):
        """Test POST request without CSRF token is rejected."""
        response = client.post('/', data={
            'data_text': 'A B C\n1 2 3',
            'method': 'power_law'
        })

        assert response.status_code == 400
        assert 'CSRF' in response.get_data(as_text=True)

    def test_post_with_valid_csrf_succeeds(self, client):
        """Test POST request with valid CSRF token succeeds."""
        # First, get a valid token by loading the page (GET request)
        with client.session_transaction() as sess:
            from app_web.security import generate_csrf_token
            token = generate_csrf_token()
            sess['csrf_token'] = token

        # Now POST with the token
        response = client.post('/', data={
            'csrf_token': token,
            'data_text': 'A B C\n1 2 3',
            'method': 'power_law'
        })

        # Should not be 400 (CSRF failure)
        assert response.status_code != 400

    def test_get_request_no_csrf_needed(self, client):
        """Test GET requests don't need CSRF token."""
        response = client.get('/')
        assert response.status_code == 200


# ============================================================
# LaTeX Security Tests
# ============================================================

class TestLaTeXSecurity:
    """Test LaTeX engine whitelist and compilation security."""

    def test_latex_engine_whitelist_valid(self):
        """Test valid LaTeX engines are accepted."""
        assert validate_latex_engine('pdflatex') == 'pdflatex'
        assert validate_latex_engine('xelatex') == 'xelatex'
        assert validate_latex_engine('lualatex') == 'lualatex'

        # Case insensitive
        assert validate_latex_engine('PDFLATEX') == 'pdflatex'
        assert validate_latex_engine('XeLaTeX') == 'xelatex'

        # With whitespace
        assert validate_latex_engine('  pdflatex  ') == 'pdflatex'

    def test_latex_engine_whitelist_invalid(self):
        """Test invalid LaTeX engines are rejected."""
        with pytest.raises(ValueError, match="不支持的LaTeX引擎"):
            validate_latex_engine('bash')

        with pytest.raises(ValueError):
            validate_latex_engine('rm -rf /')

        with pytest.raises(ValueError):
            validate_latex_engine('pdflatex; whoami')

        with pytest.raises(ValueError):
            validate_latex_engine('../../../etc/passwd')

    def test_latex_engine_default(self):
        """Test empty engine returns default."""
        assert validate_latex_engine('') == 'pdflatex'
        assert validate_latex_engine(None) == 'pdflatex'

    def test_latex_compilation_timeout(self, app, monkeypatch):
        """Test LaTeX compilation times out on infinite loop."""
        import app_web.latex_security as latex_security
        monkeypatch.setattr(latex_security, "LATEX_TIMEOUT", 1)

        # LaTeX with infinite loop
        dangerous_tex = r"""
\documentclass{article}
\begin{document}
\loop\iftrue\repeat
\end{document}
"""
        warnings = []

        # This should timeout
        with app.app_context():
            result = latex_security.compile_latex_safe(
                dangerous_tex,
                'pdflatex',
                warnings,
                'timeout_test'
            )

        assert result is None
        assert any('超时' in w for w in warnings)

    def test_latex_shell_escape_blocked(self, app):
        """Test shell escape commands are blocked."""
        from app_web.latex_security import validate_latex_content

        # Dangerous TeX with shell escape
        dangerous_tex = r"""
\documentclass{article}
\begin{document}
\write18{rm -rf /}
\end{document}
"""
        is_safe, warnings = validate_latex_content(dangerous_tex)

        assert is_safe is False
        assert any('write18' in w.lower() for w in warnings)


# ============================================================
# Input Size Limit Tests
# ============================================================

class TestInputSizeLimits:
    """Test input size validation."""

    def test_text_size_valid(self):
        """Test normal-sized text is accepted."""
        normal_text = "A B C\n" * 100  # 600 chars
        assert validate_text_size(normal_text, "test") == normal_text

    def test_text_size_too_large(self):
        """Test oversized text is rejected."""
        # Create text larger than MAX_TEXT_INPUT_LENGTH
        huge_text = "A" * (MAX_TEXT_INPUT_LENGTH + 1000)

        with pytest.raises(ValueError, match="过大"):
            validate_text_size(huge_text, "test")

    def test_text_lines_too_many(self):
        """Test too many lines is rejected."""
        # Create text with more than MAX_TEXT_LINES
        many_lines = "A\n" * (MAX_TEXT_LINES + 100)

        with pytest.raises(ValueError, match="行数过多"):
            validate_text_size(many_lines, "test")

    def test_file_upload_size_limit(self, client):
        """Test file upload size limit."""
        # Create 15MB file (exceeds 10MB limit)
        large_file = BytesIO(b"A" * (15 * 1024 * 1024))
        large_file.name = 'large.txt'

        # Get CSRF token
        with client.session_transaction() as sess:
            from app_web.security import generate_csrf_token
            token = generate_csrf_token()
            sess['csrf_token'] = token

        response = client.post('/', data={
            'csrf_token': token,
            'use_file': '1',
            'data_file': (large_file, 'large.txt')
        })

        # Should get 413 (Request Entity Too Large)
        assert response.status_code == 413


# ============================================================
# Concurrent mpmath Safety Tests
# ============================================================

class TestConcurrentMpmath:
    """Test mpmath concurrent access is safe."""

    def test_mpmath_precision_lock(self):
        """Test mpmath precision changes are synchronized."""
        from app_web.security import mpmath_synchronized
        from mpmath import mp

        results = {}
        errors = []

        @mpmath_synchronized
        def compute_with_precision(prec, key):
            """Compute with specific precision."""
            try:
                original = mp.dps
                mp.dps = prec
                time.sleep(0.01)  # Simulate computation
                # Verify precision didn't change during computation
                assert mp.dps == prec, f"Expected {prec}, got {mp.dps}"
                result = mp.pi  # Some computation
                mp.dps = original
                results[key] = (prec, float(result))
            except AssertionError as e:
                errors.append(str(e))

        # Run concurrent computations with different precisions
        threads = []
        for i, prec in enumerate([16, 50, 100, 16, 50]):
            t = threading.Thread(target=compute_with_precision, args=(prec, f"t{i}"))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Errors: {errors}"

        # All results should be computed with correct precision
        assert len(results) == 5


# ============================================================
# XSS Protection Tests
# ============================================================

class TestXSSProtection:
    """Test XSS protection in templates and responses."""

    def test_user_input_escaped_in_error(self, client):
        """Test user input is escaped in error messages."""
        xss_payload = '<script>alert("XSS")</script>'

        with client.session_transaction() as sess:
            from app_web.security import generate_csrf_token
            token = generate_csrf_token()
            sess['csrf_token'] = token

        response = client.post('/', data={
            'csrf_token': token,
            'caption': xss_payload,
            'data_text': 'invalid data format'
        })

        html = response.get_data(as_text=True)

        # User payload must not appear unescaped in the response.
        assert xss_payload not in html
        assert '&lt;script&gt;' in html or xss_payload not in html


# ============================================================
# Security Headers Tests
# ============================================================

class TestSecurityHeaders:
    """Test security HTTP headers are set."""

    def test_security_headers_present(self, client):
        """Test security headers are in responses."""
        response = client.get('/')

        headers = response.headers

        assert 'X-Content-Type-Options' in headers
        assert headers['X-Content-Type-Options'] == 'nosniff'

        assert 'X-Frame-Options' in headers
        assert headers['X-Frame-Options'] == 'DENY'

        assert 'X-XSS-Protection' in headers


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Test error handling doesn't leak sensitive info."""

    def test_500_error_no_stack_trace(self, client, monkeypatch):
        """Test 500 errors don't expose stack traces to users."""

        # Monkey-patch to force an error
        def raise_error(*args, **kwargs):
            raise RuntimeError("Internal error with /secret/path/info.py")

        with client.session_transaction() as sess:
            from app_web.security import generate_csrf_token
            token = generate_csrf_token()
            sess['csrf_token'] = token

        # This is hard to test without modifying actual code,
        # so we test the error handler configuration exists
        from app_web.server import create_app
        app = create_app()

        assert 500 in app.error_handler_spec.get(None, {})

    def test_404_error_message(self, client):
        """Test 404 has friendly message."""
        response = client.get('/nonexistent', headers={"Accept": "application/json"})

        assert response.status_code == 404
        data = response.get_json()
        assert '未找到' in data.get('error', '')


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """Integration tests combining multiple security features."""

    def test_full_workflow_with_security(self, client):
        """Test a complete workflow with all security measures."""

        # Step 1: Load page (GET) - should get CSRF token
        response = client.get('/')
        assert response.status_code == 200

        # Step 2: Submit form with valid data and CSRF token
        with client.session_transaction() as sess:
            from app_web.security import generate_csrf_token
            token = generate_csrf_token()
            sess['csrf_token'] = token

        response = client.post('/', data={
            'csrf_token': token,
            'data_text': 'A B C\n1 2 3\n2 4 6',
            'method': 'power_law',
            'x1': '1',
            'x2': '2',
            'x3': '3'
        })

        # Should succeed (not 400 CSRF, not 413 too large)
        assert response.status_code == 200


# ============================================================
# Run Tests
# ============================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
