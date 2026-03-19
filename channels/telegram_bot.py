"""
Telegram Bot 介面
每個用戶有自己獨立的對話歷史（存在記憶體，重啟後清空）
"""
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
from core.agent import run_agent

# 每個 user_id 對應自己的對話歷史
conversation_histories: dict[int, list] = {}

def is_allowed(user_id: int) -> bool:
    return user_id == TELEGRAM_ALLOWED_USER_ID

# ── /start 指令 ────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return
    await update.message.reply_text(
        "👋 Agent 已啟動！\n\n"
        "可以試試：\n"
        "• 現在幾點？\n"
        "• 幫我寫一個叫 todo.txt 的檔案，內容是買牛奶\n"
        "• 讀取 todo.txt\n"
        "• 列出所有檔案\n\n"
        "輸入 /clear 清除對話記憶"
    )

# ── /clear 指令 ────────────────────────────────────────────────────────
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    user_id = update.effective_user.id
    conversation_histories[user_id] = []
    await update.message.reply_text("🗑️ 對話記憶已清除")

# ── 一般訊息處理 ───────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return

    user_text = update.message.text
    await update.message.reply_text("⏳ 思考中...")

    # 取得或初始化這個用戶的對話歷史
    history = conversation_histories.get(user_id, [])

    reply, updated_history = run_agent(user_text, history)

    # 更新歷史（避免無限增長，只保留最近 20 輪）
    conversation_histories[user_id] = updated_history[-40:]

    await update.message.reply_text(reply)

# ── 啟動 Bot ───────────────────────────────────────────────────────────
def start_bot():
    print("[Telegram Bot] 啟動中...")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("[Telegram Bot] 已上線，等待訊息...")
    app.run_polling()

if __name__ == "__main__":
    start_bot()