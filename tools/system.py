"""
系統控制工具：音量、截圖、滑鼠、鍵盤、Shell
"""
import datetime
import os
import re
import subprocess

FILES_DIR = "agent_files"


# ── 音量控制 ──────────────────────────────────────────────────────────
def set_volume(action: str, value: int = 10) -> str:
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        import ctypes

        devices   = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol       = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        current   = round(vol.GetMasterVolumeLevelScalar() * 100)

        if action == "get":
            muted = vol.GetMute()
            return f"🔊 目前音量：{current}%{'（靜音中）' if muted else ''}"
        elif action == "set":
            t = max(0, min(100, int(value)))
            vol.SetMasterVolumeLevelScalar(t / 100, None)
            return f"✅ 音量已設定為 {t}%"
        elif action == "up":
            t = max(0, min(100, current + int(value)))
            vol.SetMasterVolumeLevelScalar(t / 100, None)
            return f"✅ 音量調大到 {t}%"
        elif action == "down":
            t = max(0, min(100, current - int(value)))
            vol.SetMasterVolumeLevelScalar(t / 100, None)
            return f"✅ 音量調小到 {t}%"
        elif action == "mute":
            vol.SetMute(1, None)
            return "✅ 已靜音"
        elif action == "unmute":
            vol.SetMute(0, None)
            return f"✅ 已取消靜音，目前音量 {current}%"
        else:
            return f"❌ 未知動作：{action}"
    except ImportError:
        return "❌ 請先安裝：pip install pycaw comtypes"
    except Exception as e:
        return f"❌ 音量控制失敗：{e}"


# ── 截圖 ──────────────────────────────────────────────────────────────
def take_screenshot(filename: str = "") -> str:
    import pyautogui
    os.makedirs(FILES_DIR, exist_ok=True)
    if not filename:
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(FILES_DIR, filename)
    try:
        pyautogui.screenshot(path)
        abs_path = os.path.abspath(path)
        return f"✅ 截圖已儲存：{filename}\n完整路徑：{abs_path}"
    except Exception as e:
        return f"❌ 截圖失敗：{e}"


# ── 滑鼠控制 ──────────────────────────────────────────────────────────
def mouse_action(action: str, x: int, y: int) -> str:
    import pyautogui
    pyautogui.FAILSAFE = True
    try:
        if action == "move":
            pyautogui.moveTo(x, y, duration=0.3)
            return f"✅ 滑鼠移動到 ({x}, {y})"
        elif action == "click":
            pyautogui.click(x, y)
            return f"✅ 點擊 ({x}, {y})"
        elif action == "double_click":
            pyautogui.doubleClick(x, y)
            return f"✅ 雙擊 ({x}, {y})"
        elif action == "right_click":
            pyautogui.rightClick(x, y)
            return f"✅ 右鍵點擊 ({x}, {y})"
        else:
            return f"❌ 未知動作：{action}"
    except pyautogui.FailSafeException:
        return "⛔ 緊急停止（滑鼠移到左上角）"
    except Exception as e:
        return f"❌ 滑鼠操作失敗：{e}"


# ── 鍵盤輸入 ──────────────────────────────────────────────────────────
def keyboard_type(text: str = "", hotkey: str = "", interval: float = 0.05) -> str:
    import pyautogui
    import time
    try:
        time.sleep(0.3)
        if hotkey:
            keys = [k.strip() for k in hotkey.lower().split("+")]
            pyautogui.hotkey(*keys)
            return f"✅ 按下：{hotkey}"
        elif text:
            pyautogui.write(text, interval=interval)
            return f"✅ 已輸入文字（{len(text)} 字元）"
        else:
            return "❌ 請提供 text 或 hotkey"
    except Exception as e:
        return f"❌ 鍵盤操作失敗：{e}"


# ── Shell 執行 ────────────────────────────────────────────────────────
_SHELL_BLACKLIST = [
    "rm -rf /", "rmdir /s /q c:\\",
    "format c:", "mkfs", "dd if=/dev/zero",
    ":(){:|:&};:",
]

def run_shell(command: str) -> str:
    cmd_lower = command.lower()
    for blocked in _SHELL_BLACKLIST:
        if blocked in cmd_lower:
            return f"⛔ 拒絕執行危險指令：{command}"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=15, encoding="utf-8", errors="replace"
        )
        output = result.stdout.strip() or result.stderr.strip() or "（無輸出）"
        if len(output) > 1500:
            output = output[:1500] + "\n...（輸出過長，已截斷）"
        return f"💻 執行：{command}\n\n{output}"
    except subprocess.TimeoutExpired:
        return f"⏱ 指令超時（15秒）：{command}"
    except Exception as e:
        return f"❌ 執行失敗：{e}"
