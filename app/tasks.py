from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass
class TaskRecord:
    id: str
    module: str
    operation: str
    status: str
    created_at: str
    updated_at: str
    progress: int = 0
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class TaskManager:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def create_task(
        self,
        module: str,
        operation: str,
        fn: Callable[..., dict[str, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> TaskRecord:
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        record = TaskRecord(
            id=task_id,
            module=module,
            operation=operation,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[task_id] = record

        future = self._executor.submit(self._run_task, task_id, fn, *args, **kwargs)
        future.add_done_callback(lambda _: None)
        return record

    def _run_task(
        self,
        task_id: str,
        fn: Callable[..., dict[str, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        self.update(task_id, status="running", progress=5, message="Task started")
        try:
            result = fn(self.progress_callback(task_id), *args, **kwargs)
            self.update(
                task_id,
                status="succeeded",
                progress=100,
                message="Task completed",
                result=result,
            )
        except Exception as exc:  # noqa: BLE001
            self.update(
                task_id,
                status="failed",
                progress=100,
                error=str(exc),
                message="Task failed",
            )

    def progress_callback(self, task_id: str) -> Callable[[int, str], None]:
        def _callback(progress: int, message: str = "") -> None:
            self.update(task_id, progress=progress, message=message)

        return _callback

    def update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            record = self._tasks[task_id]
            for key, value in fields.items():
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc).isoformat()

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def all(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._tasks.values())


TASK_MANAGER = TaskManager()
