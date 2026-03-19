from dotenv import load_dotenv
import os

load_dotenv()

# ── AI Provider 設定（"claude" / "gemini" / "groq"）────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")

# ── Telegram ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
