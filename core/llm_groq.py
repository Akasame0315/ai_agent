"""
Groq LLM 實作
使用 llama-3.3-70b 模型，免費方案額度充足
Tool Use 格式與 OpenAI 相容
"""
from groq import Groq
from config import GROQ_API_KEY
from tools import TOOL_DEFINITIONS, execute_tool
import json

client = Groq(api_key=GROQ_API_KEY)

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """你是一個個人 AI Agent，運行在 Windows 電腦上，可以幫使用者完成各種任務。
你有工具可以使用：查詢時間、讀寫檔案、網路搜尋、天氣查詢、開啟程式、控制音量、截圖、滑鼠鍵盤操作、執行指令。
請用繁體中文回覆。回覆要簡潔清楚。"""


def _to_groq_tools() -> list:
    """把 Anthropic 格式的 tool definitions 轉成 OpenAI/Groq 格式"""
    tools = []
    for t in TOOL_DEFINITIONS:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"]
            }
        })
    return tools


def _to_groq_messages(conversation_history: list) -> list:
    """把內部對話歷史轉成 Groq 格式"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in conversation_history:
        role    = msg["role"]
        content = msg["content"]

        # 純文字訊息
        if isinstance(content, str):
            messages.append({"role": role, "content": content})

        # assistant 訊息（可能含 tool_calls）
        elif isinstance(content, list) and role == "assistant":
            text_parts  = []
            tool_calls  = []

            for block in content:
                # Anthropic SDK 物件格式（從 Claude 歷史帶過來的）
                if hasattr(block, "type"):
                    if block.type == "text" and block.text:
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_calls.append({
                            "id":       block.id,
                            "type":     "function",
                            "function": {
                                "name":      block.name,
                                "arguments": json.dumps(block.input)
                            }
                        })
                # dict 格式（從 Groq 歷史帶過來的）
                elif isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id":       block.get("id", ""),
                            "type":     "function",
                            "function": {
                                "name":      block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {}))
                            }
                        })

            assistant_msg = {"role": "assistant", "content": " ".join(text_parts) or None}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

        # tool_result 訊息（user role，list of tool results）
        elif isinstance(content, list) and role == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content":      block.get("content", "")
                    })

    return messages


def run(conversation_history: list) -> tuple[str, list]:
    """執行一次 Groq ReAct 循環，最多 5 輪 tool call"""
    groq_tools = _to_groq_tools()

    for _ in range(5):
        messages = _to_groq_messages(conversation_history)

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            max_tokens=1024,
        )

        choice  = response.choices[0]
        message = choice.message

        # 把回應存進歷史（用統一的 dict 格式）
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

        # 沒有 tool call → 直接回傳文字
        if not message.tool_calls:
            return message.content or "（無回覆）", conversation_history

        # 有 tool call → 執行工具
        tool_results = []
        for tc in message.tool_calls:
            name  = tc.function.name
            args  = json.loads(tc.function.arguments)
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
