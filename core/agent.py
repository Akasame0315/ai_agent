"""
Agent 主入口：根據 LLM_PROVIDER 自動選擇對應的 LLM 模組
支援：claude / gemini / groq
"""
from config import LLM_PROVIDER

def run_agent(user_message: str, conversation_history: list) -> tuple[str, list]:
    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    if LLM_PROVIDER == "claude":
        from core.llm_claude import run
    elif LLM_PROVIDER == "gemini":
        from core.llm_gemini import run
    elif LLM_PROVIDER == "groq":
        from core.llm_groq import run
    else:
        return (
            f"❌ 未知的 LLM_PROVIDER：{LLM_PROVIDER}（請填 claude / gemini / groq）",
            conversation_history
        )

    try:
        return run(conversation_history)
    except Exception as e:
        return f"❌ LLM 呼叫失敗：{e}", conversation_history
