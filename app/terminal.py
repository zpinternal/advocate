from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field


router = APIRouter(prefix="/terminal", tags=["terminal"])
BASE_DIR = Path.cwd().resolve()


class ExecRequest(BaseModel):
    command: str = Field(min_length=1)
    cwd: str | None = None
    timeout_seconds: int = Field(default=20, ge=1, le=300)


def _safe_cwd(cwd: str | None) -> Path:
    if not cwd:
        return BASE_DIR

    target = Path(cwd)
    if not target.is_absolute():
        target = (BASE_DIR / cwd).resolve()
    else:
        target = target.resolve()

    if not str(target).startswith(str(BASE_DIR)):
        raise HTTPException(status_code=400, detail="cwd escapes base directory")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="cwd does not exist")
    return target


@router.post("/exec")
def execute_command(payload: ExecRequest):
    cwd = _safe_cwd(payload.cwd)
    try:
        proc = subprocess.run(
            payload.command,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=payload.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="Command timed out")

    stdout = proc.stdout[-20000:]
    stderr = proc.stderr[-20000:]

    return {
        "ok": True,
        "data": {
            "command": payload.command,
            "cwd": str(cwd),
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        },
    }


async def _run_ws_command(command: str, cwd: Path) -> dict[str, str | int]:
    process = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = await process.communicate()
    return {
        "command": command,
        "exit_code": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[-20000:],
        "stderr": stderr.decode("utf-8", errors="replace")[-20000:],
    }


@router.websocket("/ws")
async def websocket_terminal(websocket: WebSocket):
    current_cwd = BASE_DIR
    await websocket.accept()
    await websocket.send_json(
        {
            "event": "connected",
            "message": "Send commands as plain text. Type 'exit' to close.",
            "cwd": str(current_cwd),
        }
    )

    while True:
        try:
            message = await websocket.receive_text()
        except WebSocketDisconnect:
            break

        command = message.strip()
        if not command:
            await websocket.send_json({"event": "error", "message": "Empty command"})
            continue

        if command.lower() in {"exit", "quit"}:
            await websocket.send_json({"event": "closing", "message": "Session closed"})
            await websocket.close()
            break

        if command.startswith("cd "):
            parts = shlex.split(command)
            if len(parts) == 2:
                try:
                    new_cwd = _safe_cwd(str((current_cwd / parts[1]).resolve()))
                except HTTPException as exc:
                    await websocket.send_json(
                        {
                            "event": "error",
                            "message": exc.detail,
                            "status_code": exc.status_code,
                        }
                    )
                    continue
                current_cwd = new_cwd
                await websocket.send_json({"event": "cwd", "cwd": str(new_cwd)})
                continue

        try:
            result = await asyncio.wait_for(
                _run_ws_command(command, current_cwd), timeout=300
            )
        except asyncio.TimeoutError:
            await websocket.send_json(
                {"event": "error", "message": "Command timed out"}
            )
            continue

        await websocket.send_json({"event": "result", "data": result})
