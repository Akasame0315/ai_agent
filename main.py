"""
主入口
路徑：main.py

支援模式：
  python main.py           → Telegram Bot（預設）
  python main.py cli       → 終端機測試
  python main.py webhook   → 只跑 Webhook Server
  python main.py all       → Bot + Webhook 同時跑（沙盒推薦）
"""
import sys
from core.paths import ensure_dirs
 
# 確保所有必要資料夾存在
ensure_dirs()

from core.logger import setup_logging
setup_logging()

import logging
logger = logging.getLogger(__name__)


def run_bot():
    from channels.telegram_bot import start_bot
    start_bot()


def run_webhook():
    import uvicorn # type: ignore
    from webhook_server import app
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


def run_all():
    """同時跑 Bot 和 Webhook（用 threading）"""
    import threading

    webhook_thread = threading.Thread(target=run_webhook, daemon=True)
    webhook_thread.start()
    logger.info("Webhook Server 已在背景啟動（port 8000）")

    # Bot 在主執行緒跑（因為 telegram bot 需要主執行緒的 event loop）
    run_bot()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "telegram"
    logger.info(f"Agent 啟動，模式：{mode}")

    if mode == "cli":
        from channels.cli import main
        main()
    elif mode == "webhook":
        run_webhook()
    elif mode == "all":
        run_all()
    else:
        run_bot()
