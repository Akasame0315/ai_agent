"""
core/planner.py
Planner — 對話管理 + Tool Call Loop
流程：
  使用者訊息
    → LLM（附帶 tool schemas）
    → 若有 tool_calls：執行技能 → 結果回送 LLM → 繼續
    → 若需要確認：暫存 pending_call，等待 /confirm 或 /cancel
    → 最終輸出文字回覆
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from services.llm_gateway import LLMGateway, Message, ToolCall

logger = logging.getLogger(__name__)

# 單次對話最多執行幾次 tool call（防止無限迴圈）
MAX_TOOL_ROUNDS = 5


# ======================================================================
# 對話上下文
# ======================================================================

@dataclass
class PendingConfirmation:
    """等待使用者確認的 tool call"""
    tool_call: ToolCall
    description: str   # 顯示給使用者的描述


@dataclass
class ConversationContext:
    """單一使用者的對話上下文"""
    user_id: int
    history: list[Message] = field(default_factory=list)
    max_history: int = 20
    pending: PendingConfirmation | None = None   # 等待確認的操作

    def add(self, role: str, content: str, **kwargs):
        self.history.append(Message(role=role, content=content, **kwargs))
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_messages(self) -> list[Message]:
        return list(self.history)


# ======================================================================
# Planner
# ======================================================================

class Planner:
    """
    Tool Call Loop：
    1. 使用者訊息 → LLM（帶 tool schemas）
    2. LLM 回傳 tool_calls → 檢查是否需要確認
       a. 需要確認 → 暫存 pending，回傳確認提示
       b. 不需要確認 → 直接執行
    3. 執行結果 → 加入 history 作為 tool message → 再次呼叫 LLM
    4. 最終 LLM 輸出純文字 → 回傳給使用者
    """

    def __init__(self, llm: LLMGateway, cfg: dict, debug: bool = False):
        self.llm = llm
        self.cfg = cfg
        self.debug = debug
        self._contexts: dict[int, ConversationContext] = {}
        # skill registry：name → skill instance（由外部注入）
        self._skills: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Skill 注入
    # ------------------------------------------------------------------

    def register_skills(self, skills: dict[str, Any]):
        """
        注入 skill instances，並將 TOOL_SCHEMA 註冊到 LLMGateway。
        skills 格式：{"weather": WeatherSkill(), "search": SearchSkill(), ...}
        """
        self._skills = skills
        schemas = []
        for skill in skills.values():
            module = type(skill).__module__
            try:
                import importlib
                mod = importlib.import_module(module)
                if hasattr(mod, "TOOL_SCHEMA"):
                    schemas.append(mod.TOOL_SCHEMA)
            except Exception as e:
                logger.warning("無法載入 %s 的 TOOL_SCHEMA: %s", module, e)

        self.llm.register_tools(schemas)
        logger.info(
            "已注入 %d 個 skill，%d 個 tool schema",
            len(skills), len(schemas),
        )

    # ------------------------------------------------------------------
    # 上下文管理
    # ------------------------------------------------------------------

    def _get_context(self, user_id: int) -> ConversationContext:
        if user_id not in self._contexts:
            self._contexts[user_id] = ConversationContext(user_id=user_id)
        return self._contexts[user_id]

    def clear_context(self, user_id: int):
        self._contexts.pop(user_id, None)
        logger.info("已清除 user %d 的對話記憶", user_id)

    # ------------------------------------------------------------------
    # 確認機制：/confirm / /cancel
    # ------------------------------------------------------------------

    async def handle_confirm(self, user_id: int) -> str:
        ctx = self._get_context(user_id)
        if not ctx.pending:
            return "目前沒有等待確認的操作。"
        tc = ctx.pending.tool_call
        ctx.pending = None
        return await self._run_tool_and_followup(ctx, tc)

    async def handle_cancel(self, user_id: int) -> str:
        ctx = self._get_context(user_id)
        if not ctx.pending:
            return "目前沒有等待確認的操作。"
        ctx.pending = None
        return "✅ 已取消操作。"

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def process(self, user_id: int, user_message: str) -> str:
        ctx = self._get_context(user_id)

        # 若有 pending confirmation，提醒使用者
        if ctx.pending:
            return (
                f"⚠️ 還有一個待確認的操作：{ctx.pending.description}\n"
                "請先回覆 /confirm 確認或 /cancel 取消。"
            )

        ctx.add("user", user_message)

        if self.debug:
            logger.info("[DEBUG] history 長度：%d 條", len(ctx.history))

        try:
            return await self._tool_call_loop(ctx)
        except Exception as e:
            logger.error("Planner 處理失敗：%s", e, exc_info=True)
            return f"⚠️ 處理時發生錯誤：{e}"

    # ------------------------------------------------------------------
    # Tool Call Loop
    # ------------------------------------------------------------------

    async def _tool_call_loop(self, ctx: ConversationContext) -> str:
        """
        持續呼叫 LLM 直到：
        - LLM 回傳純文字（無 tool call）
        - 遇到需要確認的操作（暫停等待）
        - 達到最大 tool call 次數
        """
        for round_num in range(MAX_TOOL_ROUNDS):
            response = await self.llm.chat(
                messages=ctx.get_messages(),
                force_local=self._is_sensitive_context(ctx),
            )

            logger.debug(
                "[%s/%s] tokens: %d+%d  tool_calls: %d",
                response.provider, response.model,
                response.prompt_tokens, response.completion_tokens,
                len(response.tool_calls),
            )

            # 無 tool call → 最終回覆
            if not response.has_tool_calls:
                reply = response.content
                ctx.add("assistant", reply)
                return reply

            # 有 tool call（目前取第一個，多 tool call 未來可擴充）
            tc = response.tool_calls[0]

            # 把 assistant 的 tool_calls 記入 history（Groq 格式要求）
            ctx.add(
                "assistant",
                response.content or "",
                tool_calls=[{
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }],
            )

            # 確認機制
            skill = self._skills.get(self._tool_name_to_skill(tc.name))
            if skill and getattr(skill, "requires_confirmation", False):
                desc = self._describe_tool_call(tc)
                ctx.pending = PendingConfirmation(tool_call=tc, description=desc)
                return (
                    f"⚠️ 即將執行：{desc}\n"
                    "確認請回覆 /confirm，取消請回覆 /cancel"
                )

            # 執行工具
            tool_result = await self._execute_tool(tc)

            # 把 tool result 加回 history
            ctx.add("tool", tool_result, tool_call_id=tc.id)

            logger.info("[Tool] %s → %s", tc.name, tool_result[:80])

        # 超過最大次數，要求 LLM 直接回覆
        logger.warning("達到最大 tool call 次數 (%d)，強制結束", MAX_TOOL_ROUNDS)
        response = await self.llm.chat(
            messages=ctx.get_messages(),
            force_local=self._is_sensitive_context(ctx),
            system_prompt=self.llm._build_system_prompt() + "\n請直接回覆，不要再呼叫工具。",
        )
        reply = response.content
        ctx.add("assistant", reply)
        return reply

    # ------------------------------------------------------------------
    # 確認後執行（/confirm 觸發）
    # ------------------------------------------------------------------

    async def _run_tool_and_followup(
        self, ctx: ConversationContext, tc: ToolCall
    ) -> str:
        tool_result = await self._execute_tool(tc)
        ctx.add("tool", tool_result, tool_call_id=tc.id)

        # 讓 LLM 根據結果產生最終回覆
        response = await self.llm.chat(
            messages=ctx.get_messages(),
            force_local=self._is_sensitive_context(ctx),
        )
        reply = response.content
        ctx.add("assistant", reply)
        return reply

    # ------------------------------------------------------------------
    # 工具執行
    # ------------------------------------------------------------------

    async def _execute_tool(self, tc: ToolCall) -> str:
        """呼叫對應 skill，回傳字串結果"""
        skill_name = self._tool_name_to_skill(tc.name)
        skill = self._skills.get(skill_name)

        if skill is None:
            logger.warning("找不到工具對應的 skill: %s", tc.name)
            return f"[錯誤] 找不到工具：{tc.name}"

        # tool name 對應 skill action
        action = self._tool_name_to_action(tc.name)
        try:
            result = await skill.execute(action=action, **tc.arguments)
            # skill 可能回傳字串或 dict
            if isinstance(result, str):
                return result
            return str(result)
        except Exception as e:
            logger.error("執行工具 %s 失敗: %s", tc.name, e, exc_info=True)
            return f"[錯誤] {tc.name} 執行失敗：{e}"

    # ------------------------------------------------------------------
    # 工具名稱映射
    # ------------------------------------------------------------------

    # tool name → (skill_name, action)
    _TOOL_MAP: dict[str, tuple[str, str]] = {
        "get_weather":    ("weather",     "get_weather"),
        "web_search":     ("search",      "search"),
        "get_system_info": ("system_info", "get_system_info"),
        "get_time":       ("system_info", "get_time"),
    }

    def _tool_name_to_skill(self, tool_name: str) -> str:
        return self._TOOL_MAP.get(tool_name, (tool_name, tool_name))[0]

    def _tool_name_to_action(self, tool_name: str) -> str:
        return self._TOOL_MAP.get(tool_name, (tool_name, tool_name))[1]

    def _describe_tool_call(self, tc: ToolCall) -> str:
        """產生人類可讀的操作描述，用於確認提示"""
        descriptions = {
            "write_file":  lambda a: f"寫入檔案 {a.get('path', '?')}",
            "delete_file": lambda a: f"刪除檔案 {a.get('path', '?')}",
            "set_volume":  lambda a: f"設定音量為 {a.get('level', '?')}%",
            "open_app":    lambda a: f"開啟應用程式 {a.get('name', '?')}",
        }
        desc_fn = descriptions.get(tc.name)
        if desc_fn:
            return desc_fn(tc.arguments)
        return f"{tc.name}（{tc.arguments}）"

    # ------------------------------------------------------------------
    # 隱私判斷
    # ------------------------------------------------------------------

    SENSITIVE_KEYWORDS = {
        "密碼", "password", "帳號", "帳戶", "身分證", "信用卡",
        "個人資料", "私鑰", "private key", "token", "secret",
    }

    def _is_sensitive_context(self, ctx: ConversationContext) -> bool:
        """若最新一條 user message 含敏感關鍵字，走本地 LLM"""
        for msg in reversed(ctx.history):
            if msg.role == "user":
                lower = msg.content.lower()
                return any(kw in lower for kw in self.SENSITIVE_KEYWORDS)
        return False
