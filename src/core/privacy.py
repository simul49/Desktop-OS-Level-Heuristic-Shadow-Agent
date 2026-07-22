"""
Heuristic Shadow Agent - Privacy Filter
Enforces local privacy by detecting sensitive windows, password fields,
and blocked applications. Prevents sensitive data from being logged.
"""

import re
import logging
from config import Config

logger = logging.getLogger(__name__)


class PrivacyFilter:
    """
    Real-time privacy enforcement layer.
    Masks or blocks event capture for sensitive contexts.
    """

    def __init__(self):
        self.blocked_apps = set(Config.PRIVACY_BLOCKED_APPS)
        self.password_keywords = Config.PASSWORD_TITLE_KEYWORDS
        self.sensitive_keywords = Config.SENSITIVE_PROCESS_KEYWORDS
        self.mask_passwords = Config.PRIVACY_MASK_PASSWORD_FIELDS
        self.is_paused = False

        logger.info(
            f"PrivacyFilter initialized. Blocked apps: {len(self.blocked_apps)}, "
            f"Password keywords: {len(self.password_keywords)}"
        )

    def is_sensitive(self, window_title: str, process_name: str) -> bool:
        """
        Determine if the current context is sensitive.
        Returns True if data capture should be suppressed.
        """
        if self.is_paused:
            logger.debug("Privacy filter paused.")
            return False

        title_lower = window_title.lower() if window_title else ""
        proc_lower = process_name.lower() if process_name else ""

        # Check blocked applications
        app_name = proc_lower.replace(".exe", "")
        if app_name in self.blocked_apps:
            logger.debug(f"Blocked app detected: {app_name}")
            return True

        # Check against sensitive process keywords
        for kw in self.sensitive_keywords:
            if kw in proc_lower:
                logger.debug(f"Sensitive process keyword match: {kw}")
                return True

        # Check for password/login/sensitive window titles
        if self.mask_passwords:
            for kw in self.password_keywords:
                if kw in title_lower:
                    logger.debug(f"Password field keyword match: {kw}")
                    return True

        # Check for common password field patterns in titles
        sensitive_patterns = [
            r"type\s+(your\s+)?password",
            r"enter\s+(your\s+)?password",
            r"master\s+password",
            r"security\s+code",
            r"verification\s+code",
        ]
        for pattern in sensitive_patterns:
            if re.search(pattern, title_lower):
                return True

        return False

    def mask_process(self, process_name: str) -> str:
        """Return a masked version of the process name for logging."""
        if not process_name:
            return "unknown"
        app_name = process_name.replace(".exe", "")
        if app_name in self.blocked_apps:
            return "[BLOCKED_APP]"
        return f"[FILTERED:{hash(process_name) % 10000:04d}]"

    def sanitize_text(self, text: str) -> str:
        """Remove potential sensitive patterns from text."""
        if not text:
            return text

        # Mask common PII patterns
        sanitized = text

        # Email addresses
        sanitized = re.sub(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            '[EMAIL]',
            sanitized
        )

        # Credit card patterns (basic)
        sanitized = re.sub(
            r'\b(?:\d[ -]*?){13,16}\b',
            '[CARD]',
            sanitized
        )

        # Phone numbers (basic)
        sanitized = re.sub(
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            '[PHONE]',
            sanitized
        )

        return sanitized

    def pause(self) -> None:
        """Temporarily pause privacy filtering."""
        self.is_paused = True
        logger.info("Privacy filter paused.")

    def resume(self) -> None:
        """Resume privacy filtering."""
        self.is_paused = False
        logger.info("Privacy filter resumed.")

    def add_blocked_app(self, app_name: str) -> None:
        """Add an application to the blocked list at runtime."""
        self.blocked_apps.add(app_name.lower())
        logger.info(f"Added '{app_name}' to blocked applications.")

    def remove_blocked_app(self, app_name: str) -> None:
        """Remove an application from the blocked list."""
        self.blocked_apps.discard(app_name.lower())
        logger.info(f"Removed '{app_name}' from blocked applications.")

    @property
    def active_blocked_count(self) -> int:
        return len(self.blocked_apps)
