"""
main.py — 程式入口
路徑：main.py（專案根目錄）

啟動方式：
    python main.py              # Telegram Bot（預設）
    python main.py --debug      # Debug 模式（印出 LLM prompt 內容）
    python main.py --cli        # 終端機測試（不需要 Telegram）
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path


# ══════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════

def _setup_logging(log_dir: str, debug: bool) -> None:
    log_path = Path(log_dir) / "agent.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for lib in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(lib).setLevel(logging.WARNING)


# ══════════════════════════════════════════════════════════════════════
# CLI 引數
# ══════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal AI Agent")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug 模式：印出 LLM prompt 與 tool call 內容",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="終端機互動模式（不啟動 Telegram Bot）",
    )
    return parser.parse_args()


# ══════════════════════════════════════════════════════════════════════
# 啟動流程
# ══════════════════════════════════════════════════════════════════════

async def _async_main(debug: bool, cli_mode: bool) -> None:
    logger = logging.getLogger(__name__)

    # ── 1. 載入設定 ──────────────────────────────────────────────────
    from config import cfg

    missing = cfg.validate()
    if missing:
        logger.error("缺少必要設定，請檢查 .env 檔案：")
        for item in missing:
            logger.error(f"  - {item}")
        sys.exit(1)

    # 確保資料夾存在
    cfg.paths.ensure_dirs()
    _relocate_file_log(cfg.paths.logs, debug)

    # ── 2. 載入 Skills（Auto-Discovery）─────────────────────────────
    from core.skill_registry import SkillRegistry

    registry = SkillRegistry()
    await registry.discover(cfg.paths.skills)

    if not registry.list_skills():
        logger.warning("未載入任何 skill，Agent 將只能進行純文字對話")

    # ── 3. 初始化 Planner ────────────────────────────────────────────
    from core.planner import Planner

    planner = Planner(cfg, registry, debug=debug)

    # ── 4. 初始化 TaskManager ────────────────────────────────────────
    from services.task_manager import TaskManager

    task_manager = TaskManager()

    # ── 5. 印出啟動摘要 ──────────────────────────────────────────────
    _log_startup(logger, cfg, registry, debug)

    # ── 6. 啟動介面 ──────────────────────────────────────────────────
    if cli_mode:
        await _run_cli(planner)
    else:
        from interface.telegram_bot import TelegramBot

        # 建立預設 LLM Gateway（Telegram Bot 啟動確認用）
        from services.llm_gateway import LLMGateway
        llm_gateway = LLMGateway.from_config(cfg)

        bot = TelegramBot(cfg, planner, task_manager)
        # run() 現在是 async，直接 await
        await bot.run(llm=llm_gateway)


def _relocate_file_log(log_dir: str, debug: bool) -> None:
    """cfg 載入後，把 file handler 搬到絕對路徑版本"""
    import logging.handlers
    from pathlib import Path

    log_path = Path(log_dir) / "agent.log"
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()

    for h in root.handlers[:]:
        if isinstance(h, logging.handlers.TimedRotatingFileHandler):
            root.removeHandler(h)
            h.close()

    fh = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        utc=False,
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)


def _log_startup(logger, cfg, registry, debug: bool) -> None:
    skills_info = registry.list_skills()
    names = [s["name"] for s in skills_info]
    allowed = cfg.telegram.allowed_user_ids

    logger.info("=" * 55)
    logger.info("Personal Agent 啟動中")
    logger.info("=" * 55)
    logger.info(f"  LLM provider  : {cfg.llm.provider}")
    if cfg.llm.provider == "auto":
        logger.info(f"  Cloud provider: {cfg.llm.cloud_provider}")
    logger.info(f"  Groq model    : {cfg.llm.groq_model}")
    logger.info(f"  Ollama model  : {cfg.llm.ollama_model}")
    logger.info(f"  Skills ({len(names):2d})    : {', '.join(names) or '（無）'}")
    logger.info(f"  Allowed IDs   : {allowed if allowed else '不限制'}")
    logger.info(f"  Log dir       : {cfg.paths.logs}")
    if debug:
        logger.info("  *** DEBUG 模式已啟用 ***")
    logger.info("=" * 55)


# ══════════════════════════════════════════════════════════════════════
# CLI 互動模式（測試用，不需要 Telegram）
# ══════════════════════════════════════════════════════════════════════

async def _run_cli(planner) -> None:
    print("\n=== Agent CLI 測試模式 ===")
    print("指令：/confirm  /cancel  /clear  exit\n")

    _CLI_USER_ID = 0

    while True:
        try:
            user_input = input("你：").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再見！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("再見！")
            break

        if user_input == "/confirm":
            reply = await planner.handle_confirm(_CLI_USER_ID)
        elif user_input == "/cancel":
            reply = await planner.handle_cancel(_CLI_USER_ID)
        elif user_input == "/clear":
            planner.clear_context(_CLI_USER_ID)
            print("Agent：對話記憶已清除\n")
            continue
        else:
            reply = await planner.process(_CLI_USER_ID, user_input)

        print(f"Agent：{reply}\n")


# ══════════════════════════════════════════════════════════════════════
# 程式進入點
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    args = _parse_args()
    _setup_logging("logs", debug=args.debug)
    asyncio.run(_async_main(debug=args.debug, cli_mode=args.cli))


if __name__ == "__main__":
    main()
