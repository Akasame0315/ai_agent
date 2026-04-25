# Claude Agent — 專案快速上手文件

> 給新對話的 Claude 閱讀，快速理解專案架構與當前狀態，減少重複說明。

---

## 專案定位

以 **Telegram Bot** 為入口的個人 AI 助理框架。  
使用者透過 Telegram 下指令，Agent 理解意圖、調用技能、回傳結果。  
LLM 負責意圖判斷與技能路由，不使用硬編碼規則。  
設計靈感參考 n8n 的節點式工作流概念，但溝通層完全走 LLM。

---

## 技術棧

| 層級 | 技術 |
|------|------|
| 語言 | Python |
| Telegram | python-telegram-bot |
| LLM | Groq API（雲端）/ Ollama（本地） |
| 向量記憶 | ChromaDB |
| 關聯式儲存 | SQLite |
| 瀏覽器自動化 | Playwright |
| 外部整合 | Gmail / Google Calendar（OAuth2） |
| 開發環境 | VS Code |

---

## 目錄結構

```
.
├── main.py                  # 入口，argparse (--debug)
├── claude.md                # 本文件
├── config/
│   ├── loader.py            # 載入 settings.yaml + .env
│   ├── settings.yaml        # 主要設定（agent / llm / telegram / logging）
│   └── .env                 # 金鑰（不 commit）
├── interface/
│   └── telegram_bot.py      # Telegram Bot 收發訊息、指令處理
├── core/
│   ├── planner.py           # 對話上下文管理、意圖分析（Phase 2+）
│   ├── router.py            # 意圖 → 技能路由（待整合）
│   ├── executor.py          # 任務佇列與執行（待整合）
│   └── security.py          # 危險操作審查、路徑安全
├── services/
│   ├── llm_gateway.py       # Groq / Ollama 路由，debug prompt log
│   └── task_manager.py      # asyncio 任務追蹤、緊急停止
├── skills/
│   ├── base.py              # Skill 抽象基底類別
│   ├── info/
│   │   ├── weather.py       # 天氣查詢（骨架）
│   │   ├── search.py        # 網路搜尋（骨架）
│   │   └── system_info.py   # 系統資訊 / 時間（骨架）
│   ├── file/
│   │   └── file_ops.py      # 讀寫 agent_files/（安全路徑限制）
│   ├── system/
│   │   ├── app_control.py   # 開啟 / 關閉應用程式（骨架）
│   │   ├── volume.py        # 音量控制（骨架）
│   │   └── screenshot.py    # 截圖（骨架）
│   ├── browser/
│   │   └── playwright_ctrl.py # Playwright 瀏覽器自動化（骨架）
│   ├── memory/
│   │   ├── short_term.py    # 當次對話摘要（骨架）
│   │   └── long_term.py     # ChromaDB RAG 跨對話記憶（骨架）
│   ├── gmail/
│   │   └── gmail_skill.py   # Gmail OAuth2 收發信（骨架）
│   ├── schedule/
│   │   └── scheduler.py     # APScheduler + Google Calendar（骨架）
│   └── stream_monitor/
│       └── yt_monitor.py    # YouTube 直播監控（骨架）
├── storage/
│   ├── db.py                # SQLite（對話歷史、排程、設定、使用者偏好）
│   └── vector_store.py      # ChromaDB 封裝
├── agent_files/             # Agent 可讀寫的本地工作區
└── logs/                    # 運行 log（rotating）
```

---

## 分層架構

```
Telegram User
    ↓
interface/telegram_bot.py     ← 訊息入口、指令處理、權限檢查
    ↓
core/planner.py               ← 對話上下文、意圖分析（Phase 2+ 接 Router）
    ↓
services/llm_gateway.py       ← LLM 路由（Groq / Ollama）、隱私判斷
    ↓
core/router.py → core/executor.py → skills/*   ← Phase 2+ 啟用
    ↓
storage/（SQLite / ChromaDB）
    ↓
Reply to Telegram
```

---

## 安全設計原則

1. **電腦控制**：不允許 Agent 模擬鍵盤滑鼠；系統操作一律走 shell 指令或系統 API（IO 方法直接建立/編輯檔案）。
2. **檔案操作**：限制在 `agent_files/` 與 `data/` 目錄，`core/security.py` 檢查路徑穿越。
3. **隱私保護**：`planner.py` 偵測敏感關鍵字，自動 `force_local=True` 走 Ollama，不送雲端。
4. **外部授權**：Gmail / Google Calendar 等外部服務一律走 OAuth2，不直接存取帳密。
5. **緊急停止**：`/stop` 指令或 `Ctrl+Shift+F12` 呼叫 `TaskManager.emergency_stop()`，取消所有進行中任務。
6. **危險操作審查**：`core/security.py` 維護危險關鍵字清單，觸發時要求使用者確認。

---

## 目前完成進度（Phase 1 ✅）

| 功能 | 狀態 |
|------|------|
| Telegram Bot 收發訊息 | ✅ 完成 |
| `/start` `/help` `/new` `/stop` `/resume` `/status` 指令 | ✅ 完成 |
| `allowed_user_ids` 白名單 | ✅ 完成 |
| Groq / Ollama LLM 路由 | ✅ 完成 |
| 對話上下文管理（記憶體，max 20 輪） | ✅ 完成 |
| 隱私關鍵字偵測 → 本地 LLM | ✅ 完成 |
| TaskManager 任務追蹤與緊急停止 | ✅ 完成 |
| `--debug` CLI flag（印 system prompt + last user message） | ✅ 完成 |
| 各技能骨架模組 | ✅ 骨架已建立，待整合 |
| SQLite / ChromaDB 儲存層 | ✅ 骨架已建立，待整合 |

---

## 待完成（Phase 2+）

### Phase 2：資訊技能整合
- [ ] `Router` / `Executor` / `Security` 正式接入 `Planner`
- [ ] 天氣查詢（OpenWeatherMap API）
- [ ] 網路搜尋（SerpAPI / DuckDuckGo）
- [ ] 系統時間 / 系統資訊

### Phase 3：檔案與系統技能
- [ ] `file_ops` 接入主流程
- [ ] `app_control`（模糊搜尋開啟應用程式）
- [ ] 音量控制
- [ ] 截圖

### Phase 4：記憶系統
- [ ] 短期摘要（LLM 自動摘要 history）
- [ ] ChromaDB RAG 接入對話流程
- [ ] SQLite 對話歷史持久化

### Phase 5：雲端整合
- [ ] Gmail OAuth2 收發信（自動過濾廣告）
- [ ] Google Calendar / Tasks 同步

### Phase 6：進階能力
- [ ] Playwright 瀏覽器自動化
- [ ] YouTube 直播開播通知（Webhook）
- [ ] Twitch 監控（待 API key）
- [ ] 個人化設定（稱呼、城市、語氣）
- [ ] 知識庫 RAG（文件匯入、語意搜尋）
- [ ] 排程提醒（APScheduler，小型事項存本地）

---

## 設定檔說明

**`config/settings.yaml`**：
```yaml
agent:
  owner_name: "user"        # Agent 如何稱呼你
  assistant_name: "agent"   # Agent 自己的名字
  persona: "assistant"      # 角色風格
  city: "Taipei"
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
```

**`config/.env`**（不 commit）：
```
TELEGRAM_BOT_TOKEN=...
GROQ_API_KEY=...
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

## 重要設計決策記錄

- **不模擬鍵盤滑鼠**：所有系統操作走 subprocess / shell，避免干擾使用者當前操作。
- **LLM 做路由**：技能選擇不用硬編碼 if/else，由 LLM 判斷意圖後交給 Router，符合 n8n 節點邏輯。
- **本地優先敏感資料**：密碼、金鑰等敏感訊息強制走 Ollama，不送 Groq 雲端。
- **OAuth 授權**：Gmail、Google Calendar 等外部服務走 OAuth2，Agent 不直接持有帳密。
- **緊急停止隨時可用**：`/stop` 會 cancel 所有 asyncio task，確保使用者隨時能中斷 Agent。
