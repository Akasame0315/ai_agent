"""
緊急停止系統
路徑：core/emergency_stop.py

提供多種方式立即停止所有 Agent 動作：
1. Telegram /stop 指令
2. 鍵盤快捷鍵（Ctrl+Shift+F12）
3. 滑鼠移到左上角（pyautogui FailSafe）
"""
import asyncio
import threading
import pyautogui

# 全域停止旗標
_stop_event = threading.Event()
_async_stop_event: asyncio.Event = None


def get_stop_event() -> threading.Event:
    return _stop_event


def is_stopped() -> bool:
    return _stop_event.is_set()


def trigger_stop():
    """觸發緊急停止"""
    _stop_event.set()
    print("[EmergencyStop] 緊急停止已觸發！")

    # 同時停止所有 task_manager 的任務
    try:
        from core.task_manager import task_manager
        task_manager.cancel_all()
    except Exception:
        pass

    # 停止 pyautogui
    try:
        pyautogui.FAILSAFE = True
    except Exception:
        pass


def reset_stop():
    """重置停止旗標（重啟後呼叫）"""
    _stop_event.clear()
    print("[EmergencyStop] 停止旗標已重置")


def start_keyboard_listener():
    """
    背景監聽 Ctrl+Shift+F12 緊急停止快捷鍵
    在獨立 thread 跑，不阻塞主程式
    """
    def _listen():
        try:
            import keyboard
            keyboard.add_hotkey("ctrl+shift+f12", trigger_stop)
            keyboard.wait()
        except ImportError:
            print("[EmergencyStop] keyboard 套件未安裝，快捷鍵停止功能不可用")
            print("  安裝方式：pip install keyboard")
        except Exception as e:
            print(f"[EmergencyStop] 鍵盤監聽失敗：{e}")

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
