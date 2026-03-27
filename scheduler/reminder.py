"""
臨時排程提醒管理器
路徑：scheduler/reminder.py

允許從 Telegram 動態新增一次性提醒。
例如：「請在明天下午 2 點提醒我準備出門」
"""
import json
import os
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore

from core.paths import REMINDER_FILE

_scheduler: AsyncIOScheduler = None
_bot       = None
_user_id   = None


def init(scheduler: AsyncIOScheduler, bot, user_id: int):
    """由 telegram_bot 啟動時注入"""
    global _scheduler, _bot, _user_id
    _scheduler = scheduler
    _bot       = bot
    _user_id   = user_id

    # 載入已存的提醒並重新排程
    _reload_reminders()


def _load() -> list:
    if not os.path.exists(REMINDER_FILE):
        return []
    with open(REMINDER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(reminders: list):
    with open(REMINDER_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=2)


def _reload_reminders():
    """程式重啟後重新載入未來的提醒"""
    reminders = _load()
    now       = datetime.datetime.now()
    for r in reminders:
        trigger_time = datetime.datetime.fromisoformat(r["time"])
        if trigger_time > now:
            _schedule_one(r["id"], r["message"], trigger_time)


def _schedule_one(reminder_id: str, message: str, trigger_time: datetime.datetime):
    """把單一提醒加進排程器"""
    if _scheduler is None:
        return

    async def _fire():
        if _bot and _user_id:
            await _bot.send_message(
                chat_id=_user_id,
                text=f"⏰ 提醒時間到！\n\n{message}"
            )
        # 觸發後從清單移除
        reminders = _load()
        reminders = [r for r in reminders if r["id"] != reminder_id]
        _save(reminders)

    _scheduler.add_job(
        _fire,
        trigger="date",
        run_date=trigger_time,
        id=f"reminder_{reminder_id}",
        replace_existing=True
    )


def add_reminder(message: str, time_str: str) -> str:
    """
    新增一次性提醒。
    time_str 格式：YYYY-MM-DD HH:MM 或 明天 HH:MM 或 今天 HH:MM
    """
    import uuid

    # 解析時間
    trigger_time = _parse_time(time_str)
    if trigger_time is None:
        return (
            f"❌ 無法解析時間：{time_str}\n"
            f"格式範例：\n"
            f"  2026-03-24 13:00\n"
            f"  今天 15:30\n"
            f"  明天 09:00"
        )

    if trigger_time <= datetime.datetime.now():
        return f"❌ 指定時間已過：{trigger_time.strftime('%Y-%m-%d %H:%M')}"

    reminder_id = str(uuid.uuid4())[:8]
    reminder    = {
        "id":      reminder_id,
        "message": message,
        "time":    trigger_time.isoformat()
    }

    # 存檔
    reminders = _load()
    reminders.append(reminder)
    _save(reminders)

    # 加進排程
    _schedule_one(reminder_id, message, trigger_time)

    return (
        f"✅ 已設定提醒\n"
        f"📝 內容：{message}\n"
        f"⏰ 時間：{trigger_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"🆔 ID：{reminder_id}"
    )


def list_reminders() -> str:
    """列出所有待觸發的提醒"""
    reminders = _load()
    now       = datetime.datetime.now()

    # 只顯示未來的提醒
    future = [r for r in reminders
              if datetime.datetime.fromisoformat(r["time"]) > now]

    if not future:
        return "📭 目前沒有設定任何提醒"

    lines = [f"⏰ 待觸發的提醒（共 {len(future)} 個）：\n"]
    for r in sorted(future, key=lambda x: x["time"]):
        t = datetime.datetime.fromisoformat(r["time"])
        lines.append(
            f"  [{r['id']}] {t.strftime('%m/%d %H:%M')} — {r['message']}"
        )
    return "\n".join(lines)


def cancel_reminder(reminder_id: str) -> str:
    """取消指定提醒"""
    reminders = _load()
    original  = len(reminders)
    reminders = [r for r in reminders if r["id"] != reminder_id]

    if len(reminders) == original:
        return f"❌ 找不到提醒 ID：{reminder_id}"

    _save(reminders)

    # 從排程器移除
    if _scheduler:
        try:
            _scheduler.remove_job(f"reminder_{reminder_id}")
        except Exception:
            pass

    return f"✅ 已取消提醒：{reminder_id}"


def _parse_time(time_str: str) -> datetime.datetime | None:
    """解析各種時間格式"""
    time_str = time_str.strip()
    now      = datetime.datetime.now()

    # 格式一：YYYY-MM-DD HH:MM
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.datetime.strptime(time_str, fmt)
        except ValueError:
            pass

    # 格式二：今天/明天 HH:MM
    for prefix, delta in [("今天", 0), ("明天", 1), ("後天", 2)]:
        if time_str.startswith(prefix):
            time_part = time_str[len(prefix):].strip()
            try:
                t = datetime.datetime.strptime(time_part, "%H:%M")
                base = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                return base + datetime.timedelta(days=delta)
            except ValueError:
                pass

    # 格式三：純時間 HH:MM（預設今天，如果已過就明天）
    try:
        t    = datetime.datetime.strptime(time_str, "%H:%M")
        base = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if base <= now:
            base += datetime.timedelta(days=1)
        return base
    except ValueError:
        pass

    return None
