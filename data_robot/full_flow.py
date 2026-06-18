from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from data_robot.common import DEFAULT_ARCHIVE_ROOT, DEFAULT_EVIDENCE_ROOT, evidence_token, hourly_batch_token, print_json, write_json
from data_robot.verify_batch import verify_batch


ROOT = Path(__file__).resolve().parents[1]
OPENPYXL_DEFAULT_STYLE_WARNING_FILTER = "ignore:Workbook contains no default style:UserWarning"


def child_python_warnings(existing: str | None) -> str:
    if not existing:
        return OPENPYXL_DEFAULT_STYLE_WARNING_FILTER
    parts = [part.strip() for part in existing.split(",") if part.strip()]
    if OPENPYXL_DEFAULT_STYLE_WARNING_FILTER not in parts:
        parts.append(OPENPYXL_DEFAULT_STYLE_WARNING_FILTER)
    return ",".join(parts)


def run_command(command: list[str], *, timeout: int) -> dict[str, Any]:
    started = datetime.now()
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env["PYTHONWARNINGS"] = child_python_warnings(env.get("PYTHONWARNINGS"))
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        return {
            "command": command,
            "returncode": 124,
            "timed_out": True,
            "timeout_seconds": timeout,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "stdout_tail": stdout[-12000:],
            "stderr_tail": stderr[-12000:],
        }
    return {
        "command": command,
        "returncode": completed.returncode,
        "timed_out": False,
        "timeout_seconds": timeout,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "stdout_tail": completed.stdout[-12000:],
        "stderr_tail": completed.stderr[-12000:],
    }


def latest_evidence(evidence_root: Path, prefix: str) -> str:
    files = sorted(evidence_root.glob(f"{prefix}*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return str(files[0]) if files else ""


def read_json(path: str) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def import_failed_on_external_dependency(import_summary: dict[str, Any] | None) -> bool:
    if not import_summary:
        return False
    error = import_summary.get("error") or {}
    text = f"{error.get('type', '')} {error.get('message', '')} {error.get('traceback_tail', '')}"
    markers = (
        "IP白名单",
        "验证IP无效",
        "jushuitan",
        "Jushuitan",
        "聚水潭",
        "Feishu",
        "飞书",
        "requests.exceptions",
    )
    return any(marker in text for marker in markers)


def download_failed_on_browser_connection(download_summary: dict[str, Any] | None) -> bool:
    if not download_summary:
        return False
    markers = (
        "connect_over_cdp",
        "retrieving websocket url",
        "URLError",
        "ConnectionClosedError",
        "ConnectionRefusedError",
        "CDP",
    )
    texts: list[str] = []
    for platform_result in download_summary.get("results") or []:
        for task_result in platform_result.get("results") or []:
            if task_result.get("status") == "error":
                texts.append(str(task_result.get("error", "")))
    return bool(texts) and all(any(marker in text for marker in markers) for text in texts)


def build_doctor_command(args: argparse.Namespace, date_token: str, batch_hour: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "data_robot.doctor",
        "--date-token",
        date_token,
        "--batch-hour",
        batch_hour,
        "--archive-root",
        args.archive_root,
        "--evidence-root",
        args.evidence_root,
        "--browser-profile-suffix",
        args.doctor_profile_suffix,
    ]
    if args.browser_profile_root:
        command.extend(["--browser-profile-root", args.browser_profile_root])
    return command


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
    for platform in args.platform or []:
        command.extend(["--platform", platform])
    for task in args.task or []:
        command.extend(["--task", task])
    if args.force:
        command.append("--force")
    if args.flat_date_folder:
        command.append("--flat-date-folder")
    if args.no_cdp:
        command.append("--no-cdp")
    if args.direct_cdp:
        command.append("--direct-cdp")
    if args.manual:
        command.append("--manual")
    if args.auto_actions:
        command.append("--auto-actions")
    if args.skip_final_verify:
        command.append("--skip-final-verify")
    return command


def build_playwright_check_command() -> list[str]:
    code = (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    print(p.chromium.name)\n"
    )
    return [sys.executable, "-c", code]


def build_import_command(args: argparse.Namespace, batch_dir: Path) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "import_daily_files_to_feishu.py"),
        "--batch-dir",
        str(batch_dir),
        "--evidence",
        args.import_evidence,
    ]
    if args.dry_run_import:
        command.append("--dry-run")
    for platform in args.import_platform or []:
        command.extend(["--platform", platform])
    for kind in args.import_kind or []:
        command.extend(["--kind", kind])
    for date in args.import_date or []:
        command.extend(["--date", date])
    if args.filter_ad_dates:
        command.append("--filter-ad-dates")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ShopOps downloader, verify the batch, then import it into Feishu.")
    parser.add_argument("--date-token", default=datetime.now().strftime("%m%d"))
    parser.add_argument("--batch-hour", default=datetime.now().strftime("%H"), help="Hourly archive subfolder. Defaults to current hour.")
    parser.add_argument("--flat-date-folder", action="store_true", help="Use the old docs/data/ShopOps/<MMDD> layout without an hourly subfolder.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--watch-dir", default=str(Path.home() / "Downloads"))
    parser.add_argument("--platform", action="append", choices=("pinduoduo", "wechat_channels", "douyin", "tmall"))
    parser.add_argument("--task", action="append")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--idle-seconds", type=int, default=30)
    parser.add_argument("--max-downloads", type=int, default=5)
    parser.add_argument("--min-task-interval-seconds", type=int, default=480)
    parser.add_argument("--retry-interval-seconds", type=int, default=480)
    parser.add_argument("--max-task-attempts", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-cdp", action="store_true")
    parser.add_argument("--direct-cdp", action="store_true", help="Use direct CDP instead of Playwright for the download step.")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--auto-actions", action="store_true")
    parser.add_argument("--skip-doctor-check", action="store_true", help="Skip the data_robot.doctor runtime gate before downloading.")
    parser.add_argument("--doctor-profile-suffix", default="doctor", help="Temporary browser profile suffix used only by the runtime doctor.")
    parser.add_argument(
        "--browser-profile-suffix",
        default="cdp",
        help="Profile suffix under data_robot/profiles for externally launched CDP browsers.",
    )
    parser.add_argument("--browser-profile-root", default="", help="Root folder for browser user-data profiles.")
    parser.add_argument("--skip-download", action="store_true", help="Only verify and import an existing archived batch.")
    parser.add_argument("--skip-playwright-check", action="store_true", help="Skip the Playwright runtime preflight before downloading.")
    parser.add_argument("--skip-final-verify", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-existing-archive", action="store_true", help="Continue importing when the archive is complete even if fresh download had errors.")
    parser.add_argument("--dry-run-import", action="store_true")
    parser.add_argument("--import-platform", action="append")
    parser.add_argument("--import-kind", action="append", choices=("orders", "ads", "influencer"))
    parser.add_argument("--import-date", action="append")
    parser.add_argument("--filter-ad-dates", action="store_true")
    parser.add_argument("--import-timeout-seconds", type=int, default=1200)
    args = parser.parse_args()

    date_token = args.date_token
    batch_token = date_token if args.flat_date_folder else hourly_batch_token(date_token, args.batch_hour)
    safe_batch_token = evidence_token(batch_token)
    evidence_root = Path(args.evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)
    batch_dir = Path(args.archive_root) / batch_token
    args.import_evidence = str(evidence_root / f"full-flow-import-{safe_batch_token}-{datetime.now().strftime('%H%M%S')}.json")

    download_result = None
    download_evidence = ""
    doctor_result = None
    doctor_evidence = ""
    doctor_summary = None
    playwright_check = None
    if not args.skip_download:
        if not args.skip_doctor_check:
            doctor_result = run_command(build_doctor_command(args, date_token, args.batch_hour), timeout=120)
            doctor_evidence = latest_evidence(evidence_root, f"doctor-{safe_batch_token}-")
            doctor_summary = read_json(doctor_evidence)
        if doctor_result is None or doctor_result["returncode"] == 0:
            if not args.skip_playwright_check and not args.direct_cdp:
                playwright_check = run_command(build_playwright_check_command(), timeout=60)
        if (doctor_result is None or doctor_result["returncode"] == 0) and (playwright_check is None or playwright_check["returncode"] == 0):
            download_command = build_download_command(args, date_token, args.batch_hour)
            download_result = run_command(download_command, timeout=max(args.import_timeout_seconds, args.timeout_seconds * args.max_task_attempts * 8))
            download_evidence = latest_evidence(evidence_root, f"daily-download-{safe_batch_token}-")

    verification = verify_batch(batch_dir)
    import_result = None
    import_summary = None
    can_import = verification["status"] == "complete"
    download_summary = read_json(download_evidence)
    playwright_ok = playwright_check is None or playwright_check["returncode"] == 0
    fresh_download_ok = args.skip_download or (download_summary or {}).get("status") == "downloaded"
    if can_import and (fresh_download_ok or args.allow_existing_archive):
        import_result = run_command(build_import_command(args, batch_dir), timeout=args.import_timeout_seconds)
        import_summary = read_json(args.import_evidence)

    status = "success"
    doctor_ok = doctor_result is None or doctor_result["returncode"] == 0
    if not doctor_ok:
        status = "failed_preflight"
    elif not playwright_ok:
        status = "failed_browser_runtime"
    elif download_failed_on_browser_connection(download_summary):
        status = "failed_browser_connection"
    elif not can_import:
        status = "failed_archive_incomplete"
    elif import_result is None:
        status = "failed_download"
    elif import_result.get("timed_out"):
        status = "failed_import_timeout"
    elif import_failed_on_external_dependency(import_summary):
        status = "failed_external_dependency"
    elif import_result["returncode"] != 0 or (import_summary or {}).get("status") not in {"success", "dry_run"}:
        status = "failed_import"
    elif not fresh_download_ok:
        status = "success_with_download_warnings"

    summary = {
        "status": status,
        "date_token": date_token,
        "batch_token": batch_token,
        "batch_dir": str(batch_dir),
        "download": download_result,
        "download_evidence": download_evidence,
        "download_summary": download_summary,
        "doctor": doctor_result,
        "doctor_evidence": doctor_evidence,
        "doctor_summary": doctor_summary,
        "playwright_check": playwright_check,
        "verification": verification,
        "import": import_result,
        "import_evidence": args.import_evidence if import_result else "",
        "import_summary": import_summary,
        "allow_existing_archive": args.allow_existing_archive,
    }
    evidence = evidence_root / f"full-flow-{safe_batch_token}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({**summary, "evidence": str(evidence)})
    return 0 if status in {"success", "success_with_download_warnings"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
