"""
資訊查詢工具：時間、天氣、網路搜尋、系統資訊
"""
import datetime
import httpx # type: ignore
import os
import re

FILES_DIR = "agent_files"

# ── 時間 ──────────────────────────────────────────────────────────────
def get_current_time(**_) -> str:
    now = datetime.datetime.now()
    return f"現在時間：{now.strftime('%Y-%m-%d %H:%M:%S')}"


# ── 系統資訊 ──────────────────────────────────────────────────────────
def get_system_info(**_) -> str:
    import platform, shutil
    uname  = platform.uname()
    total, used, free = shutil.disk_usage("/")
    lines = [
        f"💻 系統：{uname.system} {uname.release}",
        f"🖥 電腦名稱：{uname.node}",
        f"⚙️ 處理器：{uname.processor or uname.machine}",
        f"💾 磁碟（C:\\）：已用 {used>>30} GB / 共 {total>>30} GB（剩 {free>>30} GB）",
    ]
    try:
        import psutil # type: ignore
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        lines.append(f"🧠 記憶體：已用 {ram.used>>20} MB / 共 {ram.total>>20} MB（{ram.percent}%）")
        lines.append(f"⚡ CPU 使用率：{cpu}%")
    except ImportError:
        pass
    return "\n".join(lines)


# ── 天氣 ──────────────────────────────────────────────────────────────
_WMO_CODES = {
    0: "晴天", 1: "大致晴朗", 2: "部分多雲", 3: "陰天",
    45: "霧", 48: "霧淞",
    51: "毛毛雨（輕）", 53: "毛毛雨", 55: "毛毛雨（濃）",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "陣雨（輕）", 81: "陣雨", 82: "陣雨（強）",
    95: "雷陣雨", 96: "雷陣雨夾冰雹", 99: "雷陣雨夾大冰雹"
}

def get_weather(city: str) -> str:
    try:
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
            timeout=10
        ).json()
        if not geo.get("results"):
            return f"❌ 找不到城市：{city}"
        loc  = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name = loc.get("name", city)
        country = loc.get("country", "")

        w = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weathercode",
                "daily":   "weathercode,temperature_2m_max,temperature_2m_min",
                "timezone": "auto", "forecast_days": 4
            }, timeout=10
        ).json()

        cur   = w["current"]
        daily = w["daily"]
        desc  = _WMO_CODES.get(cur.get("weathercode", 0), "")
        lines = [
            f"🌍 {name}，{country}",
            f"🌤 {desc}",
            f"🌡 {cur['temperature_2m']}°C（體感 {cur['apparent_temperature']}°C）",
            f"💧 濕度 {cur['relative_humidity_2m']}%  💨 風速 {cur['wind_speed_10m']} km/h",
            "", "📅 未來 3 天："
        ]
        for i in range(1, 4):
            lines.append(
                f"  {daily['time'][i]}  "
                f"{_WMO_CODES.get(daily['weathercode'][i], '')}  "
                f"{daily['temperature_2m_min'][i]}°C ~ {daily['temperature_2m_max'][i]}°C"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 天氣查詢失敗：{e}"


# ── 網路搜尋 ──────────────────────────────────────────────────────────
def web_search(query: str, max_results: int = 5) -> str:
    max_results = min(int(max_results), 10)
    try:
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10
        )
        data    = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append(f"📌 {data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"   {data['AbstractURL']}")
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"• {topic['Text'][:200]}\n  {topic.get('FirstURL','')}")
        if results:
            return f"🔍 搜尋「{query}」：\n\n" + "\n\n".join(results)
        return _ddg_html_search(query, max_results)
    except Exception as e:
        return f"❌ 搜尋失敗：{e}"

def _ddg_html_search(query: str, max_results: int) -> str:
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10, follow_redirects=True
        )
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', resp.text)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', resp.text)
        lines = []
        for i, title in enumerate(titles[:max_results]):
            t = re.sub(r'<[^>]+>', '', title).strip()
            s = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
            lines.append(f"• {t}\n  {s}")
        return f"🔍 搜尋「{query}」：\n\n" + "\n\n".join(lines) if lines else f"找不到「{query}」的結果"
    except Exception as e:
        return f"❌ 備用搜尋失敗：{e}"


# ── 檔案操作 ──────────────────────────────────────────────────────────
def write_file(filename: str, content: str) -> str:
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(os.path.join(FILES_DIR, filename), "w", encoding="utf-8") as f:
        f.write(content)
    return f"✅ 已寫入 {filename}"

def read_file(filename: str) -> str:
    path = os.path.join(FILES_DIR, filename)
    if not os.path.exists(path):
        return f"❌ 找不到：{filename}"
    with open(path, "r", encoding="utf-8") as f:
        return f"📄 {filename}：\n{f.read()}"

def list_files(**_) -> str:
    os.makedirs(FILES_DIR, exist_ok=True)
    files = os.listdir(FILES_DIR)
    return "📂 agent_files：\n" + "\n".join(f"  - {f}" for f in files) if files else "📂 資料夾是空的"


# ── 記憶操作（讓使用者可以從 Telegram 管理記憶）──────────────────────
def list_memories(**_) -> str:
    try:
        from core.memory import list_all_memories
        return list_all_memories()
    except Exception as e:
        return f"❌ 記憶系統未啟動：{e}"

def clear_memories(**_) -> str:
    try:
        from core.memory import clear_memories as _clear
        return _clear()
    except Exception as e:
        return f"❌ 清除失敗：{e}"


# ── RAG 知識庫操作 ────────────────────────────────────────────────────
def import_document(file_path: str, source_name: str = "") -> str:
    """匯入本機文件到知識庫（.txt / .md / .pdf）"""
    try:
        from core.rag import add_document
        return add_document(file_path, source_name)
    except Exception as e:
        return f"❌ 匯入失敗：{e}"

def import_text_to_knowledge(content: str, source_name: str) -> str:
    """把一段文字直接加入知識庫"""
    try:
        from core.rag import add_text
        return add_text(content, source_name)
    except Exception as e:
        return f"❌ 加入失敗：{e}"

def list_knowledge_documents(**_) -> str:
    """列出知識庫裡的所有文件"""
    try:
        from core.rag import list_documents
        return list_documents()
    except Exception as e:
        return f"❌ 查詢失敗：{e}"

def delete_knowledge_document(source_name: str) -> str:
    """從知識庫刪除指定文件"""
    try:
        from core.rag import delete_document
        return delete_document(source_name)
    except Exception as e:
        return f"❌ 刪除失敗：{e}"


# ── 自動研究（網路搜尋 → 整理 → 存入知識庫）─────────────────────────
def research_topic(topic: str, depth: int = 3) -> str:
    """
    給一個主題，自動上網搜尋多個角度，整理後存入知識庫。
    depth: 搜尋幾個子問題（1~5），越高資料越豐富但越慢
    """

    depth = max(1, min(5, int(depth)))

    # ── 第一步：產生多角度搜尋關鍵字 ────────────────────────────────
    # 根據主題自動展開成幾個搜尋面向
    search_queries = _expand_queries(topic, depth)
    print(f"[Research] 主題：{topic}，搜尋 {len(search_queries)} 個面向")

    all_content = []

    for i, query in enumerate(search_queries):
        print(f"[Research] 搜尋 {i+1}/{len(search_queries)}：{query}")

        # 用 DuckDuckGo 搜尋
        raw = _ddg_search_raw(query)
        if raw:
            all_content.append(f"## {query}\n{raw}")

    if not all_content:
        return f"❌ 搜尋「{topic}」失敗，找不到任何資料"

    # ── 第二步：整理成一份完整內容存進知識庫 ────────────────────────
    combined = f"# {topic}\n\n" + "\n\n".join(all_content)

    try:
        from core.rag import add_text
        result = add_text(combined, source_name=f"研究：{topic}")
    except Exception as e:
        return f"❌ 存入知識庫失敗：{e}"

    return (
        f"✅ 已完成「{topic}」的自動研究\n"
        f"   搜尋了 {len(search_queries)} 個面向\n"
        f"   收集了 {len(combined)} 字元的資料\n"
        f"   已存入知識庫，之後問相關問題會自動參考"
    )


def _expand_queries(topic: str, depth: int) -> list[str]:
    """把一個主題展開成多個搜尋角度"""
    base_templates = [
        "{topic}",
        "{topic} 入門介紹",
        "{topic} 最新資訊",
        "{topic} 教學攻略",
        "{topic} 常見問題",
    ]
    queries = []
    for t in base_templates[:depth]:
        queries.append(t.format(topic=topic))
    return queries


def _ddg_search_raw(query: str) -> str:
    """搜尋 DuckDuckGo，回傳純文字摘要"""
    import httpx, re # type: ignore

    try:
        # 先試 Instant Answer API
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10
        )
        data  = resp.json()
        parts = []

        if data.get("AbstractText"):
            parts.append(data["AbstractText"])

        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                parts.append(topic["Text"])

        if parts:
            return "\n".join(parts)

        # 備用：HTML 搜尋
        resp2 = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
            follow_redirects=True
        )
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', resp2.text)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', resp2.text)
        lines    = []
        for i, title in enumerate(titles[:5]):
            t = re.sub(r'<[^>]+>', '', title).strip()
            s = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
            if t or s:
                lines.append(f"{t}：{s}")
        return "\n".join(lines)

    except Exception as e:
        print(f"[Research] 搜尋失敗：{e}")
        return ""


# ── 個人化設定 ────────────────────────────────────────────────────────
def get_persona(**_) -> str:
    """查看目前的個人化設定"""
    try:
        from core.persona import load
        p = load()
        lines = ["👤 目前個人化設定：\n"]
        lines.append(f"  稱呼：{p.get('name', '老闆')}")
        lines.append(f"  城市：{p.get('city', '（未設定）')}")
        lines.append(f"  風格：{p.get('style', '')}")
        lines.append(f"  語言：{p.get('language', '繁體中文')}")
        extra = p.get("extra", [])
        if extra:
            lines.append(f"  額外指示：{', '.join(extra)}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 讀取設定失敗：{e}"


def update_persona(key: str, value: str) -> str:
    """更新個人化設定（name / city / style / language）"""
    try:
        from core.persona import update
        return update(key, value)
    except Exception as e:
        return f"❌ 更新失敗：{e}"


def add_persona_instruction(instruction: str) -> str:
    """新增額外指示，例如「回覆要簡短」"""
    try:
        from core.persona import load, save
        p = load()
        p["extra"].append(instruction)
        save(p)
        return f"✅ 已新增指示：{instruction}"
    except Exception as e:
        return f"❌ 新增失敗：{e}"


# ── 臨時提醒 ─────────────────────────────────────────────────────────
def add_reminder(message: str, time_str: str) -> str:
    """新增一次性提醒，到時間自動推播 Telegram"""
    try:
        from scheduler.reminder import add_reminder as _add
        return _add(message, time_str)
    except Exception as e:
        return f"❌ 新增提醒失敗：{e}"

def list_reminders(**_) -> str:
    """列出所有待觸發的提醒"""
    try:
        from scheduler.reminder import list_reminders as _list
        return _list()
    except Exception as e:
        return f"❌ 查詢提醒失敗：{e}"

def cancel_reminder(reminder_id: str) -> str:
    """取消指定提醒"""
    try:
        from scheduler.reminder import cancel_reminder as _cancel
        return _cancel(reminder_id)
    except Exception as e:
        return f"❌ 取消提醒失敗：{e}"

		
# ── 動態 Skill ────────────────────────────────────────────────────────
def generate_skill(name: str, description: str, code: str) -> str:
    """生成 Python 腳本並存檔，等待人工確認後才執行"""
    try:
        from core.dynamic_skill import generate_skill as _gen # type: ignore
        return _gen(name, description, code)
    except Exception as e:
        return f"❌ 生成腳本失敗：{e}"

# def execute_skill(filename: str) -> str:
#     """執行已確認的腳本"""
#     try:
#         from core.dynamic_skill import execute_skill as _exec # type: ignore
#         return _exec(filename)
#     except Exception as e:
#         return f"❌ 執行腳本失敗：{e}"

def list_skills(**_) -> str:
    """列出所有已生成的腳本"""
    try:
        from core.dynamic_skill import list_skills as _list # type: ignore
        return _list()
    except Exception as e:
        return f"❌ 查詢腳本失敗：{e}"