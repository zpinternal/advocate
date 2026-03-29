from __future__ import annotations

import io
import tarfile
import uuid
from dataclasses import dataclass
from ftplib import FTP, FTP_TLS, all_errors
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file


bp = Blueprint("ftp", __name__, url_prefix="/ftp")
ARTIFACT_DIR = Path("static/ftp")
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class FTPSession:
    id: str
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool
    passive: bool


SESSIONS: dict[str, FTPSession] = {}


def _connect(session: FTPSession):
    client = FTP_TLS() if session.use_ssl else FTP()
    client.connect(session.host, session.port, timeout=20)
    client.login(session.username, session.password)
    client.set_pasv(session.passive)
    if session.use_ssl:
        client.prot_p()
    return client


def _session(session_id: str) -> FTPSession | None:
    return SESSIONS.get(session_id)


@bp.get("/ui")
def ftp_ui():
    return render_template("ftp/dashboard.html", title="FTP Viewer")


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    required = ["host", "username", "password"]
    if not all(payload.get(k) for k in required):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "host, username, password are required",
                    },
                }
            ),
            422,
        )

    session = FTPSession(
        id=str(uuid.uuid4()),
        host=str(payload["host"]),
        port=int(payload.get("port", 21)),
        username=str(payload["username"]),
        password=str(payload["password"]),
        use_ssl=bool(payload.get("use_ssl", False)),
        passive=bool(payload.get("passive", True)),
    )
    try:
        client = _connect(session)
        cwd = client.pwd()
        client.quit()
    except all_errors as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "FTP_LOGIN_FAILED",
                        "message": f"FTP login failed: {exc}",
                    },
                }
            ),
            400,
        )

    SESSIONS[session.id] = session
    return jsonify({"ok": True, "data": {"session_id": session.id, "cwd": cwd}})


@bp.get("/browse")
def browse():
    session_id = request.args.get("session_id", "")
    path = request.args.get("path", ".")
    session = _session(session_id)
    if not session:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "FTP session not found"},
                }
            ),
            404,
        )
    try:
        client = _connect(session)
        client.cwd(path)
        items = client.nlst()
        cwd = client.pwd()
        client.quit()
    except all_errors as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "FTP_ERROR", "message": f"Browse failed: {exc}"},
                }
            ),
            400,
        )

    return jsonify(
        {
            "ok": True,
            "data": {
                "cwd": cwd,
                "items": [{"name": n, "path": f"{cwd.rstrip('/')}/{n}"} for n in items],
            },
        }
    )


@bp.post("/upload")
def upload():
    session_id = request.form.get("session_id", "")
    remote_path = request.form.get("remote_path", "")
    file = request.files.get("file")
    if not session_id or not remote_path or not file:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "session_id, remote_path, file are required",
                    },
                }
            ),
            422,
        )
    session = _session(session_id)
    if not session:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "FTP session not found"},
                }
            ),
            404,
        )
    try:
        client = _connect(session)
        client.storbinary(f"STOR {remote_path}", file.stream)
        client.quit()
    except all_errors as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "FTP_ERROR", "message": f"Upload failed: {exc}"},
                }
            ),
            400,
        )
    return jsonify({"ok": True, "data": {"remote_path": remote_path}})


@bp.get("/download")
def download():
    session_id = request.args.get("session_id", "")
    remote_path = request.args.get("remote_path", "")
    session = _session(session_id)
    if not session:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "FTP session not found"},
                }
            ),
            404,
        )

    buffer = io.BytesIO()
    try:
        client = _connect(session)
        client.retrbinary(f"RETR {remote_path}", buffer.write)
        client.quit()
    except all_errors as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "FTP_ERROR",
                        "message": f"Download failed: {exc}",
                    },
                }
            ),
            400,
        )

    buffer.seek(0)
    filename = Path(remote_path).name or "download.bin"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/octet-stream",
    )


@bp.post("/archive-download")
def archive_download():
    payload = request.get_json(silent=True) or {}
    session = _session(str(payload.get("session_id", "")))
    remote_path = str(payload.get("path", ""))
    out_name = str(payload.get("output_name", "archive.tar"))
    if not session or not remote_path:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "valid session_id and path required",
                    },
                }
            ),
            422,
        )
    if not out_name.endswith(".tar"):
        out_name += ".tar"

    try:
        client = _connect(session)
        source = io.BytesIO()
        client.retrbinary(f"RETR {remote_path}", source.write)
        client.quit()
    except all_errors as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "FTP_ERROR",
                        "message": f"Archive download failed: {exc}",
                    },
                }
            ),
            400,
        )

    artifact_name = f"{uuid.uuid4()}-{Path(out_name).name}"
    artifact_path = ARTIFACT_DIR / artifact_name
    source_bytes = source.getvalue()
    with tarfile.open(artifact_path, "w") as tf:
        info = tarfile.TarInfo(name=Path(remote_path).name)
        info.size = len(source_bytes)
        tf.addfile(info, io.BytesIO(source_bytes))

    return jsonify(
        {
            "ok": True,
            "data": {
                "latest-version": "n/a",
                "download-url": f"/static/ftp/{artifact_name}",
                "local_path": str(artifact_path),
            },
        }
    )
