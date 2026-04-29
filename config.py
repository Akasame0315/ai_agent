"""
config.py — 全域設定
路徑：config.py（專案根目錄）

唯一的設定載入點。其他模組一律：
    from config import cfg

不要在其他模組直接讀 os.environ 或重複 load_dotenv()。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv  # type: ignore

# ── .env 載入 ─────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
env_path = _HERE / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"✅ 成功從 {env_path} 載入設定")
else:
    parent_env = _HERE.parent / ".env"
    if parent_env.exists():
        load_dotenv(dotenv_path=parent_env, override=True)
        print(f"💡 在 {parent_env} 找到 .env")
    else:
        print("❌ 嚴重錯誤：找不到 .env 檔案！")

# ── 小工具 ────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    return val.strip() if val else default


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_list(key: str) -> list[int]:
    """逗號分隔的整數清單，例如 TELEGRAM_ALLOWED_USER_IDS=123,456"""
    raw = _env(key)
    if not raw:
        return []
    result = []
    for item in raw.split(","):
        try:
            result.append(int(item.strip()))
        except ValueError:
            pass
    return result


# ══════════════════════════════════════════════════════════════════════
# 設定資料類別
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LLMConfig:
    # auto = 由 router.py 決定；groq / ollama = 強制使用
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "auto"))
    # auto 模式下，非敏感指令預設走這個雲端 provider
    cloud_provider: str = field(default_factory=lambda: _env("CLOUD_PROVIDER", "groq"))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.3-70b-versatile"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:14b"))
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))
    max_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_TOKENS", 2048))
    temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.7))
    timeout: int = field(default_factory=lambda: _env_int("LLM_TIMEOUT", 60))
    max_tool_rounds: int = 5


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    allowed_user_ids: list[int] = field(default_factory=lambda: _env_list("TELEGRAM_ALLOWED_USER_IDS"))


@dataclass(frozen=True)
class AgentConfig:
    owner_name: str = field(default_factory=lambda: _env("AGENT_OWNER_NAME", "老闆"))
    assistant_name: str = field(default_factory=lambda: _env("AGENT_ASSISTANT_NAME", "Agent"))
    persona: str = field(default_factory=lambda: _env("AGENT_PERSONA", "assistant"))
    city: str = field(default_factory=lambda: _env("AGENT_CITY", "台北"))
    timezone: str = field(default_factory=lambda: _env("AGENT_TIMEZONE", "Asia/Taipei"))
    language: str = field(default_factory=lambda: _env("AGENT_LANGUAGE", "zh-TW"))
    system_prompt: str = field(default_factory=lambda: _env("AGENT_SYSTEM_PROMPT", ""))


@dataclass(frozen=True)
class SearchConfig:
    provider: str = field(default_factory=lambda: _env("SEARCH_PROVIDER", "duckduckgo"))
    serper_api_key: str = field(default_factory=lambda: _env("SERPER_API_KEY", ""))
    max_results: int = field(default_factory=lambda: _env_int("SEARCH_MAX_RESULTS", 5))


@dataclass(frozen=True)
class ExternalConfig:
    """第三方服務 API Keys"""
    youtube_api_key: str = field(default_factory=lambda: _env("YOUTUBE_API_KEY"))
    ngrok_authtoken: str = field(default_factory=lambda: _env("NGROK_AUTHTOKEN"))
    gmail_client_id: str = field(default_factory=lambda: _env("GMAIL_CLIENT_ID"))
    gmail_client_secret: str = field(default_factory=lambda: _env("GMAIL_CLIENT_SECRET"))
    twitch_client_id: str = field(default_factory=lambda: _env("TWITCH_CLIENT_ID"))
    twitch_client_secret: str = field(default_factory=lambda: _env("TWITCH_CLIENT_SECRET"))


@dataclass(frozen=True)
class PathConfig:
    """重要路徑（全部使用絕對路徑）"""
    root: str = field(default_factory=lambda: str(_HERE))
    agent_files: str = field(default_factory=lambda: str(_HERE / "agent_files"))
    data: str = field(default_factory=lambda: str(_HERE / "data"))
    logs: str = field(default_factory=lambda: str(_HERE / "logs"))
    skills: str = field(default_factory=lambda: str(_HERE / "skills"))

    def ensure_dirs(self) -> None:
        for d in [self.agent_files, self.data, self.logs]:
            os.makedirs(d, exist_ok=True)


@dataclass(frozen=True)
class Config:
    """根設定物件"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    external: ExternalConfig = field(default_factory=ExternalConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    debug: bool = field(
        default_factory=lambda: _env("DEBUG", "false").lower() == "true"
    )

    def validate(self) -> list[str]:
        missing: list[str] = []
        if not self.telegram.bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.llm.provider == "groq" and not self.llm.groq_api_key:
            missing.append("GROQ_API_KEY")
        if self.llm.provider == "auto" and self.llm.cloud_provider == "groq" and not self.llm.groq_api_key:
            missing.append("GROQ_API_KEY")
        return missing


# ── 全域單例 ──────────────────────────────────────────────────────────
cfg = Config()
