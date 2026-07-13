from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from data_robot.common import DEFAULT_ARCHIVE_ROOT, DEFAULT_EVIDENCE_ROOT, add_batch_layout_args, evidence_token, hourly_batch_token, write_json
from data_robot.start_chrome import start_chrome_for_task_with_log, stop_chrome_for_task
from data_robot.verify_batch import verify_batch


ROOT = Path(__file__).resolve().parents[1]


def run_playwright_check() -> dict[str, Any]:
    code = (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    print(p.chromium.name)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    return {
        "status": "ready" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-8000:],
    }


def wait_for_cdp_stability(port: int, *, timeout_seconds: int, stable_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    first_ready_at: float | None = None
    last_error = ""
    ready_samples = 0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            ready_samples += 1
            first_ready_at = first_ready_at or time.monotonic()
            if time.monotonic() - first_ready_at >= stable_seconds:
                return {
                    "status": "ready",
                    "ready_samples": ready_samples,
                    "browser": payload.get("Browser", ""),
                    "websocket": payload.get("webSocketDebuggerUrl", ""),
                }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            first_ready_at = None
        time.sleep(1)
    return {
        "status": "failed",
        "ready_samples": ready_samples,
        "last_error": last_error,
    }


def run_browser_check(
    task: str,
    *,
    port: int,
    profile_suffix: str,
    profile_root: str,
    evidence_root: Path,
) -> dict[str, Any]:
    log_path = evidence_root / f"doctor-browser-{task}-{datetime.now().strftime('%H%M%S')}.log"
    stop_chrome_for_task(task, profile_suffix=profile_suffix, profile_root=profile_root)
    process = start_chrome_for_task_with_log(
        task,
        port=port,
        profile_suffix=profile_suffix,
        profile_root=profile_root,
        log_path=log_path,
    )
    stability = wait_for_cdp_stability(port, timeout_seconds=25, stable_seconds=10)
    poll = process.poll()
    log_tail = ""
    if log_path.exists():
        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
    return {
        "status": stability["status"],
        "port": port,
        "profile_suffix": profile_suffix,
        "profile_root": profile_root,
        "pid": process.pid,
        "process_poll": poll,
        "stability": stability,
        "log_path": str(log_path),
        "log_tail": log_tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose ShopOps data robot runtime readiness.")
    parser.add_argument("--date-token", default=datetime.now().strftime("%m%d"))
    add_batch_layout_args(parser, batch_hour_default=datetime.now().strftime("%H"))
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--task", default="pinduoduo_orders")
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--browser-profile-suffix", default="doctor")
    parser.add_argument("--browser-profile-root", default="", help="Root folder for browser user-data profiles.")
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)
    batch_token = args.date_token if args.flat_date_folder else hourly_batch_token(args.date_token, args.batch_hour)
    summary = {
        "status": "unknown",
        "date_token": args.date_token,
        "batch_token": batch_token,
        "batch_dir": str(Path(args.archive_root) / batch_token),
        "archive": verify_batch(Path(args.archive_root) / batch_token),
        "playwright": run_playwright_check(),
        "browser": run_browser_check(
            args.task,
            port=args.port,
            profile_suffix=args.browser_profile_suffix,
            profile_root=args.browser_profile_root,
            evidence_root=evidence_root,
        ),
    }
    if summary["playwright"]["status"] == "ready" or summary["browser"]["status"] == "ready":
        summary["status"] = "ready"
    else:
        summary["status"] = "failed_browser_runtime"
    evidence = evidence_root / f"doctor-{evidence_token(batch_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print(json.dumps({**summary, "evidence": str(evidence)}, ensure_ascii=True, indent=2))
    return 0 if summary["status"] == "ready" else 4


if __name__ == "__main__":
    raise SystemExit(main())
