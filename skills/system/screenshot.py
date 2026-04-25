"""
Screenshot Skill - 截圖
"""

import logging
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any, Dict
from ..base import Skill

logger = logging.getLogger(__name__)


class ScreenshotSkill(Skill):
    """截圖技能"""
    
    name = "screenshot"
    description = "螢幕截圖"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.system = platform.system()
        self.save_dir = Path("./agent_files/screenshots")
        self.save_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "capture":
            return await self.capture(kwargs.get("filename"))
        elif action == "capture_region":
            return await self.capture_region(
                kwargs.get("x"), 
                kwargs.get("y"), 
                kwargs.get("width"), 
                kwargs.get("height"),
                kwargs.get("filename")
            )
        return {"error": f"未知動作: {action}"}
    
    def _generate_filename(self, custom_name: str = None) -> str:
        """產生檔案名稱"""
        if custom_name:
            return f"{custom_name}.png"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"screenshot_{timestamp}.png"
    
    async def capture(self, filename: str = None) -> Dict[str, Any]:
        """全螢幕截圖"""
        logger.info("全螢幕截圖")
        
        filename = filename or self._generate_filename()
        filepath = self.save_dir / filename
        
        try:
            if self.system == "Windows":
                # Windows: 使用 PowerShell
                subprocess.run(
                    ['powershell', '-Command', 
                     f'Add-Type -AssemblyName System.Windows.Forms; '
                     f'[System.Windows.Forms.Screen]::PrimaryScreen.Bounds | '
                     f'ForEach-Object {{ '
                     f'$bmp = New-Object System.Drawing.Bitmap($_.Width, $_.Height); '
                     f'$graphics = [System.Drawing.Graphics]::FromImage($bmp); '
                     f'$graphics.CopyFromScreen($_.Location, [System.Drawing.Point]::Empty, $_.Size); '
                     f'$bmp.Save("{filepath.as_posix()}"); '
                     f'$graphics.Dispose(); $bmp.Dispose()'
                     f'}}'],
                    check=True
                )
            elif self.system == "Darwin":
                # macOS: 使用 screencapture
                subprocess.run(
                    ["screencapture", "-x", str(filepath)],
                    check=True
                )
            else:
                # Linux: 使用 scrot 或 gnome-screenshot
                try:
                    subprocess.run(["scrot", str(filepath)], check=True)
                except:
                    subprocess.run(["gnome-screenshot", "-f", str(filepath)], check=True)
            
            return {"success": True, "path": str(filepath), "filename": filename}
            
        except Exception as e:
            logger.error(f"截圖失敗: {e}")
            return {"error": str(e)}
    
    async def capture_region(self, x: int, y: int, width: int, height: int, filename: str = None) -> Dict[str, Any]:
        """區域截圖"""
        logger.info(f"區域截圖: ({x}, {y}) {width}x{height}")
        
        filename = filename or self._generate_filename()
        filepath = self.save_dir / filename
        
        try:
            if self.system == "Windows":
                # Windows: 使用 PowerShell 區域截圖
                subprocess.run(
                    ['powershell', '-Command', 
                     f'$bmp = New-Object System.Drawing.Bitmap({width}, {height}); '
                     f'$graphics = [System.Drawing.Graphics]::FromImage($bmp); '
                     f'$graphics.CopyFromScreen({x}, {y}, 0, 0, [System.Drawing.Size]::new({width}, {height})); '
                     f'$bmp.Save("{filepath.as_posix()}"); '
                     f'$graphics.Dispose(); $bmp.Dispose()'],
                    check=True
                )
            elif self.system == "Darwin":
                # macOS: 使用 screencapture -i 互動式選取
                subprocess.run(
                    ["screencapture", "-i", str(filepath)],
                    check=True
                )
            else:
                # Linux: 使用 scrot -a
                subprocess.run(
                    ["scrot", "-a", f"{x},{y},{width},{height}", str(filepath)],
                    check=True
                )
            
            return {"success": True, "path": str(filepath), "filename": filename}
            
        except Exception as e:
            logger.error(f"區域截圖失敗: {e}")
            return {"error": str(e)}
    
    def get_available_actions(self) -> list:
        return ["capture", "capture_region"]