"""
skills/info/info.py — 資訊查詢 Skill
路徑：skills/info/info.py

工具：
  - get_current_time  : 取得目前時間
  - get_system_info   : 系統資訊（OS、CPU、記憶體、磁碟）
  - get_weather       : 即時天氣 + 3 日預報（Open-Meteo，免費無需 API key）
  - web_search        : DuckDuckGo 搜尋（Instant Answer API + HTML fallback）
"""
from __future__ import annotations

import datetime
import logging
import platform
import re
import shutil
from typing import Any

import httpx  # type: ignore

from skills.base import Skill

logger = logging.getLogger(__name__)

# ── WMO 天氣代碼（中文）────────────────────────────────────────────────
_WMO_CODES: dict[int, str] = {
    0: "晴天", 1: "大致晴朗", 2: "部分多雲", 3: "陰天",
    45: "霧", 48: "霧淞",
    51: "毛毛雨（輕）", 53: "毛毛雨", 55: "毛毛雨（濃）",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "陣雨（輕）", 81: "陣雨", 82: "陣雨（強）",
    95: "雷陣雨", 96: "雷陣雨夾冰雹", 99: "雷陣雨夾大冰雹",
}

# ── Tool Schemas ───────────────────────────────────────────────────────
_SCHEMAS: list[dict] = [
    {
        "name": "get_current_time",
        "description": "取得目前的日期、時間與星期",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_system_info",
        "description": "查詢電腦的系統資訊：作業系統、CPU、記憶體用量、磁碟用量",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "查詢指定城市的即時天氣與未來 3 天預報。"
            "使用 Open-Meteo 免費 API，不需要 API key。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名稱，例如：台北、Tokyo、New York、London",
                }
            },
            "required": ["city"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "使用 DuckDuckGo 搜尋網路資訊。"
            "適合查詢新聞、最新資訊、不確定的事實。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字",
                },
                "max_results": {
                    "type": "integer",
                    "description": "回傳筆數，預設 5，最多 10",
                },
            },
            "required": ["query"],
        },
    },
]


# ══════════════════════════════════════════════════════════════════════
# InfoSkill
# ══════════════════════════════════════════════════════════════════════

class InfoSkill(Skill):
    """資訊查詢技能：時間、系統資訊、天氣、網路搜尋"""

    requires_confirmation = False
    privacy_level = "public"

    def get_schemas(self) -> list[dict]:
        return _SCHEMAS

    async def execute(self, tool_name: str, **kwargs: Any) -> str:
        match tool_name:
            case "get_current_time":
                return self._get_time()
            case "get_system_info":
                return self._get_system_info()
            case "get_weather":
                city = kwargs.get("city", "台北")
                return await self._get_weather(city)
            case "web_search":
                query = kwargs.get("query", "")
                max_results = int(kwargs.get("max_results", 5))
                return await self._web_search(query, max_results)
            case _:
                raise ValueError(f"InfoSkill 未處理工具：{tool_name}")

    # ── 時間 ──────────────────────────────────────────────────────────

    def _get_time(self) -> str:
        now = datetime.datetime.now()
        weekdays = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
        wd = weekdays[now.weekday()]
        return (
            f"🕐 現在時間：{now.strftime('%Y-%m-%d')} {wd} "
            f"{now.strftime('%H:%M:%S')}"
        )

    # ── 系統資訊 ──────────────────────────────────────────────────────

    def _get_system_info(self) -> str:
        uname = platform.uname()
        total, used, free = shutil.disk_usage("/")

        lines = [
            f"💻 系統：{uname.system} {uname.release}",
            f"🖥  主機名稱：{uname.node}",
            f"⚙️  處理器：{uname.processor or uname.machine}",
            f"💾 磁碟：已用 {used >> 30} GB / 共 {total >> 30} GB"
            f"（剩餘 {free >> 30} GB）",
        ]

        try:
            import psutil  # type: ignore
            ram = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            lines.append(
                f"🧠 記憶體：已用 {ram.used >> 20} MB / "
                f"共 {ram.total >> 20} MB（{ram.percent:.1f}%）"
            )
            lines.append(f"⚡ CPU 使用率：{cpu:.1f}%")
        except ImportError:
            lines.append("（安裝 psutil 可顯示 CPU/記憶體詳情）")

        return "\n".join(lines)

    # ── 天氣 ──────────────────────────────────────────────────────────

    async def _get_weather(self, city: str) -> str:
        try:
            # Step 1: 地理編碼
            async with httpx.AsyncClient(timeout=10) as client:
                geo_resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": city,
                        "count": 1,
                        "language": "zh",
                        "format": "json",
                    },
                )
                geo_resp.raise_for_status()
                geo = geo_resp.json()

            if not geo.get("results"):
                return f"❌ 找不到城市：{city}"

            loc = geo["results"][0]
            lat = loc["latitude"]
            lon = loc["longitude"]
            name = loc.get("name", city)
            country = loc.get("country", "")

            # Step 2: 取得天氣資料
            async with httpx.AsyncClient(timeout=10) as client:
                w_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": ",".join([
                            "temperature_2m",
                            "apparent_temperature",
                            "relative_humidity_2m",
                            "wind_speed_10m",
                            "weathercode",
                        ]),
                        "daily": ",".join([
                            "weathercode",
                            "temperature_2m_max",
                            "temperature_2m_min",
                        ]),
                        "timezone": "auto",
                        "forecast_days": 4,
                    },
                )
                w_resp.raise_for_status()
                w = w_resp.json()

            cur = w["current"]
            daily = w["daily"]
            desc = _WMO_CODES.get(cur.get("weathercode", 0), "未知")

            lines = [
                f"🌍 {name}，{country}",
                f"🌤  {desc}",
                f"🌡  {cur['temperature_2m']}°C"
                f"（體感 {cur['apparent_temperature']}°C）",
                f"💧 濕度 {cur['relative_humidity_2m']}%"
                f"  💨 風速 {cur['wind_speed_10m']} km/h",
                "",
                "📅 未來 3 天：",
            ]
            for i in range(1, 4):
                day_desc = _WMO_CODES.get(daily["weathercode"][i], "")
                lines.append(
                    f"  {daily['time'][i]}  {day_desc}  "
                    f"{daily['temperature_2m_min'][i]}°C"
                    f" ~ {daily['temperature_2m_max'][i]}°C"
                )

            return "\n".join(lines)

        except httpx.HTTPStatusError as e:
            return f"❌ 天氣 API 回應錯誤：{e.response.status_code}"
        except Exception as e:
            logger.exception("[InfoSkill] get_weather 失敗")
            return f"❌ 天氣查詢失敗：{e}"

    # ── 網路搜尋 ──────────────────────────────────────────────────────

    async def _web_search(self, query: str, max_results: int = 5) -> str:
        max_results = min(max(1, max_results), 10)

        # 先嘗試 Instant Answer API
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results: list[str] = []

            if data.get("AbstractText"):
                results.append(f"📌 {data['AbstractText']}")
                if data.get("AbstractURL"):
                    results.append(f"   來源：{data['AbstractURL']}")

            for topic in (data.get("RelatedTopics") or [])[:max_results]:
                if isinstance(topic, dict) and topic.get("Text"):
                    text = topic["Text"][:200]
                    url = topic.get("FirstURL", "")
                    results.append(f"• {text}")
                    if url:
                        results.append(f"  {url}")

            if results:
                return f"🔍 搜尋「{query}」：\n\n" + "\n\n".join(results)

        except Exception:
            pass  # fallback to HTML search

        # HTML fallback
        return await self._ddg_html_search(query, max_results)

    async def _ddg_html_search(self, query: str, max_results: int) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=10,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible)"},
            ) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                )
                resp.raise_for_status()
                html = resp.text

            titles = re.findall(
                r'class="result__a"[^>]*>(.*?)</a>', html
            )
            snippets = re.findall(
                r'class="result__snippet"[^>]*>(.*?)</span>', html
            )

            lines: list[str] = []
            for i, title in enumerate(titles[:max_results]):
                t = re.sub(r"<[^>]+>", "", title).strip()
                s = (
                    re.sub(r"<[^>]+>", "", snippets[i]).strip()
                    if i < len(snippets)
                    else ""
                )
                if t:
                    lines.append(f"• {t}")
                    if s:
                        lines.append(f"  {s}")

            if lines:
                return f"🔍 搜尋「{query}」：\n\n" + "\n\n".join(lines)

            return f"🔍 找不到「{query}」的相關搜尋結果"

        except Exception as e:
            logger.exception("[InfoSkill] web_search HTML fallback 失敗")
            return f"❌ 搜尋失敗：{e}"


SKILL_CLASS = InfoSkill