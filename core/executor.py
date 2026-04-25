"""
Executor - 任務佇列、執行、結果整合
"""

import asyncio
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class Executor:
    """負責執行任務並整合結果"""
    
    def __init__(self, skills: Dict[str, Any]):
        self.skills = skills
        self.task_queue = asyncio.Queue()
    
    async def execute_task(self, task: Dict[str, Any]) -> Any:
        """
        執行單一任務
        """
        skill_name = task.get("skill")
        action = task.get("action")
        params = task.get("params", {})
        
        logger.info(f"執行任務: {skill_name}.{action}")
        
        if skill_name not in self.skills:
            logger.error(f"技能不存在: {skill_name}")
            return {"error": f"技能不存在: {skill_name}"}
        
        skill = self.skills[skill_name]
        
        if not hasattr(skill, action):
            logger.error(f"技能 {skill_name} 沒有動作: {action}")
            return {"error": f"動作不存在: {action}"}
        
        try:
            method = getattr(skill, action)
            result = await method(**params) if params else await method()
            return result
        except Exception as e:
            logger.error(f"執行任務失敗: {e}")
            return {"error": str(e)}
    
    async def execute_tasks(self, tasks: List[Dict[str, Any]]) -> List[Any]:
        """
        依序執行多個任務
        """
        results = []
        
        for task in tasks:
            result = await self.execute_task(task)
            results.append(result)
        
        return results
    
    async def stop(self):
        """停止所有進行中的任務"""
        logger.info("停止所有任務...")
        # TODO: 實現任務中斷邏輯