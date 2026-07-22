"""
Heuristic Shadow Agent - OS Event Listener
Captures global mouse, keyboard, and window focus events via pynput + win32.
Runs as a lightweight background thread with event queuing to DB.
"""

import logging
import threading
import time
import hashlib
import json
from datetime import datetime
from queue import Queue
from typing import Optional

try:
    import win32gui
    import win32process
    import psutil
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from pynput import mouse, keyboard

from core.privacy import PrivacyFilter
from core.ocr_engine import OCREngine
from db.database import db_manager
from db.models import RawEvent
from config import Config

logger = logging.getLogger(__name__)


class OSEventListener:
    """
    Global OS event listener capturing:
    - Mouse clicks (position, button)
    - Keyboard presses (sanitized)
    - Window focus changes (process name, title)
    - Periodic OCR snapshots on app switches
    """

    def __init__(self):
        self._running = False
        self._mouse_listener: Optional[mouse.Listener] = None
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._event_queue = Queue(maxsize=5000)
        self._db_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None

        self.privacy = PrivacyFilter()
        self.ocr_engine: Optional[OCREngine] = None

        self._current_app: str = ""
        self._current_title: str = ""
        self._last_ocr_time: float = 0.0
        self._ocr_cooldown: float = 2.0  # seconds between OCR captures

        self._event_count: int = 0
        self._start_time: float = 0.0

        logger.info("OSEventListener initialized.")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start all listener threads."""
        if self._running:
            logger.warning("Listener already running.")
            return

        self._running = True
        self._start_time = time.time()

        # Start the DB writer thread
        self._db_thread = threading.Thread(
            target=self._db_writer_loop, name="DBWriter", daemon=True
        )
        self._db_thread.start()

        # Start the watchdog thread (periodic window title polling)
        self._watchdog_thread = threading.Thread(
            target=self._window_watchdog_loop, name="WindowWatchdog", daemon=True
        )
        self._watchdog_thread.start()

        # Start mouse listener
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
        )
        self._mouse_listener.start()

        # Start keyboard listener
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
        )
        self._keyboard_listener.start()

        # Initialize OCR engine (lazy)
        self.ocr_engine = OCREngine()

        logger.info("OSEventListener started - mouse, keyboard, window monitoring active.")

    def stop(self) -> None:
        """Gracefully stop all listeners."""
        self._running = False

        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()

        # Drain remaining events
        self._flush_events()

        logger.info(f"OSEventListener stopped. Total events captured: {self._event_count}")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def uptime_seconds(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        """Mouse click event handler."""
        if not self._running:
            return False
        if not pressed:
            return True  # Only record press-down events

        btn_name = str(button).replace("Button.", "")
        process, title = self._get_active_window_info()
        is_sensitive = self.privacy.is_sensitive(title, process)

        event_data = {
            "timestamp": datetime.utcnow(),
            "event_type": "click",
            "process_name": process if not is_sensitive else self.privacy.mask_process(process),
            "window_title": title if not is_sensitive else "[REDACTED]",
            "x_coord": x,
            "y_coord": y,
            "key_name": btn_name,
            "is_sensitive": is_sensitive,
        }

        # Trigger OCR on click if cooldown passed
        if time.time() - self._last_ocr_time > self._ocr_cooldown and not is_sensitive:
            self._last_ocr_time = time.time()
            ocr_text = self.ocr_engine.capture_region_text(x, y) if self.ocr_engine else ""
            if ocr_text:
                event_data["ocr_text"] = ocr_text

        self._queue_event(event_data)
        return True

    def _on_press(self, key) -> None:
        """Keyboard press event handler."""
        if not self._running:
            return False

        try:
            key_str = key.char if hasattr(key, 'char') and key.char else str(key)
        except AttributeError:
            key_str = str(key)

        process, title = self._get_active_window_info()
        is_sensitive = self.privacy.is_sensitive(title, process)

        event_data = {
            "timestamp": datetime.utcnow(),
            "event_type": "keypress",
            "process_name": process if not is_sensitive else self.privacy.mask_process(process),
            "window_title": title if not is_sensitive else "[REDACTED]",
            "x_coord": None,
            "y_coord": None,
            "key_name": key_str,
            "is_sensitive": is_sensitive,
        }
        self._queue_event(event_data)
        return True

    # ------------------------------------------------------------------
    # Window monitoring
    # ------------------------------------------------------------------

    def _window_watchdog_loop(self) -> None:
        """Periodically poll for active window changes."""
        while self._running:
            try:
                process, title = self._get_active_window_info()
                current_key = f"{process}:{title}"

                if current_key != f"{self._current_app}:{self._current_title}":
                    is_sensitive = self.privacy.is_sensitive(title, process)
                    event_data = {
                        "timestamp": datetime.utcnow(),
                        "event_type": "app_switch",
                        "process_name": process if not is_sensitive else self.privacy.mask_process(process),
                        "window_title": title if not is_sensitive else "[REDACTED]",
                        "x_coord": None,
                        "y_coord": None,
                        "is_sensitive": is_sensitive,
                    }

                    # OCR on app switch
                    if not is_sensitive and self.ocr_engine:
                        ocr_text = self.ocr_engine.capture_full_screen_text()
                        if ocr_text:
                            event_data["ocr_text"] = ocr_text

                    self._queue_event(event_data)
                    self._current_app = process
                    self._current_title = title
                    self._last_ocr_time = time.time()

            except Exception as e:
                logger.debug(f"Window watchdog error: {e}")

            time.sleep(0.5)  # Poll every 500ms

    @staticmethod
    def _get_active_window_info() -> tuple:
        """Get (process_name, window_title) of the foreground window."""
        if not HAS_WIN32:
            return ("unknown", "unknown")

        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                process_name = proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = f"pid:{pid}"

            return (process_name, title)
        except Exception:
            return ("unknown", "unknown")

    # ------------------------------------------------------------------
    # Event queuing & DB persistence
    # ------------------------------------------------------------------

    def _queue_event(self, event_data: dict) -> None:
        """Enqueue event for async DB write."""
        try:
            self._event_queue.put_nowait(event_data)
            self._event_count += 1
        except Exception:
            logger.debug("Event queue full, dropping event.")

    def _db_writer_loop(self) -> None:
        """Background thread that flushes queued events to DB in batches."""
        batch = []
        batch_size = 50
        last_flush = time.time()

        while self._running or not self._event_queue.empty():
            try:
                event = self._event_queue.get(timeout=1.0)
                batch.append(event)
            except Exception:
                pass  # Timeout, flush what we have

            if len(batch) >= batch_size or (batch and time.time() - last_flush > 5.0):
                self._persist_batch(batch)
                batch.clear()
                last_flush = time.time()

        # Final flush
        if batch:
            self._persist_batch(batch)

    def _persist_batch(self, batch: list) -> None:
        """Write a batch of events to the database."""
        if not batch:
            return
        try:
            with db_manager.get_session() as session:
                for data in batch:
                    event = RawEvent(
                        timestamp=data["timestamp"],
                        event_type=data["event_type"],
                        process_name=data.get("process_name", "")[:256],
                        window_title=data.get("window_title", "")[:512],
                        x_coord=data.get("x_coord"),
                        y_coord=data.get("y_coord"),
                        key_name=data.get("key_name", "")[:64],
                        ocr_text=data.get("ocr_text", "")[:2000],
                        is_sensitive=data.get("is_sensitive", False),
                    )
                    session.add(event)
            logger.debug(f"Persisted {len(batch)} events to DB.")
        except Exception as e:
            logger.error(f"Failed to persist events batch: {e}")

    def _flush_events(self) -> None:
        """Force flush remaining events synchronously."""
        batch = []
        while not self._event_queue.empty():
            try:
                batch.append(self._event_queue.get_nowait())
            except Exception:
                break
        if batch:
            self._persist_batch(batch)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return current listener statistics."""
        return {
            "running": self._running,
            "total_events": self._event_count,
            "queue_size": self._event_queue.qsize(),
            "uptime_seconds": self.uptime_seconds,
            "current_app": self._current_app,
            "current_title": self._current_title[:100] if self._current_title else "",
            "using_win32": HAS_WIN32,
            "ocr_available": self.ocr_engine is not None and self.ocr_engine.ready,
        }
