from fastapi import APIRouter, HTTPException

from app.tasks import TASK_MANAGER


router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks():
    return {
        "ok": True,
        "data": [record.__dict__ for record in TASK_MANAGER.all()],
    }


@router.get("/{task_id}")
def get_task(task_id: str):
    task = TASK_MANAGER.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"ok": True, "data": task.__dict__}
