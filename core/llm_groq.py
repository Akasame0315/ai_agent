"""
Groq LLM 實作
路徑：core/llm_groq.py
"""
import json
from groq import Groq # type: ignore
from config import GROQ_API_KEY
from tools import _get_safe_tools, execute_tool

client = Groq(api_key=GROQ_API_KEY)

MODELS = [
    "moonshotai/kimi-k2-instruct",
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
]

_BASE_PROMPT = """你是一個個人 AI Agent，運行在 Windows 電腦上，可以幫使用者完成各種任務。
你有工具可以使用：查詢時間、讀寫檔案、網路搜尋、天氣查詢、開啟程式、控制音量、截圖、執行指令。"""


def _get_system_prompt() -> str:
    try:
        from core.persona import build_system_prompt
        return build_system_prompt(_BASE_PROMPT)
    except Exception:
        return _BASE_PROMPT


def _to_groq_tools() -> list:
    tools = []
    for t in _get_safe_tools():
        tools.append({
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"]
            }
        })
    return tools


def _to_groq_messages(conversation_history: list) -> list:
    messages = [{"role": "system", "content": _get_system_prompt()}]
    for msg in conversation_history:
        role    = msg["role"]
        content = msg["content"]
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
        elif isinstance(content, list) and role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", "call_0"),
                            "type": "function",
                            "function": {
                                "name":      block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {}))
                            }
                        })
            assistant_msg: dict = {
                "role":    "assistant",
                "content": " ".join(text_parts) or None
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)
        elif isinstance(content, list) and role == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content":      block.get("content", "")
                    })
    return messages


def _run_with_model(model: str, groq_tools: list, conversation_history: list) -> tuple[str, list]:
    print(f"[Groq] 使用模型：{model}")
    for _ in range(5):
        messages = _to_groq_messages(conversation_history)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            max_tokens=1024,
        )
        choice  = response.choices[0]
        message = choice.message

        assistant_content = []
        if message.content:
            assistant_content.append({"type": "text", "text": message.content})
        if message.tool_calls:
            for tc in message.tool_calls:
                assistant_content.append({
                    "type":  "tool_use",
                    "id":    tc.id,
                    "name":  tc.function.name,
                    "input": json.loads(tc.function.arguments)
                })

        conversation_history.append({
            "role":    "assistant",
            "content": assistant_content
        })

        if not message.tool_calls:
            return message.content or "（無回覆）", conversation_history

        tool_results = []
        for tc in message.tool_calls:
            name   = tc.function.name
            args   = json.loads(tc.function.arguments)
            print(f"[Groq] 呼叫工具：{name}，參數：{args}")
            result = execute_tool(name, args)
            print(f"[Groq] 工具結果：{result}")
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,
                "content":     result
            })

        conversation_history.append({
            "role":    "user",
            "content": tool_results
        })

    return "❌ 超過最大迴圈次數，請重試", conversation_history


def run(conversation_history: list) -> tuple[str, list]:
    import re, time
    groq_tools = _to_groq_tools()
    for model in MODELS:
        try:
            return _run_with_model(model, groq_tools, conversation_history)
        except Exception as e:
            if "503" in str(e) or "over capacity" in str(e):
                print(f"[Groq] {model} 過載，切換備用模型...")
                continue
            if "429" in str(e):
                try:
                    wait = int(re.search(r'\d+', str(e)).group()) + 5
                except Exception:
                    wait = 60
                print(f"[Groq] Rate limit，等待 {wait} 秒...")
                time.sleep(wait)
                continue
            raise e
    return "❌ 所有模型目前都過載，請稍後再試", conversation_history
