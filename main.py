"""
主入口：選擇用 CLI 測試 或 啟動 Telegram Bot
"""
import logging, sys
from core.paths import ensure_dirs
 
# 確保所有必要資料夾存在
ensure_dirs()

# 初始化 logging（必須在其他 import 之前）
from core.logger import setup_logging
setup_logging()

import logging
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "telegram"

    if mode == "cli":
        from channels.cli import main
        main()
    else:
        from channels.telegram_bot import start_bot
        start_bot()
