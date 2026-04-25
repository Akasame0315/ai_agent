"""
core/planner.py
Planner — 接收使用者訊息，分析意圖，產生任務計畫
Phase 1：直接對話模式（無 skill routing），後續 Phase 加入任務分解
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from services.llm_gateway import LLMGateway, Message

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """單一使用者的對話上下文（存於記憶體，Phase 4 後接 ChromaDB）"""
    user_id: int
    history: list[Message] = field(default_factory=list)
    max_history: int = 20  # 最多保留幾輪

    def add(self, role: str, content: str):
        self.history.append(Message(role=role, content=content))
        # 超過上限時，保留最近 N 筆
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_messages(self) -> list[Message]:
        return list(self.history)


class Planner:
    """
    Phase 1：簡單直接對話。
    使用者訊息 → Planner → LLM → 回覆文字

    Phase 2+ 會在這裡加入：
      - 意圖分類（search / file / system / ...）
      - 任務分解為 Task list
      - 傳給 Router 路由到對應 Skill
    """

    def __init__(self, llm: LLMGateway, cfg: dict, debug: bool = False):
        self.llm = llm
        self.cfg = cfg
        self.debug = debug
        self._contexts: dict[int, ConversationContext] = {}

    def _get_context(self, user_id: int) -> ConversationContext:
        if user_id not in self._contexts:
            self._contexts[user_id] = ConversationContext(user_id=user_id)
        return self._contexts[user_id]

    def clear_context(self, user_id: int):
        """清除對話記憶（/new 指令用）"""
        self._contexts.pop(user_id, None)
        logger.info(f"已清除 user {user_id} 的對話記憶")

    async def process(self, user_id: int, user_message: str) -> str:
        """
        處理使用者輸入，回傳 agent 回覆字串。
        Phase 1 直接走 LLM chat，不經過 skill routing。
        """
        ctx = self._get_context(user_id)
        ctx.add("user", user_message)

        if self.debug:
            logger.info(
                "[DEBUG] history 長度：%d 條（含本次 user message）",
                len(ctx.history),
            )

        try:
            response = await self.llm.chat(
                messages=ctx.get_messages(),
                force_local=self._is_sensitive(user_message),
            )
            reply = response.content
            ctx.add("assistant", reply)
            logger.debug(
                f"[{response.provider}/{response.model}] "
                f"tokens: {response.prompt_tokens}+{response.completion_tokens}"
            )
            return reply

        except Exception as e:
            logger.error(f"Planner 處理失敗：{e}")
            return f"⚠️ 處理時發生錯誤：{e}"

    # ------------------------------------------------------------------ #
    #  隱私初步判斷（Phase 1 簡化版，Security 模組會更完整）               #
    # ------------------------------------------------------------------ #

    SENSITIVE_KEYWORDS = {
        "密碼", "password", "帳號", "帳戶", "身分證", "信用卡",
        "個人資料", "私鑰", "private key", "token", "secret",
    }

    def _is_sensitive(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in self.SENSITIVE_KEYWORDS)
