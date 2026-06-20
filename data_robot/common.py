from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import urllib.request

from data_robot.tasks import PLATFORM_TASKS, TASKS, RobotTask


ROOT = Path(__file__).resolve().parents[1]
DATA_ROBOT_DIR = ROOT / "data_robot"
DEFAULT_ARCHIVE_ROOT = ROOT / "docs" / "data" / "ShopOps_Order"
DEFAULT_EVIDENCE_ROOT = ROOT / "docs" / "live-evidence" / "data-robot"
DOWNLOAD_ROOT = DATA_ROBOT_DIR / "downloads"
PROFILE_ROOT = DATA_ROBOT_DIR / "profiles"
ACTION_ROOT = DATA_ROBOT_DIR / "actions"
STATE_ROOT = DATA_ROBOT_DIR / ".state"
COOLDOWN_STATE_PATH = STATE_ROOT / "download_cooldown.json"
GLOBAL_EXPORT_COOLDOWN_KEY = "__global_export__"
TMALL_ORDER_EXPORT_LIST_URL = "https://myseller.taobao.com/home.htm/trade-platform/tp/export-list"

USERNAME_SELECTORS = (
    "input[name='fm-login-id']",
    "input[name='loginId']",
    "input[name='TPL_username']",
    "input[name='username']",
    "input[name='account']",
    "input[type='tel']",
    "input[type='text']",
    "input[placeholder*='账号']",
    "input[placeholder*='会员名']",
    "input[placeholder*='手机号']",
)

PASSWORD_SELECTORS = (
    "input[name='fm-login-password']",
    "input[name='TPL_password']",
    "input[name='password']",
    "input[type='password']",
    "input[placeholder*='密码']",
)

LOGIN_BUTTON_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    ".fm-button",
    "#login-form button",
    "[class*='login'] button",
)

TASK_FILENAME_HINTS = {
    "pinduoduo_orders": ("orders_export", "订单"),
    "pinduoduo_ads": ("商品推广", "账户", "分天数据"),
    "wechat_channels_orders": ("微信小店订单",),
    "douyin_ads": ("全域推广数据", "商品"),
    "tmall_orders": ("ExportOrderList",),
    "tmall_ads": ("营销场景报表",),
}


def json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, default=str)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text(payload), encoding="utf-8")


def print_json(payload: Any) -> None:
    print(json_text(payload), flush=True)


def evidence_token(token: str) -> str:
    return re.sub(r"[\\/:\s]+", "-", token).strip("-") or "batch"


def hourly_batch_token(date_token: str, batch_hour: str = "") -> str:
    hour = batch_hour or datetime.now().strftime("%H")
    hour_label = hour if hour.endswith("下载") else f"{hour}点下载"
    return f"{date_token}/{hour_label}"


@dataclass(frozen=True)
class CollectOptions:
    archive_root: Path = DEFAULT_ARCHIVE_ROOT
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT
    headed: bool = True
    manual: bool = False
    timeout_seconds: int | None = None
    idle_seconds: int = 20
    max_downloads: int = 5
    dry_run_import: bool = True
    skip_import_check: bool = False
    browser_channel: str = "chrome"
    cdp_url: str = ""
    direct_cdp: bool = False
    watch_dir: Path | None = None
    min_task_interval_seconds: int = 480
    retry_interval_seconds: int = 480
    max_task_attempts: int = 5
    force: bool = False


@dataclass(frozen=True)
class ArchivedFile:
    source: Path
    archived: Path
    extracted_from: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "archived": str(self.archived),
            "extracted_from": str(self.extracted_from) if self.extracted_from else "",
            "size_bytes": self.archived.stat().st_size if self.archived.exists() else 0,
        }


def parse_common_args(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--task", action="append", choices=sorted(TASKS), help="Only run selected task key; repeatable.")
    parser.add_argument("--date-token", default="", help="Archive date directory, e.g. 0612. Defaults to today.")
    parser.add_argument("--batch-hour", default="", help="Hourly archive subfolder, e.g. 23. Defaults to current hour.")
    parser.add_argument("--flat-date-folder", action="store_true", help="Use the old docs/data/ShopOps/<MMDD> layout without an hourly subfolder.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help="Root folder for normalized daily files.")
    parser.add_argument("--timeout-seconds", type=int, default=0, help="Download wait timeout. 0 uses task default.")
    parser.add_argument("--idle-seconds", type=int, default=20, help="After the first download, keep watching this many seconds.")
    parser.add_argument("--max-downloads", type=int, default=5, help="Maximum downloads to capture per task.")
    parser.add_argument("--auto-actions", action="store_true", help="Run JSON actions from data_robot/actions/<task>.json when present.")
    parser.add_argument("--manual", action="store_true", help="Open the page and wait for you to click export/download manually.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Use only after selectors are stable.")
    parser.add_argument("--browser-channel", default="chrome", help="Playwright browser channel. Default: chrome. Use empty string for bundled Chromium.")
    parser.add_argument("--cdp-url", default="", help="Attach to an existing Chrome remote debugging URL, e.g. http://127.0.0.1:9222.")
    parser.add_argument("--direct-cdp", action="store_true", help="Use a lightweight CDP client instead of the Playwright driver. Requires --cdp-url.")
    parser.add_argument("--watch-dir", default="", help="Also archive new csv/xls/xlsx/zip files created in this folder during the run.")
    parser.add_argument("--min-task-interval-seconds", type=int, default=480, help="Minimum interval between two export attempts for the same task. Default: 480 seconds.")
    parser.add_argument("--retry-interval-seconds", type=int, default=480, help="Wait this many seconds before retrying a task that produced no download. Default: 480 seconds.")
    parser.add_argument("--max-task-attempts", type=int, default=5, help="Maximum attempts per task before skipping to the next task. Default: 5.")
    parser.add_argument("--force", action="store_true", help="Bypass the anti-risk cooldown.")
    parser.add_argument("--run-import-check", action="store_true", help="Optional: run import_daily_files_to_feishu.py dry-run after archiving.")
    parser.add_argument("--skip-import-check", action="store_true", help=argparse.SUPPRESS)
    return parser


def options_from_args(args: argparse.Namespace) -> CollectOptions:
    return CollectOptions(
        archive_root=Path(args.archive_root),
        headed=not args.headless,
        manual=args.manual,
        timeout_seconds=args.timeout_seconds or None,
        idle_seconds=args.idle_seconds,
        max_downloads=args.max_downloads,
        skip_import_check=not args.run_import_check or args.skip_import_check,
        browser_channel=args.browser_channel,
        cdp_url=args.cdp_url,
        direct_cdp=args.direct_cdp,
        watch_dir=Path(args.watch_dir) if args.watch_dir else None,
        min_task_interval_seconds=max(0, args.min_task_interval_seconds),
        retry_interval_seconds=max(0, args.retry_interval_seconds),
        max_task_attempts=max(1, args.max_task_attempts),
        force=args.force,
    )


def resolve_task_keys(platform: str, selected: list[str] | None) -> list[str]:
    allowed = list(PLATFORM_TASKS[platform])
    if not selected:
        return allowed
    return [key for key in selected if key in allowed]


async def run_platform(platform: str, args: argparse.Namespace) -> dict[str, Any]:
    options = options_from_args(args)
    date_token = args.date_token or datetime.now().strftime("%m%d")
    if hasattr(args, "batch_hour") and not getattr(args, "flat_date_folder", False):
        date_token = hourly_batch_token(date_token, getattr(args, "batch_hour", ""))
    results = []
    for key in resolve_task_keys(platform, args.task):
        result = await collect_task_with_retries(TASKS[key], options, date_token=date_token, use_actions=args.auto_actions)
        results.append(result)
    summary = {
        "status": summarize_task_results(results),
        "platform": platform,
        "date_token": date_token,
        "results": results,
    }
    evidence = options.evidence_root / f"{platform}-{evidence_token(date_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({**summary, "evidence": str(evidence)})
    return summary


async def collect_task_with_retries(
    task: RobotTask,
    options: CollectOptions,
    *,
    date_token: str,
    use_actions: bool = False,
) -> dict[str, Any]:
    attempt_results: list[dict[str, Any]] = []
    for attempt in range(1, options.max_task_attempts + 1):
        try:
            result = await collect_task(task, options, date_token=date_token, use_actions=use_actions)
        except Exception as exc:
            result = {
                "task": task.key,
                "status": "error",
                "platform": task.platform,
                "kind": task.kind,
                "error": f"{type(exc).__name__}: {exc}",
                "downloaded": [],
                "archived": [],
                "manifest": "",
                "import_check": None,
            }
        result["attempt"] = attempt
        attempt_results.append(result)
        if not should_retry_task_result(result) or attempt >= options.max_task_attempts:
            final = dict(result)
            final["attempts"] = attempt
            if attempt > 1:
                final["previous_attempts"] = attempt_results[:-1]
            return final
        wait_seconds = retry_wait_seconds(result, options)
        print(
            f"[{task.key}] attempt {attempt}/{options.max_task_attempts} ended with {result['status']}; "
            f"waiting {wait_seconds} seconds before retry.",
            flush=True,
        )
        await asyncio.sleep(wait_seconds)
    return attempt_results[-1]


def should_retry_task_result(result: dict[str, Any]) -> bool:
    status = str(result.get("status", ""))
    if status in {"no_download", "skipped_cooldown"}:
        return True
    return status == "error" and (is_recoverable_cdp_error(result) or is_recoverable_export_error(result))


def is_recoverable_cdp_error(result: dict[str, Any]) -> bool:
    error = str(result.get("error", ""))
    markers = (
        "connect_over_cdp",
        "retrieving websocket url",
        "URLError",
        "ConnectionClosedError",
        "ConnectionRefusedError",
        "CDP",
        "TimeoutError",
    )
    return any(marker in error for marker in markers)


def is_recoverable_export_error(result: dict[str, Any]) -> bool:
    error = str(result.get("error", ""))
    markers = (
        "HTTP Error 429",
        "HTTP Error 500",
        "HTTP Error 502",
        "HTTP Error 503",
        "HTTP Error 504",
        "Bad Gateway",
        "Service Unavailable",
        "Gateway Timeout",
        "Too Many Requests",
    )
    return any(marker in error for marker in markers)


def retry_wait_seconds(result: dict[str, Any], options: CollectOptions) -> int:
    if str(result.get("status", "")) == "error" and is_recoverable_cdp_error(result):
        return min(60, max(5, options.retry_interval_seconds))
    if str(result.get("status", "")) == "skipped_cooldown":
        remaining = int(result.get("cooldown_remaining_seconds") or options.retry_interval_seconds)
        return max(5, min(options.retry_interval_seconds, remaining))
    return options.retry_interval_seconds


def summarize_task_results(results: list[dict[str, Any]]) -> str:
    statuses = [str(item.get("status", "")) for item in results]
    if not statuses:
        return "empty"
    if all(status == "downloaded" for status in statuses):
        return "downloaded"
    if all(status == "skipped_cooldown" for status in statuses):
        return "skipped_cooldown"
    if any(status == "error" for status in statuses):
        return "finished_with_errors"
    if any(status == "no_download" for status in statuses):
        return "finished_with_missing_downloads"
    if any(status == "skipped_cooldown" for status in statuses):
        return "finished_with_skips"
    return "finished_with_unknown_status"


def summarize_platform_results(results: list[dict[str, Any]]) -> str:
    statuses = [str(item.get("status", "")) for item in results]
    if not statuses:
        return "empty"
    if all(status == "downloaded" for status in statuses):
        return "downloaded"
    if all(status == "skipped_cooldown" for status in statuses):
        return "skipped_cooldown"
    if any(status == "finished_with_errors" for status in statuses):
        return "finished_with_errors"
    if any(status == "finished_with_missing_downloads" for status in statuses):
        return "finished_with_missing_downloads"
    if any(status in {"finished_with_skips", "skipped_cooldown"} for status in statuses):
        return "finished_with_skips"
    return "finished_with_unknown_status"


async def collect_task(task: RobotTask, options: CollectOptions, *, date_token: str, use_actions: bool = False) -> dict[str, Any]:
    if options.direct_cdp:
        return await collect_task_direct_cdp(task, options, date_token=date_token, use_actions=use_actions)

    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright

    run_token = datetime.now().strftime("%Y%m%d-%H%M%S")
    download_dir = DOWNLOAD_ROOT / run_token / task.key
    download_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = PROFILE_ROOT / task.profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    timeout_ms = (options.timeout_seconds or task.default_timeout_seconds) * 1000
    started_at = datetime.now().timestamp()
    downloaded: list[Path] = []
    diagnostics: dict[str, Any] = {
        "page_url": "",
        "page_title": "",
        "local_capture_dir": str(download_dir),
        "watch_dir": str(options.watch_dir) if options.watch_dir else "",
    }
    task_cooldown = cooldown_remaining(task.key, options.min_task_interval_seconds)
    global_cooldown = cooldown_remaining(GLOBAL_EXPORT_COOLDOWN_KEY, options.min_task_interval_seconds)
    cooldown = max(task_cooldown, global_cooldown)
    if cooldown > 0 and not options.force:
        return {
            "task": task.key,
            "status": "skipped_cooldown",
            "platform": task.platform,
            "kind": task.kind,
            "cooldown_remaining_seconds": cooldown,
            "task_cooldown_remaining_seconds": task_cooldown,
            "global_cooldown_remaining_seconds": global_cooldown,
            "downloaded": [],
            "watch_dir": str(options.watch_dir) if options.watch_dir else "",
            "diagnostics": diagnostics,
            "archived": [],
            "manifest": "",
            "import_check": None,
        }

    async with async_playwright() as playwright:
        browser = None
        if options.cdp_url:
            browser = await connect_over_cdp_with_retry(playwright, options.cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context(accept_downloads=True)
            page = await select_page_for_task(context, task)
        else:
            launch_kwargs: dict[str, Any] = {}
            if options.browser_channel:
                launch_kwargs["channel"] = options.browser_channel
            context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                accept_downloads=True,
                downloads_path=str(download_dir),
                headless=not options.headed,
                viewport={"width": 1440, "height": 960},
                **launch_kwargs,
            )
            page = context.pages[0] if context.pages else await context.new_page()
        if not should_preserve_current_page(task, page.url):
            await page.goto(task.url, wait_until="domcontentloaded", timeout=120_000)
        await page.bring_to_front()
        record_export_attempt(task.key, datetime.now().timestamp())
        record_export_attempt(GLOBAL_EXPORT_COOLDOWN_KEY, datetime.now().timestamp())

        try:
            first_download_task = asyncio.create_task(page.wait_for_event("download", timeout=timeout_ms))
            if use_actions:
                await run_actions(page, task)
            elif options.manual:
                print(f"[{task.key}] Browser opened. Log in if needed, set the date range, then click the export/download button.", flush=True)
            else:
                print(f"[{task.key}] Browser opened. The robot will try export/download buttons automatically after login.", flush=True)
                await run_smart_export(
                    page,
                    task,
                    timeout_ms=timeout_ms,
                    download_task=first_download_task,
                    watch_dir=options.watch_dir,
                    started_at=started_at,
                )
            first_download = None
            watched_files: list[Path] = []
            if options.watch_dir:
                first_download, watched_files = await wait_for_first_download_or_watched_file(
                    first_download_task,
                    options.watch_dir,
                    started_at,
                    timeout_seconds=timeout_ms / 1000,
                    limit=options.max_downloads,
                )
            else:
                try:
                    first_download = await first_download_task
                except PlaywrightTimeoutError:
                    first_download = None
            if first_download is not None:
                downloaded.append(await save_download(first_download, download_dir))
                while len(downloaded) < options.max_downloads:
                    try:
                        next_download = await page.wait_for_event("download", timeout=options.idle_seconds * 1000)
                        downloaded.append(await save_download(next_download, download_dir))
                    except PlaywrightTimeoutError:
                        break
            downloaded.extend(watched_files)
            diagnostics.update(await collect_page_diagnostics(page))
        finally:
            if "first_download_task" in locals() and not first_download_task.done():
                first_download_task.cancel()
            if browser is not None:
                # Keep externally launched Chrome alive; in CDP mode the user owns that browser.
                pass
            else:
                await context.close()

    if options.watch_dir:
        watched = wait_for_watched_files(
            options.watch_dir,
            started_at,
            limit=options.max_downloads,
            timeout_seconds=max(1, options.idle_seconds),
        )
        known = {path.resolve() for path in downloaded if path.exists()}
        downloaded.extend(path for path in watched if path.resolve() not in known)

    archived = archive_downloads(task, downloaded, options.archive_root, date_token=date_token, run_token=run_token)
    manifest_path = write_archive_manifest(
        task,
        archived,
        options.archive_root,
        date_token=date_token,
        run_token=run_token,
        downloaded=downloaded,
    )
    import_check = None
    if archived and not options.skip_import_check:
        import_check = run_import_check(
            batch_dir=options.archive_root / date_token,
            platform=task.platform,
            kind=task.kind,
            evidence_root=options.evidence_root,
            date_token=date_token,
            task_key=task.key,
        )
    return {
        "task": task.key,
        "status": "downloaded" if archived else "no_download",
        "platform": task.platform,
        "kind": task.kind,
        "downloaded": [str(path) for path in downloaded],
        "watch_dir": str(options.watch_dir) if options.watch_dir else "",
        "diagnostics": diagnostics,
        "archived": [str(item.archived) for item in archived],
        "manifest": str(manifest_path) if manifest_path else "",
        "import_check": import_check,
    }


async def collect_page_diagnostics(page: Any) -> dict[str, str]:
    diagnostics = {"page_url": "", "page_title": ""}
    try:
        diagnostics["page_url"] = str(page.url)
    except Exception:
        pass
    try:
        diagnostics["page_title"] = str(await page.title())
    except Exception:
        pass
    return diagnostics


def cooldown_remaining(task_key: str, min_interval_seconds: int) -> int:
    if min_interval_seconds <= 0:
        return 0
    state = read_cooldown_state()
    last_attempt = float(state.get(task_key, 0) or 0)
    return compute_cooldown_remaining(last_attempt, min_interval_seconds, now=time.time())


def compute_cooldown_remaining(last_attempt: float, min_interval_seconds: int, *, now: float | None = None) -> int:
    if min_interval_seconds <= 0 or last_attempt <= 0:
        return 0
    elapsed = (now if now is not None else time.time()) - last_attempt
    remaining = int(min_interval_seconds - elapsed)
    return max(0, remaining)


def record_export_attempt(task_key: str, timestamp: float | None = None) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    state = read_cooldown_state()
    state[task_key] = timestamp or time.time()
    write_json(COOLDOWN_STATE_PATH, state)


def read_cooldown_state() -> dict[str, float]:
    if not COOLDOWN_STATE_PATH.exists():
        return {}
    try:
        payload = json.loads(COOLDOWN_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): float(value) for key, value in payload.items() if isinstance(value, int | float)}


def load_local_env_files() -> None:
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def read_dpapi_login_credential(platform_code: str) -> tuple[str, str] | None:
    secret_root = Path(os.getenv("SHOPOPS_SECRET_ROOT", os.path.expandvars(r"%APPDATA%\ShopOps\secrets")))
    path = secret_root / f"{platform_code}-login.credential.xml"
    if not path.exists():
        return None
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "$c = Import-Clixml -LiteralPath $args[0]; "
            "$p = $c.GetNetworkCredential().Password; "
            "[Console]::Out.Write(($c.UserName + [char]0x1f + $p))"
        ),
        str(path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=20, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or "\x1f" not in completed.stdout:
        return None
    username, password = completed.stdout.split("\x1f", 1)
    username = username.strip()
    password = password.strip()
    if username and password:
        return username, password
    return None


def get_login_credentials(platform_code: str) -> tuple[str, str]:
    load_local_env_files()
    platform = platform_code.upper()
    prefixes = [f"SHOPOPS_{platform}_", f"{platform}_"]
    if platform_code == "tmall":
        prefixes.extend(["SHOPOPS_QIANNIU_", "QIANNIU_", "SHOPOPS_TAOBAO_", "TAOBAO_"])
    if platform_code == "douyin":
        prefixes.extend(["SHOPOPS_QIANCHUAN_", "QIANCHUAN_", "SHOPOPS_OCEANENGINE_", "OCEANENGINE_"])
    for prefix in prefixes:
        username = os.getenv(prefix + "USERNAME") or os.getenv(prefix + "ACCOUNT") or os.getenv(prefix + "LOGIN_ID")
        password = os.getenv(prefix + "PASSWORD") or os.getenv(prefix + "PASS")
        if username and password:
            return username, password
    credential = read_dpapi_login_credential(platform_code)
    if credential:
        return credential
    return "", ""


class DirectCdpPage:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.ws: Any = None
        self.next_id = 0
        self.session_id = ""
        self.target_id = ""
        self.close_target_on_exit = False

    async def __aenter__(self) -> "DirectCdpPage":
        import websockets

        with urllib.request.urlopen(f"{self.base_url}/json/version", timeout=5) as response:
            version = json.loads(response.read().decode("utf-8"))
        self.ws = await websockets.connect(
            version["webSocketDebuggerUrl"],
            origin=self.base_url,
            ping_interval=None,
            max_size=16 * 1024 * 1024,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.target_id and self.close_target_on_exit:
            try:
                await self.send("Target.closeTarget", {"targetId": self.target_id})
            except Exception:
                pass
        if self.ws is not None:
            await self.ws.close()

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session: bool = False,
        timeout_seconds: float = 20,
    ) -> dict[str, Any]:
        self.next_id += 1
        message: dict[str, Any] = {"id": self.next_id, "method": method}
        if params:
            message["params"] = params
        if session:
            message["sessionId"] = self.session_id
        await asyncio.wait_for(self.ws.send(json.dumps(message)), timeout=timeout_seconds)
        while True:
            response = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=timeout_seconds))
            if response.get("id") != self.next_id:
                continue
            if "error" in response:
                raise RuntimeError(f"CDP {method} failed: {response['error']}")
            return response.get("result") or {}

    async def open(self, url: str, *, download_dir: Path) -> None:
        await self.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(download_dir)})
        target_id = await self.reusable_target_id(url)
        if target_id:
            await self.attach(target_id, close_on_exit=False)
        else:
            created = await self.send("Target.createTarget", {"url": "about:blank"})
            self.target_id = str(created["targetId"])
            await self.attach(self.target_id, close_on_exit=True)
        await self.navigate(url)
        await self.close_duplicate_targets(url)

    async def reusable_target_id(self, url: str) -> str:
        targets = await self.send("Target.getTargets")
        return direct_cdp_reusable_target_id(targets.get("targetInfos") or [], url)

    async def close_duplicate_targets(self, url: str) -> list[str]:
        targets = await self.send("Target.getTargets")
        closed: list[str] = []
        for target_id in direct_cdp_duplicate_target_ids(
            targets.get("targetInfos") or [],
            url,
            keep_target_id=self.target_id,
        ):
            try:
                await self.send("Target.closeTarget", {"targetId": target_id})
                closed.append(target_id)
            except Exception:
                pass
        return closed

    async def attach(self, target_id: str, *, close_on_exit: bool = False) -> None:
        self.target_id = target_id
        self.close_target_on_exit = close_on_exit
        attached = await self.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        self.session_id = str(attached["sessionId"])
        await self.send("Page.enable", session=True)
        await self.send("Runtime.enable", session=True)
        await self.send("Page.bringToFront", session=True)

    async def detach(self) -> None:
        if not self.session_id:
            return
        try:
            await self.send("Target.detachFromTarget", {"sessionId": self.session_id})
        finally:
            self.session_id = ""
            self.target_id = ""
            self.close_target_on_exit = False

    async def navigate(self, url: str) -> None:
        await self.send("Page.navigate", {"url": url}, session=True)
        try:
            await self.wait_ready(timeout_seconds=15)
        except TimeoutError:
            # Some Alibaba/Qianniu pages keep the document busy during login redirects.
            # Continue with the visible page so the login detector can fill credentials.
            return
        except asyncio.TimeoutError:
            return

    async def reload(self) -> None:
        await self.send("Page.reload", {"ignoreCache": True}, session=True)
        try:
            await self.wait_ready(timeout_seconds=15)
        except (TimeoutError, asyncio.TimeoutError):
            return

    async def wait_ready(self, *, timeout_seconds: int) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            state = await self.evaluate("document.readyState", timeout_seconds=3)
            if state in {"interactive", "complete"}:
                await asyncio.sleep(1)
                return
            await asyncio.sleep(0.5)

    async def evaluate(self, expression: str, *, timeout_seconds: int = 10, context_id: int | None = None) -> Any:
        params: dict[str, Any] = {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True,
            "userGesture": True,
        }
        if context_id is not None:
            params["contextId"] = context_id
        result = await asyncio.wait_for(
            self.send("Runtime.evaluate", params, session=True),
            timeout=timeout_seconds,
        )
        remote = result.get("result") or {}
        return remote.get("value")

    async def frame_contexts(self, *, timeout_seconds: int = 10) -> list[dict[str, Any]]:
        def collect(frame_tree: dict[str, Any], output: list[dict[str, Any]]) -> None:
            frame = frame_tree.get("frame") or {}
            frame_id = str(frame.get("id") or "")
            if frame_id:
                output.append(
                    {
                        "frame_id": frame_id,
                        "url": str(frame.get("url") or ""),
                        "name": str(frame.get("name") or ""),
                    }
                )
            for child in frame_tree.get("childFrames") or []:
                collect(child, output)

        tree = await asyncio.wait_for(self.send("Page.getFrameTree", session=True), timeout=timeout_seconds)
        frames: list[dict[str, Any]] = []
        collect(tree.get("frameTree") or {}, frames)
        contexts: list[dict[str, Any]] = []
        for frame in frames:
            try:
                created = await asyncio.wait_for(
                    self.send(
                        "Page.createIsolatedWorld",
                        {
                            "frameId": frame["frame_id"],
                            "worldName": "shopops-login",
                            "grantUniveralAccess": True,
                        },
                        session=True,
                    ),
                    timeout=timeout_seconds,
                )
            except Exception as exc:
                contexts.append({**frame, "error": str(exc)})
                continue
            context_id = created.get("executionContextId")
            if isinstance(context_id, int):
                contexts.append({**frame, "context_id": context_id})
        return contexts

    async def click_label(self, label: str, *, exact: bool = False) -> str | None:
        payload = json.dumps({"label": label, "exact": exact}, ensure_ascii=False)
        expression = r"""
        ((payload) => {
          const { label, exact } = JSON.parse(payload);
          const collect = (root) => {
            const found = Array.from(root.querySelectorAll('button,a,[role=button],div,span'));
            const nested = Array.from(root.querySelectorAll('*'))
              .filter((element) => element.shadowRoot)
              .flatMap((element) => collect(element.shadowRoot));
            return found.concat(nested);
          };
          const visible = (element) => {
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          };
          const candidates = collect(document).filter((element) => {
            const text = (element.innerText || element.textContent || '').trim();
            if (exact ? text !== label : !text.includes(label)) return false;
            return visible(element);
          });
          candidates.sort((left, right) => {
            const leftRole = /^(BUTTON|A)$/.test(left.tagName) || left.getAttribute('role') === 'button' ? 0 : 1;
            const rightRole = /^(BUTTON|A)$/.test(right.tagName) || right.getAttribute('role') === 'button' ? 0 : 1;
            if (leftRole !== rightRole) return leftRole - rightRole;
            const leftText = (left.innerText || left.textContent || '').trim();
            const rightText = (right.innerText || right.textContent || '').trim();
            return leftText.length - rightText.length;
          });
          const candidate = candidates[0];
          if (!candidate) return '';
          candidate.scrollIntoView({ block: 'center', inline: 'center' });
          candidate.click();
          return candidate.tagName.toLowerCase();
        })(""" + json.dumps(payload) + ")"
        clicked = await self.evaluate(expression, timeout_seconds=5)
        return f"direct-cdp {clicked}" if clicked else None


async def collect_task_direct_cdp(
    task: RobotTask,
    options: CollectOptions,
    *,
    date_token: str,
    use_actions: bool = False,
) -> dict[str, Any]:
    if not options.cdp_url:
        raise RuntimeError("--direct-cdp requires --cdp-url")
    if use_actions:
        print("[direct-cdp] action JSON is not supported; using built-in smart export clicks.", flush=True)

    run_token = datetime.now().strftime("%Y%m%d-%H%M%S")
    download_dir = DOWNLOAD_ROOT / run_token / task.key
    download_dir.mkdir(parents=True, exist_ok=True)
    timeout_seconds = options.timeout_seconds or task.default_timeout_seconds
    started_at = datetime.now().timestamp()
    diagnostics: dict[str, Any] = {
        "page_url": "",
        "page_title": "",
        "local_capture_dir": str(download_dir),
        "watch_dir": str(options.watch_dir) if options.watch_dir else "",
        "engine": "direct-cdp",
    }

    task_cooldown = cooldown_remaining(task.key, options.min_task_interval_seconds)
    global_cooldown = cooldown_remaining(GLOBAL_EXPORT_COOLDOWN_KEY, options.min_task_interval_seconds)
    cooldown = max(task_cooldown, global_cooldown)
    if cooldown > 0 and not options.force:
        return {
            "task": task.key,
            "status": "skipped_cooldown",
            "platform": task.platform,
            "kind": task.kind,
            "cooldown_remaining_seconds": cooldown,
            "task_cooldown_remaining_seconds": task_cooldown,
            "global_cooldown_remaining_seconds": global_cooldown,
            "downloaded": [],
            "watch_dir": str(options.watch_dir) if options.watch_dir else "",
            "diagnostics": diagnostics,
            "archived": [],
            "manifest": "",
            "import_check": None,
        }

    async with DirectCdpPage(options.cdp_url) as page:
        await page.open(direct_cdp_initial_url(task), download_dir=download_dir)
        login_result = await direct_cdp_login_if_needed(page, task, timeout_seconds=min(timeout_seconds, 240))
        diagnostics["login"] = login_result
        record_export_attempt(task.key, datetime.now().timestamp())
        record_export_attempt(GLOBAL_EXPORT_COOLDOWN_KEY, datetime.now().timestamp())
        if options.manual:
            print(f"[{task.key}] Direct CDP page opened. Click export/download manually in the browser.", flush=True)
            export_started = True
        else:
            print(f"[{task.key}] Direct CDP opened the page and will try export/download buttons.", flush=True)
            export_started = await run_direct_cdp_smart_export(
                page,
                task,
                timeout_seconds=timeout_seconds,
                watch_dirs=[download_dir, *( [options.watch_dir] if options.watch_dir else [] )],
                started_at=started_at,
            )
        download_wait_seconds = timeout_seconds if export_started else min(timeout_seconds, max(30, options.idle_seconds))
        downloaded = wait_for_direct_cdp_downloads(
            [download_dir, *( [options.watch_dir] if options.watch_dir else [] )],
            started_at,
            limit=options.max_downloads,
            timeout_seconds=download_wait_seconds,
            idle_seconds=options.idle_seconds,
        )
        if task.key == "tmall_orders":
            downloaded, diagnostics["tmall_order_export_date_check"] = filter_tmall_order_exports_for_today(downloaded)
        diagnostics["page_url"] = str(await page.evaluate("location.href", timeout_seconds=3) or "")
        diagnostics["page_title"] = str(await page.evaluate("document.title", timeout_seconds=3) or "")
        diagnostics["closed_duplicate_targets"] = await page.close_duplicate_targets(task.url)

    archived = archive_downloads(task, downloaded, options.archive_root, date_token=date_token, run_token=run_token)
    manifest_path = write_archive_manifest(
        task,
        archived,
        options.archive_root,
        date_token=date_token,
        run_token=run_token,
        downloaded=downloaded,
    )
    import_check = None
    if archived and not options.skip_import_check:
        import_check = run_import_check(
            batch_dir=options.archive_root / date_token,
            platform=task.platform,
            kind=task.kind,
            evidence_root=options.evidence_root,
            date_token=date_token,
            task_key=task.key,
        )
    return {
        "task": task.key,
        "status": "downloaded" if archived else "no_download",
        "platform": task.platform,
        "kind": task.kind,
        "downloaded": [str(path) for path in downloaded],
        "watch_dir": str(options.watch_dir) if options.watch_dir else "",
        "diagnostics": diagnostics,
        "archived": [str(item.archived) for item in archived],
        "manifest": str(manifest_path) if manifest_path else "",
        "import_check": import_check,
    }


async def run_direct_cdp_smart_export(
    page: DirectCdpPage,
    task: RobotTask,
    *,
    timeout_seconds: int,
    watch_dirs: list[Path],
    started_at: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    if task.key == "tmall_orders":
        return await direct_cdp_export_tmall_orders_default_range(
            page,
            task,
            deadline=deadline,
            watch_dirs=watch_dirs,
            started_at=started_at,
        )
    if await direct_cdp_click_existing_export_result(page, task, deadline=deadline, watch_dirs=watch_dirs, started_at=started_at):
        return True

    clicked = False
    while time.monotonic() < deadline:
        clicked_at = await direct_cdp_special_primary_export(page, task)
        if clicked_at:
            print(f"[{task.key}] direct-cdp clicked primary via {clicked_at}", flush=True)
            clicked = True
            await asyncio.sleep(1.5)
            break
        for label in smart_export_labels(task):
            clicked_at = await page.click_label(label)
            if clicked_at:
                print(f"[{task.key}] direct-cdp clicked primary '{label}' via {clicked_at}", flush=True)
                clicked = True
                await asyncio.sleep(1.5)
                break
        if clicked:
            break
        await asyncio.sleep(1)

    if not clicked:
        print(f"[{task.key}] Direct CDP did not find an export/download button.", flush=True)
        return False

    clicked_followups: set[str] = set()
    followup_deadline = min(deadline, time.monotonic() + followup_poll_seconds(task))
    while time.monotonic() < followup_deadline:
        if direct_cdp_download_started(watch_dirs, started_at):
            return True
        advanced = False
        for label in followup_export_labels(task):
            if label in clicked_followups:
                continue
            clicked_at = await direct_cdp_special_followup_label(page, task, label)
            if not clicked_at:
                clicked_at = await page.click_label(label, exact=followup_label_exact(task, label))
            if clicked_at:
                print(f"[{task.key}] direct-cdp clicked follow-up '{label}' via {clicked_at}", flush=True)
                clicked_followups.add(label)
                advanced = True
                await asyncio.sleep(2)
                if direct_cdp_download_started(watch_dirs, started_at):
                    return True
                break
        if not advanced:
            await asyncio.sleep(1.5)
    return direct_cdp_download_started(watch_dirs, started_at)


def direct_cdp_initial_url(task: RobotTask) -> str:
    if task.key == "tmall_orders":
        return task.url
    return task.url


async def direct_cdp_export_tmall_orders_default_range(
    page: DirectCdpPage,
    task: RobotTask,
    *,
    deadline: float,
    watch_dirs: list[Path],
    started_at: float,
) -> bool:
    await page.navigate(task.url)
    if not await wait_direct_cdp_text(page, ["近3个月", "批量导出"], timeout_seconds=30):
        print(f"[{task.key}] direct-cdp Tmall order page did not finish loading the default 3-month export controls.", flush=True)
        return await direct_cdp_click_existing_export_result(page, task, deadline=deadline, watch_dirs=watch_dirs, started_at=started_at)
    clicked_export = await page.click_label("批量导出", exact=True)
    if not clicked_export:
        clicked_export = await page.click_label("导出订单", exact=True)
    if not clicked_export:
        print(f"[{task.key}] direct-cdp could not find Tmall batch export button after setting date.", flush=True)
        return await direct_cdp_click_existing_export_result(page, task, deadline=deadline, watch_dirs=watch_dirs, started_at=started_at)
    print(f"[{task.key}] direct-cdp clicked Tmall default 3-month batch export via {clicked_export}", flush=True)
    await asyncio.sleep(2)
    clicked_followups: set[str] = set()
    followup_deadline = min(deadline, time.monotonic() + 30)
    while time.monotonic() < followup_deadline:
        if direct_cdp_download_started(watch_dirs, started_at):
            return True
        for label in followup_export_labels(task):
            if label in clicked_followups:
                continue
            clicked_at = await page.click_label(label, exact=followup_label_exact(task, label))
            if clicked_at:
                print(f"[{task.key}] direct-cdp clicked Tmall export follow-up '{label}' via {clicked_at}", flush=True)
                clicked_followups.add(label)
                await asyncio.sleep(3)
                break
        else:
            await asyncio.sleep(2)
    await page.navigate(TMALL_ORDER_EXPORT_LIST_URL)
    await asyncio.sleep(3)
    clicked_report = await direct_cdp_click_tmall_report_covering_today(
        page,
        deadline=min(deadline, time.monotonic() + 30),
        watch_dirs=watch_dirs,
        started_at=started_at,
    )
    if not clicked_report:
        print(f"[{task.key}] direct-cdp did not find a generated Tmall order report covering today before the deadline.", flush=True)
    return clicked_report


async def direct_cdp_click_existing_export_result(
    page: DirectCdpPage,
    task: RobotTask,
    *,
    deadline: float,
    watch_dirs: list[Path],
    started_at: float,
) -> bool:
    if task.key != "tmall_orders":
        return False
    if "/trade-platform/tp/export-list" not in str(await page.evaluate("location.href", timeout_seconds=3) or ""):
        await page.navigate(TMALL_ORDER_EXPORT_LIST_URL)
    clicked = await direct_cdp_click_tmall_report_covering_today(
        page,
        deadline=min(deadline, time.monotonic() + 30),
        watch_dirs=watch_dirs,
        started_at=started_at,
    )
    if not clicked:
        print(f"[{task.key}] direct-cdp found no existing generated report covering today; creating a new export task.", flush=True)
    return clicked


async def direct_cdp_click_tmall_report_covering_today(
    page: DirectCdpPage,
    *,
    deadline: float,
    watch_dirs: list[Path],
    started_at: float,
) -> bool:
    target_date = date.today().isoformat()
    list_deadline = deadline
    transient_errors = 0
    while time.monotonic() < list_deadline:
        try:
            clicked = await page.evaluate(
            r"""
            ((targetDate) => {
              const visible = (element) => {
                const rect = element.getBoundingClientRect();
                const style = window.getComputedStyle(element);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
              };
              const textOf = (element) => (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim();
              const downloadTextPattern = /\u4e0b\u8f7d\u8ba2\u5355\u62a5\u8868|\u4e0b\u8f7d\u62a5\u8868|\u4e0b\u8f7d/;
              const reportTimePattern = /\u62a5\u8868\u7533\u8bf7\u65f6\u95f4[:\uff1a]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/;
              const cardSelectors = [
                '.order-export_order-block__pyg21',
                '[class*="order-export_order-block"]',
                '[class*="order-block"]',
                '[class*="export"]',
                '[class*="list"] > *',
                'tr',
                'li',
              ];
              const cards = Array.from(new Set(cardSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)))))
                .filter((element) => visible(element) && textOf(element).includes(targetDate));
              const buttonCards = Array.from(document.querySelectorAll('button,a,[role=button],div,span'))
                .filter((element) => visible(element) && downloadTextPattern.test(textOf(element)))
                .map((button) => {
                  let cursor = button;
                  let best = null;
                  for (let depth = 0; cursor && depth < 8; depth += 1, cursor = cursor.parentElement) {
                    const text = textOf(cursor);
                    if (text.includes(targetDate)) best = { element: button, text };
                  }
                  return best;
                })
                .filter(Boolean);
              const candidates = cards
                .map((card) => {
                  const text = (card.innerText || card.textContent || '').replace(/\\s+/g, ' ').trim();
                  const buttons = Array.from(card.querySelectorAll('button,a,[role=button]'))
                    .filter((element) => visible(element));
                  const button = buttons.find((element) => /下载订单报表|下载报表/.test(element.innerText || element.textContent || ''))
                    || buttons[0];
                  return { element: button, text };
                })
                .filter((item) => item.element)
                .filter((item) => item.text.includes(targetDate));
              candidates.sort((left, right) => {
                const leftMatch = left.text.match(/\\u62a5\\u8868\\u7533\\u8bf7\\u65f6\\u95f4[:\\uff1a]\\s*(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})/);
                const rightMatch = right.text.match(/\\u62a5\\u8868\\u7533\\u8bf7\\u65f6\\u95f4[:\\uff1a]\\s*(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})/);
                const leftTime = leftMatch ? leftMatch[1] : '';
                const rightTime = rightMatch ? rightMatch[1] : '';
                return rightTime.localeCompare(leftTime);
              });
              const candidate = candidates[0];
              if (!candidate) {
                return { clicked: false, candidateCount: 0, cardCount: cards.length, bodyText: document.body.innerText.slice(0, 500) };
              }
              candidate.element.scrollIntoView({ block: 'center', inline: 'center' });
              candidate.element.click();
              return { clicked: true, candidateCount: candidates.length, cardCount: cards.length, rowText: candidate.text.slice(0, 600) };
            })(""" + json.dumps(target_date) + ")",
                timeout_seconds=10,
            )
            transient_errors = 0
        except (TimeoutError, asyncio.TimeoutError, RuntimeError) as exc:
            transient_errors += 1
            print(
                f"[tmall_orders] direct-cdp report-list query failed ({type(exc).__name__}); refreshing and continuing.",
                flush=True,
            )
            if transient_errors <= 3:
                try:
                    await page.reload()
                except Exception:
                    pass
            await asyncio.sleep(min(10, 2 * transient_errors))
            continue
        print(f"[tmall_orders] direct-cdp searched report covering today: {clicked}", flush=True)
        if isinstance(clicked, dict) and clicked.get("clicked"):
            if await wait_direct_cdp_download_started(watch_dirs, started_at, timeout_seconds=10):
                return True
            clicked_at = None
            try:
                clicked_at = await page.click_label("下载订单报表", exact=True)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                print(
                    f"[tmall_orders] direct-cdp fallback report-label click timed out; continuing download wait: {type(exc).__name__}",
                    flush=True,
                )
            if clicked_at:
                print(f"[tmall_orders] direct-cdp fallback clicked report label via {clicked_at}", flush=True)
                if await wait_direct_cdp_download_started(watch_dirs, started_at, timeout_seconds=10):
                    return True
        if direct_cdp_download_started(watch_dirs, started_at):
            return True
        await asyncio.sleep(10)
    return False


async def direct_cdp_click_tmall_report_covering_today(
    page: DirectCdpPage,
    *,
    deadline: float,
    watch_dirs: list[Path],
    started_at: float,
) -> bool:
    target_date = date.today().isoformat()
    list_deadline = deadline
    transient_errors = 0
    click_expression = r"""
    ((targetDate) => {
      const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const textOf = (element) => (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim();
      const downloadTextPattern = /\u4e0b\u8f7d\u8ba2\u5355\u62a5\u8868|\u4e0b\u8f7d\u62a5\u8868|\u4e0b\u8f7d/;
      const reportTimePattern = /\u62a5\u8868\u7533\u8bf7\u65f6\u95f4[:\uff1a]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/;
      const clickableSelector = 'button,a,[role=button],div,span';
      const buttonCandidates = Array.from(document.querySelectorAll(clickableSelector))
        .filter((element) => visible(element) && downloadTextPattern.test(textOf(element)))
        .map((button) => {
          let cursor = button;
          let rowText = textOf(button);
          for (let depth = 0; cursor && depth < 10; depth += 1, cursor = cursor.parentElement) {
            const text = textOf(cursor);
            if (text.includes(targetDate)) {
              rowText = text;
              break;
            }
          }
          return { element: button, text: rowText };
        })
        .filter((item) => item.text.includes(targetDate));
      const blockSelectors = [
        '.order-export_order-block__pyg21',
        '[class*="order-export_order-block"]',
        '[class*="order-block"]',
        '[class*="export"]',
        '[class*="list"] > *',
        'tr',
        'li',
      ];
      const blockCandidates = Array.from(new Set(blockSelectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)))))
        .filter((element) => visible(element) && textOf(element).includes(targetDate))
        .map((block) => {
          const text = textOf(block);
          const button = Array.from(block.querySelectorAll(clickableSelector))
            .filter((element) => visible(element))
            .find((element) => downloadTextPattern.test(textOf(element)));
          return { element: button, text };
        })
        .filter((item) => item.element);
      const candidates = buttonCandidates.concat(blockCandidates);
      candidates.sort((left, right) => {
        const leftMatch = left.text.match(reportTimePattern);
        const rightMatch = right.text.match(reportTimePattern);
        const leftTime = leftMatch ? leftMatch[1] : '';
        const rightTime = rightMatch ? rightMatch[1] : '';
        return rightTime.localeCompare(leftTime);
      });
      const candidate = candidates[0];
      if (!candidate) {
        return {
          clicked: false,
          candidateCount: 0,
          buttonCandidateCount: buttonCandidates.length,
          blockCandidateCount: blockCandidates.length,
          bodyText: (document.body.innerText || '').slice(0, 500)
        };
      }
      candidate.element.scrollIntoView({ block: 'center', inline: 'center' });
      candidate.element.click();
      return {
        clicked: true,
        candidateCount: candidates.length,
        buttonCandidateCount: buttonCandidates.length,
        blockCandidateCount: blockCandidates.length,
        rowText: candidate.text.slice(0, 600)
      };
    })(
    """
    while time.monotonic() < list_deadline:
        try:
            clicked = await page.evaluate(click_expression + json.dumps(target_date) + ")", timeout_seconds=10)
            transient_errors = 0
        except (TimeoutError, asyncio.TimeoutError, RuntimeError) as exc:
            transient_errors += 1
            print(
                f"[tmall_orders] direct-cdp report-list query failed ({type(exc).__name__}); refreshing and continuing.",
                flush=True,
            )
            if transient_errors <= 3:
                try:
                    await page.reload()
                except Exception:
                    pass
            await asyncio.sleep(min(10, 2 * transient_errors))
            continue
        print(f"[tmall_orders] direct-cdp searched report covering today: {clicked}", flush=True)
        if isinstance(clicked, dict) and clicked.get("clicked"):
            if await wait_direct_cdp_download_started(watch_dirs, started_at, timeout_seconds=10):
                return True
            clicked_at = None
            try:
                clicked_at = await page.click_label("\u4e0b\u8f7d\u8ba2\u5355\u62a5\u8868", exact=True)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                print(
                    f"[tmall_orders] direct-cdp fallback report-label click timed out; continuing download wait: {type(exc).__name__}",
                    flush=True,
                )
            if clicked_at:
                print(f"[tmall_orders] direct-cdp fallback clicked report label via {clicked_at}", flush=True)
                if await wait_direct_cdp_download_started(watch_dirs, started_at, timeout_seconds=10):
                    return True
        if direct_cdp_download_started(watch_dirs, started_at):
            return True
        await asyncio.sleep(10)
    return False


async def direct_cdp_special_primary_export(page: DirectCdpPage, task: RobotTask) -> str | None:
    if task.key != "douyin_ads":
        return None
    clicked = await page.evaluate(
        """
        (() => {
          const element = document.querySelector('.qc-report-download-btn.download-btn');
          if (!element) return false;
          element.scrollIntoView({ block: 'center', inline: 'center' });
          element.click();
          return true;
        })()
        """,
        timeout_seconds=5,
    )
    return "qianchuan report download button" if clicked else None


async def direct_cdp_special_followup_label(page: DirectCdpPage, task: RobotTask, label: str) -> str | None:
    if task.key == "tmall_ads" and label == "涓嬭浇浠诲姟绠＄悊":
        await page.evaluate("location.hash = '!/report/download-list'", timeout_seconds=5)
        await asyncio.sleep(2.5)
        return "download-list route"
    return None


def direct_cdp_download_started(watch_dirs: list[Path], started_at: float) -> bool:
    return any(files_created_since(folder, started_at, limit=1) or active_partial_downloads(folder, started_at) for folder in watch_dirs)


async def wait_direct_cdp_download_started(watch_dirs: list[Path], started_at: float, *, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(0.5, timeout_seconds)
    while time.monotonic() < deadline:
        if direct_cdp_download_started(watch_dirs, started_at):
            return True
        await asyncio.sleep(0.5)
    return False


async def wait_direct_cdp_text(page: DirectCdpPage, terms: list[str], *, timeout_seconds: int) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            text = str(await page.evaluate("document.body ? document.body.innerText : ''", timeout_seconds=5) or "")
            if all(term in text for term in terms):
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


def filter_tmall_order_exports_for_today(paths: list[Path]) -> tuple[list[Path], list[dict[str, Any]]]:
    target = date.today()
    accepted: list[Path] = []
    diagnostics: list[dict[str, Any]] = []
    for path in paths:
        check = tmall_order_export_date_check(path, target)
        diagnostics.append(check)
        if check.get("accepted"):
            accepted.append(path)
        else:
            print(f"[tmall_orders] rejected export with wrong date range: {check}", flush=True)
    return accepted, diagnostics


def tmall_order_export_date_check(path: Path, target: date) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file": str(path),
        "accepted": False,
        "target_date": target.isoformat(),
        "min_date": "",
        "max_date": "",
        "row_count": 0,
        "reason": "",
    }
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        result["reason"] = "not_excel"
        return result
    try:
        import openpyxl
    except Exception as exc:
        result["reason"] = f"openpyxl_unavailable:{exc}"
        return result
    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value or "").strip() for value in next(rows, ())]
        date_indexes = [
            index
            for index, header in enumerate(headers)
            if header in {"订单创建时间", "创建时间", "订单付款时间", "付款时间"}
        ]
        if not date_indexes:
            result["reason"] = "missing_date_columns"
            workbook.close()
            return result
        seen: list[date] = []
        for row in rows:
            row_date = first_date_in_row(row, date_indexes)
            if row_date is None:
                continue
            seen.append(row_date)
        workbook.close()
        if not seen:
            result["reason"] = "no_dated_rows"
            return result
        result["row_count"] = len(seen)
        result["min_date"] = min(seen).isoformat()
        result["max_date"] = max(seen).isoformat()
        result["accepted"] = min(seen) <= target <= max(seen)
        if not result["accepted"]:
            result["reason"] = "date_range_does_not_include_today"
        return result
    except Exception as exc:
        result["reason"] = f"inspect_failed:{type(exc).__name__}:{exc}"
        return result


def first_date_in_row(row: tuple[Any, ...], indexes: list[int]) -> date | None:
    for index in indexes:
        if index >= len(row):
            continue
        parsed = parse_excel_date(row[index])
        if parsed is not None:
            return parsed
    return None


def parse_excel_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def wait_for_direct_cdp_downloads(
    watch_dirs: list[Path],
    since_timestamp: float,
    *,
    limit: int,
    timeout_seconds: int,
    idle_seconds: int,
) -> list[Path]:
    deadline = time.monotonic() + timeout_seconds
    last_seen: list[Path] = []
    while time.monotonic() < deadline:
        current = collect_unique_watched_files(watch_dirs, since_timestamp, limit=limit)
        partials = [partial for folder in watch_dirs for partial in active_partial_downloads(folder, since_timestamp)]
        if current and not partials:
            last_seen = current
            idle_deadline = time.monotonic() + max(1, idle_seconds)
            while time.monotonic() < idle_deadline:
                expanded = collect_unique_watched_files(watch_dirs, since_timestamp, limit=limit)
                if len(expanded) > len(last_seen):
                    last_seen = expanded
                    idle_deadline = time.monotonic() + max(1, idle_seconds)
                if not any(active_partial_downloads(folder, since_timestamp) for folder in watch_dirs):
                    time.sleep(0.5)
                else:
                    idle_deadline = time.monotonic() + max(1, idle_seconds)
                    time.sleep(0.5)
                if len(last_seen) >= limit:
                    return last_seen[:limit]
            return last_seen[:limit]
        time.sleep(0.5)
    return last_seen[:limit]


def collect_unique_watched_files(watch_dirs: list[Path], since_timestamp: float, *, limit: int) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for folder in watch_dirs:
        for path in files_created_since(folder, since_timestamp, limit=limit):
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    files.sort(key=lambda path: path.stat().st_mtime)
    return files[:limit]


async def connect_over_cdp_with_retry(playwright: Any, cdp_url: str, *, attempts: int = 3, timeout_ms: int = 120_000) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_ms)
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            await asyncio.sleep(2 * attempt)
    assert last_error is not None
    raise last_error


async def select_page_for_task(context: Any, task: RobotTask) -> Any:
    pages = [page for page in context.pages if not page.is_closed()]
    if not pages:
        return await context.new_page()
    for page in reversed(pages):
        if should_preserve_current_page(task, page.url):
            return page
    scored = sorted(((page_match_score(page.url, task.url), page) for page in pages), key=lambda item: item[0], reverse=True)
    if scored[0][0] > 0:
        return scored[0][1]
    return pages[0]


def should_preserve_current_page(task: RobotTask, current_url: str) -> bool:
    page = urlparse(current_url)
    if task.key == "pinduoduo_orders":
        return page.hostname == "mms.pinduoduo.com" and page.path == "/orders/exportExcel"
    if task.key == "tmall_orders":
        return page.hostname == "myseller.taobao.com" and page.path == "/home.htm/trade-platform/tp/export-list"
    return False


def page_match_score(page_url: str, task_url: str) -> int:
    if not page_url or page_url == "about:blank":
        return 0
    page = urlparse(page_url)
    task = urlparse(task_url)
    if page.hostname != task.hostname:
        return 0
    score = 10
    if direct_cdp_page_family(page_url) and direct_cdp_page_family(page_url) == direct_cdp_page_family(task_url):
        score += 8
    if page.path == task.path:
        score += 5
    elif page.path and task.path and (page.path.startswith(task.path) or task.path.startswith(page.path)):
        score += 2
    return score


def direct_cdp_page_family(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    path = parsed.path or ""
    if hostname == "myseller.taobao.com" and "/trade-platform/tp/" in path:
        return "tmall_orders"
    if (hostname == "myseller.taobao.com" and "tuiguangcenter_new" in path) or hostname == "one.alimama.com":
        return "tmall_ads"
    if hostname in {"qianchuan.jinritemai.com", "business.oceanengine.com"}:
        return "douyin_ads"
    return ""


def direct_cdp_reusable_target_id(targets: list[dict[str, Any]], task_url: str) -> str:
    fallback_id = ""
    scored: list[tuple[int, str]] = []
    task_family = direct_cdp_page_family(task_url)
    for target in targets:
        if target.get("type") != "page":
            continue
        target_id = str(target.get("targetId") or target.get("id") or "")
        page_url = str(target.get("url") or "")
        if not target_id:
            continue
        parsed = urlparse(page_url)
        if parsed.scheme in {"chrome", "devtools"} or page_url == "about:blank":
            continue
        page_family = direct_cdp_page_family(page_url)
        if task_family and page_family and task_family != page_family:
            continue
        score = page_match_score(page_url, task_url)
        if score > 0:
            scored.append((score, target_id))
        elif not task_family and not fallback_id:
            fallback_id = target_id
    if scored:
        return sorted(scored, key=lambda item: item[0], reverse=True)[0][1]
    return fallback_id


def direct_cdp_duplicate_target_ids(
    targets: list[dict[str, Any]],
    task_url: str,
    *,
    keep_target_id: str = "",
) -> list[str]:
    task_family = direct_cdp_page_family(task_url)
    if not task_family:
        return []
    duplicate_ids: list[str] = []
    for target in targets:
        if target.get("type") != "page":
            continue
        target_id = str(target.get("targetId") or target.get("id") or "")
        if not target_id or target_id == keep_target_id:
            continue
        if direct_cdp_page_family(str(target.get("url") or "")) == task_family:
            duplicate_ids.append(target_id)
    return duplicate_ids


async def save_download(download: Any, download_dir: Path) -> Path:
    suggested = safe_filename(download.suggested_filename or f"download-{datetime.now().strftime('%H%M%S')}")
    target = unique_path(download_dir / suggested)
    await download.save_as(str(target))
    return target


async def run_actions(page: Any, task: RobotTask) -> None:
    action_path = ACTION_ROOT / f"{task.key}.json"
    if not action_path.exists():
        print(f"[{task.key}] No action file at {action_path}; waiting for manual download.", flush=True)
        return
    actions = json.loads(action_path.read_text(encoding="utf-8"))
    for action in actions:
        kind = action.get("type")
        selector = action.get("selector")
        timeout = int(action.get("timeout_ms", 30_000))
        if kind == "click":
            await page.locator(selector).click(timeout=timeout)
        elif kind == "fill":
            await page.locator(selector).fill(str(action.get("value", "")), timeout=timeout)
        elif kind == "press":
            await page.locator(selector or "body").press(str(action["key"]), timeout=timeout)
        elif kind == "wait":
            await page.wait_for_timeout(int(float(action.get("seconds", 1)) * 1000))
        else:
            raise ValueError(f"Unsupported action type in {action_path}: {kind}")


async def run_smart_export(
    page: Any,
    task: RobotTask,
    *,
    timeout_ms: int,
    download_task: asyncio.Task[Any] | None = None,
    watch_dir: Path | None = None,
    started_at: float | None = None,
) -> None:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    labels = smart_export_labels(task)
    deadline = time.monotonic() + (timeout_ms / 1000)
    page = await refresh_task_page(page, task)
    if await click_existing_export_result(page, task, deadline=deadline):
        return

    clicked = False
    while time.monotonic() < deadline:
        clicked_at = await click_special_primary_export(page, task)
        if clicked_at:
            print(f"[{task.key}] clicked primary via {clicked_at}", flush=True)
            clicked = True
            await page.wait_for_timeout(1500)
            page = await refresh_task_page(page, task)
            break
        for label in labels:
            clicked_at = await click_first_visible_label(page, label)
            if clicked_at:
                print(f"[{task.key}] clicked primary '{label}' via {clicked_at}", flush=True)
                clicked = True
                await page.wait_for_timeout(1500)
                page = await refresh_task_page(page, task)
                break
        if clicked:
            break
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        await page.wait_for_timeout(1000)

    if not clicked:
        print(f"[{task.key}] No export/download button was found. If the page is blocked or needs login, rerun with --manual after logging in.", flush=True)
        return

    # Many Chinese commerce portals use a two-step export flow:
    # click export -> confirm/create task -> download generated file.
    clicked_followup_labels: set[str] = set()
    followup_deadline = min(deadline, time.monotonic() + followup_poll_seconds(task))
    while time.monotonic() < followup_deadline:
        if export_started(download_task=download_task, watch_dir=watch_dir, started_at=started_at):
            return
        advanced = False
        for label in followup_export_labels(task):
            if label in clicked_followup_labels:
                continue
            clicked_at = await click_special_followup_label(page, task, label)
            if not clicked_at:
                clicked_at = await click_first_visible_label(page, label, exact=followup_label_exact(task, label))
            if clicked_at:
                print(f"[{task.key}] clicked follow-up '{label}' via {clicked_at}", flush=True)
                clicked_followup_labels.add(label)
                advanced = True
                await page.wait_for_timeout(2000)
                page = await refresh_task_page(page, task)
                if export_started(download_task=download_task, watch_dir=watch_dir, started_at=started_at):
                    return
                break
        if not advanced:
            page = await refresh_task_page(page, task)
            await page.wait_for_timeout(1500)


async def refresh_task_page(page: Any, task: RobotTask) -> Any:
    fresh_page = await select_page_for_task(page.context, task)
    if fresh_page != page:
        await fresh_page.bring_to_front()
    return fresh_page


async def click_existing_export_result(page: Any, task: RobotTask, *, deadline: float) -> bool:
    if task.key == "tmall_orders" and "/trade-platform/tp/export-list" in page.url:
        while time.monotonic() < deadline:
            clicked_at = await click_first_visible_label(page, "下载订单报表", exact=True)
            if clicked_at:
                print(f"[{task.key}] clicked existing generated report '下载订单报表' via {clicked_at}", flush=True)
                await page.wait_for_timeout(2000)
                return True
            await page.wait_for_timeout(1500)
        return False
    if task.key != "pinduoduo_orders" or "/orders/exportExcel" not in page.url:
        return False
    while time.monotonic() < deadline:
        clicked_at = await click_pinduoduo_generated_report_button(page)
        if not clicked_at:
            clicked_at = await click_first_visible_label(page, "下载报表", exact=True)
        if clicked_at:
            print(f"[{task.key}] clicked existing generated report '下载报表' via {clicked_at}", flush=True)
            await page.wait_for_timeout(2000)
            return True
        await page.wait_for_timeout(1500)
    return False


async def click_pinduoduo_generated_report_button(page: Any) -> str | None:
    clicked = await page.evaluate(
        r"""
        () => {
          const label = '\u4e0b\u8f7d\u62a5\u8868';
          const buttons = Array.from(document.querySelectorAll('button'));
          const visibleButtons = buttons.filter((button) => {
            const text = (button.innerText || button.textContent || '').trim();
            if (text !== label) return false;
            const rect = button.getBoundingClientRect();
            const style = window.getComputedStyle(button);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          });
          if (!visibleButtons.length) return false;
          visibleButtons[0].click();
          return true;
        }
        """
    )
    return "pinduoduo generated report button" if clicked else None


def followup_poll_seconds(task: RobotTask) -> int:
    if task.key == "pinduoduo_orders":
        return 180
    if task.key == "tmall_ads":
        return 120
    return 30


def followup_label_exact(task: RobotTask, label: str) -> bool:
    if task.key == "tmall_ads" and label == "下载任务管理":
        return False
    return True


async def click_special_followup_label(page: Any, task: RobotTask, label: str) -> str | None:
    if task.key == "tmall_ads" and label == "下载任务管理":
        await page.evaluate("location.hash = '!/report/download-list'")
        await page.wait_for_timeout(2500)
        return "download-list route"
    return None


async def click_special_primary_export(page: Any, task: RobotTask) -> str | None:
    if task.key != "douyin_ads":
        return None
    locator = page.locator(".qc-report-download-btn.download-btn").first
    try:
        if await locator.count() == 0:
            return None
        await locator.scroll_into_view_if_needed(timeout=1500)
        await locator.click(timeout=2000)
        return "qianchuan report download button"
    except Exception:
        return None


def export_started(
    *,
    download_task: asyncio.Task[Any] | None,
    watch_dir: Path | None,
    started_at: float | None,
) -> bool:
    if download_task is not None and download_task.done():
        return True
    if watch_dir is None or started_at is None:
        return False
    return bool(files_created_since(watch_dir, started_at, limit=1) or active_partial_downloads(watch_dir, started_at))


async def click_first_visible_label(page: Any, label: str, *, exact: bool = False) -> str | None:
    text_match: str | re.Pattern[str] = exact_text_pattern(label) if exact else label
    candidates = [
        ("dialog button", page.locator('[role="dialog"] button').filter(has_text=text_match).first),
        ("modal button", page.locator('.weui-dialog button, .ant-modal button, .semi-modal button, .el-dialog button').filter(has_text=text_match).first),
        ("button text", page.locator("button").filter(has_text=text_match).first),
        ("role button", page.get_by_role("button", name=label, exact=exact).first),
        ("role link", page.get_by_role("link", name=label, exact=exact).first),
        ("text", page.get_by_text(label, exact=exact).first),
    ]
    for name, locator in candidates:
        try:
            if await locator.count() == 0:
                continue
            await locator.click(timeout=1500)
            return name
        except Exception:
            continue
    if await click_visible_text_by_dom(page, label, exact=exact):
        return "dom text"
    return None


def exact_text_pattern(label: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{re.escape(label)}\s*$")


async def click_visible_text_by_dom(page: Any, label: str, *, exact: bool = False) -> bool:
    handle = await page.evaluate_handle(
        """
        ({label, exact}) => {
          const collect = (root) => {
            const found = Array.from(root.querySelectorAll('button,a,[role=button],div,span'));
            const nested = Array.from(root.querySelectorAll('*'))
              .filter((element) => element.shadowRoot)
              .flatMap((element) => collect(element.shadowRoot));
            return found.concat(nested);
          };
          const elements = collect(document);
          const candidates = elements.filter((element) => {
            const text = (element.innerText || element.textContent || '').trim();
            if (exact ? text !== label : !text.includes(label)) return false;
            const rect = element.getBoundingClientRect();
            const style = window.getComputedStyle(element);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
          });
          candidates.sort((left, right) => {
            const leftRole = /^(BUTTON|A)$/.test(left.tagName) || left.getAttribute('role') === 'button' ? 0 : 1;
            const rightRole = /^(BUTTON|A)$/.test(right.tagName) || right.getAttribute('role') === 'button' ? 0 : 1;
            if (leftRole !== rightRole) return leftRole - rightRole;
            const leftText = (left.innerText || left.textContent || '').trim();
            const rightText = (right.innerText || right.textContent || '').trim();
            return leftText.length - rightText.length;
          });
          const candidate = candidates[0];
          return candidate || null;
        }
        """,
        {"label": label, "exact": exact},
    )
    element = handle.as_element()
    if element is None:
        return False
    try:
        await element.scroll_into_view_if_needed(timeout=1500)
        box = await element.bounding_box()
        if box is None:
            return False
        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        return True
    except Exception:
        return False


async def wait_for_first_download_or_watched_file(
    download_task: asyncio.Task[Any],
    watch_dir: Path,
    since_timestamp: float,
    *,
    timeout_seconds: float,
    limit: int,
) -> tuple[Any | None, list[Path]]:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    deadline = time.monotonic() + max(0, timeout_seconds)
    while time.monotonic() < deadline:
        if download_task.done():
            try:
                return await download_task, []
            except PlaywrightTimeoutError:
                return None, []
        watched = files_created_since(watch_dir, since_timestamp, limit=limit)
        if watched and not active_partial_downloads(watch_dir, since_timestamp):
            return None, watched
        await asyncio.sleep(0.5)
    try:
        return await download_task, []
    except PlaywrightTimeoutError:
        return None, []


def smart_export_labels(task: RobotTask) -> list[str]:
    common = ["导出", "下载", "导出数据", "下载数据", "导出报表", "下载报表", "导出明细"]
    by_task = {
        "pinduoduo_orders": ["批量导出"],
        "pinduoduo_ads": ["下载报表", "导出报表", "导出数据", "下载数据", "导出"],
        "wechat_channels_orders": ["全部导出", "导出订单", "批量导出"],
        "douyin_ads": ["下载数据", "导出数据", "下载报表", "导出报表"],
        "douyin_influencer": ["导出数据", "导出明细"],
        "tmall_orders": ["批量导出", "导出订单", "订单导出", "导出"],
        "tmall_ads": ["下载报表"],
    }
    if task.key in {"pinduoduo_orders", "wechat_channels_orders", "douyin_influencer", "tmall_orders", "tmall_ads"}:
        return by_task[task.key]
    return dedupe([*by_task.get(task.key, []), *common])


def followup_export_labels(task: RobotTask) -> list[str]:
    common = ["导出", "确定", "确认", "确认导出", "开始导出", "生成报表", "创建报表", "立即下载", "下载文件", "下载"]
    by_task = {
        "pinduoduo_orders": ["导出", "确认导出", "生成报表", "下载报表", "下载数据", "下载文件", "立即下载"],
        "pinduoduo_ads": ["下载", "下载文件", "确认"],
        "wechat_channels_orders": ["导出", "确认导出", "下载文件", "立即下载"],
        "douyin_ads": ["确认", "下载文件", "立即下载"],
        "douyin_influencer": ["确认", "下载列表", "下载文件", "立即下载"],
        "tmall_orders": ["确认", "确定", "生成报表", "下载订单报表", "下载文件", "立即下载"],
        "tmall_ads": ["确定", "确认", "下载任务管理", "下载"],
    }
    if task.key == "tmall_ads":
        return by_task[task.key]
    if task.key == "tmall_orders":
        return by_task[task.key]
    return dedupe([*by_task.get(task.key, []), *common])


def dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def url_looks_like_login(url: str) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.netloc}{parsed.path}".lower()
    return any(token in haystack for token in ("login", "passport", "auth", "captcha", "verify"))


def text_looks_like_login(text: str) -> bool:
    haystack = text.lower()
    return any(
        token.lower() in haystack
        for token in (
            "登录",
            "扫码",
            "二维码",
            "验证码",
            "安全验证",
            "滑块",
            "短信验证",
            "login",
            "captcha",
            "verify",
        )
    )


async def direct_cdp_login_if_needed(page: DirectCdpPage, task: RobotTask, *, timeout_seconds: int) -> dict[str, Any]:
    started_at = datetime.now()
    url = str(await page.evaluate("location.href", timeout_seconds=3) or "")
    text = str(
        await page.evaluate(
            "document.body && (document.body.innerText || document.body.textContent || '') || ''",
            timeout_seconds=5,
        )
        or ""
    )
    if not url_looks_like_login(url) and not text_looks_like_login(text):
        return {"status": "not_needed", "url": url}
    username, password = get_login_credentials(task.platform_code)
    if not username or not password:
        print(f"[{task.key}] Login page detected but no local credentials were found; please finish login in the visible browser.", flush=True)
        return await wait_direct_cdp_login_ready(page, task, started_at=started_at, timeout_seconds=timeout_seconds)
    fill_result = await direct_cdp_fill_login(page, username=username, password=password)
    print(
        f"[{task.key}] Login page detected; auto-filled username/password status={fill_result.get('status')}.",
        flush=True,
    )
    wait_result = await wait_direct_cdp_login_ready(page, task, started_at=started_at, timeout_seconds=timeout_seconds)
    return {"status": wait_result.get("status"), "fill": fill_result, "wait": wait_result}


async def wait_direct_cdp_login_ready(
    page: DirectCdpPage,
    task: RobotTask,
    *,
    started_at: datetime,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    checks = 0
    last_url = ""
    while time.monotonic() < deadline:
        checks += 1
        last_url = str(await page.evaluate("location.href", timeout_seconds=3) or "")
        body_text = str(
            await page.evaluate(
                "document.body && (document.body.innerText || document.body.textContent || '') || ''",
                timeout_seconds=5,
            )
            or ""
        )
        if not url_looks_like_login(last_url):
            return {
                "status": "ready",
                "checks": checks,
                "url": last_url,
                "waited_seconds": int((datetime.now() - started_at).total_seconds()),
            }
        if text_looks_like_login(body_text):
            print(f"[{task.key}] Waiting for login/security verification in visible Chrome; current URL: {last_url}", flush=True)
        await asyncio.sleep(5)
    return {
        "status": "login_timeout",
        "checks": checks,
        "url": last_url,
        "waited_seconds": int((datetime.now() - started_at).total_seconds()),
    }


async def direct_cdp_fill_login(page: DirectCdpPage, *, username: str, password: str) -> dict[str, Any]:
    payload = {
        "username": username,
        "password": password,
        "usernameSelectors": USERNAME_SELECTORS,
        "passwordSelectors": PASSWORD_SELECTORS,
        "buttonSelectors": LOGIN_BUTTON_SELECTORS,
    }
    expression = r"""
    ((payloadText) => {
      const payload = JSON.parse(payloadText);
      const roots = [document];
      for (const element of Array.from(document.querySelectorAll('*'))) {
        if (element.shadowRoot) roots.push(element.shadowRoot);
      }
      const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const first = (selectors) => {
        for (const root of roots) {
          for (const selector of selectors) {
            for (const element of Array.from(root.querySelectorAll(selector))) {
              if (visible(element)) return element;
            }
          }
        }
        return null;
      };
      const setValue = (element, value) => {
        element.focus();
        const proto = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const descriptor = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (descriptor && descriptor.set) {
          descriptor.set.call(element, value);
        } else {
          element.value = value;
        }
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
      };
      const usernameInput = first(payload.usernameSelectors);
      const passwordInput = first(payload.passwordSelectors);
      if (usernameInput) setValue(usernameInput, payload.username);
      if (passwordInput) setValue(passwordInput, payload.password);
      let button = first(payload.buttonSelectors);
      if (!button) {
        const candidates = roots.flatMap((root) => Array.from(root.querySelectorAll('button,a,input[type=submit],[role=button],div,span')));
        button = candidates.find((element) => visible(element) && /登录|登 录|登陆|submit/i.test((element.innerText || element.value || element.textContent || '').trim())) || null;
      }
      let submitted = false;
      if (usernameInput && passwordInput && button) {
        button.scrollIntoView({ block: 'center', inline: 'center' });
        button.click();
        submitted = true;
      } else if (usernameInput && passwordInput) {
        const form = passwordInput.form || passwordInput.closest('form') || usernameInput.closest('form');
        if (form && typeof form.requestSubmit === 'function') {
          form.requestSubmit();
          submitted = true;
        } else if (form && typeof form.submit === 'function') {
          form.submit();
          submitted = true;
        } else {
          passwordInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
          passwordInput.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
          submitted = true;
        }
      }
      return {
        status: usernameInput && passwordInput && submitted ? 'submitted' : usernameInput && passwordInput ? 'filled' : 'fields_not_found',
        username_filled: !!usernameInput,
        password_filled: !!passwordInput,
        clicked_login: !!(usernameInput && passwordInput && button),
        submitted: !!submitted,
        input_count: roots.reduce((count, root) => count + root.querySelectorAll('input').length, 0),
        iframe_count: document.querySelectorAll('iframe').length,
        url: location.href,
        title: document.title
      };
    })(""" + json.dumps(json.dumps(payload, ensure_ascii=False)) + ")"
    attempts: list[dict[str, Any]] = []
    result = await page.evaluate(expression, timeout_seconds=10)
    if isinstance(result, dict):
        top_attempt = {"frame": "top", **result}
        attempts.append(top_attempt)
        if result.get("status") in {"submitted", "filled"}:
            return {"status": result.get("status"), "attempts": attempts}
    else:
        attempts.append({"frame": "top", "status": "unknown", "raw": result})

    try:
        contexts = await page.frame_contexts(timeout_seconds=8)
    except Exception as exc:
        return {"status": "fields_not_found", "attempts": attempts, "frame_error": str(exc)}

    for context in contexts:
        context_id = context.get("context_id")
        if not isinstance(context_id, int):
            attempts.append(
                {
                    "frame": context.get("frame_id") or "",
                    "frame_url": context.get("url") or "",
                    "status": "context_unavailable",
                    "error": context.get("error") or "",
                }
            )
            continue
        try:
            frame_result = await page.evaluate(expression, timeout_seconds=10, context_id=context_id)
        except Exception as exc:
            attempts.append(
                {
                    "frame": context.get("frame_id") or "",
                    "frame_url": context.get("url") or "",
                    "status": "evaluate_failed",
                    "error": str(exc),
                }
            )
            continue
        if not isinstance(frame_result, dict):
            attempts.append(
                {
                    "frame": context.get("frame_id") or "",
                    "frame_url": context.get("url") or "",
                    "status": "unknown",
                    "raw": frame_result,
                }
            )
            continue
        attempt = {
            "frame": context.get("frame_id") or "",
            "frame_url": context.get("url") or "",
            "frame_name": context.get("name") or "",
            **frame_result,
        }
        attempts.append(attempt)
        if frame_result.get("status") in {"submitted", "filled"}:
            return {"status": frame_result.get("status"), "attempts": attempts}
    return {"status": "fields_not_found", "attempts": attempts}


def archive_downloads(task: RobotTask, files: list[Path], archive_root: Path, *, date_token: str, run_token: str) -> list[ArchivedFile]:
    target_dir = archive_root / date_token / task.platform
    target_dir.mkdir(parents=True, exist_ok=True)
    archived: list[ArchivedFile] = []
    for source in files:
        if not matches_task_filename(task, source.name):
            continue
        suffix = source.suffix.lower()
        if suffix == ".zip":
            archived.extend(extract_zip(task, source, target_dir, run_token=run_token))
            continue
        if suffix not in {".csv", ".xls", ".xlsx"}:
            continue
        target = target_dir / normalized_name(task, source.name, run_token=run_token)
        target = unique_path(target)
        copy_when_stable(source, target)
        archived.append(ArchivedFile(source=source, archived=target))
    return archived


def matches_task_filename(task: RobotTask, filename: str) -> bool:
    if task.key == "douyin_influencer":
        return bool(
            re.match(r"^[0-9a-f-]{20,}_[0-9]+(?: \(\d+\))?\.xlsx$", filename, flags=re.IGNORECASE)
            or "佣金" in filename
            or "达人" in filename
        )
    if task.key == "pinduoduo_ads" and "分天数据" not in filename:
        return False
    hints = TASK_FILENAME_HINTS.get(task.key)
    if not hints:
        return True
    lowered = filename.lower()
    return any(hint.lower() in lowered for hint in hints)


def write_archive_manifest(
    task: RobotTask,
    archived: list[ArchivedFile],
    archive_root: Path,
    *,
    date_token: str,
    run_token: str,
    downloaded: list[Path],
) -> Path | None:
    if not archived:
        return None
    target_dir = archive_root / date_token / task.platform
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = target_dir / f"{run_token}_{task.platform_code}_{task.kind}_{task.slug}_manifest.json"
    payload = {
        "task": task.key,
        "platform": task.platform,
        "kind": task.kind,
        "date_token": date_token,
        "run_token": run_token,
        "downloaded": [str(path) for path in downloaded],
        "archived": [item.as_dict() for item in archived],
    }
    write_json(manifest, payload)
    return manifest


def files_created_since(folder: Path, since_timestamp: float, *, limit: int = 20) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    candidates: list[Path] = []
    ignored_suffixes = {".crdownload", ".tmp", ".part"}
    allowed_suffixes = {".csv", ".xls", ".xlsx", ".zip"}
    for child in folder.iterdir():
        if not child.is_file():
            continue
        suffix = child.suffix.lower()
        if suffix in ignored_suffixes or suffix not in allowed_suffixes:
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        if stat.st_mtime >= since_timestamp - 1:
            candidates.append(child)
    candidates.sort(key=lambda path: path.stat().st_mtime)
    return candidates[:limit]


def wait_for_watched_files(folder: Path, since_timestamp: float, *, limit: int = 20, timeout_seconds: int = 20) -> list[Path]:
    deadline = time.monotonic() + max(0, timeout_seconds)
    last_candidates: list[Path] = []
    while True:
        candidates = files_created_since(folder, since_timestamp, limit=limit)
        partials = active_partial_downloads(folder, since_timestamp)
        if candidates and not partials:
            return candidates
        last_candidates = candidates
        if time.monotonic() >= deadline:
            return last_candidates
        time.sleep(0.5)


def active_partial_downloads(folder: Path, since_timestamp: float) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    partials: list[Path] = []
    for child in folder.iterdir():
        if not child.is_file() or child.suffix.lower() not in {".crdownload", ".tmp", ".part"}:
            continue
        try:
            if child.stat().st_mtime >= since_timestamp - 1:
                partials.append(child)
        except OSError:
            continue
    return partials


def extract_zip(task: RobotTask, source: Path, target_dir: Path, *, run_token: str) -> list[ArchivedFile]:
    extracted: list[ArchivedFile] = []
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_name = Path(member.filename).name
            if not member_name:
                continue
            suffix = Path(member_name).suffix.lower()
            if suffix not in {".csv", ".xls", ".xlsx"}:
                continue
            target = target_dir / normalized_name(task, member_name, run_token=run_token)
            target = unique_path(target)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(ArchivedFile(source=source, archived=target, extracted_from=source))
    return extracted


def copy_when_stable(source: Path, target: Path, *, attempts: int = 10, delay_seconds: float = 0.5) -> None:
    last_size = -1
    for _ in range(attempts):
        try:
            current_size = source.stat().st_size
            if current_size == last_size:
                shutil.copy2(source, target)
                return
            last_size = current_size
        except OSError:
            pass
        time.sleep(delay_seconds)
    shutil.copy2(source, target)


def normalized_name(task: RobotTask, original_name: str, *, run_token: str) -> str:
    original = safe_filename(original_name)
    path = Path(original)
    stem = safe_filename(path.stem)[:80] or "download"
    prefix = f"{run_token}_{task.platform_code}_{task.kind}_{task.slug}"
    if stem.lower() in {task.kind.lower(), task.slug.lower(), "download", "export"}:
        return f"{prefix}{path.suffix.lower()}"
    return f"{prefix}_{stem}{path.suffix.lower()}"


def safe_filename(value: str) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip().strip(".")
    text = re.sub(r"\s+", " ", text)
    return text or "download"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot find unique path for {path}")


def run_import_check(*, batch_dir: Path, platform: str, kind: str, evidence_root: Path, date_token: str, task_key: str) -> dict[str, Any]:
    evidence = evidence_root / f"import-check-{task_key}-{date_token}-{datetime.now().strftime('%H%M%S')}.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "import_daily_files_to_feishu.py"),
        "--batch-dir",
        str(batch_dir),
        "--dry-run",
        "--platform",
        platform,
        "--kind",
        kind,
        "--evidence",
        str(evidence),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=180, encoding="utf-8", errors="replace")
    return {
        "returncode": completed.returncode,
        "evidence": str(evidence),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
