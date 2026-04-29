"""
core/router.py — LLM Provider 路由
路徑：core/router.py

職責：根據訊息內容與 skill 的 privacy_level 決定使用哪個 LLM provider。

規則（優先度由高到低）：
  1. cfg.llm.provider 明確指定（非 "auto"）→ 直接使用
  2. 訊息含敏感關鍵字 → 強制 "ollama"（本地，不送雲端）
  3. 其他 → cfg.llm.cloud_provider（預設 "groq"）

使用方式：
    from core.router import resolve_provider
    provider = resolve_provider(user_message, cfg)  # → "groq" | "ollama"
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)

# ── 敏感關鍵字清單 ────────────────────────────────────────────────────
# 包含以下任一關鍵字的訊息，強制走本地 Ollama
_SENSITIVE_KEYWORDS: frozenset[str] = frozenset({
    # 帳號/認證
    "密碼", "password", "帳號", "帳戶", "登入", "登錄",
    "2fa", "驗證碼", "otp",
    # 金融
    "信用卡", "銀行帳號", "轉帳", "atm",
    # 個資
    "身分證", "護照", "個人資料", "地址", "電話號碼",
    # 金鑰/Token
    "私鑰", "private key", "api key", "token", "secret",
    "ssh", "憑證",
    # 信件（含個人內容）
    "信件", "email", "gmail", "郵件", "收信", "寄信",
    "inbox", "寄件", "收件",
    # 記憶/知識庫（含個人資訊）
    "我的記憶", "列出記憶", "清除記憶",
})


def resolve_provider(user_message: str, cfg: "Config") -> str:
    """
    根據訊息內容決定使用哪個 LLM provider。

    Args:
        user_message: 使用者輸入的訊息
        cfg:          全域設定物件

    Returns:
        "groq" 或 "ollama"
    """
    # 明確指定 provider（非 auto）→ 直接使用
    if cfg.llm.provider != "auto":
        return cfg.llm.provider

    # 敏感關鍵字檢查
    msg_lower = user_message.lower()
    for keyword in _SENSITIVE_KEYWORDS:
        if keyword.lower() in msg_lower:
            logger.info(f"[Router] 偵測到敏感關鍵字「{keyword}」→ ollama（本地）")
            return "ollama"

    # 一般訊息 → 雲端 provider
    provider = cfg.llm.cloud_provider
    logger.debug(f"[Router] 一般訊息 → {provider}")
    return provider


def is_sensitive(user_message: str) -> bool:
    """
    單純判斷訊息是否包含敏感關鍵字（不依賴 cfg）。
    供其他模組（如 Planner）快速判斷用。
    """
    msg_lower = user_message.lower()
    return any(kw.lower() in msg_lower for kw in _SENSITIVE_KEYWORDS)
