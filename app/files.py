from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.tasks import TASK_MANAGER


router = APIRouter(prefix="/files", tags=["files"])


BASE_DIR = Path.cwd().resolve()
CURRENT_DIR = BASE_DIR


def _safe_path(path: str) -> Path:
    global CURRENT_DIR

    requested = (
        (CURRENT_DIR / path).resolve()
        if not Path(path).is_absolute()
        else Path(path).resolve()
    )
    if not str(requested).startswith(str(BASE_DIR)):
        raise HTTPException(status_code=400, detail="Path escapes base directory")
    return requested


class ChdirRequest(BaseModel):
    path: str = Field(min_length=1)


class RenameRequest(BaseModel):
    old_path: str = Field(min_length=1)
    new_path: str = Field(min_length=1)


class CreateRequest(BaseModel):
    path: str = Field(min_length=1)
    kind: str = Field(pattern="^(file|dir)$")


class ArchiveRequest(BaseModel):
    source_path: str = Field(min_length=1)
    output_name: str = Field(min_length=1)


@router.get("/cwd")
def cwd_info():
    return {"ok": True, "data": {"base_dir": str(BASE_DIR), "cwd": str(CURRENT_DIR)}}


@router.post("/chdir")
def chdir(payload: ChdirRequest):
    global CURRENT_DIR

    new_dir = _safe_path(payload.path)
    if not new_dir.exists() or not new_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    CURRENT_DIR = new_dir
    return {"ok": True, "data": {"cwd": str(CURRENT_DIR)}}


@router.get("/list")
def list_items(path: str = "."):
    target = _safe_path(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    entries = []
    for item in sorted(
        target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
    ):
        entries.append(
            {
                "name": item.name,
                "path": str(item),
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            }
        )

    return {
        "ok": True,
        "data": {"cwd": str(CURRENT_DIR), "path": str(target), "items": entries},
    }


@router.post("/create")
def create_item(payload: CreateRequest):
    target = _safe_path(payload.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="Path already exists")

    if payload.kind == "dir":
        target.mkdir(parents=True, exist_ok=False)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=False)

    return {"ok": True, "data": {"path": str(target), "kind": payload.kind}}


@router.post("/rename")
def rename_item(payload: RenameRequest):
    old_target = _safe_path(payload.old_path)
    new_target = _safe_path(payload.new_path)

    if not old_target.exists():
        raise HTTPException(status_code=404, detail="Source path does not exist")
    if new_target.exists():
        raise HTTPException(status_code=409, detail="Destination path already exists")

    old_target.rename(new_target)
    return {
        "ok": True,
        "data": {"old_path": str(old_target), "new_path": str(new_target)},
    }


@router.post("/upload")
def upload_file(file: UploadFile = File(...), target_dir: str = "."):
    target = _safe_path(target_dir)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Target directory not found")

    output_file = target / file.filename
    with output_file.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return {
        "ok": True,
        "data": {"path": str(output_file), "size": output_file.stat().st_size},
    }


@router.get("/download")
def download_file(path: str):
    target = _safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=target, filename=target.name)


def _tar_job(progress, source: Path, output_path: Path) -> dict[str, str]:
    progress(20, "Preparing tar archive")
    with tarfile.open(output_path, "w") as tf:
        tf.add(source, arcname=source.name)
    progress(100, "Tar archive created")
    return {"output_path": str(output_path), "type": "tar"}


def _zip_job(progress, source: Path, output_path: Path) -> dict[str, str]:
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


@router.post("/archive")
def archive(payload: ArchiveRequest):
    source = _safe_path(payload.source_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source path not found")

    output = _safe_path(payload.output_name)
    if output.suffix != ".tar":
        output = output.with_suffix(".tar")

    task = TASK_MANAGER.create_task("files", "archive", _tar_job, source, output)
    return {
        "ok": True,
        "data": {
            "task_id": task.id,
            "status": task.status,
            "status_url": f"/tasks/{task.id}",
        },
    }


@router.post("/compress")
def compress(payload: ArchiveRequest):
    source = _safe_path(payload.source_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Source path not found")

    output = _safe_path(payload.output_name)
    if output.suffix != ".zip":
        output = output.with_suffix(".zip")

    task = TASK_MANAGER.create_task("files", "compress", _zip_job, source, output)
    return {
        "ok": True,
        "data": {
            "task_id": task.id,
            "status": task.status,
            "status_url": f"/tasks/{task.id}",
        },
    }
