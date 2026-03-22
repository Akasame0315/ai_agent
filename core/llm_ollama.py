"""
Ollama 本地 LLM 實作
Ollama 提供 OpenAI 相容 API，預設跑在 http://localhost:11434
支援 tool use 的模型：qwen2.5、llama3.1、mistral-nemo 等
"""
import json
import httpx # type: ignore
from config import OLLAMA_MODEL, OLLAMA_BASE_URL
from tools import TOOL_DEFINITIONS, execute_tool
from config import OLLAMA_MODEL

SYSTEM_PROMPT = f"""你是一個個人 AI Agent，運行在電腦上，可以幫使用者完成各種任務。
你使用的模型是：{OLLAMA_MODEL}
你有工具可以使用：查詢時間、讀寫檔案、網路搜尋、天氣查詢、開啟程式、控制音量、截圖、滑鼠鍵盤操作、執行指令。

【重要】遇到以下情況請主動使用工具：
- 問到時間、日期 → 用 get_current_time
- 問到天氣 → 用 get_weather
- 問到新聞、時事、你不確定的資訊 → 用 web_search
- 要開應用程式或網站 → 用 open_application
不要憑記憶回答可能過時的資訊，優先用工具查詢。

請用繁體中文回覆。回覆要簡潔清楚。"""


def _to_ollama_tools() -> list:
    """把 Anthropic 格式的 tool definitions 轉成 OpenAI/Ollama 格式"""
    tools = []
    for t in TOOL_DEFINITIONS:
        tools.append({
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"]
            }
        })
    return tools


def _to_ollama_messages(conversation_history: list) -> list:
    """把內部對話歷史轉成 OpenAI 格式"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for msg in conversation_history:
        role    = msg["role"]
        content = msg["content"]

        # 純文字
        if isinstance(content, str):
            messages.append({"role": role, "content": content})

        # assistant 訊息（可能含 tool_calls）
        elif isinstance(content, list) and role == "assistant":
            text_parts = []
            tool_calls = []

            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id":   block.get("id", "call_0"),
                            "type": "function",
                            "function": {
                                "name":      block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {}),
                                                        ensure_ascii=False)
                            }
                        })

            assistant_msg: dict = {
                "role":    "assistant",
                "content": " ".join(text_parts) or ""
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

        # tool_result（user role）
        elif isinstance(content, list) and role == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": block.get("tool_use_id", "call_0"),
                        "content":      block.get("content", "")
                    })

    return messages


def run(conversation_history: list) -> tuple[str, list]:
    """執行一次 Ollama ReAct 循環，最多 5 輪 tool call"""
    ollama_tools = _to_ollama_tools()
    url = f"{OLLAMA_BASE_URL}/v1/chat/completions"

    for _ in range(5):
        messages = _to_ollama_messages(conversation_history)

        payload = {
            "model":    OLLAMA_MODEL,
            "messages": messages,
            "tools":    ollama_tools,
            "stream":   False,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=120)  # 本地模型可能慢一點
            resp.raise_for_status()
        except httpx.ConnectError:
            return "❌ 無法連線到 Ollama，請確認 Ollama 有在執行（ollama serve）", conversation_history
        except Exception as e:
            return f"❌ Ollama 呼叫失敗：{e}", conversation_history

        data    = resp.json()
        choice  = data["choices"][0]
        message = choice["message"]

        # 存進歷史
        assistant_content = []
        if message.get("content"):
            assistant_content.append({
                "type": "text",
                "text": message["content"]
            })
        for tc in message.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}
            assistant_content.append({
                "type":  "tool_use",
                "id":    tc.get("id", "call_0"),
                "name":  tc["function"]["name"],
                "input": args
            })

        conversation_history.append({
            "role":    "assistant",
            "content": assistant_content
        })

        # 沒有 tool call → 回傳文字
        # ── Fallback：有些模型會把 tool call 輸出成純文字 JSON ──────
        raw_content = message.get("content") or ""
        if not message.get("tool_calls") and '{"name"' in raw_content:
            import re
            matches = re.findall(r'\{"name":\s*"(\w+)",\s*"arguments":\s*(\{.*?\})\}',
                                 raw_content, re.DOTALL)
            if matches:
                fake_tool_calls = []
                for name, args_str in matches:
                    try:
                        args = json.loads(args_str)
                    except Exception:
                        args = {}
                    fake_tool_calls.append({
                        "id": "call_fallback",
                        "function": {"name": name, "arguments": json.dumps(args)}
                    })
                message["tool_calls"] = fake_tool_calls
                print(f"[Ollama] Fallback 解析到 {len(fake_tool_calls)} 個工具呼叫")

        # 沒有 tool call（包含 fallback 也沒解析到）→ 直接回傳文字
        if not message.get("tool_calls"):
            return message.get("content") or "（無回覆）", conversation_history

        # 有 tool call → 執行工具
        tool_results = []
        for tc in message.get("tool_calls") or []:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except Exception:
                args = {}

            print(f"[Ollama] 呼叫工具：{name}，參數：{args}")
            result = execute_tool(name, args)
            print(f"[Ollama] 工具結果：{result}")

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tc.get("id", "call_0"),
                "content":     result
            })

        conversation_history.append({
            "role":    "user",
            "content": tool_results
        })

    return "❌ 超過最大迴圈次數，請重試", conversation_history
