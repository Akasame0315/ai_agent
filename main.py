"""
主入口：選擇用 CLI 測試 或 啟動 Telegram Bot
"""
import logging, os, sys
from datetime import datetime

from core.paths import ensure_dirs
 
# 確保所有必要資料夾存在
ensure_dirs()

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        logging.FileHandler(
            f"logs/agent_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout)
    ]
)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "telegram"

    if mode == "cli":
        from channels.cli import main
        main()
    else:
        from channels.telegram_bot import start_bot
        start_bot()
