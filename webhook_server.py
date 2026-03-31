"""
Webhook 接收伺服器
路徑：webhook_server.py（專案根目錄）

目前啟用：YouTube WebSub
暫停啟用：Twitch EventSub（API 設定中，程式已保留）

啟動方式：python webhook_server.py
"""
import asyncio
import json
import os
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager

import logging
import httpx # type: ignore
import ngrok # type: ignore
logger = logging.getLogger(__name__)
from fastapi import FastAPI, Request, Response # type: ignore
from dotenv import load_dotenv # type: ignore

load_dotenv()

# ── 設定 ──────────────────────────────────────────────────────────────
TWITCH_ENABLED       = os.getenv("TWITCH_ENABLED", "false").lower() == "true"
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TWITCH_WEBHOOK_SECRET = os.getenv("TWITCH_WEBHOOK_SECRET", "mysecret")
TWITCH_CHANNELS      = [c.strip() for c in os.getenv("TWITCH_CHANNELS", "").split(",") if c.strip()]

TELEGRAM_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID     = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")

NGROK_AUTHTOKEN      = os.getenv("NGROK_AUTHTOKEN", "")
YOUTUBE_CHANNELS     = [c.strip() for c in os.getenv("YOUTUBE_CHANNELS", "").split(",") if c.strip()]

# 全域儲存 ngrok URL（啟動後取得）
PUBLIC_URL = ""

# 待確認的直播通知 {callback_id: url}
PENDING_STREAMS: dict[str, str] = {}


# ── Telegram 推播 ────────────────────────────────────────────────────
async def send_telegram(text: str, reply_markup: dict = None):
    payload = {"chat_id": TELEGRAM_USER_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json=payload, timeout=10
            )
        except Exception as e:
            print(f"[Telegram] 推播失敗：{e}")


async def notify_stream_live(platform: str, channel: str, title: str, url: str, stream_id: str):
    from tools.stream_monitor import is_notified, mark_notified
    if is_notified(stream_id):
        return
    mark_notified(stream_id)
    PENDING_STREAMS[stream_id] = url

    # 同步寫入檔案讓 telegram_bot 也能讀取
    pending_file = os.path.join("data", "pending_streams.json")
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
    await send_telegram(
        f"{emoji} <b>{channel}</b> 開始直播了！\n\n📺 {title}\n🔗 {url}\n\n要開啟直播嗎？",
        markup
    )
    print(f"[Stream] 推播通知：{platform} / {channel}")


# ── YouTube WebSub ────────────────────────────────────────────────────
async def subscribe_youtube_websub(channel_id: str) -> bool:
    """訂閱 YouTube WebSub，回傳是否成功發送訂閱請求"""
    topic    = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    callback = f"{PUBLIC_URL}/youtube/webhook"

    if not PUBLIC_URL:
        logger.error("[YouTube] PUBLIC_URL 未設定，無法訂閱")
        return False

    logger.info(f"[YouTube] 訂閱 WebSub：{channel_id}")
    logger.info(f"[YouTube] Callback URL：{callback}")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://pubsubhubbub.appspot.com/subscribe",
                data={
                    "hub.callback":      callback,
                    "hub.topic":         topic,
                    "hub.verify":        "async",
                    "hub.mode":          "subscribe",
                    "hub.lease_seconds": "864000"
                },
                timeout=15
            )
            if resp.status_code in (200, 202, 204):
                logger.info(f"[YouTube] 訂閱請求已接受（{resp.status_code}），等待 PubSubHubbub 驗證 GET {callback}")
                return True
            else:
                logger.error(f"[YouTube] 訂閱失敗：{resp.status_code} {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"[YouTube] 訂閱異常：{e}")
        return False


# ── Twitch（保留但預設停用）──────────────────────────────────────────
async def _setup_twitch():
    """Twitch 設定，TWITCH_ENABLED=true 時才執行"""
    if not TWITCH_ENABLED:
        print("[Twitch] 已停用（設定 TWITCH_ENABLED=true 可啟用）")
        return
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        print("[Twitch] 缺少 API 憑證，跳過")
        return

    try:
        # 取得 Access Token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id":     TWITCH_CLIENT_ID,
                    "client_secret": TWITCH_CLIENT_SECRET,
                    "grant_type":    "client_credentials"
                }
            )
            token = resp.json().get("access_token", "")

        if not token:
            print("[Twitch] 無法取得 token，跳過")
            return

        # 訂閱頻道
        for channel in TWITCH_CHANNELS:
            # 取得 user_id
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.twitch.tv/helix/users",
                    params={"login": channel},
                    headers={"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {token}"}
                )
                data = r.json().get("data", [])
                if not data:
                    print(f"[Twitch] 找不到頻道：{channel}")
                    continue
                user_id = data[0]["id"]

            # 訂閱 EventSub
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.twitch.tv/helix/eventsub/subscriptions",
                    headers={
                        "Client-ID": TWITCH_CLIENT_ID,
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "type": "stream.online", "version": "1",
                        "condition": {"broadcaster_user_id": user_id},
                        "transport": {
                            "method": "webhook",
                            "callback": f"{PUBLIC_URL}/webhook/twitch",
                            "secret": TWITCH_WEBHOOK_SECRET
                        }
                    }
                )
                if r.status_code == 202:
                    print(f"[Twitch] 已訂閱：{channel}")
                else:
                    print(f"[Twitch] 訂閱失敗：{channel} → {r.status_code} {r.text}")
    except Exception as e:
        print(f"[Twitch] 設定失敗，跳過：{e}")


# ── FastAPI ───────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global PUBLIC_URL

    # 啟動 ngrok
    if NGROK_AUTHTOKEN:
        try:
            ngrok.set_auth_token(NGROK_AUTHTOKEN)
            listener   = await ngrok.forward(8000, authtoken=NGROK_AUTHTOKEN)
            PUBLIC_URL = listener.url()
            print(f"[ngrok] 公開 URL：{PUBLIC_URL}")
        except Exception as e:
            print(f"[ngrok] 啟動失敗：{e}")
            PUBLIC_URL = os.getenv("PUBLIC_URL", "")
    else:
        PUBLIC_URL = os.getenv("PUBLIC_URL", "")
        print(f"[Webhook] PUBLIC_URL：{PUBLIC_URL or '未設定'}")

    if not PUBLIC_URL:
        print("[Webhook] ⚠️ 沒有公開 URL，無法接收推播")
    else:
        # 訂閱 YouTube
        for ch in YOUTUBE_CHANNELS:
            await subscribe_youtube_websub(ch)

        # 嘗試訂閱 Twitch（失敗不影響 YouTube）
        await _setup_twitch()

    status_lines = [
        f"📡 直播監控已啟動",
        f"YouTube：{', '.join(YOUTUBE_CHANNELS) or '無'}",
        f"Twitch：{'啟用' if TWITCH_ENABLED else '停用（可設定 TWITCH_ENABLED=true 開啟）'}",
    ]
    await send_telegram("\n".join(status_lines))

    # 取消輪詢排程（備用，每 30 分鐘檢查一次）
    # from apscheduler.schedulers.asyncio import AsyncIOScheduler # type: ignore
    # poll_scheduler = AsyncIOScheduler(timezone="Asia/Taipei")

    # async def _poll():
    #     from tools.stream_check import poll_all_streams
    #     count = await poll_all_streams(notify_stream_live)
    #     if count:
    #         logger.info(f"[Poll] 本次發現 {count} 個新直播")

    # poll_scheduler.add_job(
    #     _poll,
    #     "interval", minutes=30,
    #     id="stream_poll",
    #     replace_existing=True
    # )
    # poll_scheduler.start()
    # logger.info("[StreamPoll] 輪詢排程已啟動（每 30 分鐘）")

    yield

    # poll_scheduler.shutdown()
    await send_telegram("📴 直播監控已關閉")


app = FastAPI(lifespan=lifespan)


@app.get("/youtube/webhook")
async def youtube_verify(request: Request):
    params    = request.query_params
    challenge = params.get("hub.challenge", "")
    topic     = params.get("hub.topic", "")
    
    # 從 topic 中解析出 channel_id (通常在網址最後面)
    channel_id = topic.split("channel_id=")[-1] if "channel_id=" in topic else "未知頻道"
    
    print(f"[YouTube] WebSub 驗證請求：{channel_id}")
    
    if challenge:
        # --- 方案 B：反向推播通知 ---
        # 這裡我們發送一個非同步任務來通知使用者驗證成功
        asyncio.create_task(send_telegram(
            f"✅ <b>YouTube 監控已生效</b>\n"
            f"頻道 ID：<code>{channel_id}</code>\n"
            f"Google 已完成 WebSub 驗證，現在開始會即時接收直播通知。"
        ))
        
        return Response(content=challenge, media_type="text/plain")
    
    return Response(status_code=404)


@app.post("/youtube/webhook")
async def youtube_webhook(request: Request):
    body = await request.body()
    try:
        root  = ET.fromstring(body)
        ns    = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt":   "http://www.youtube.com/xml/schemas/2015"
        }
        entry = root.find("atom:entry", ns)
        if entry is None:
            return Response(status_code=200)

        video_id   = entry.findtext("yt:videoId",   "", ns)
        channel_id = entry.findtext("yt:channelId", "", ns)
        title      = entry.findtext("atom:title",   "新直播/影片", ns)
        url        = f"https://www.youtube.com/watch?v={video_id}"

        from tools.stream_monitor import get_monitored_channels
        if channel_id in get_monitored_channels().get("youtube", []):
            channel_name = channel_id
            try:
                author = entry.find("atom:author/atom:name", ns)
                if author is not None:
                    channel_name = author.text or channel_id
            except Exception:
                pass
            asyncio.create_task(
                notify_stream_live("youtube", channel_name, title, url, video_id)
            )
    except ET.ParseError as e:
        print(f"[YouTube] XML 解析失敗：{e}")
    return Response(status_code=200)


@app.post("/webhook/twitch")
async def twitch_webhook(request: Request):
    """Twitch EventSub（停用時也要保留 endpoint 避免 404）"""
    if not TWITCH_ENABLED:
        return Response(status_code=200)

    import hashlib, hmac as _hmac
    body      = await request.body()
    headers   = request.headers
    msg_id    = headers.get("twitch-eventsub-message-id", "")
    timestamp = headers.get("twitch-eventsub-message-timestamp", "")
    signature = headers.get("twitch-eventsub-message-signature", "")
    msg_type  = headers.get("twitch-eventsub-message-type", "")

    hmac_msg = (msg_id + timestamp + body.decode()).encode()
    expected = "sha256=" + _hmac.new(
        TWITCH_WEBHOOK_SECRET.encode(), hmac_msg, hashlib.sha256
    ).hexdigest()

    if not _hmac.compare_digest(expected, signature):
        return Response(status_code=403)

    data = json.loads(body)
    if msg_type == "webhook_callback_verification":
        return Response(content=data.get("challenge", ""), media_type="text/plain")

    if msg_type == "notification":
        event   = data.get("event", {})
        channel = event.get("broadcaster_user_login", "")
        url     = f"https://twitch.tv/{channel}"
        asyncio.create_task(
            notify_stream_live("twitch", channel, "直播中", url, msg_id)
        )
    return Response(status_code=200)


@app.get("/status")
async def status():
    from tools.stream_monitor import get_monitored_channels
    channels = get_monitored_channels()
    return {
        "public_url":    PUBLIC_URL,
        "youtube":       channels["youtube"],
        "twitch":        channels["twitch"],
        "twitch_enabled": TWITCH_ENABLED,
        "pending":       list(PENDING_STREAMS.keys())
    }



@app.get("/debug/websub")
async def debug_websub(channel_id: str = ""):
    """診斷 WebSub 訂閱狀態"""
    if not channel_id:
        channels_info = {
            "public_url": PUBLIC_URL,
            "webhook_url": f"{PUBLIC_URL}/youtube/webhook",
            "youtube_channels": YOUTUBE_CHANNELS,
        }
        return channels_info
    topic    = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    callback = f"{PUBLIC_URL}/youtube/webhook"
    return {
        "channel_id":   channel_id,
        "topic":        topic,
        "callback":     callback,
        "public_url":   PUBLIC_URL,
    }

@app.get("/debug/subscribe_now")
async def force_subscribe(channel_id: str):
    if not channel_id:
        return {"status": "error", "message": "Missing channel_id"}
    
    success = await subscribe_youtube_websub(channel_id)
    return {
        "status": "success" if success else "failed",
        "channel_id": channel_id,
        "callback_url": f"{PUBLIC_URL}/youtube/webhook"
    }


if __name__ == "__main__":
    import uvicorn # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
