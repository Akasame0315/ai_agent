"""
Agent 主入口
路徑：core/agent.py

支援 auto 模式：自動根據指令內容選擇本地或雲端模型。
本地模型（Ollama）：啟用記憶、RAG、所有敏感工具。
雲端模型：停用敏感工具，保護隱私。
"""
from config import LLM_PROVIDER


def _resolve_provider(message: str) -> str:
    """決定實際要用哪個 provider"""
    if LLM_PROVIDER == "auto":
        from core.router import route
        return route(message)
    return LLM_PROVIDER


def run_agent(user_message: str, conversation_history: list) -> tuple[str, list]:

    # ── 決定使用哪個模型 ──────────────────────────────────────────────
    provider   = _resolve_provider(user_message)
    is_local   = (provider == "ollama")

    context_parts  = []
    memory_enabled = False

    # ── 記憶 + RAG：只在本地模型下運作 ──────────────────────────────
    if is_local:
        try:
            from core.memory import search_memory, save_memory
            memory_ctx = search_memory(user_message)
            if memory_ctx:
                context_parts.append(memory_ctx)
            memory_enabled = True
        except ImportError:
            pass

        try:
            from core.rag import search_knowledge
            rag_ctx = search_knowledge(user_message)
            if rag_ctx:
                context_parts.append(rag_ctx)
        except ImportError:
            pass

    # 把記憶和知識庫內容附加在使用者訊息前
    enriched_message = user_message
    if context_parts:
        context_block    = "\n\n".join(context_parts)
        enriched_message = f"{context_block}\n\n用戶訊息：{user_message}"

    conversation_history.append({
        "role":    "user",
        "content": enriched_message
    })

    # ── 選擇 LLM 並執行 ───────────────────────────────────────────────
    try:
        if provider == "claude":
            from core.llm_claude import run
        elif provider == "gemini":
            from core.llm_gemini import run
        elif provider == "groq":
            from core.llm_groq import run
        elif provider == "ollama":
            from core.llm_ollama import run
        else:
            return (
                f"❌ 未知的 provider：{provider}",
                conversation_history
            )

        # 把實際使用的 provider 傳給 LLM 模組（用於工具過濾）
        import os
        os.environ["_ACTIVE_PROVIDER"] = provider

        reply, conversation_history = run(conversation_history)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ LLM 呼叫失敗（{provider}）：{e}", conversation_history

    # ── 儲存記憶（只有本地模型）──────────────────────────────────────
    if is_local and memory_enabled:
        try:
            save_memory(user_message, reply)
        except Exception as e:
            print(f"[Memory] 儲存失敗：{e}")

    return reply, conversation_history
