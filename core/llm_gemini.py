"""
Gemini (Google) 的 LLM 實作

Gemini 的 Tool Use 格式和 Claude 不同，這裡做了轉換：
- Claude 用 "tool_use" / "tool_result" 格式
- Gemini 用 "function_call" / "function_response" 格式

Tool definitions 也從 Anthropic JSON Schema 格式轉成 Gemini 格式。
"""
import json
import httpx
from config import GEMINI_API_KEY
from tools import TOOL_DEFINITIONS, execute_tool
import time

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.0-flash:generateContent"
)

SYSTEM_INSTRUCTION = """你是一個個人 AI Agent，運行在 Windows 電腦上，可以幫使用者完成各種任務。

你有以下工具可以使用：查詢時間、讀寫本機檔案、網路搜尋、天氣查詢、開啟應用程式、控制滑鼠鍵盤、執行 shell 指令。

【重要】run_shell 工具可以執行 PowerShell 指令來控制系統，例如：
- 調整音量：powershell -c "(New-Object -ComObject WScript.Shell).SendKeys([char]174)"  # 音量減
- 靜音切換：powershell -c "$obj = New-Object -ComObject WScript.Shell; $obj.SendKeys([char]173)"
- 音量設定到指定值：powershell -c "$vol = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 50;$i++){$vol.SendKeys([char]174)}"
- 查系統資訊：powershell -c "Get-ComputerInfo | Select-Object WindowsProductName, TotalPhysicalMemory"
- 列出視窗：powershell -c "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name, MainWindowTitle"
- 關閉程式：powershell -c "Stop-Process -Name 'notepad' -Force"

當使用者說「調整音量」、「靜音」、「關掉某程式」等系統操作，優先考慮用 run_shell 搭配 PowerShell 指令完成。
請用繁體中文回覆。回覆要簡潔清楚。"""


# ── 把 Anthropic 格式的 tool definitions 轉成 Gemini 格式 ──────────────
def _to_gemini_tools() -> list:
    declarations = []
    for t in TOOL_DEFINITIONS:
        schema = t["input_schema"].copy()
        schema.pop("required", None)   # Gemini 不需要 required 欄位
        declarations.append({
            "name": t["name"],
            "description": t["description"],
            "parameters": schema
        })
    return [{"function_declarations": declarations}]


# ── 把我們內部的對話歷史格式轉成 Gemini contents 格式 ─────────────────
def _to_gemini_contents(conversation_history: list) -> list:
    contents = []
    for msg in conversation_history:
        role = "user" if msg["role"] == "user" else "model"
        content = msg["content"]

        # 純文字訊息
        if isinstance(content, str):
            contents.append({
                "role": role,
                "parts": [{"text": content}]
            })

        # Claude 格式的 assistant 訊息（含 tool_use blocks）
        elif isinstance(content, list):
            parts = []
            for block in content:
                # anthropic SDK 物件
                if hasattr(block, "type"):
                    if block.type == "text" and block.text:
                        parts.append({"text": block.text})
                    elif block.type == "tool_use":
                        parts.append({
                            "function_call": {
                                "name": block.name,
                                "args": block.input
                            }
                        })
                # tool_result（dict 格式）
                elif isinstance(block, dict) and block.get("type") == "tool_result":
                    parts.append({
                        "function_response": {
                            "name": _find_tool_name(block["tool_use_id"], contents),
                            "response": {"result": block["content"]}
                        }
                    })
            if parts:
                contents.append({"role": role, "parts": parts})

    return contents


def _find_tool_name(tool_use_id: str, contents: list) -> str:
    """從已有的 contents 裡找到對應 tool_use_id 的工具名稱"""
    for c in reversed(contents):
        for p in c.get("parts", []):
            if "function_call" in p:
                return p["function_call"]["name"]
    return "unknown_tool"


# ── 主函式：執行一次 Gemini ReAct 循環 ────────────────────────────────
def run(conversation_history: list) -> tuple[str, list]:
    """執行一次 Gemini ReAct 循環，最多 5 輪 tool call"""

    gemini_tools = _to_gemini_tools()

    for _ in range(5):
        time.sleep(2) # <--- 加入這行，避免 429 錯誤
        contents = _to_gemini_contents(conversation_history)

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": contents,
            "tools": gemini_tools
        }

        # 測試用：印出送給 Google 的內容，看哪裡格式怪怪的
        # print(json.dumps(payload, indent=2, ensure_ascii=False))
        for attempt in range(3):
            resp = httpx.post(
                GEMINI_API_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=30
            )
            print(f"[Gemini] HTTP {resp.status_code}")

            if resp.status_code == 429:
                # 從錯誤訊息裡抓建議等待秒數
                try:
                    retry_delay = resp.json()["error"]["details"][-1].get("retryDelay", "60s")
                    wait = int(re.search(r'\d+', retry_delay).group()) + 5
                except Exception:
                    wait = 60
                print(f"[Gemini] Rate limit，等待 {wait} 秒後重試...")
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                print(f"[Gemini] 錯誤：{resp.status_code} - {resp.text}")
                return f"❌ API 錯誤 {resp.status_code}：{resp.text[:200]}", conversation_history

            resp.raise_for_status()
            break
        else:
            return "❌ Gemini rate limit，請稍後再試", conversation_history
        
        data = resp.json()

        candidate = data["candidates"][0]
        parts = candidate["content"]["parts"]

        # 把這次回應存進歷史（用簡單 dict 格式）
        conversation_history.append({
            "role": "assistant",
            "content": _parts_to_internal(parts)
        })

        # 有 function_call → 執行工具
        function_calls = [p for p in parts if "functionCall" in p]
        if function_calls:
            tool_results = []
            for p in function_calls:
                fc = p["functionCall"]
                name = fc["name"]
                args = fc.get("args", {})
                print(f"[Gemini] 呼叫工具：{name}，參數：{args}")
                result = execute_tool(name, args)
                print(f"[Gemini] 工具結果：{result}")

                # Gemini 的 function_response 要放在 user turn
                tool_results.append({
                    "type": "tool_result",
                    # 用工具名稱當 id（Gemini 沒有 tool_use_id 概念）
                    "tool_use_id": name,
                    "content": result
                })

            conversation_history.append({
                "role": "user",
                "content": tool_results
            })
            continue  # 繼續下一輪

        # 沒有 function_call → 取文字回覆
        texts = [p["text"] for p in parts if "text" in p]
        final_text = "\n".join(texts).strip() or "（無文字回覆）"
        return final_text, conversation_history

    return "❌ 超過最大迴圈次數，請重試", conversation_history


def _parts_to_internal(parts: list) -> list:
    """把 Gemini parts 轉成我們內部統一的格式（方便後續 history 處理）"""
    result = []
    for p in parts:
        if "text" in p:
            result.append({"type": "text", "text": p["text"]})
        elif "functionCall" in p:
            result.append({
                "type": "function_call",
                "name": p["functionCall"]["name"],
                "args": p["functionCall"].get("args", {})
            })
    return result
