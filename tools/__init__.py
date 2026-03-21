"""
工具總入口：統一定義 + 統一呼叫
所有工具實作分散在子模組，這裡只做彙整。
"""

from tools.info   import (get_current_time, get_system_info,
                           get_weather, web_search,
                           write_file, read_file, list_files,
                           list_memories, clear_memories,
                           import_document, import_text_to_knowledge,
                           list_knowledge_documents, delete_knowledge_document,
                           research_topic)
from tools.apps   import (open_application, search_installed_apps,
                           list_running_apps, close_application)
from tools.system import (set_volume, take_screenshot,
                           mouse_action, keyboard_type, run_shell)

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
            "支援模糊名稱（打『chrome』會找到 Google Chrome）。"
            "如果電腦沒安裝，會回傳官方下載連結。"
            "也可以直接輸入網址（例如 op.gg、youtube.com）用瀏覽器開啟。"
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
                "name": {"type": "string", "description": "要關閉的程式名稱，例如：notepad、chrome"}
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
                    "description": "動作：set（設定）/ up（調大）/ down（調小）/ mute / unmute / get（查詢）"
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
        "description": "鍵盤輸入文字或按下組合鍵（例如 ctrl+c、alt+f4、win+d）",
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
        "description": (
            "執行 shell / PowerShell 指令。"
            "適合查系統資訊、管理檔案、執行腳本。"
            "危險指令會被自動拒絕。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要執行的指令"}
            },
            "required": ["command"]
        }
    },
    # ── 自動研究 ─────────────────────────────────────────────────────
    {
        "name": "research_topic",
        "description": (
            "給一個主題，自動上網搜尋多個角度並整理存入知識庫。"
            "之後問相關問題時會自動參考這份研究資料。"
            "例如：幫我研究 Python 非同步程式設計 / 幫我研究台北的美食推薦"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "要研究的主題"},
                "depth": {"type": "integer", "description": "搜尋深度 1~5，越高資料越豐富但越慢，預設 3"}
            },
            "required": ["topic"]
        }
    },

    # ── 知識庫（RAG）─────────────────────────────────────────────────
    {
        "name": "import_document",
        "description": "把本機的文件（.txt / .md / .pdf）匯入知識庫，之後問相關問題時會自動參考",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path":   {"type": "string", "description": "文件的完整路徑，例如 C:\\Users\\amber\\Documents\\note.txt"},
                "source_name": {"type": "string", "description": "這份文件的名稱標籤（選填，預設用檔名）"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "import_text_to_knowledge",
        "description": "把一段文字直接加入知識庫，適合從網頁複製的內容或手動輸入的資料",
        "input_schema": {
            "type": "object",
            "properties": {
                "content":     {"type": "string", "description": "要加入知識庫的文字內容"},
                "source_name": {"type": "string", "description": "這段內容的名稱標籤"}
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
        "description": "從知識庫刪除指定文件的所有內容",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_name": {"type": "string", "description": "要刪除的文件名稱標籤"}
            },
            "required": ["source_name"]
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
        "description": "清除所有記憶，讓 Agent 忘記之前記住的所有資訊",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },

]

# ══════════════════════════════════════════════════════════════════════
# 統一呼叫入口
# ══════════════════════════════════════════════════════════════════════
TOOL_HANDLERS = {
    "get_current_time":    get_current_time,
    "get_system_info":     get_system_info,
    "get_weather":         get_weather,
    "web_search":          web_search,
    "write_file":          write_file,
    "read_file":           read_file,
    "list_files":          list_files,
    "open_application":    open_application,
    "search_installed_apps": search_installed_apps,
    "list_running_apps":   list_running_apps,
    "close_application":   close_application,
    "set_volume":          set_volume,
    "take_screenshot":     take_screenshot,
    "mouse_action":        mouse_action,
    "keyboard_type":       keyboard_type,
    "run_shell":           run_shell,
    "list_memories":       list_memories,
    "clear_memories":      clear_memories,
    "research_topic":           research_topic,
    "import_document":          import_document,
    "import_text_to_knowledge": import_text_to_knowledge,
    "list_knowledge_documents": list_knowledge_documents,
    "delete_knowledge_document":delete_knowledge_document,
}

def execute_tool(name: str, inputs: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return f"❌ 未知工具：{name}"
    try:
        return handler(**inputs)
    except Exception as e:
        return f"❌ 工具執行錯誤（{name}）：{e}"
