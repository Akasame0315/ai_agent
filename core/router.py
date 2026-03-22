"""
模型路由器
路徑：core/router.py

根據使用者訊息內容，自動決定要用本地模型還是雲端模型。
敏感指令 → Ollama（本地，隱私安全）
一般指令 → Groq（雲端，快速）
"""

# ── 敏感關鍵字：出現這些詞就用本地模型 ──────────────────────────────
SENSITIVE_KEYWORDS = [
    # 信件
    "信件", "email", "gmail", "郵件", "收信", "寄信", "回覆信",
    "寄件", "收件", "信箱", "mail",
    # 記憶與個人資料
    "記憶", "記住", "記得", "我的資料", "個人", "隱私",
    "密碼", "帳號", "帳戶", "銀行", "信用卡",
    # 檔案操作
    "讀取檔案", "寫入檔案", "我的文件", "讀檔", "存檔",
    # 知識庫
    "知識庫", "rag", "匯入文件", "研究主題",
    # 瀏覽器（可能包含個人資訊）
    "登入", "登錄", "帳密", "填寫表單",
    # 系統
    "shell", "執行指令", "終端機",
]

def route(message: str) -> str:
    """
    分析訊息，回傳應使用的 provider。
    回傳值：'ollama' 或 CLOUD_PROVIDER（groq/gemini/claude）
    """
    from config import CLOUD_PROVIDER
    msg_lower = message.lower()

    for keyword in SENSITIVE_KEYWORDS:
        if keyword.lower() in msg_lower:
            print(f"[Router] 偵測到敏感關鍵字「{keyword}」→ 使用本地 Ollama")
            return "ollama"

    print(f"[Router] 一般指令 → 使用雲端 {CLOUD_PROVIDER}")
    return CLOUD_PROVIDER
