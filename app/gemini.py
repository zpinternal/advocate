from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/gemini", tags=["gemini"])
DB_PATH = Path("data/advocate.db")


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="New Conversation", min_length=1)


class MessageCreateRequest(BaseModel):
    message: str = Field(min_length=1)
    type: str = Field(default="user", pattern="^(user|assistant|system)$")


class SendRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: int | None = None
    title: str = "New Conversation"
    model: str = "gemini-2.0-flash"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    target_language: str = Field(min_length=2)
    source_language: str | None = None
    model: str = "gemini-2.0-flash"


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


def _conversation_or_404(conversation_id: int) -> sqlite3.Row:
    with _db() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


def _add_message(conversation_id: int, message: str, msg_type: str) -> int:
    _conversation_or_404(conversation_id)
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
        raise HTTPException(
            status_code=400,
            detail="Set GEMINI_API_KEY to enable Gemini model calls",
        )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
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
        raise HTTPException(status_code=502, detail=f"Gemini API HTTP error: {detail}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Gemini API call failed: {exc}")

    candidates = body.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=502, detail="Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    text_chunks = [p.get("text", "") for p in parts if p.get("text")]
    response_text = "\n".join(text_chunks).strip()
    if not response_text:
        raise HTTPException(status_code=502, detail="Gemini response was empty")
    return response_text


@router.post("/conversations")
def create_conversation(payload: ConversationCreateRequest):
    conversation_id = _create_conversation(payload.title)
    return {"ok": True, "data": {"conversation_id": conversation_id}}


@router.get("/conversations")
def list_conversations():
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()

    return {
        "ok": True,
        "data": [
            {
                "id": int(row["id"]),
                "title": row["title"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


@router.post("/conversations/{conversation_id}/messages")
def add_message(conversation_id: int, payload: MessageCreateRequest):
    message_id = _add_message(conversation_id, payload.message, payload.type)
    return {
        "ok": True,
        "data": {
            "conversation_id": conversation_id,
            "message_id": message_id,
            "type": payload.type,
        },
    }


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int, after_id: int = 0):
    _conversation_or_404(conversation_id)
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, conv_id, message, type, created_at
            FROM messages
            WHERE conv_id = ? AND id > ?
            ORDER BY id ASC
            """,
            (conversation_id, after_id),
        ).fetchall()

    messages = [
        {
            "id": int(row["id"]),
            "conversation_id": int(row["conv_id"]),
            "message": row["message"],
            "type": row["type"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {"ok": True, "data": {"messages": messages}}


@router.get("/sync")
def sync_messages(conversation_id: int, last_saved_message_id: int = 0):
    return list_messages(
        conversation_id=conversation_id, after_id=last_saved_message_id
    )


@router.post("/chat/send")
def send_chat(payload: SendRequest):
    conversation_id = payload.conversation_id or _create_conversation(payload.title)

    user_message_id = _add_message(conversation_id, payload.message, "user")
    assistant_text = _call_gemini_text(payload.message, payload.model)
    assistant_message_id = _add_message(conversation_id, assistant_text, "assistant")

    return {
        "ok": True,
        "data": {
            "conversation_id": conversation_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "assistant_message": assistant_text,
            "model": payload.model,
        },
    }


@router.post("/translate")
def translate(payload: TranslateRequest):
    source = payload.source_language or "auto"
    prompt = (
        "Translate the following text. Return only the translated text without explanation. "
        f"Source language: {source}. Target language: {payload.target_language}. "
        f"Text: {payload.text}"
    )
    translated = _call_gemini_text(prompt, payload.model)
    return {
        "ok": True,
        "data": {
            "translated_text": translated,
            "source_language": source,
            "target_language": payload.target_language,
            "model": payload.model,
        },
    }
