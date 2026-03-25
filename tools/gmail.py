"""
Gmail 工具：收信、過濾、寄信
路徑：tools/gmail.py

第一次執行會開啟瀏覽器要求 Google 授權，
授權完成後會在專案根目錄產生 gmail_token.json，之後不需要再授權。
"""
import os
import base64
import re
from email.mime.text    import MIMEText
from email.mime.multipart import MIMEMultipart

# Gmail API 授權範圍
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # 標記已讀 / 移到垃圾桶
]

CREDENTIALS_FILE = "gmail_credentials.json"
TOKEN_FILE       = "gmail_token.json"

# ── 垃圾/廣告信判斷關鍵字 ─────────────────────────────────────────────
SPAM_KEYWORDS = [
    # 中文促銷
    "優惠", "折扣", "限時", "免費領取", "恭喜您", "中獎",
    "點擊領取", "立即搶購", "超低價", "特價", "促銷",
    "訂閱電子報", "取消訂閱", "unsubscribe",
    # 英文促銷
    "sale", "discount", "offer", "deal", "free gift",
    "congratulations you", "click here", "limited time",
    "act now", "buy now", "order now", "shop now",
    "you have been selected", "winner",
    # 垃圾信常見
    "no-reply@", "noreply@", "newsletter",
    "donotreply", "do-not-reply",
]


# ══════════════════════════════════════════════════════════════════════
# 授權
# ══════════════════════════════════════════════════════════════════════

def _get_service():
    """取得 Gmail API service，第一次執行會觸發瀏覽器授權"""
    from google.oauth2.credentials    import Credentials # type: ignore
    from google_auth_oauthlib.flow    import InstalledAppFlow # type: ignore
    from google.auth.transport.requests import Request # type: ignore
    from googleapiclient.discovery    import build # type: ignore

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"找不到 {CREDENTIALS_FILE}，"
                    "請先從 Google Cloud Console 下載 OAuth 憑證並放到專案根目錄"
                )
            flow  = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ══════════════════════════════════════════════════════════════════════
# 判斷是否為廣告/垃圾信
# ══════════════════════════════════════════════════════════════════════

def _is_spam(sender: str, subject: str, snippet: str) -> bool:
    text = f"{sender} {subject} {snippet}".lower()
    return any(kw.lower() in text for kw in SPAM_KEYWORDS)


def _is_spam_ai(sender: str, subject: str, snippet: str) -> bool:
    """用 LLM 語意判斷是否為廣告/垃圾信"""
    # 先用規則快速過濾明顯的垃圾信（省 API 呼叫）
    if _is_spam(sender, subject, snippet):
        return True

    # 讀取使用者的過濾偏好
    filter_prefs = _load_filter_prefs()

    prompt = f"""判斷以下信件是否為廣告、促銷、垃圾信或不重要的自動通知。

寄件人：{sender}
主旨：{subject}
摘要：{snippet[:200]}

使用者的過濾偏好：{filter_prefs}

只回答 "spam" 或 "important"，不要其他文字。"""

    try:
        import httpx, os
        from config import OLLAMA_BASE_URL, OLLAMA_MODEL

        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/v1/chat/completions",
            json={
                "model":    OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream":   False,
                "max_tokens": 10
            },
            timeout=15
        )
        result = resp.json()["choices"][0]["message"]["content"].strip().lower()
        return "spam" in result
    except Exception:
        return False   # 判斷失敗就預設為重要信件


def _load_filter_prefs() -> str:
    """從 persona.json 或記憶庫讀取過濾偏好"""
    try:
        from core.persona import load
        p = load()
        prefs = p.get("email_filter", [])
        if prefs:
            return "、".join(prefs)
    except Exception:
        pass
    return "一般廣告、促銷、電子報、系統自動通知"


# ══════════════════════════════════════════════════════════════════════
# 收信
# ══════════════════════════════════════════════════════════════════════

def check_inbox(max_results: int = 10, unread_only: bool = True) -> str:
    """
    檢查收件匣，自動過濾廣告信，只顯示重要信件。
    max_results: 最多查幾封（預設 10）
    unread_only: 只看未讀（預設 True）
    """
    try:
        service = _get_service()
        query   = "in:inbox"
        if unread_only:
            query += " is:unread"

        result   = service.users().messages().list(
            userId="me", q=query,
            maxResults=min(int(max_results), 20)
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return "📭 收件匣沒有新信件"

        important = []
        spam_count = 0

        for msg in messages:
            detail  = service.users().messages().get(
                userId="me", id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()

            headers = {
                h["name"]: h["value"]
                for h in detail["payload"]["headers"]
            }
            sender   = headers.get("From", "未知寄件人")
            subject  = headers.get("Subject", "（無主旨）")
            date     = headers.get("Date", "")
            snippet  = detail.get("snippet", "")
            msg_id   = msg["id"]

            if _is_spam_ai(sender, subject, snippet):
                spam_count += 1
                continue

            important.append({
                "id":      msg_id,
                "sender":  sender,
                "subject": subject,
                "date":    date,
                "snippet": snippet[:100]
            })

        if not important:
            return (
                f"📭 沒有重要信件\n"
                f"（已過濾 {spam_count} 封廣告/垃圾信）"
            )

        lines = [
            f"📬 找到 {len(important)} 封重要信件"
            + (f"（已過濾 {spam_count} 封廣告信）" if spam_count else "")
            + "\n"
        ]
        for i, m in enumerate(important, 1):
            lines.append(
                f"【{i}】{m['subject']}\n"
                f"   寄件人：{m['sender']}\n"
                f"   時間：{m['date']}\n"
                f"   摘要：{m['snippet']}\n"
                f"   ID：{m['id']}"
            )

        return "\n".join(lines)

    except FileNotFoundError as e:
        return f"❌ {e}"
    except Exception as e:
        return f"❌ 收信失敗：{e}"


def read_email(message_id: str) -> str:
    """
    讀取特定信件的完整內容。
    message_id 從 check_inbox 的結果裡取得。
    """
    try:
        service = _get_service()
        detail  = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = {
            h["name"]: h["value"]
            for h in detail["payload"]["headers"]
        }
        sender  = headers.get("From", "")
        subject = headers.get("Subject", "（無主旨）")
        date    = headers.get("Date", "")

        # 抓取信件內文
        body = _extract_body(detail["payload"])

        # 標記為已讀
        service.users().messages().modify(
            userId="me", id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()

        return (
            f"📧 信件內容\n"
            f"主旨：{subject}\n"
            f"寄件人：{sender}\n"
            f"時間：{date}\n"
            f"{'─' * 30}\n"
            f"{body[:2000]}"
            + ("...\n（內容過長，已截斷）" if len(body) > 2000 else "")
        )

    except Exception as e:
        return f"❌ 讀取信件失敗：{e}"


def _extract_body(payload: dict) -> str:
    """從 Gmail payload 中提取純文字內文"""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        # 沒有純文字就用 HTML 版本（去掉標籤）
        for part in payload["parts"]:
            if part["mimeType"] == "text/html":
                data = part["body"].get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    return re.sub(r'<[^>]+>', '', html).strip()
    else:
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    return "（無法讀取內文）"


# ══════════════════════════════════════════════════════════════════════
# 寄信
# ══════════════════════════════════════════════════════════════════════

def send_email(to: str, subject: str, body: str, cc: str = "") -> str:
    """
    寄送電子郵件。
    to:      收件人 email（多個用逗號分隔）
    subject: 主旨
    body:    內文
    cc:      副本（選填）
    """
    try:
        service = _get_service()

        msg = MIMEMultipart()
        msg["To"]      = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "plain", "utf-8"))

        raw     = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result  = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        return (
            f"✅ 信件已寄出\n"
            f"   收件人：{to}\n"
            f"   主旨：{subject}\n"
            f"   郵件 ID：{result.get('id', '')}"
        )

    except Exception as e:
        return f"❌ 寄信失敗：{e}"


def reply_email(message_id: str, body: str) -> str:
    """
    回覆指定信件。
    message_id 從 check_inbox 或 read_email 取得。
    """
    try:
        service = _get_service()

        # 取得原始信件資訊
        original = service.users().messages().get(
            userId="me", id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID"]
        ).execute()

        headers    = {h["name"]: h["value"] for h in original["payload"]["headers"]}
        to         = headers.get("From", "")
        subject    = headers.get("Subject", "")
        message_id_header = headers.get("Message-ID", "")
        thread_id  = original.get("threadId", "")

        # 主旨加上 Re:
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"

        msg = MIMEMultipart()
        msg["To"]         = to
        msg["Subject"]    = subject
        msg["In-Reply-To"] = message_id_header
        msg["References"]  = message_id_header
        msg.attach(MIMEText(body, "plain", "utf-8"))

        raw    = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": thread_id}
        ).execute()

        return (
            f"✅ 回覆已寄出\n"
            f"   回覆給：{to}\n"
            f"   主旨：{subject}"
        )

    except Exception as e:
        return f"❌ 回覆失敗：{e}"


def move_to_trash(message_id: str) -> str:
    """把指定信件移到垃圾桶"""
    try:
        service = _get_service()
        service.users().messages().trash(
            userId="me", id=message_id
        ).execute()
        return f"🗑️ 已將信件移到垃圾桶"
    except Exception as e:
        return f"❌ 移動失敗：{e}"


def mark_as_read(message_id: str) -> str:
    """把指定信件標記為已讀"""
    try:
        service = _get_service()
        service.users().messages().modify(
            userId="me", id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        return f"✅ 已標記為已讀：{message_id}"
    except Exception as e:
        return f"❌ 標記失敗：{e}"


def mark_as_unread(message_id: str) -> str:
    """把指定信件標記為未讀"""
    try:
        service = _get_service()
        service.users().messages().modify(
            userId="me", id=message_id,
            body={"addLabelIds": ["UNREAD"]}
        ).execute()
        return f"✅ 已標記為未讀：{message_id}"
    except Exception as e:
        return f"❌ 標記失敗：{e}"