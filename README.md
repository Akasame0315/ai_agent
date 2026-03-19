# 🤖 Personal AI Agent

透過 Telegram 控制你的 Windows 電腦的個人 AI Agent。
發一則訊息，就能查天氣、搜尋網路、開啟程式、調整音量、執行指令。

---

## ✨ 功能

| 類別 | 功能 |
|---|---|
| 🔍 資訊查詢 | 網路搜尋（DuckDuckGo）、天氣預報、系統資訊、時間 |
| 📂 檔案操作 | 讀寫 `agent_files/` 資料夾內的檔案 |
| 🖥 應用程式 | 模糊搜尋並開啟已安裝程式、開啟網址、關閉程式 |
| 🔊 系統控制 | 調整 / 靜音音量、截圖 |
| ⌨️ 自動化 | 滑鼠點擊移動、鍵盤輸入、組合鍵、Shell 指令 |

---

## 🗂 專案結構

```
ai_agent/
├── main.py                  # 入口（cli / telegram 模式）
├── config.py                # 環境變數載入
├── .env                     # API Keys（自己建立，不上傳）
├── .env.example             # 環境變數範本
├── requirements.txt
│
├── core/
│   ├── agent.py             # LLM 分派器
│   ├── llm_groq.py          # Groq (Llama / Kimi K2)
│   ├── llm_gemini.py        # Google Gemini
│   └── llm_claude.py        # Anthropic Claude
│
├── tools/
│   ├── __init__.py          # 工具總入口（定義 + 呼叫）
│   ├── apps.py              # 應用程式控制
│   ├── system.py            # 系統控制（音量、截圖、滑鼠）
│   └── info.py              # 資訊查詢（天氣、搜尋、檔案）
│
└── channels/
    ├── telegram_bot.py      # Telegram 介面
    └── cli.py               # 終端機測試介面
```

---

## 🚀 快速開始

### 1. 環境需求

- Windows 10 / 11
- Python 3.11+
- Telegram 帳號

### 2. 安裝

```bash
git clone https://github.com/你的帳號/ai_agent.git
cd ai_agent

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

### 3. 取得 API Keys

| 服務 | 用途 | 申請網址 | 費用 |
|---|---|---|---|
| Groq | AI 模型（推薦） | [console.groq.com](https://console.groq.com) | 免費 |
| Gemini | AI 模型（備用） | [aistudio.google.com](https://aistudio.google.com) | 免費（有限制）|
| Claude | AI 模型（備用） | [console.anthropic.com](https://console.anthropic.com) | 付費 |
| Telegram Bot | 訊息介面 | 在 Telegram 找 `@BotFather` | 免費 |

**取得 Telegram Bot Token：**
1. 在 Telegram 搜尋 `@BotFather`
2. 傳送 `/newbot`，依指示設定名稱
3. 複製取得的 Token

**取得你的 Telegram User ID：**
1. 在 Telegram 搜尋 `@userinfobot`
2. 傳送任意訊息，複製回傳的數字 ID

### 4. 設定環境變數

```bash
copy .env.example .env
```

編輯 `.env`，填入你的 API Keys：

```env
LLM_PROVIDER=groq

ANTHROPIC_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx

TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxxx
TELEGRAM_ALLOWED_USER_ID=123456789
```

### 5. 執行

```bash
# Telegram 模式（正式使用）
python main.py

# 終端機測試模式（不需要 Telegram）
python main.py cli
```

---

## 💬 使用範例

在 Telegram 對 Bot 傳送以下訊息：

```
台北今天天氣如何？
搜尋最新的 AI 新聞
幫我開啟 Chrome
幫我開啟 spotify
音量調到 50
靜音
幫我截圖
現在幾點？
查一下我電腦記憶體還剩多少
幫我建立一個 todo.txt，內容是買牛奶
```

**Telegram 指令：**
- `/start` — 啟動並查看說明
- `/clear` — 清除對話記憶

---

## 🔄 切換 AI 模型

只需修改 `.env` 的一行：

```env
LLM_PROVIDER=groq    # 使用 Groq（預設，免費額度最高）
LLM_PROVIDER=gemini  # 使用 Google Gemini
LLM_PROVIDER=claude  # 使用 Anthropic Claude
```

---

## 🖥 開機自動啟動

建立 `start_agent.bat`：

```bat
@echo off
cd /d D:\ai_agent
call venv\Scripts\activate
start /min python main.py
```

在 PowerShell 執行以下指令加入開機啟動：

```powershell
$bat = "D:\ai_agent\start_agent.bat"
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("$startup\AI_Agent.lnk")
$shortcut.TargetPath = $bat
$shortcut.Save()
```

重開機後 Agent 會自動在背景執行，打開 Telegram 就能使用。

---

## 📦 打包成 .exe

```bash
pip install pyinstaller

pyinstaller --onefile --noconsole --name "AI_Agent" ^
  --add-data "tools;tools" ^
  --add-data "channels;channels" ^
  --add-data "core;core" ^
  main.py
```

打包完成後：

```
dist/
├── AI_Agent.exe    # 雙擊執行
└── .env            # 從專案根目錄複製過來
```

---

## ⚠️ 注意事項

- **安全性**：`.env` 包含敏感 API Keys，絕對不要上傳到 Git
- **白名單**：`TELEGRAM_ALLOWED_USER_ID` 只填你自己的 ID，防止他人控制你的電腦
- **FailSafe**：執行滑鼠操作時，將滑鼠快速移到**螢幕左上角**可緊急停止
- **Shell 指令**：危險指令（如 `format`、`rm -rf`）已被內建黑名單擋掉

---

## 🛠 新增自訂工具

在 `tools/` 下任意檔案新增函式，然後在 `tools/__init__.py` 的 `TOOL_DEFINITIONS` 和 `TOOL_HANDLERS` 各加一筆，Agent 就會自動學會使用新工具。

```python
# tools/my_tool.py
def my_custom_tool(param: str) -> str:
    # 你的邏輯
    return f"結果：{param}"
```

```python
# tools/__init__.py

# TOOL_DEFINITIONS 加入：
{
    "name": "my_custom_tool",
    "description": "描述這個工具做什麼",
    "input_schema": {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "參數說明"}
        },
        "required": ["param"]
    }
},

# TOOL_HANDLERS 加入：
"my_custom_tool": my_custom_tool,
```

---

## 📄 License

MIT
