from __future__ import annotations

import io
import tarfile
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from ftplib import FTP, FTP_TLS, all_errors
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/ftp", tags=["ftp"])
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


class LoginRequest(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=21, ge=1, le=65535)
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    use_ssl: bool = False
    passive: bool = True


class PathRequest(BaseModel):
    session_id: str = Field(min_length=1)
    path: str = Field(default=".")


class ArchiveRequest(BaseModel):
    session_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    output_name: str = Field(min_length=1)


class ExtractRequest(BaseModel):
    session_id: str = Field(min_length=1)
    archive_path: str = Field(min_length=1)
    target_dir: str = Field(default=".")


def _connect(session: FTPSession):
    client = FTP_TLS() if session.use_ssl else FTP()
    client.connect(session.host, session.port, timeout=20)
    client.login(session.username, session.password)
    client.set_pasv(session.passive)
    if session.use_ssl:
        client.prot_p()
    return client


def _session(session_id: str) -> FTPSession:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="FTP session not found")
    return session


@router.post("/login")
def login(payload: LoginRequest):
    session = FTPSession(
        id=str(uuid.uuid4()),
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        use_ssl=payload.use_ssl,
        passive=payload.passive,
    )

    try:
        client = _connect(session)
        cwd = client.pwd()
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"FTP login failed: {exc}") from exc

    SESSIONS[session.id] = session
    return {"ok": True, "data": {"session_id": session.id, "cwd": cwd}}


@router.get("/browse")
def browse(session_id: str, path: str = "."):
    session = _session(session_id)
    try:
        client = _connect(session)
        client.cwd(path)
        items = client.nlst()
        cwd = client.pwd()
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Browse failed: {exc}") from exc

    entries = []
    for name in items:
        entries.append({"name": name, "path": f"{cwd.rstrip('/')}/{name}"})

    return {"ok": True, "data": {"cwd": cwd, "items": entries}}


@router.post("/upload")
def upload(
    session_id: str = Form(...),
    remote_path: str = Form(...),
    file: UploadFile = File(...),
):
    session = _session(session_id)
    try:
        client = _connect(session)
        client.storbinary(f"STOR {remote_path}", file.file)
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Upload failed: {exc}") from exc

    return {"ok": True, "data": {"remote_path": remote_path}}


@router.get("/download")
def download(session_id: str, remote_path: str):
    session = _session(session_id)
    buffer = io.BytesIO()
    try:
        client = _connect(session)
        client.retrbinary(f"RETR {remote_path}", buffer.write)
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Download failed: {exc}") from exc

    buffer.seek(0)
    filename = Path(remote_path).name or "download.bin"
    return StreamingResponse(
        buffer,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _download_remote_file(client, remote_path: str) -> bytes:
    buffer = io.BytesIO()
    client.retrbinary(f"RETR {remote_path}", buffer.write)
    return buffer.getvalue()


def _upload_bytes(client, remote_path: str, data: bytes) -> None:
    client.storbinary(f"STOR {remote_path}", io.BytesIO(data))


@router.post("/archive")
def archive(payload: ArchiveRequest):
    session = _session(payload.session_id)
    try:
        client = _connect(session)
        source_bytes = _download_remote_file(client, payload.path)

        out_name = payload.output_name
        if not out_name.endswith(".tar"):
            out_name += ".tar"

        out_buffer = io.BytesIO()
        with tarfile.open(fileobj=out_buffer, mode="w") as tf:
            info = tarfile.TarInfo(name=Path(payload.path).name)
            info.size = len(source_bytes)
            tf.addfile(info, io.BytesIO(source_bytes))

        out_buffer.seek(0)
        _upload_bytes(client, out_name, out_buffer.read())
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Archive failed: {exc}") from exc

    return {"ok": True, "data": {"remote_path": out_name, "type": "tar"}}


@router.post("/compress")
def compress(payload: ArchiveRequest):
    session = _session(payload.session_id)
    try:
        client = _connect(session)
        source_bytes = _download_remote_file(client, payload.path)

        out_name = payload.output_name
        if not out_name.endswith(".zip"):
            out_name += ".zip"

        out_buffer = io.BytesIO()
        with zipfile.ZipFile(
            out_buffer, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            zf.writestr(Path(payload.path).name, source_bytes)

        out_buffer.seek(0)
        _upload_bytes(client, out_name, out_buffer.read())
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Compress failed: {exc}") from exc

    return {"ok": True, "data": {"remote_path": out_name, "type": "zip"}}


def _upload_tree(client, root: Path, target_dir: str) -> list[str]:
    uploaded = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(root)
        relative_str = str(relative).replace("\\", "/")
        remote_path = f"{target_dir.rstrip('/')}/{relative_str}"
        with path.open("rb") as fh:
            client.storbinary(f"STOR {remote_path}", fh)
        uploaded.append(remote_path)
    return uploaded


@router.post("/extract")
def extract(payload: ExtractRequest):
    session = _session(payload.session_id)

    try:
        client = _connect(session)
        data = _download_remote_file(client, payload.archive_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            archive_name = Path(payload.archive_path).name
            archive_file = tmp / archive_name
            archive_file.write_bytes(data)

            extract_dir = tmp / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)

            if archive_name.endswith(".zip"):
                with zipfile.ZipFile(archive_file, "r") as zf:
                    zf.extractall(extract_dir)
            elif archive_name.endswith(".tar") or archive_name.endswith(".tar.gz"):
                with tarfile.open(archive_file, "r:*") as tf:
                    tf.extractall(extract_dir)
            else:
                raise HTTPException(
                    status_code=400, detail="Unsupported archive format"
                )

            uploaded = _upload_tree(client, extract_dir, payload.target_dir)

        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Extract failed: {exc}") from exc

    return {
        "ok": True,
        "data": {"uploaded_files": uploaded, "target_dir": payload.target_dir},
    }


@router.post("/upload-extract")
def upload_extract(
    session_id: str = Form(...),
    target_dir: str = Form("."),
    file: UploadFile = File(...),
):
    session = _session(session_id)
    data = file.file.read()

    try:
        client = _connect(session)
        remote_path = f"{target_dir.rstrip('/')}/{file.filename}"
        _upload_bytes(client, remote_path, data)
        client.quit()
    except all_errors as exc:
        raise HTTPException(status_code=400, detail=f"Upload failed: {exc}") from exc

    return extract(
        ExtractRequest(
            session_id=session_id, archive_path=remote_path, target_dir=target_dir
        )
    )


@router.post("/archive-download")
def archive_download(payload: ArchiveRequest):
    session = _session(payload.session_id)

    try:
        client = _connect(session)
        source_bytes = _download_remote_file(client, payload.path)
        client.quit()
    except all_errors as exc:
        raise HTTPException(
            status_code=400, detail=f"Archive download failed: {exc}"
        ) from exc

    out_name = payload.output_name
    if not out_name.endswith(".tar"):
        out_name += ".tar"

    artifact_name = f"{uuid.uuid4()}-{Path(out_name).name}"
    artifact_path = ARTIFACT_DIR / artifact_name

    with tarfile.open(artifact_path, "w") as tf:
        info = tarfile.TarInfo(name=Path(payload.path).name)
        info.size = len(source_bytes)
        tf.addfile(info, io.BytesIO(source_bytes))

    return {
        "ok": True,
        "data": {
            "latest-version": "n/a",
            "download-url": f"/static/ftp/{artifact_name}",
            "local_path": str(artifact_path),
        },
    }


@router.get("/artifact")
def artifact(path: str):
    artifact_path = ARTIFACT_DIR / path
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path=artifact_path, filename=artifact_path.name)
