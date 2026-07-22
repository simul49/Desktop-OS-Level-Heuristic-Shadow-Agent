"""
Heuristic Shadow Agent - Centralized Configuration
Loads from .env file with sensible defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration singleton for the Heuristic Shadow Agent."""

    # ---- Database ----
    DB_NAME = os.getenv("DB_NAME", "HeuristicShadow")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))

    @classmethod
    def get_db_url(cls) -> str:
        return (
            f"mysql+pymysql://{cls.DB_USER}:{cls.DB_PASSWORD}"
            f"@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"
            f"?charset=utf8mb4"
        )

    # Fallback SQLite when MySQL is unavailable
    SQLITE_FALLBACK_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "heuristic_shadow.db"
    )

    # ---- AI Providers (Fallback Chain: DeepSeek -> Qwen -> Hunyuan) ----
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_ALT_API_KEY = os.getenv("DEEPSEEK_ALT_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
    HUNYUAN_API_KEY = os.getenv("HUNYUAN_API_KEY", "")

    # ---- Pattern Mining ----
    PATTERN_CONFIDENCE_THRESHOLD = float(
        os.getenv("PATTERN_CONFIDENCE_THRESHOLD", "0.75")
    )
    PATTERN_MIN_FREQUENCY = int(os.getenv("PATTERN_MIN_FREQUENCY", "3"))
    PATTERN_MAX_SEQUENCE_LENGTH = int(os.getenv("PATTERN_MAX_SEQUENCE_LENGTH", "10"))
    PATTERN_MIN_SEQUENCE_LENGTH = int(os.getenv("PATTERN_MIN_SEQUENCE_LENGTH", "3"))
    ROLLING_WINDOW_HOURS = int(os.getenv("ROLLING_WINDOW_HOURS", "24"))

    # ---- OCR ----
    OCR_ENGINE = os.getenv("OCR_ENGINE", "easyocr")
    OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "en,ch_sim").split(",")

    # ---- Privacy ----
    PRIVACY_BLOCKED_APPS = [
        app.strip().lower()
        for app in os.getenv("PRIVACY_BLOCKED_APPS", "").split(",")
        if app.strip()
    ]
    PRIVACY_MASK_PASSWORD_FIELDS = (
        os.getenv("PRIVACY_MASK_PASSWORD_FIELDS", "true").lower() == "true"
    )
    PRIVACY_AUTO_PAUSE_ON_SECURE_DESKTOP = (
        os.getenv("PRIVACY_AUTO_PAUSE_ON_SECURE_DESKTOP", "true").lower() == "true"
    )

    # ---- Sandbox ----
    SANDBOX_DRY_RUN_ENABLED = (
        os.getenv("SANDBOX_DRY_RUN_ENABLED", "true").lower() == "true"
    )
    SANDBOX_TIMEOUT_SECONDS = int(os.getenv("SANDBOX_TIMEOUT_SECONDS", "30"))

    # ---- Application ----
    APP_NAME = "Heuristic Shadow"
    APP_VERSION = "1.0.0"
    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "scripts", "generated"
    )
    LOG_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "logs"
    )

    # ---- Privacy: Password field window title keywords ----
    PASSWORD_TITLE_KEYWORDS = [
        "password", "login", "sign in", "sign-in", "credentials",
        "authentication", "verify", "2fa", "mfa", "passcode",
        "pin", "secret", "token",
    ]

    # ---- Privacy: Sensitive process name patterns ----
    SENSITIVE_PROCESS_KEYWORDS = [
        "bank", "paypal", "stripe", "coinbase", "binance",
        "metamask", "ledger", "trezor", "authy", "duo",
    ]


# Ensure directories exist
os.makedirs(Config.DATA_DIR, exist_ok=True)
os.makedirs(Config.SCRIPTS_DIR, exist_ok=True)
os.makedirs(Config.LOG_DIR, exist_ok=True)
