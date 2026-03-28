"""
直播狀態輪詢（備用方案）
路徑：tools/stream_check.py

當 Webhook 無法使用時，用輪詢方式檢查直播狀態。
Twitch 和 YouTube 都支援，整合在同一個排程任務裡。
"""
import httpx # type: ignore
import os
from core.logger import get_logger

logger = get_logger(__name__)

YOUTUBE_API_KEY  = os.getenv("YOUTUBE_API_KEY", "")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")

# 快取：避免重複通知同一場直播
_live_cache: dict[str, str] = {}   # {channel_id: stream_id}
_twitch_token: str = ""
_twitch_token_exp: float = 0


# ── Twitch 輪詢（不需要 Webhook）────────────────────────────────────
async def _get_twitch_token() -> str:
    global _twitch_token, _twitch_token_exp
    import time
    if _twitch_token and time.time() < _twitch_token_exp:
        return _twitch_token
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return ""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id":     TWITCH_CLIENT_ID,
                    "client_secret": TWITCH_CLIENT_SECRET,
                    "grant_type":    "client_credentials"
                },
                timeout=10
            )
            data = resp.json()
            _twitch_token     = data.get("access_token", "")
            _twitch_token_exp = time.time() + data.get("expires_in", 3600) - 60
            return _twitch_token
    except Exception as e:
        logger.error(f"[Twitch] 取得 token 失敗：{e}")
        return ""


async def check_twitch_live(channels: list[str]) -> list[dict]:
    """檢查 Twitch 頻道是否在直播"""
    if not channels:
        return []
    token = await _get_twitch_token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient() as client:
            params = [("user_login", ch) for ch in channels]
            resp   = await client.get(
                "https://api.twitch.tv/helix/streams",
                params=params,
                headers={
                    "Client-ID":     TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {token}"
                },
                timeout=10
            )
            streams = resp.json().get("data", [])
            return [
                {
                    "platform":  "twitch",
                    "channel":   s["user_login"],
                    "title":     s.get("title", ""),
                    "url":       f"https://twitch.tv/{s['user_login']}",
                    "stream_id": s["id"]
                }
                for s in streams if s.get("type") == "live"
            ]
    except Exception as e:
        logger.error(f"[Twitch] 輪詢失敗：{e}")
        return []


async def check_youtube_live(channel_ids: list[str]) -> list[dict]:
    """檢查 YouTube 頻道是否在直播（使用 YouTube Data API）"""
    if not channel_ids or not YOUTUBE_API_KEY:
        return []
    results = []
    try:
        async with httpx.AsyncClient() as client:
            for channel_id in channel_ids:
                resp = await client.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part":       "snippet",
                        "channelId":  channel_id,
                        "type":       "video",
                        "eventType":  "live",
                        "key":        YOUTUBE_API_KEY,
                        "maxResults": 1
                    },
                    timeout=10
                )
                if resp.status_code == 403:
                    logger.warning("[YouTube] API 額度用完，跳過輪詢")
                    break
                items = resp.json().get("items", [])
                for item in items:
                    video_id = item["id"].get("videoId", "")
                    title    = item["snippet"].get("title", "")
                    channel  = item["snippet"].get("channelTitle", channel_id)
                    if video_id:
                        results.append({
                            "platform":  "youtube",
                            "channel":   channel,
                            "title":     title,
                            "url":       f"https://youtube.com/watch?v={video_id}",
                            "stream_id": video_id
                        })
    except Exception as e:
        logger.error(f"[YouTube] 輪詢失敗：{e}")
    return results


async def poll_all_streams(notify_callback) -> int:
    """
    輪詢所有監控頻道，發現新直播就呼叫 notify_callback。
    回傳本次發現的新直播數。
    """
    from tools.stream_monitor import get_monitored_channels

    channels   = get_monitored_channels()
    new_count  = 0
    live_items = []

    # 檢查 Twitch
    if channels.get("twitch"):
        twitch_live = await check_twitch_live(channels["twitch"])
        live_items.extend(twitch_live)

    # 檢查 YouTube
    if channels.get("youtube"):
        yt_live = await check_youtube_live(channels["youtube"])
        live_items.extend(yt_live)

    # 通知新開播的
    for item in live_items:
        key = f"{item['platform']}_{item['channel']}"
        if _live_cache.get(key) != item["stream_id"]:
            _live_cache[key] = item["stream_id"]
            logger.info(f"[StreamPoll] 發現新直播：{item['platform']} / {item['channel']}")
            await notify_callback(
                item["platform"], item["channel"],
                item["title"], item["url"], item["stream_id"]
            )
            new_count += 1

    # 清理已下播的快取
    live_keys = {f"{i['platform']}_{i['channel']}" for i in live_items}
    for key in list(_live_cache.keys()):
        if key not in live_keys:
            del _live_cache[key]

    return new_count
