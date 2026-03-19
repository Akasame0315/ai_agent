"""
應用程式控制工具
- 模糊搜尋已安裝的程式（登錄檔 + Program Files）
- 智慧開啟（程式名稱 / 網址 / 系統內建）
- 列出執行中程式、關閉程式
"""
import os
import re
import subprocess
import winreg
import webbrowser
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# 常用系統內建指令別名（不需要完整路徑）
# ══════════════════════════════════════════════════════════════════════
BUILTIN_ALIASES = {
    "記事本": "notepad",
    "小算盤": "calc",
    "計算機": "calc",
    "小畫家": "mspaint",
    "畫圖": "mspaint",
    "檔案總管": "explorer",
    "命令提示字元": "cmd",
    "終端機": "cmd",
    "控制台": "control",
    "工作管理員": "taskmgr",
    "登錄編輯程式": "regedit",
    "桌面": "explorer shell:Desktop",
    "下載": "explorer shell:Downloads",
    "文件": "explorer shell:Personal",
}

# 網址判斷用的域名後綴
URL_SUFFIXES = {".com", ".org", ".net", ".io", ".tw",
                ".co", ".app", ".dev", ".ai", ".tv"}


# ══════════════════════════════════════════════════════════════════════
# 搜尋已安裝程式
# ══════════════════════════════════════════════════════════════════════

def _search_registry(keyword: str) -> list[dict]:
    """從 Windows 登錄檔找已安裝程式"""
    results = []
    keyword_lower = keyword.lower()

    reg_paths = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, path in reg_paths:
        try:
            key = winreg.OpenKey(hive, path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub_key_name = winreg.EnumKey(key, i)
                    sub_key = winreg.OpenKey(key, sub_key_name)

                    def _get(name):
                        try:
                            return winreg.QueryValueEx(sub_key, name)[0]
                        except Exception:
                            return ""

                    display_name    = _get("DisplayName")
                    install_loc     = _get("InstallLocation")
                    display_icon    = _get("DisplayIcon")

                    if not display_name:
                        continue
                    if keyword_lower not in display_name.lower():
                        continue

                    # 嘗試找到可執行檔路徑
                    exe_path = ""
                    if display_icon:
                        # DisplayIcon 通常是 "C:\path\to\app.exe,0"
                        icon_path = display_icon.split(",")[0].strip('"')
                        if icon_path.endswith(".exe") and os.path.exists(icon_path):
                            exe_path = icon_path
                    if not exe_path and install_loc and os.path.isdir(install_loc):
                        # 在安裝目錄裡找 .exe
                        for f in Path(install_loc).glob("*.exe"):
                            exe_path = str(f)
                            break

                    results.append({
                        "name": display_name,
                        "exe":  exe_path,
                        "loc":  install_loc,
                    })
                except Exception:
                    continue
        except Exception:
            continue

    return results


def _search_start_menu(keyword: str) -> list[dict]:
    """從 Start Menu 捷徑找程式（速度最快）"""
    results = []
    keyword_lower = keyword.lower()

    start_dirs = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    ]

    for start_dir in start_dirs:
        if not os.path.isdir(start_dir):
            continue
        for lnk in Path(start_dir).rglob("*.lnk"):
            if keyword_lower in lnk.stem.lower():
                results.append({
                    "name": lnk.stem,
                    "exe":  str(lnk),   # 用捷徑路徑直接開啟
                    "loc":  "",
                })

    return results


def find_installed_apps(keyword: str) -> list[dict]:
    """綜合搜尋：登錄檔 + Start Menu，去重後回傳"""
    seen_names = set()
    combined   = []

    # Start Menu 先找（有捷徑代表可以直接啟動）
    for r in _search_start_menu(keyword):
        key = r["name"].lower()
        if key not in seen_names:
            seen_names.add(key)
            combined.append(r)

    # 再用登錄檔補充（有 exe 路徑的優先）
    for r in _search_registry(keyword):
        key = r["name"].lower()
        if key not in seen_names:
            seen_names.add(key)
            combined.append(r)

    # 有 exe 的排前面
    combined.sort(key=lambda x: 0 if x["exe"] else 1)
    return combined


# ══════════════════════════════════════════════════════════════════════
# Tool 實作
# ══════════════════════════════════════════════════════════════════════

# """
# 智慧開啟程式或網址：
# 1. 系統內建別名（記事本、小算盤…）
# 2. 網址 → 瀏覽器
# 3. 模糊比對已安裝程式
# 4. 都找不到 → 回傳搜尋下載連結
# """
def open_application(target: str) -> str:
    # ── 1. 系統內建別名 ──────────────────────────────────────────────
    for alias, cmd in BUILTIN_ALIASES.items():
        if alias in target or target.lower() in cmd.lower():
            subprocess.Popen(cmd, shell=True)
            return f"✅ 已開啟：{alias}"

    # ── 2. 網址判斷 ──────────────────────────────────────────────────
    t = target.strip()
    is_url = (
        t.startswith("http://") or
        t.startswith("https://") or
        any(t.lower().endswith(s) for s in URL_SUFFIXES) or
        ("." in t and " " not in t and len(t.split(".")) >= 2)
    )
    if is_url:
        url = t if t.startswith("http") else "https://" + t
        webbrowser.open(url)
        return f"✅ 已用瀏覽器開啟：{url}"

    # ── 3. 模糊比對已安裝程式 ────────────────────────────────────────
    apps = find_installed_apps(target)

    EXCLUDE_KEYWORDS = ["uninstall", "解除安裝", "remove", "uninst"]
    filtered = [
        a for a in apps
        if not any(kw in a["name"].lower() for kw in EXCLUDE_KEYWORDS)
    ]
    # 過濾後如果還有結果就用過濾後的，否則用原始結果
    apps = filtered if filtered else apps

    if apps:
        best = apps[0]
        launch_target = best["exe"] or best["name"]

        print(f"[APP] 準備開啟：{best['name']} → {launch_target}")

        try:
            if launch_target.lower().endswith(".lnk"):
                os.startfile(launch_target)
            else:
                subprocess.Popen(f'"{launch_target}"', shell=True)
            return f"✅ 已開啟：{best['name']}"
        except Exception as e:
            return f"❌ 找到程式但開啟失敗：{best['name']}\n   錯誤：{e}"

    # ── 4. 找不到 → 回傳下載搜尋建議 ────────────────────────────────
    search_url = f"https://www.google.com/search?q={target}+official+download+site"
    return (
        f"❌ 電腦上找不到「{target}」\n\n"
        f"可能未安裝，官方下載搜尋：\n"
        f"🔗 {search_url}"
    )

def search_installed_apps(keyword: str) -> str:
    """列出符合關鍵字的已安裝程式"""
    apps = find_installed_apps(keyword)
    if not apps:
        return f"🔍 找不到包含「{keyword}」的已安裝程式"

    lines = [f"🔍 找到 {len(apps)} 個符合「{keyword}」的程式："]
    for i, app in enumerate(apps[:10], 1):
        exe_info = f"\n   路徑：{app['exe']}" if app["exe"] else ""
        lines.append(f"{i}. {app['name']}{exe_info}")

    return "\n".join(lines)


def list_running_apps() -> str:
    """列出目前執行中有視窗的應用程式"""
    try:
        import psutil
        apps = []
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                name = proc.info["name"]
                pid  = proc.info["pid"]
                if name and not name.lower() in {
                    "svchost.exe", "system", "registry", "smss.exe",
                    "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
                    "fontdrvhost.exe", "dwm.exe", "sihost.exe", "taskhostw.exe"
                }:
                    apps.append(f"  - {name} (PID: {pid})")
            except Exception:
                continue

        if not apps:
            return "📋 找不到執行中的應用程式"

        apps.sort()
        return "🖥 執行中的應用程式：\n" + "\n".join(apps[:40])

    except ImportError:
        # psutil 沒裝就用 tasklist
        result = subprocess.run(
            "tasklist /fo csv /nh",
            shell=True, capture_output=True, text=True, timeout=10
        )
        lines = []
        for line in result.stdout.strip().split("\n")[:30]:
            parts = line.strip('"').split('","')
            if parts:
                lines.append(f"  - {parts[0]}")
        return "🖥 執行中的程式：\n" + "\n".join(lines)


def close_application(name: str) -> str:
    """關閉指定名稱的應用程式"""
    try:
        result = subprocess.run(
            f'taskkill /f /im "{name}"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return f"✅ 已關閉：{name}"
        # 嘗試模糊比對
        result2 = subprocess.run(
            f'taskkill /f /fi "IMAGENAME eq *{name}*"',
            shell=True, capture_output=True, text=True, timeout=10
        )
        if result2.returncode == 0:
            return f"✅ 已關閉包含「{name}」的程式"
        return f"❌ 找不到執行中的程式：{name}"
    except Exception as e:
        return f"❌ 關閉失敗：{e}"
