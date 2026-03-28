"""
Ollama 本地 LLM 實作
路徑：core/llm_ollama.py
"""
import json
import httpx # type: ignore
from config import OLLAMA_MODEL, OLLAMA_BASE_URL
from tools import _get_safe_tools, execute_tool

_BASE_PROMPT = """你是一個個人 AI Agent，運行在電腦上，可以幫使用者完成各種任務。
你有工具可以使用：查詢時間、讀寫檔案、網路搜尋、天氣查詢、開啟程式、控制音量、截圖、收發信件、記憶管理。
遇到需要查詢的資訊請主動使用工具，不要憑記憶回答可能過時的資訊。"""


def _get_system_prompt() -> str:
    try:
        from core.persona import build_system_prompt
        return build_system_prompt(_BASE_PROMPT)
    except Exception:
        return _BASE_PROMPT + f"\n你使用的模型是：{OLLAMA_MODEL}"


def _to_ollama_tools() -> list:
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


def _to_ollama_messages(conversation_history: list) -> list:
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
                            "id":   block.get("id", "call_0"),
                            "type": "function",
                            "function": {
                                "name":      block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)
                            }
                        })
            assistant_msg: dict = {
                "role":    "assistant",
                "content": " ".join(text_parts) or ""
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)
        elif isinstance(content, list) and role == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": block.get("tool_use_id", "call_0"),
                        "content":      block.get("content", "")
                    })
    return messages

def _try_start_ollama() -> bool:
    """嘗試啟動 Ollama 並預載模型，回傳是否成功"""
    import subprocess
    import time

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        # 第一階段：等 Ollama 服務起來（最多 15 秒）
        print("[Ollama] 等待服務啟動...")
        for i in range(15):
            time.sleep(1)
            try:
                r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
                if r.status_code == 200:
                    print(f"[Ollama] 服務已啟動（{i+1} 秒）")
                    break
            except Exception:
                continue
        else:
            print("[Ollama] 服務啟動超時")
            return False

        # 第二階段：預載模型（用 /api/generate 發一個空請求）
        print(f"[Ollama] 預載模型 {OLLAMA_MODEL}...")
        try:
            httpx.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": "", "stream": False},
                timeout=60  # 第一次載入模型可能需要較長時間
            )
            print("[Ollama] 模型已載入")
            return True
        except Exception as e:
            print(f"[Ollama] 模型預載失敗：{e}")
            return False

    except Exception as e:
        print(f"[Ollama] 自動啟動失敗：{e}")
        return False

def run(conversation_history: list) -> tuple[str, list]:
    print(f"[Ollama] BASE_URL={OLLAMA_BASE_URL}, MODEL={OLLAMA_MODEL}")
    ollama_tools = _to_ollama_tools()
    url = f"{OLLAMA_BASE_URL}/v1/chat/completions"
    print(f"[Ollama] 準備呼叫：{url}，模型：{OLLAMA_MODEL}")  # 加這行

    for _ in range(5):
        messages = _to_ollama_messages(conversation_history)
        payload  = {
            "model":    OLLAMA_MODEL,
            "messages": messages,
            "tools":    ollama_tools,
            "stream":   False,
        }
        try:
            resp = httpx.post(url, json=payload, timeout=300)
            resp.raise_for_status()
        except httpx.ConnectError:
            # 嘗試自動啟動 Ollama
            print("[Ollama] 連線失敗，嘗試自動啟動...")
            started = _try_start_ollama()
            if not started:
                return "❌ 無法連線到 Ollama，請手動啟動", conversation_history
            # 等待啟動完成後重試
            try:
                resp = httpx.post(url, json=payload, timeout=300)
                resp.raise_for_status()
            except Exception as e2:
                return f"❌ Ollama 重啟後仍然失敗：{e2}", conversation_history
        except Exception as e:
            return f"❌ Ollama 呼叫失敗：{e}", conversation_history

        data    = resp.json()
        choice  = data["choices"][0]
        message = choice["message"]

        assistant_content = []
        if message.get("content"):
            assistant_content.append({"type": "text", "text": message["content"]})
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

        # Fallback：模型把 tool call 輸出成純文字
        raw_content = message.get("content") or ""
        if not message.get("tool_calls") and '{"name"' in raw_content:
            import re
            matches = re.findall(
                r'\{"name":\s*"(\w+)",\s*"arguments":\s*(\{.*?\})\}',
                raw_content, re.DOTALL
            )
            if matches:
                fake_calls = []
                for name, args_str in matches:
                    try:
                        args = json.loads(args_str)
                    except Exception:
                        args = {}
                    fake_calls.append({
                        "id": "call_fallback",
                        "function": {"name": name, "arguments": json.dumps(args)}
                    })
                message["tool_calls"] = fake_calls

        if not message.get("tool_calls"):
            return message.get("content") or "（無回覆）", conversation_history

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
