"""
Telegram Bot 介面
路徑：channels/telegram_bot.py

啟動時同時跑 Heartbeat 排程器。
每個使用者有獨立的對話歷史（存在記憶體，重啟後清空）。
"""
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
from core.agent import run_agent

# 每個 user_id 對應自己的對話歷史
conversation_histories: dict[int, list] = {}


def is_allowed(user_id: int) -> bool:
    return user_id == TELEGRAM_ALLOWED_USER_ID


# ── /start ────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return
    await update.message.reply_text(
        "👋 Agent 已啟動！\n\n"
        "📅 排程任務：\n"
        "  • 每天 10:00 早安推播（天氣+信件+行程）\n"
        "  • 每天 22:00 晚安回顧\n\n"
        "指令：\n"
        "  /clear — 清除對話記憶\n"
        "  /test_morning — 立即測試早安推播\n"
        "  /test_evening — 立即測試晚安推播\n"
        "  /schedule — 查看排程狀態"
    )


# ── /clear ────────────────────────────────────────────────────────────
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    conversation_histories[update.effective_user.id] = []
    await update.message.reply_text("🗑️ 對話記憶已清除")


# ── /test_morning（立即觸發早安推播，方便測試）────────────────────────
async def cmd_test_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("⏳ 執行早安推播測試...")
    from scheduler.heartbeat import morning_heartbeat
    await morning_heartbeat()


# ── /test_evening ─────────────────────────────────────────────────────
async def cmd_test_evening(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from scheduler.heartbeat import evening_heartbeat
    await evening_heartbeat()


# ── /schedule（查看排程狀態）─────────────────────────────────────────
async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from scheduler.heartbeat import create_scheduler
    import datetime
    lines = ["⏰ 排程狀態：\n"]
    lines.append("  • 早安推播：每天 10:00")
    lines.append("  • 晚安推播：每天 22:00")
    now = datetime.datetime.now().strftime("%H:%M")
    lines.append(f"\n現在時間：{now}")
    await update.message.reply_text("\n".join(lines))


# ── 一般訊息處理 ───────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return

    user_text = update.message.text
    await update.message.reply_text("⏳ 思考中...")

    history = conversation_histories.get(user_id, [])
    reply, updated_history = run_agent(user_text, history)

    # 只保留最近 40 輪（避免無限增長）
    conversation_histories[user_id] = updated_history[-40:]

    # 超過 4000 字自動切段
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i+4000])


# ── 啟動 Bot + 排程器 ─────────────────────────────────────────────────
def start_bot():
    print("[Telegram Bot] 啟動中...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # 指令 handlers
    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("clear",        cmd_clear))
    app.add_handler(CommandHandler("test_morning", cmd_test_morning))
    app.add_handler(CommandHandler("test_evening", cmd_test_evening))
    app.add_handler(CommandHandler("schedule",     cmd_schedule))

    # 一般訊息
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))

# ── 啟動排程器（等 event loop 起來後再啟動）──────────────────────
    from scheduler.heartbeat import create_scheduler, init as heartbeat_init

    heartbeat_init(app.bot, TELEGRAM_ALLOWED_USER_ID)
    scheduler = create_scheduler()

    async def on_startup(application):
        scheduler.start()
        print("[Scheduler] 排程器已啟動")
        print("[Scheduler]   • 早安推播：每天 10:00")
        print("[Scheduler]   • 晚安推播：每天 22:00")

    async def on_shutdown(application):
        scheduler.shutdown()
        print("[Scheduler] 排程器已關閉")

    app.post_init     = on_startup
    app.post_shutdown = on_shutdown

    print("[Telegram Bot] 已上線，等待訊息...")
    app.run_polling()