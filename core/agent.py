"""
Agent 主入口
路徑：core/agent.py

改進：
1. LLM 呼叫移到背景 thread，不阻塞 Telegram event loop
2. 智慧路由：記憶儲存永遠在本地，查詢可以走雲端
"""
import asyncio
import concurrent.futures
from config import LLM_PROVIDER

# 背景 thread pool（處理同步 LLM 呼叫）
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _resolve_provider(message: str) -> tuple[str, bool]:
    """決定使用哪個 provider 和是否本地存記憶"""
    if LLM_PROVIDER == "auto":
        from core.router import route
        result = route(message)
        # 確保回傳的是 tuple
        if isinstance(result, tuple) and len(result) == 2:
            return result
        # route 只回傳字串的話
        return result, (result == "ollama")
    return LLM_PROVIDER, (LLM_PROVIDER == "ollama")


def _run_llm(provider: str, conversation_history: list) -> tuple[str, list]:
    """同步執行 LLM，在背景 thread 裡跑"""
    import os

    # 防呆：確保 provider 是有效值
    valid_providers = {"claude", "gemini", "groq", "ollama"}
    if provider not in valid_providers:
        print(f"[Agent] ⚠️ 無效的 provider：{repr(provider)}，fallback 到 groq")
        provider = "groq"

    os.environ["_ACTIVE_PROVIDER"] = provider

    if provider == "claude":
        from core.llm_claude import run
    elif provider == "gemini":
        from core.llm_gemini import run
    elif provider == "groq":
        from core.llm_groq import run
    elif provider == "ollama":
        from core.llm_ollama import run

    return run(conversation_history)

def run_agent(user_message: str, conversation_history: list) -> tuple[str, list]:
    """同步版 run_agent（供 CLI 模式使用）"""
    provider, save_memory = _resolve_provider(user_message)
    is_local = (provider == "ollama")

    context_parts = []

    # 記憶 + RAG 搜尋（本地模型或需要記憶的指令）
    memory_fn = None
    if is_local or save_memory:
        try:
            from core.memory import search_memory, save_memory as _save
            ctx = search_memory(user_message)
            if ctx:
                context_parts.append(ctx)
            memory_fn = _save
        except ImportError:
            pass

    if is_local:
        try:
            from core.rag import search_knowledge
            ctx = search_knowledge(user_message)
            if ctx:
                context_parts.append(ctx)
        except ImportError:
            pass

    enriched = user_message
    if context_parts:
        enriched = "\n\n".join(context_parts) + f"\n\n用戶訊息：{user_message}"

    conversation_history.append({"role": "user", "content": enriched})

    try:
        reply, conversation_history = _run_llm(provider, conversation_history)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ LLM 呼叫失敗（{provider}）：{e}", conversation_history

    # 儲存記憶（本地執行，不需要 LLM）
    if memory_fn:
        try:
            memory_fn(user_message, reply)
        except Exception as e:
            print(f"[Memory] 儲存失敗：{e}")

    return reply, conversation_history


async def run_agent_async(
    user_message: str,
    conversation_history: list
) -> tuple[str, list]:
    """
    非同步版 run_agent（供 Telegram Bot 使用）
    LLM 呼叫在背景 thread 執行，不阻塞 event loop
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        run_agent,
        user_message,
        conversation_history
    )
