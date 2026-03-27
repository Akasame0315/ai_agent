"""
統一路徑管理
路徑：core/paths.py

所有 JSON 資料檔案集中在 data/ 資料夾。
其他模組都從這裡取得路徑，不要硬寫路徑字串。
"""
import os

# 專案根目錄
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 資料資料夾
DATA_DIR       = os.path.join(ROOT_DIR, "data")
AGENT_FILES_DIR = os.path.join(ROOT_DIR, "agent_files")
LOGS_DIR       = os.path.join(ROOT_DIR, "logs")

# 各 JSON 檔案路徑
PERSONA_FILE        = os.path.join(DATA_DIR, "persona.json")
REMINDER_FILE       = os.path.join(DATA_DIR, "reminders.json")
STREAM_MONITOR_FILE = os.path.join(DATA_DIR, "stream_monitor.json")
PENDING_STREAMS_FILE = os.path.join(DATA_DIR, "pending_streams.json")
SKILL_LOG_FILE      = os.path.join(DATA_DIR, "skill_log.json")

# Gmail token（敏感，放根目錄方便 .gitignore）
GMAIL_CREDENTIALS_FILE = os.path.join(ROOT_DIR, "gmail_credentials.json")
GMAIL_TOKEN_FILE       = os.path.join(ROOT_DIR, "gmail_token.json")


def ensure_dirs():
    """確保所有必要資料夾存在"""
    for d in [DATA_DIR, AGENT_FILES_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)
