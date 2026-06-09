from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.models import dt
from shopops.scheduler import Scheduler


def summarize_cycle(index: int, result: dict[str, Any]) -> dict[str, Any]:
    order = result.get("order")
    promotion = result.get("promotion")
    log = result.get("log")
    promotion_item = promotion.items[0] if promotion and promotion.items else None
    return {
        "cycle": index,
        "finished_at": dt(datetime.now()),
        "order": {
            "success": order.success if order else False,
            "error_code": order.error_code if order else None,
            "order_count": order.order_count if order else None,
            "orders": order.orders if order else [],
            "page_url": (order.raw or {}).get("page_url") if order else None,
            "screenshot_path": (order.raw or {}).get("screenshot_path") if order else None,
        },
        "promotion": {
            "success": promotion.success if promotion else False,
            "status": promotion.status if promotion else None,
            "error_code": promotion.error_code if promotion else None,
            "cost": promotion_item.cost if promotion_item else None,
            "page_url": (promotion_item.raw or {}).get("page_url") if promotion_item and promotion_item.raw else None,
            "screenshot_path": (promotion_item.raw or {}).get("screenshot_path") if promotion_item and promotion_item.raw else None,
        },
        "log": {
            "total_status": log.total_status if log else None,
            "saved_count": log.saved_count if log else None,
            "error_code": log.error_code if log else None,
            "error_message": log.error_message if log else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Qianniu to Feishu acceptance cycles.")
    parser.add_argument("--cycles", type=int, default=3, help="Number of collection cycles.")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Seconds to wait between cycles. Defaults to FETCH_INTERVAL_SECONDS.")
    parser.add_argument("--no-wait", action="store_true", help="Run cycles back-to-back for dry validation.")
    args = parser.parse_args()

    settings = load_settings()
    interval = args.interval_seconds if args.interval_seconds is not None else settings.fetch_interval_seconds
    evidence_dir = Path(settings.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = evidence_dir / f"acceptance-run-{run_id}.json"
    scheduler = Scheduler(settings=settings)
    cycles: list[dict[str, Any]] = []

    for index in range(1, args.cycles + 1):
        result = scheduler.run_once()
        cycles.append(summarize_cycle(index, result))
        report_path.write_text(json.dumps({"run_id": run_id, "cycles": cycles}, ensure_ascii=False, indent=2), encoding="utf-8")
        if index < args.cycles and not args.no_wait:
            time.sleep(interval)

    print(str(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
