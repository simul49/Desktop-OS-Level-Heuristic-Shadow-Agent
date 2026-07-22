#!/usr/bin/env python3
"""
Heuristic Shadow Agent - Main Entry Point
Desktop/OS-Level autonomous agent for workflow observation & automation.

Usage:
    python main.py                    # Start with GUI (system tray)
    python main.py --no-gui           # Start headless (background service)
    python main.py --mine-only        # Run pattern mining once and exit
    python main.py --health           # Run health checks and exit
"""

import argparse
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from src.db.database import db_manager


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging with console and file handlers."""
    log_format = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(log_format)
    console.setLevel(level)

    # File handler
    log_file = os.path.join(Config.LOG_DIR, "heuristic_shadow.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    for noisy in ("PIL", "easyocr", "httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def init_database() -> bool:
    """Initialize the database connection and schema."""
    logger = logging.getLogger(__name__)
    try:
        db_manager.initialize()
        if db_manager.is_using_fallback:
            logger.warning(
                "Using SQLite fallback. To use MySQL, ensure the service is running "
                f"on {Config.DB_HOST}:{Config.DB_PORT}."
            )
        else:
            logger.info("MySQL database connected successfully.")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def run_headless() -> None:
    """Run the agent without GUI (background service mode)."""
    logger = logging.getLogger(__name__)
    logger.info("Starting Heuristic Shadow in headless mode...")

    from src.core.listener import OSEventListener
    from src.core.pattern_miner import PatternMiner
    from src.ai.script_generator import ScriptGenerator

    listener = OSEventListener()
    miner = PatternMiner()
    script_gen = ScriptGenerator()

    listener.start()

    import time
    try:
        while True:
            time.sleep(300)  # Every 5 minutes
            patterns = miner.mine_patterns()
            if patterns:
                logger.info(f"Discovered {len(patterns)} patterns.")
                for p in patterns:
                    if p.get("confidence", 0) >= 0.85:
                        script_gen.generate_script(p, dry_run=False)
    except KeyboardInterrupt:
        logger.info("Shutting down headless mode...")
        listener.stop()
        logger.info("Goodbye.")


def run_mine_only() -> None:
    """Run pattern mining once and print results."""
    logger = logging.getLogger(__name__)
    logger.info("Running pattern mining (one-shot)...")

    from src.core.pattern_miner import PatternMiner
    from src.ai.script_generator import ScriptGenerator

    miner = PatternMiner()
    script_gen = ScriptGenerator()

    patterns = miner.mine_patterns()

    if not patterns:
        print("\n" + "=" * 60)
        print("  No workflow patterns discovered yet.")
        print("  Keep using your desktop applications to build up event data,")
        print("  then run mining again.")
        print("=" * 60)
        return

    print("\n" + "=" * 60)
    print(f"  Discovered {len(patterns)} workflow patterns!")
    print("=" * 60)

    for i, p in enumerate(patterns, 1):
        print(f"\n  --- Pattern {i} ---")
        print(f"  Name:       {p.get('pattern_name', '?')}")
        print(f"  Confidence: {p.get('confidence', 0):.1%}")
        print(f"  Frequency:  {p.get('frequency', 0)}x")
        print(f"  Steps:      {len(p.get('sequence', []))}")

        if p.get("confidence", 0) >= Config.PATTERN_CONFIDENCE_THRESHOLD:
            print(f"  [ABOVE THRESHOLD - Generating script...]")
            code = script_gen.generate_script(p, dry_run=False)
            if code:
                print(f"  Script generated: {len(code)} chars")
            else:
                print(f"  Script generation failed.")

    miner_stats = miner.get_statistics()
    print(f"\n  Total patterns in DB: {miner_stats.get('total_patterns', 0)}")
    print(f"  Ready for automation: {miner_stats.get('ready', 0)}")
    print(f"  Average confidence:   {miner_stats.get('avg_confidence', 0):.2%}")
    print("=" * 60)


def run_health_check() -> None:
    """Run comprehensive health checks."""
    logger = logging.getLogger(__name__)
    print("\n" + "=" * 60)
    print(f"  {Config.APP_NAME} v{Config.APP_VERSION} - Health Check")
    print("=" * 60)

    # 1. Database
    print("\n[1/4] Database Connection...")
    try:
        healthy = db_manager.health_check()
        db_type = "SQLite (fallback)" if db_manager.is_using_fallback else "MySQL"
        print(f"  Status: {'OK' if healthy else 'FAILED'} ({db_type})")
    except Exception as e:
        print(f"  Status: ERROR - {e}")

    # 2. AI Providers
    print("\n[2/4] AI Provider Health...")
    try:
        from src.ai.llm_client import LLMClient
        llm = LLMClient()
        results = llm.health_check()
        for provider, result in results.items():
            status = result.get("status", "?")
            icon = "OK" if status == "healthy" else "FAIL"
            extra = f" - {result.get('error', '')}" if status != "healthy" else ""
            print(f"  {provider:12s}: {icon}{extra}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 3. OCR Engine
    print("\n[3/4] OCR Engine...")
    try:
        from src.core.ocr_engine import OCREngine
        ocr = OCREngine()
        status = ocr.get_status()
        print(f"  Ready: {status['ready']}")
        print(f"  Languages: {status['languages']}")
        if status.get("error"):
            print(f"  Warning: {status['error']}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # 4. Windows API
    print("\n[4/4] Windows API Availability...")
    try:
        import win32gui
        import win32process
        print("  win32gui:      OK")
        print("  win32process:  OK")
    except ImportError:
        print("  PyWin32 not installed (window tracking limited)")

    try:
        import psutil
        print("  psutil:        OK")
    except ImportError:
        print("  psutil not installed (process info limited)")

    try:
        from pynput import mouse, keyboard
        print("  pynput:        OK")
    except ImportError:
        print("  pynput not installed (event monitoring unavailable)")

    print("\n" + "=" * 60)
    print("  Health check complete.")
    print("=" * 60 + "\n")


def run_gui() -> int:
    """Run the full GUI application with system tray."""
    logger = logging.getLogger(__name__)
    logger.info("Starting Heuristic Shadow with GUI...")

    from src.ui.tray import TrayApplication

    app = TrayApplication()
    return app.run()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description=f"{Config.APP_NAME} - Desktop Automation Observer & Executor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                  Start with system tray GUI
  python main.py --no-gui         Run as background service (no GUI)
  python main.py --mine-only      Run pattern mining once and exit
  python main.py --health         Run health checks and exit
  python main.py -v               Enable verbose logging
        """,
    )

    parser.add_argument(
        "--no-gui", action="store_true",
        help="Run in headless mode without GUI",
    )
    parser.add_argument(
        "--mine-only", action="store_true",
        help="Run pattern mining once and print results",
    )
    parser.add_argument(
        "--health", action="store_true",
        help="Run health checks for all components",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)

    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info(f"{Config.APP_NAME} v{Config.APP_VERSION} starting...")
    logger.info(f"Database: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
    logger.info(f"AI Providers: DeepSeek -> Qwen -> Hunyuan (fallback chain)")
    logger.info(f"Pattern Threshold: {Config.PATTERN_CONFIDENCE_THRESHOLD}")
    logger.info("=" * 50)

    # Initialize database
    if not init_database():
        logger.critical("Cannot initialize database. Exiting.")
        return 1

    # Determine mode
    if args.health:
        run_health_check()
        return 0

    if args.mine_only:
        run_mine_only()
        return 0

    if args.no_gui:
        run_headless()
        return 0

    # Default: GUI mode
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
