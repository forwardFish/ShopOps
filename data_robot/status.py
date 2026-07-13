from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from data_robot.check_cdp import check_platforms
from data_robot.common import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_EVIDENCE_ROOT,
    GLOBAL_EXPORT_COOLDOWN_KEY,
    add_batch_layout_args,
    cooldown_remaining,
    effective_min_task_interval_seconds,
    evidence_token,
    hourly_batch_token,
    print_json,
    write_json,
)
from data_robot.run_all import PLATFORMS
from data_robot.tasks import PLATFORM_TASKS, TASKS
from data_robot.verify_batch import verify_batch


def selected_task_keys(platforms: list[str], tasks: list[str] | None) -> list[str]:
    allowed = [task_key for platform in platforms for task_key in PLATFORM_TASKS[platform]]
    if not tasks:
        return allowed
    return [task_key for task_key in tasks if task_key in allowed]


def build_status(
    *,
    date_token: str,
    archive_root: Path,
    platforms: list[str],
    task_keys: list[str] | None,
    min_task_interval_seconds: int,
    include_cdp: bool,
) -> dict[str, Any]:
    selected_tasks = selected_task_keys(platforms, task_keys)
    batch_dir = archive_root / date_token
    archive_status = verify_batch(batch_dir, selected_tasks)
    task_intervals = {
        task_key: effective_min_task_interval_seconds(TASKS[task_key], min_task_interval_seconds)
        for task_key in selected_tasks
    }
    cooldowns = {
        task_key: {
            "platform": TASKS[task_key].platform,
            "kind": TASKS[task_key].kind,
            "min_export_interval_seconds": task_intervals[task_key],
            "task_remaining_seconds": cooldown_remaining(task_key, task_intervals[task_key]),
            # Kept as a compatibility field for older evidence readers.  New
            # runs intentionally do not let one platform block another.
            "global_remaining_seconds": 0,
            "remaining_seconds": cooldown_remaining(task_key, task_intervals[task_key]),
        }
        for task_key in selected_tasks
    }
    blocked_by_cooldown = [
        task_key for task_key, item in cooldowns.items() if int(item["remaining_seconds"]) > 0
    ]
    cdp_status = check_platforms(platforms) if include_cdp else None
    can_collect = not blocked_by_cooldown and (cdp_status is None or cdp_status["status"] == "ready")
    archive_complete = archive_status["status"] == "complete"
    return {
        "status": "archive_complete" if archive_complete else "archive_incomplete",
        "can_collect": can_collect,
        "date_token": date_token,
        "batch_token": date_token,
        "batch_dir": str(batch_dir),
        "platforms": platforms,
        "task_keys": selected_tasks,
        "archive_status": archive_status,
        "cooldowns": cooldowns,
        "global_cooldown_remaining_seconds": max(
            (int(item["global_remaining_seconds"]) for item in cooldowns.values()),
            default=0,
        ),
        "blocked_by_cooldown": blocked_by_cooldown,
        "cdp_status": cdp_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only ShopOps data robot status check.")
    parser.add_argument("--date-token", default="", help="Archive date directory, e.g. 0613. Defaults to today.")
    add_batch_layout_args(parser)
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--platform", action="append", choices=PLATFORMS, help="Only check selected platform; repeatable.")
    parser.add_argument("--task", action="append", choices=sorted(TASKS), help="Only check selected task; repeatable.")
    parser.add_argument("--min-task-interval-seconds", type=int, default=0)
    parser.add_argument("--skip-cdp", action="store_true", help="Do not check Chrome CDP debug ports.")
    args = parser.parse_args()

    platforms = args.platform or list(PLATFORMS)
    date_token = args.date_token or datetime.now().strftime("%m%d")
    batch_token = date_token if args.flat_date_folder else hourly_batch_token(date_token, args.batch_hour)
    summary = build_status(
        date_token=batch_token,
        archive_root=Path(args.archive_root),
        platforms=platforms,
        task_keys=args.task,
        min_task_interval_seconds=max(0, args.min_task_interval_seconds),
        include_cdp=not args.skip_cdp,
    )
    summary["date_token"] = date_token
    summary["batch_token"] = batch_token
    summary["batch_dir"] = str(Path(args.archive_root) / batch_token)
    evidence_root = Path(args.evidence_root)
    evidence = evidence_root / f"status-{evidence_token(batch_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({**summary, "evidence": str(evidence)})
    return 0 if summary["can_collect"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
