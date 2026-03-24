"""
任務管理器
路徑：core/task_manager.py

功能：
- 非同步任務佇列，讓 Agent 可以背景執行長時任務
- 隨時取消執行中的任務
- 任務狀態追蹤
"""
import asyncio
import uuid
import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

class TaskStatus(Enum):
    PENDING   = "待執行"
    RUNNING   = "執行中"
    DONE      = "已完成"
    CANCELLED = "已取消"
    FAILED    = "失敗"


@dataclass
class Task:
    id:         str
    name:       str
    status:     TaskStatus      = TaskStatus.PENDING
    result:     str             = ""
    created_at: str             = field(default_factory=lambda: datetime.datetime.now().strftime("%H:%M:%S"))
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class TaskManager:
    def __init__(self):
        self.tasks:   dict[str, Task] = {}
        self._notify: Optional[Callable] = None   # Telegram 推播 callback

    def set_notify(self, callback: Callable):
        """設定推播 callback（由 telegram_bot 注入）"""
        self._notify = callback

    async def _push(self, text: str):
        if self._notify:
            try:
                await self._notify(text)
            except Exception:
                pass

    async def run(self, name: str, coro: Awaitable) -> str:
        """
        把協程丟進背景執行，立刻回傳 task_id。
        任務完成後自動推播結果到 Telegram。
        """
        task_id = str(uuid.uuid4())[:8]
        task    = Task(id=task_id, name=name, status=TaskStatus.RUNNING)
        self.tasks[task_id] = task

        async def _wrapper():
            try:
                result = await coro
                task.status = TaskStatus.DONE
                task.result = result or "完成"
                await self._push(f"✅ 任務完成【{name}】\n{result}")
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.result = "已取消"
                await self._push(f"⛔ 任務已取消【{name}】")
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.result = str(e)
                await self._push(f"❌ 任務失敗【{name}】\n{e}")

        asyncio.create_task(_wrapper())
        return task_id

    def cancel(self, task_id: str) -> str:
        """取消指定任務"""
        task = self.tasks.get(task_id)
        if not task:
            return f"❌ 找不到任務：{task_id}"
        if task.status != TaskStatus.RUNNING:
            return f"⚠️ 任務已是「{task.status.value}」狀態"
        task.cancel_event.set()
        task.status = TaskStatus.CANCELLED
        return f"✅ 已取消任務：{task.name}（{task_id}）"

    def cancel_all(self) -> str:
        """取消所有執行中的任務"""
        running = [t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]
        if not running:
            return "目前沒有執行中的任務"
        for t in running:
            t.cancel_event.set()
            t.status = TaskStatus.CANCELLED
        return f"✅ 已取消 {len(running)} 個任務"

    def list_tasks(self) -> str:
        """列出所有任務狀態"""
        if not self.tasks:
            return "📋 目前沒有任何任務"
        lines = ["📋 任務清單：\n"]
        for t in sorted(self.tasks.values(), key=lambda x: x.created_at, reverse=True)[:10]:
            icon = {"待執行": "⏳", "執行中": "🔄", "已完成": "✅", "已取消": "⛔", "失敗": "❌"}.get(t.status.value, "❓")
            lines.append(f"{icon} [{t.id}] {t.name}（{t.created_at}）")
            if t.result:
                lines.append(f"   → {t.result[:80]}")
        return "\n".join(lines)


# 全域單例
task_manager = TaskManager()
