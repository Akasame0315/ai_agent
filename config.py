"""
設定檔
路徑：config.py
"""
from dotenv import load_dotenv
import os

load_dotenv()

# ── AI Provider 設定 ───────────────────────────────────────────────────
# 選項：claude / gemini / groq / ollama / auto
# auto = 自動根據指令內容選擇模型
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()

# ── API Keys ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")

# ── Ollama 本地設定 ────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

# ── 預設雲端模型（auto 模式下非敏感指令使用）──────────────────────────
CLOUD_PROVIDER  = os.getenv("CLOUD_PROVIDER", "groq").lower()

# ── Telegram ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
