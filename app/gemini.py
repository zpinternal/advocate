from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request


bp = Blueprint("gemini", __name__, url_prefix="/gemini")
DB_PATH = Path("data/advocate.db")


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conv_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(conv_id) REFERENCES conversations(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conv_id_id ON messages(conv_id, id)"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_conversation(title: str) -> int:
    now = _now_iso()
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO conversations(title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now),
        )
        return int(cur.lastrowid)


def _conversation_or_none(conversation_id: int):
    with _db() as conn:
        return conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()


def _add_message(conversation_id: int, message: str, msg_type: str) -> int:
    if not _conversation_or_none(conversation_id):
        raise LookupError("Conversation not found")
    now = _now_iso()
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO messages(conv_id, message, type, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, message, msg_type, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        return int(cur.lastrowid)


def _call_gemini_text(prompt: str, model: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY to enable Gemini model calls")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API HTTP error: {detail}")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Gemini API call failed: {exc}")

    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    response_text = "\n".join(
        [p.get("text", "") for p in parts if p.get("text")]
    ).strip()
    if not response_text:
        raise RuntimeError("Gemini response was empty")
    return response_text


@bp.get("/ui")
def gemini_ui():
    return render_template("gemini/dashboard.html", title="Gemini Assistant")


@bp.post("/conversations")
def create_conversation():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title", "New Conversation")).strip() or "New Conversation"
    return jsonify(
        {"ok": True, "data": {"conversation_id": _create_conversation(title)}}
    )


@bp.get("/conversations")
def list_conversations():
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return jsonify(
        {
            "ok": True,
            "data": [
                {
                    "id": int(r["id"]),
                    "title": r["title"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ],
        }
    )


@bp.post("/conversations/<int:conversation_id>/messages")
def add_message(conversation_id: int):
    payload = request.get_json(silent=True) or {}
    msg = str(payload.get("message", "")).strip()
    msg_type = str(payload.get("type", "user")).strip()
    if not msg or msg_type not in {"user", "assistant", "system"}:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "message and valid type are required",
                    },
                }
            ),
            422,
        )
    try:
        mid = _add_message(conversation_id, msg, msg_type)
    except LookupError:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                }
            ),
            404,
        )
    return jsonify(
        {
            "ok": True,
            "data": {
                "conversation_id": conversation_id,
                "message_id": mid,
                "type": msg_type,
            },
        }
    )


@bp.get("/conversations/<int:conversation_id>/messages")
def list_messages(conversation_id: int):
    if not _conversation_or_none(conversation_id):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                }
            ),
            404,
        )
    after_id = int(request.args.get("after_id", "0"))
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, conv_id, message, type, created_at FROM messages WHERE conv_id = ? AND id > ? ORDER BY id ASC",
            (conversation_id, after_id),
        ).fetchall()
    messages = [
        {
            "id": int(r["id"]),
            "conversation_id": int(r["conv_id"]),
            "message": r["message"],
            "type": r["type"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return jsonify({"ok": True, "data": {"messages": messages}})


@bp.get("/sync")
def sync_messages():
    conversation_id = int(request.args.get("conversation_id", "0"))
    last_saved = int(request.args.get("last_saved_message_id", "0"))
    if not conversation_id:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "conversation_id is required",
                    },
                }
            ),
            422,
        )
    if not _conversation_or_none(conversation_id):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                }
            ),
            404,
        )
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, conv_id, message, type, created_at FROM messages WHERE conv_id = ? AND id > ? ORDER BY id ASC",
            (conversation_id, last_saved),
        ).fetchall()
    messages = [
        {
            "id": int(r["id"]),
            "conversation_id": int(r["conv_id"]),
            "message": r["message"],
            "type": r["type"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return jsonify({"ok": True, "data": {"messages": messages}})


@bp.post("/chat/send")
def send_chat():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "message is required",
                    },
                }
            ),
            422,
        )

    conversation_id = payload.get("conversation_id")
    title = str(payload.get("title", "New Conversation"))
    model = str(payload.get("model", "gemini-2.0-flash"))
    if not conversation_id:
        conversation_id = _create_conversation(title)
    try:
        user_message_id = _add_message(int(conversation_id), message, "user")
        assistant_text = _call_gemini_text(message, model)
        assistant_message_id = _add_message(
            int(conversation_id), assistant_text, "assistant"
        )
    except LookupError:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "Conversation not found"},
                }
            ),
            404,
        )
    except RuntimeError as exc:
        return (
            jsonify(
                {"ok": False, "error": {"code": "UPSTREAM_ERROR", "message": str(exc)}}
            ),
            502,
        )

    return jsonify(
        {
            "ok": True,
            "data": {
                "conversation_id": int(conversation_id),
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
                "assistant_message": assistant_text,
                "model": model,
            },
        }
    )


@bp.post("/translate")
def translate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    target = str(payload.get("target_language", "")).strip()
    source = str(payload.get("source_language", "auto")).strip() or "auto"
    model = str(payload.get("model", "gemini-2.0-flash"))
    if not text or len(target) < 2:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "text and target_language are required",
                    },
                }
            ),
            422,
        )

    prompt = (
        "Translate the following text. Return only the translated text without explanation. "
        f"Source language: {source}. Target language: {target}. Text: {text}"
    )
    try:
        translated = _call_gemini_text(prompt, model)
    except RuntimeError as exc:
        return (
            jsonify(
                {"ok": False, "error": {"code": "UPSTREAM_ERROR", "message": str(exc)}}
            ),
            502,
        )

    return jsonify(
        {
            "ok": True,
            "data": {
                "translated_text": translated,
                "source_language": source,
                "target_language": target,
                "model": model,
            },
        }
    )
