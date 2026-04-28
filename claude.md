# Claude Agent — 專案快速上手文件

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
| Telegram | python-telegram-bot |
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
├── main.py                    # 入口，argparse (--debug)，skill 初始化
├── config.py                  # 環境變數載入（.env → 全域設定物件）
├── .env                       # API Keys（不 commit）
├── .env.example               # .env 範本
├── claude.md                  # 本文件
├── interface/
│   └── telegram_bot.py        # Telegram Bot，含 /confirm /cancel /stop 等指令
├── core/
│   ├── planner.py             # Tool Call Loop（最多 5 輪），確認機制，對話上下文
│   ├── router.py              # 敏感指令路由：偵測關鍵字 → 強制走 Ollama
│   ├── security.py            # 危險 shell 指令黑名單、路徑穿越檢查
│   └── emergency_stop.py      # 緊急停止旗標（threading.Event）
├── services/
│   ├── llm_gateway.py         # ✅ 統一 LLM 呼叫：Groq / Ollama，格式轉換，retry
│   └── task_manager.py        # asyncio 任務追蹤、背景任務推播
├── skills/
│   ├── base.py                # Skill 抽象基底（含 requires_confirmation 旗標）
│   ├── info/
│   │   ├── wmo_codes.py       # WMO 天氣代碼常數（中文）
│   │   ├── weather.py         # 天氣查詢（Open-Meteo）
│   │   ├── search.py          # 網路搜尋（DuckDuckGo）
│   │   └── system_info.py     # 時間 / 系統資訊
│   ├── file/
│   │   └── file_ops.py        # 讀寫 agent_files/（requires_confirmation=True）
│   ├── system/
│   │   ├── app_control.py     # 開啟/關閉應用程式（v1 移植）
│   │   ├── volume.py          # 音量控制（v1 移植）
│   │   └── shell_runner.py    # run_shell，含黑名單過濾（v1 移植）
│   ├── browser/
│   │   └── playwright_ctrl.py # Playwright 瀏覽器自動化（Phase 6）
│   ├── memory/
│   │   ├── short_term.py      # 對話摘要（Phase 4）
│   │   └── long_term.py       # ChromaDB RAG（Phase 4）
│   ├── gmail/
│   │   └── gmail_skill.py     # Gmail OAuth2（Phase 5）
│   ├── schedule/
│   │   ├── reminder.py        # 一次性 + 循環提醒（v1 移植）
│   │   └── heartbeat.py       # 早安/晚安定時推播（v1 移植）
│   └── stream_monitor/
│       ├── monitor.py         # 監控清單管理（v1 移植）
│       └── webhook_server.py  # YouTube WebSub Webhook（v1 移植）
├── storage/
│   ├── db.py                  # SQLite（Phase 4）
│   └── vector_store.py        # ChromaDB 封裝（Phase 4）
├── agent_files/               # Agent 可讀寫的本地工作區
└── logs/                      # 運行 log（rotating）
```

---

## 分層架構

```
Telegram User
    ↓
interface/telegram_bot.py     ← 訊息/指令入口
    ↓
core/router.py                ← 敏感偵測：決定 provider（groq / ollama）
    ↓
core/planner.py               ← Tool Call Loop（最多 5 輪），確認機制
    ↓
services/llm_gateway.py       ← 統一 LLM 呼叫，格式轉換，retry 邏輯
    ↓
skills/*                      ← 各功能技能
    ↓
storage/（Phase 4）
    ↓
Reply to Telegram
```

---

## Tool Call 運作流程

```
使用者: 「台北天氣怎樣？」
    ↓
router.py → 非敏感 → groq
    ↓
Planner._tool_call_loop()
    ↓
LLMGateway.chat() → LLM 回傳: tool_call{ name="get_weather", args={city="Taipei"} }
    ↓
requires_confirmation? → 否（查詢類）→ 直接執行
    ↓
WeatherSkill.execute("get_weather", city="Taipei")
    → 「🌍 台北，台灣 🌤 晴天 🌡 28°C ...」
    ↓
結果加入 history 作為 tool message
    ↓
LLM 再次呼叫 → 根據結果生成自然語言回覆
    ↓
使用者收到回覆
```

需要確認的流程（`requires_confirmation=True`）：
```
使用者: 「把 notes.txt 的內容改成 hello」
    ↓
LLM 回傳: tool_call{ name="write_file", args={path="notes.txt", content="hello"} }
    ↓
requires_confirmation? → 是 → 暫存 pending_call
    ↓
Bot 回覆: 「⚠️ 即將執行：寫入 notes.txt，確認請回覆 /confirm，取消請回覆 /cancel」
    ↓
使用者回 /confirm → 執行 → LLM 生成最終回覆
```

---

## Skill 新增方式

1. 在 `skills/` 下建立新 skill，繼承 `skills/base.py` 的 `Skill`
2. 定義 `TOOL_SCHEMA`（OpenAI function calling 格式）
3. 在 `main.py` 的 `build_skills()` 加入初始化
4. 在 `core/planner.py` 的 `_TOOL_MAP` 加入 `tool_name → (skill_instance, method)` 映射

不需要改動 LLMGateway 或 Telegram Bot。

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
```
LLM_PROVIDER=auto              # auto | groq | ollama
CLOUD_PROVIDER=groq            # auto 模式下非敏感指令使用的雲端 provider

GROQ_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:14b

TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_ID=...   # 你的 Telegram user ID，留空不限制

YOUTUBE_API_KEY=...            # YouTube 頻道搜尋用（選填）
NGROK_AUTHTOKEN=...            # Webhook server 公開 URL（選填）
```

**`config.py`** 負責載入並提供全域設定物件，其他模組 `from config import cfg` 取用，不直接讀 `os.environ`。

---

## 執行方式

```bash
# 一般啟動（Telegram Bot）
python main.py

# Debug 模式
python main.py --debug

# 終端機測試（不需要 Telegram）
python main.py --cli

# Bot + Webhook Server 同時啟動
python main.py --all
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

| 功能 | 狀態 |
|------|------|
| Telegram Bot 收發訊息 | ✅ |
| 基礎指令（/start /stop /status /clear） | ✅ |
| 確認指令（/confirm /cancel） | ✅ |
| **LLMGateway 統一層（Groq + Ollama）** | ✅ 本次完成 |
| Tool Call Loop（Planner） | ✅ |
| 敏感路由（Router） | ✅ |
| 天氣查詢 | ✅ |
| 網路搜尋 | ✅ |
| 時間 / 系統資訊 | ✅ |
| 各技能骨架 | ✅ 骨架已建 |
| SQLite / ChromaDB 儲存層 | 🔲 Phase 4 |

---

## 待完成

### 【技術債】v1 → v2 架構遷移（按優先度排序）

> **已完成：** `services/llm_gateway.py` 統一 LLM 層

#### 🔴 高優先（影響其他模組）
- [ ] **`core/planner.py` 重構**：從 v1 `core/agent.py` 整合；
  - v1 問題：`run_agent()` 把 provider 路由、記憶注入、LLM 呼叫全部混在一起，無法單獨測試
  - 目標：planner 只負責 tool call loop，路由交給 router，記憶交給 memory skill

#### 🟡 中優先（功能完整性）
- [ ] **`interface/telegram_bot.py` 瘦身**：
  - v1 問題：`channels/telegram_bot.py` 混入模型切換邏輯、直播通知、.env 寫入等業務邏輯（約 400 行）
  - 目標：bot 只做訊息收發，業務邏輯下沉到各自模組
- [ ] **`skills/` 全面接入 tool call**：
  - v1 的 `tools/__init__.py` 近 700 行，所有工具定義、handler、隱私過濾全混在一起
  - 目標：每個 skill 自帶 `TOOL_SCHEMA`，由 `main.py` 統一 register

#### 🟢 低優先（功能擴充）
- [ ] **`core/security.py`**：從 v1 `tools/system.py` 的 `_SHELL_BLACKLIST` 和 `core/dynamic_skill.py` 的 `FORBIDDEN_PATTERNS` 整合
- [ ] **`core/emergency_stop.py`**：直接從 v1 移植，邏輯已完整

### Phase 3：系統技能移植（從 v1）
- [ ] `skills/system/app_control.py`：從 `tools/apps.py` 移植（Windows 登錄檔模糊搜尋）
- [ ] `skills/system/volume.py`：從 `tools/system.py` 移植（pycaw）
- [ ] `skills/system/shell_runner.py`：從 `tools/system.py` 移植（run_shell + 黑名單）
- [ ] `skills/file/file_ops.py`：接入 tool call schema

### Phase 4：記憶系統
- [ ] ContextCompressor（token 接近上限時壓縮 history）
- [ ] SQLite 對話歷史持久化
- [ ] ChromaDB RAG（從 v1 `core/memory.py` + `core/rag.py` 移植）

### Phase 5：雲端整合
- [ ] `skills/gmail/`：從 v1 `tools/gmail.py` 移植（OAuth2 收發信 + AI 廣告過濾）
- [ ] `skills/schedule/reminder.py`：從 v1 `scheduler/reminder.py` 移植
- [ ] `skills/schedule/heartbeat.py`：從 v1 `scheduler/heartbeat.py` 移植

### Phase 6：進階能力
- [ ] `skills/browser/`：從 v1 `tools/browser.py` 移植（Playwright）
- [ ] `skills/stream_monitor/`：從 v1 `webhook_server.py` + `tools/stream_monitor.py` 移植
- [ ] `skills/stream_monitor/youtube.py`：從 v1 `tools/youtube.py` 移植（頻道搜尋）