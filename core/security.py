"""
Security - 危險操作審查、緊急停止
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)


class Security:
    """負責安全審查和緊急停止"""
    
    # 危險操作關鍵字
    DANGEROUS_KEYWORDS = [
        "刪除系統",
        "格式化",
        "rm -rf",
        "del /f /s",
        "shutdown",
        "reboot",
        "kill process",
        "終止程序",
    ]
    
    # 允許的檔案操作路徑
    ALLOWED_PATHS = ["./agent_files/", "./data/"]
    
    def __init__(self):
        self.emergency_stop = False
    
    def check_dangerous_operation(self, action: str, params: dict) -> bool:
        """
        檢查是否為危險操作
        
        Returns:
            True 表示危險，False 表示安全
        """
        action_str = f"{action} {params}".lower()
        
        for keyword in self.DANGEROUS_KEYWORDS:
            if keyword.lower() in action_str:
                logger.warning(f"檢測到危險操作: {keyword}")
                return True
        
        return False
    
    def check_path_traversal(self, path: str) -> bool:
        """
        檢查路徑穿越攻擊
        """
        # 防止 ../ 穿越
        if ".." in path:
            logger.warning(f"檢測到路徑穿越: {path}")
            return True
        
        return False
    
    def check_allowed_path(self, path: str) -> bool:
        """
        檢查路徑是否在允許範圍內
        """
        path = path.replace("\\", "/")
        
        for allowed in self.ALLOWED_PATHS:
            if path.startswith(allowed.replace("\\", "/")):
                return True
        
        logger.warning(f"路徑不在允許範圍內: {path}")
        return False
    
    def emergency_stop_all(self):
        """緊急停止所有操作"""
        logger.warning("觸發緊急停止！")
        self.emergency_stop = True
    
    def reset_emergency(self):
        """重置緊急停止狀態"""
        self.emergency_stop = False
        logger.info("緊急停止已重置")