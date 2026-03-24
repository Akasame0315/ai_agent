@echo off
echo [Setup] 開始安裝環境...

:: 安裝 Python（如果 Sandbox 沒有）
winget install Python.Python.3.11 --silent --accept-source-agreements

:: 等待 Python 安裝完成
timeout /t 30 /nobreak

:: 進入專案資料夾
cd /d C:\ai_agent

:: 建立虛擬環境
python -m venv venv
call venv\Scripts\activate

setx CONTAINER_MODE 1
setx SANDBOX_MODE 1
set PIP_CACHE_DIR=C:\pip_cache

:: 安裝套件（排除桌面控制）
pip install -r requirements_sandbox.txt

:: 啟動 Agent
start /min python main.py

echo [Setup] Agent 已在背景啟動
```