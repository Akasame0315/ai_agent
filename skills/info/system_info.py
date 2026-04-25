"""
System Info Skill - 系統資訊
"""

import logging
import platform
from datetime import datetime
from typing import Any, Dict
from ..base import Skill

logger = logging.getLogger(__name__)


class SystemInfoSkill(Skill):
    """系統資訊技能"""
    
    name = "system_info"
    description = "取得系統資訊和時間"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "get_time":
            return await self.get_time(kwargs.get("timezone"))
        elif action == "get_system_info":
            return await self.get_system_info()
        elif action == "get_uptime":
            return await self.get_uptime()
        return {"error": f"未知動作: {action}"}
    
    async def get_time(self, timezone: str = None) -> Dict[str, Any]:
        """取得現在時間"""
        logger.info(f"查詢時間: {timezone}")
        
        now = datetime.now()
        
        return {
            "datetime": now.isoformat(),
            "timestamp": now.timestamp(),
            "timezone": timezone or "本地"
        }
    
    async def get_system_info(self) -> Dict[str, Any]:
        """取得系統資訊"""
        logger.info("查詢系統資訊")
        
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version()
        }
    
    async def get_uptime(self) -> Dict[str, Any]:
        """取得系統運行時間"""
        # TODO: 使用 psutil 取得精確運行時間
        return {"uptime": "未知"}
    
    def get_available_actions(self) -> list:
        return ["get_time", "get_system_info", "get_uptime"]