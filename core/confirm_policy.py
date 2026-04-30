"""
core/confirm_policy.py — 工具確認策略
路徑：core/confirm_policy.py

集中定義哪些工具呼叫需要 /confirm 確認，而不是依賴 skill 的 class 屬性。

好處：
  - 查詢類操作（read_file、list_files）即使在 requires_confirmation=True 的 skill
    裡也可以直接執行，不打斷使用者
  - 需要確認的工具清單一目了然，易於維護

使用方式：
    from core.confirm_policy import needs_confirmation
    if needs_confirmation(tool_name, arguments):
        # 暫停，等待 /confirm
"""
from __future__ import annotations

# ── 永遠需要確認的工具 ────────────────────────────────────────────────
# 這些工具無論如何都要等 /confirm
_ALWAYS_CONFIRM: frozenset[str] = frozenset({
    # 檔案寫入/刪除
    "write_file",
    "delete_file",
    # 應用程式控制
    "open_application",
    "close_application",
    # 系統設定變更
    "set_volume",
    # Shell 執行
    "run_shell",
    # Gmail 操作（Phase 5）
    "send_email",
    "reply_email",
    "move_to_trash",
})

# ── 永遠不需要確認的工具（純查詢） ────────────────────────────────────
_NEVER_CONFIRM: frozenset[str] = frozenset({
    "get_current_time",
    "get_system_info",
    "get_weather",
    "web_search",
    "read_file",
    "list_files",
    "list_running_apps",
    "take_screenshot",       # 截圖只記錄，不影響系統
    "check_inbox",           # 讀取信件（Phase 5）
    "read_email",
    "list_reminders",
    "list_stream_channels",
})


def needs_confirmation(tool_name: str, arguments: dict | None = None) -> bool:
    """
    判斷指定工具呼叫是否需要使用者確認。

    Args:
        tool_name:  工具名稱
        arguments:  工具參數（預留，目前未使用，未來可依參數值判斷）

    Returns:
        True  → 需要 /confirm
        False → 直接執行
    """
    if tool_name in _NEVER_CONFIRM:
        return False
    if tool_name in _ALWAYS_CONFIRM:
        return True
    # 預設：不確定的工具需要確認（安全優先）
    return True
