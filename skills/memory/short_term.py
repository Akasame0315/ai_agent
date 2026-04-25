"""
Short-term Memory - 當次對話摘要
"""

import logging
from typing import Any, Dict, List
from ..base import Skill

logger = logging.getLogger(__name__)


class ShortTermMemorySkill(Skill):
    """短期記憶技能 - 當次對話摘要"""
    
    name = "short_term"
    description = "當次對話摘要和上下文管理"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.conversation_history: List[Dict[str, Any]] = []
        self.max_history = config.get("max_history", 20) if config else 20
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "add":
            return await self.add_message(
                kwargs.get("role"),
                kwargs.get("content")
            )
        elif action == "get_history":
            return await self.get_history(kwargs.get("limit"))
        elif action == "summarize":
            return await self.summarize()
        elif action == "clear":
            return await self.clear()
        return {"error": f"未知動作: {action}"}
    
    async def add_message(self, role: str, content: str) -> Dict[str, Any]:
        """新增訊息到對話歷史"""
        logger.info(f"新增訊息: {role}")
        
        message = {
            "role": role,  # "user" or "assistant"
            "content": content
        }
        
        self.conversation_history.append(message)
        
        # 保持歷史長度
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
        
        return {"success": True, "count": len(self.conversation_history)}
    
    async def get_history(self, limit: int = None) -> Dict[str, Any]:
        """取得對話歷史"""
        logger.info("取得對話歷史")
        
        history = self.conversation_history
        if limit:
            history = history[-limit:]
        
        return {
            "history": history,
            "count": len(history)
        }
    
    async def summarize(self) -> Dict[str, Any]:
        """摘要對話"""
        logger.info("摘要對話")
        
        if not self.conversation_history:
            return {"summary": "無對話記錄"}
        
        # TODO: 使用 LLM 生成摘要
        summary = f"對話包含 {len(self.conversation_history)} 條訊息"
        
        return {"summary": summary}
    
    async def clear(self) -> Dict[str, Any]:
        """清除對話歷史"""
        logger.info("清除對話歷史")
        
        self.conversation_history = []
        
        return {"success": True}
    
    def get_available_actions(self) -> list:
        return ["add", "get_history", "summarize", "clear"]