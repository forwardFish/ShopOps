from __future__ import annotations

import argparse
import asyncio
import os
import time
import urllib.request
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any

from data_robot.common import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_EVIDENCE_ROOT,
    add_batch_layout_args,
    configure_console_encoding,
    evidence_token,
    hourly_batch_token,
    is_recoverable_cdp_error,
    print_json,
    run_platform,
    summarize_platform_results,
    write_json,
)
from data_robot.run_all import PLATFORMS
from data_robot.start_chrome import restart_chrome_for_task, start_chrome_for_task
from data_robot.tasks import PLATFORM_TASKS
from data_robot.verify_batch import verify_batch


PLATFORM_PORTS = {
    "pinduoduo": 9222,
    "wechat_channels": 9223,
    "douyin": 9224,
    "tmall": 9225,
}

PLATFORM_ENTRY_TASK = {
    "pinduoduo": "pinduoduo_orders",
    "wechat_channels": "wechat_channels_orders",
    "douyin": "douyin_ads",
    "tmall": "tmall_orders",
}


def ensure_platform_cdp(
    platform: str,
    *,
    profile_suffix: str,
    profile_root: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Use an existing CDP browser or start the dedicated platform profile."""
    port = PLATFORM_PORTS[platform]
    if wait_for_cdp(port, timeout_seconds=2):
        return {"status": "ready", "started": False, "port": port}
    task_key = PLATFORM_ENTRY_TASK[platform]
    try:
        process = start_chrome_for_task(
            task_key,
            port=port,
            profile_suffix=profile_suffix,
            profile_root=profile_root,
        )
    except Exception as exc:
        return {
            "status": "start_failed",
            "started": False,
            "port": port,
            "error": f"{type(exc).__name__}: {exc}",
        }
    ready = wait_for_cdp(port, timeout_seconds=timeout_seconds)
    return {
        "status": "ready" if ready else "not_ready",
        "started": True,
        "port": port,
        "pid": process.pid,
    }


def cdp_base_url(platform: str) -> str:
    return f"http://localhost:{PLATFORM_PORTS[platform]}"


def default_downloads_dir() -> Path:
    return Path(os.path.expanduser("~")) / "Downloads"


def launch_login_browsers(
    platforms: list[str],
    *,
    profile_suffix: str = "cdp",
    profile_root: str = "",
) -> dict[str, str]:
    launched: dict[str, str] = {}
    for platform in platforms:
        port = PLATFORM_PORTS[platform]
        ensure_platform_cdp(
            platform,
            profile_suffix=profile_suffix,
            profile_root=profile_root,
        )
        launched[platform] = cdp_base_url(platform)
    return launched


def wait_for_cdp(port: int, *, timeout_seconds: int = 30) -> bool:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://localhost:{port}/json/version"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.status == 200
        except Exception:
            time.sleep(1)
    return False


def selected_task_keys(platforms: list[str], task_keys: list[str] | None) -> list[str]:
    allowed = [task for platform in platforms for task in PLATFORM_TASKS[platform]]
    if not task_keys:
        return allowed
    return [task for task in task_keys if task in allowed]


def platform_result_failed_on_cdp_connect(platform_result: dict[str, Any]) -> bool:
    task_results = platform_result.get("results") or []
    if not task_results:
        return False
    errors = [item for item in task_results if item.get("status") == "error"]
    return len(errors) == len(task_results) and all(is_recoverable_cdp_error(item) for item in errors)


async def run_daily(args: argparse.Namespace) -> dict[str, Any]:
    platforms = args.platform or list(PLATFORMS)
    if args.prepare_login:
        launched = launch_login_browsers(
            platforms,
            profile_suffix=args.browser_profile_suffix,
            profile_root=args.browser_profile_root,
        )
        summary = {
            "status": "login_browsers_started",
            "platforms": platforms,
            "browser_profile_suffix": args.browser_profile_suffix,
            "browser_profile_root": args.browser_profile_root,
            "cdp_urls": launched,
            "next_command": (
                f"python -m data_robot.daily_download --date-token {args.date_token or datetime.now().strftime('%m%d')}"
            ),
        }
        print_json(summary)
        return summary

    date_token = args.date_token or datetime.now().strftime("%m%d")
    batch_token = date_token if args.flat_date_folder else hourly_batch_token(date_token, args.batch_hour)
    watch_dir = Path(args.watch_dir) if args.watch_dir else default_downloads_dir()
    cdp_bootstrap: dict[str, dict[str, Any]] = {}
    if not args.no_cdp:
        for platform in platforms:
            cdp_bootstrap[platform] = ensure_platform_cdp(
                platform,
                profile_suffix=args.browser_profile_suffix,
                profile_root=args.browser_profile_root,
            )
    results = []
    for platform in platforms:
        cdp_url = "" if args.no_cdp else cdp_base_url(platform)
        platform_args = Namespace(
            task=args.task,
            date_token=batch_token,
            archive_root=args.archive_root,
            timeout_seconds=args.timeout_seconds,
            idle_seconds=args.idle_seconds,
            max_downloads=args.max_downloads,
            auto_actions=args.auto_actions,
            manual=args.manual,
            headless=args.headless,
            browser_channel=args.browser_channel,
            cdp_url=cdp_url,
            direct_cdp=args.direct_cdp,
            watch_dir=str(watch_dir),
            min_task_interval_seconds=args.min_task_interval_seconds,
            retry_interval_seconds=args.retry_interval_seconds,
            max_task_attempts=args.max_task_attempts,
            force=args.force,
            run_import_check=args.run_import_check,
            skip_import_check=not args.run_import_check,
            evidence_root=args.evidence_root,
        )
        platform_result = await run_platform(platform, platform_args)
        if cdp_url and platform_result_failed_on_cdp_connect(platform_result):
            # Preserve the existing Chrome session and retry through the
            # minimal direct-CDP path.  This is especially important for
            # long-running Tmall pages whose Playwright attachment can stall
            # while normal browser input remains available.
            direct_args = Namespace(**vars(platform_args))
            direct_args.direct_cdp = True
            print(f"[{platform}] Playwright CDP attach failed; retrying through direct CDP without restarting Chrome.", flush=True)
            platform_result = await run_platform(platform, direct_args)
            platform_result["retried_with_direct_cdp"] = True
        if (
            cdp_url
            and args.restart_stale_cdp
            and platform_result_failed_on_cdp_connect(platform_result)
        ):
            print(f"[{platform}] CDP connection is stale; restarting the dedicated Chrome profile and retrying once.", flush=True)
            restart_chrome_for_task(
                PLATFORM_ENTRY_TASK[platform],
                port=PLATFORM_PORTS[platform],
                start_url="about:blank",
                profile_suffix=args.browser_profile_suffix,
                profile_root=args.browser_profile_root,
            )
            wait_for_cdp(PLATFORM_PORTS[platform])
            platform_result = await run_platform(platform, platform_args)
            platform_result["retried_after_cdp_restart"] = True
        results.append(platform_result)

    verification = None if args.skip_final_verify else verify_batch(
        Path(args.archive_root) / batch_token,
        task_keys=selected_task_keys(platforms, args.task),
    )
    summary = {
        "status": summarize_platform_results(results),
        "date_token": date_token,
        "batch_token": batch_token,
        "batch_dir": str(Path(args.archive_root) / batch_token),
        "watch_dir": str(watch_dir),
        "cdp_bootstrap": cdp_bootstrap,
        "platforms": platforms,
        "results": results,
        "verification": verification,
    }
    evidence_root = Path(args.evidence_root)
    evidence = evidence_root / f"daily-download-{evidence_token(batch_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({**summary, "evidence": str(evidence)})
    return summary


def main() -> int:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="Daily ShopOps Excel/CSV downloader for all configured platforms.")
    parser.add_argument("--prepare-login", action="store_true", help="Open one normal Chrome session per platform for login.")
    parser.add_argument("--platform", action="append", choices=PLATFORMS, help="Only run selected platform; repeatable.")
    parser.add_argument("--task", action="append", help="Only run selected task key; repeatable.")
    parser.add_argument("--date-token", default="", help="Archive date directory, e.g. 0611. Defaults to today.")
    add_batch_layout_args(parser)
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--watch-dir", default=str(default_downloads_dir()))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--idle-seconds", type=int, default=30)
    parser.add_argument("--max-downloads", type=int, default=5)
    parser.add_argument("--min-task-interval-seconds", type=int, default=0, help="Optional interval override; platform floors are applied automatically.")
    parser.add_argument("--retry-interval-seconds", type=int, default=0, help="Optional retry interval override; platform floors are applied automatically.")
    parser.add_argument("--max-task-attempts", type=int, default=5, help="Maximum attempts per task before skipping to the next task.")
    parser.add_argument("--force", action="store_true", help="Bypass the anti-risk cooldown.")
    parser.add_argument("--auto-actions", action="store_true")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument(
        "--browser-profile-suffix",
        default="cdp",
        help="Profile suffix under data_robot/profiles for externally launched CDP browsers.",
    )
    parser.add_argument("--browser-profile-root", default="", help="Root folder for browser user-data profiles.")
    parser.add_argument("--no-cdp", action="store_true", help="Use Playwright-launched browser profiles instead of normal Chrome CDP sessions.")
    parser.add_argument("--direct-cdp", action="store_true", help="Use direct Chrome DevTools Protocol instead of the Playwright driver. Requires CDP mode.")
    parser.add_argument(
        "--restart-stale-cdp",
        action="store_true",
        help="Explicitly restart the managed Chrome profile after a stale CDP connection. Disabled by default to preserve open pages and login sessions.",
    )
    parser.add_argument(
        "--no-restart-stale-cdp",
        action="store_false",
        dest="restart_stale_cdp",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--run-import-check", action="store_true")
    parser.add_argument("--skip-final-verify", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    summary = asyncio.run(run_daily(args))
    return 0 if summary.get("status") in {"downloaded", "skipped_cooldown", "finished_with_skips"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
