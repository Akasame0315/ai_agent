"""
動態 Skill 系統（安全模式）
路徑：core/dynamic_skill.py

Agent 可以生成腳本，但需要人工確認後才能執行。
腳本存在 agent_files/skills/ 資料夾，你說「執行腳本 xxx」才會跑。
"""
import os
import json
import datetime
import subprocess

SKILLS_DIR    = os.path.join("agent_files", "skills")
from core.paths import SKILL_LOG_FILE as SKILL_LOG

# 安全黑名單：這些操作即使人工確認也不允許
FORBIDDEN_PATTERNS = [
    "os.remove", "shutil.rmtree", "format(",
    "subprocess.call", "eval(", "exec(",
    "__import__", "open('/", "open(\"/"
]


def generate_skill(name: str, description: str, code: str) -> str:
    """
    Agent 生成一個新的腳本，存檔後等待人工確認。
    不會自動執行。
    """
    os.makedirs(SKILLS_DIR, exist_ok=True)

    # 安全檢查
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in code:
            return (
                f"⛔ 腳本包含危險操作「{pattern}」，已拒絕生成。\n"
                f"如果這是必要操作，請手動寫入程式碼。"
            )

    # 儲存腳本
    filename = f"{name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    filepath = os.path.join(SKILLS_DIR, filename)

    full_code = f'''"""
自動生成的 Skill
名稱：{name}
描述：{description}
生成時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

{code}
'''

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(full_code)

    return (
        f"✅ 腳本已生成並存檔：\n"
        f"📄 檔案：{filepath}\n"
        f"📝 描述：{description}\n\n"
        f"⚠️ 請檢查腳本內容確認安全後，\n"
        f"說「執行腳本 {filename}」才會實際執行。"
    )


def execute_skill(filename: str) -> str:
    """
    執行已存檔的腳本（需要人工指定檔名）。
    僅限沙盒環境，主機環境直接阻擋。
    """
    import os as _os
    is_sandbox = (
        _os.environ.get("SANDBOX_MODE", "0") == "1" or
        _os.environ.get("CONTAINER_MODE", "0") == "1"
    )
    if not is_sandbox:
        return (
            "⛔ 動態腳本執行僅限沙盒環境。\n\n"
            "在主機上執行任意腳本有安全風險，已自動阻擋。\n"
            "如需執行自動化任務，請使用內建工具或手動執行腳本。"
        )

    filepath = os.path.join(SKILLS_DIR, filename)

    if not os.path.exists(filepath):
        # 列出可用的腳本
        skills = list_skills()
        return f"❌ 找不到腳本：{filename}\n\n{skills}"

    # 再次安全檢查
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()

    for pattern in FORBIDDEN_PATTERNS:
        if pattern in code:
            return f"⛔ 腳本包含危險操作「{pattern}」，執行已拒絕。"

    try:
        result = subprocess.run(
            ["python", filepath],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace"
        )
        output = result.stdout.strip() or result.stderr.strip() or "（無輸出）"
        if len(output) > 1000:
            output = output[:1000] + "\n...（輸出過長，已截斷）"

        # 記錄執行歷史
        _log_execution(filename, output, result.returncode == 0)

        status = "✅ 執行成功" if result.returncode == 0 else "⚠️ 執行完成（有錯誤）"
        return f"{status}\n\n輸出：\n{output}"

    except subprocess.TimeoutExpired:
        return "⏱ 腳本執行超時（30秒）"
    except Exception as e:
        return f"❌ 執行失敗：{e}"


def list_skills() -> str:
    """列出所有已生成的腳本"""
    os.makedirs(SKILLS_DIR, exist_ok=True)
    files = [f for f in os.listdir(SKILLS_DIR) if f.endswith(".py")]

    if not files:
        return "📂 目前沒有任何生成的腳本"

    lines = [f"📂 可用腳本（共 {len(files)} 個）：\n"]
    for f in sorted(files, reverse=True)[:10]:
        lines.append(f"  • {f}")
    return "\n".join(lines)


def _log_execution(filename: str, output: str, success: bool):
    logs = []
    if os.path.exists(SKILL_LOG):
        with open(SKILL_LOG, "r", encoding="utf-8") as f:
            logs = json.load(f)
    logs.append({
        "time":     datetime.datetime.now().isoformat(),
        "file":     filename,
        "success":  success,
        "output":   output[:200]
    })
    logs = logs[-50:]   # 只保留最近 50 筆
    with open(SKILL_LOG, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)
