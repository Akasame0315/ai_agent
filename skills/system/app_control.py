"""
App Control Skill - 應用程式控制
"""

import logging
import subprocess
import platform
from typing import Any, Dict, List
from ..base import Skill

logger = logging.getLogger(__name__)


class AppControlSkill(Skill):
    """應用程式控制技能"""
    
    name = "app_control"
    description = "模糊搜尋並開啟應用程式"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.system = platform.system()
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "open":
            return await self.open_app(kwargs.get("name", ""))
        elif action == "list_running":
            return await self.list_running_apps()
        elif action == "close":
            return await self.close_app(kwargs.get("name", ""))
        return {"error": f"未知動作: {action}"}
    
    async def open_app(self, name: str) -> Dict[str, Any]:
        """開啟應用程式"""
        logger.info(f"開啟應用程式: {name}")
        
        try:
            if self.system == "Windows":
                # Windows: 使用 start 命令
                subprocess.Popen(f'start "" "{name}"', shell=True)
            elif self.system == "Darwin":
                # macOS: 使用 open 命令
                subprocess.Popen(["open", "-a", name])
            else:
                # Linux: 嘗試使用 xdg-open
                subprocess.Popen(["xdg-open", name])
            
            return {"success": True, "app": name}
            
        except Exception as e:
            logger.error(f"開啟失敗: {e}")
            return {"error": str(e)}
    
    async def list_running_apps(self) -> Dict[str, Any]:
        """列出執行中的應用程式"""
        logger.info("列出執行中的應用程式")
        
        try:
            if self.system == "Windows":
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True
                )
                apps = [line.split('"')[1] for line in result.stdout.strip().split('\n')[:10]]
            elif self.system == "Darwin":
                result = subprocess.run(
                    ["osascript", "-e", 'tell app "System Events" to get name of every process whose background only is false'],
                    capture_output=True,
                    text=True
                )
                apps = result.stdout.strip().split(", ")
            else:
                # Linux
                result = subprocess.run(
                    ["wmctrl", "-l"],
                    capture_output=True,
                    text=True
                )
                apps = [line.split(None, 3)[-1] for line in result.stdout.strip().split('\n')[:10]]
            
            return {"apps": apps}
            
        except Exception as e:
            logger.error(f"列出失敗: {e}")
            return {"error": str(e)}
    
    async def close_app(self, name: str) -> Dict[str, Any]:
        """關閉應用程式"""
        logger.info(f"關閉應用程式: {name}")
        
        try:
            if self.system == "Windows":
                subprocess.run(f'taskkill /IM "{name}.exe" /F', shell=True)
            elif self.system == "Darwin":
                subprocess.run(["osascript", "-e", f'tell app "{name}" to quit'])
            else:
                # Linux
                subprocess.run(["pkill", name])
            
            return {"success": True, "app": name}
            
        except Exception as e:
            logger.error(f"關閉失敗: {e}")
            return {"error": str(e)}
    
    def get_available_actions(self) -> list:
        return ["open", "list_running", "close"]