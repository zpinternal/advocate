from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field


DB_PATH = Path("data/advocate.db")
STATIC_DIR = Path("static")
LATEST_FILENAME = "zlink-latest.zip"


@dataclass
class Point:
    ts_hour: str
    bytes_used: int


class UsageItem(BaseModel):
    server: str = Field(min_length=1)
    usage: dict[str, int]


router = APIRouter(prefix="/zlink", tags=["zlink"])
templates = Jinja2Templates(directory="templates")


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS zlink_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server TEXT NOT NULL,
                ts_hour TEXT NOT NULL,
                bytes_used INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_zlink_server_ts ON zlink_usage(server, ts_hour)"
        )


def _is_valid_hour_key(key: str) -> bool:
    try:
        datetime.strptime(key, "%Y-%m-%d %H")
        return True
    except ValueError:
        return False


@router.post("/metrics/usage")
def ingest_usage(payload: list[UsageItem]):
    if not payload:
        raise HTTPException(status_code=400, detail="Payload must not be empty")

    now = datetime.now(timezone.utc).isoformat()
    rows: list[tuple[str, str, int, str]] = []

    for item in payload:
        for ts_hour, bytes_used in item.usage.items():
            if not _is_valid_hour_key(ts_hour):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid hour key '{ts_hour}'. Expected format: YYYY-MM-DD HH",
                )
            if bytes_used < 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"Usage bytes cannot be negative for '{item.server}' at '{ts_hour}'",
                )
            rows.append((item.server, ts_hour, bytes_used, now))

    with _db() as conn:
        conn.executemany(
            "INSERT INTO zlink_usage(server, ts_hour, bytes_used, created_at) VALUES (?, ?, ?, ?)",
            rows,
        )

    return {"ok": True, "data": {"inserted": len(rows)}}


def _series() -> dict[str, list[Point]]:
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT server, ts_hour, SUM(bytes_used) AS total_bytes
            FROM zlink_usage
            GROUP BY server, ts_hour
            ORDER BY ts_hour ASC
            """
        ).fetchall()

    data: dict[str, list[Point]] = {}
    for row in rows:
        data.setdefault(row["server"], []).append(
            Point(ts_hour=row["ts_hour"], bytes_used=int(row["total_bytes"]))
        )
    return data


@router.get("/metrics/usage")
def usage_timeseries():
    data = _series()
    return {
        "ok": True,
        "data": {
            server: [{"ts_hour": p.ts_hour, "bytes": p.bytes_used} for p in points]
            for server, points in data.items()
        },
    }


@router.get("/dashboard")
def dashboard(request: Request):
    return templates.TemplateResponse(
        "zlink/dashboard.html",
        {"request": request, "title": "ZLink Usage Dashboard"},
    )


def _read_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as response:
        destination.write_bytes(response.read())


@router.post("/latest/refresh")
def refresh_latest_release():
    repo = os.getenv("ZLINK_REPO")
    if not repo:
        raise HTTPException(status_code=400, detail="Set ZLINK_REPO as owner/repo")

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "advocate-zlink"}

    try:
        data = _read_json(api_url, headers=headers)
    except Exception as exc:  # network/runtime errors surfaced in API response
        raise HTTPException(
            status_code=502, detail=f"Failed fetching latest release metadata: {exc}"
        ) from exc

    tag = data.get("tag_name") or data.get("name") or "unknown"

    assets = data.get("assets") or []
    download_url = None
    if assets:
        download_url = assets[0].get("browser_download_url")
    if not download_url:
        download_url = data.get("zipball_url")

    if not download_url:
        raise HTTPException(
            status_code=502, detail="No downloadable asset found in latest release"
        )

    local_path = STATIC_DIR / LATEST_FILENAME
    try:
        _download(download_url, local_path)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed downloading release asset: {exc}"
        ) from exc

    return {
        "latest-version": str(tag).lstrip("v"),
        "download-url": f"/static/{LATEST_FILENAME}",
    }


@router.get("/latest")
def latest_release_info():
    local_path = STATIC_DIR / LATEST_FILENAME
    if local_path.exists():
        return {
            "latest-version": "cached",
            "download-url": f"/static/{LATEST_FILENAME}",
        }
    return {"latest-version": "unknown", "download-url": ""}
