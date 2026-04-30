"""
skills/system/system.py — 系統控制 Skill
路徑：skills/system/system.py

設計原則（非侵入式）：
  - 禁止模擬鍵盤滑鼠操作
  - 應用程式控制走 subprocess / os.startfile（Windows）
  - Shell 指令有黑名單過濾 + 15 秒 timeout
  - 所有寫入/執行操作設 requires_confirmation=True

工具：
  - open_application   : 開啟程式或網址（模糊比對）
  - close_application  : 關閉程式（taskkill）
  - list_running_apps  : 列出執行中應用程式
  - set_volume         : 音量調整（pycaw / PowerShell fallback）
  - take_screenshot    : 截圖存入 agent_files/
  - run_shell          : 執行 shell 指令（黑名單過濾）
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any

from skills.base import Skill

logger = logging.getLogger(__name__)

# ── Shell 危險指令黑名單 ───────────────────────────────────────────────
_SHELL_BLACKLIST: tuple[str, ...] = (
    "rm -rf /",
    "rm -rf ~",
    "rmdir /s /q c:\\",
    "format c:",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",
    "del /f /s /q c:\\",
    "rd /s /q c:\\",
    "shutdown /s",
    "shutdown -h",
)

# ── 系統內建別名（Windows）────────────────────────────────────────────
_BUILTIN_ALIASES: dict[str, str] = {
    "記事本": "notepad",
    "小算盤": "calc",
    "計算機": "calc",
    "小畫家": "mspaint",
    "檔案總管": "explorer",
    "命令提示字元": "cmd",
    "終端機": "wt",          # Windows Terminal
    "控制台": "control",
    "工作管理員": "taskmgr",
    "登錄編輯程式": "regedit",
}

_URL_SUFFIXES = {
    ".com", ".org", ".net", ".io", ".tw",
    ".co", ".app", ".dev", ".ai", ".tv",
    ".gov", ".edu",
}

_SCHEMAS: list[dict] = [
    {
        "name": "open_application",
        "description": (
            "開啟電腦上的應用程式或網址。"
            "支援模糊名稱（輸入 chrome 會找到 Google Chrome）。"
            "⚠️ 執行前需要 /confirm 確認。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "程式名稱或網址，例如：chrome、記事本、spotify、https://google.com",
                }
            },
            "required": ["target"],
        },
    },
    {
        "name": "close_application",
        "description": (
            "關閉指定名稱的應用程式（taskkill）。"
            "⚠️ 執行前需要 /confirm 確認。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "程式名稱，例如：notepad、chrome.exe",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_running_apps",
        "description": "列出目前正在執行中的應用程式",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "set_volume",
        "description": (
            "控制電腦音量：查詢、設定數值、調大調小、靜音/取消靜音。"
            "⚠️ 變更音量需要 /confirm 確認。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "動作：get（查詢）、set（設定）、up（調大）、down（調小）、mute（靜音）、unmute（取消靜音）",
                    "enum": ["get", "set", "up", "down", "mute", "unmute"],
                },
                "value": {
                    "type": "integer",
                    "description": "音量值 0~100（set 時必填）；up/down 時代表幅度（預設 10）",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "take_screenshot",
        "description": "截取目前螢幕畫面，儲存到 agent_files/ 資料夾",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "截圖檔名（選填，預設自動命名）",
                }
            },
            "required": [],
        },
    },
    {
        "name": "run_shell",
        "description": (
            "執行 shell 指令（Windows: PowerShell/cmd；macOS/Linux: bash）。"
            "危險指令會被自動拒絕。"
            "⚠️ 執行前需要 /confirm 確認。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要執行的指令",
                },
                "timeout": {
                    "type": "integer",
                    "description": "逾時秒數（預設 15，最多 60）",
                },
            },
            "required": ["command"],
        },
    },
]

# 查詢類工具不需要確認
_NO_CONFIRM_TOOLS = {"list_running_apps", "take_screenshot"}


class SystemSkill(Skill):
    """
    系統控制技能（非侵入式）。

    重要限制：
      - 不使用 pyautogui / keyboard 模擬輸入
      - 所有操作透過 API / subprocess / shell
      - 破壞性操作設 requires_confirmation=True
    """

    requires_confirmation = True
    privacy_level = "local_only"

    def __init__(self) -> None:
        self._files_dir = Path("agent_files")

    async def setup(self) -> None:
        self._files_dir.mkdir(parents=True, exist_ok=True)

    def get_schemas(self) -> list[dict]:
        return _SCHEMAS

    async def execute(self, tool_name: str, **kwargs: Any) -> str:
        match tool_name:
            case "open_application":
                return await self._open_application(kwargs.get("target", ""))
            case "close_application":
                return self._close_application(kwargs.get("name", ""))
            case "list_running_apps":
                return self._list_running_apps()
            case "set_volume":
                return self._set_volume(
                    kwargs.get("action", "get"),
                    kwargs.get("value", 10),
                )
            case "take_screenshot":
                return await self._take_screenshot(kwargs.get("filename", ""))
            case "run_shell":
                return await self._run_shell(
                    kwargs.get("command", ""),
                    kwargs.get("timeout", 15),
                )
            case _:
                raise ValueError(f"SystemSkill 未處理工具：{tool_name}")

    # ── 開啟應用程式 ──────────────────────────────────────────────────

    async def _open_application(self, target: str) -> str:
        if not target.strip():
            return "❌ 請提供程式名稱或網址"

        t = target.strip()

        # 1. 系統內建別名
        for alias, cmd in _BUILTIN_ALIASES.items():
            if alias in t or t.lower() == cmd.lower():
                try:
                    subprocess.Popen(cmd, shell=True)
                    return f"✅ 已開啟：{alias}"
                except Exception as e:
                    return f"❌ 開啟失敗：{e}"

        # 2. 網址
        is_url = (
            t.startswith("http://")
            or t.startswith("https://")
            or any(t.lower().endswith(s) for s in _URL_SUFFIXES)
        )
        if is_url:
            url = t if t.startswith("http") else f"https://{t}"
            webbrowser.open(url)
            return f"✅ 已用預設瀏覽器開啟：{url}"

        # 3. 本機路徑
        if os.path.exists(t):
            try:
                if sys.platform == "win32":
                    os.startfile(t)
                else:
                    subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", t])
                return f"✅ 已開啟：{os.path.basename(t)}"
            except Exception as e:
                return f"❌ 開啟失敗：{e}"

        # 4. Windows：用 Start Menu 模糊搜尋
        if sys.platform == "win32":
            result = await self._win_find_and_open(t)
            if result:
                return result

        # 5. 找不到
        search_url = f"https://www.google.com/search?q={t}+download+official"
        return (
            f"❌ 找不到「{t}」\n"
            f"可能尚未安裝，搜尋下載：{search_url}"
        )

    async def _win_find_and_open(self, keyword: str) -> str | None:
        """Windows：從 Start Menu 找捷徑並開啟"""
        start_dirs = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        ]
        kw_lower = keyword.lower()
        for start_dir in start_dirs:
            if not os.path.isdir(start_dir):
                continue
            for root, _, files in os.walk(start_dir):
                for file in files:
                    if file.lower().endswith(".lnk") and kw_lower in file.lower():
                        # 過濾卸載捷徑
                        if any(x in file.lower() for x in ["uninstall", "remove"]):
                            continue
                        lnk_path = os.path.join(root, file)
                        try:
                            os.startfile(lnk_path)
                            return f"✅ 已開啟：{os.path.splitext(file)[0]}"
                        except Exception:
                            continue
        return None

    # ── 關閉應用程式 ──────────────────────────────────────────────────

    def _close_application(self, name: str) -> str:
        if not name.strip():
            return "❌ 請提供程式名稱"
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    f'taskkill /f /im "{name}"',
                    shell=True, capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return f"✅ 已關閉：{name}"
                # 模糊比對
                result2 = subprocess.run(
                    f'taskkill /f /fi "IMAGENAME eq *{name}*"',
                    shell=True, capture_output=True, text=True, timeout=10,
                )
                if result2.returncode == 0:
                    return f"✅ 已關閉包含「{name}」的程式"
                return f"❌ 找不到執行中的程式：{name}"
            else:
                result = subprocess.run(
                    ["pkill", "-f", name],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return f"✅ 已關閉：{name}"
                return f"❌ 找不到執行中的程式：{name}"
        except Exception as e:
            return f"❌ 關閉失敗：{e}"

    # ── 列出執行中程式 ────────────────────────────────────────────────

    def _list_running_apps(self) -> str:
        try:
            import psutil  # type: ignore
            _SYSTEM_PROCS = {
                "svchost.exe", "system", "registry", "smss.exe",
                "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
                "fontdrvhost.exe", "dwm.exe", "sihost.exe", "taskhostw.exe",
                "idle", "kernel_task",
            }
            apps: list[str] = []
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    name = proc.info["name"] or ""
                    if name.lower() not in _SYSTEM_PROCS and name:
                        apps.append(f"  - {name} (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if not apps:
                return "📋 找不到執行中的應用程式"
            apps = sorted(set(apps))[:40]
            return f"🖥 執行中的應用程式（前 {len(apps)} 個）：\n" + "\n".join(apps)

        except ImportError:
            # psutil 未安裝，用 tasklist
            if sys.platform == "win32":
                result = subprocess.run(
                    "tasklist /fo csv /nh",
                    shell=True, capture_output=True, text=True, timeout=10,
                )
                lines = []
                for line in result.stdout.strip().split("\n")[:30]:
                    parts = line.strip('"').split('","')
                    if parts and parts[0]:
                        lines.append(f"  - {parts[0]}")
                return "🖥 執行中的程式：\n" + "\n".join(lines)
            return "❌ 請安裝 psutil：pip install psutil"

    # ── 音量控制 ──────────────────────────────────────────────────────

    def _set_volume(self, action: str, value: int = 10) -> str:
        # 優先用 pycaw（Windows，精確控制）
        if sys.platform == "win32":
            result = self._set_volume_pycaw(action, value)
            if result:
                return result
            # pycaw 失敗，fallback 到 PowerShell（不夠精確但至少能用）
            return self._set_volume_powershell(action, value)
        else:
            return self._set_volume_unix(action, value)

    def _set_volume_pycaw(self, action: str, value: int) -> str | None:
        try:
            import ctypes
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
            from comtypes import CLSCTX_ALL  # type: ignore

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
            current = round(vol.GetMasterVolumeLevelScalar() * 100)
            muted = vol.GetMute()

            match action:
                case "get":
                    return f"🔊 目前音量：{current}%{'（靜音中）' if muted else ''}"
                case "set":
                    t = max(0, min(100, int(value)))
                    vol.SetMasterVolumeLevelScalar(t / 100, None)
                    return f"✅ 音量已設定為 {t}%"
                case "up":
                    t = max(0, min(100, current + int(value)))
                    vol.SetMasterVolumeLevelScalar(t / 100, None)
                    return f"✅ 音量調大到 {t}%"
                case "down":
                    t = max(0, min(100, current - int(value)))
                    vol.SetMasterVolumeLevelScalar(t / 100, None)
                    return f"✅ 音量調小到 {t}%"
                case "mute":
                    vol.SetMute(1, None)
                    return "✅ 已靜音"
                case "unmute":
                    vol.SetMute(0, None)
                    return f"✅ 已取消靜音，目前音量 {current}%"
                case _:
                    return None
        except ImportError:
            return None
        except Exception as e:
            logger.warning(f"[SystemSkill] pycaw 失敗：{e}")
            return None

    def _set_volume_powershell(self, action: str, value: int) -> str:
        """Windows PowerShell fallback（音量控制較不精確）"""
        _PS = "powershell -Command"
        try:
            match action:
                case "get":
                    r = subprocess.run(
                        f'{_PS} "(Get-AudioDevice -playback).DefaultAudioEndpointVolume"',
                        shell=True, capture_output=True, text=True, timeout=5,
                    )
                    return f"🔊 音量：{r.stdout.strip() or '（無法取得）'}"
                case "mute":
                    code = "[char]173"
                    subprocess.run(
                        f'{_PS} "$s = New-Object -ComObject WScript.Shell; $s.SendKeys([char]173)"',
                        shell=True, timeout=5,
                    )
                    return "✅ 已切換靜音狀態"
                case _:
                    return f"❌ PowerShell fallback 不支援 {action!r} 動作，請安裝 pycaw"
        except Exception as e:
            return f"❌ 音量控制失敗：{e}\n提示：Windows 上請安裝 pycaw：pip install pycaw"

    def _set_volume_unix(self, action: str, value: int) -> str:
        """macOS / Linux 音量控制"""
        try:
            if sys.platform == "darwin":
                if action == "get":
                    r = subprocess.run(
                        ["osascript", "-e", "output volume of (get volume settings)"],
                        capture_output=True, text=True, timeout=5,
                    )
                    return f"🔊 目前音量：{r.stdout.strip()}%"
                elif action == "set":
                    subprocess.run(
                        ["osascript", "-e", f"set volume output volume {value}"],
                        timeout=5,
                    )
                    return f"✅ 音量已設定為 {value}%"
                elif action == "mute":
                    subprocess.run(
                        ["osascript", "-e", "set volume with output muted"],
                        timeout=5,
                    )
                    return "✅ 已靜音"
                elif action == "unmute":
                    subprocess.run(
                        ["osascript", "-e", "set volume without output muted"],
                        timeout=5,
                    )
                    return "✅ 已取消靜音"
            else:
                # Linux amixer
                if action == "set":
                    subprocess.run(
                        ["amixer", "-q", "sset", "Master", f"{value}%"],
                        timeout=5,
                    )
                    return f"✅ 音量已設定為 {value}%"
                elif action == "mute":
                    subprocess.run(
                        ["amixer", "-q", "sset", "Master", "mute"],
                        timeout=5,
                    )
                    return "✅ 已靜音"
        except Exception as e:
            return f"❌ 音量控制失敗：{e}"
        return f"❌ 不支援的 action：{action}"

    # ── 截圖 ──────────────────────────────────────────────────────────

    async def _take_screenshot(self, filename: str = "") -> str:
        if not filename:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{ts}.png"

        path = self._files_dir / filename
        try:
            import mss  # type: ignore
            with mss.mss() as sct:
                sct.shot(output=str(path))
            size = path.stat().st_size
            return f"✅ 截圖已儲存：{filename}（{size:,} bytes）"
        except ImportError:
            pass

        try:
            import pyautogui  # type: ignore
            pyautogui.screenshot(str(path))
            size = path.stat().st_size
            return f"✅ 截圖已儲存：{filename}（{size:,} bytes）"
        except ImportError:
            return (
                "❌ 截圖需要安裝：\n"
                "  pip install mss\n"
                "或\n"
                "  pip install pyautogui pillow"
            )
        except Exception as e:
            return f"❌ 截圖失敗：{e}"

    # ── Shell 執行 ────────────────────────────────────────────────────

    async def _run_shell(self, command: str, timeout: int = 15) -> str:
        if not command.strip():
            return "❌ 指令不得為空"

        # 黑名單檢查
        cmd_lower = command.lower()
        for blocked in _SHELL_BLACKLIST:
            if blocked.lower() in cmd_lower:
                logger.warning(f"[SystemSkill] 拒絕危險指令：{command!r}")
                return f"⛔ 拒絕執行危險指令：{command}"

        timeout = max(1, min(timeout, 60))

        try:
            # 使用 asyncio subprocess，不阻塞 event loop
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    executable="/bin/bash",
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout)
                )
            except asyncio.TimeoutError:
                proc.kill()
                return f"⏱ 指令執行逾時（{timeout}s）：{command}"

            output = (stdout or b"").decode("utf-8", errors="replace").strip()
            err_out = (stderr or b"").decode("utf-8", errors="replace").strip()
            combined = output or err_out or "（無輸出）"

            if len(combined) > 2000:
                combined = combined[:2000] + "\n...（輸出過長，已截斷）"

            status = "✅" if proc.returncode == 0 else "⚠️"
            return (
                f"{status} 執行：{command}\n"
                f"退出碼：{proc.returncode}\n\n"
                f"{combined}"
            )

        except Exception as e:
            logger.exception(f"[SystemSkill] run_shell 失敗：{command}")
            return f"❌ 執行失敗：{e}"


SKILL_CLASS = SystemSkill
