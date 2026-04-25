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
| 搜尋 | duckduckgo-search（預設）/ Serper.dev（擴充） |
| 天氣 | Open-Meteo（免費，無需 API key） |
| 向量記憶 | ChromaDB（骨架已建，Phase 4 接入） |
| 關聯式儲存 | SQLite（骨架已建，Phase 4 接入） |
| 瀏覽器自動化 | Playwright（Phase 6） |
| 外部整合 | Gmail / Google Calendar OAuth2（Phase 5） |
| 開發環境 | VS Code |

---

## 目錄結構

```
.
├── main.py                    # 入口，argparse (--debug)，skill 初始化
├── claude.md                  # 本文件
├── config/
│   ├── loader.py              # 載入 settings.yaml + .env
│   ├── settings.yaml          # 主設定（agent/llm/telegram/search/logging）
│   ├── settings.yaml.example  # 設定範例（含所有欄位說明）
│   └── .env                   # 金鑰（不 commit）
├── interface/
│   └── telegram_bot.py        # Telegram Bot，含 /confirm /cancel 指令
├── core/
│   ├── planner.py             # Tool Call Loop，確認機制，對話上下文
│   ├── router.py              # 意圖路由（Phase 2 暫未使用，由 tool call 取代）
│   ├── executor.py            # 任務佇列（Phase 2 暫未使用）
│   └── security.py            # 危險操作審查、路徑安全
├── services/
│   ├── llm_gateway.py         # Groq（原生 tool call）/ Ollama（原生→JSON fallback）
│   └── task_manager.py        # asyncio 任務追蹤、緊急停止
├── skills/
│   ├── base.py                # Skill 抽象基底（含 requires_confirmation 旗標）
│   ├── info/
│   │   ├── wmo_codes.py       # WMO 天氣代碼常數（中文）
│   │   ├── weather.py         # ✅ 天氣查詢（Open-Meteo，async）
│   │   ├── search.py          # ✅ 網路搜尋（DuckDuckGo/Serper，可切換）
│   │   └── system_info.py     # ✅ 時間 / 系統資訊
│   ├── file/
│   │   └── file_ops.py        # 讀寫 agent_files/（requires_confirmation=True）
│   ├── system/
│   │   ├── app_control.py     # 開啟/關閉應用程式（骨架）
│   │   ├── volume.py          # 音量控制（骨架）
│   │   └── screenshot.py      # 截圖（骨架）
│   ├── browser/
│   │   └── playwright_ctrl.py # Playwright 瀏覽器自動化（骨架）
│   ├── memory/
│   │   ├── short_term.py      # 對話摘要（骨架）
│   │   └── long_term.py       # ChromaDB RAG（骨架）
│   ├── gmail/
│   │   └── gmail_skill.py     # Gmail OAuth2（骨架）
│   ├── schedule/
│   │   └── scheduler.py       # APScheduler + Google Calendar（骨架）
│   └── stream_monitor/
│       └── yt_monitor.py      # YouTube 直播監控（骨架）
├── storage/
│   ├── db.py                  # SQLite（對話歷史、排程、設定、偏好）
│   └── vector_store.py        # ChromaDB 封裝
├── agent_files/               # Agent 可讀寫的本地工作區
└── logs/                      # 運行 log（rotating）
```

---

## 分層架構

```
Telegram User
    ↓
interface/telegram_bot.py     ← 訊息/指令入口，/confirm /cancel 處理
    ↓
core/planner.py               ← Tool Call Loop（最多 5 輪），確認機制
    ↓
services/llm_gateway.py       ← Groq（原生 tool call）/ Ollama（原生→JSON fallback）
    ↓
skills/*                      ← 天氣 / 搜尋 / 時間（已接入）；其他骨架待 Phase 3+
    ↓
storage/（SQLite / ChromaDB）  ← Phase 4 接入
    ↓
Reply to Telegram
```

---

## Tool Call 運作流程

```
使用者: 「台北天氣怎樣？」
    ↓
Planner._tool_call_loop()
    ↓
LLM 回傳: tool_call{ name="get_weather", args={city="Taipei"} }
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
requires_confirmation? → 是（寫入操作）→ 暫存 pending
    ↓
Bot 回覆: 「⚠️ 即將執行：寫入檔案 notes.txt，確認請回覆 /confirm，取消請回覆 /cancel」
    ↓
使用者回 /confirm → 執行 → LLM 生成最終回覆
```

---

## Skill 新增方式（未來擴充）

1. 在 `skills/` 下建立新 skill，繼承 `Skill` 基底類
2. 在 skill 模組層級定義 `TOOL_SCHEMA`（OpenAI function calling 格式）
3. 在 `main.py` 的 `build_skills()` 加入初始化
4. 在 `core/planner.py` 的 `_TOOL_MAP` 加入 tool name → (skill_name, action) 映射

不需要改動 LLMGateway 或 Telegram Bot。

---

## 搜尋 Provider 切換方式

```yaml
# settings.yaml
search:
  provider: "duckduckgo"   # 改成 "serper" 即可切換
  serper_api_key: "..."    # 使用 serper 時填入
  max_results: 5
```

架構：`SearchProvider` 抽象基底 → `DuckDuckGoProvider` / `SerperProvider`，由 `build_provider(config)` factory 建立，新增 provider 只需實作 `SearchProvider` 介面。

---

## 安全設計原則

1. **電腦控制**：不允許模擬鍵盤滑鼠，系統操作一律走 subprocess / shell。
2. **檔案操作**：限制在 `agent_files/`，`core/security.py` 檢查路徑穿越。
3. **隱私保護**：偵測敏感關鍵字，自動 `force_local=True` 走 Ollama。
4. **確認機制**：`requires_confirmation=True` 的 skill 會暫停等待 `/confirm`。
5. **外部授權**：Gmail / Google Calendar 等一律走 OAuth2。
6. **緊急停止**：`/stop` 取消所有 asyncio task，`/resume` 恢復。
7. **Tool Call 安全**：LLM 只能呼叫已在 `register_tools()` 中明確註冊的工具。

---

## 目前完成進度

| 功能 | 狀態 |
|------|------|
| Telegram Bot 收發訊息 | ✅ |
| 基礎指令（/start /help /new /stop /resume /status） | ✅ |
| 確認指令（/confirm /cancel） | ✅ |
| Groq / Ollama LLM 路由 | ✅ |
| Tool Call（Groq 原生 / Ollama 原生+JSON fallback） | ✅ |
| 天氣查詢（Open-Meteo，async） | ✅ |
| 網路搜尋（DuckDuckGo，Serper 可切換） | ✅ |
| 時間 / 系統資訊 | ✅ |
| --debug CLI flag | ✅ |
| 各技能骨架 | ✅ 骨架已建，待 Phase 3+ |
| SQLite / ChromaDB 儲存層 | ✅ 骨架已建，待 Phase 4 |

---

## 待完成（Phase 3+）

### Phase 3：檔案與系統技能
- [ ] `file_ops` 接入 tool call（需補 TOOL_SCHEMA + _TOOL_MAP）
- [ ] `app_control`（模糊搜尋開啟應用程式）
- [ ] 音量控制
- [ ] 截圖

### Phase 4：記憶系統
- [ ] ContextCompressor（token 接近上限時壓縮中間 history）
- [ ] SQLite 對話歷史持久化
- [ ] ChromaDB RAG 接入對話流程

### Phase 5：雲端整合
- [ ] Gmail OAuth2 收發信（自動過濾廣告）
- [ ] Google Calendar / Tasks 同步

### Phase 6：進階能力
- [ ] Playwright 瀏覽器自動化
- [ ] YouTube 直播開播通知（Webhook）
- [ ] 知識庫 RAG（文件匯入、語意搜尋）
- [ ] 排程提醒（APScheduler）

---

## 設定檔說明

**`config/settings.yaml`** 關鍵欄位：

```yaml
agent:
  owner_name: "user"        # Agent 如何稱呼你
  assistant_name: "agent"   # Agent 自己的名字
  persona: "assistant"      # 角色風格
  city: "Taipei"           # 天氣 fallback 城市
  timezone: "Asia/Taipei"  # 時間查詢預設時區
  language: "zh-TW"
  system_prompt: ""         # 額外補充 prompt

llm:
  default_provider: "groq"  # groq | ollama
  groq_model: "llama-3.3-70b-versatile"
  ollama_model: "qwen2.5:14b"
  max_tokens: 2048
  temperature: 0.7
  timeout: 30

telegram:
  allowed_user_ids: []      # 留空不限制；填入 Telegram user ID 啟用白名單

search:
  provider: "duckduckgo"   # duckduckgo | serper
  serper_api_key: ""
  max_results: 5
  

```

**`config/.env`**（不 commit）：
```
TELEGRAM_BOT_TOKEN=...
GROQ_API_KEY=...
# SERPER_API_KEY=...   # 選填，改用 serper 時填入
```

---

## 執行方式

```bash
# 正常啟動
python main.py

# Debug 模式（console 印出 system prompt + last user message）
python main.py --debug
```

---

## 重要設計決策

- **不模擬鍵盤滑鼠**：所有系統操作走 subprocess / shell，避免干擾使用者當前操作。
- **Tool Call 取代 intent mapping**：技能路由完全由 LLM 決定，不用硬編碼 if/else，符合 n8n 節點邏輯。
- **本地優先敏感資料**：密碼、金鑰等敏感訊息強制走 Ollama，不送 Groq 雲端。
- **OAuth 授權**：Gmail、Google Calendar 等外部服務走 OAuth2，Agent 不直接持有帳密。
- **Ollama 雙模式**：先嘗試原生 tool call，失敗時 fallback 到 system prompt JSON 模式，確保任何 Ollama 模型都能運作。
- **Provider 抽象層**：搜尋、LLM 都有抽象基底類，切換 provider 只需改 settings.yaml，不需改程式碼。
- **requires_confirmation 旗標**：查詢類 skill 直接執行，寫入/系統操作需 /confirm，安全與便利兼顧。
- **最大 tool call 輪數（5）**：防止 LLM 進入無限 tool call 迴圈。