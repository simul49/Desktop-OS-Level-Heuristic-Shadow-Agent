"""
Heuristic Shadow Agent - Sandboxed Script Executor
Validates and safely executes generated automation scripts.
Includes dry-run, syntax checking, and fail-safe enforcement.
"""

import ast
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional

from config import Config
from src.db.database import db_manager
from src.db.models import AutomationScript

logger = logging.getLogger(__name__)


class ScriptValidationError(Exception):
    """Raised when a generated script fails validation."""
    pass


class SandboxExecutor:
    """
    Validates and executes automation scripts in a controlled environment.
    Enforces safety constraints before allowing execution.
    """

    REQUIRED_SAFETY_CHECKS = [
        "pyautogui.FAILSAFE",
        "try",
        "except",
    ]

    FORBIDDEN_PATTERNS = [
        "os.system(",
        "subprocess.call(",
        "eval(",
        "exec(",
        "__import__",
        "shutil.rmtree",
        "os.remove(",
        "os.unlink(",
    ]

    def __init__(self):
        self.dry_run_enabled = Config.SANDBOX_DRY_RUN_ENABLED
        self.timeout = Config.SANDBOX_TIMEOUT_SECONDS
        self._running_script: Optional[str] = None
        self._execution_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_script(self, code: str) -> tuple:
        """
        Validate a generated script for safety and syntax.

        Returns:
            (is_valid: bool, message: str)
        """
        if not code or not code.strip():
            return False, "Script is empty."

        # Check syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        # Check for forbidden patterns
        code_lower = code.lower()
        for pattern in self.FORBIDDEN_PATTERNS:
            if pattern.lower() in code_lower:
                return False, (
                    f"Forbidden pattern detected: '{pattern}'. "
                    f"Scripts must not use system-level operations."
                )

        # Check required safety checks
        for check in self.REQUIRED_SAFETY_CHECKS:
            if check not in code:
                return False, f"Missing required safety check: '{check}'"

        # Check that FAILSAFE is set to True
        if "pyautogui.FAILSAFE = True" not in code and "pyautogui.FAILSAFE=True" not in code:
            return False, "pyautogui.FAILSAFE must be explicitly set to True."

        # Verify imports are reasonable
        try:
            tree = ast.parse(code)
            imports = [
                node.names[0].name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
            ]
            imports_from = [
                f"{node.module}.{alias.name}"
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
            ]
            all_imports = imports + imports_from

            # Check for suspicious imports
            suspicious = {"os", "subprocess", "shutil", "socket", "requests"}
            found_suspicious = [i for i in all_imports if i.split(".")[0] in suspicious]
            if found_suspicious:
                return False, f"Suspicious imports detected: {found_suspicious}"

        except SyntaxError:
            pass  # Already caught above

        return True, "Script validation passed."

    # ------------------------------------------------------------------
    # Dry run (analysis only)
    # ------------------------------------------------------------------

    def dry_run(self, code: str) -> dict:
        """
        Analyze a script without executing it.
        Returns analysis results: parsed steps, estimated duration, etc.
        """
        try:
            tree = ast.parse(code)

            # Count PyAutoGUI actions
            action_count = 0
            actions = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            if node.func.value.id in ("pyautogui", "pag"):
                                action_count += 1
                                actions.append(node.func.attr)

            # Count sleep/wait calls
            sleep_calls = 0
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                        if name in ("sleep", "wait"):
                            sleep_calls += 1

            # Estimate duration (rough)
            estimated_duration = action_count * 0.5 + sleep_calls * 0.5

            return {
                "valid": True,
                "action_count": action_count,
                "actions": list(set(actions)),
                "sleep_calls": sleep_calls,
                "estimated_duration_seconds": estimated_duration,
                "line_count": len(code.splitlines()),
            }

        except SyntaxError as e:
            return {"valid": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_script(
        self,
        script_id: int,
        dry_run_only: bool = None,
    ) -> dict:
        """
        Execute a script by ID from the database.
        Runs validation first, then optional dry-run, then actual execution.

        Returns execution result dict.
        """
        if dry_run_only is None:
            dry_run_only = self.dry_run_enabled

        try:
            with db_manager.get_session() as session:
                script = (
                    session.query(AutomationScript).filter_by(id=script_id).first()
                )
                if not script:
                    return {"success": False, "error": f"Script {script_id} not found."}
                code = script.python_code

        except Exception as e:
            return {"success": False, "error": f"Database error: {e}"}

        # Validate
        valid, msg = self.validate_script(code)
        if not valid:
            return {"success": False, "error": f"Validation failed: {msg}"}

        # Dry run analysis
        analysis = self.dry_run(code)

        if dry_run_only:
            return {
                "success": True,
                "executed": False,
                "dry_run": True,
                "analysis": analysis,
            }

        # Actual execution
        result = self._run_script(code, script_id, script.script_name)

        # Update execution count
        if result.get("success"):
            try:
                with db_manager.get_session() as session:
                    s = session.query(AutomationScript).filter_by(id=script_id).first()
                    if s:
                        s.execution_count = (s.execution_count or 0) + 1
                        s.last_executed = __import__("datetime").datetime.utcnow()
            except Exception:
                pass

        return result

    def _run_script(self, code: str, script_id: int, script_name: str) -> dict:
        """
        Execute the script in a subprocess with timeout.
        """
        # Write to temp file
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="heuristic_shadow_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(code)

            logger.info(f"Executing script '{script_name}' (ID: {script_id})...")

            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=os.path.dirname(tmp_path),
            )

            success = result.returncode == 0
            output = result.stdout.strip()[:5000]
            error_output = result.stderr.strip()[:5000]

            if success:
                logger.info(f"Script '{script_name}' completed successfully.")
            else:
                logger.warning(
                    f"Script '{script_name}' failed (exit={result.returncode}): {error_output[:200]}"
                )

            return {
                "success": success,
                "executed": True,
                "exit_code": result.returncode,
                "stdout": output,
                "stderr": error_output,
                "script_id": script_id,
                "script_name": script_name,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "executed": True,
                "error": f"Script timed out after {self.timeout}s.",
            }
        except Exception as e:
            return {
                "success": False,
                "executed": False,
                "error": f"Execution error: {e}",
            }
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Background execution helpers
    # ------------------------------------------------------------------

    def execute_async(self, script_id: int, callback=None) -> None:
        """Execute a script asynchronously in a background thread."""
        if self._execution_thread and self._execution_thread.is_alive():
            logger.warning("Another script is already running.")
            return

        def _run():
            result = self.execute_script(script_id, dry_run_only=False)
            if callback:
                callback(result)

        self._execution_thread = threading.Thread(
            target=_run, name="ScriptExecutor", daemon=True
        )
        self._execution_thread.start()

    @property
    def is_executing(self) -> bool:
        return self._execution_thread is not None and self._execution_thread.is_alive()

    def get_last_result(self) -> Optional[dict]:
        """Get the result of the last execution (if available)."""
        return getattr(self, "_last_result", None)
