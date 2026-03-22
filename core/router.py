"""
模型路由器
路徑：core/router.py

路由原則：
- 含個人資訊 / 敏感操作 → Ollama（全程本地）
- 一般查詢 → 雲端（快速）
- 含記憶關鍵字但查詢本身不敏感 → 雲端查詢 + 本地存記憶
"""

# ── 完全敏感：整個指令走 Ollama ───────────────────────────────────────
FULLY_SENSITIVE = [
    # 信件（真的含個人資訊）
    "信件", "email", "gmail", "郵件", "收信", "寄信",
    "回覆信", "寄件", "收件", "信箱", "寄給",
    "mail", "inbox", "check mail", "檢查信",
    "標記", "已讀", "未讀", "封信", "這封", "那封",
    "刪除信", "移到垃圾", "回覆這", "轉寄",
    # 帳密
    "密碼", "帳號", "帳戶", "銀行", "信用卡", "登入", "登錄",
    # 系統操作
    "shell", "執行指令", "讀取檔案", "讀檔",
    # 記憶操作
    "我的記憶", "列出記憶", "清除記憶",
]

# ── 含記憶關鍵字：雲端查詢 + 本地存記憶 ─────────────────────────────
MEMORY_SAVE_KEYWORDS = [
    "記住", "記得", "記錄", "幫我記",
    "我喜歡", "我不喜歡", "我習慣",
]


def route(message: str) -> tuple[str, bool]:
    """
    回傳 (provider, save_memory_locally)
    save_memory_locally=True：對話結束後在本地存記憶
    """
    from config import CLOUD_PROVIDER
    msg_lower = message.lower()

    for keyword in FULLY_SENSITIVE:
        if keyword.lower() in msg_lower:
            print(f"[Router] 敏感指令「{keyword}」→ Ollama")
            return "ollama", True

    for keyword in MEMORY_SAVE_KEYWORDS:
        if keyword.lower() in msg_lower:
            print(f"[Router] 記憶請求「{keyword}」→ {CLOUD_PROVIDER} + 本地存記憶")
            return CLOUD_PROVIDER, True

    print(f"[Router] 一般指令 → {CLOUD_PROVIDER}")
    return CLOUD_PROVIDER, False
