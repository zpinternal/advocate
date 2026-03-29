from __future__ import annotations

import subprocess
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request


bp = Blueprint("terminal", __name__, url_prefix="/terminal")
BASE_DIR = Path.cwd().resolve()


def _safe_cwd(cwd: str | None) -> Path:
    if not cwd:
        return BASE_DIR

    target = Path(cwd)
    if not target.is_absolute():
        target = (BASE_DIR / cwd).resolve()
    else:
        target = target.resolve()

    if not str(target).startswith(str(BASE_DIR)):
        raise ValueError("cwd escapes base directory")
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError("cwd does not exist")
    return target


@bp.get("/ui")
def terminal_ui():
    return render_template("terminal/dashboard.html", title="Terminal")


@bp.post("/exec")
def execute_command():
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    timeout_seconds = int(payload.get("timeout_seconds", 20))
    cwd_value = payload.get("cwd")
    if not command:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "command is required",
                    },
                }
            ),
            422,
        )

    try:
        cwd = _safe_cwd(cwd_value)
    except ValueError as exc:
        return (
            jsonify({"ok": False, "error": {"code": "BAD_CWD", "message": str(exc)}}),
            400,
        )
    except FileNotFoundError as exc:
        return (
            jsonify({"ok": False, "error": {"code": "NOT_FOUND", "message": str(exc)}}),
            404,
        )

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(1, min(300, timeout_seconds)),
        )
    except subprocess.TimeoutExpired:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "TIMEOUT", "message": "Command timed out"},
                }
            ),
            408,
        )

    return jsonify(
        {
            "ok": True,
            "data": {
                "command": command,
                "cwd": str(cwd),
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-20000:],
                "stderr": proc.stderr[-20000:],
            },
        }
    )
