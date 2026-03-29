# 🤖 Personal AI Agent

透過 Telegram 控制你的 Windows 電腦的個人 AI Agent。
支援本地（Ollama）與雲端（Groq / Gemini / Claude）模型自動切換，敏感操作全程本地執行保護隱私。

---

## ✨ 功能總覽

| 類別 | 功能 |
|---|---|
| 🔍 資訊查詢 | 網路搜尋、天氣預報、系統資訊、時間 |
| 📂 檔案操作 | 讀寫 `agent_files/` 資料夾 |
| 🖥 應用程式 | 模糊搜尋開啟程式、開啟網址、關閉、帶到最上層 |
| 🔊 系統控制 | 音量調整、靜音、截圖（沙盒環境）|
| ⌨️ 自動化 | 滑鼠、鍵盤輸入（沙盒環境限定）|
| 🌐 瀏覽器 | 用 Playwright 開啟網頁、點擊、填表單、截圖 |
| 📧 Gmail | 收信（自動過濾廣告）、讀信、寄信、回覆、標記、刪除 |
| 💬 Discord | 透過 Webhook 推播訊息到指定頻道 |
| 🧠 記憶系統 | 自動記住對話重要資訊，跨對話保留 |
| 📚 知識庫（RAG）| 匯入文件、自動研究主題、語意搜尋 |
| ⏰ 排程提醒 | 一次性提醒、每日/每週/每月循環提醒 |
| 📅 早晚推播 | 每天早上天氣+信件+行程，晚上回顧 |
| 📺 直播監控 | YouTube / Twitch 開播推播通知（Webhook + 輪詢雙保險）|
| 👤 個人化 | 自訂稱呼、城市、語氣，存本地不上傳 |
| 🔒 隱私保護 | 敏感指令自動走本地 Ollama，雲端不接觸個人資料 |
| 🛡 安全機制 | 緊急停止（/stop、Ctrl+Shift+F12）、任務管理 |

---

## 🗂 專案結構

```
ai_agent/
├── main.py                      # 入口（支援 bot / cli / webhook / all 模式）
├── config.py                    # 環境變數載入
├── webhook_server.py            # 直播監控 Webhook 伺服器
├── sandbox_setup.bat            # 沙盒自動安裝啟動腳本
├── sandbox.wsb                  # Windows Sandbox 設定檔
├── .env                         # API Keys（自己建立，不上傳）
├── .env.example                 # 環境變數範本
├── persona.example.json         # 個人化設定範本
├── requirements.txt             # 完整套件清單
├── requirements_sandbox.txt     # 沙盒套件清單（排除桌面控制）
│
├── core/
│   ├── agent.py                 # Agent 主循環（支援 auto 路由）
│   ├── router.py                # 自動選模型（敏感→本地，一般→雲端）
│   ├── persona.py               # 個人化設定
│   ├── memory.py                # 記憶系統（ChromaDB）
│   ├── rag.py                   # 知識庫（RAG）
│   ├── paths.py                 # 統一路徑管理
│   ├── logger.py                # logging 設定
│   ├── task_manager.py          # 背景任務管理
│   ├── emergency_stop.py        # 緊急停止系統
│   ├── dynamic_skill.py         # 動態腳本生成（沙盒限定）
│   ├── llm_groq.py              # Groq LLM
│   ├── llm_ollama.py            # Ollama 本地 LLM
│   ├── llm_gemini.py            # Google Gemini LLM
│   └── llm_claude.py            # Anthropic Claude LLM
│
├── tools/
│   ├── __init__.py              # 工具總入口 + 隱私過濾
│   ├── info.py                  # 時間、天氣、搜尋、檔案、記憶、RAG、提醒
│   ├── apps.py                  # 應用程式控制
│   ├── system.py                # 音量、截圖、滑鼠、鍵盤、Shell
│   ├── browser.py               # 瀏覽器控制（Playwright）
│   ├── gmail.py                 # Gmail 收發信
│   ├── youtube.py               # YouTube 頻道搜尋
│   ├── stream_monitor.py        # 直播監控清單管理
│   └── stream_check.py          # 直播狀態輪詢（備用）
│
├── channels/
│   ├── telegram_bot.py          # Telegram 介面
│   └── cli.py                   # 終端機測試介面
│
├── scheduler/
│   ├── heartbeat.py             # 早安/晚安排程推播
│   └── reminder.py              # 提醒系統（一次性 + 循環）
│
└── data/                        # 運行時 JSON 資料（不上傳 git）
    ├── persona.json
    ├── reminders.json
    ├── stream_monitor.json
    └── pending_streams.json
```

---

## 🚀 快速開始

### 1. 環境需求

- Windows 10/11 Pro（沙盒需要 Pro）
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
playwright install chromium
```

### 3. 取得 API Keys

| 服務 | 用途 | 申請 | 費用 |
|---|---|---|---|
| Groq | 雲端 AI（推薦）| [console.groq.com](https://console.groq.com) | 免費 |
| Gemini | 雲端 AI 模型（備用）| [aistudio.google.com](https://aistudio.google.com) | 免費（有限制）|
| Claude | 雲端 AI 模型（備用）| [console.anthropic.com](https://console.anthropic.com) | 付費 |
| Ollama | 本地 AI | [ollama.com](https://ollama.com) | 免費 |
| Telegram Bot | 訊息介面 | `@BotFather` | 免費 |
| YouTube Data v3 | 頻道搜尋 | [console.cloud.google.com](https://console.cloud.google.com) | 免費（有限額）|
| Discord Webhook | 推播通知 | 頻道設定 → 整合 → Webhook | 免費 |
| ngrok | Webhook 公開 URL | [ngrok.com](https://ngrok.com) | 免費 |

**Gmail API（選用）：**
1. 前往 [console.cloud.google.com](https://console.cloud.google.com) 建立專案
2. 啟用 Gmail API
3. 建立 OAuth 憑證（桌面應用程式），下載並改名為 `gmail_credentials.json`
4. 放到專案根目錄
### 4. 設定環境變數

```bash
copy .env.example .env
```

編輯 `.env` 填入對應的值。

### 5. 下載本地模型

```bash
ollama pull qwen2.5:latest
# 有 10GB+ VRAM 的話可以用更強的版本：
ollama pull qwen2.5:14b
```

### 6. 執行

```bash
# 一般模式（只跑 Telegram Bot）
python main.py

# 完整模式（Bot + Webhook Server，沙盒推薦）
python main.py all

# 終端機測試模式
python main.py cli
```

---

## 💬 使用範例

```
台北今天天氣如何？
幫我檢查有沒有新信件
幫我開啟 Spotify
音量調到 50
幫我截圖
搜尋最新的 AI 新聞

# 提醒
請在今天 22:30 提醒我要睡覺
每週日早上 9 點提醒我看週報
每月 1 號早上 10 點提醒我繳帳單
列出所有提醒

# 直播監控
追蹤 @hololive
追蹤 hololive
列出所有監控中的頻道

# Discord
傳訊息到 Discord：今天天氣很好

# 個人化
幫我更新設定：稱呼改成老闆
幫我更新設定：城市改成台北
查看目前的個人化設定
```

---

## ⌨️ Telegram 指令

| 指令 | 說明 |
|---|---|
| `/start` | 查看說明 |
| `/stop` | 🚨 緊急停止所有動作 |
| `/reset` | 恢復正常運作 |
| `/tasks` | 查看背景任務 |
| `/cancel [id]` | 取消指定任務 |
| `/status` | 查看模型狀態 |
| `/model` | 查看目前模型 |
| `/use_ollama` | 切換本地 Ollama |
| `/use_groq` | 切換 Groq |
| `/use_auto` | 自動路由模式 |
| `/clear` | 清除對話記憶 |
| `/restart` | 重啟 Agent |
| `/test_morning` | 測試早安推播 |
| `/test_evening` | 測試晚安推播 |

---

## 🔒 隱私保護

| 指令類型 | 使用模型 |
|---|---|
| 天氣、搜尋、時間 | Groq（雲端，快速）|
| Gmail、信件 | Ollama（本地）|
| 記憶、知識庫 | Ollama（本地）|
| 帳密、登入 | Ollama（本地）|

天氣 API 只傳送經緯度，DuckDuckGo 不追蹤用戶，Gmail 和記憶全程在本地處理。

---

## 🛡 安全機制

| 功能 | 說明 |
|---|---|
| 緊急停止 | `/stop`、`Ctrl+Shift+F12`、滑鼠移左上角 |
| 沙盒限定 | 滑鼠/鍵盤控制、動態腳本執行 |
| 隱私過濾 | 雲端模型自動移除敏感工具 |
| Shell 黑名單 | 危險指令自動拒絕 |

---

## 🖥 Windows Sandbox 模式

隔離環境執行，避免 Agent 失控影響主機。

```
雙擊 sandbox.wsb
```

沙盒記憶和設定透過共享資料夾存在主機，重開沙盒不會消失。

**主機需要先設定 Ollama 對外監聽：**
```powershell
[System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
# 重啟 Ollama 後生效
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

把 `.env` 和 `data/` 資料夾複製到 `dist/` 旁邊。

---

## 🛠 新增自訂工具

1. 在 `tools/` 新增函式
2. 在 `tools/__init__.py` 的 import、`TOOL_DEFINITIONS`、`TOOL_HANDLERS` 各加一筆
3. 如果是敏感工具，加進 `PRIVATE_TOOLS`

---

## 📋 .gitignore 重點

```gitignore
.env
gmail_credentials.json
gmail_token.json
data/
agent_files/
memory_db/
rag_db/
logs/
pip_cache/
venv/
__pycache__/
dist/
build/
```

---

## 📄 License

MIT
Claude
Gemini
