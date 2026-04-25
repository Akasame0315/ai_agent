"""
services/task_manager.py
任務管理器 — asyncio 任務追蹤、/stop 緊急停止
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Any

logger = logging.getLogger(__name__)


class TaskManager:
    """
    管理 agent 的所有非同步任務。
    提供：
      - 建立具追蹤能力的 task
      - 全域緊急停止（cancel 所有執行中 task）
      - 單一 task 取消
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._stop_event = asyncio.Event()

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def create_task(
        self,
        coro: Coroutine,
        name: str | None = None,
    ) -> asyncio.Task:
        """建立並追蹤一個 asyncio Task"""
        task = asyncio.create_task(coro, name=name)
        task_id = name or str(id(task))
        self._tasks[task_id] = task
        task.add_done_callback(lambda t: self._tasks.pop(task_id, None))
        return task

    def emergency_stop(self) -> int:
        """
        緊急停止所有執行中任務。
        回傳被 cancel 的任務數量。
        """
        self._stop_event.set()
        cancelled = 0
        for task_id, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
                cancelled += 1
                logger.warning(f"[STOP] 任務已取消：{task_id}")
        logger.warning(f"[STOP] 緊急停止完成，共取消 {cancelled} 個任務")
        return cancelled

    def resume(self):
        """解除停止狀態（重新啟用 agent）"""
        self._stop_event.clear()
        logger.info("Agent 已恢復運作")

    def active_count(self) -> int:
        return len([t for t in self._tasks.values() if not t.done()])

    def active_names(self) -> list[str]:
        return [
            name for name, task in self._tasks.items() if not task.done()
        ]
