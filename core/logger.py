"""
統一 logging 設定
路徑：core/logger.py

使用方式：
  from core.logger import get_logger
  logger = get_logger(__name__)
  logger.info("訊息")
  logger.error("錯誤")
"""
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from core.paths import LOGS_DIR


def setup_logging():
    """初始化 logging，在 main.py 啟動時呼叫一次"""
    os.makedirs(LOGS_DIR, exist_ok=True)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return  # 已初始化過

    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ── Console handler：只顯示 INFO 以上 ────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    # ── 完整 log 檔：每天輪替，保留 7 天 ────────────────────────────
    full_log = TimedRotatingFileHandler(
        os.path.join(LOGS_DIR, "agent.log"),
        when="midnight", interval=1, backupCount=7,
        encoding="utf-8"
    )
    full_log.setLevel(logging.DEBUG)
    full_log.setFormatter(formatter)
    root_logger.addHandler(full_log)

    # ── 錯誤專用 log 檔：只記錄 WARNING 以上 ────────────────────────
    error_log = TimedRotatingFileHandler(
        os.path.join(LOGS_DIR, "error.log"),
        when="midnight", interval=1, backupCount=30,  # 錯誤保留更久
        encoding="utf-8"
    )
    error_log.setLevel(logging.WARNING)
    error_log.setFormatter(formatter)
    root_logger.addHandler(error_log)

    # 讓第三方套件安靜一點
    for noisy in ["httpx", "httpcore", "apscheduler", "telegram"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """取得指定名稱的 logger"""
    return logging.getLogger(name)
