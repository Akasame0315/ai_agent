"""
YouTube 頻道搜尋工具
路徑：tools/youtube.py

支援多種輸入格式：
  - 完整網址：https://youtube.com/@hololive
  - handle：@hololive
  - 頻道名稱：hololive
  - Channel ID：UCxxxxxxxxx（直接使用）

優先使用 YouTube Data API v3，
API 額度用完時自動切換到備用方案（解析網頁）。
"""
import os
import re
import httpx # type: ignore
from core.logger import get_logger

logger = get_logger(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"


# ══════════════════════════════════════════════════════════════════════
# 輸入解析
# ══════════════════════════════════════════════════════════════════════

def parse_channel_input(text: str) -> dict:
    """
    解析使用者輸入，判斷是哪種格式。
    回傳 {"type": "id"|"handle"|"url"|"name", "value": "..."}
    """
    text = text.strip()

    # Channel ID（UC 開頭，24 字元）
    if re.match(r'^UC[\w-]{22}$', text):
        return {"type": "id", "value": text}

    # 完整 YouTube 網址
    if "youtube.com" in text or "youtu.be" in text:
        # 提取 handle 或 channel id
        handle_match = re.search(r'/@([\w.-]+)', text)
        if handle_match:
            return {"type": "handle", "value": handle_match.group(1)}

        channel_match = re.search(r'/channel/(UC[\w-]{22})', text)
        if channel_match:
            return {"type": "id", "value": channel_match.group(1)}

        # /c/ 或 /user/ 路徑
        legacy_match = re.search(r'/(?:c|user)/([\w.-]+)', text)
        if legacy_match:
            return {"type": "handle", "value": legacy_match.group(1)}

        return {"type": "url", "value": text}

    # @ handle
    if text.startswith("@"):
        return {"type": "handle", "value": text[1:]}

    # 一般名稱搜尋
    return {"type": "name", "value": text}


# ══════════════════════════════════════════════════════════════════════
# YouTube Data API v3
# ══════════════════════════════════════════════════════════════════════

def _api_search_by_handle(handle: str) -> list[dict]:
    """用 handle 搜尋頻道（forHandle 參數）"""
    if not YOUTUBE_API_KEY:
        return []
    try:
        resp = httpx.get(
            f"{YOUTUBE_API_URL}/channels",
            params={
                "part":      "snippet",
                "forHandle": handle,
                "key":       YOUTUBE_API_KEY,
                "maxResults": 1
            },
            timeout=10
        )
        if resp.status_code == 403:
            logger.warning("[YouTube API] 額度已用完，切換備用方案")
            return []
        data  = resp.json()
        items = data.get("items", [])
        return [_format_channel(item) for item in items]
    except Exception as e:
        logger.error(f"[YouTube API] handle 搜尋失敗：{e}")
        return []


def _api_search_by_name(name: str) -> list[dict]:
    """用名稱關鍵字搜尋頻道"""
    if not YOUTUBE_API_KEY:
        return []
    try:
        resp = httpx.get(
            f"{YOUTUBE_API_URL}/search",
            params={
                "part":       "snippet",
                "type":       "channel",
                "q":          name,
                "key":        YOUTUBE_API_KEY,
                "maxResults": 5
            },
            timeout=10
        )
        if resp.status_code == 403:
            logger.warning("[YouTube API] 額度已用完，切換備用方案")
            return []
        data  = resp.json()
        items = data.get("items", [])
        return [_format_search_item(item) for item in items]
    except Exception as e:
        logger.error(f"[YouTube API] 名稱搜尋失敗：{e}")
        return []


def _format_channel(item: dict) -> dict:
    snippet = item.get("snippet", {})
    return {
        "id":          item.get("id", ""),
        "name":        snippet.get("title", ""),
        "description": snippet.get("description", "")[:100],
        "url":         f"https://youtube.com/channel/{item.get('id', '')}"
    }


def _format_search_item(item: dict) -> dict:
    snippet   = item.get("snippet", {})
    channel_id = item.get("id", {}).get("channelId", "")
    return {
        "id":          channel_id,
        "name":        snippet.get("channelTitle", ""),
        "description": snippet.get("description", "")[:100],
        "url":         f"https://youtube.com/channel/{channel_id}"
    }


# ══════════════════════════════════════════════════════════════════════
# 備用方案：解析 YouTube 網頁
# ══════════════════════════════════════════════════════════════════════

def _scrape_channel_id(handle: str) -> str:
    """從頻道網頁抓取 Channel ID（備用方案，不消耗 API 額度）"""
    try:
        url  = f"https://www.youtube.com/@{handle}"
        resp = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
            follow_redirects=True
        )
        content = resp.text

        # 從 HTML meta 或 JS 變數找 Channel ID
        patterns = [
            r'"channelId":"(UC[\w-]{22})"',
            r'"externalChannelId":"(UC[\w-]{22})"',
            r'<meta itemprop="channelId" content="(UC[\w-]{22})"',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        return ""
    except Exception as e:
        logger.error(f"[YouTube Scrape] 失敗：{e}")
        return ""


# ══════════════════════════════════════════════════════════════════════
# 主要搜尋函式
# ══════════════════════════════════════════════════════════════════════

def search_youtube_channel(query: str) -> list[dict]:
    """
    搜尋 YouTube 頻道，支援多種輸入格式。
    自動嘗試 API → 備用方案。
    """
    parsed = parse_channel_input(query)
    logger.info(f"[YouTube] 搜尋：{query} → 類型：{parsed['type']}")

    # 直接使用 Channel ID
    if parsed["type"] == "id":
        return [{"id": parsed["value"], "name": parsed["value"],
                 "description": "", "url": f"https://youtube.com/channel/{parsed['value']}"}]

    # Handle 或網址
    if parsed["type"] in ("handle", "url"):
        handle = parsed["value"]

        # 先用 API
        results = _api_search_by_handle(handle)
        if results:
            return results

        # API 失敗，用爬蟲
        channel_id = _scrape_channel_id(handle)
        if channel_id:
            return [{"id": channel_id, "name": f"@{handle}",
                     "description": "", "url": f"https://youtube.com/@{handle}"}]

    # 名稱搜尋
    if parsed["type"] == "name":
        # 先用 API 搜尋
        results = _api_search_by_name(parsed["value"])
        if results:
            return results

        # API 失敗，嘗試把名稱當 handle 用爬蟲
        handle    = parsed["value"].replace(" ", "").lower()
        channel_id = _scrape_channel_id(handle)
        if channel_id:
            return [{"id": channel_id, "name": parsed["value"],
                     "description": "", "url": f"https://youtube.com/@{handle}"}]

    return []


# ══════════════════════════════════════════════════════════════════════
# 工具函式（供 tools/__init__.py 呼叫）
# ══════════════════════════════════════════════════════════════════════

def find_youtube_channel(query: str) -> str:
    """
    搜尋 YouTube 頻道並格式化結果。
    找到一個直接回傳，找到多個列出讓使用者選擇。
    """
    results = search_youtube_channel(query)

    if not results:
        return (
            f"❌ 找不到頻道：{query}\n\n"
            f"建議：\n"
            f"  • 試試完整頻道名稱\n"
            f"  • 試試 @handle 格式\n"
            f"  • 直接貼上頻道網址"
        )

    if len(results) == 1:
        ch = results[0]
        return (
            f"✅ 找到頻道：\n"
            f"名稱：{ch['name']}\n"
            f"ID：{ch['id']}\n"
            f"網址：{ch['url']}\n\n"
            f"要新增監控嗎？說「監控這個頻道」即可。"
        )

    lines = [f"🔍 找到 {len(results)} 個頻道，請確認要追蹤哪一個：\n"]
    for i, ch in enumerate(results, 1):
        lines.append(f"{i}. {ch['name']}")
        if ch["description"]:
            lines.append(f"   {ch['description']}")
        lines.append(f"   ID：{ch['id']}")
        lines.append("")

    lines.append("請說「追蹤第 X 個」或直接說頻道 ID。")
    return "\n".join(lines)


def add_youtube_channel_by_query(query: str) -> str:
    """
    搜尋並直接新增 YouTube 頻道監控。
    找到唯一結果直接新增，找到多個讓使用者選。
    """
    results = search_youtube_channel(query)

    if not results:
        return f"❌ 找不到頻道：{query}"

    if len(results) == 1:
        ch = results[0]
        from tools.stream_monitor import add_stream_channel
        result = add_stream_channel("youtube", ch["id"])
        return f"{result}\n頻道：{ch['name']}\nID：{ch['id']}"

    # 多個結果，讓使用者選
    return find_youtube_channel(query)
