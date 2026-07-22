"""
Heuristic Shadow Agent - System Tray Application (PySide6)
Provides the always-available desktop interface via system tray icon.
"""

import logging
import sys
import threading
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton,
    QHBoxLayout, QListWidget, QListWidgetItem, QWidget,
    QTabWidget, QProgressBar, QGroupBox,
)
from PySide6.QtCore import QTimer, Qt, Signal, QObject
from PySide6.QtGui import QIcon, QAction, QFont

from config import Config
from core.listener import OSEventListener
from core.pattern_miner import PatternMiner
from ai.script_generator import ScriptGenerator
from sandbox.executor import SandboxExecutor

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Signals for background worker communication with UI."""
    stats_updated = Signal(dict)
    patterns_found = Signal(list)
    script_generated = Signal(str)


class TrayApplication:
    """
    System tray application providing:
    - Start/Stop monitoring controls
    - Pattern discovery status
    - Script management (view, approve, execute)
    - Quick stats display
    """

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(Config.APP_NAME)
        self.app.setApplicationVersion(Config.APP_VERSION)
        self.app.setQuitOnLastWindowClosed(False)

        self.listener = OSEventListener()
        self.miner = PatternMiner()
        self.script_gen = ScriptGenerator()
        self.executor = SandboxExecutor()

        self.signals = WorkerSignals()

        # Timers
        self._stats_timer: Optional[QTimer] = None
        self._mining_timer: Optional[QTimer] = None

        # Dialogs (keep references to prevent GC)
        self._stats_dialog: Optional[QDialog] = None
        self._scripts_dialog: Optional[QDialog] = None
        self._patterns_dialog: Optional[QDialog] = None

        self._setup_tray()
        self._setup_timers()

        logger.info("Tray application initialized.")

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        """Create and configure the system tray icon and menu."""
        self.tray = QSystemTrayIcon()
        self.tray.setToolTip(f"{Config.APP_NAME} v{Config.APP_VERSION}")

        # Try to set icon (create a simple colored icon if file doesn't exist)
        icon = self._create_icon()
        if icon:
            self.tray.setIcon(icon)

        # Build menu
        menu = QMenu()

        # Status
        self.status_action = QAction("Status: Idle")
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()

        # Controls
        self.start_action = QAction("Start Monitoring")
        self.start_action.triggered.connect(self.start_monitoring)
        menu.addAction(self.start_action)

        self.stop_action = QAction("Stop Monitoring")
        self.stop_action.triggered.connect(self.stop_monitoring)
        self.stop_action.setEnabled(False)
        menu.addAction(self.stop_action)

        menu.addSeparator()

        # Views
        stats_action = QAction("Dashboard")
        stats_action.triggered.connect(self.show_dashboard)
        menu.addAction(stats_action)

        patterns_action = QAction("Discovered Patterns")
        patterns_action.triggered.connect(self.show_patterns)
        menu.addAction(patterns_action)

        scripts_action = QAction("Automation Scripts")
        scripts_action.triggered.connect(self.show_scripts)
        menu.addAction(scripts_action)

        menu.addSeparator()

        # Mining
        mine_action = QAction("Run Pattern Mining Now")
        mine_action.triggered.connect(self.run_mining)
        menu.addAction(mine_action)
        menu.addSeparator()

        # About & Quit
        about_action = QAction("About")
        about_action.triggered.connect(self.show_about)
        menu.addAction(about_action)

        quit_action = QAction("Quit")
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

        # Show welcome message
        self.tray.showMessage(
            Config.APP_NAME,
            f"v{Config.APP_VERSION} is running.\nRight-click the tray icon for options.",
            QSystemTrayIcon.Information,
            3000,
        )

    def _create_icon(self) -> Optional[QIcon]:
        """Create a programmatic icon (purple H on transparent background)."""
        try:
            from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush
            from PySide6.QtCore import QRect

            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw a rounded rectangle background
            painter.setBrush(QBrush(QColor(99, 58, 188)))  # Purple
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRect(4, 4, 56, 56), 12, 12)

            # Draw "HS" text
            painter.setPen(QPen(QColor(255, 255, 255)))
            font = QFont("Segoe UI", 22, QFont.Bold)
            painter.setFont(font)
            painter.drawText(QRect(0, 0, 64, 64), Qt.AlignCenter, "HS")

            painter.end()
            return QIcon(pixmap)

        except Exception:
            return None

    def _setup_timers(self) -> None:
        """Setup periodic timers for stats and mining."""
        # Stats refresh every 5 seconds
        self._stats_timer = QTimer()
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(5000)

        # Pattern mining every 5 minutes
        self._mining_timer = QTimer()
        self._mining_timer.timeout.connect(self._auto_mining)
        self._mining_timer.start(5 * 60 * 1000)

    # ------------------------------------------------------------------
    # Monitoring controls
    # ------------------------------------------------------------------

    def start_monitoring(self) -> None:
        """Start the OS event listener."""
        if not self.listener.is_running:
            self.listener.start()
            self.start_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            self.status_action.setText("Status: Monitoring")
            self.tray.showMessage(
                Config.APP_NAME,
                "Event monitoring started.\nCapturing interactions for pattern discovery.",
                QSystemTrayIcon.Information,
                2000,
            )
            logger.info("Monitoring started from tray.")

    def stop_monitoring(self) -> None:
        """Stop the OS event listener."""
        if self.listener.is_running:
            self.listener.stop()
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.status_action.setText("Status: Paused")
            self.tray.showMessage(
                Config.APP_NAME,
                "Event monitoring paused.",
                QSystemTrayIcon.Information,
                2000,
            )
            logger.info("Monitoring stopped from tray.")

    # ------------------------------------------------------------------
    # Mining
    # ------------------------------------------------------------------

    def run_mining(self) -> None:
        """Manually trigger pattern mining."""
        self.tray.showMessage(
            Config.APP_NAME,
            "Running pattern mining...",
            QSystemTrayIcon.Information,
            1500,
        )

        def _mine():
            patterns = self.miner.mine_patterns()
            if patterns:
                self._auto_generate_scripts(patterns)
                self.tray.showMessage(
                    Config.APP_NAME,
                    f"Found {len(patterns)} workflow patterns! Check 'Discovered Patterns'.",
                    QSystemTrayIcon.Information,
                    4000,
                )
            else:
                self.tray.showMessage(
                    Config.APP_NAME,
                    "No new patterns discovered. Keep using your apps!",
                    QSystemTrayIcon.Information,
                    2000,
                )

        threading.Thread(target=_mine, daemon=True).start()

    def _auto_mining(self) -> None:
        """Periodic auto-mining (runs silently)."""
        try:
            patterns = self.miner.mine_patterns()
            if patterns:
                logger.info(f"Auto-mining found {len(patterns)} patterns.")
                self._auto_generate_scripts(patterns)
        except Exception as e:
            logger.error(f"Auto-mining error: {e}")

    def _auto_generate_scripts(self, patterns: list) -> None:
        """Auto-generate scripts for high-confidence patterns."""
        for pattern in patterns:
            try:
                confidence = pattern.get("confidence", 0)
                if confidence >= 0.85:
                    self.script_gen.generate_script(pattern, dry_run=False)
                    logger.info(
                        f"Auto-generated script for pattern "
                        f"'{pattern.get('pattern_name', '?')}' (confidence={confidence:.2f})"
                    )
            except Exception as e:
                logger.debug(f"Script generation skipped: {e}")

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def show_dashboard(self) -> None:
        """Show the main dashboard/status dialog."""
        if self._stats_dialog and self._stats_dialog.isVisible():
            self._stats_dialog.raise_()
            return

        dialog = QDialog()
        dialog.setWindowTitle(f"{Config.APP_NAME} - Dashboard")
        dialog.resize(500, 400)
        dialog.setMinimumSize(400, 300)

        layout = QVBoxLayout(dialog)

        # Header
        header = QLabel(f"<h2>{Config.APP_NAME} v{Config.APP_VERSION}</h2>")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Stats group
        stats_group = QGroupBox("System Status")
        stats_layout = QVBoxLayout(stats_group)

        self._stats_labels = {}
        fields = [
            ("Monitor Status", "Idle"),
            ("Events Captured", "0"),
            ("Queue Size", "0"),
            ("Patterns Discovered", "0"),
            ("Scripts Generated", "0"),
            ("Uptime", "0s"),
            ("AI Provider", "Not configured"),
        ]
        for label, default in fields:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"<b>{label}:</b>"))
            value = QLabel(default)
            row.addWidget(value)
            row.addStretch()
            stats_layout.addLayout(row)
            self._stats_labels[label] = value

        layout.addWidget(stats_group)

        # Action buttons
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_stats)
        btn_layout.addWidget(refresh_btn)
        layout.addLayout(btn_layout)

        dialog.setLayout(layout)
        self._stats_dialog = dialog
        dialog.show()
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        """Update dashboard statistics."""
        if not self._stats_dialog or not self._stats_dialog.isVisible():
            return

        try:
            listener_stats = self.listener.get_stats()
            miner_stats = self.miner.get_statistics()
            llm_stats = self.script_gen.llm.get_stats()

            stats_map = {
                "Monitor Status": "Active" if self.listener.is_running else "Paused",
                "Events Captured": str(listener_stats.get("total_events", 0)),
                "Queue Size": str(listener_stats.get("queue_size", 0)),
                "Patterns Discovered": str(miner_stats.get("total_patterns", 0)),
                "Scripts Generated": str(len(self.script_gen.get_scripts())),
                "Uptime": f"{listener_stats.get('uptime_seconds', 0):.0f}s",
                "AI Provider": ", ".join(llm_stats.get("available", ["none"])),
            }

            for label, value in stats_map.items():
                if label in self._stats_labels:
                    self._stats_labels[label].setText(value)
        except Exception as e:
            logger.debug(f"Stats refresh error: {e}")

    # ------------------------------------------------------------------
    # Patterns dialog
    # ------------------------------------------------------------------

    def show_patterns(self) -> None:
        """Show discovered patterns in a dialog."""
        patterns = self.miner.get_ready_patterns()

        dialog = QDialog()
        dialog.setWindowTitle("Discovered Workflow Patterns")
        dialog.resize(650, 450)
        dialog.setMinimumSize(500, 350)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"<b>{len(patterns)} patterns discovered</b>"))

        list_widget = QListWidget()
        for p in patterns:
            name = p.get("pattern_name", "Unknown")
            conf = p.get("confidence_score", 0)
            freq = p.get("frequency_count", 0)
            status = p.get("status", "?")
            item = QListWidgetItem(
                f"[{status.upper()}] {name} "
                f"(confidence: {conf:.2f}, frequency: {freq})"
            )
            item.setData(Qt.UserRole, p)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()

        details_btn = QPushButton("View Details")
        details_btn.clicked.connect(
            lambda: self._show_pattern_details(list_widget)
        )
        btn_layout.addWidget(details_btn)

        generate_btn = QPushButton("Generate Script")
        generate_btn.clicked.connect(
            lambda: self._generate_script_for_pattern(list_widget)
        )
        btn_layout.addWidget(generate_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.clicked.connect(
            lambda: self._dismiss_pattern(list_widget, dialog)
        )
        btn_layout.addWidget(dismiss_btn)

        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        self._patterns_dialog = dialog
        dialog.show()

    def _show_pattern_details(self, list_widget: QListWidget) -> None:
        """Show detailed view of a selected pattern."""
        item = list_widget.currentItem()
        if not item:
            return
        pattern = item.data(Qt.UserRole)

        try:
            import json
            seq = json.loads(pattern.get("sequence_json", "[]"))
            steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(seq))
        except Exception:
            steps = pattern.get("sequence_json", "")

        details = (
            f"<b>Name:</b> {pattern.get('pattern_name', 'N/A')}<br>"
            f"<b>Confidence:</b> {pattern.get('confidence_score', 0):.2%}<br>"
            f"<b>Frequency:</b> {pattern.get('frequency_count', 0)}<br>"
            f"<b>Status:</b> {pattern.get('status', 'N/A')}<br>"
            f"<b>Hash:</b> {pattern.get('pattern_hash', 'N/A')}<br><br>"
            f"<b>Sequence:</b><br><pre>{steps}</pre>"
        )

        msg = QMessageBox()
        msg.setWindowTitle("Pattern Details")
        msg.setTextFormat(Qt.RichText)
        msg.setText(details)
        msg.exec()

    def _generate_script_for_pattern(self, list_widget: QListWidget) -> None:
        """Generate automation script for selected pattern."""
        item = list_widget.currentItem()
        if not item:
            return
        pattern = item.data(Qt.UserRole)

        QMessageBox.information(
            None, "Generating",
            f"Generating automation script for:\n{pattern.get('pattern_name', 'Unknown')}\n\n"
            "This may take a moment..."
        )

        def _gen():
            code = self.script_gen.generate_script(pattern, dry_run=False)
            if code:
                self.tray.showMessage(
                    Config.APP_NAME,
                    f"Script generated: {pattern.get('pattern_name', 'Unknown')}",
                    QSystemTrayIcon.Information,
                    3000,
                )
            else:
                self.tray.showMessage(
                    Config.APP_NAME,
                    "Script generation failed. Check logs.",
                    QSystemTrayIcon.Warning,
                    3000,
                )

        threading.Thread(target=_gen, daemon=True).start()

    def _dismiss_pattern(
        self, list_widget: QListWidget, dialog: QDialog
    ) -> None:
        """Dismiss (ignore) a selected pattern."""
        item = list_widget.currentItem()
        if not item:
            return
        pattern = item.data(Qt.UserRole)
        self.miner.dismiss_pattern(pattern.get("pattern_hash", ""))
        list_widget.takeItem(list_widget.row(item))
        self.tray.showMessage(
            Config.APP_NAME,
            "Pattern dismissed.",
            QSystemTrayIcon.Information,
            2000,
        )

    # ------------------------------------------------------------------
    # Scripts dialog
    # ------------------------------------------------------------------

    def show_scripts(self) -> None:
        """Show generated automation scripts."""
        scripts = self.script_gen.get_scripts()

        dialog = QDialog()
        dialog.setWindowTitle("Automation Scripts")
        dialog.resize(700, 500)
        dialog.setMinimumSize(500, 400)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"<b>{len(scripts)} automation scripts</b>"))

        list_widget = QListWidget()
        for s in scripts:
            status = "ACTIVE" if s.get("is_active") else "inactive"
            item = QListWidgetItem(
                f"[{status}] {s.get('script_name', '?')} "
                f"(executed: {s.get('execution_count', 0)}x)"
            )
            item.setData(Qt.UserRole, s)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()

        view_btn = QPushButton("View Code")
        view_btn.clicked.connect(lambda: self._view_script(list_widget))
        btn_layout.addWidget(view_btn)

        run_btn = QPushButton("Execute")
        run_btn.clicked.connect(lambda: self._execute_script(list_widget))
        btn_layout.addWidget(run_btn)

        toggle_btn = QPushButton("Toggle Active")
        toggle_btn.clicked.connect(lambda: self._toggle_script(list_widget))
        btn_layout.addWidget(toggle_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(
            lambda: self._delete_script(list_widget, dialog)
        )
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        self._scripts_dialog = dialog
        dialog.show()

    def _view_script(self, list_widget: QListWidget) -> None:
        """View the Python code of a selected script."""
        item = list_widget.currentItem()
        if not item:
            return
        script = item.data(Qt.UserRole)

        code_dialog = QDialog()
        code_dialog.setWindowTitle(f"Script: {script.get('script_name', '?')}")
        code_dialog.resize(650, 500)

        layout = QVBoxLayout(code_dialog)

        info = QLabel(
            f"<b>{script.get('script_name', 'N/A')}</b> | "
            f"Executed: {script.get('execution_count', 0)}x | "
            f"Active: {script.get('is_active', False)}"
        )
        layout.addWidget(info)

        code_edit = QTextEdit()
        code_edit.setReadOnly(True)
        code_edit.setFont(QFont("Consolas", 10))
        code_edit.setPlainText(script.get("python_code", ""))
        layout.addWidget(code_edit)

        code_dialog.setLayout(layout)
        code_dialog.show()

    def _execute_script(self, list_widget: QListWidget) -> None:
        """Execute a selected automation script."""
        item = list_widget.currentItem()
        if not item:
            return
        script = item.data(Qt.UserRole)

        reply = QMessageBox.question(
            None,
            "Confirm Execution",
            f"Execute automation script:\n<b>{script.get('script_name', 'Unknown')}</b>?\n\n"
            f"<i>Move mouse to any screen corner to abort during execution.</i>",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        def _exec():
            result = self.executor.execute_script(script["id"], dry_run_only=False)
            if result.get("success"):
                self.tray.showMessage(
                    Config.APP_NAME,
                    f"Script executed successfully!",
                    QSystemTrayIcon.Information,
                    2000,
                )
            else:
                self.tray.showMessage(
                    Config.APP_NAME,
                    f"Script failed: {result.get('error', 'Unknown error')[:100]}",
                    QSystemTrayIcon.Warning,
                    3000,
                )

        threading.Thread(target=_exec, daemon=True).start()

    def _toggle_script(self, list_widget: QListWidget) -> None:
        """Toggle the active status of a script."""
        item = list_widget.currentItem()
        if not item:
            return
        script = item.data(Qt.UserRole)
        new_state = not script.get("is_active", False)
        self.script_gen.toggle_script_active(script["id"], new_state)

        # Refresh the list
        self.show_scripts()

    def _delete_script(self, list_widget: QListWidget, dialog: QDialog) -> None:
        """Delete a script."""
        item = list_widget.currentItem()
        if not item:
            return
        script = item.data(Qt.UserRole)
        self.script_gen.delete_script(script["id"])
        list_widget.takeItem(list_widget.row(item))

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------

    def show_about(self) -> None:
        """Show the About dialog."""
        about_text = (
            f"<h2>{Config.APP_NAME}</h2>"
            f"<p>Version {Config.APP_VERSION}</p>"
            f"<p>Desktop/OS-Level autonomous agent that observes "
            f"human-computer interactions to discover and automate "
            f"repetitive workflows.</p>"
            f"<hr>"
            f"<p><b>Core Features:</b></p>"
            f"<ul>"
            f"<li>Global event monitoring (mouse, keyboard, windows)</li>"
            f"<li>Privacy-first local data storage</li>"
            f"<li>AI-powered pattern discovery</li>"
            f"<li>Automatic PyAutoGUI script generation</li>"
            f"<li>Sandboxed execution with fail-safes</li>"
            f"</ul>"
            f"<p><b>AI Providers:</b> {', '.join(self.script_gen.llm.get_available_providers())}</p>"
        )

        QMessageBox.about(None, f"About {Config.APP_NAME}", about_text)

    # ------------------------------------------------------------------
    # Application lifecycle
    # ------------------------------------------------------------------

    def run(self) -> int:
        """Start the application event loop."""
        logger.info(f"Starting {Config.APP_NAME} v{Config.APP_VERSION}...")

        # Auto-start monitoring
        self.start_monitoring()

        return self.app.exec()

    def quit(self) -> None:
        """Graceful shutdown."""
        if self.listener.is_running:
            self.listener.stop()
        self.tray.hide()
        self.app.quit()
        logger.info(f"{Config.APP_NAME} terminated.")
