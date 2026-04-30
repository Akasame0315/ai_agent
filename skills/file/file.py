"""
skills/file/file.py — 檔案操作 Skill
路徑：skills/file/file.py

安全設計：
  - 所有操作限制在 agent_files/ 目錄內（路徑穿越檢查）
  - 寫入與刪除操作設定 requires_confirmation=True
  - 讀取與列出不需確認（純查詢）
  - privacy_level="local_only" 強制走本地 Ollama

工具：
  - write_file  : 寫入（或追加）檔案，needs /confirm
  - read_file   : 讀取檔案內容
  - list_files  : 列出所有檔案
  - delete_file : 刪除檔案，needs /confirm
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from skills.base import Skill

logger = logging.getLogger(__name__)

_SCHEMAS: list[dict] = [
    {
        "name": "write_file",
        "description": (
            "將內容寫入 agent_files/ 資料夾中的檔案。"
            "若檔案已存在則覆蓋；mode='append' 可追加內容。"
            "⚠️ 執行前需要 /confirm 確認。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "檔案名稱（不含路徑），例如：notes.txt、report.md",
                },
                "content": {
                    "type": "string",
                    "description": "要寫入的文字內容",
                },
                "mode": {
                    "type": "string",
                    "description": "'write'（預設，覆蓋）或 'append'（追加）",
                    "enum": ["write", "append"],
                },
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "讀取 agent_files/ 資料夾中的檔案內容",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "要讀取的檔案名稱",
                }
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_files",
        "description": "列出 agent_files/ 資料夾中的所有檔案及其大小",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "delete_file",
        "description": (
            "刪除 agent_files/ 資料夾中的指定檔案。"
            "⚠️ 執行前需要 /confirm 確認，此操作不可撤銷。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "要刪除的檔案名稱",
                }
            },
            "required": ["filename"],
        },
    },
]

# 讀取類工具不需要確認，寫入/刪除需要
_READ_ONLY_TOOLS = {"read_file", "list_files"}


class FileSkill(Skill):
    """
    檔案操作技能。

    安全說明：
      - 所有路徑均限制在 agent_files/ 目錄內
      - 寫入與刪除操作設 requires_confirmation=True
        （Planner 會暫停等 /confirm）
    """

    # 整個 skill 標記需要確認（write/delete 才會進確認流程）
    # read/list 由 execute() 內部直接執行，不走確認
    requires_confirmation = True
    privacy_level = "local_only"

    def __init__(self) -> None:
        self._files_dir: Path = Path("agent_files")

    async def setup(self) -> None:
        self._files_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[FileSkill] agent_files 目錄：{self._files_dir.resolve()}")

    def get_schemas(self) -> list[dict]:
        return _SCHEMAS

    async def execute(self, tool_name: str, **kwargs: Any) -> str:
        # 讀取類操作不需確認，直接執行
        match tool_name:
            case "write_file":
                return self._write_file(
                    kwargs.get("filename", ""),
                    kwargs.get("content", ""),
                    kwargs.get("mode", "write"),
                )
            case "read_file":
                return self._read_file(kwargs.get("filename", ""))
            case "list_files":
                return self._list_files()
            case "delete_file":
                return self._delete_file(kwargs.get("filename", ""))
            case _:
                raise ValueError(f"FileSkill 未處理工具：{tool_name}")

    # ── 安全路徑解析 ──────────────────────────────────────────────────

    def _safe_path(self, filename: str) -> Path:
        """
        解析並驗證路徑安全性。
        防止路徑穿越攻擊（../../etc/passwd 等）。
        """
        if not filename or not filename.strip():
            raise ValueError("檔案名稱不得為空")

        # 只取檔名部分（去掉任何目錄成分）
        safe_name = Path(filename).name
        if not safe_name:
            raise ValueError(f"無效的檔案名稱：{filename!r}")

        # 禁止隱藏檔案（以 . 開頭）
        if safe_name.startswith("."):
            raise ValueError(f"不允許存取隱藏檔案：{safe_name!r}")

        resolved = (self._files_dir / safe_name).resolve()
        base = self._files_dir.resolve()

        # 確保解析後路徑仍在 agent_files/ 內
        if not str(resolved).startswith(str(base)):
            raise PermissionError(f"路徑穿越攻擊偵測：{filename!r}")

        return resolved

    # ── 工具實作 ──────────────────────────────────────────────────────

    def _write_file(self, filename: str, content: str, mode: str = "write") -> str:
        try:
            path = self._safe_path(filename)
            write_mode = "a" if mode == "append" else "w"
            with open(path, write_mode, encoding="utf-8") as f:
                f.write(content)
            size = path.stat().st_size
            action = "追加到" if mode == "append" else "寫入"
            return (
                f"✅ 已{action} {filename}\n"
                f"   路徑：{path}\n"
                f"   大小：{size:,} bytes"
            )
        except (ValueError, PermissionError) as e:
            return f"❌ 拒絕存取：{e}"
        except Exception as e:
            logger.exception(f"[FileSkill] write_file 失敗：{filename}")
            return f"❌ 寫入失敗：{e}"

    def _read_file(self, filename: str) -> str:
        try:
            path = self._safe_path(filename)
            if not path.exists():
                return f"❌ 找不到檔案：{filename}"
            content = path.read_text(encoding="utf-8", errors="replace")
            size = len(content)
            if size > 8000:
                content = content[:8000] + f"\n\n...（內容過長，已截斷，共 {size:,} 字元）"
            return f"📄 {filename}（{size:,} 字元）：\n\n{content}"
        except (ValueError, PermissionError) as e:
            return f"❌ 拒絕存取：{e}"
        except Exception as e:
            logger.exception(f"[FileSkill] read_file 失敗：{filename}")
            return f"❌ 讀取失敗：{e}"

    def _list_files(self) -> str:
        try:
            files = sorted(self._files_dir.iterdir())
            if not files:
                return "📂 agent_files/ 資料夾是空的"

            lines = [f"📂 agent_files/（共 {len(files)} 個檔案）：\n"]
            for f in files:
                if f.is_file():
                    size = f.stat().st_size
                    if size < 1024:
                        size_str = f"{size} B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / 1024 / 1024:.1f} MB"
                    lines.append(f"  📄 {f.name}  ({size_str})")
                elif f.is_dir():
                    lines.append(f"  📁 {f.name}/")
            return "\n".join(lines)
        except Exception as e:
            logger.exception("[FileSkill] list_files 失敗")
            return f"❌ 列出檔案失敗：{e}"

    def _delete_file(self, filename: str) -> str:
        try:
            path = self._safe_path(filename)
            if not path.exists():
                return f"❌ 找不到檔案：{filename}"
            size = path.stat().st_size
            path.unlink()
            return (
                f"🗑️ 已刪除：{filename}\n"
                f"   大小：{size:,} bytes"
            )
        except (ValueError, PermissionError) as e:
            return f"❌ 拒絕存取：{e}"
        except Exception as e:
            logger.exception(f"[FileSkill] delete_file 失敗：{filename}")
            return f"❌ 刪除失敗：{e}"


SKILL_CLASS = FileSkill
