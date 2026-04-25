"""
Skill Base Class - 技能基底類別
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class Skill(ABC):
    """所有技能的基底類別"""
    
    name: str = "base"
    description: str = "基礎技能"
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
    
    @abstractmethod
    async def execute(self, action: str, **kwargs) -> Any:
        """
        執行技能動作
        
        Args:
            action: 動作名稱
            **kwargs: 動作參數
            
        Returns:
            執行結果
        """
        pass
    
    def get_available_actions(self) -> list:
        """取得可用動作列表"""
        return []
    
    async def validate_params(self, action: str, params: Dict) -> bool:
        """驗證參數"""
        return True