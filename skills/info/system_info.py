"""
System Info Skill - 系統資訊與時間
"""

from __future__ import annotations

import logging
import platform
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from skills.base import Skill

logger = logging.getLogger(__name__)

# Tool call schema，供 LLMGateway 註冊用
TOOL_SCHEMA = {
    "name": "get_system_info",
    "description": "取得現在時間、系統資訊（OS、Python 版本等）。",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_time", "get_system_info"],
                "description": "get_time：查詢現在時間；get_system_info：查詢系統資訊",
            },
            "timezone": {
                "type": "string",
                "description": "時區名稱，例如 Asia/Taipei（選填，預設使用設定值）",
            },
        },
        "required": ["action"],
    },
}


class SystemInfoSkill(Skill):
    """系統資訊與時間技能"""

    name = "system_info"
    description = "查詢現在時間與系統資訊"
    requires_confirmation = False

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        cfg = config or {}
        # 預設時區從 settings.yaml agent.timezone 傳入，fallback Asia/Taipei
        self.default_timezone: str = cfg.get("timezone", "Asia/Taipei")

    # ------------------------------------------------------------------
    # Skill 介面
    # ------------------------------------------------------------------

    async def execute(self, action: str, **kwargs) -> Any:
        if action == "get_time":
            return await self.get_time(kwargs.get("timezone"))
        if action == "get_system_info":
            return await self.get_system_info()
        return {"error": f"未知動作: {action}"}

    def get_available_actions(self) -> list[str]:
        return ["get_time", "get_system_info"]

    # ------------------------------------------------------------------
    # 時間查詢
    # ------------------------------------------------------------------

    async def get_time(self, timezone: str | None = None) -> str:
        tz_name = timezone or self.default_timezone
        logger.info("查詢時間: %s", tz_name)

        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            logger.warning("未知時區 '%s'，使用 UTC", tz_name)
            tz = ZoneInfo("UTC")
            tz_name = "UTC"

        now = datetime.now(tz)
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        weekday = weekdays[now.weekday()]

        return (
            f"🕐 現在時間（{tz_name}）\n"
            f"📅 {now.strftime('%Y-%m-%d')} 星期{weekday}\n"
            f"⏰ {now.strftime('%H:%M:%S')}"
        )

    # ------------------------------------------------------------------
    # 系統資訊
    # ------------------------------------------------------------------

    async def get_system_info(self) -> str:
        logger.info("查詢系統資訊")
        info = {
            "OS":        f"{platform.system()} {platform.release()}",
            "版本":      platform.version(),
            "架構":      platform.machine(),
            "Python":    platform.python_version(),
        }
        lines = ["💻 系統資訊"]
        for k, v in info.items():
            lines.append(f"  {k}：{v}")
        return "\n".join(lines)
