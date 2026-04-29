"""
skills/base.py — Skill 抽象基底
路徑：skills/base.py

所有 skill 都必須繼承 Skill，實作以下兩個方法：
  - get_schemas()  → 回傳這個 skill 提供的工具 schema 清單
  - execute()      → 執行指定工具，回傳字串結果

SkillRegistry（core/skill_registry.py）負責自動探索並載入所有 skill。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Skill(ABC):
    """
    所有 Skill 的抽象基底類別。

    子類別範例：
        class WeatherSkill(Skill):
            def get_schemas(self) -> list[dict]:
                return [WEATHER_SCHEMA]

            async def execute(self, tool_name: str, **kwargs) -> str:
                if tool_name == "get_weather":
                    return await self._fetch_weather(kwargs["city"])
                raise ValueError(f"未知工具：{tool_name}")
    """

    # ── 子類別可覆寫的屬性 ────────────────────────────────────────────

    # True  → 執行前需要使用者 /confirm 確認
    # False → 直接執行（查詢類操作）
    requires_confirmation: bool = False

    # "public"     → 可走雲端 LLM（Groq）
    # "local_only" → 強制走本地 Ollama（含個資、帳密、信件等）
    privacy_level: str = "public"

    # ── 必須實作的方法 ────────────────────────────────────────────────

    @abstractmethod
    def get_schemas(self) -> list[dict]:
        """
        回傳這個 skill 提供的工具 schema 清單（OpenAI function calling 格式）。

        格式範例：
            [
                {
                    "name": "get_weather",
                    "description": "查詢指定城市的即時天氣",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "城市名稱"}
                        },
                        "required": ["city"]
                    }
                }
            ]
        """
        ...

    @abstractmethod
    async def execute(self, tool_name: str, **kwargs: Any) -> str:
        """
        執行指定工具，回傳文字結果（LLM 會看到這個結果）。

        Args:
            tool_name: 工具名稱（對應 get_schemas 裡的 name）
            **kwargs:  工具參數（由 LLM 提供，對應 parameters 定義）

        Returns:
            str: 工具執行結果，會加回對話 history 供 LLM 參考

        Raises:
            ValueError: tool_name 不屬於這個 skill
            Exception:  執行失敗（SkillRegistry 會 catch 並回傳錯誤訊息給 LLM）
        """
        ...

    # ── 可選覆寫的方法 ────────────────────────────────────────────────

    async def setup(self) -> None:
        """
        Skill 載入後的初始化，例如建立資料夾、檢查 API key。
        預設為空操作。SkillRegistry 在 discover() 後呼叫此方法。
        """

    def get_tool_names(self) -> list[str]:
        """回傳這個 skill 提供的所有工具名稱"""
        return [schema["name"] for schema in self.get_schemas()]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(tools={self.get_tool_names()})"
