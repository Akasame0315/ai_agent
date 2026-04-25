"""
YouTube Stream Monitor Skill - YouTube 直播監控
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional
from ..base import Skill

logger = logging.getLogger(__name__)


class StreamMonitorSkill(Skill):
    """YouTube 直播監控技能"""
    
    name = "yt_monitor"
    description = "YouTube 直播開播通知"
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.monitored_channels: Dict[str, Dict] = {}
        self.webhook_url = config.get("webhook_url") if config else None
        self.polling_task = None
        self.is_running = False
    
    async def execute(self, action: str, **kwargs) -> Any:
        if action == "add_channel":
            return await self.add_channel(
                kwargs.get("channel_id"),
                kwargs.get("channel_name")
            )
        elif action == "remove_channel":
            return await self.remove_channel(kwargs.get("channel_id"))
        elif action == "list_channels":
            return await self.list_channels()
        elif action == "start":
            return await self.start_monitoring()
        elif action == "stop":
            return await self.stop_monitoring()
        elif action == "check":
            return await self.check_streams()
        return {"error": f"未知動作: {action}"}
    
    async def add_channel(self, channel_id: str, channel_name: str = None) -> Dict[str, Any]:
        """新增監控頻道"""
        logger.info(f"新增監控頻道: {channel_id}")
        
        self.monitored_channels[channel_id] = {
            "id": channel_id,
            "name": channel_name or channel_id,
            "is_live": False,
            "last_check": None
        }
        
        return {"success": True, "channel_id": channel_id}
    
    async def remove_channel(self, channel_id: str) -> Dict[str, Any]:
        """移除監控頻道"""
        logger.info(f"移除監控頻道: {channel_id}")
        
        if channel_id in self.monitored_channels:
            del self.monitored_channels[channel_id]
            return {"success": True}
        
        return {"error": "頻道不存在"}
    
    async def list_channels(self) -> Dict[str, Any]:
        """列出監控中的頻道"""
        logger.info("列出監控頻道")
        
        return {
            "channels": list(self.monitored_channels.values())
        }
    
    async def start_monitoring(self) -> Dict[str, Any]:
        """開始監控"""
        logger.info("開始 YouTube 直播監控")
        
        if self.is_running:
            return {"error": "監控已在執行中"}
        
        self.is_running = True
        
        # TODO: 啟動背景輪詢任務
        # self.polling_task = asyncio.create_task(self._poll_streams())
        
        return {"success": True}
    
    async def stop_monitoring(self) -> Dict[str, Any]:
        """停止監控"""
        logger.info("停止 YouTube 直播監控")
        
        self.is_running = False
        
        if self.polling_task:
            self.polling_task.cancel()
            self.polling_task = None
        
        return {"success": True}
    
    async def check_streams(self) -> Dict[str, Any]:
        """檢查所有頻道直播狀態"""
        logger.info("檢查直播狀態")
        
        results = []
        
        for channel_id, channel in self.monitored_channels.items():
            # TODO: 使用 YouTube Data API 檢查直播狀態
            # import requests
            # url = f"https://www.googleapis.com/youtube/v3/search"
            # params = {
            #     "part": "snippet",
            #     "channelId": channel_id,
            #     "eventType": "live",
            #     "type": "video",
            #     "key": API_KEY
            # }
            
            is_live = False  # 模擬結果
            
            results.append({
                "channel_id": channel_id,
                "channel_name": channel.get("name"),
                "is_live": is_live
            })
            
            # 如果從離線變線上，發送通知
            if is_live and not channel.get("is_live"):
                await self._notify_stream_start(channel)
            
            # 更新狀態
            channel["is_live"] = is_live
        
        return {"results": results}
    
    async def _notify_stream_start(self, channel: Dict):
        """通知直播開始"""
        logger.info(f"頻道 {channel.get('name')} 開播了！")
        
        if self.webhook_url:
            # TODO: 發送 Webhook 通知
            # import requests
            # requests.post(self.webhook_url, json={
            #     "type": "stream_start",
            #     "channel": channel
            # })
            pass
    
    async def _poll_streams(self):
        """輪詢直播狀態"""
        while self.is_running:
            try:
                await self.check_streams()
                await asyncio.sleep(60)  # 每分鐘檢查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"輪詢錯誤: {e}")
                await asyncio.sleep(60)
    
    def get_available_actions(self) -> list:
        return ["add_channel", "remove_channel", "list_channels", "start", "stop", "check"]