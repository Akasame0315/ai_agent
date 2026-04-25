"""
config/loader.py
設定載入器 — 合併 settings.yaml 與 .env 金鑰，提供全域 cfg 物件
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

CONFIG_DIR = Path(__file__).parent
PROJECT_ROOT = CONFIG_DIR.parent


@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    載入設定，優先順序：
      1. 環境變數（已設定的）
      2. config/.env
      3. config/settings.yaml 預設值
    """
    # 載入 .env（若存在）
    env_path = CONFIG_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        # 嘗試 .env.example 提示
        print(f"[警告] 找不到 {env_path}，請複製 .env.example 為 .env 並填入金鑰")

    # 載入 YAML
    yaml_path = CONFIG_DIR / "settings.yaml"
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 注入機密環境變數
    cfg["telegram"]["token"] = _require_env("TELEGRAM_BOT_TOKEN")
    cfg["llm"]["groq_api_key"] = _require_env("GROQ_API_KEY", required=False)

    # 可選覆寫
    if os.getenv("OLLAMA_BASE_URL"):
        cfg["llm"]["ollama_base_url"] = os.environ["OLLAMA_BASE_URL"]

    return cfg


def _require_env(key: str, required: bool = True) -> str | None:
    value = os.getenv(key)
    if required and not value:
        raise EnvironmentError(
            f"必要的環境變數 '{key}' 未設定。\n"
            f"請確認 config/.env 中有填入 {key}=<your_value>"
        )
    return value
