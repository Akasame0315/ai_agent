"""
Router - 技能路由、隱私判斷
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class Router:
    """負責路由請求到正確的技能"""
    
    def __init__(self, skills: Dict[str, Any]):
        self.skills = skills
    
    def route(self, intent: str) -> Optional[str]:
        """
        根據意圖名稱返回技能名稱
        
        Returns:
            技能名稱，如 "weather", "search" 等
        """
        # 意圖到技能的映射
        intent_to_skill = {
            "search_weather": "weather",
            "web_search": "search",
            "open_app": "app_control",
            "screenshot": "screenshot",
            "volume": "volume",
            "read_file": "file_ops",
            "write_file": "file_ops",
            "send_email": "gmail",
            "check_email": "gmail",
            "schedule": "scheduler",
            "monitor_stream": "yt_monitor",
        }
        
        return intent_to_skill.get(intent)
    
    def should_use_cloud_llm(self, user_message: str) -> bool:
        """
        判斷是否需要使用雲端 LLM（涉及隱私時使用本地）
        """
        privacy_keywords = ["密碼", "金鑰", "私人", "機密"]
        
        for keyword in privacy_keywords:
            if keyword in user_message:
                logger.info(f"檢測到隱私關鍵字: {keyword}，使用本地 LLM")
                return False
        
        return True