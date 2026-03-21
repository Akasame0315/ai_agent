"""
Heartbeat 排程系統
路徑：scheduler/heartbeat.py

排程內容：
- 每天 10:00 早安：信件摘要 + 天氣 + 行程建議
- 每天 22:00 晚安：今日回顧，詢問待記錄事項
"""
import asyncio
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron      import CronTrigger

# ── 全域變數（由 telegram_bot.py 注入）────────────────────────────────
_bot     = None   # telegram.Bot 實例
_user_id = None   # 要推播的 Telegram user ID


def init(bot, user_id: int):
    """由 telegram_bot.py 啟動時呼叫，注入 bot 和 user_id"""
    global _bot, _user_id
    _bot     = bot
    _user_id = user_id


async def _send(text: str):
    """傳訊息給使用者，超過 4000 字自動切段"""
    if _bot and _user_id:
        for i in range(0, len(text), 4000):
            await _bot.send_message(chat_id=_user_id, text=text[i:i+4000])


# ══════════════════════════════════════════════════════════════════════
# 早安 Heartbeat（每天 10:00）
# ══════════════════════════════════════════════════════════════════════

async def morning_heartbeat():
    """早上推播：天氣 + 信件摘要 + 行程建議"""
    print("[Heartbeat] 早安 Heartbeat 啟動")
    today = datetime.datetime.now().strftime("%Y-%m-%d %A")
    parts = [f"🌅 早安！今天是 {today}\n"]

    # ── 1. 天氣 ───────────────────────────────────────────────────────
    try:
        from tools.info  import get_weather
        from core.memory import search_memory
        city_hint = search_memory("我住在哪裡 我的城市")
        city      = _extract_city(city_hint) or "台北"
        weather   = get_weather(city)
        parts.append(f"🌤 今日天氣\n{weather}\n")
    except Exception as e:
        print(f"[Heartbeat] 天氣失敗：{e}")

    # ── 2. 信件摘要 ───────────────────────────────────────────────────
    inbox_summary = ""
    try:
        from tools.gmail import check_inbox
        inbox_summary = check_inbox(max_results=10, unread_only=True)
        parts.append(f"📬 信件摘要\n{inbox_summary}\n")
    except Exception as e:
        parts.append("📬 信件：無法取得（請確認 Gmail 授權）\n")
        print(f"[Heartbeat] 信件失敗：{e}")

    # ── 3. 從記憶撈出待辦和習慣 ──────────────────────────────────────
    todos = habits = schedule = ""
    try:
        from core.memory import search_memory
        todos    = search_memory("待辦 要做 記得 任務")
        habits   = search_memory("習慣 每天 固定 例行")
        schedule = search_memory("行程 會議 預約 約好")
    except Exception:
        pass

    # ── 4. 用 LLM 產生今日行程建議 ────────────────────────────────────
    try:
        suggestion = await _generate_schedule(inbox_summary, todos, habits, schedule)
        parts.append(f"📅 今日行程建議\n{suggestion}\n")
        parts.append("💬 需要調整行程的話直接告訴我，我會記錄下來！")
    except Exception as e:
        print(f"[Heartbeat] 行程建議失敗：{e}")

    await _send("\n".join(parts))
    print("[Heartbeat] 早安推播完成")


async def _generate_schedule(
    inbox_summary: str, todos: str, habits: str, schedule: str
) -> str:
    """呼叫 LLM 根據信件、待辦、習慣產生今日行程建議"""
    from config import LLM_PROVIDER
    today  = datetime.datetime.now().strftime("%Y-%m-%d")
    prompt = f"""今天是 {today}。
請根據以下資訊，幫使用者規劃今天的行程建議，格式要清楚易讀。

【未讀信件摘要】
{inbox_summary or '無'}

【待辦事項（從記憶中找到的）】
{todos or '無'}

【使用者習慣】
{habits or '無'}

【已知行程】
{schedule or '無'}

請輸出簡潔的今日行程建議，用時間軸格式。
不需要把每個小時都填滿，留白也沒關係。
用繁體中文回答。"""

    try:
        if LLM_PROVIDER == "ollama":
            from core.llm_ollama import run
        elif LLM_PROVIDER == "groq":
            from core.llm_groq import run
        elif LLM_PROVIDER == "gemini":
            from core.llm_gemini import run
        else:
            from core.llm_claude import run

        reply, _ = run([{"role": "user", "content": prompt}])
        return reply
    except Exception as e:
        return f"（行程建議產生失敗：{e}）"


def _extract_city(memory_text: str) -> str:
    """從記憶文字中提取城市名稱"""
    if not memory_text:
        return ""
    cities = [
        "台北", "臺北", "新北", "桃園", "台中", "臺中",
        "台南", "臺南", "高雄", "基隆", "新竹", "苗栗",
        "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭",
        "花蓮", "台東", "臺東", "澎湖", "金門", "連江",
    ]
    for city in cities:
        if city in memory_text:
            return city
    return ""


# ══════════════════════════════════════════════════════════════════════
# 晚安 Heartbeat（每天 22:00）
# ══════════════════════════════════════════════════════════════════════

async def evening_heartbeat():
    """晚上推播：今日回顧 + 詢問要記錄的事"""
    print("[Heartbeat] 晚安 Heartbeat 啟動")
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    msg   = (
        f"🌙 晚安！今天是 {today}\n\n"
        f"今天有什麼想記錄下來的嗎？\n"
        f"例如：完成的事、明天的待辦、想讓我記住的事情。\n\n"
        f"直接回覆我就好，我會幫你記起來 📝"
    )
    await _send(msg)
    print("[Heartbeat] 晚安推播完成")


# ══════════════════════════════════════════════════════════════════════
# 排程器建立
# ══════════════════════════════════════════════════════════════════════

def create_scheduler() -> AsyncIOScheduler:
    """建立並回傳設定好的排程器"""
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")

    scheduler.add_job(
        morning_heartbeat,
        CronTrigger(hour=10, minute=0, timezone="Asia/Taipei"),
        id="morning_heartbeat",
        name="早安推播",
        replace_existing=True
    )

    scheduler.add_job(
        evening_heartbeat,
        CronTrigger(hour=22, minute=0, timezone="Asia/Taipei"),
        id="evening_heartbeat",
        name="晚安推播",
        replace_existing=True
    )

    return scheduler
