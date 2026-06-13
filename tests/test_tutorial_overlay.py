"""Phase 6 #27 — tutorial overlay regression tests.

Pins:
- Step navigation (next / prev / first / last)
- ``dismissed`` signal semantics
- Bilingual label selection
- should_show_tutorial / mark_tutorial_seen round-trip
- Constructor validation (empty steps, unknown language)
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import Any, Dict  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


class _FakeQSettings:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self._data: Dict[str, Any] = {}

    def value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def setValue(self, key: str, value: Any) -> None:  # noqa: N802
        self._data[key] = value

    def remove(self, key: str) -> None:
        self._data.pop(key, None)

    def sync(self) -> None:
        pass

    def clear(self) -> None:
        self._data.clear()

    def status(self):
        from PySide6.QtCore import QSettings

        return QSettings.Status.NoError


@pytest.fixture
def _store():
    from shared.settings_store import SettingsStore

    return SettingsStore(store=_FakeQSettings())


def test_default_steps_are_loaded(_app):
    from app_desktop.tutorial_overlay import TUTORIAL_STEPS, TutorialOverlay

    overlay = TutorialOverlay()
    assert overlay.step_count() == len(TUTORIAL_STEPS)


def test_constructor_rejects_empty_steps(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay

    with pytest.raises(ValueError):
        TutorialOverlay(steps=[])


def test_constructor_rejects_unknown_language(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay

    with pytest.raises(ValueError):
        TutorialOverlay(language="fr")


def test_next_step_advances(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay

    overlay = TutorialOverlay()
    assert overlay.step_index() == 0
    overlay._next_step()
    assert overlay.step_index() == 1


def test_prev_step_at_first_is_noop(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay

    overlay = TutorialOverlay()
    overlay._prev_step()
    assert overlay.step_index() == 0


def test_next_step_at_last_dismisses(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay, TutorialStep

    steps = [
        TutorialStep(title_dual="a / a", body_dual="x / x"),
        TutorialStep(title_dual="b / b", body_dual="y / y"),
    ]
    overlay = TutorialOverlay(steps=steps)
    fired = []
    overlay.dismissed.connect(lambda: fired.append(True))
    overlay._next_step()  # → idx 1 (last)
    overlay._next_step()  # → should dismiss
    assert fired == [True]


def test_dismissed_signal_fires_on_skip(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay

    overlay = TutorialOverlay()
    fired = []
    overlay.dismissed.connect(lambda: fired.append(True))
    overlay._dismiss()
    assert fired == [True]


def test_chinese_language_picks_chinese_label(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay, TutorialStep

    step = TutorialStep(title_dual="你好 / Hello", body_dual="世界 / World")
    overlay = TutorialOverlay(steps=[step], language="zh")
    assert "你好" in overlay._title.text()
    assert "世界" in overlay._body.text()


def test_english_language_picks_english_label(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay, TutorialStep

    step = TutorialStep(title_dual="你好 / Hello", body_dual="世界 / World")
    overlay = TutorialOverlay(steps=[step], language="en")
    assert overlay._title.text() == "Hello"
    assert overlay._body.text() == "World"


def test_non_dual_text_passes_through(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay, TutorialStep

    step = TutorialStep(title_dual="standalone", body_dual="text")
    overlay = TutorialOverlay(steps=[step])
    assert overlay._title.text() == "standalone"
    assert overlay._body.text() == "text"


def test_should_show_tutorial_true_when_unset(_store):
    from app_desktop.tutorial_overlay import should_show_tutorial

    assert should_show_tutorial(_store) is True


def test_should_show_tutorial_false_when_seen(_store):
    from app_desktop.tutorial_overlay import (
        mark_tutorial_seen,
        should_show_tutorial,
    )

    mark_tutorial_seen(_store)
    assert should_show_tutorial(_store) is False


def test_mark_tutorial_seen_is_idempotent(_store):
    from app_desktop.tutorial_overlay import (
        mark_tutorial_seen,
        should_show_tutorial,
    )

    mark_tutorial_seen(_store)
    mark_tutorial_seen(_store)
    assert should_show_tutorial(_store) is False


def test_finish_button_label_on_last_step(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay, TutorialStep

    steps = [
        TutorialStep(title_dual="a / a", body_dual="x / x"),
        TutorialStep(title_dual="b / b", body_dual="y / y"),
    ]
    overlay = TutorialOverlay(steps=steps, language="en")
    overlay._next_step()
    assert overlay._next_btn.text() == "Finish"


def test_back_button_disabled_on_first_step(_app):
    from app_desktop.tutorial_overlay import TutorialOverlay

    overlay = TutorialOverlay()
    assert overlay._prev_btn.isEnabled() is False
    overlay._next_step()
    assert overlay._prev_btn.isEnabled() is True


def test_tutorial_overlay_does_not_embed_targeted_qss() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "tutorial_overlay.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_snippets = {
        """
            TutorialOverlay {
                background: rgba(0, 0, 0, 120);
            }
            QWidget#card {
                background: white;
                border-radius: 10px;
            }
        """,
        "font-size: 16pt; font-weight: 600;",
        "font-size: 11pt; color: #333;",
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert literals.isdisjoint(forbidden_snippets)
