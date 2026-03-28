"""
提醒管理器（支援一次性和循環提醒）
路徑：scheduler/reminder.py

允許從 Telegram 動態新增一次性提醒。
例如：「請在明天下午 2 點提醒我準備出門」
"""
import json
import os
import uuid
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore
from apscheduler.triggers.cron      import CronTrigger # type: ignore
from apscheduler.triggers.date      import DateTrigger # type: ignore
from core.paths import REMINDER_FILE
from core.logger import get_logger

logger = get_logger(__name__)

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
    os.makedirs(os.path.dirname(REMINDER_FILE), exist_ok=True)
    with open(REMINDER_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=2)


def _reload_reminders():
    """程式重啟後重新載入所有提醒"""
    reminders = _load()
    now       = datetime.datetime.now()
    reloaded  = 0
    for r in reminders:
        if r.get("repeat"):
            _schedule_repeat(r)
            reloaded += 1
        else:
            trigger_time = datetime.datetime.fromisoformat(r["time"])
            if trigger_time > now:
                _schedule_one(r["id"], r["message"], trigger_time)
                reloaded += 1
    if reloaded:
        logger.info(f"[Reminder] 已載入 {reloaded} 個提醒")


def _schedule_one(reminder_id: str, message: str, trigger_time: datetime.datetime):
    """排程一次性提醒"""
    if _scheduler is None:
        return

    async def _fire():
        if _bot and _user_id:
            await _bot.send_message(
                chat_id=_user_id,
                text=f"⏰ 提醒！\n\n{message}"
            )
        # 觸發後從清單移除
        reminders = _load()
        _save([r for r in reminders if r["id"] != reminder_id])

    _scheduler.add_job(
        _fire,
        trigger=DateTrigger(run_date=trigger_time),
        id=f"reminder_{reminder_id}",
        replace_existing=True
    )


def _schedule_repeat(r: dict):
    """排程循環提醒"""
    if _scheduler is None:
        return

    repeat     = r["repeat"]  # daily / weekly / monthly
    message    = r["message"]
    reminder_id = r["id"]
    hour       = r.get("hour", 9)
    minute     = r.get("minute", 0)
    day_of_week = r.get("day_of_week", None)   # 0=週一 ~ 6=週日
    day        = r.get("day", None)             # 每月幾號

    async def _fire():
        if _bot and _user_id:
            await _bot.send_message(
                chat_id=_user_id,
                text=f"🔔 循環提醒\n\n{message}"
            )
        logger.info(f"[Reminder] 循環提醒觸發：{message[:30]}")

    if repeat == "daily":
        trigger = CronTrigger(hour=hour, minute=minute, timezone="Asia/Taipei")
    elif repeat == "weekly":
        dow     = day_of_week if day_of_week is not None else 6  # 預設週日
        trigger = CronTrigger(day_of_week=dow, hour=hour, minute=minute, timezone="Asia/Taipei")
    elif repeat == "monthly":
        d       = day if day else 1
        trigger = CronTrigger(day=d, hour=hour, minute=minute, timezone="Asia/Taipei")
    else:
        logger.warning(f"[Reminder] 未知的循環類型：{repeat}")
        return

    _scheduler.add_job(
        _fire,
        trigger=trigger,
        id=f"reminder_{reminder_id}",
        replace_existing=True
    )


# ══════════════════════════════════════════════════════════════════════
# 公開 API
# ══════════════════════════════════════════════════════════════════════

def add_reminder(message: str, time_str: str) -> str:
    """新增一次性提醒"""
    trigger_time = _parse_time(time_str)
    if trigger_time is None:
        return (
            f"❌ 無法解析時間：{time_str}\n"
            f"格式：今天 15:30 / 明天 09:00 / 2026-03-24 13:00"
        )
    if trigger_time <= datetime.datetime.now():
        return f"❌ 指定時間已過：{trigger_time.strftime('%Y-%m-%d %H:%M')}"

    reminder_id = str(uuid.uuid4())[:8]
    reminder    = {
        "id":      reminder_id,
        "message": message,
        "time":    trigger_time.isoformat(),
        "repeat":  None
    }

    # 存檔
    reminders = _load()
    reminders.append(reminder)
    _save(reminders)

    # 加進排程
    _schedule_one(reminder_id, message, trigger_time)

    return (
        f"✅ 已設定一次性提醒\n"
        f"📝 {message}\n"
        f"⏰ {trigger_time.strftime('%Y-%m-%d %H:%M')}\n"
        f"🆔 {reminder_id}"
    )


def add_repeat_reminder(
    message: str,
    repeat: str,
    hour: int = 9,
    minute: int = 0,
    day_of_week: int = None,
    day: int = None
) -> str:
    """
    新增循環提醒。
    repeat: daily（每天）/ weekly（每週）/ monthly（每月）
    hour/minute: 觸發時間
    day_of_week: 週幾（0=週一, 6=週日），weekly 時使用
    day: 幾號，monthly 時使用
    """
    repeat = repeat.lower()
    if repeat not in ("daily", "weekly", "monthly"):
        return "❌ repeat 請填：daily / weekly / monthly"

    reminder_id = str(uuid.uuid4())[:8]
    reminder    = {
        "id":          reminder_id,
        "message":     message,
        "time":        None,
        "repeat":      repeat,
        "hour":        hour,
        "minute":      minute,
        "day_of_week": day_of_week,
        "day":         day
    }
    reminders = _load()
    reminders.append(reminder)
    _save(reminders)
    _schedule_repeat(reminder)

    # 產生說明文字
    time_desc = f"{hour:02d}:{minute:02d}"
    if repeat == "daily":
        freq_desc = f"每天 {time_desc}"
    elif repeat == "weekly":
        days = ["週一","週二","週三","週四","週五","週六","週日"]
        dow  = day_of_week if day_of_week is not None else 6
        freq_desc = f"每{days[dow]} {time_desc}"
    else:
        d = day if day else 1
        freq_desc = f"每月 {d} 號 {time_desc}"

    return (
        f"✅ 已設定循環提醒\n"
        f"📝 {message}\n"
        f"🔄 {freq_desc}\n"
        f"🆔 {reminder_id}"
    )


def list_reminders() -> str:
    """列出所有提醒"""
    reminders = _load()
    now       = datetime.datetime.now()

    one_time = [r for r in reminders if not r.get("repeat") and
                datetime.datetime.fromisoformat(r["time"]) > now]
    repeats  = [r for r in reminders if r.get("repeat")]

    if not one_time and not repeats:
        return "📭 目前沒有任何提醒"

    lines = []
    if one_time:
        lines.append(f"⏰ 一次性提醒（{len(one_time)} 個）：")
        for r in sorted(one_time, key=lambda x: x["time"]):
            t = datetime.datetime.fromisoformat(r["time"])
            lines.append(f"  [{r['id']}] {t.strftime('%m/%d %H:%M')} — {r['message']}")

    if repeats:
        lines.append(f"\n🔄 循環提醒（{len(repeats)} 個）：")
        days_tw = ["週一","週二","週三","週四","週五","週六","週日"]
        for r in repeats:
            h, m = r.get("hour", 9), r.get("minute", 0)
            if r["repeat"] == "daily":
                freq = f"每天 {h:02d}:{m:02d}"
            elif r["repeat"] == "weekly":
                dow  = r.get("day_of_week", 6)
                freq = f"每{days_tw[dow]} {h:02d}:{m:02d}"
            else:
                d    = r.get("day", 1)
                freq = f"每月{d}號 {h:02d}:{m:02d}"
            lines.append(f"  [{r['id']}] {freq} — {r['message']}")

    return "\n".join(lines)


def cancel_reminder(reminder_id: str) -> str:
    """取消指定提醒"""
    reminders = _load()
    original  = len(reminders)
    reminders = [r for r in reminders if r["id"] != reminder_id]

    if len(reminders) == original:
        return f"❌ 找不到提醒 ID：{reminder_id}"

    _save(reminders)
    if _scheduler:
        try:
            _scheduler.remove_job(f"reminder_{reminder_id}")
        except Exception:
            pass

    return f"✅ 已取消提醒：{reminder_id}"


def _parse_time(time_str: str) -> datetime.datetime | None:
    """解析時間字串"""
    time_str = time_str.strip()
    now      = datetime.datetime.now()

    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.datetime.strptime(time_str, fmt)
        except ValueError:
            pass

    for prefix, delta in [("今天", 0), ("明天", 1), ("後天", 2)]:
        if time_str.startswith(prefix):
            try:
                t    = datetime.datetime.strptime(time_str[len(prefix):].strip(), "%H:%M")
                base = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                return base + datetime.timedelta(days=delta)
            except ValueError:
                pass

    try:
        t    = datetime.datetime.strptime(time_str, "%H:%M")
        base = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if base <= now:
            base += datetime.timedelta(days=1)
        return base
    except ValueError:
        pass

    return None
