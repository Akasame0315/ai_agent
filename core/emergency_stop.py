"""
緊急停止系統
路徑：core/emergency_stop.py

提供多種方式立即停止所有 Agent 動作：
1. Telegram /stop 指令
2. 鍵盤快捷鍵（Ctrl+Shift+F12）
3. 滑鼠移到左上角（pyautogui FailSafe）
"""
import threading
import os

_stop_event = threading.Event()

# 偵測是否在沙盒或容器環境
IS_SANDBOX = os.environ.get("SANDBOX_MODE", "0") == "1" or \
             os.environ.get("CONTAINER_MODE", "0") == "1"


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
    # 沙盒環境不需要 pyautogui
    if not IS_SANDBOX:
        try:
            import pyautogui # type: ignore
            pyautogui.FAILSAFE = True
        except ImportError:
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
    if IS_SANDBOX:
        print("[EmergencyStop] 沙盒模式，跳過鍵盤監聽")
        return

    def _listen():
        try:
            import keyboard # type: ignore
            keyboard.add_hotkey("ctrl+shift+f12", trigger_stop)
            keyboard.wait()
        except ImportError:
            print("[EmergencyStop] keyboard 套件未安裝，快捷鍵停止不可用")
            print("  安裝方式：pip install keyboard")
        except Exception as e:
            print(f"[EmergencyStop] 鍵盤監聽失敗：{e}")

    t = threading.Thread(target=_listen, daemon=True)
    t.start()