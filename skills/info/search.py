"""
Search Skill - 網路搜尋
Provider 架構：DuckDuckGo（預設，免費）| Serper.dev（擴充）
切換方式：settings.yaml search.provider = "duckduckgo" | "serper"
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from skills.base import Skill

logger = logging.getLogger(__name__)

# Tool call schema，供 LLMGateway 註冊用
TOOL_SCHEMA = {
    "name": "web_search",
    "description": "搜尋網路上的即時資訊、新聞、知識。當需要查詢近期事件或不確定的資訊時使用。",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜尋關鍵字或問題",
            },
            "max_results": {
                "type": "string",
                "description": "最多回傳幾筆結果（預設 5）",
                "default": "5",
            },
        },
        "required": ["query"],
    },
}


# ======================================================================
# Provider 抽象層
# ======================================================================

class SearchProvider(ABC):
    """搜尋 provider 基底類別，所有 provider 必須實作 search()"""

    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[dict]:
        """
        回傳結果列表，每筆格式：
        {"title": str, "url": str, "snippet": str}
        """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider 識別名稱"""


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo 搜尋（免費，無需 API key）"""

    provider_name = "duckduckgo"

    async def search(self, query: str, max_results: int) -> list[dict]:
        try:
            from duckduckgo_search import AsyncDDGS
        except ImportError:
            raise RuntimeError(
                "請安裝 duckduckgo-search：pip install duckduckgo-search"
            )

        logger.info("[DDG] 搜尋: %s", query)
        results = []
        async with AsyncDDGS() as ddgs:
            async for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results


class SerperProvider(SearchProvider):
    """Serper.dev 搜尋（需要 API key，結果品質較好）"""

    provider_name = "serper"
    _API_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Serper 需要 api_key，請在 settings.yaml 設定 search.serper_api_key")
        self.api_key = api_key

    async def search(self, query: str, max_results: int) -> list[dict]:
        logger.info("[Serper] 搜尋: %s", query)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                self._API_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max_results},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("organic", [])[:max_results]:
            results.append({
                "title":   item.get("title", ""),
                "url":     item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results


# ======================================================================
# Provider Factory
# ======================================================================

def build_provider(config: dict) -> SearchProvider:
    """
    根據 settings.yaml 的 search 區塊建立 provider。
    config 預期為 cfg["search"]。
    """
    provider_name = config.get("provider", "duckduckgo").lower()

    if provider_name == "serper":
        api_key = config.get("serper_api_key", "")
        return SerperProvider(api_key=api_key)

    # 預設 / 未知 provider 都走 DuckDuckGo
    if provider_name != "duckduckgo":
        logger.warning("未知搜尋 provider '%s'，使用 duckduckgo", provider_name)
    return DuckDuckGoProvider()


# ======================================================================
# SearchSkill
# ======================================================================

class SearchSkill(Skill):
    """網路搜尋技能"""

    name = "search"
    description = "搜尋網路資訊"
    requires_confirmation = False

    def __init__(self, config: dict[str, Any] = None):
        super().__init__(config)
        cfg = config or {}
        self.max_results: int = self._normalize_max_results(cfg.get("max_results", 5))
        self._provider: SearchProvider = build_provider(cfg)
        logger.info("搜尋 provider: %s", self._provider.provider_name)

    # ------------------------------------------------------------------
    # Skill 介面
    # ------------------------------------------------------------------

    async def execute(self, action: str, **kwargs) -> Any:
        if action == "search":
            return await self.search(
                query=kwargs.get("query", ""),
                max_results=self._normalize_max_results(
                    kwargs.get("max_results", self.max_results)
                ),
            )
        return {"error": f"未知動作: {action}"}

    def get_available_actions(self) -> list[str]:
        return ["search"]

    # ------------------------------------------------------------------
    # 核心搜尋
    # ------------------------------------------------------------------

    async def search(self, query: str, max_results: int | None = None) -> str:
        """執行搜尋，回傳格式化字串"""
        if not query:
            return "❌ 請提供搜尋關鍵字"

        n = self._normalize_max_results(max_results or self.max_results)
        logger.info("搜尋: %s（最多 %d 筆）", query, n)

        try:
            results = await self._provider.search(query, n)
        except RuntimeError as e:
            # import error 等明確問題
            return f"❌ {e}"
        except Exception as e:
            logger.error("搜尋失敗: %s", e)
            return f"❌ 搜尋失敗：{e}"

        if not results:
            return f"🔍 找不到「{query}」的相關結果"

        return self._format(query, results)

    def _normalize_max_results(self, value: Any) -> int:
        """Normalize LLM-provided max_results and clamp to a safe range."""
        if isinstance(value, str):
            value = value.strip()
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = 5
        return max(1, min(parsed, 10))

    # ------------------------------------------------------------------
    # 格式化
    # ------------------------------------------------------------------

    def _format(self, query: str, results: list[dict]) -> str:
        lines = [f"🔍 「{query}」的搜尋結果：", ""]
        for i, r in enumerate(results, 1):
            title   = r.get("title", "（無標題）")
            url     = r.get("url", "")
            snippet = r.get("snippet", "").strip()
            lines.append(f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   🔗 {url}")
            lines.append("")
        return "\n".join(lines).rstrip()
