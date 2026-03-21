"""
Agent 主入口
路徑：core/agent.py

根據 LLM_PROVIDER 自動選擇對應的 LLM 模組
整合記憶系統（Memory）和知識庫（RAG）
"""
from config import LLM_PROVIDER


def run_agent(user_message: str, conversation_history: list) -> tuple[str, list]:

    # ── 同時搜尋記憶和知識庫 ─────────────────────────────────────────
    context_parts = []

    try:
        from core.memory import search_memory, save_memory
        memory_ctx = search_memory(user_message)
        if memory_ctx:
            context_parts.append(memory_ctx)
        MEMORY_ENABLED = True
    except ImportError:
        MEMORY_ENABLED = False

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

    # ── 選擇 LLM ─────────────────────────────────────────────────────
    if LLM_PROVIDER == "claude":
        from core.llm_claude import run
    elif LLM_PROVIDER == "gemini":
        from core.llm_gemini import run
    elif LLM_PROVIDER == "groq":
        from core.llm_groq import run
    elif LLM_PROVIDER == "ollama":
        from core.llm_ollama import run
    else:
        return (
            f"❌ 未知的 LLM_PROVIDER：{LLM_PROVIDER}\n"
            f"請填：claude / gemini / groq / ollama",
            conversation_history
        )

    try:
        reply, conversation_history = run(conversation_history)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ LLM 呼叫失敗：{e}", conversation_history

    # ── 對話結束後儲存記憶 ────────────────────────────────────────────
    if MEMORY_ENABLED:
        try:
            save_memory(user_message, reply)
        except Exception as e:
            print(f"[Memory] 儲存記憶時發生錯誤：{e}")

    return reply, conversation_history
