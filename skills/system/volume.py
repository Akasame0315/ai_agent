"""
Volume Control Skill - 音量控制
"""

import logging
import platform
import subprocess
from typing import Any, Dict
from ..base import Skill

logger = logging.getLogger(__name__)


class VolumeSkill(Skill):
    """音量控制技能"""
    
    name = "volume"
    description = "控制系統音量"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.system = platform.system()
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "get":
            return await self.get_volume()
        elif action == "set":
            return await self.set_volume(kwargs.get("level", 50))
        elif action == "mute":
            return await self.mute()
        elif action == "unmute":
            return await self.unmute()
        return {"error": f"未知動作: {action}"}
    
    async def get_volume(self) -> Dict[str, Any]:
        """取得目前音量"""
        logger.info("取得音量")
        
        try:
            if self.system == "Windows":
                # Windows: 使用 PowerShell
                result = subprocess.run(
                    ['powershell', '-Command', '(Get-AudioDevice -PlaybackVolume).Value'],
                    capture_output=True,
                    text=True
                )
                level = int(result.stdout.strip()) if result.stdout.strip() else 50
            elif self.system == "Darwin":
                # macOS: 使用 osascript
                result = subprocess.run(
                    ["osascript", "-e", "output volume of (get volume settings)"],
                    capture_output=True,
                    text=True
                )
                level = int(result.stdout.strip()) if result.stdout.strip() else 50
            else:
                # Linux: 使用 pactl
                result = subprocess.run(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    capture_output=True,
                    text=True
                )
                # 解析輸出
                level = 50  # 預設值
            
            return {"level": level, "muted": False}
            
        except Exception as e:
            logger.error(f"取得音量失敗: {e}")
            return {"error": str(e)}
    
    async def set_volume(self, level: int) -> Dict[str, Any]:
        """設定音量"""
        logger.info(f"設定音量: {level}")
        
        # 限制在 0-100
        level = max(0, min(100, level))
        
        try:
            if self.system == "Windows":
                subprocess.run(
                    ['powershell', '-Command', f'Set-AudioDevice -PlaybackVolume {level}'],
                    check=True
                )
            elif self.system == "Darwin":
                subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)
            else:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
            
            return {"success": True, "level": level}
            
        except Exception as e:
            logger.error(f"設定音量失敗: {e}")
            return {"error": str(e)}
    
    async def mute(self) -> Dict[str, Any]:
        """靜音"""
        logger.info("靜音")
        
        try:
            if self.system == "Windows":
                subprocess.run(
                    ['powershell', '-Command', 'Set-AudioDevice -PlaybackMute $true'],
                    check=True
                )
            elif self.system == "Darwin":
                subprocess.run(["osascript", "-e", "set volume with output muted"], check=True)
            else:
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"], check=True)
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"靜音失敗: {e}")
            return {"error": str(e)}
    
    async def unmute(self) -> Dict[str, Any]:
        """取消靜音"""
        logger.info("取消靜音")
        
        try:
            if self.system == "Windows":
                subprocess.run(
                    ['powershell', '-Command', 'Set-AudioDevice -PlaybackMute $false'],
                    check=True
                )
            elif self.system == "Darwin":
                subprocess.run(["osascript", "-e", "set volume without output muted"], check=True)
            else:
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], check=True)
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"取消靜音失敗: {e}")
            return {"error": str(e)}
    
    def get_available_actions(self) -> list:
        return ["get", "set", "mute", "unmute"]