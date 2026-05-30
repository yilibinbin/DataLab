"""First-run tutorial overlay (Phase 6 #27).

Shows a transient QWidget over the main window on first launch,
walking through the three primary workflows (extrapolation, error
propagation, curve fitting). The ``tutorial_seen`` flag in
SettingsStore suppresses the overlay on every subsequent launch.

Design goals:
- Non-modal: clicking outside dismisses the overlay. The tutorial
  must never trap a user who knows what they're doing.
- Keyboard-dismissible: Escape always dismisses.
- Bilingual: reuses ``_dual_msg`` for all text so the tutorial
  respects the app's current language setting.
- Persistence-safe: a crash mid-tutorial must not leave the user
  stuck in a perpetual tutorial loop. The ``tutorial_seen`` flag
  is set as soon as the first step is dismissed, not when the
  entire walkthrough completes.
- Widget-only, no windows: a floating QDialog would trigger the
  Qt platform plugin's focus-stealing warnings. An overlay
  QWidget parented to the main window is lighter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

__all__ = [
    "KEY_TUTORIAL_SEEN",
    "TUTORIAL_STEPS",
    "TutorialOverlay",
    "TutorialStep",
    "should_show_tutorial",
    "mark_tutorial_seen",
]

_logger = logging.getLogger(__name__)

# SettingsStore key controlling whether the tutorial runs on next
# launch. Namespaced under Preferences/ so it's allowlisted in the
# SettingsStore validator.
KEY_TUTORIAL_SEEN = "Preferences/tutorial_seen"


@dataclass(frozen=True)
class TutorialStep:
    """One step in the first-run walkthrough.

    Text is stored as ``"zh / en"`` so the overlay can pick the
    active language via ``_dual_msg``-style parsing.
    """

    title_dual: str
    body_dual: str
    # Optional widget anchor: if the calling code knows the relevant
    # QWidget (e.g. the "Load data" button), the overlay can point
    # an arrow at it. Kept as a string key for now; resolution to
    # the actual widget is the caller's responsibility.
    anchor_id: Optional[str] = None


TUTORIAL_STEPS: list[TutorialStep] = [
    TutorialStep(
        title_dual="欢迎使用 DataLab / Welcome to DataLab",
        body_dual=(
            "一款高精度科学计算工具,支持外推、误差传递和曲线拟合。 / "
            "A high-precision scientific tool for sequence extrapolation, "
            "error propagation, and curve fitting."
        ),
    ),
    TutorialStep(
        title_dual="第 1 步:选择模式 / Step 1: Choose a mode",
        body_dual=(
            "左侧面板顶部的下拉菜单提供三种工作流:序列外推、误差传递、"
            "曲线拟合。 / The dropdown at the top of the left panel "
            "offers three workflows: sequence extrapolation, error "
            "propagation, and curve fitting."
        ),
        anchor_id="mode_combo",
    ),
    TutorialStep(
        title_dual="第 2 步:加载数据 / Step 2: Load data",
        body_dual=(
            "粘贴 Excel/CSV 数据或从文件加载。支持美式和欧式数字格式。"
            " / Paste Excel/CSV data or load from a file. US and EU "
            "number formats are both supported."
        ),
        anchor_id="manual_table",
    ),
    TutorialStep(
        title_dual="第 3 步:查看结果 / Step 3: Review results",
        body_dual=(
            "右侧面板显示图表、LaTeX 代码和 PDF 预览。每次计算的结果都会"
            "保留历史记录。 / The right panel shows the plot, LaTeX "
            "output, and inline PDF preview. Each computation keeps a "
            "history for easy comparison."
        ),
        anchor_id="result_plot",
    ),
    TutorialStep(
        title_dual="完成! / Done!",
        body_dual=(
            "可以随时通过帮助菜单重新打开本教程。 / "
            "You can reopen this tutorial from the Help menu at any time."
        ),
    ),
]


def _split_dual(text: str, lang: str) -> str:
    """Split a ``"zh / en"`` string into the active-language half."""
    if " / " in text:
        zh, en = text.split(" / ", 1)
        return en.strip() if lang == "en" else zh.strip()
    return text


def should_show_tutorial(store) -> bool:
    """Consult the SettingsStore for the tutorial_seen flag."""
    try:
        return store.load_int(
            KEY_TUTORIAL_SEEN, default=0, min_val=0, max_val=1
        ) == 0
    except Exception as exc:  # noqa: BLE001
        _logger.debug("should_show_tutorial read failed: %s", exc)
        return False


def mark_tutorial_seen(store) -> None:
    """Persist the ``seen`` flag so the overlay doesn't fire again.

    Called as soon as the first step is dismissed (not when the
    walkthrough completes) — a crash mid-tutorial shouldn't trap
    the user in an infinite loop.
    """
    try:
        store.save_int(KEY_TUTORIAL_SEEN, 1)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("mark_tutorial_seen write failed: %s", exc)


class TutorialOverlay(QWidget):
    """Transient, bilingual overlay that walks a user through the
    first-run workflow.

    Emits:
        dismissed: when the user closes the overlay (via Esc, click
            outside, "Skip", or completing the last step).
    """

    dismissed = Signal()

    def __init__(
        self,
        steps: Optional[list[TutorialStep]] = None,
        language: str = "zh",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._steps = steps if steps is not None else TUTORIAL_STEPS
        if not self._steps:
            raise ValueError("TutorialOverlay requires at least one step")
        if language not in ("zh", "en"):
            raise ValueError(f"Unknown language {language!r}; expected zh or en")
        self._lang = language
        self._step_idx = 0

        # Make the overlay semi-transparent over its parent. We don't
        # use Qt.Popup — popups dismiss on any click anywhere, which
        # defeats the "click outside to dismiss" contract (outside =
        # outside the dialog box, not outside the whole window).
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("""
            TutorialOverlay {
                background: rgba(0, 0, 0, 120);
            }
            QWidget#card {
                background: white;
                border-radius: 10px;
            }
        """)

        self._card = QWidget(self)
        self._card.setObjectName("card")
        self._card.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet("font-size: 16pt; font-weight: 600;")
        card_layout.addWidget(self._title)

        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setStyleSheet("font-size: 11pt; color: #333;")
        self._body.setMinimumWidth(420)
        card_layout.addWidget(self._body)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._skip_btn = QPushButton()
        self._skip_btn.setText(
            "跳过" if self._lang == "zh" else "Skip"
        )
        self._skip_btn.clicked.connect(self._dismiss)
        self._prev_btn = QPushButton()
        self._prev_btn.setText(
            "上一步" if self._lang == "zh" else "Back"
        )
        self._prev_btn.clicked.connect(self._prev_step)
        self._next_btn = QPushButton()
        self._next_btn.clicked.connect(self._next_step)
        button_row.addWidget(self._skip_btn)
        button_row.addWidget(self._prev_btn)
        button_row.addWidget(self._next_btn)
        card_layout.addLayout(button_row)

        outer = QVBoxLayout(self)
        outer.addStretch(1)
        inner = QHBoxLayout()
        inner.addStretch(1)
        inner.addWidget(self._card)
        inner.addStretch(1)
        outer.addLayout(inner)
        outer.addStretch(1)

        self._refresh_step()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_step(self) -> TutorialStep:
        return self._steps[self._step_idx]

    def step_count(self) -> int:
        return len(self._steps)

    def step_index(self) -> int:
        return self._step_idx

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt naming
        if event.key() == Qt.Key.Key_Escape:
            self._dismiss()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._next_step()
            return
        if event.key() == Qt.Key.Key_Left:
            self._prev_step()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Click outside the card → dismiss."""
        if not self._card.geometry().contains(event.pos()):
            self._dismiss()
            return
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_step(self) -> None:
        step = self._steps[self._step_idx]
        self._title.setText(_split_dual(step.title_dual, self._lang))
        self._body.setText(_split_dual(step.body_dual, self._lang))
        at_last = self._step_idx == len(self._steps) - 1
        at_first = self._step_idx == 0
        self._next_btn.setText(
            ("完成" if at_last else "下一步") if self._lang == "zh"
            else ("Finish" if at_last else "Next")
        )
        self._prev_btn.setEnabled(not at_first)

    def _next_step(self) -> None:
        if self._step_idx >= len(self._steps) - 1:
            self._dismiss()
            return
        self._step_idx += 1
        self._refresh_step()

    def _prev_step(self) -> None:
        if self._step_idx == 0:
            return
        self._step_idx -= 1
        self._refresh_step()

    def _dismiss(self) -> None:
        self.dismissed.emit()
        self.close()
