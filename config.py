from dotenv import load_dotenv
import sys, os

# 打包成 exe 後，找 exe 同目錄的 .env；一般執行時找專案目錄的 .env
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(base_dir, '.env'))

# ── AI Provider 設定（"claude" / "gemini" / "groq" / "ollama"）────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

# ── API Keys ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")

# ── Ollama 本地設定 ────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "qwen2")

# ── Telegram ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
