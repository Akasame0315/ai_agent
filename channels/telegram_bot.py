"""
Telegram Bot 介面
路徑：channels/telegram_bot.py

改進：使用 run_agent_async，LLM 在背景 thread 跑，不阻塞 event loop。
"""
from telegram import Update # type: ignore
from telegram.ext import ( # type: ignore
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
from core.agent import run_agent_async

conversation_histories: dict[int, list] = {}


def is_allowed(user_id: int) -> bool:
    return user_id == TELEGRAM_ALLOWED_USER_ID


# ── /start ────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return
    from config import LLM_PROVIDER, CLOUD_PROVIDER, OLLAMA_MODEL
    mode = (
        f"自動路由（敏感 → Ollama，一般 → {CLOUD_PROVIDER}）"
        if LLM_PROVIDER == "auto"
        else LLM_PROVIDER
    )
    await update.message.reply_text(
        f"👋 Agent 已啟動！\n\n"
        f"🤖 模型模式：{mode}\n"
        f"🏠 本地模型：{OLLAMA_MODEL}\n\n"
        f"📅 排程：\n"
        f"  • 每天 10:00 早安推播\n"
        f"  • 每天 22:00 晚安回顧\n\n"
        f"指令：\n"
        f"  /clear         — 清除對話記憶\n"
        f"  /status        — 查看目前模型狀態\n"
        f"  /test_morning  — 測試早安推播\n"
        f"  /test_evening  — 測試晚安推播"
    )


# ── /clear ────────────────────────────────────────────────────────────
async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    conversation_histories[update.effective_user.id] = []
    await update.message.reply_text("🗑️ 對話記憶已清除")


# ── /status ───────────────────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from config import LLM_PROVIDER, CLOUD_PROVIDER, OLLAMA_MODEL, OLLAMA_BASE_URL
    import httpx # type: ignore

    # 檢查 Ollama 是否在線
    ollama_status = "❌ 離線"
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            ollama_status = f"✅ 在線（{', '.join(models[:3])}）"
    except Exception:
        pass

    lines = [
        "📊 目前狀態\n",
        f"模式：{LLM_PROVIDER}",
    ]
    if LLM_PROVIDER == "auto":
        lines.append(f"雲端模型：{CLOUD_PROVIDER}")
    lines += [
        f"本地模型：{OLLAMA_MODEL}",
        f"Ollama：{ollama_status}",
    ]
    await update.message.reply_text("\n".join(lines))


# ── /test_morning ─────────────────────────────────────────────────────
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


# ── /start_ollama ─────────────────────────────────────────────────────
async def cmd_start_ollama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("⏳ 嘗試啟動 Ollama...")
    from core.llm_ollama import _try_start_ollama
    ok = await asyncio.get_event_loop().run_in_executor(None, _try_start_ollama) # type: ignore
    if ok:
        await update.message.reply_text("✅ Ollama 已啟動")
    else:
        await update.message.reply_text("❌ 啟動失敗，請手動開啟 Ollama")


# ── 一般訊息處理 ───────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return

    user_text = update.message.text
    await update.message.reply_text("⏳ 思考中...")

    history = conversation_histories.get(user_id, [])

    # 非同步執行，不阻塞 event loop
    reply, updated_history = await run_agent_async(user_text, history)

    conversation_histories[user_id] = updated_history[-40:]

    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i+4000])


# ── 啟動 ──────────────────────────────────────────────────────────────
def start_bot():
    print("[Telegram Bot] 啟動中...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("clear",        cmd_clear))
    app.add_handler(CommandHandler("status",       cmd_status))
    app.add_handler(CommandHandler("test_morning", cmd_test_morning))
    app.add_handler(CommandHandler("test_evening", cmd_test_evening))
    app.add_handler(CommandHandler("start_ollama", cmd_start_ollama))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))

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
