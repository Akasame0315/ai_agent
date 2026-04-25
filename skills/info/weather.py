"""
Weather Skill - 天氣查詢
使用 Open-Meteo（免費，無需 API key）
geocoding: https://geocoding-api.open-meteo.com
forecast:  https://api.open-meteo.com
"""

import logging
from typing import Any

import httpx

from skills.base import Skill
from skills.info.wmo_codes import WMO_CODES

logger = logging.getLogger(__name__)

# Tool call schema，供 LLMGateway 註冊用
TOOL_SCHEMA = {
    "name": "get_weather",
    "description": "查詢指定城市的即時天氣與未來三天預報。",
    "parameters": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名稱，例如：Taipei、Tokyo、London",
            }
        },
        "required": ["city"],
    },
}


class WeatherSkill(Skill):
    """天氣查詢技能（Open-Meteo，免費無 API key）"""

    name = "weather"
    description = "查詢城市即時天氣與三日預報"
    requires_confirmation = False

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        # 預設城市從 settings.yaml agent.city 傳入
        self.default_city: str = (config or {}).get("default_city", "Taipei")

    # ------------------------------------------------------------------
    # Skill 介面
    # ------------------------------------------------------------------

    async def execute(self, action: str, **kwargs) -> Any:
        if action == "get_weather":
            return await self.get_weather(kwargs.get("city") or self.default_city)
        if action == "get_forecast":
            # 別名，相同邏輯
            return await self.get_weather(kwargs.get("city") or self.default_city)
        return {"error": f"未知動作: {action}"}

    def get_available_actions(self) -> list[str]:
        return ["get_weather", "get_forecast"]

    # ------------------------------------------------------------------
    # 核心查詢
    # ------------------------------------------------------------------

    async def get_weather(self, city: str) -> str:
        """查詢天氣，回傳格式化字串（直接送給使用者）"""
        logger.info("查詢天氣: %s", city)

        async with httpx.AsyncClient(timeout=10) as client:
            # 1. Geocoding
            try:
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
            except Exception as e:
                logger.error("Geocoding 失敗: %s", e)
                return f"❌ 無法解析城市座標：{e}"

            if not geo.get("results"):
                return f"❌ 找不到城市：{city}"

            loc = geo["results"][0]
            lat = loc["latitude"]
            lon = loc["longitude"]
            name = loc.get("name", city)
            country = loc.get("country", "")

            # 2. Forecast
            try:
                w_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": (
                            "temperature_2m,apparent_temperature,"
                            "relative_humidity_2m,wind_speed_10m,weathercode"
                        ),
                        "daily": (
                            "weathercode,temperature_2m_max,temperature_2m_min"
                        ),
                        "timezone": "auto",
                        "forecast_days": 4,
                    },
                )
                w_resp.raise_for_status()
                w = w_resp.json()
            except Exception as e:
                logger.error("天氣 API 失敗: %s", e)
                return f"❌ 天氣查詢失敗：{e}"

        return self._format(name, country, w)

    # ------------------------------------------------------------------
    # 格式化
    # ------------------------------------------------------------------

    def _format(self, name: str, country: str, w: dict) -> str:
        cur = w["current"]
        daily = w["daily"]
        desc = WMO_CODES.get(cur.get("weathercode", 0), "未知")

        lines = [
            f"🌍 {name}，{country}",
            f"🌤 {desc}",
            f"🌡 {cur['temperature_2m']}°C（體感 {cur['apparent_temperature']}°C）",
            f"💧 濕度 {cur['relative_humidity_2m']}%  💨 風速 {cur['wind_speed_10m']} km/h",
            "",
            "📅 未來 3 天：",
        ]
        for i in range(1, 4):
            day_desc = WMO_CODES.get(daily["weathercode"][i], "未知")
            lines.append(
                f"  {daily['time'][i]}  "
                f"{day_desc}  "
                f"{daily['temperature_2m_min'][i]}°C ~ {daily['temperature_2m_max'][i]}°C"
            )

        return "\n".join(lines)
