"""
個人化設定檔
路徑：core/persona.py

儲存使用者的個人偏好：稱呼、城市、語氣等。
存在本地 persona.json，不會上傳到任何雲端。
"""
import json
import os
from core.paths import PERSONA_FILE

# 預設值
DEFAULT_PERSONA = {
    "name":        "老闆",          # Agent 稱呼你的方式
    "city":        "新北市",              # 居住城市（天氣查詢用）
    "style":       "專業但友善，像個人助理",  # 回覆風格
    "language":    "繁體中文",
    "extra":       [],              # 額外指示，例如「回覆要簡短」
}


def load() -> dict:
    """載入個人化設定"""
    if not os.path.exists(PERSONA_FILE):
        save(DEFAULT_PERSONA)
        return DEFAULT_PERSONA.copy()
    try:
        with open(PERSONA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 補上新版本可能新增的欄位
        for k, v in DEFAULT_PERSONA.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return DEFAULT_PERSONA.copy()


def save(persona: dict) -> None:
    """儲存個人化設定"""
    with open(PERSONA_FILE, "w", encoding="utf-8") as f:
        json.dump(persona, f, ensure_ascii=False, indent=2)


def update(key: str, value) -> str:
    """更新單一設定項目"""
    persona = load()
    if key not in DEFAULT_PERSONA:
        return f"❌ 未知的設定項目：{key}"
    persona[key] = value
    save(persona)
    return f"✅ 已更新：{key} = {value}"


def build_system_prompt(base_prompt: str) -> str:
    """
    把個人化設定注入 System Prompt。
    所有 LLM 模組都應該呼叫這個函式取得最終 prompt。
    """
    p = load()
    name  = p.get("name", "老闆")
    city  = p.get("city", "")
    style = p.get("style", "")
    lang  = p.get("language", "繁體中文")
    extra = p.get("extra", [])

    persona_block = f"""
【個人化設定】
- 請稱呼用戶為「{name}」
- 回覆語言：{lang}
- 回覆風格：{style}
"""
    if city:
        persona_block += f"- 用戶居住城市：{city}（天氣等查詢預設使用此城市）\n"
    if extra:
        persona_block += "- 額外指示：\n"
        for e in extra:
            persona_block += f"  • {e}\n"

    return base_prompt.strip() + "\n" + persona_block.strip()


def get_city() -> str:
    """快速取得城市設定"""
    return load().get("city", "")


def get_name() -> str:
    """快速取得稱呼設定"""
    return load().get("name", "老闆")
