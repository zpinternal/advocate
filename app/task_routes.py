from __future__ import annotations

from flask import Blueprint, jsonify

from app.tasks import TASK_MANAGER


bp = Blueprint("tasks", __name__, url_prefix="/tasks")


@bp.get("")
def list_tasks():
    return jsonify(
        {"ok": True, "data": [record.to_dict() for record in TASK_MANAGER.all()]}
    )


@bp.get("/<task_id>")
def get_task(task_id: str):
    task = TASK_MANAGER.get(task_id)
    if not task:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {"code": "NOT_FOUND", "message": "Task not found"},
                }
            ),
            404,
        )
    return jsonify({"ok": True, "data": task.to_dict()})
