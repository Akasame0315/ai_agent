"""
工具總入口：統一定義 + 統一呼叫
路徑：tools/__init__.py

所有工具實作分散在子模組，這裡負責：
1. 彙整所有工具的 import
2. 定義 TOOL_DEFINITIONS（告訴 LLM 有哪些工具）
3. 隱私過濾：雲端模型自動移除敏感工具
4. execute_tool：統一呼叫入口
"""

from tools.info    import (get_current_time, get_system_info,
                            get_weather, web_search,
                            write_file, read_file, list_files,
                            list_memories, clear_memories,
                            import_document, import_text_to_knowledge,
                            list_knowledge_documents, delete_knowledge_document,
                            research_topic,
                            get_persona, update_persona, add_persona_instruction)
from tools.apps    import (open_application, search_installed_apps,
                            list_running_apps, close_application,
                            focus_application)
from tools.system  import (set_volume, take_screenshot,
                            mouse_action, keyboard_type, run_shell)
from tools.gmail   import (check_inbox, read_email, send_email,
                            reply_email, move_to_trash, 
                          mark_as_read, mark_as_unread)
from tools.stream_monitor import (add_stream_channel, remove_stream_channel,
                               list_stream_channels)
from tools.browser import (browser_open, browser_read, browser_click,
                            browser_fill, browser_screenshot,
                            browser_search, browser_close,
                            browser_current_url)

import os as _os
# 容器模式：停用需要桌面環境的工具
_CONTAINER_MODE = _os.environ.get("CONTAINER_MODE", "0") == "1"

# 在容器模式下額外停用的工具
CONTAINER_DISABLED_TOOLS = {
    "set_volume", "take_screenshot",
    "mouse_action", "keyboard_type",
    "open_application", "search_installed_apps",
    "list_running_apps", "close_application",
} if _CONTAINER_MODE else set()


# ══════════════════════════════════════════════════════════════════════
# Tool 定義（告訴 LLM 有哪些工具）
# ══════════════════════════════════════════════════════════════════════
TOOL_DEFINITIONS = [

    # ── 時間 / 系統資訊 ───────────────────────────────────────────────
    {
        "name": "get_current_time",
        "description": "取得現在的日期和時間",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_system_info",
        "description": "查詢電腦系統資訊：CPU、記憶體、磁碟、作業系統版本",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },

    # ── 天氣 ──────────────────────────────────────────────────────────
    {
        "name": "get_weather",
        "description": "查詢指定城市的即時天氣和未來 3 天預報",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名稱，例如：台北、Tokyo、New York"}
            },
            "required": ["city"]
        }
    },

    # ── 搜尋 ──────────────────────────────────────────────────────────
    {
        "name": "web_search",
        "description": "用 DuckDuckGo 搜尋網路資訊",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":       {"type": "string",  "description": "搜尋關鍵字"},
                "max_results": {"type": "integer", "description": "回傳幾筆，預設 5"}
            },
            "required": ["query"]
        }
    },

    # ── 檔案 ──────────────────────────────────────────────────────────
    {
        "name": "write_file",
        "description": "把內容寫入 agent_files 資料夾裡的檔案",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "檔案名稱"},
                "content":  {"type": "string", "description": "要寫入的內容"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "read_file",
        "description": "讀取 agent_files 資料夾裡的檔案",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "要讀取的檔案名稱"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "list_files",
        "description": "列出 agent_files 資料夾裡的所有檔案",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },

    # ── 應用程式 ──────────────────────────────────────────────────────
    {
        "name": "open_application",
        "description": (
            "開啟電腦上的程式或網址。"
            "支援模糊名稱（打 chrome 會找到 Google Chrome）。"
            "如果電腦沒安裝，會回傳官方下載連結。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "程式名稱或網址，例如：chrome、記事本、spotify、op.gg"}
            },
            "required": ["target"]
        }
    },
    {
        "name": "search_installed_apps",
        "description": "搜尋電腦上已安裝的程式，回傳符合關鍵字的程式清單和路徑",
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜尋關鍵字"}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "list_running_apps",
        "description": "列出目前正在執行中的應用程式",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "close_application",
        "description": "關閉指定名稱的應用程式（支援模糊名稱）",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "要關閉的程式名稱"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "focus_application",
        "description": "把已開啟但最小化或被遮蓋的應用程式帶到最上層顯示",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "視窗標題或應用程式名稱，支援模糊比對"}
            },
            "required": ["name"]
        }
    },

    # ── 音量 ──────────────────────────────────────────────────────────
    {
        "name": "set_volume",
        "description": "控制電腦音量：設定數值、調大調小、靜音、查詢目前音量",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "動作：set / up / down / mute / unmute / get"
                },
                "value": {
                    "type": "integer",
                    "description": "音量值 0~100（set 時必填）；up/down 時代表幅度（預設 10）"
                }
            },
            "required": ["action"]
        }
    },

    # ── 截圖 / 滑鼠 / 鍵盤 ───────────────────────────────────────────
    {
        "name": "take_screenshot",
        "description": "截取目前螢幕畫面，儲存到 agent_files",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "截圖檔名，預設自動命名"}
            },
            "required": []
        }
    },
    {
        "name": "mouse_action",
        "description": "控制滑鼠：移動、點擊、雙擊、右鍵",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "move / click / double_click / right_click"},
                "x":      {"type": "integer", "description": "螢幕 X 座標"},
                "y":      {"type": "integer", "description": "螢幕 Y 座標"}
            },
            "required": ["action", "x", "y"]
        }
    },
    {
        "name": "keyboard_type",
        "description": (
            "鍵盤輸入文字或按下組合鍵。"
            "【重要】如果使用者要求「寫文件」、「記錄內容」、「儲存文字」，"
            "請優先用 write_file 存成檔案，不要用這個工具。"
            "只有在使用者明確說「直接輸入到視窗」或「貼到應用程式」時才使用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text":     {"type": "string", "description": "要輸入的文字"},
                "hotkey":   {"type": "string", "description": "組合鍵，例如 ctrl+c"},
                "interval": {"type": "number",  "description": "輸入間隔秒數，預設 0.05"}
            },
            "required": []
        }
    },

    # ── Shell ─────────────────────────────────────────────────────────
    {
        "name": "run_shell",
        "description": "執行 shell / PowerShell 指令。危險指令會被自動拒絕。",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要執行的指令"}
            },
            "required": ["command"]
        }
    },

    # ── 直播監控 ─────────────────────────────────────────────────────
    {
        "name": "add_stream_channel",
        "description": "新增要監控的直播頻道，開播時會推播 Telegram 通知",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "description": "平台：twitch 或 youtube"},
                "channel":  {"type": "string", "description": "Twitch 頻道名稱 或 YouTube Channel ID"}
            },
            "required": ["platform", "channel"]
        }
    },
    {
        "name": "remove_stream_channel",
        "description": "移除直播監控頻道",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "description": "平台：twitch 或 youtube"},
                "channel":  {"type": "string", "description": "頻道名稱或 ID"}
            },
            "required": ["platform", "channel"]
        }
    },
    {
        "name": "list_stream_channels",
        "description": "列出所有正在監控的直播頻道",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },

    # ── 瀏覽器控制 ───────────────────────────────────────────────────
    {
        "name": "browser_open",
        "description": "用瀏覽器開啟指定網址",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要開啟的網址"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "browser_read",
        "description": "讀取目前瀏覽器網頁的文字內容",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "browser_search",
        "description": "用真實瀏覽器搜尋，結果比 API 搜尋更完整",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜尋關鍵字"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "browser_click",
        "description": "點擊網頁元素，可用 CSS selector 或 text=文字",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector 或 text=按鈕文字"}
            },
            "required": ["selector"]
        }
    },
    {
        "name": "browser_fill",
        "description": "在網頁輸入框填入文字",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "輸入框的 CSS selector"},
                "value":    {"type": "string", "description": "要填入的文字"}
            },
            "required": ["selector", "value"]
        }
    },
    {
        "name": "browser_screenshot",
        "description": "截取目前網頁完整截圖，儲存到 agent_files",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "截圖檔名，預設自動命名"}
            },
            "required": []
        }
    },
    {
        "name": "browser_current_url",
        "description": "取得目前瀏覽器的網址和標題",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "browser_close",
        "description": "關閉瀏覽器",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },

    # ── Gmail ─────────────────────────────────────────────────────────
    {
        "name": "check_inbox",
        "description": "檢查 Gmail 收件匣，自動過濾廣告信",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "最多查幾封，預設 10"},
                "unread_only": {"type": "boolean", "description": "只看未讀，預設 true"}
            },
            "required": []
        }
    },
    {
        "name": "read_email",
        "description": "讀取特定信件的完整內容",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "信件 ID（從 check_inbox 取得）"}
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "send_email",
        "description": "寄送新的電子郵件",
        "input_schema": {
            "type": "object",
            "properties": {
                "to":      {"type": "string", "description": "收件人 email"},
                "subject": {"type": "string", "description": "郵件主旨"},
                "body":    {"type": "string", "description": "郵件內文"},
                "cc":      {"type": "string", "description": "副本收件人（選填）"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "reply_email",
        "description": "回覆某封信件",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "要回覆的信件 ID"},
                "body":       {"type": "string", "description": "回覆內容"}
            },
            "required": ["message_id", "body"]
        }
    },
    {
        "name": "move_to_trash",
        "description": "把指定信件移到垃圾桶",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "要刪除的信件 ID"}
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "mark_as_read",
        "description": "把指定信件標記為已讀",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "信件 ID"}
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "mark_as_unread",
        "description": "把指定信件標記為未讀",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "信件 ID"}
            },
            "required": ["message_id"]
        }
    },

    # ── 自動研究 ─────────────────────────────────────────────────────
    {
        "name": "research_topic",
        "description": "給一個主題，自動上網搜尋並整理存入知識庫",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "要研究的主題"},
                "depth": {"type": "integer", "description": "搜尋深度 1~5，預設 3"}
            },
            "required": ["topic"]
        }
    },

    # ── 知識庫（RAG）─────────────────────────────────────────────────
    {
        "name": "import_document",
        "description": "把本機文件（.txt / .md / .pdf）匯入知識庫",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string", "description": "文件完整路徑"},
                "source_name": {"type": "string", "description": "文件名稱標籤（選填）"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "import_text_to_knowledge",
        "description": "把一段文字直接加入知識庫",
        "input_schema": {
            "type": "object",
            "properties": {
                "content":     {"type": "string", "description": "要加入的文字內容"},
                "source_name": {"type": "string", "description": "內容的名稱標籤"}
            },
            "required": ["content", "source_name"]
        }
    },
    {
        "name": "list_knowledge_documents",
        "description": "列出知識庫裡有哪些文件",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "delete_knowledge_document",
        "description": "從知識庫刪除指定文件",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "要刪除的文件名稱"}
            },
            "required": ["source_name"]
        }
    },

    # ── 個人化設定 ────────────────────────────────────────────────────
    {
        "name": "get_persona",
        "description": "查看目前的個人化設定（稱呼、城市、語氣等）",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "update_persona",
        "description": "更新個人化設定，key 可以是 name（稱呼）/ city（城市）/ style（風格）/ language（語言）",
        "input_schema": {
            "type": "object",
            "properties": {
                "key":   {"type": "string", "description": "設定項目：name / city / style / language"},
                "value": {"type": "string", "description": "新的設定值"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "add_persona_instruction",
        "description": "新增額外的行為指示，例如「回覆要簡短」、「每次都問我需不需要記錄」",
        "input_schema": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "要新增的指示內容"}
            },
            "required": ["instruction"]
        }
    },

    # ── 記憶 ──────────────────────────────────────────────────────────
    {
        "name": "list_memories",
        "description": "列出 Agent 目前記住的所有關於你的資訊",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "clear_memories",
        "description": "清除所有記憶",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    
]

# ══════════════════════════════════════════════════════════════════════
# 敏感工具清單（雲端模型會被移除）
# ══════════════════════════════════════════════════════════════════════
PRIVATE_TOOLS = {
    "check_inbox", "read_email", "send_email", "reply_email", "move_to_trash","mark_as_read", "mark_as_unread",
    "list_memories", "clear_memories",
    "import_document", "import_text_to_knowledge",
    "list_knowledge_documents", "delete_knowledge_document",
    "browser_open", "browser_read", "browser_click", "browser_fill",
    "browser_screenshot", "browser_search", "browser_current_url", "browser_close",
    "run_shell", "write_file", "read_file",
}


def _get_safe_tools() -> list:
    """
    根據目前執行的 provider 和執行環境回傳安全工具清單。
    本地（ollama）：開放非容器停用的工具
    雲端：移除敏感工具
    容器模式：額外移除桌面控制工具
    """
    import os
    active = os.environ.get("_ACTIVE_PROVIDER", "ollama")

    # 合併需要停用的工具
    disabled = CONTAINER_DISABLED_TOOLS.copy()
    if active != "ollama":
        disabled = disabled | PRIVATE_TOOLS

    if not disabled:
        return TOOL_DEFINITIONS

    safe    = [t for t in TOOL_DEFINITIONS if t["name"] not in disabled]
    removed = [t["name"] for t in TOOL_DEFINITIONS if t["name"] in disabled]

    if _CONTAINER_MODE and CONTAINER_DISABLED_TOOLS:
        print(f"[Container] 容器模式，已停用桌面工具：{len(CONTAINER_DISABLED_TOOLS)} 個")
    if active != "ollama" and PRIVATE_TOOLS - CONTAINER_DISABLED_TOOLS:
        print(f"[Privacy] 雲端模型（{active}），已停用 {len(PRIVATE_TOOLS)} 個敏感工具")

    return safe


# ══════════════════════════════════════════════════════════════════════
# 統一呼叫入口
# ══════════════════════════════════════════════════════════════════════
TOOL_HANDLERS = {
    "get_current_time":          get_current_time,
    "get_system_info":           get_system_info,
    "get_weather":               get_weather,
    "web_search":                web_search,
    "write_file":                write_file,
    "read_file":                 read_file,
    "list_files":                list_files,
    "open_application":          open_application,
    "search_installed_apps":     search_installed_apps,
    "list_running_apps":         list_running_apps,
    "close_application":         close_application,
    "focus_application":         focus_application,
    "set_volume":                set_volume,
    "take_screenshot":           take_screenshot,
    "mouse_action":              mouse_action,
    "keyboard_type":             keyboard_type,
    "run_shell":                 run_shell,
    "add_stream_channel":        add_stream_channel,
    "remove_stream_channel":     remove_stream_channel,
    "list_stream_channels":      list_stream_channels,
    "browser_open":              browser_open,
    "browser_read":              browser_read,
    "browser_search":            browser_search,
    "browser_click":             browser_click,
    "browser_fill":              browser_fill,
    "browser_screenshot":        browser_screenshot,
    "browser_current_url":       browser_current_url,
    "browser_close":             browser_close,
    "check_inbox":               check_inbox,
    "read_email":                read_email,
    "send_email":                send_email,
    "reply_email":               reply_email,
    "move_to_trash":             move_to_trash,
    "mark_as_read":              mark_as_read,
    "mark_as_unread":            mark_as_unread,
    "research_topic":            research_topic,
    "import_document":           import_document,
    "import_text_to_knowledge":  import_text_to_knowledge,
    "list_knowledge_documents":  list_knowledge_documents,
    "delete_knowledge_document": delete_knowledge_document,
    "get_persona":               get_persona,
    "update_persona":            update_persona,
    "add_persona_instruction":   add_persona_instruction,
    "list_memories":             list_memories,
    "clear_memories":            clear_memories,
}


def execute_tool(name: str, inputs: dict) -> str:
    import os
    active = os.environ.get("_ACTIVE_PROVIDER", "ollama")

    # 雲端模型嘗試呼叫敏感工具時直接拒絕（雙重保險）
    if active != "ollama" and name in PRIVATE_TOOLS:
        return (
            f"⛔ 工具「{name}」只在本地 Ollama 模式下可用，"
            f"目前使用 {active}，已拒絕以保護隱私"
        )

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"❌ 未知工具：{name}"
    try:
        return handler(**inputs)
    except Exception as e:
        return f"❌ 工具執行錯誤（{name}）：{e}"
