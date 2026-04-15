@echo off
echo 正在重啟 Agent...
taskkill /f /im python.exe 2>nul
timeout /t 2 /nobreak >nul
cd /d D:\ai_agent
call venv\Scripts\activate
start /min python main.py all
echo Agent 已重啟