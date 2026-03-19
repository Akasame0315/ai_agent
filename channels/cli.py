"""
本機終端機測試版（不需要 Telegram）
直接在命令列跟 Agent 對話，測試 Tool Use 流程
"""
from core.agent import run_agent

def main():
    print("=== Agent CLI 測試模式 ===")
    print("輸入 'exit' 離開\n")

    conversation_history = []

    while True:
        try:
            user_input = input("你：").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再見！")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("再見！")
            break

        print("Agent 思考中...\n")
        reply, conversation_history = run_agent(user_input, conversation_history)
        print(f"Agent：{reply}\n")

if __name__ == "__main__":
    main()