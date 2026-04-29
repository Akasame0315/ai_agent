"""
interface/telegram_bot.py — Telegram Bot 介面
路徑：interface/telegram_bot.py

修正：
  - run() 為 async，用 asyncio.Event 取代已移除的 updater.idle()
  - Ctrl+C / SIGTERM 透過 signal handler 設定 stop_event 觸發優雅關閉
"""
from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

from telegram import BotCommand, Message, Update
from telegram.constants import ChatAction
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

if TYPE_CHECKING:
    from config import Config
    from core.planner import Planner
    from services.llm_gateway import LLMGateway
    from services.task_manager import TaskManager

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


class TelegramBot:
    def __init__(
        self,
        cfg: "Config",
        planner: "Planner",
        task_manager: "TaskManager",
    ):
        self.cfg = cfg
        self.planner = planner
        self.task_manager = task_manager
        self._app: Application | None = None
        self._llm: "LLMGateway | None" = None
        self._allowed_ids: set[int] = set(cfg.telegram.allowed_user_ids)
        # 用來保持 Bot 運行的 Event，收到停止訊號時 set()
        self._stop_event = asyncio.Event()

    async def run(self, llm: "LLMGateway") -> None:
        """
        async 啟動 Telegram Bot，保持運行直到 Ctrl+C 或 SIGTERM。
        python-telegram-bot v21 已移除 Updater.idle()，
        改用 asyncio.Event.wait() 讓 coroutine 持續 await。
        """
        self._llm = llm
        token = self.cfg.telegram.bot_token

        self._app = Application.builder().token(token).build()
        self._register_handlers()

        # 註冊停止訊號：set stop_event → finally 區塊執行關閉流程
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._stop_event.set)
            except (NotImplementedError, OSError):
                # Windows 不支援 SIGTERM 的 add_signal_handler，略過
                pass

        await self._app.initialize()
        await self._post_init(self._app)
        await self._app.start()
        await self._app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

        logger.info("[TelegramBot] 已上線，等待訊息...（Ctrl+C 停止）")

        try:
            # 一直等到 stop_event 被 set（訊號或外部呼叫 self.stop()）
            await self._stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            logger.info("[TelegramBot] 正在關閉...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("[TelegramBot] 已關閉")

    def stop(self) -> None:
        """從外部觸發優雅停止"""
        self._stop_event.set()

    def _register_handlers(self):
        if self._app is None:
            raise RuntimeError("Telegram application 尚未建立")

        self._app.add_handler(CommandHandler("start",   self._cmd_start))
        self._app.add_handler(CommandHandler("help",    self._cmd_help))
        self._app.add_handler(CommandHandler("new",     self._cmd_new))
        self._app.add_handler(CommandHandler("stop",    self._cmd_stop))
        self._app.add_handler(CommandHandler("resume",  self._cmd_resume))
        self._app.add_handler(CommandHandler("status",  self._cmd_status))
        self._app.add_handler(CommandHandler("confirm", self._cmd_confirm))
        self._app.add_handler(CommandHandler("cancel",  self._cmd_cancel))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_error_handler(self._on_error)

    async def _post_init(self, app: Application) -> None:
        if self._llm is None:
            raise RuntimeError("LLM gateway 尚未指定")

        if hasattr(self._llm, "start"):
            await self._llm.start()

        await app.bot.set_my_commands([
            BotCommand("start",   "顯示啟動訊息"),
            BotCommand("help",    "顯示可用指令"),
            BotCommand("new",     "清除對話記錄"),
            BotCommand("stop",    "停止目前任務"),
            BotCommand("resume",  "恢復處理訊息"),
            BotCommand("status",  "查看目前狀態"),
            BotCommand("confirm", "確認待執行的操作"),
            BotCommand("cancel",  "取消待執行的操作"),
        ])
        await self._send_startup_messages(app)
        logger.info("[TelegramBot] 初始化完成")

    # ------------------------------------------------------------------
    # 啟動訊息
    # ------------------------------------------------------------------

    def _build_start_text(self) -> str:
        assistant_name = self.cfg.agent.assistant_name
        owner_name     = self.cfg.agent.owner_name
        return (
            f"你好，{owner_name}！\n"
            f"我是 {assistant_name}，已成功連上 Telegram。\n"
            "直接傳送訊息給我即可開始對話。\n"
            "輸入 /help 可以查看可用指令。"
        )

    async def _send_startup_messages(self, app: Application) -> None:
        if not self._allowed_ids:
            logger.info("[TelegramBot] 未設定 allowed_user_ids，跳過啟動訊息")
            return
        text = self._build_start_text()
        for user_id in sorted(self._allowed_ids):
            try:
                await app.bot.send_message(chat_id=user_id, text=text)
                logger.info(f"[TelegramBot] 已發送啟動訊息給 user_id={user_id}")
            except Forbidden:
                logger.warning(
                    f"[TelegramBot] 無法發送給 user_id={user_id}，"
                    "請先從 Telegram 傳訊息給 Bot"
                )
            except TelegramError as exc:
                logger.error(f"[TelegramBot] 發送啟動訊息失敗 user_id={user_id}: {exc}")

    # ------------------------------------------------------------------
    # 指令 handler
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            await update.message.reply_text(self._build_start_text())

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            await update.message.reply_text(
                "可用指令：\n"
                "/new     — 清除目前對話記錄\n"
                "/stop    — 停止目前執行中的任務\n"
                "/resume  — 恢復 agent 接收訊息\n"
                "/status  — 查看目前狀態\n"
                "/confirm — 確認待執行的操作\n"
                "/cancel  — 取消待執行的操作"
            )

    async def _cmd_new(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            user_id = update.effective_user.id
            self.planner.clear_context(user_id)
            await update.message.reply_text("✅ 已清除目前的對話記錄。")

    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            count = self.task_manager.emergency_stop()
            await update.message.reply_text(
                f"🚨 已停止 {count} 個進行中的任務。\n"
                "輸入 /resume 可恢復處理新訊息。"
            )

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            self.task_manager.resume()
            await update.message.reply_text("✅ Agent 已恢復，可繼續接收訊息。")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            stopped = self.task_manager.is_stopped
            active  = self.task_manager.active_count()
            names   = self.task_manager.active_names()
            status  = "🔴 已停止" if stopped else "🟢 運行中"

            llm_info = self.cfg.llm.provider
            if self.cfg.llm.provider == "auto":
                llm_info += f"（雲端：{self.cfg.llm.cloud_provider} / 本地：ollama）"

            lines = [
                f"狀態：{status}",
                f"LLM：{llm_info}",
                f"執行中任務：{active}",
            ]
            if names:
                lines.extend(f"  - {name}" for name in names)
            await update.message.reply_text("\n".join(lines))

    async def _cmd_confirm(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            user_id = update.effective_user.id
            self.task_manager.create_task(
                self._confirm_and_reply(update.message, user_id),
                name=f"confirm_{user_id}",
            )

    async def _cmd_cancel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return
        if update.message:
            user_id = update.effective_user.id
            reply = await self.planner.handle_cancel(user_id)
            await update.message.reply_text(reply)

    # ------------------------------------------------------------------
    # 一般訊息
    # ------------------------------------------------------------------

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None or not message.text:
            return

        if self.task_manager.is_stopped:
            await message.reply_text("🚨 Agent 目前已停止，請先輸入 /resume。")
            return

        user_id   = update.effective_user.id
        user_name = update.effective_user.first_name or str(user_id)
        text      = message.text.strip()
        if not text:
            return

        logger.info(f"[Bot] user={user_id} ({user_name}): {text[:120]}")

        # 發送「正在輸入中」動作
        await ctx.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )

        # 在 TaskManager 的背景任務中執行，不阻塞 handler
        self.task_manager.create_task(
            self._process_and_reply(message, user_id, text),
            name=f"msg_{user_id}_{message.message_id}",
        )

    # ------------------------------------------------------------------
    # 非同步工作
    # ------------------------------------------------------------------

    async def _process_and_reply(self, message: Message, user_id: int, text: str):
        try:
            reply = await self.planner.process(user_id, text)
            await self._send_long_message(message, reply)
        except Exception as exc:
            logger.error(f"[Bot] 處理訊息失敗：{exc}", exc_info=True)
            await message.reply_text(f"⚠️ 處理訊息時發生錯誤：{exc}")

    async def _confirm_and_reply(self, message: Message, user_id: int):
        try:
            reply = await self.planner.handle_confirm(user_id)
            await self._send_long_message(message, reply)
        except Exception as exc:
            logger.error(f"[Bot] /confirm 失敗：{exc}", exc_info=True)
            await message.reply_text(f"⚠️ 確認操作時發生錯誤：{exc}")

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def _check_allowed(self, update: Update) -> bool:
        """若 allowed_ids 為空則允許所有人；否則只允許清單內的 user"""
        if not self._allowed_ids:
            return True
        if update.effective_user is None:
            return False
        user_id = update.effective_user.id
        if user_id not in self._allowed_ids:
            logger.warning(f"[Bot] 拒絕未授權的 user_id={user_id}")
            return False
        return True

    async def _send_long_message(self, message: Message, text: str) -> None:
        """自動切割超過 4096 字元的訊息"""
        if len(text) <= MAX_MESSAGE_LENGTH:
            await message.reply_text(text)
            return

        chunks: list[str] = []
        current = ""
        for line in text.splitlines(keepends=True):
            if len(current) + len(line) > MAX_MESSAGE_LENGTH:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)

        for index, chunk in enumerate(chunks, start=1):
            suffix = f"\n\n({index}/{len(chunks)})" if len(chunks) > 1 else ""
            await message.reply_text(chunk + suffix)

    async def _on_error(self, update: object, ctx: ContextTypes.DEFAULT_TYPE):
        logger.error(f"[Bot] Telegram 錯誤：{ctx.error}", exc_info=ctx.error)
