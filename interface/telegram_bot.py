from __future__ import annotations

import logging
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
    from core.planner import Planner
    from services.llm_gateway import LLMGateway
    from services.task_manager import TaskManager

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096


class TelegramBot:
    def __init__(
        self,
        cfg: dict,
        planner: "Planner",
        task_manager: "TaskManager",
    ):
        self.cfg = cfg
        self.planner = planner
        self.task_manager = task_manager
        self._app: Application | None = None
        self._llm: LLMGateway | None = None
        self._allowed_ids: set[int] = set(cfg["telegram"].get("allowed_user_ids", []))

    def run(self, llm: "LLMGateway"):
        self._llm = llm
        token = self.cfg["telegram"]["token"]

        async def _post_shutdown(_: Application):
            logger.info("Shutting down telegram bot...")
            self.task_manager.emergency_stop()
            await llm.stop()
            logger.info("Telegram bot stopped.")

        self._app = (
            Application.builder()
            .token(token)
            .post_init(self._post_init)
            .post_shutdown(_post_shutdown)
            .build()
        )
        self._register_handlers()

        logger.info("Telegram bot starting polling.")
        self._app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

    def _register_handlers(self):
        if self._app is None:
            raise RuntimeError("Telegram application has not been created.")

        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("new", self._cmd_new))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(CommandHandler("resume", self._cmd_resume))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )
        self._app.add_error_handler(self._on_error)

    async def _post_init(self, app: Application):
        if self._llm is None:
            raise RuntimeError("LLM gateway was not assigned before startup.")

        await self._llm.start()
        await app.bot.set_my_commands(
            [
                BotCommand("start", "顯示啟動訊息"),
                BotCommand("help", "顯示可用指令"),
                BotCommand("new", "清除對話記錄"),
                BotCommand("stop", "停止目前任務"),
                BotCommand("resume", "恢復處理訊息"),
                BotCommand("status", "查看目前狀態"),
            ]
        )
        await self._send_startup_messages(app)
        logger.info("Telegram bot initialized successfully.")

    def _get_identity(self) -> tuple[str, str]:
        agent_cfg = self.cfg.get("agent", {})
        assistant_name = agent_cfg.get("assistant_name") or "助理"
        owner_name = agent_cfg.get("owner_name") or agent_cfg.get("name") or "你"
        return assistant_name, owner_name

    def _build_start_text(self) -> str:
        assistant_name, owner_name = self._get_identity()
        return (
            f"你好，{owner_name}。\n"
            f"我是 {assistant_name}，已成功連上 Telegram。\n"
            "直接傳送訊息給我即可開始對話。\n"
            "輸入 /help 可以查看可用指令。"
        )

    async def _send_startup_messages(self, app: Application):
        if not self._allowed_ids:
            logger.info("No allowed_user_ids configured; skipped startup message.")
            return

        text = self._build_start_text()
        for user_id in sorted(self._allowed_ids):
            try:
                await app.bot.send_message(chat_id=user_id, text=text)
                logger.info("Startup message sent to user_id=%s", user_id)
            except Forbidden:
                logger.warning(
                    "Cannot send startup message to user_id=%s. Start the bot from Telegram first.",
                    user_id,
                )
            except TelegramError as exc:
                logger.error(
                    "Failed to send startup message to user_id=%s: %s",
                    user_id,
                    exc,
                )

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None:
            return
        await message.reply_text(self._build_start_text())

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None:
            return
        await message.reply_text(
            "可用指令：\n"
            "/new - 清除目前對話記錄\n"
            "/stop - 停止目前執行中的任務\n"
            "/resume - 恢復 agent 接收訊息\n"
            "/status - 查看目前狀態"
        )

    async def _cmd_new(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None:
            return

        user_id = update.effective_user.id
        self.planner.clear_context(user_id)
        await message.reply_text("已清除目前的對話記錄。")

    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None:
            return

        count = self.task_manager.emergency_stop()
        await message.reply_text(
            f"已停止 {count} 個進行中的任務。\n"
            "輸入 /resume 可恢復處理新訊息。"
        )

    async def _cmd_resume(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None:
            return

        self.task_manager.resume()
        await message.reply_text("Agent 已恢復，可繼續接收訊息。")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None:
            return

        stopped = self.task_manager.is_stopped
        active = self.task_manager.active_count()
        names = self.task_manager.active_names()
        status = "已停止" if stopped else "運行中"
        details = [f"狀態：{status}", f"執行中任務數：{active}"]
        if names:
            details.extend(f"- {name}" for name in names)

        await message.reply_text("\n".join(details))

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self._check_allowed(update):
            return

        message = update.message
        if message is None or not message.text:
            return

        if self.task_manager.is_stopped:
            await message.reply_text("Agent 目前已停止，請先輸入 /resume。")
            return

        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or str(user_id)
        text = message.text.strip()
        if not text:
            return

        logger.info("[%s] %s: %s", user_id, user_name, text[:120])
        await ctx.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING,
        )
        self.task_manager.create_task(
            self._process_and_reply(message, user_id, text),
            name=f"msg_{user_id}_{message.message_id}",
        )

    async def _process_and_reply(self, message: Message, user_id: int, text: str):
        try:
            reply = await self.planner.process(user_id, text)
            await self._send_long_message(message, reply)
        except Exception as exc:
            logger.error("Failed to process telegram message: %s", exc, exc_info=True)
            await message.reply_text(f"處理訊息時發生錯誤：{exc}")

    def _check_allowed(self, update: Update) -> bool:
        if not self._allowed_ids:
            return True

        user_id = update.effective_user.id
        if user_id not in self._allowed_ids:
            logger.warning("Rejected message from unauthorized user_id=%s", user_id)
            return False
        return True

    async def _send_long_message(self, message: Message, text: str):
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
        logger.error("Telegram error: %s", ctx.error, exc_info=ctx.error)
