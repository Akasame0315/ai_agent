# Claude Agent v2 — 專案快速上手文件

> 給新對話的 Claude 閱讀，快速理解專案架構與當前狀態，減少重複說明。

---

## 專案定位

以 **Telegram Bot** 為入口的個人 AI 助理框架。  
使用者透過 Telegram 下指令，Agent 透過 **LLM Tool Call** 決定呼叫哪個技能、執行後將結果回送 LLM、最終輸出自然語言回覆。  
設計參考 OpenClaw / Hermes Agent 的架構概念，溝通層完全走 LLM（不使用硬編碼 intent mapping）。

---

## 技術棧

| 層級 | 技術 |
|------|------|
| 語言 | Python 3.11+ |
| Telegram | python-telegram-bot v21+ |
| LLM | Groq API（雲端）/ Ollama（本地） |
| 搜尋 | DuckDuckGo（預設，無需 API key） |
| 天氣 | Open-Meteo（免費，無需 API key） |
| 向量記憶 | ChromaDB（Phase 4） |
| 關聯式儲存 | SQLite（Phase 4） |
| 瀏覽器自動化 | Playwright（Phase 6） |
| 外部整合 | Gmail OAuth2（Phase 5） |
| 開發環境 | VS Code |

---

## 目錄結構

```
.
├── main.py                    # 入口，asyncio.run，支援 --debug / --cli
├── config.py                  # 環境變數載入（.env → dataclass Config 單例）
├── .env                       # API Keys（不 commit）
├── .env.example               # .env 範本
├── claude.md                  # 本文件
│
├── interface/
│   └── telegram_bot.py        # Telegram Bot（async run），含所有指令 handler
│
├── core/
│   ├── planner.py             # Tool Call Loop（最多 5 輪），確認機制，對話上下文
│   ├── router.py              # 敏感指令路由：偵測關鍵字 → 強制走 Ollama
│   ├── security.py            # 危險 shell 指令黑名單、路徑穿越檢查
│   └── emergency_stop.py      # 緊急停止旗標（threading.Event）
│   └── skill_registry.py      # Auto-Discovery 插件系統
│
├── services/
│   ├── llm_gateway.py         # 統一 LLM 呼叫：Groq / Ollama，格式轉換，retry
│   └── task_manager.py        # asyncio 任務追蹤、緊急停止
│
├── skills/
│   ├── base.py                # Skill 抽象基底（含 requires_confirmation 旗標）
│   ├── info/                  # 🔲 待實作
│   │   ├── wmo_codes.py       # WMO 天氣代碼常數（中文）
│   │   ├── weather.py         # 天氣查詢（Open-Meteo）
│   │   ├── search.py          # 網路搜尋（DuckDuckGo）
│   │   └── system_info.py     # 時間 / 系統資訊
│   ├── file/                  # 🔲 待實作
│   │   └── file_ops.py        # 讀寫 agent_files/（requires_confirmation=True）
│   ├── system/                # 🔲 待實作
│   │   ├── app_control.py     # 開啟/關閉應用程式（v1 移植）
│   │   ├── volume.py          # 音量控制（v1 移植）
│   │   └── shell_runner.py    # run_shell，含黑名單過濾（v1 移植）
│   ├── browser/               # 🔲 待實作（Phase 6）
│   │   └── playwright_ctrl.py # Playwright 瀏覽器自動化（Phase 6）
│   ├── memory/                # 🔲 待實作（Phase 4）
│   │   ├── short_term.py      # 對話摘要（Phase 4）
│   │   └── long_term.py       # ChromaDB RAG（Phase 4）
│   ├── gmail/                 # 🔲 待實作（Phase 5）
│   │   └── gmail_skill.py     # Gmail OAuth2（Phase 5）
│   ├── schedule/              # 🔲 待實作
│   │   ├── reminder.py        # 一次性 + 循環提醒（v1 移植）
│   │   └── heartbeat.py       # 早安/晚安定時推播（v1 移植）
│   └── stream_monitor/        # 🔲 待實作（Phase 6）
│       ├── monitor.py         # 監控清單管理（v1 移植）
│       └── webhook_server.py  # YouTube WebSub Webhook（v1 移植）
├── storage/
│   ├── db.py                  # SQLite（Phase 4）
│   └── vector_store.py        # ChromaDB 封裝（Phase 4）
│
├── agent_files/               # Agent 可讀寫的本地工作區
└── logs/                      # 運行 log（每日輪替，保留 30 天）
```

---

## 分層架構

```
Telegram User
    ↓
interface/telegram_bot.py     ← 訊息/指令入口（async，不阻塞 event loop）
    ↓
core/router.py                ← 敏感偵測：決定 provider（groq / ollama）
    ↓
core/planner.py               ← Tool Call Loop（最多 5 輪），確認機制
    ↓
services/llm_gateway.py       ← 統一 LLM 呼叫，格式轉換，retry 邏輯
    ↓
skills/*                      ← 各功能技能（Auto-Discovery 插件）
    ↓
storage/（Phase 4）
    ↓
Reply to Telegram
```

---

## 重要設計決策

- **async-first**：所有 I/O 操作（LLM、HTTP、檔案）全走 async，TelegramBot.run() 也是 async，由 asyncio.run() 統一管理 event loop。
- **不模擬鍵盤滑鼠**：所有系統操作走 subprocess / shell。
- **Tool Call 取代 intent mapping**：技能路由完全由 LLM 決定。
- **本地優先敏感資料**：敏感指令強制走 Ollama，不送雲端。
- **OAuth 授權**：外部服務走 OAuth2，Agent 不直接持有帳密。
- **requires_confirmation 旗標**：查詢類直接執行，寫入/系統操作需 /confirm。
- **最大 tool call 輪數（5）**：防止無限迴圈。
- **Config dataclass 單例**：`from config import cfg`，不直接讀 os.environ。

---

## Skill 系統：模組化插件設計

Skill 採用**自動探索（Auto-Discovery）**機制，類似 OpenClaw / Hermes 的插件概念。  
新增或移除功能只需要操作 `skills/` 資料夾，不需要改動 `main.py`、Planner 或 LLMGateway。

### Skill 資料夾結構

每個 skill 是一個自包含的資料夾：

```
skills/
└── weather/
    ├── manifest.json          # 必要：id, tools, privacy_level 等
    └── weather.py             # 必要：繼承 Skill，export SKILL_CLASS
```

**`manifest.json` 格式：**
```json
{
  "id": "weather",
  "name": "天氣查詢",
  "version": "1.0.0",
  "description": "查詢即時天氣與 3 日預報",
  "requires_confirmation": false,
  "privacy_level": "public",
  "tools": ["get_weather"],
  "enabled": true
}
```

**新增 Skill 步驟：**
1. 在 `skills/` 建立新資料夾並放入 `manifest.json`
2. 建立 `.py` 檔，繼承 `Skill`，實作 `execute()` 與 `get_schemas()`
3. 重啟 Agent，SkillRegistry 自動掃描載入
### 停用 Skill（不刪除）

在 `manifest.json` 加上 `"enabled": false`，Registry 載入時會跳過。

---

## 安全設計原則

1. **電腦控制**：不允許模擬鍵盤滑鼠，系統操作一律走 subprocess / shell。
2. **檔案操作**：限制在 `agent_files/`，`core/security.py` 檢查路徑穿越。
3. **隱私保護**：`core/router.py` 偵測敏感關鍵字，自動強制走 Ollama（本地）。
4. **確認機制**：`requires_confirmation=True` 的 skill 暫停等待 `/confirm`。
5. **外部授權**：Gmail 等外部服務走 OAuth2，Agent 不直接持有帳密。
6. **緊急停止**：`/stop` 設定 `emergency_stop.Event`，取消所有背景任務。
7. **Tool Call 安全**：LLM 只能呼叫已在 `register_tools()` 中明確註冊的工具。
8. **Shell 黑名單**：`core/security.py` 過濾 `rm -rf /`、`format c:` 等危險指令。

---

## 設定檔說明

設定採用 **`.env` + `config.py`** 方式（不使用 yaml）。

**`.env`**（不 commit，參考 `.env.example`）：

```env
# LLM 設定
LLM_PROVIDER=auto              # auto | groq | ollama
CLOUD_PROVIDER=groq            # auto 模式下非敏感指令使用的雲端 provider

GROQ_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...   # 你的 Telegram user ID，留空不限制

YOUTUBE_API_KEY=...            # YouTube 頻道搜尋用（選填）
NGROK_AUTHTOKEN=...            # Webhook server 公開 URL（選填）
.
.
.
```

**`config.py`** 負責載入並提供全域設定物件，其他模組 `from config import cfg` 取用，不直接讀 `os.environ`。
---

## 執行方式

```bash
# 安裝依賴
pip install python-telegram-bot python-dotenv groq httpx

# 啟動 Bot
python main.py

# Debug 模式
python main.py --debug

# 終端機測試（不需要 Telegram）
python main.py --cli
```

---

## 重要設計決策

- **不模擬鍵盤滑鼠**：所有系統操作走 subprocess / shell。
- **Tool Call 取代 intent mapping**：技能路由完全由 LLM 決定。
- **本地優先敏感資料**：敏感指令強制走 Ollama，不送雲端。
- **OAuth 授權**：外部服務走 OAuth2。
- **Ollama 雙模式**：先嘗試原生 tool call，失敗時 fallback 到 JSON prompt 模式。
- **Provider 抽象層**：LLMGateway 統一介面，切換 provider 只改 `.env`。
- **requires_confirmation 旗標**：查詢類直接執行，寫入/系統操作需 `/confirm`。
- **最大 tool call 輪數（5）**：防止無限迴圈。

---

## 目前完成進度

### ✅ 核心框架（Phase 1 & 2）

| 檔案 | 狀態 | 說明 |
|------|------|------|
| `config.py` | ✅ 完成 | dataclass 單例，`cloud_provider` 欄位正確分離 |
| `services/llm_gateway.py` | ✅ 完成 | Groq + Ollama 統一層，retry，JSON fallback |
| `services/task_manager.py` | ✅ 完成 | asyncio 任務追蹤，emergency_stop/resume |
| `skills/base.py` | ✅ 完成 | Skill 抽象基底，`requires_confirmation`，`privacy_level` |
| `core/skill_registry.py` | ✅ 完成 | Auto-Discovery 插件系統 |
| `core/planner.py` | ✅ 完成 | Tool Call Loop + 確認機制，ConversationContext |
| `core/router.py` | ✅ 完成 | 敏感關鍵字路由 |
| `main.py` | ✅ 完成 | async 入口，CLI 模式，正確 event loop 管理 |
| `interface/telegram_bot.py` | ✅ 完成 | async run()，指令 handler，長訊息切割 |

### 🔧 已修正的 Bug（2026-04-30）

| 問題 | 原因 | 修正 |
|------|------|------|
| `RuntimeError: This event loop is already running` | `telegram_bot.run()` 是同步的，內部呼叫 `run_polling()` 試圖建立新 event loop，與外層 `asyncio.run()` 衝突 | `run()` 改為 `async`，改用 `initialize()` + `start()` + `updater.start_polling()` + `updater.idle()` |
| `LLMConfig` 有重複的 `provider` field | 複製貼上時把 `cloud_provider` 的 key 寫成 `provider` | 修正為 `cloud_provider: str` |
| `cfg.get("agent", {})` AttributeError | `cfg` 是 dataclass，不是 dict | 改為 `cfg.agent.xxx` 直接存取 |
| `cfg.llm.cloud_provider` AttributeError | `LLMConfig` 沒有 `cloud_provider` 欄位 | 補上 `cloud_provider` 欄位 |

### 🔲 待實作（Phase 3+）

#### Phase 3：系統技能移植（優先度高）
從 v1 `tools/` 搬遷：

| Skill | 來源（v1） | 說明 |
|-------|-----------|------|
| `skills/info/` | `tools/info.py` | 時間、天氣（Open-Meteo）、DuckDuckGo 搜尋 |
| `skills/file/` | `tools/info.py` | agent_files/ 讀寫，requires_confirmation=True |
| `skills/system/app_control` | `tools/apps.py` | Windows 模糊搜尋開啟程式 |
| `skills/system/volume` | `tools/system.py` | pycaw 音量控制 |
| `skills/system/shell_runner` | `tools/system.py` | run_shell + 黑名單 |

每個 skill 需要：
1. `skills/{name}/manifest.json`
2. `skills/{name}/{name}.py`（繼承 Skill）

#### Phase 4：記憶系統
- ChromaDB RAG（從 v1 `core/memory.py` + `core/rag.py` 移植）
- SQLite 對話歷史持久化
- ContextCompressor（token 超限時壓縮 history）

#### Phase 5：雲端整合
- `skills/gmail/`：Gmail OAuth2 收發信 + AI 廣告過濾
- `skills/schedule/reminder`：一次性 + 循環提醒
- `skills/schedule/heartbeat`：早安/晚安定時推播
- Google Calendar/Tasks 整合（排程同步）

#### Phase 6：進階能力
- `skills/browser/`：Playwright 瀏覽器自動化
- `skills/stream_monitor/`：YouTube WebSub + Twitch EventSub 開播通知

---

## 下一步建議

1. **建立第一個 skill**（驗證插件系統可用）：
   ```
   skills/info/
   ├── manifest.json
   └── info.py   ← get_current_time, get_weather, web_search
   ```

2. **測試 CLI 模式**確認 Planner + LLM Gateway 流程正常：
   ```bash
   python main.py --cli
   ```

3. **逐步移植 Phase 3 skills**，每完成一個就測試一次

---

## 已知限制

- Skill 資料夾目前只有空目錄（沒有 manifest.json），啟動時會出現 ERROR log（不影響運行，只是警告）
- Ollama 需要本機先執行 `ollama serve`，gateway 會自動嘗試啟動但可能失敗
- Twitch API key 尚未取得，stream_monitor 的 Twitch 功能暫時無法使用
