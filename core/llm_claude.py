"""
Claude (Anthropic) 的 LLM 實作
"""
import anthropic
from config import ANTHROPIC_API_KEY
from tools import TOOL_DEFINITIONS, execute_tool

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """你是一個個人 AI Agent，可以幫使用者完成各種任務。
你有工具可以使用：查詢時間、讀寫本機檔案。
請用繁體中文回覆。回覆要簡潔清楚。"""

def run(conversation_history: list) -> tuple[str, list]:
    """執行一次 Claude ReAct 循環，最多 5 輪 tool call"""
    for _ in range(5):
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=conversation_history
        )

        conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        if response.stop_reason == "end_turn":
            texts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(texts) or "（無文字回覆）", conversation_history

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Claude] 呼叫工具：{block.name}，參數：{block.input}")
                    result = execute_tool(block.name, block.input)
                    print(f"[Claude] 工具結果：{result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            conversation_history.append({"role": "user", "content": tool_results})

    return "❌ 超過最大迴圈次數，請重試", conversation_history
