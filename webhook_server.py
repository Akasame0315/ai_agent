"""
Webhook 接收伺服器
路徑：webhook_server.py（專案根目錄）

接收 Twitch EventSub 和 YouTube WebSub 的推播通知，
解析後推播到 Telegram，等待使用者確認再開瀏覽器。

啟動方式：
  python webhook_server.py

通常和 main.py 一起跑，開兩個終端機視窗即可。
"""
import asyncio
import hashlib
import hmac
import json
import os
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime

import httpx # type: ignore
import ngrok # type: ignore
from fastapi import FastAPI, Request, Response # type: ignore
from dotenv import load_dotenv # type: ignore

load_dotenv()

# ── 設定 ──────────────────────────────────────────────────────────────
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_WEBHOOK_SECRET = os.getenv("TWITCH_WEBHOOK_SECRET", "mysecret")
TELEGRAM_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID     = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
NGROK_AUTHTOKEN      = os.getenv("NGROK_AUTHTOKEN", "")
TWITCH_CHANNELS      = [c.strip() for c in os.getenv("TWITCH_CHANNELS", "").split(",") if c.strip()]
YOUTUBE_CHANNELS     = [c.strip() for c in os.getenv("YOUTUBE_CHANNELS", "").split(",") if c.strip()]

# 全域儲存 ngrok URL（啟動後取得）
PUBLIC_URL = ""

# 待確認的直播通知 {callback_id: url}
PENDING_STREAMS: dict[str, str] = {}


# ══════════════════════════════════════════════════════════════════════
# Telegram 推播
# ══════════════════════════════════════════════════════════════════════

async def send_telegram(text: str, reply_markup: dict = None):
    """推播訊息到 Telegram"""
    payload = {
        "chat_id": TELEGRAM_USER_ID,
        "text":    text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )


async def notify_stream_live(
    platform: str,
    channel:  str,
    title:    str,
    url:      str,
    stream_id: str
):
    """推播直播通知，附上開啟按鈕"""
    from tools.stream_monitor import is_notified, mark_notified

    if is_notified(stream_id):
        print(f"[Stream] 已通知過：{stream_id}，略過")
        return

    mark_notified(stream_id)
    PENDING_STREAMS[stream_id] = url

    # 同步寫入檔案讓 telegram_bot.py 也能讀取
    import json
    pending_file = "pending_streams.json"
    try:
        existing = {}
        if os.path.exists(pending_file):
            with open(pending_file) as f:
                existing = json.load(f)
        existing[stream_id] = url
        with open(pending_file, "w") as f:
            json.dump(existing, f)
    except Exception:
        pass

    emoji = "🟣" if platform == "twitch" else "🔴"
    text  = (
        f"{emoji} <b>{channel}</b> 開始直播了！\n\n"
        f"📺 {title}\n"
        f"🔗 {url}\n\n"
        f"要開啟直播嗎？"
    )

    # Telegram inline keyboard
    markup = {
        "inline_keyboard": [[
            {"text": "✅ 開啟直播", "callback_data": f"open_stream:{stream_id}"},
            {"text": "❌ 略過",     "callback_data": f"skip_stream:{stream_id}"}
        ]]
    }

    await send_telegram(text, markup)
    print(f"[Stream] 已推播通知：{platform} / {channel}")


# ══════════════════════════════════════════════════════════════════════
# Twitch API
# ══════════════════════════════════════════════════════════════════════

_twitch_token = ""
_twitch_token_expires = 0

async def get_twitch_token() -> str:
    global _twitch_token, _twitch_token_expires
    if _twitch_token and datetime.now().timestamp() < _twitch_token_expires:
        return _twitch_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id":     TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type":    "client_credentials"
            }
        )
        data = resp.json()
        _twitch_token         = data["access_token"]
        _twitch_token_expires = datetime.now().timestamp() + data["expires_in"] - 60
        return _twitch_token


async def get_twitch_user_id(username: str) -> str:
    """用頻道名稱取得 Twitch user_id"""
    token = await get_twitch_token()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.twitch.tv/helix/users",
            params={"login": username},
            headers={
                "Client-ID":     TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {token}"
            }
        )
        data = resp.json().get("data", [])
        return data[0]["id"] if data else ""


async def subscribe_twitch_eventsub(broadcaster_id: str, channel: str):
    """訂閱 Twitch stream.online 事件"""
    token = await get_twitch_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.twitch.tv/helix/eventsub/subscriptions",
            headers={
                "Client-ID":     TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json"
            },
            json={
                "type":    "stream.online",
                "version": "1",
                "condition": {"broadcaster_user_id": broadcaster_id},
                "transport": {
                    "method":   "webhook",
                    "callback": f"{PUBLIC_URL}/webhook/twitch",
                    "secret":   TWITCH_WEBHOOK_SECRET
                }
            }
        )
        result = resp.json()
        if resp.status_code == 202:
            print(f"[Twitch] 已訂閱：{channel}（{broadcaster_id}）")
        else:
            print(f"[Twitch] 訂閱失敗：{channel} → {result}")


# ══════════════════════════════════════════════════════════════════════
# YouTube WebSub
# ══════════════════════════════════════════════════════════════════════

async def subscribe_youtube_websub(channel_id: str):
    """訂閱 YouTube WebSub 推播"""
    topic    = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    callback = f"{PUBLIC_URL}/webhook/youtube"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://pubsubhubbub.appspot.com/subscribe",
            data={
                "hub.callback":      callback,
                "hub.topic":         topic,
                "hub.verify":        "async",
                "hub.mode":          "subscribe",
                "hub.lease_seconds": "864000"    # 10 天，需要定期更新
            }
        )
        if resp.status_code in (200, 202, 204):
            print(f"[YouTube] 已訂閱 WebSub：{channel_id}")
        else:
            print(f"[YouTube] 訂閱失敗：{channel_id} → {resp.status_code}")


# ══════════════════════════════════════════════════════════════════════
# FastAPI 路由
# ══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """啟動時：設定 ngrok、訂閱所有頻道"""
    global PUBLIC_URL

    # 啟動 ngrok
    if NGROK_AUTHTOKEN:
        ngrok.set_auth_token(NGROK_AUTHTOKEN)
        listener   = await ngrok.forward(8000, authtoken=NGROK_AUTHTOKEN)
        PUBLIC_URL = listener.url()
        print(f"[ngrok] 公開 URL：{PUBLIC_URL}")
    else:
        PUBLIC_URL = os.getenv("PUBLIC_URL", "https://your-domain.com")
        print(f"[Webhook] 使用設定的 URL：{PUBLIC_URL}")

    # 訂閱 Twitch 頻道
    for channel in TWITCH_CHANNELS:
        broadcaster_id = await get_twitch_user_id(channel)
        if broadcaster_id:
            await subscribe_twitch_eventsub(broadcaster_id, channel)
        else:
            print(f"[Twitch] 找不到頻道：{channel}")

    # 訂閱 YouTube 頻道
    for channel_id in YOUTUBE_CHANNELS:
        await subscribe_youtube_websub(channel_id)

    await send_telegram(
        f"📡 直播監控已啟動\n"
        f"Twitch：{', '.join(TWITCH_CHANNELS) or '無'}\n"
        f"YouTube：{', '.join(YOUTUBE_CHANNELS) or '無'}"
    )

    yield

    # 關閉時通知
    await send_telegram("📴 直播監控已關閉")


app = FastAPI(lifespan=lifespan)


# ── Twitch EventSub Webhook ───────────────────────────────────────────
@app.post("/webhook/twitch")
async def twitch_webhook(request: Request):
    body      = await request.body()
    headers   = request.headers
    msg_id    = headers.get("twitch-eventsub-message-id", "")
    timestamp = headers.get("twitch-eventsub-message-timestamp", "")
    signature = headers.get("twitch-eventsub-message-signature", "")
    msg_type  = headers.get("twitch-eventsub-message-type", "")

    # 驗證簽名
    hmac_msg = (msg_id + timestamp + body.decode()).encode()
    expected = "sha256=" + hmac.new(
        TWITCH_WEBHOOK_SECRET.encode(),
        hmac_msg,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        print("[Twitch] 簽名驗證失敗")
        return Response(status_code=403)

    data = json.loads(body)

    # Webhook 驗證握手
    if msg_type == "webhook_callback_verification":
        challenge = data.get("challenge", "")
        print("[Twitch] Webhook 驗證成功")
        return Response(content=challenge, media_type="text/plain")

    # 直播開始通知
    if msg_type == "notification":
        event     = data.get("event", {})
        channel   = event.get("broadcaster_user_login", "")
        stream_id = event.get("id", msg_id)
        url       = f"https://twitch.tv/{channel}"

        # 取得直播標題
        title = "直播中"
        try:
            token = await get_twitch_token()
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.twitch.tv/helix/streams",
                    params={"user_login": channel},
                    headers={
                        "Client-ID":     TWITCH_CLIENT_ID,
                        "Authorization": f"Bearer {token}"
                    }
                )
                streams = r.json().get("data", [])
                if streams:
                    title = streams[0].get("title", "直播中")
        except Exception:
            pass

        asyncio.create_task(
            notify_stream_live("twitch", channel, title, url, stream_id)
        )

    return Response(status_code=200)


# ── YouTube WebSub Webhook ────────────────────────────────────────────
@app.get("/webhook/youtube")
async def youtube_verify(request: Request):
    """WebSub 訂閱驗證"""
    params    = request.query_params
    challenge = params.get("hub.challenge", "")
    print(f"[YouTube] WebSub 驗證：{params.get('hub.topic', '')}")
    return Response(content=challenge, media_type="text/plain")


@app.post("/webhook/youtube")
async def youtube_webhook(request: Request):
    """接收 YouTube 推播"""
    body = await request.body()
    print(f"[YouTube] 收到推播，長度：{len(body)}")

    try:
        # 解析 Atom XML
        root = ET.fromstring(body)
        ns   = {
            "atom":  "http://www.w3.org/2005/Atom",
            "yt":    "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/"
        }

        entry = root.find("atom:entry", ns)
        if entry is None:
            return Response(status_code=200)

        video_id   = entry.findtext("yt:videoId",   "", ns)
        channel_id = entry.findtext("yt:channelId", "", ns)
        title      = entry.findtext("atom:title",   "直播中", ns)
        url        = f"https://www.youtube.com/watch?v={video_id}"

        # 只有在監控清單裡的頻道才通知
        from tools.stream_monitor import get_monitored_channels
        monitored = get_monitored_channels().get("youtube", [])
        if channel_id not in monitored:
            return Response(status_code=200)

        # 取得頻道名稱
        channel_name = channel_id
        try:
            link = entry.find("atom:author/atom:name", ns)
            if link is not None:
                channel_name = link.text or channel_id
        except Exception:
            pass

        asyncio.create_task(
            notify_stream_live("youtube", channel_name, title, url, video_id)
        )

    except ET.ParseError as e:
        print(f"[YouTube] XML 解析失敗：{e}")

    return Response(status_code=200)


# ── Telegram Callback（處理按鈕回應）────────────────────────────────
@app.post("/telegram/callback")
async def telegram_callback(request: Request):
    """
    處理 Telegram inline keyboard 按鈕回應。
    注意：這個 endpoint 需要在 Telegram Bot 設定 Webhook，
    或是由 main.py 的 bot 處理 callback_query。
    """
    data = await request.json()
    return Response(status_code=200)


# ── 狀態查詢 ──────────────────────────────────────────────────────────
@app.get("/status")
async def status():
    from tools.stream_monitor import get_monitored_channels
    channels = get_monitored_channels()
    return {
        "public_url": PUBLIC_URL,
        "twitch":     channels["twitch"],
        "youtube":    channels["youtube"],
        "pending":    list(PENDING_STREAMS.keys())
    }


if __name__ == "__main__":
    import uvicorn # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
