from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, render_template, request


DB_PATH = Path("data/advocate.db")
STATIC_DIR = Path("static")
LATEST_FILENAME = "zlink-latest.zip"

bp = Blueprint("zlink", __name__, url_prefix="/zlink")


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


@bp.post("/metrics/usage")
def ingest_usage():
    payload = request.get_json(silent=True)
    if not isinstance(payload, list) or not payload:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "Payload must be a non-empty array",
                    },
                }
            ),
            400,
        )

    now = datetime.now(timezone.utc).isoformat()
    rows: list[tuple[str, str, int, str]] = []
    for item in payload:
        server = str(item.get("server", "")).strip() if isinstance(item, dict) else ""
        usage = item.get("usage") if isinstance(item, dict) else None
        if not server or not isinstance(usage, dict):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Each item requires server and usage map",
                        },
                    }
                ),
                422,
            )
        for ts_hour, bytes_used in usage.items():
            if not _is_valid_hour_key(str(ts_hour)):
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": f"Invalid hour key '{ts_hour}'",
                            },
                        }
                    ),
                    422,
                )
            if not isinstance(bytes_used, int) or bytes_used < 0:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": {
                                "code": "VALIDATION_ERROR",
                                "message": f"Usage bytes must be a non-negative integer for '{server}' at '{ts_hour}'",
                            },
                        }
                    ),
                    422,
                )
            rows.append((server, str(ts_hour), bytes_used, now))

    with _db() as conn:
        conn.executemany(
            "INSERT INTO zlink_usage(server, ts_hour, bytes_used, created_at) VALUES (?, ?, ?, ?)",
            rows,
        )

    return jsonify({"ok": True, "data": {"inserted": len(rows)}})


@bp.get("/metrics/usage")
def usage_timeseries():
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT server, ts_hour, SUM(bytes_used) AS total_bytes
            FROM zlink_usage
            GROUP BY server, ts_hour
            ORDER BY ts_hour ASC
            """
        ).fetchall()

    data: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        data.setdefault(row["server"], []).append(
            {"ts_hour": row["ts_hour"], "bytes": int(row["total_bytes"])}
        )

    return jsonify({"ok": True, "data": data})


@bp.get("/dashboard")
def dashboard():
    return render_template("zlink/dashboard.html", title="ZLink Usage Dashboard")


def _read_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as response:
        destination.write_bytes(response.read())


@bp.post("/latest/refresh")
def refresh_latest_release():
    repo = os.getenv("ZLINK_REPO")
    if not repo:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "BAD_REQUEST",
                        "message": "Set ZLINK_REPO as owner/repo",
                    },
                }
            ),
            400,
        )

    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "advocate-zlink"}

    try:
        data = _read_json(api_url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "UPSTREAM_ERROR",
                        "message": f"Failed fetching latest release metadata: {exc}",
                    },
                }
            ),
            502,
        )

    tag = data.get("tag_name") or data.get("name") or "unknown"
    assets = data.get("assets") or []
    download_url = (
        assets[0].get("browser_download_url") if assets else data.get("zipball_url")
    )
    if not download_url:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "NO_ASSET",
                        "message": "No downloadable asset found in latest release",
                    },
                }
            ),
            502,
        )

    local_path = STATIC_DIR / LATEST_FILENAME
    try:
        _download(download_url, local_path)
    except Exception as exc:  # noqa: BLE001
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "DOWNLOAD_FAILED",
                        "message": f"Failed downloading release asset: {exc}",
                    },
                }
            ),
            502,
        )

    return jsonify(
        {
            "latest-version": str(tag).lstrip("v"),
            "download-url": f"/static/{LATEST_FILENAME}",
        }
    )


@bp.get("/latest")
def latest_release_info():
    local_path = STATIC_DIR / LATEST_FILENAME
    if local_path.exists():
        return jsonify(
            {"latest-version": "cached", "download-url": f"/static/{LATEST_FILENAME}"}
        )
    return jsonify({"latest-version": "unknown", "download-url": ""})
