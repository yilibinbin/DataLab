from __future__ import annotations

from app_web.security import get_config_value


def test_get_config_value_int_invalid_without_app_context(monkeypatch):
    monkeypatch.setenv("DATALAB_TEST_INT", "not-an-int")
    assert get_config_value("DATALAB_TEST_INT", 123, int) == 123
