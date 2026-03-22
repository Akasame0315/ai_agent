# 🤖 Personal AI Agent

透過 Telegram 控制你的 Windows 電腦的個人 AI Agent。
支援本地（Ollama）與雲端（Groq / Gemini / Claude）模型自動切換，敏感操作全程本地執行保護隱私。

---

## ✨ 功能總覽

| 類別 | 功能 |
|---|---|
| 🔍 資訊查詢 | 網路搜尋（DuckDuckGo）、天氣預報、系統資訊、時間 |
| 📂 檔案操作 | 讀寫 `agent_files/` 資料夾內的檔案 |
| 🖥 應用程式 | 模糊搜尋並開啟已安裝程式、開啟網址、關閉程式 |
| 🔊 系統控制 | 調整／靜音音量、截圖、滑鼠點擊、鍵盤輸入 |
| ⌨️ 自動化 | 滑鼠移動點擊、鍵盤輸入組合鍵、Shell 指令 |
| 🌐 瀏覽器控制 | 用 Playwright 開啟網頁、點擊、填表單、截圖 |
| 📧 Gmail | 收信（自動過濾廣告）、讀信、寄信、回覆、刪除 |
| 🧠 記憶系統 | 自動記住對話中的重要資訊，跨對話保留 |
| 📚 知識庫（RAG）| 匯入文件／文字，自動研究主題並存入知識庫 |
| 📅 排程推播 | 每天早上推播天氣＋信件摘要＋行程建議，晚上回顧 |
| 👤 個人化 | 自訂稱呼、城市、回覆風格，存在本地不上傳 |
| 🔒 隱私保護 | 敏感指令自動走本地 Ollama，雲端模型不接觸個人資料 |

---

## 🗂 專案結構

```
ai_agent/
├── main.py                      # 入口（cli / telegram 模式）
├── config.py                    # 環境變數載入
├── .env                         # API Keys（自己建立，不上傳）
├── .env.example                 # 環境變數範本
├── persona.example.json         # 個人化設定範本
├── requirements.txt
│
├── core/
│   ├── agent.py                 # Agent 主循環（支援 auto 路由）
│   ├── router.py                # 自動選模型（敏感→本地，一般→雲端）
│   ├── persona.py               # 個人化設定（稱呼、城市、風格）
│   ├── memory.py                # 記憶系統（ChromaDB 向量庫）
│   ├── rag.py                   # 知識庫（RAG，ChromaDB）
│   ├── llm_groq.py              # Groq LLM
│   ├── llm_ollama.py            # Ollama 本地 LLM
│   ├── llm_gemini.py            # Google Gemini LLM
│   └── llm_claude.py            # Anthropic Claude LLM
│
├── tools/
│   ├── __init__.py              # 工具總入口 + 隱私過濾
│   ├── info.py                  # 時間、天氣、搜尋、檔案、記憶、RAG、個人化
│   ├── apps.py                  # 應用程式控制
│   ├── system.py                # 音量、截圖、滑鼠、鍵盤、Shell
│   ├── browser.py               # 瀏覽器控制（Playwright）
│   └── gmail.py                 # Gmail 收發信
│
├── channels/
│   ├── telegram_bot.py          # Telegram 介面 + 排程啟動
│   └── cli.py                   # 終端機測試介面
│
└── scheduler/
    ├── __init__.py
    └── heartbeat.py             # 早安／晚安排程推播
```

---

## 🚀 快速開始

### 1. 環境需求

- Windows 10 / 11
- Python 3.11+
- Telegram 帳號
- [Ollama](https://ollama.com)（本地模型，選用）

### 2. 安裝

```bash
git clone https://github.com/你的帳號/ai_agent.git
cd ai_agent

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

# 安裝 Playwright 瀏覽器
playwright install chromium
```

### 3. 取得 API Keys

| 服務 | 用途 | 申請網址 | 費用 |
|---|---|---|---|
| Groq | 雲端 AI 模型（推薦）| [console.groq.com](https://console.groq.com) | 免費 |
| Gemini | 雲端 AI 模型（備用）| [aistudio.google.com](https://aistudio.google.com) | 免費（有限制）|
| Claude | 雲端 AI 模型（備用）| [console.anthropic.com](https://console.anthropic.com) | 付費 |
| Ollama | 本地 AI 模型 | [ollama.com](https://ollama.com) | 免費 |
| Telegram Bot | 訊息介面 | 在 Telegram 找 `@BotFather` | 免費 |

**取得 Telegram Bot Token：**
1. 在 Telegram 搜尋 `@BotFather` → 傳送 `/newbot`
2. 依指示設定名稱，複製取得的 Token

**取得你的 Telegram User ID：**
1. 在 Telegram 搜尋 `@userinfobot` → 傳送任意訊息
2. 複製回傳的數字 ID

**Gmail API（選用）：**
1. 前往 [console.cloud.google.com](https://console.cloud.google.com) 建立專案
2. 啟用 Gmail API
3. 建立 OAuth 憑證（桌面應用程式），下載並改名為 `gmail_credentials.json`
4. 放到專案根目錄

### 4. 設定環境變數

```bash
copy .env.example .env
```

編輯 `.env`：

```env
# auto = 自動根據指令選擇模型（推薦）
LLM_PROVIDER=auto

# auto 模式下非敏感指令使用的雲端模型
CLOUD_PROVIDER=groq

# API Keys
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx

# Ollama 本地設定
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:latest

# Telegram
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxxx
TELEGRAM_ALLOWED_USER_ID=123456789
```

### 5. 下載本地模型（選用）

```bash
ollama pull qwen2.5:latest   # 約 4.7GB，適合一般硬體
ollama pull qwen2.5:14b      # 約 9GB，需要 10GB+ VRAM，品質更好
```

### 6. 執行

```bash
# Telegram 模式（正式使用）
python main.py

# 終端機測試模式（不需要 Telegram）
python main.py cli
```

---

## 💬 使用範例

```
台北今天天氣如何？
搜尋最新的 AI 新聞
幫我開啟 Chrome
幫我開啟 Spotify
音量調到 50
靜音
幫我截圖
現在幾點？
查一下我電腦記憶體還剩多少
幫我建立一個 todo.txt，內容是買牛奶
幫我檢查有沒有新信件
幫我研究 Python 非同步程式設計
知識庫裡有哪些文件？
你記得我叫什麼嗎？
幫我更新設定：城市改成台北
```

**Telegram 指令：**

| 指令 | 說明 |
|---|---|
| `/start` | 啟動並查看說明 |
| `/clear` | 清除對話記憶 |
| `/status` | 查看目前模型狀態和 Ollama 是否在線 |
| `/test_morning` | 立即測試早安推播 |
| `/test_evening` | 立即測試晚安推播 |

---

## 🔄 模型切換與隱私保護

### Auto 模式（推薦）

```env
LLM_PROVIDER=auto
CLOUD_PROVIDER=groq
```

系統自動根據指令內容選擇模型：

| 指令類型 | 使用模型 | 原因 |
|---|---|---|
| 天氣、搜尋、時間 | Groq（雲端）| 不含個人資訊，求速度 |
| Gmail、信件 | Ollama（本地）| 含個人資訊，保護隱私 |
| 記憶、知識庫 | Ollama（本地）| 個人資料不離開電腦 |
| 帳密、登入 | Ollama（本地）| 高度敏感 |

### 固定模式

```env
LLM_PROVIDER=ollama    # 全部走本地（最安全）
LLM_PROVIDER=groq      # 全部走雲端（最快）
```

### 隱私說明

- 天氣 API（Open-Meteo）只接收經緯度，不含任何個人資訊
- DuckDuckGo 搜尋不追蹤用戶
- Gmail、記憶、知識庫全程在本地處理，不經過任何雲端 LLM

---

## 👤 個人化設定

```bash
copy persona.example.json persona.json
```

編輯 `persona.json` 或在 Telegram 直接下指令：

```
幫我更新設定：稱呼改成老闆
幫我更新設定：城市改成台北
幫我更新設定：風格改成簡短幽默
新增指示：每次回覆結尾都問我需不需要記錄
查看目前的個人化設定
```

---

## 📅 排程推播

每天自動推播，不需要手動詢問：

| 時間 | 內容 |
|---|---|
| 每天 10:00 | 天氣預報 ＋ Gmail 摘要 ＋ 今日行程建議 |
| 每天 22:00 | 今日回顧，詢問想記錄的事 |

---

## 🖥 開機自動啟動

建立 `start_agent.bat`：

```bat
@echo off
cd /d D:\ai_agent
call venv\Scripts\activate
start /min python main.py
```

在 PowerShell 加入開機啟動：

```powershell
$bat = "D:\ai_agent\start_agent.bat"
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("$startup\AI_Agent.lnk")
$shortcut.TargetPath = $bat
$shortcut.Save()
```

讓 Ollama 也開機自動啟動：

```powershell
$startup = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("$startup\Ollama.lnk")
$shortcut.TargetPath = "ollama"
$shortcut.Arguments = "serve"
$shortcut.Save()
```

---

## 📦 打包成 .exe

```bash
pip install pyinstaller

pyinstaller --onefile --noconsole --name "AI_Agent" ^
  --add-data "tools;tools" ^
  --add-data "channels;channels" ^
  --add-data "core;core" ^
  --add-data "scheduler;scheduler" ^
  main.py
```

打包完成後把 `.env` 和 `persona.json` 複製到 `dist/` 資料夾旁邊。

---

## 🛠 新增自訂工具

1. 在 `tools/` 下的任意檔案新增函式
2. 在 `tools/__init__.py` 的 import、`TOOL_DEFINITIONS`、`TOOL_HANDLERS` 各加一筆
3. 如果是敏感工具，加進 `PRIVATE_TOOLS` 集合

```python
# tools/my_tool.py
def my_custom_tool(param: str) -> str:
    return f"結果：{param}"
```

```python
# tools/__init__.py

# 1. import
from tools.my_tool import my_custom_tool

# 2. TOOL_DEFINITIONS 加入
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

# 3. TOOL_HANDLERS 加入
"my_custom_tool": my_custom_tool,
```

---

## ⚠️ 注意事項

- **安全性**：`.env`、`persona.json`、`gmail_credentials.json` 絕對不要上傳到 Git
- **白名單**：`TELEGRAM_ALLOWED_USER_ID` 只填你自己的 ID，防止他人控制你的電腦
- **FailSafe**：執行滑鼠操作時，將滑鼠快速移到**螢幕左上角**可緊急停止
- **Shell 指令**：危險指令（`format`、`rm -rf` 等）已被內建黑名單擋掉
- **Gmail 首次使用**：第一次呼叫 Gmail 工具時會開啟瀏覽器要求 Google 授權

---

## 📄 .gitignore 建議

```gitignore
.env
persona.json
gmail_credentials.json
gmail_token.json
memory_db/
rag_db/
agent_files/
__pycache__/
*.pyc
venv/
.venv/
dist/
build/
*.spec
```

---

## 📄 License

MIT
