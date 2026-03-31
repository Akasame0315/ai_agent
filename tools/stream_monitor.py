"""
直播監控工具
路徑：tools/stream_monitor.py

功能：
- 管理 Twitch / YouTube 監控頻道清單
- 查詢目前監控狀態
- 記錄已通知的直播（避免重複通知）
"""
import json
import logging
import os
import asyncio
logger = logging.getLogger(__name__)

from core.paths import STREAM_MONITOR_FILE as MONITOR_FILE

DEFAULT_CONFIG = {
    "twitch":  [],    # Twitch 頻道名稱列表
    "youtube": [],    # YouTube Channel ID 列表
    "notified": {}    # {stream_id: timestamp} 避免重複通知
}


def _load() -> dict:
    if not os.path.exists(MONITOR_FILE):
        _save(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    with open(MONITOR_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(config: dict):
    with open(MONITOR_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def trigger_subscribe(target_id: str):
    """
    發送同步請求給本機 Webhook Server 觸發訂閱
    """
    import httpx #type: ignore
    try:
        # 使用同步 Client，這在 Thread 裡是非常安全的
        with httpx.Client() as client:
            resp = client.get(
                f"http://127.0.0.1:8000/debug/subscribe_now?channel_id={target_id}", 
                timeout=10.0
            )
            result = resp.json()
            if result.get("status") == "success":
                logger.info(f"[YouTube] 已成功觸發 Webhook Server 訂閱請求：{target_id}")
            else:
                logger.error(f"[YouTube] Webhook Server 訂閱失敗：{result.get('message')}")
    except Exception as e:
        logger.error(f"[YouTube] 連動 Webhook Server 異常: {e}")


def add_stream_channel(platform: str, channel: str) -> str:
    """新增要監控的頻道"""
    platform = platform.lower()
    if platform not in ("twitch", "youtube"):
        return "❌ platform 請填 twitch 或 youtube"

    config = _load()
    target_id = channel
    display_name = channel

    from tools.youtube import search_youtube_channel, parse_channel_input
    # --- YouTube 專屬處理邏輯 ---
    if platform == "youtube":
        # 先解析輸入格式 (可能是網址、handle、或名稱)
        parsed = parse_channel_input(channel)
        
        # 如果不是直接給 ID，就去搜尋
        if parsed["type"] != "id":
            results = search_youtube_channel(channel)
            if not results:
                return f"❌ 找不到 YouTube 頻道：{channel}，請提供正確名稱或網址。"
            
            # 取得搜尋結果的第一個（最匹配的）
            target_id = results[0]["id"]
            display_name = results[0]["name"]
        else:
            target_id = parsed["value"]
            display_name = f"ID: {target_id}"

    if target_id in config[platform]:
        return f"⚠️ {platform} 頻道「{display_name}」已在監控清單中"

    config[platform].append(target_id)
    _save(config)
    
    # --- 新增：通知 Webhook Server 立即訂閱 ---
    if platform == "youtube":
        import threading
        threading.Thread(target=trigger_subscribe, args=(target_id,)).start()

    return f"✅ 已新增監控：{platform} / {display_name}（{target_id}）"


def remove_stream_channel(platform: str, channel: str) -> str:
    """移除監控頻道"""
    platform = platform.lower()
    config   = _load()

    if channel not in config.get(platform, []):
        return f"❌ 找不到：{platform} / {channel}"

    config[platform].remove(channel)
    _save(config)
    return f"✅ 已移除監控：{platform} / {channel}"


def list_stream_channels(**_) -> str:
    """列出所有監控中的頻道"""
    config = _load()
    lines  = ["📺 直播監控清單：\n"]

    twitch = config.get("twitch", [])
    if twitch:
        lines.append("Twitch：")
        for ch in twitch:
            lines.append(f"  • {ch}  →  twitch.tv/{ch}")
    else:
        lines.append("Twitch：（無）")

    youtube = config.get("youtube", [])
    if youtube:
        lines.append("\nYouTube：")
        for ch in youtube:
            lines.append(f"  • {ch}")
    else:
        lines.append("\nYouTube：（無）")

    return "\n".join(lines)


def is_notified(stream_id: str) -> bool:
    """檢查這場直播是否已經通知過"""
    config = _load()
    return stream_id in config.get("notified", {})


def mark_notified(stream_id: str):
    """標記這場直播已通知"""
    import datetime
    config = _load()
    config.setdefault("notified", {})
    config["notified"][stream_id] = datetime.datetime.now().isoformat()

    # 清理超過 7 天的舊記錄
    cutoff = (datetime.datetime.now() -
              datetime.timedelta(days=7)).isoformat()
    config["notified"] = {
        k: v for k, v in config["notified"].items() if v > cutoff
    }
    _save(config)


def get_monitored_channels() -> dict:
    """供 webhook server 使用：取得所有監控頻道"""
    config = _load()
    return {
        "twitch":  config.get("twitch", []),
        "youtube": config.get("youtube", [])
    }
