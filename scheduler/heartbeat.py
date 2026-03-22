"""
Heartbeat 排程系統
路徑：scheduler/heartbeat.py

排程內容：
- 每天 10:00 早安：天氣 + 信件摘要 + 行程建議
- 每天 22:00 晚安：今日回顧，詢問待記錄事項
"""
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore
from apscheduler.triggers.cron      import CronTrigger # type: ignore

_bot     = None
_user_id = None


def init(bot, user_id: int):
    global _bot, _user_id
    _bot     = bot
    _user_id = user_id


async def _send(text: str):
    if _bot and _user_id:
        for i in range(0, len(text), 4000):
            await _bot.send_message(chat_id=_user_id, text=text[i:i+4000])


# ══════════════════════════════════════════════════════════════════════
# 早安 Heartbeat（每天 10:00）
# ══════════════════════════════════════════════════════════════════════

async def morning_heartbeat():
    print("[Heartbeat] 早安 Heartbeat 啟動")

    # ── 讀取個人化設定 ────────────────────────────────────────────────
    try:
        from core.persona import load as load_persona
        persona = load_persona()
        name    = persona.get("name", "老闆")
        city    = persona.get("city", "新北市")
    except Exception:
        name = "老闆"
        city = "新北市"

    today = datetime.datetime.now().strftime("%Y-%m-%d %A")
    parts = [f"🌅 早安，{name}！今天是 {today}\n"]

    # ── 1. 天氣 ───────────────────────────────────────────────────────
    try:
        from tools.info import get_weather

        # 優先用 persona.json 的城市，沒有再從記憶庫找
        if not city:
            try:
                from core.memory import search_memory
                hint = search_memory("我住在哪裡 我的城市")
                city = _extract_city(hint)
            except Exception:
                pass

        if not city:
            city = "台北"   # 最終預設值

        weather = get_weather(city)
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
    todos = habits = schedule_hint = ""
    try:
        from core.memory import search_memory
        todos         = search_memory("待辦 要做 記得 任務")
        habits        = search_memory("習慣 每天 固定 例行")
        schedule_hint = search_memory("行程 會議 預約 約好")
    except Exception:
        pass

    # ── 4. 用 LLM 產生今日行程建議 ────────────────────────────────────
    try:
        suggestion = await _generate_schedule(
            name, city, inbox_summary, todos, habits, schedule_hint
        )
        parts.append(f"📅 今日行程建議\n{suggestion}\n")
        parts.append(f"💬 {name}，需要調整行程的話直接告訴我，我會記錄下來！")
    except Exception as e:
        print(f"[Heartbeat] 行程建議失敗：{e}")

    await _send("\n".join(parts))
    print("[Heartbeat] 早安推播完成")


async def _generate_schedule(
    name: str, city: str,
    inbox_summary: str, todos: str,
    habits: str, schedule_hint: str
) -> str:
    """呼叫本地 LLM 產生今日行程建議"""
    from config import LLM_PROVIDER
    today  = datetime.datetime.now().strftime("%Y-%m-%d")
    prompt = f"""今天是 {today}，請以個人助理身份稱呼用戶為「{name}」。
請根據以下資訊，幫用戶規劃今天的行程建議，格式清楚易讀。

【未讀信件摘要】
{inbox_summary or '無'}

【待辦事項】
{todos or '無'}

【用戶習慣】
{habits or '無'}

【已知行程】
{schedule_hint or '無'}

請輸出簡潔的今日行程建議，用時間軸格式，稱呼用戶為「{name}」。
不需要把每個小時都填滿，用繁體中文回答。"""


    # 行程建議固定用本地 Ollama，不走雲端
    try:
        from core.llm_ollama import run
        import os
        os.environ["_ACTIVE_PROVIDER"] = "ollama"
        reply, _ = run([{"role": "user", "content": prompt}])
        return reply
    except Exception as e:
        # Ollama 失敗時改用雲端備援
        try:
            from config import CLOUD_PROVIDER
            if CLOUD_PROVIDER == "groq":
                from core.llm_groq import run as cloud_run
            elif CLOUD_PROVIDER == "gemini":
                from core.llm_gemini import run as cloud_run
            else:
                return f"（行程建議產生失敗：{e}）"
            import os
            os.environ["_ACTIVE_PROVIDER"] = CLOUD_PROVIDER
            reply, _ = cloud_run([{"role": "user", "content": prompt}])
            return reply
        except Exception as e2:
            return f"（行程建議產生失敗：{e2}）"


def _extract_city(memory_text: str) -> str:
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
    print("[Heartbeat] 晚安 Heartbeat 啟動")

    try:
        from core.persona import get_name
        name = get_name()
    except Exception:
        name = "老闆"

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    msg   = (
        f"🌙 {name}，晚安！今天是 {today}\n\n"
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
