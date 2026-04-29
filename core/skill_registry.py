"""
core/skill_registry.py — Skill 自動探索與分派
路徑：core/skill_registry.py

職責：
  1. 掃描 skills/ 目錄，讀取每個 skill 的 manifest.json
  2. 動態 import skill module，取得 Skill 子類別實例
  3. 收集所有工具 schema，提供給 Planner → LLMGateway
  4. 接收 LLM 的 tool call，找到對應 skill 並執行

使用方式（main.py）：
    registry = SkillRegistry()
    await registry.discover("skills/")          # 掃描並載入
    schemas = registry.get_all_schemas()        # 給 LLM 用
    result  = await registry.dispatch("get_weather", city="台北")  # 執行工具
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
from typing import Any

from skills.base import Skill

logger = logging.getLogger(__name__)


# manifest.json 必要欄位
_REQUIRED_MANIFEST_KEYS = {"id", "tools"}


class SkillLoadError(Exception):
    """Skill 載入失敗（manifest 格式錯誤、import 失敗等）"""


class SkillRegistry:
    """
    Skill 插件系統的核心。

    設計原則：
      - 一個工具名稱只能由一個 skill 負責（重複時後載入的 skill 會被跳過並警告）
      - Skill 本身不知道 Registry 的存在，保持解耦
      - privacy_level 資訊由 Registry 統一管理，Router 查詢用
    """

    def __init__(self) -> None:
        # skill_id → Skill 實例
        self._skills: dict[str, Skill] = {}
        # tool_name → skill_id（分派用）
        self._tool_map: dict[str, str] = {}
        # skill_id → manifest dict
        self._manifests: dict[str, dict] = {}

    # ── 載入 ─────────────────────────────────────────────────────────

    async def discover(self, skills_dir: str) -> None:
        """
        掃描 skills_dir 下的所有子資料夾，載入有效的 skill。
        可多次呼叫（重複 skill id 會被忽略）。
        """
        if not os.path.isdir(skills_dir):
            logger.warning(f"[Registry] skills 目錄不存在：{skills_dir}")
            return

        for entry in sorted(os.scandir(skills_dir), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            skill_dir = entry.path
            try:
                await self._load_skill(skill_dir)
            except SkillLoadError as e:
                logger.error(f"[Registry] 跳過 {entry.name}：{e}")
            except Exception as e:
                logger.exception(f"[Registry] 載入 {entry.name} 時發生未預期錯誤：{e}")

        logger.info(
            f"[Registry] 載入完成：{len(self._skills)} 個 skill，"
            f"{len(self._tool_map)} 個工具"
        )

    async def _load_skill(self, skill_dir: str) -> None:
        """載入單個 skill 資料夾"""
        skill_name = os.path.basename(skill_dir)

        # ── 讀取 manifest.json ────────────────────────────────────────
        manifest_path = os.path.join(skill_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise SkillLoadError("找不到 manifest.json")

        with open(manifest_path, "r", encoding="utf-8") as f:
            try:
                manifest = json.load(f)
            except json.JSONDecodeError as e:
                raise SkillLoadError(f"manifest.json 格式錯誤：{e}") from e

        # 檢查必要欄位
        missing = _REQUIRED_MANIFEST_KEYS - manifest.keys()
        if missing:
            raise SkillLoadError(f"manifest.json 缺少欄位：{missing}")

        skill_id = manifest["id"]

        # 已載入則跳過
        if skill_id in self._skills:
            logger.debug(f"[Registry] {skill_id} 已載入，跳過")
            return

        # 停用的 skill
        if not manifest.get("enabled", True):
            logger.info(f"[Registry] {skill_id} 已停用（manifest enabled=false），跳過")
            return

        # ── 動態 import skill module ──────────────────────────────────
        skill_instance = self._import_skill(skill_dir, skill_name, manifest)

        # ── 檢查工具名稱衝突 ─────────────────────────────────────────
        tool_names = manifest.get("tools", [])
        if not tool_names:
            logger.warning(f"[Registry] {skill_id} 的 manifest.tools 為空，此 skill 不提供任何工具")

        for tool_name in tool_names:
            if tool_name in self._tool_map:
                existing = self._tool_map[tool_name]
                logger.warning(
                    f"[Registry] 工具名稱衝突：{tool_name!r} 已被 {existing!r} 使用，"
                    f"跳過 {skill_id!r} 的此工具"
                )
            else:
                self._tool_map[tool_name] = skill_id

        # ── 呼叫 skill.setup() ────────────────────────────────────────
        await skill_instance.setup()

        # ── 存入 registry ─────────────────────────────────────────────
        self._skills[skill_id] = skill_instance
        self._manifests[skill_id] = manifest
        logger.info(f"[Registry] ✅ 已載入：{skill_id}（工具：{tool_names}）")

    def _import_skill(self, skill_dir: str, dir_name: str, manifest: dict) -> Skill:
        """
        動態 import skill module 並取得 Skill 實例。

        尋找 module 的順序：
          1. manifest["module"] 欄位指定的 .py 檔案
          2. 與資料夾同名的 .py 檔案（e.g. skills/weather/weather.py）
          3. skill_dir 下唯一的 .py 檔案
        """
        skill_id = manifest["id"]

        # 決定要 import 的檔案
        if "module" in manifest:
            module_file = os.path.join(skill_dir, manifest["module"])
        else:
            # 先找同名檔案
            default = os.path.join(skill_dir, f"{dir_name}.py")
            if os.path.isfile(default):
                module_file = default
            else:
                # 找唯一的 .py 檔
                py_files = [
                    f for f in os.listdir(skill_dir)
                    if f.endswith(".py") and f != "__init__.py"
                ]
                if len(py_files) == 1:
                    module_file = os.path.join(skill_dir, py_files[0])
                elif len(py_files) == 0:
                    raise SkillLoadError("找不到任何 .py 檔案")
                else:
                    raise SkillLoadError(
                        f"找到多個 .py 檔案，請在 manifest.json 指定 module 欄位：{py_files}"
                    )

        if not os.path.isfile(module_file):
            raise SkillLoadError(f"找不到 module 檔案：{module_file}")

        # 動態載入 module
        module_name = f"skills.{skill_id}.{os.path.splitext(os.path.basename(module_file))[0]}"
        spec = importlib.util.spec_from_file_location(module_name, module_file)
        if spec is None or spec.loader is None:
            raise SkillLoadError(f"無法載入 module：{module_file}")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as e:
            raise SkillLoadError(f"module 執行失敗：{e}") from e

        # 取得 Skill 實例
        # 優先找 SKILL_CLASS 變數；其次找繼承 Skill 的類別
        if hasattr(module, "SKILL_CLASS"):
            skill_cls = module.SKILL_CLASS
        else:
            candidates = [
                obj for obj in vars(module).values()
                if isinstance(obj, type)
                and issubclass(obj, Skill)
                and obj is not Skill
            ]
            if not candidates:
                raise SkillLoadError("找不到 Skill 子類別，請確認 module 內有繼承 Skill 的類別")
            if len(candidates) > 1:
                # 找和 skill_id 最相近的名稱
                best = next(
                    (c for c in candidates if c.__name__.lower().startswith(skill_id.lower())),
                    candidates[0]
                )
                logger.debug(f"[Registry] {skill_id} 找到多個 Skill 子類別，使用：{best.__name__}")
                skill_cls = best
            else:
                skill_cls = candidates[0]

        try:
            return skill_cls()
        except Exception as e:
            raise SkillLoadError(f"Skill 實例化失敗：{e}") from e

    # ── 查詢 ─────────────────────────────────────────────────────────

    def get_all_schemas(self) -> list[dict]:
        """
        回傳所有已載入 skill 的工具 schema 清單。
        供 Planner 傳給 LLMGateway 使用。
        """
        schemas: list[dict] = []
        for skill in self._skills.values():
            schemas.extend(skill.get_schemas())
        return schemas

    def get_local_only_tools(self) -> set[str]:
        """
        回傳所有 privacy_level="local_only" 的工具名稱集合。
        Router 用來決定是否強制走 Ollama。
        """
        local_tools: set[str] = set()
        for skill_id, skill in self._skills.items():
            if getattr(skill, "privacy_level", "public") == "local_only":
                local_tools.update(skill.get_tool_names())
        return local_tools

    def get_skill_by_tool(self, tool_name: str) -> Skill | None:
        """根據工具名稱找到對應的 skill 實例"""
        skill_id = self._tool_map.get(tool_name)
        if skill_id is None:
            return None
        return self._skills.get(skill_id)

    def list_skills(self) -> list[dict]:
        """列出所有已載入的 skill 資訊（給 /status 指令用）"""
        result = []
        for skill_id, manifest in self._manifests.items():
            skill = self._skills[skill_id]
            result.append({
                "id": skill_id,
                "name": manifest.get("name", skill_id),
                "version": manifest.get("version", "?"),
                "tools": skill.get_tool_names(),
                "privacy_level": getattr(skill, "privacy_level", "public"),
                "requires_confirmation": getattr(skill, "requires_confirmation", False),
            })
        return result

    # ── 執行 ─────────────────────────────────────────────────────────

    async def dispatch(self, tool_name: str, **kwargs: Any) -> str:
        """
        執行指定工具，回傳字串結果。
        由 Planner 呼叫，不應直接在其他地方使用。

        回傳的字串會直接當作 tool message 的 content 傳給 LLM，
        所以最好是人類可讀的格式。
        """
        skill = self.get_skill_by_tool(tool_name)
        if skill is None:
            return f"❌ 未知工具：{tool_name}（請確認 skill 是否已載入）"

        try:
            result = await skill.execute(tool_name, **kwargs)
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.exception(f"[Registry] 工具 {tool_name!r} 執行失敗：{e}")
            return f"❌ 工具執行錯誤（{tool_name}）：{e}"

    def __repr__(self) -> str:
        return (
            f"SkillRegistry("
            f"skills={list(self._skills.keys())}, "
            f"tools={list(self._tool_map.keys())})"
        )
