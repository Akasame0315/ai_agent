"""
資訊查詢工具：時間、天氣、網路搜尋、系統資訊
"""
import datetime
import httpx
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
        import psutil
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
