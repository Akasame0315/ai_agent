"""
主入口：選擇用 CLI 測試 或 啟動 Telegram Bot
"""
import sys

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "telegram"

    if mode == "cli":
        from channels.cli import main
        main()
    else:
        from channels.telegram_bot import start_bot
        start_bot()
