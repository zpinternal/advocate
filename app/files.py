from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file

from app.tasks import TASK_MANAGER


bp = Blueprint("files", __name__, url_prefix="/files")

BASE_DIR = Path.cwd().resolve()
CURRENT_DIR = BASE_DIR


def _error(status: int, code: str, message: str):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def _safe_path(path: str) -> Path:
    global CURRENT_DIR
    requested = (
        (CURRENT_DIR / path).resolve()
        if not Path(path).is_absolute()
        else Path(path).resolve()
    )
    if not str(requested).startswith(str(BASE_DIR)):
        raise ValueError("Path escapes base directory")
    return requested


@bp.get("/ui")
def files_ui():
    return render_template("files/dashboard.html", title="File Explorer")


@bp.get("/cwd")
def cwd_info():
    return jsonify(
        {"ok": True, "data": {"base_dir": str(BASE_DIR), "cwd": str(CURRENT_DIR)}}
    )


@bp.post("/chdir")
def chdir():
    global CURRENT_DIR
    payload = request.get_json(silent=True) or {}
    path = str(payload.get("path", "")).strip()
    if not path:
        return _error(422, "VALIDATION_ERROR", "path is required")

    try:
        new_dir = _safe_path(path)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not new_dir.exists() or not new_dir.is_dir():
        return _error(404, "NOT_FOUND", "Directory not found")

    CURRENT_DIR = new_dir
    return jsonify({"ok": True, "data": {"cwd": str(CURRENT_DIR)}})


@bp.get("/list")
def list_items():
    path = request.args.get("path", ".")
    try:
        target = _safe_path(path)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not target.exists() or not target.is_dir():
        return _error(404, "NOT_FOUND", "Directory not found")

    items = []
    for item in sorted(
        target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
    ):
        items.append(
            {
                "name": item.name,
                "path": str(item),
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            }
        )

    return jsonify(
        {
            "ok": True,
            "data": {"cwd": str(CURRENT_DIR), "path": str(target), "items": items},
        }
    )


@bp.post("/create")
def create_item():
    payload = request.get_json(silent=True) or {}
    path = str(payload.get("path", "")).strip()
    kind = payload.get("kind")
    if not path or kind not in {"file", "dir"}:
        return _error(422, "VALIDATION_ERROR", "path and kind (file|dir) are required")

    try:
        target = _safe_path(path)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if target.exists():
        return _error(409, "CONFLICT", "Path already exists")

    if kind == "dir":
        target.mkdir(parents=True, exist_ok=False)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=False)

    return jsonify({"ok": True, "data": {"path": str(target), "kind": kind}})


@bp.post("/rename")
def rename_item():
    payload = request.get_json(silent=True) or {}
    old_path = str(payload.get("old_path", "")).strip()
    new_path = str(payload.get("new_path", "")).strip()
    if not old_path or not new_path:
        return _error(422, "VALIDATION_ERROR", "old_path and new_path are required")

    try:
        old_target = _safe_path(old_path)
        new_target = _safe_path(new_path)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not old_target.exists():
        return _error(404, "NOT_FOUND", "Source path does not exist")
    if new_target.exists():
        return _error(409, "CONFLICT", "Destination path already exists")

    old_target.rename(new_target)
    return jsonify(
        {"ok": True, "data": {"old_path": str(old_target), "new_path": str(new_target)}}
    )


@bp.post("/upload")
def upload_file():
    target_dir = request.form.get("target_dir", ".")
    file = request.files.get("file")
    if not file:
        return _error(422, "VALIDATION_ERROR", "file is required")

    try:
        target = _safe_path(target_dir)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not target.exists() or not target.is_dir():
        return _error(404, "NOT_FOUND", "Target directory not found")

    output_file = target / file.filename
    file.save(output_file)
    return jsonify(
        {
            "ok": True,
            "data": {"path": str(output_file), "size": output_file.stat().st_size},
        }
    )


@bp.get("/download")
def download_file():
    path = request.args.get("path", "")
    try:
        target = _safe_path(path)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not target.exists() or not target.is_file():
        return _error(404, "NOT_FOUND", "File not found")
    return send_file(target, as_attachment=True, download_name=target.name)


def _tar_job(progress, source: Path, output_path: Path):
    progress(20, "Preparing tar archive")
    with tarfile.open(output_path, "w") as tf:
        tf.add(source, arcname=source.name)
    progress(100, "Tar archive created")
    return {"output_path": str(output_path), "type": "tar"}


def _zip_job(progress, source: Path, output_path: Path):
    progress(20, "Preparing zip archive")
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if source.is_file():
            zf.write(source, arcname=source.name)
        else:
            for root, _, files in os.walk(source):
                for filename in files:
                    full_path = Path(root) / filename
                    rel_path = full_path.relative_to(source.parent)
                    zf.write(full_path, arcname=str(rel_path))
    progress(100, "Zip archive created")
    return {"output_path": str(output_path), "type": "zip"}


@bp.post("/archive")
def archive():
    payload = request.get_json(silent=True) or {}
    source_path = str(payload.get("source_path", "")).strip()
    output_name = str(payload.get("output_name", "")).strip()
    if not source_path or not output_name:
        return _error(
            422, "VALIDATION_ERROR", "source_path and output_name are required"
        )

    try:
        source = _safe_path(source_path)
        output = _safe_path(output_name)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not source.exists():
        return _error(404, "NOT_FOUND", "Source path not found")

    if output.suffix != ".tar":
        output = output.with_suffix(".tar")

    task = TASK_MANAGER.create_task("files", "archive", _tar_job, source, output)
    return jsonify(
        {
            "ok": True,
            "data": {
                "task_id": task.id,
                "status": task.status,
                "status_url": f"/tasks/{task.id}",
            },
        }
    )


@bp.post("/compress")
def compress():
    payload = request.get_json(silent=True) or {}
    source_path = str(payload.get("source_path", "")).strip()
    output_name = str(payload.get("output_name", "")).strip()
    if not source_path or not output_name:
        return _error(
            422, "VALIDATION_ERROR", "source_path and output_name are required"
        )

    try:
        source = _safe_path(source_path)
        output = _safe_path(output_name)
    except ValueError as exc:
        return _error(400, "BAD_PATH", str(exc))

    if not source.exists():
        return _error(404, "NOT_FOUND", "Source path not found")

    if output.suffix != ".zip":
        output = output.with_suffix(".zip")

    task = TASK_MANAGER.create_task("files", "compress", _zip_job, source, output)
    return jsonify(
        {
            "ok": True,
            "data": {
                "task_id": task.id,
                "status": task.status,
                "status_url": f"/tasks/{task.id}",
            },
        }
    )
