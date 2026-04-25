"""
Weather Skill - 天氣查詢
"""

import logging
from typing import Any, Dict
from ..base import Skill

logger = logging.getLogger(__name__)


class WeatherSkill(Skill):
    """天氣查詢技能"""
    
    name = "weather"
    description = "查詢天氣資訊"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.api_key = config.get("weather_api_key") if config else None
        self.default_city = config.get("city", "Taipei") if config else "Taipei"
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "get_weather":
            return await self.get_weather(kwargs.get("city", self.default_city))
        elif action == "get_forecast":
            return await self.get_forecast(kwargs.get("city", self.default_city))
        return {"error": f"未知動作: {action}"}
    
    async def get_weather(self, city: str) -> Dict[str, Any]:
        """取得現在天氣"""
        logger.info(f"查詢天氣: {city}")
        
        if not self.api_key:
            logger.warning("未設定 OpenWeatherMap API Key")
            return {"error": "天氣服務未設定"}
        
        # TODO: 呼叫 OpenWeatherMap API
        return {
            "city": city,
            "temperature": 25,
            "condition": "晴天",
            "humidity": 65,
            "wind_speed": 10
        }
    
    async def get_forecast(self, city: str) -> Dict[str, Any]:
        """取得天氣預報"""
        logger.info(f"查詢天氣預報: {city}")
        # TODO: 呼叫 OpenWeatherMap API
        return {"city": city, "forecast": []}
    
    def get_available_actions(self) -> list:
        return ["get_weather", "get_forecast"]