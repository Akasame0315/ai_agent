from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(cfg: dict):
    log_cfg = cfg.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO"))
    log_file = Path(log_cfg.get("file", "logs/agent.log"))
    log_file.parent.mkdir(parents=True, exist_ok=True)

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
    root.setLevel(level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_cfg.get("max_bytes", 5_242_880),
        backupCount=log_cfg.get("backup_count", 3),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for lib in ("httpx", "httpcore", "telegram", "groq", "apscheduler"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Personal Agent")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="啟用 debug 模式：印出 system prompt 與最後一條 user message",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    from config.loader import load_config

    try:
        cfg = load_config()
    except EnvironmentError as exc:
        print(f"\n設定載入失敗：{exc}\n")
        sys.exit(1)

    setup_logging(cfg)
    logger.info("=" * 60)
    logger.info("personal-agent 啟動中...")
    logger.info("=" * 60)

    if args.debug:
        logger.info("*** DEBUG 模式已啟用：將印出 LLM prompt 內容 ***")

    from core.planner import Planner
    from interface.telegram_bot import TelegramBot
    from services.llm_gateway import LLMGateway
    from services.task_manager import TaskManager

    llm = LLMGateway(cfg, debug=args.debug)
    task_manager = TaskManager()
    planner = Planner(llm, cfg, debug=args.debug)
    bot = TelegramBot(cfg, planner, task_manager)

    allowed = cfg["telegram"].get("allowed_user_ids", [])
    logger.info("設定載入完成")
    logger.info("  LLM provider: %s", cfg["llm"]["default_provider"])
    logger.info("  Groq model  : %s", cfg["llm"]["groq_model"])
    logger.info("  Ollama model: %s", cfg["llm"]["ollama_model"])
    if allowed:
        logger.info("  Allowed IDs : %s", allowed)
    else:
        logger.info("  Allowed IDs : not configured")
    if args.debug:
        logger.info("  Debug mode  : ON")
    logger.info("  Press Ctrl+C to stop")

    bot.run(llm)


if __name__ == "__main__":
    main()
