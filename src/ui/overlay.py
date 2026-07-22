"""
Heuristic Shadow Agent - Authorization Overlay Widget
Floating desktop overlay for showing automation proposals and requesting user consent.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QRect
from PySide6.QtGui import QFont, QColor, QPalette

logger = logging.getLogger(__name__)


class AutomationOverlay(QWidget):
    """
    Floating overlay panel that appears when a new automation script
    is ready for user review and authorization.

    Features:
    - Semi-transparent borderless window
    - Shows workflow steps
    - View/edit/approve/dismiss actions
    - Auto-dimisses after timeout
    """

    approved = Signal(dict)
    dismissed = Signal(dict)
    edit_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._pattern_data: Optional[dict] = None
        self._auto_close_timer: Optional[QTimer] = None

        self._setup_ui()
        logger.info("AutomationOverlay initialized.")

    def _setup_ui(self) -> None:
        """Build the overlay widget UI."""
        self.setFixedSize(420, 320)

        # Main container with rounded corners
        container = QFrame(self)
        container.setGeometry(0, 0, 420, 320)
        container.setStyleSheet("""
            QFrame#overlayContainer {
                background-color: #1e1e2e;
                border: 2px solid #7c3aed;
                border-radius: 16px;
            }
        """)
        container.setObjectName("overlayContainer")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QLabel("Automation Discovered")
        header.setStyleSheet(
            "color: #a78bfa; font-size: 16px; font-weight: bold;"
        )
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Pattern name
        self._name_label = QLabel("Loading...")
        self._name_label.setStyleSheet("color: #e0e0e0; font-size: 13px;")
        self._name_label.setWordWrap(True)
        layout.addWidget(self._name_label)

        # Confidence bar
        self._confidence_label = QLabel("Confidence: 0%")
        self._confidence_label.setStyleSheet(
            "color: #a78bfa; font-size: 11px;"
        )
        layout.addWidget(self._confidence_label)

        # Steps preview
        self._steps_text = QTextEdit()
        self._steps_text.setReadOnly(True)
        self._steps_text.setMaximumHeight(120)
        self._steps_text.setStyleSheet("""
            QTextEdit {
                background-color: #2d2d3f;
                color: #cccccc;
                border: 1px solid #3f3f5c;
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        layout.addWidget(self._steps_text)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        approve_btn = QPushButton("Approve & Run")
        approve_btn.setStyleSheet(self._btn_style("#7c3aed", "#8b5cf6"))
        approve_btn.clicked.connect(self._on_approve)
        btn_layout.addWidget(approve_btn)

        view_btn = QPushButton("View Script")
        view_btn.setStyleSheet(self._btn_style("#4f46e5", "#6366f1"))
        view_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(view_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setStyleSheet(self._btn_style("#374151", "#4b5563"))
        dismiss_btn.clicked.connect(self._on_dismiss)
        btn_layout.addWidget(dismiss_btn)

        layout.addLayout(btn_layout)

        # Hint
        hint = QLabel("This overlay will auto-close in 60 seconds")
        hint.setStyleSheet("color: #666666; font-size: 10px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    @staticmethod
    def _btn_style(bg: str, hover: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {bg};
            }}
        """

    # ------------------------------------------------------------------
    # Show / Hide
    # ------------------------------------------------------------------

    def show_for_pattern(self, pattern: dict) -> None:
        """
        Show the overlay for a specific pattern.
        Positions near the bottom-right of the screen.
        """
        self._pattern_data = pattern

        # Update content
        name = pattern.get("pattern_name", "Unnamed Pattern")
        self._name_label.setText(name)

        conf = pattern.get("confidence_score", 0)
        self._confidence_label.setText(f"Confidence: {conf:.0%}")

        # Parse and show steps
        try:
            import json
            seq = json.loads(pattern.get("sequence_json", "[]"))
            steps = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(seq[:8]))
            if len(seq) > 8:
                steps += f"\n  ... (+{len(seq) - 8} more steps)"
            self._steps_text.setPlainText(steps)
        except Exception:
            self._steps_text.setPlainText("Could not parse steps.")

        # Position at bottom-right
        screen = self.screen().availableGeometry()
        x = screen.right() - self.width() - 20
        y = screen.bottom() - self.height() - 20
        self.move(x, y)

        self.show()
        self.raise_()

        # Auto-close timer
        if self._auto_close_timer:
            self._auto_close_timer.stop()
        self._auto_close_timer = QTimer()
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self._on_dismiss)
        self._auto_close_timer.start(60000)  # 60 seconds

        logger.info(f"Overlay shown for pattern: {name}")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_approve(self) -> None:
        """User approved the automation."""
        if self._pattern_data:
            logger.info(f"Pattern approved: {self._pattern_data.get('pattern_hash', '?')}")
            self.approved.emit(self._pattern_data)
        self._cleanup_and_hide()

    def _on_edit(self) -> None:
        """User wants to view/edit before approving."""
        if self._pattern_data:
            logger.info(f"Pattern edit requested: {self._pattern_data.get('pattern_hash', '?')}")
            self.edit_requested.emit(self._pattern_data)
        self._cleanup_and_hide()

    def _on_dismiss(self) -> None:
        """User dismissed or auto-timeout."""
        if self._pattern_data:
            logger.info(f"Pattern dismissed: {self._pattern_data.get('pattern_hash', '?')}")
            self.dismissed.emit(self._pattern_data)
        self._cleanup_and_hide()

    def _cleanup_and_hide(self) -> None:
        """Stop timer and hide the overlay."""
        if self._auto_close_timer:
            self._auto_close_timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    # Window positioning
    # ------------------------------------------------------------------

    def move_to_mouse(self) -> None:
        """Reposition overlay near the current mouse cursor."""
        from PySide6.QtGui import QCursor
        cursor_pos = QCursor.pos()
        screen = self.screen().availableGeometry()

        x = cursor_pos.x() + 20
        y = cursor_pos.y() + 20

        # Keep within screen bounds
        if x + self.width() > screen.right():
            x = cursor_pos.x() - self.width() - 20
        if y + self.height() > screen.bottom():
            y = cursor_pos.y() - self.height() - 20

        self.move(max(0, x), max(0, y))
