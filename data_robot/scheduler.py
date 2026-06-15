from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from data_robot.run_all import PLATFORMS, run


async def main_loop(args: argparse.Namespace) -> None:
    interval = max(60, min(1440, args.interval_minutes))
    while True:
        args.date_token = args.date_token or datetime.now().strftime("%m%d")
        await run(args)
        if args.once:
            return
        print(f"Next data robot run starts in {interval} minutes.", flush=True)
        await asyncio.sleep(interval * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ShopOps data robots on a fixed interval.")
    parser.add_argument("--interval-minutes", type=int, default=120, help="Run interval, clamped to 60..1440 minutes.")
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--platform", action="append", choices=PLATFORMS, help="Only run selected platform; repeatable.")
    parser.add_argument("--task", action="append", help="Only run selected task key; repeatable.")
    parser.add_argument("--date-token", default="", help="Archive date directory, e.g. 0612. Defaults to today.")
    parser.add_argument("--archive-root", default=r"D:\lyh\agent\agent-frame\ShopOps\docs\data\ShopOps")
    parser.add_argument("--evidence-root", default=r"D:\lyh\agent\agent-frame\ShopOps\docs\live-evidence\data-robot")
    parser.add_argument("--timeout-seconds", type=int, default=0)
    parser.add_argument("--idle-seconds", type=int, default=20)
    parser.add_argument("--max-downloads", type=int, default=5)
    parser.add_argument("--min-task-interval-seconds", type=int, default=480)
    parser.add_argument("--retry-interval-seconds", type=int, default=480)
    parser.add_argument("--max-task-attempts", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--auto-actions", action="store_true")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument("--cdp-url", default="")
    parser.add_argument("--watch-dir", default="")
    parser.add_argument("--run-import-check", action="store_true")
    parser.add_argument("--skip-import-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    asyncio.run(main_loop(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
