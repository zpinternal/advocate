from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
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


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>ZLink Usage Dashboard</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    #chart { border: 1px solid #ccc; width: 100%; height: 420px; }
    .legend { margin-top: 10px; }
  </style>
</head>
<body>
  <h1>ZLink Usage Dashboard</h1>
  <p>Usage (bytes) over time per server.</p>
  <svg id="chart" viewBox="0 0 1000 420"></svg>
  <div id="legend" class="legend"></div>

  <script>
    const colors = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2"];

    function draw(data) {
      const svg = document.getElementById("chart");
      const legend = document.getElementById("legend");
      svg.innerHTML = "";
      legend.innerHTML = "";

      const entries = Object.entries(data);
      if (entries.length === 0) {
        svg.innerHTML = "<text x='20' y='40'>No data yet.</text>";
        return;
      }

      const allPoints = entries.flatMap(([_, points]) => points);
      const ys = allPoints.map(p => p.bytes);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      const xPadding = 60;
      const yPadding = 30;
      const width = 1000 - xPadding * 2;
      const height = 420 - yPadding * 2;

      const allTs = [...new Set(allPoints.map(p => p.ts_hour))].sort();
      const xMap = new Map(allTs.map((ts, i) => [ts, i]));
      const xScale = (idx) => xPadding + (idx / Math.max(allTs.length - 1, 1)) * width;
      const yScale = (v) => yPadding + (maxY === minY ? height / 2 : (1 - ((v - minY) / (maxY - minY))) * height);

      const axis = document.createElementNS("http://www.w3.org/2000/svg", "line");
      axis.setAttribute("x1", xPadding);
      axis.setAttribute("x2", xPadding);
      axis.setAttribute("y1", yPadding);
      axis.setAttribute("y2", yPadding + height);
      axis.setAttribute("stroke", "#777");
      svg.appendChild(axis);

      const axisX = document.createElementNS("http://www.w3.org/2000/svg", "line");
      axisX.setAttribute("x1", xPadding);
      axisX.setAttribute("x2", xPadding + width);
      axisX.setAttribute("y1", yPadding + height);
      axisX.setAttribute("y2", yPadding + height);
      axisX.setAttribute("stroke", "#777");
      svg.appendChild(axisX);

      entries.forEach(([server, points], idx) => {
        const color = colors[idx % colors.length];
        const ordered = [...points].sort((a,b) => a.ts_hour.localeCompare(b.ts_hour));
        const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        const coords = ordered
          .map(p => `${xScale(xMap.get(p.ts_hour))},${yScale(p.bytes)}`)
          .join(" ");
        poly.setAttribute("points", coords);
        poly.setAttribute("fill", "none");
        poly.setAttribute("stroke", color);
        poly.setAttribute("stroke-width", "2");
        svg.appendChild(poly);

        const item = document.createElement("div");
        item.innerHTML = `<span style="display:inline-block;width:12px;height:12px;background:${color};margin-right:8px;"></span>${server}`;
        legend.appendChild(item);
      });
    }

    fetch('/zlink/metrics/usage')
      .then(r => r.json())
      .then(r => draw(r.data || {}))
      .catch(() => {
        document.getElementById('chart').innerHTML = "<text x='20' y='40'>Failed to load data.</text>";
      });
  </script>
</body>
</html>
    """


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
