"""
File Operations Skill - 檔案讀寫
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List
from ..base import Skill

logger = logging.getLogger(__name__)


class FileOpsSkill(Skill):
    """檔案操作技能"""
    
    name = "file_ops"
    description = "讀寫 agent_files 目錄中的檔案"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.base_path = Path("./agent_files")
        self.base_path.mkdir(exist_ok=True)
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "read":
            return await self.read_file(kwargs.get("path", ""))
        elif action == "write":
            return await self.write_file(kwargs.get("path", ""), kwargs.get("content", ""))
        elif action == "list":
            return await self.list_files(kwargs.get("path", ""))
        elif action == "delete":
            return await self.delete_file(kwargs.get("path", ""))
        return {"error": f"未知動作: {action}"}
    
    def _resolve_path(self, path: str) -> Path:
        """安全地解析路徑"""
        # 防止路徑穿越
        if ".." in path:
            raise ValueError("不允許路徑穿越")
        
        full_path = self.base_path / path.lstrip("/")
        
        # 確保路徑在 base_path 內
        try:
            full_path.resolve().relative_to(self.base_path.resolve())
        except ValueError:
            raise ValueError("路徑不在允許範圍內")
        
        return full_path
    
    async def read_file(self, path: str) -> Dict[str, Any]:
        """讀取檔案"""
        logger.info(f"讀取檔案: {path}")
        
        try:
            full_path = self._resolve_path(path)
            
            if not full_path.exists():
                return {"error": "檔案不存在"}
            
            if full_path.is_dir():
                return {"error": "這是目錄，不是檔案"}
            
            content = full_path.read_text(encoding="utf-8")
            return {"content": content, "path": path}
            
        except Exception as e:
            logger.error(f"讀取失敗: {e}")
            return {"error": str(e)}
    
    async def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """寫入檔案"""
        logger.info(f"寫入檔案: {path}")
        
        try:
            full_path = self._resolve_path(path)
            
            # 建立目錄
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            full_path.write_text(content, encoding="utf-8")
            return {"success": True, "path": path}
            
        except Exception as e:
            logger.error(f"寫入失敗: {e}")
            return {"error": str(e)}
    
    async def list_files(self, path: str = "") -> Dict[str, Any]:
        """列出目錄內容"""
        logger.info(f"列出目錄: {path}")
        
        try:
            full_path = self._resolve_path(path)
            
            if not full_path.exists():
                return {"error": "目錄不存在"}
            
            if not full_path.is_dir():
                return {"error": "這不是目錄"}
            
            items = []
            for item in full_path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None
                })
            
            return {"items": items, "path": path}
            
        except Exception as e:
            logger.error(f"列出失敗: {e}")
            return {"error": str(e)}
    
    async def delete_file(self, path: str) -> Dict[str, Any]:
        """刪除檔案"""
        logger.info(f"刪除檔案: {path}")
        
        try:
            full_path = self._resolve_path(path)
            
            if not full_path.exists():
                return {"error": "檔案不存在"}
            
            if full_path.is_dir():
                import shutil
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            
            return {"success": True, "path": path}
            
        except Exception as e:
            logger.error(f"刪除失敗: {e}")
            return {"error": str(e)}
    
    def get_available_actions(self) -> list:
        return ["read", "write", "list", "delete"]