import datetime
import os
import httpx

# ══════════════════════════════════════════════════════════════════════
# Tool 定義（告訴 LLM 有哪些工具可以用）
# ══════════════════════════════════════════════════════════════════════
TOOL_DEFINITIONS = [
    # ── 時間 ────────────────────────────────────────────────────────
    {
        "name": "get_current_time",
        "description": "取得現在的日期和時間",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },

    # ── 檔案 ────────────────────────────────────────────────────────
    {
        "name": "write_file",
        "description": "把內容寫入本機檔案，檔案會存在 agent_files 資料夾",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "檔案名稱，例如 note.txt"},
                "content":  {"type": "string", "description": "要寫入的內容"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "read_file",
        "description": "讀取 agent_files 資料夾裡的檔案內容",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "要讀取的檔案名稱"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "list_files",
        "description": "列出 agent_files 資料夾裡有哪些檔案",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },

    # ── 網路搜尋 ─────────────────────────────────────────────────────
    {
        "name": "web_search",
        "description": (
            "用 DuckDuckGo 搜尋網路上的資訊。"
            "適合查新聞、知識、最新資料。"
            "回傳前幾筆搜尋結果的標題和摘要。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string", "description": "搜尋關鍵字"},
                "max_results": {"type": "integer", "description": "回傳幾筆結果，預設 5，最多 10"}
            },
            "required": ["query"]
        }
    },

    # ── 天氣 ─────────────────────────────────────────────────────────
    {
        "name": "get_weather",
        "description": (
            "查詢指定城市的即時天氣和未來 3 天預報。"
            "回傳溫度、體感溫度、天氣狀況、濕度、風速。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名稱，例如：台北、Tokyo、New York"}
            },
            "required": ["city"]
        }
    },

    # ── Shell ────────────────────────────────────────────────────────
    {
        "name": "run_shell",
        "description": (
            "在本機執行 shell 指令並回傳輸出結果。"
            "適合查系統資訊、列目錄、跑腳本等。"
            "危險指令（rm -rf、格式化等）會被拒絕執行。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要執行的 shell 指令，例如：dir、python --version"}
            },
            "required": ["command"]
        }
    },

    # ── 應用程式控制 ──────────────────────────────────────────────────
    {
        "name": "open_application",
        "description": "開啟電腦裡的應用程式或檔案，例如記事本、瀏覽器、資料夾",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "程式名稱或完整路徑，例如：notepad、chrome、calc、C:\\\\Users\\\\你的名字\\\\Desktop\\\\file.txt"}
            },
            "required": ["target"]
        }
    },
    {
        "name": "list_running_apps",
        "description": "列出目前正在執行中的應用程式",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "mouse_action",
        "description": "控制滑鼠：移動到指定座標、點擊、雙擊、右鍵點擊",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "動作類型：move / click / double_click / right_click"},
                "x":      {"type": "integer", "description": "螢幕 X 座標（像素）"},
                "y":      {"type": "integer", "description": "螢幕 Y 座標（像素）"}
            },
            "required": ["action", "x", "y"]
        }
    },
    {
        "name": "keyboard_type",
        "description": "用鍵盤輸入文字，或按下特定按鍵（例如 Enter、Ctrl+C）",
        "input_schema": {
            "type": "object",
            "properties": {
                "text":    {"type": "string", "description": "要輸入的文字（和 hotkey 擇一填寫）"},
                "hotkey":  {"type": "string", "description": "要按的組合鍵，例如：ctrl+c、alt+f4、enter、win+d（和 text 擇一填寫）"},
                "interval":{"type": "number",  "description": "每個字之間的間隔秒數，預設 0.05，打中文或特殊情境可加大"}
            },
            "required": []
        }
    },
    {
        "name": "take_screenshot",
        "description": "截取目前螢幕畫面，儲存到 agent_files 資料夾，回傳檔案名稱",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "截圖檔名，例如 screen.png，預設自動用時間命名"}
            },
            "required": []
        }
    },
]


# ══════════════════════════════════════════════════════════════════════
# Tool 實作
# ══════════════════════════════════════════════════════════════════════
FILES_DIR = "agent_files"

# ── 時間 ──────────────────────────────────────────────────────────────
def get_current_time(**_) -> str:
    now = datetime.datetime.now()
    return f"現在時間：{now.strftime('%Y-%m-%d %H:%M:%S')}"


# ── 檔案 ──────────────────────────────────────────────────────────────
def write_file(filename: str, content: str) -> str:
    os.makedirs(FILES_DIR, exist_ok=True)
    with open(os.path.join(FILES_DIR, filename), "w", encoding="utf-8") as f:
        f.write(content)
    return f"✅ 已寫入 {filename}"

def read_file(filename: str) -> str:
    path = os.path.join(FILES_DIR, filename)
    if not os.path.exists(path):
        return f"❌ 找不到檔案：{filename}"
    with open(path, "r", encoding="utf-8") as f:
        return f"📄 {filename}：\n{f.read()}"

def list_files(**_) -> str:
    os.makedirs(FILES_DIR, exist_ok=True)
    files = os.listdir(FILES_DIR)
    return "📂 現有檔案：\n" + "\n".join(f"  - {f}" for f in files) if files else "📂 資料夾是空的"


# ── 網路搜尋（DuckDuckGo，免費無需 API key）──────────────────────────
def web_search(query: str, max_results: int = 5) -> str:
    max_results = min(int(max_results), 10)
    try:
        # DuckDuckGo Instant Answer API
        resp = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        results = []

        # Abstract（即時摘要）
        if data.get("AbstractText"):
            results.append(f"📌 摘要：{data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"   來源：{data['AbstractURL']}")

        # RelatedTopics（相關結果）
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                text = topic["Text"][:200]
                url  = topic.get("FirstURL", "")
                results.append(f"• {text}\n  {url}")

        if results:
            return f"🔍 搜尋「{query}」結果：\n\n" + "\n\n".join(results)

        # DuckDuckGo Instant Answer 沒有結果時，改用 HTML 搜尋頁抓標題
        return _ddg_html_search(query, max_results)

    except Exception as e:
        return f"❌ 搜尋失敗：{e}"


def _ddg_html_search(query: str, max_results: int) -> str:
    """備用：抓 DuckDuckGo HTML 搜尋結果"""
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
            follow_redirects=True
        )
        # 簡單用字串切割抓標題（避免引入 BeautifulSoup 依賴）
        content = resp.text
        snippets = []
        # 抓 <a class="result__a"> 的文字
        import re
        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', content)
        snippets_raw = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', content)
        for i, title in enumerate(titles[:max_results]):
            clean_title   = re.sub(r'<[^>]+>', '', title).strip()
            clean_snippet = re.sub(r'<[^>]+>', '', snippets_raw[i]).strip() if i < len(snippets_raw) else ""
            snippets.append(f"• {clean_title}\n  {clean_snippet}")
        if snippets:
            return f"🔍 搜尋「{query}」結果：\n\n" + "\n\n".join(snippets)
        return f"🔍 搜尋「{query}」：找不到相關結果"
    except Exception as e:
        return f"❌ 備用搜尋也失敗：{e}"


# ── 天氣（Open-Meteo，完全免費無需 API key）──────────────────────────
# 天氣代碼對照表
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
        # 第一步：地理編碼（城市名稱 → 經緯度）
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
            timeout=10
        ).json()

        if not geo.get("results"):
            return f"❌ 找不到城市：{city}"

        loc      = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        name     = loc.get("name", city)
        country  = loc.get("country", "")

        # 第二步：抓天氣資料
        weather = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":  lat,
                "longitude": lon,
                "current":   "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weathercode",
                "daily":     "weathercode,temperature_2m_max,temperature_2m_min",
                "timezone":  "auto",
                "forecast_days": 4
            },
            timeout=10
        ).json()

        cur   = weather["current"]
        daily = weather["daily"]

        # 即時天氣
        code  = cur.get("weathercode", 0)
        desc  = _WMO_CODES.get(code, f"代碼{code}")
        lines = [
            f"🌍 {name}，{country} 即時天氣",
            f"🌤 狀況：{desc}",
            f"🌡 氣溫：{cur['temperature_2m']}°C（體感 {cur['apparent_temperature']}°C）",
            f"💧 濕度：{cur['relative_humidity_2m']}%",
            f"💨 風速：{cur['wind_speed_10m']} km/h",
            "",
            "📅 未來 3 天預報："
        ]

        # 未來 3 天（跳過 index 0，那是今天）
        for i in range(1, 4):
            date     = daily["time"][i]
            hi       = daily["temperature_2m_max"][i]
            lo       = daily["temperature_2m_min"][i]
            day_desc = _WMO_CODES.get(daily["weathercode"][i], "")
            lines.append(f"  {date}  {day_desc}  {lo}°C ~ {hi}°C")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ 天氣查詢失敗：{e}"


# ── Shell 執行 ────────────────────────────────────────────────────────
# 黑名單：拒絕高風險指令
_SHELL_BLACKLIST = [
    "rm -rf /",
    "rmdir /s /q c:\\",
    "format c:",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",    
]

def run_shell(command: str) -> str:
    import subprocess
    cmd_lower = command.lower()
    for blocked in _SHELL_BLACKLIST:
        if blocked in cmd_lower:
            return f"⛔ 拒絕執行危險指令：{command}"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace"
        )
        output = result.stdout.strip() or result.stderr.strip() or "（無輸出）"
        # 限制輸出長度避免 LLM token 爆炸
        if len(output) > 1500:
            output = output[:1500] + "\n... （輸出過長，已截斷）"
        return f"💻 執行：{command}\n\n{output}"
    except subprocess.TimeoutExpired:
        return f"⏱ 指令超時（15秒）：{command}"
    except Exception as e:
        return f"❌ 執行失敗：{e}"

# ── 應用程式控制 ──────────────────────────────────────────────────────
def open_application(target: str) -> str:
    import subprocess
    try:
        subprocess.Popen(target, shell=True)
        return f"✅ 已開啟：{target}"
    except Exception as e:
        return f"❌ 開啟失敗：{e}"

def list_running_apps(**_) -> str:
    import psutil
    try:
        apps = set()
        for proc in psutil.process_iter(["name"]):
            name = proc.info["name"]
            if name and not name.lower().endswith(("svchost.exe", "system", "idle")):
                apps.add(name)
        sorted_apps = sorted(apps)
        return "🖥 執行中的程式：\n" + "\n".join(f"  - {a}" for a in sorted_apps[:40])
    except Exception as e:
        return f"❌ 查詢失敗：{e}"


# ── 滑鼠控制 ──────────────────────────────────────────────────────────
def mouse_action(action: str, x: int, y: int) -> str:
    import pyautogui
    pyautogui.FAILSAFE = True   # 滑鼠移到左上角會緊急停止
    try:
        if action == "move":
            pyautogui.moveTo(x, y, duration=0.3)
            return f"✅ 滑鼠移動到 ({x}, {y})"
        elif action == "click":
            pyautogui.click(x, y)
            return f"✅ 點擊 ({x}, {y})"
        elif action == "double_click":
            pyautogui.doubleClick(x, y)
            return f"✅ 雙擊 ({x}, {y})"
        elif action == "right_click":
            pyautogui.rightClick(x, y)
            return f"✅ 右鍵點擊 ({x}, {y})"
        else:
            return f"❌ 未知動作：{action}"
    except pyautogui.FailSafeException:
        return "⛔ 緊急停止（滑鼠移到左上角）"
    except Exception as e:
        return f"❌ 滑鼠操作失敗：{e}"


# ── 鍵盤輸入 ──────────────────────────────────────────────────────────
def keyboard_type(text: str = "", hotkey: str = "", interval: float = 0.05) -> str:
    import pyautogui
    import time
    try:
        time.sleep(0.3)   # 給視窗切換的緩衝時間
        if hotkey:
            keys = [k.strip() for k in hotkey.lower().split("+")]
            pyautogui.hotkey(*keys)
            return f"✅ 按下：{hotkey}"
        elif text:
            pyautogui.write(text, interval=interval)
            return f"✅ 已輸入文字（{len(text)} 字元）"
        else:
            return "❌ 請提供 text 或 hotkey"
    except Exception as e:
        return f"❌ 鍵盤操作失敗：{e}"


# ── 截圖 ──────────────────────────────────────────────────────────────
def take_screenshot(filename: str = "") -> str:
    import pyautogui
    os.makedirs(FILES_DIR, exist_ok=True)
    if not filename:
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(FILES_DIR, filename)
    try:
        pyautogui.screenshot(path)
        return f"✅ 截圖已儲存：{filename}"
    except Exception as e:
        return f"❌ 截圖失敗：{e}"

# ══════════════════════════════════════════════════════════════════════
# 統一呼叫入口
# ══════════════════════════════════════════════════════════════════════
TOOL_HANDLERS = {
    "get_current_time": get_current_time,
    "write_file":       write_file,
    "read_file":        read_file,
    "list_files":       list_files,
    "web_search":       web_search,
    "get_weather":      get_weather,
    "run_shell":        run_shell,
    "open_application":  open_application,
    "list_running_apps": list_running_apps,
    "mouse_action":      mouse_action,
    "keyboard_type":     keyboard_type,
    "take_screenshot":   take_screenshot,
}

def execute_tool(name: str, inputs: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"❌ 未知工具：{name}"
    try:
        return handler(**inputs)
    except Exception as e:
        return f"❌ 工具執行錯誤（{name}）：{e}"