from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from data_robot.common import DEFAULT_ARCHIVE_ROOT, DEFAULT_EVIDENCE_ROOT, evidence_token, hourly_batch_token, write_json
from data_robot.full_flow import run_command
from data_robot.verify_batch import verify_batch


ROOT = Path(__file__).resolve().parents[1]
TMALL = "\u5929\u732b"
DOUYIN = "\u6296\u97f3"


def next_window_start(now: datetime, *, start_hour: int, end_hour: int) -> datetime:
    today_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    today_end = day_boundary(now, end_hour)
    if now < today_start:
        return today_start
    if now >= today_end:
        return today_start + timedelta(days=1)
    return now


def day_boundary(now: datetime, hour: int) -> datetime:
    if hour == 24:
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return now.replace(hour=hour, minute=0, second=0, microsecond=0)


def next_delay_seconds(
    now: datetime,
    *,
    start_hour: int = 9,
    end_hour: int = 24,
    interval_minutes: int = 60,
    jitter_minutes: int = 12,
    rng: random.Random | None = None,
) -> int:
    rng = rng or random.Random()
    window_start = next_window_start(now, start_hour=start_hour, end_hour=end_hour)
    if window_start > now:
        return max(0, int((window_start - now).total_seconds()) + rng.randint(0, max(0, jitter_minutes * 60)))
    base = interval_minutes * 60
    jitter = rng.randint(-jitter_minutes * 60, jitter_minutes * 60) if jitter_minutes > 0 else 0
    delay = max(60, base + jitter)
    next_run = now + timedelta(seconds=delay)
    window_end = day_boundary(now, end_hour)
    if next_run >= window_end:
        tomorrow_start = now.replace(hour=start_hour, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return max(0, int((tomorrow_start - now).total_seconds()) + rng.randint(0, max(0, jitter_minutes * 60)))
    return int(delay)


def build_download_command(args: argparse.Namespace, date_token: str, batch_hour: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "data_robot.daily_download",
        "--date-token",
        date_token,
        "--batch-hour",
        batch_hour,
        "--archive-root",
        args.archive_root,
        "--evidence-root",
        args.evidence_root,
        "--watch-dir",
        args.watch_dir,
        "--platform",
        "tmall",
        "--task",
        "tmall_orders",
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--idle-seconds",
        str(args.idle_seconds),
        "--max-downloads",
        str(args.max_downloads),
        "--min-task-interval-seconds",
        str(args.min_task_interval_seconds),
        "--retry-interval-seconds",
        str(args.retry_interval_seconds),
        "--max-task-attempts",
        str(args.max_task_attempts),
        "--browser-profile-suffix",
        args.browser_profile_suffix,
    ]
    if args.browser_profile_root:
        command.extend(["--browser-profile-root", args.browser_profile_root])
    if args.no_cdp:
        command.append("--no-cdp")
    if args.direct_cdp:
        command.append("--direct-cdp")
    if not args.restart_stale_cdp:
        command.append("--no-restart-stale-cdp")
    if args.manual:
        command.append("--manual")
    if args.auto_actions:
        command.append("--auto-actions")
    if args.force:
        command.append("--force")
    return command


def build_import_command(args: argparse.Namespace, batch_dir: Path, stat_date: str, evidence: Path) -> list[str]:
    order_platforms = getattr(args, "order_platform", None) or [TMALL, DOUYIN]
    order_lookback_days = getattr(args, "order_lookback_days", 0)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "import_daily_files_to_feishu.py"),
        "--batch-dir",
        str(batch_dir),
        "--evidence",
        str(evidence),
        "--kind",
        "orders",
        "--date",
        stat_date,
        "--order-lookback-days",
        str(order_lookback_days),
    ]
    for platform in order_platforms:
        command.extend(["--platform", platform])
    if args.dry_run_import:
        command.append("--dry-run")
    return command


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now()
    date_token = args.date_token or now.strftime("%m%d")
    stat_date = args.import_date or date.today().isoformat()
    batch_hour = args.batch_hour or now.strftime("%H%M%S")
    batch_token = hourly_batch_token(date_token, batch_hour)
    safe_batch = evidence_token(batch_token)
    evidence_root = Path(args.evidence_root)
    batch_dir = Path(args.archive_root) / batch_token
    download_result = None
    if not args.skip_download:
        download_timeout = max(args.timeout_seconds * args.max_task_attempts * 3, 900)
        download_result = run_command(build_download_command(args, date_token, batch_hour), timeout=download_timeout)

    verification = verify_batch(batch_dir, ["tmall_orders"], include_legacy=True)
    import_evidence = evidence_root / f"hourly-order-import-{safe_batch}-{now.strftime('%H%M%S')}.json"
    import_result = None
    tmall_excel_ready = verification["status"] in {"complete", "legacy_present"}
    if tmall_excel_ready or args.allow_missing_tmall_download:
        batch_dir.mkdir(parents=True, exist_ok=True)
        import_result = run_command(build_import_command(args, batch_dir, stat_date, import_evidence), timeout=args.import_timeout_seconds)

    status = "success"
    if download_result and download_result["returncode"] != 0:
        status = "download_failed"
    elif not tmall_excel_ready:
        status = "archive_incomplete"
    elif import_result is None:
        status = "archive_incomplete"
    elif import_result["returncode"] != 0:
        status = "import_failed"
    summary = {
        "status": status,
        "batch_token": batch_token,
        "batch_dir": str(batch_dir),
        "stat_date": stat_date,
        "download": download_result,
        "verification": verification,
        "import": import_result,
        "import_evidence": str(import_evidence) if import_result else "",
        "tmall_excel_required": True,
        "tmall_excel_ready": tmall_excel_ready,
        "order_strategy": {
            "tmall": "download the existing Tmall order Excel export, archive it, then import orders; no screenshot/OCR fallback",
            "douyin": "use the existing Jushuitan fallback in import_daily_files_to_feishu.py",
        },
    }
    evidence = evidence_root / f"hourly-order-flow-{safe_batch}-{now.strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print(json.dumps({**summary, "evidence": str(evidence)}, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly ShopOps order import: Tmall Excel plus Douyin Jushuitan fallback.")
    add_schedule_args(parser)
    args = parser.parse_args()

    while True:
        now = datetime.now()
        if next_window_start(now, start_hour=args.start_hour, end_hour=args.end_hour) > now:
            delay = next_delay_seconds(
                now,
                start_hour=args.start_hour,
                end_hour=args.end_hour,
                interval_minutes=args.interval_minutes,
                jitter_minutes=args.jitter_minutes,
            )
            print(f"Outside collection window; sleeping {delay} seconds.", flush=True)
            time.sleep(delay)
        result = run_once(args)
        if args.once:
            return 0 if result["status"] == "success" else 4
        delay = next_delay_seconds(
            datetime.now(),
            start_hour=args.start_hour,
            end_hour=args.end_hour,
            interval_minutes=args.interval_minutes,
            jitter_minutes=args.jitter_minutes,
        )
        print(f"Next scheduled order import starts in {delay} seconds.", flush=True)
        time.sleep(delay)


def add_schedule_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--date-token", default="")
    parser.add_argument("--batch-hour", default="")
    parser.add_argument("--import-date", default="")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--watch-dir", default=str(Path.home() / "Downloads"))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--idle-seconds", type=int, default=30)
    parser.add_argument("--max-downloads", type=int, default=3)
    parser.add_argument("--min-task-interval-seconds", type=int, default=1500)
    parser.add_argument("--retry-interval-seconds", type=int, default=600)
    parser.add_argument("--max-task-attempts", type=int, default=3)
    parser.add_argument(
        "--order-platform",
        action="append",
        choices=(TMALL, DOUYIN),
        default=None,
        help="Order platform to import; repeatable. Defaults to both Tmall and Douyin.",
    )
    parser.add_argument("--start-hour", type=int, default=8)
    parser.add_argument("--end-hour", type=int, default=23)
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument("--jitter-minutes", type=int, default=12)
    parser.add_argument(
        "--order-lookback-days",
        type=int,
        default=0,
        help="Hourly order import lookback around --date. Default 0 imports only the requested date; daily historical imports keep their own wider window.",
    )
    parser.add_argument("--browser-profile-suffix", default="cdp")
    parser.add_argument("--browser-profile-root", default="")
    parser.add_argument("--cdp-url", default="", help="Existing Chrome CDP URL. Order downloads normally use per-platform defaults when empty.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-cdp", action="store_true")
    parser.add_argument("--direct-cdp", action="store_true")
    parser.add_argument("--restart-stale-cdp", action="store_true", help="Allow the downloader to restart its managed Chrome profile after a stale CDP connection.")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--auto-actions", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--dry-run-import", action="store_true")
    parser.add_argument("--allow-missing-tmall-download", action="store_true")
    parser.add_argument("--import-timeout-seconds", type=int, default=1200)


if __name__ == "__main__":
    raise SystemExit(main())
