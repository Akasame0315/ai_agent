@echo off
:: 定義 Log 檔案路徑（存在你掛載的 D 槽資料夾中）
set LOG_FILE=C:\ai_agent\install_log.txt
echo [Setup] start install... > %LOG_FILE%

echo [Setup] start install python...
:: 安裝 Python（如果 Sandbox 沒有）
@REM winget install Python.Python.3.11 --silent --accept-source-agreements
C:\ai_agent\python-3.13.12-amd64.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

:: 等待 Python 安裝完成
timeout /t 10 /nobreak
set "PATH=%PATH%;C:\Program Files\Python313\;C:\Program Files\Python313\Scripts\"

::驗證 Python 是否真的裝好了 (如果失敗會跳出提示)
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [Error] Python installation failed or path not added, trying absolute path...
    set PYTHON_EXE="C:\Program Files\Python313\python.exe"
) else (
    set PYTHON_EXE=python
)

:: 進入專案資料夾
cd /d C:\ai_agent

:: 建立虛擬環境
echo [Setup] creating virtual environment...
%PYTHON_EXE% -m venv venv
call venv\Scripts\activate

set CONTAINER_MODE=1
set SANDBOX_MODE=1
set PIP_CACHE_DIR=C:\pip_cache

:: 自動抓取 Windows Sandbox 的網關 IP (主機 IP)
for /f "tokens=3" %%a in ('route print 0.0.0.0 ^| findstr 0.0.0.0') do (
    set HOST_IP=%%a
    goto :break
)
:break
set OLLAMA_BASE_URL=http://%HOST_IP%:11434

:: 安裝套件（排除桌面控制）
echo [Setup] install packages...
python -m pip install --upgrade pip --cache-dir C:\pip_cache
pip install -r requirements_sandbox.txt --cache-dir C:\pip_cache

:: 檢查上一行指令是否有錯
if %errorlevel% neq 0 (
    echo [Error] installation failed. Check %LOG_FILE% for details.
    pause
    exit /b %errorlevel%
)

:: 啟動 Agent
:: ── 啟動（all 模式：Bot + Webhook 在同一個程序）─────────────────
echo [Setup] start main.py... >> %LOG_FILE%
start "AI Agent" cmd /k "python main.py all"

echo [Setup] Agent started in sandbox mode. You can close this window now.
pause