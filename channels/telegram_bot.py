"""
Telegram Bot 介面
路徑：channels/telegram_bot.py

新增功能：
- /stop   緊急停止所有任務
- /tasks  查看任務清單
- /cancel 取消指定任務
- 支援背景任務推播
- 多線程任務不阻塞對話
"""
from telegram import Update # type: ignore
from telegram.ext import ( # type: ignore
    ApplicationBuilder, MessageHandler,
    CommandHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID
from core.agent import run_agent_async

conversation_histories: dict[int, list] = {}


def is_allowed(user_id: int) -> bool:
    return user_id == TELEGRAM_ALLOWED_USER_ID


def _strip_tool_history(history: list) -> list:
    """切換模型時保留純文字，移除 tool_use / tool_result"""
    cleaned = []
    for msg in history:
        content = msg["content"]
        if isinstance(content, str):
            cleaned.append(msg)
        elif isinstance(content, list):
            text_parts = [
                b for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if text_parts:
                combined = " ".join(b.get("text", "") for b in text_parts)
                if combined.strip():
                    cleaned.append({"role": msg["role"], "content": combined})
    return cleaned


# ── /start ────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return
    from config import LLM_PROVIDER, CLOUD_PROVIDER, OLLAMA_MODEL
    mode = (
        f"自動路由（敏感 → Ollama {OLLAMA_MODEL}，一般 → {CLOUD_PROVIDER}）"
        if LLM_PROVIDER == "auto" else LLM_PROVIDER
    )
    await update.message.reply_text(
        f"👋 Agent 已啟動！\n\n"
        f"🤖 模型模式：{mode}\n"
        f"🏠 本地模型：{OLLAMA_MODEL}\n\n"
        f"📅 排程：\n"
        f"  • 每天 10:00 早安推播\n"
        f"  • 每天 22:00 晚安回顧\n\n"
        f"指令：\n"
        f"  /stop          — 🚨 緊急停止所有動作\n"
        f"  /tasks         — 查看背景任務清單\n"
        f"  /cancel [id]   — 取消指定任務\n"
        f"  /status        — 查看模型狀態\n"
        f"  /clear         — 清除對話記憶\n"
        f"  /test_morning  — 測試早安推播\n"
        f"  /test_evening  — 測試晚安推播\n"
        f"  /restart       — 重啟 Agent"
    )


# ── /stop 緊急停止 ────────────────────────────────────────────────────
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from core.emergency_stop import trigger_stop
    from core.task_manager   import task_manager
    trigger_stop()
    result = task_manager.cancel_all()
    await update.message.reply_text(
        f"🚨 緊急停止已觸發！\n{result}\n\n"
        f"所有鍵盤/滑鼠操作已中止。\n"
        f"傳送 /reset 可重置停止旗標繼續使用。"
    )


# ── /reset 重置停止旗標 ───────────────────────────────────────────────
async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from core.emergency_stop import reset_stop
    reset_stop()
    await update.message.reply_text("✅ 停止旗標已重置，Agent 恢復正常運作")


# ── /tasks 查看任務 ───────────────────────────────────────────────────
async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    from core.task_manager import task_manager
    await update.message.reply_text(task_manager.list_tasks())


# ── /cancel 取消任務 ──────────────────────────────────────────────────
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    args = context.args
    if not args:
        from core.task_manager import task_manager
        result = task_manager.cancel_all()
        await update.message.reply_text(result)
        return
    from core.task_manager import task_manager
    result = task_manager.cancel(args[0])
    await update.message.reply_text(result)


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

    from core.emergency_stop import is_stopped
    stop_status = "🚨 停止中（傳 /reset 恢復）" if is_stopped() else "✅ 正常運作"

    lines = [
        "📊 目前狀態\n",
        f"模式：{LLM_PROVIDER}",
        f"雲端：{CLOUD_PROVIDER}" if LLM_PROVIDER == "auto" else "",
        f"本地：{OLLAMA_MODEL}",
        f"Ollama：{ollama_status}",
        f"Agent：{stop_status}",
    ]
    await update.message.reply_text("\n".join(l for l in lines if l))


# ── /test_morning / /test_evening ────────────────────────────────────
async def cmd_test_morning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("⏳ 執行早安推播測試...")
    from scheduler.heartbeat import morning_heartbeat
    await morning_heartbeat()


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

# ── /restart ───────────────────────────────────────────────────────
async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text("🔄 重啟中...")
    import subprocess, sys, os
    subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=os.path.dirname(os.path.abspath("main.py")),
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    os._exit(0)


# ── 工具歷史清理 ─────────────────────────────────────────────────────
def _strip_tool_history(history: list) -> list:
    """
    切換模型時，保留純文字對話，移除 tool_use / tool_result。
    這樣新模型知道對話脈絡，但不會嘗試呼叫不存在的工具。
    """
    cleaned = []
    for msg in history:
        content = msg["content"]
        if isinstance(content, str):
            cleaned.append(msg)
        elif isinstance(content, list):
            # 只保留 type=text 的部分
            text_parts = [
                b for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if text_parts:
                # 合併成純文字訊息
                combined = " ".join(b.get("text", "") for b in text_parts)
                if combined.strip():
                    cleaned.append({
                        "role":    msg["role"],
                        "content": combined
                    })
    return cleaned

# ── Inline Keyboard 按鈕（直播通知）─────────────────────────────────
async def handle_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    if not is_allowed(user_id):
        await query.answer("⛔ 無權限")
        return
    await query.answer()
    data = query.data

    if data.startswith("open_stream:"):
        stream_id = data.replace("open_stream:", "")
        try:
            import json, os
            pending_file = "pending_streams.json"
            if os.path.exists(pending_file):
                with open(pending_file) as f:
                    pending = json.load(f)
                url = pending.get(stream_id, "")
                if url:
                    import webbrowser
                    webbrowser.open(url)
                    await query.edit_message_text(f"✅ 已開啟直播：{url}")
                    del pending[stream_id]
                    with open(pending_file, "w") as f:
                        json.dump(pending, f)
                else:
                    await query.edit_message_text("❌ 找不到直播連結，可能已過期")
            else:
                await query.edit_message_text("❌ 找不到待確認的直播")
        except Exception as e:
            await query.edit_message_text(f"❌ 開啟失敗：{e}")

    elif data.startswith("skip_stream:"):
        await query.edit_message_text("⏭ 已略過此次直播通知")


# ── 一般訊息處理 ───────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("⛔ 你沒有使用權限")
        return

    # 檢查緊急停止旗標
    from core.emergency_stop import is_stopped
    if is_stopped():
        await update.message.reply_text(
            "🚨 Agent 目前處於停止狀態\n傳送 /reset 可恢復正常運作"
        )
        return

    user_text = update.message.text

    # 判斷這次用哪個模型
    from config import LLM_PROVIDER
    if LLM_PROVIDER == "auto":
        from core.router import route
        current_provider, _ = route(user_text)
    else:
        current_provider = LLM_PROVIDER

    history = conversation_histories.get(user_id, [])

    # 模型切換時清除工具歷史
    last_provider = context.user_data.get("last_provider")
    if last_provider and last_provider != current_provider:
        print(f"[Bot] 模型切換 {last_provider} → {current_provider}，清除工具歷史")
        history = _strip_tool_history(history)
    context.user_data["last_provider"] = current_provider

    await update.message.reply_text("⏳ 思考中...")

    reply, updated_history = await run_agent_async(user_text, history)
    conversation_histories[user_id] = updated_history[-40:]

    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i+4000])


# ── Error Handler ─────────────────────────────────────────────────────
async def error_handler(update, context):
    import telegram.error as tg_err # type: ignore
    err = context.error
    if isinstance(err, tg_err.NetworkError):
        print(f"[Bot] 網路錯誤（自動重連中）：{err}")
        return
    print(f"[Bot] 未預期錯誤：{err}")


# ── 啟動 ──────────────────────────────────────────────────────────────
def start_bot():
    print("[Telegram Bot] 啟動中...")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("stop",         cmd_stop))
    app.add_handler(CommandHandler("reset",        cmd_reset))
    app.add_handler(CommandHandler("tasks",        cmd_tasks))
    app.add_handler(CommandHandler("cancel",       cmd_cancel))
    app.add_handler(CommandHandler("clear",        cmd_clear))
    app.add_handler(CommandHandler("status",       cmd_status))
    app.add_handler(CommandHandler("test_morning", cmd_test_morning))
    app.add_handler(CommandHandler("test_evening", cmd_test_evening))
    app.add_handler(CommandHandler("start_ollama", cmd_start_ollama))
    app.add_handler(CommandHandler("restart",      cmd_restart))
    app.add_handler(CallbackQueryHandler(handle_stream_callback))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))
    app.add_error_handler(error_handler)

    from scheduler.heartbeat import create_scheduler, init as heartbeat_init
    heartbeat_init(app.bot, TELEGRAM_ALLOWED_USER_ID)
    scheduler = create_scheduler()

    # 注入 task_manager 推播 callback
    from core.task_manager import task_manager
    async def _push(text: str):
        await app.bot.send_message(chat_id=TELEGRAM_ALLOWED_USER_ID, text=text)
    task_manager.set_notify(_push)

    async def on_startup(application):
        scheduler.start()
        print("[Scheduler] 排程器已啟動")

        # 啟動鍵盤快捷鍵監聽
        from core.emergency_stop import start_keyboard_listener
        start_keyboard_listener()
        print("[EmergencyStop] Ctrl+Shift+F12 緊急停止已啟用")

        # 啟動通知
        from config import LLM_PROVIDER, CLOUD_PROVIDER, OLLAMA_MODEL
        mode = (
            f"自動路由（{CLOUD_PROVIDER} + Ollama）"
            if LLM_PROVIDER == "auto" else LLM_PROVIDER
        )
        startup_msg = (
            f"✅ Agent 已上線！\n\n"
            f"🤖 模型模式：{mode}\n\n"
            f"📋 可用指令：\n"
            f"  /start         — 查看說明\n"
            f"  /status        — 查看模型狀態\n"
            f"  /clear         — 清除對話記憶\n"
            f"  /test_morning  — 測試早安推播\n"
            f"  /test_evening  — 測試晚安推播\n"
            f"  /restart       — 重啟 Agent\n\n"
            f"💬 直接傳訊息就可以開始使用！"
            f"🚨 緊急停止：/stop 或 Ctrl+Shift+F12"
        )
        try:
            await application.bot.send_message(
                chat_id=TELEGRAM_ALLOWED_USER_ID,
                text=startup_msg
            )
        except Exception as e:
            print(f"[Bot] 啟動通知發送失敗：{e}")

    async def on_shutdown(application):
        scheduler.shutdown()
        print("[Scheduler] 排程器已關閉")

    async def error_handler(update, context):
        import telegram.error as tg_err # type: ignore
        err = context.error
        if isinstance(err, tg_err.NetworkError):
            print(f"[Bot] 網路錯誤（自動重連中）：{err}")
            return  # 不處理，讓 library 自動重試
        print(f"[Bot] 未預期錯誤：{err}")

    app.add_error_handler(error_handler)
    app.post_init     = on_startup
    app.post_shutdown = on_shutdown

    print("[Telegram Bot] 已上線，等待訊息...")
    app.run_polling()
