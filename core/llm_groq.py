"""
Groq LLM 實作
路徑：core/llm_groq.py
"""
import json
from groq import Groq # type: ignore
from config import GROQ_API_KEY
from tools import _get_safe_tools, execute_tool

def _safe_parse_args(arguments: str) -> dict:
    """安全解析 tool call arguments，處理格式錯誤"""
    if not arguments:
        return {}
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        # 嘗試修復常見格式錯誤
        import re
        # 移除多餘的 }{ 或 {}{
        fixed = re.sub(r'\}\s*\{', ',', arguments)
        # 移除尾部多餘的 }
        fixed = re.sub(r'\}\}+$', '}', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            print(f"[Groq] ⚠️ 無法解析 tool arguments：{arguments[:100]}")
            return {}


client = Groq(api_key=GROQ_API_KEY)

MODELS = [
    "moonshotai/kimi-k2-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.2-70b-versatile",
    "llama-3.3-8b-versatile",
    "mixtral-8x7b-32768",
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
            args   = _safe_parse_args(tc.function.arguments)
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
            err_str = str(e)
            if "503" in err_str or "over capacity" in err_str:
                print(f"[Groq] {model} 過載，切換備用模型...")
                continue
            if "429" in err_str:
                try:
                    wait = int(re.search(r'\d+', err_str).group()) + 5
                except Exception:
                    wait = 60
                print(f"[Groq] Rate limit，等待 {wait} 秒...")
                time.sleep(wait)
                continue
            if "tool_use_failed" in err_str or "Failed to call a function" in err_str:
                # Tool call 格式錯誤，換下一個模型重試
                print(f"[Groq] {model} tool call 格式錯誤，切換備用模型...")
                continue
            raise e
    # 所有模型都 400，可能是 history 格式問題，清除 tool 記錄後用第一個模型重試
    print("[Groq] 嘗試清除對話歷史後重試...")
    clean_history = [
        msg for msg in conversation_history
        if isinstance(msg.get("content"), str)  # 只保留純文字訊息
    ]
    try:
        return _run_with_model(MODELS[0], groq_tools, clean_history)
    except Exception:
        return "❌ LLM 呼叫失敗，請重新傳送指令", conversation_history
