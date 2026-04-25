# V2 Agent

V2 Agent 是一個以 **Telegram Bot** 為入口的個人 AI 助理專案。  
整體設計採用分層架構，將對話入口、任務協調、技能模組、服務層與儲存層拆分，目標是從可用的對話型代理，逐步擴充成具備資訊查詢、系統操作、記憶能力與雲端整合的個人代理系統。

目前專案已完成 **Phase 1：基礎對話主線**，可透過 Telegram 與 agent 對話，並經由 Planner 與 LLM Gateway 使用 **Groq / Ollama** 產生回覆。  
其餘功能已依照架構規劃建立模組骨架，後續將逐步整合進主流程。

## Features

### Current

- **Telegram 對話入口**
  - 支援 Telegram Bot 訊息接收與回覆
  - 提供 `/start`、`/help`、`/new`、`/stop`、`/resume`、`/status`
  - 支援 `allowed_user_ids` 控制可使用者

- **對話協調主線**
  - `Planner` 管理單一使用者對話上下文
  - `TaskManager` 管理背景任務與緊急停止
  - `LLMGateway` 支援 Groq 與 Ollama 路由

- **基礎隱私路由**
  - 對敏感內容可優先走本地 Ollama
  - 為後續更完整的安全與權限控管預留擴充點

### In Progress / Planned

- **資訊技能**
  - 搜尋
  - 天氣
  - 時間
  - 截圖

- **系統與檔案技能**
  - `file_ops`
  - `app_control`
  - 音量控制

- **記憶能力**
  - 短期摘要
  - ChromaDB RAG
  - 跨對話記憶

- **雲端整合**
  - Gmail OAuth 與收發信
  - Google Calendar 與排程提醒

- **進階能力**
  - Playwright 瀏覽器自動化
  - YouTube / Twitch 直播監控
  - 個人化設定

## Architecture

專案依照五層架構設計：

### 1. Interface Layer

負責與使用者互動，目前以 Telegram Bot 為主要入口。

- Telegram Bot
- `/stop` 緊急停止
- 危險操作確認提示（規劃中）

### 2. Orchestration Layer

負責理解使用者需求、決定要不要呼叫技能，以及如何執行任務。

- **Planner**：意圖分析、任務拆解、對話上下文管理
- **Router**：技能路由、隱私判斷
- **Executor**：任務佇列、結果回傳

### 3. Skill Layer

負責具體能力執行，未來會逐步將各 skill 接入主流程。

- **Info**：搜尋、天氣、時間
- **File**：讀寫 `agent_files/`
- **System**：音量、截圖、應用程式控制
- **Browser**：Playwright 自動化
- **Gmail**：OAuth、收發信
- **Memory**：RAG、跨對話記憶
- **Schedule**：提醒、Calendar
- **Stream**：YT / Twitch Webhook

### 4. Service Layer

提供底層共用能力與安全控管。

- **LLM Gateway**：Groq / Ollama 路由
- **Security Guard**：隱私過濾、權限審查
- **Task Manager**：排程、中斷、狀態管理

### 5. Storage Layer

負責資料持久化與本地資源管理。

- **ChromaDB**：向量記憶、RAG
- **SQLite**：對話、排程、設定
- **agent_files/**：本地檔案操作
- **OAuth**：Token 保存

## System Flow

```text
Telegram User
   ↓
Telegram Bot
   ↓
Planner
   ↓
LLM Gateway / Router / Executor
   ↓
Skills / Services
   ↓
Storage
   ↓
Reply to Telegram
```

## Roadmap

### Phase 1: Foundation

- Telegram ↔ Planner ↔ Groq / Ollama ↔ 回覆
- 基礎對話上下文
- 任務中斷與恢復

**Status:** Completed as current MVP

### Phase 2: Information Skills

- 搜尋
- 天氣
- 時間
- 截圖

**Status:** 模組骨架已存在，待 API 與主流程整合

### Phase 3: File + System Skills

- `file_ops`
- `app_control`
- 音量控制

**Status:** 已有初步實作，待安全控管與調度整合

### Phase 4: Memory

- 短期摘要
- ChromaDB RAG
- 跨對話記憶

**Status:** storage 與 skill 骨架已建立，尚未正式接入對話流程

### Phase 5: Cloud Integration

- Gmail OAuth
- Gmail 收發信
- Google Calendar

**Status:** 已有整合方向與模組骨架，尚待 API 與 OAuth 流程完善

### Phase 6: Advanced Capabilities

- Playwright 瀏覽器操作
- 直播監控
- 個人化設定

**Status:** 屬於進階能力階段，已建立雛形模組

## Project Structure

```text
.
├─ interface/      # Telegram Bot
├─ core/           # Planner / Router / Executor / Security
├─ services/       # LLM Gateway / Task Manager
├─ skills/         # Info / File / System / Browser / Gmail / Memory / Schedule / Stream
├─ storage/        # SQLite / ChromaDB abstraction
├─ config/         # Settings and environment loader
├─ agent_files/    # Local workspace for agent file operations
├─ logs/           # Runtime logs
└─ main.py         # Application entry point
```

## Current Status

已可使用的核心能力是 Telegram 對話與 Groq / Ollama 回覆主線；  
其餘能力目前多數處於「模組已建立、等待整合」的狀態。

## Next Focus
#### update at: 2026/04/26
接下來最重要的優化方向：

1. 將 `Router`、`Executor`、`Security` 正式接入 `Planner`
2. 完成資訊類與系統類技能的主流程整合
3. 把 SQLite 與 ChromaDB 記憶層接入對話系統
4. 完成 Gmail / Calendar / Browser / Stream 等外部整合

## Tech Stack

- Python
- python-telegram-bot
- Groq API
- Ollama
- SQLite
- ChromaDB
- Playwright
- Google OAuth / Gmail / Calendar APIs

## Vision

這個專案的方向不是只做一個聊天機器人，而是建立一個可長期演進的個人代理框架：

- 能理解任務
- 能調用技能
- 能操作本地系統與檔案
- 能記住重要資訊
- 能串接外部服務

隨著各 phase 完成，V2 Agent 會從「對話入口」逐步演進成真正可協作的個人 AI 助理。
