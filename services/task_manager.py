"""
services/task_manager.py — asyncio 任務追蹤與緊急停止
路徑：services/task_manager.py

職責：
  - 建立並追蹤所有 agent 背景任務
  - /stop 指令：cancel 所有執行中任務，設定停止旗標
  - /resume 指令：解除停止狀態
  - Telegram Bot 呼叫 task_manager.create_task() 包裝所有 coroutine

使用方式：
    task_manager = TaskManager()
    task = task_manager.create_task(some_coroutine(), name="llm_call")

    # 緊急停止
    cancelled = task_manager.emergency_stop()

    # 查詢狀態
    task_manager.is_stopped       → bool
    task_manager.active_count()   → int
"""
from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class TaskManager:
    """
    管理 agent 的所有非同步任務。

    設計說明：
      - _tasks 只追蹤「進行中」的任務，完成後自動移除（done callback）
      - emergency_stop() 設定旗標後，Planner 的 process() 會在每輪開頭檢查
      - resume() 清除旗標，不需要重啟程序
    """

    def __init__(self) -> None:
        # task_id（name 或 id(task)）→ asyncio.Task
        self._tasks: dict[str, asyncio.Task] = {}
        # 緊急停止旗標
        self._stop_event = asyncio.Event()

    # ── 狀態查詢 ─────────────────────────────────────────────────────

    @property
    def is_stopped(self) -> bool:
        """是否處於緊急停止狀態"""
        return self._stop_event.is_set()

    def active_count(self) -> int:
        """目前執行中（未完成）的任務數量"""
        return sum(1 for t in self._tasks.values() if not t.done())

    def active_names(self) -> list[str]:
        """執行中任務的名稱清單（給 /status 用）"""
        return [name for name, t in self._tasks.items() if not t.done()]

    # ── 任務管理 ─────────────────────────────────────────────────────

    def create_task(
        self,
        coro: Coroutine,
        name: str | None = None,
    ) -> asyncio.Task:
        """
        建立並追蹤一個 asyncio Task。
        任務完成後自動從追蹤清單移除。
        """
        task = asyncio.create_task(coro, name=name)
        task_id = name or str(id(task))
        self._tasks[task_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(task_id, None))
        logger.debug(f"[TaskManager] 建立任務：{task_id}")
        return task

    # ── 停止 / 恢復 ───────────────────────────────────────────────────

    def emergency_stop(self) -> int:
        """
        緊急停止所有執行中任務。
        設定停止旗標（Planner 會在每輪 loop 開頭檢查）。
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

    def resume(self) -> None:
        """
        解除緊急停止狀態，恢復正常運作。
        不需要重啟程序。
        """
        self._stop_event.clear()
        logger.info("[TaskManager] Agent 已恢復運作")

    def stop_event(self) -> asyncio.Event:
        """
        回傳停止旗標（asyncio.Event）。
        供需要長時間等待的任務自行檢查是否要中止。
        """
        return self._stop_event
