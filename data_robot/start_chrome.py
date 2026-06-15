from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from data_robot.common import PROFILE_ROOT
from data_robot.tasks import TASKS


BROWSER_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


DEFAULT_BROWSER_FLAGS = (
    "--remote-debugging-address=127.0.0.1",
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check",
)


def default_profile_root() -> Path:
    return Path(os.environ.get("SHOP_DATA_ROBOT_PROFILE_ROOT") or PROFILE_ROOT)


def chrome_path() -> Path | None:
    return next((path for path in BROWSER_PATHS if path.exists()), None)


def build_browser_command(
    task_key: str,
    *,
    port: int,
    start_url: str | None = None,
    profile_suffix: str = "cdp",
    profile_root: Path | str | None = None,
    browser_path: Path | None = None,
) -> list[str]:
    browser = browser_path or chrome_path()
    if not browser:
        raise RuntimeError("Chrome executable not found.")
    task = TASKS[task_key]
    root = Path(profile_root) if profile_root else default_profile_root()
    profile = root / f"{task.profile}-{profile_suffix}"
    profile.mkdir(parents=True, exist_ok=True)
    return [
        str(browser),
        f"--remote-debugging-port={port}",
        *DEFAULT_BROWSER_FLAGS,
        f"--user-data-dir={profile}",
        start_url or task.url,
    ]


def start_chrome_for_task(
    task_key: str,
    *,
    port: int,
    start_url: str | None = None,
    profile_suffix: str = "cdp",
    profile_root: Path | str | None = None,
) -> subprocess.Popen:
    command = build_browser_command(
        task_key,
        port=port,
        start_url=start_url,
        profile_suffix=profile_suffix,
        profile_root=profile_root,
    )
    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def start_chrome_for_task_with_log(
    task_key: str,
    *,
    port: int,
    log_path: Path,
    start_url: str | None = None,
    profile_suffix: str = "cdp",
    profile_root: Path | str | None = None,
) -> subprocess.Popen:
    command = build_browser_command(
        task_key,
        port=port,
        start_url=start_url,
        profile_suffix=profile_suffix,
        profile_root=profile_root,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("w", encoding="utf-8", errors="replace")
    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [*command, "--enable-logging=stderr", "--v=1"],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        creationflags=creationflags,
        close_fds=True,
    )


def chrome_profile_dir(task_key: str, *, profile_suffix: str = "cdp", profile_root: Path | str | None = None) -> Path:
    task = TASKS[task_key]
    root = Path(profile_root) if profile_root else default_profile_root()
    return root / f"{task.profile}-{profile_suffix}"


def chrome_process_ids_for_profile(profile_dir: Path) -> list[int]:
    resolved = str(profile_dir.resolve())
    ps_value = "'" + resolved.replace("'", "''") + "'"
    ps_script = (
        "$targetProfile = "
        + ps_value
        + "; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -in @('chrome.exe', 'msedge.exe') } | "
        "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($targetProfile) } | "
        "Select-Object -ExpandProperty ProcessId | ConvertTo-Json"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        text=True,
        capture_output=True,
        timeout=20,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    payload: Any = json.loads(completed.stdout)
    if isinstance(payload, int):
        return [payload]
    if isinstance(payload, list):
        return [int(item) for item in payload]
    return []


def stop_chrome_for_task(
    task_key: str,
    *,
    wait_seconds: float = 3,
    profile_suffix: str = "cdp",
    profile_root: Path | str | None = None,
) -> list[int]:
    profile = chrome_profile_dir(task_key, profile_suffix=profile_suffix, profile_root=profile_root)
    pids = chrome_process_ids_for_profile(profile)
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
    if pids:
        time.sleep(wait_seconds)
    return pids


def restart_chrome_for_task(
    task_key: str,
    *,
    port: int,
    start_url: str | None = None,
    profile_suffix: str = "cdp",
    profile_root: Path | str | None = None,
) -> subprocess.Popen:
    stop_chrome_for_task(task_key, profile_suffix=profile_suffix, profile_root=profile_root)
    return start_chrome_for_task(
        task_key,
        port=port,
        start_url=start_url,
        profile_suffix=profile_suffix,
        profile_root=profile_root,
    )


def wait_for_debug_port(port: int, *, timeout_seconds: int = 20, stable_seconds: int = 10) -> bool:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{port}/json/version"
    first_ready_at: float | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    first_ready_at = first_ready_at or time.monotonic()
                    if time.monotonic() - first_ready_at >= stable_seconds:
                        return True
        except Exception:
            first_ready_at = None
            time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Start a normal Chrome window with remote debugging for data_robot.")
    parser.add_argument("task", choices=sorted(TASKS))
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--restart", action="store_true", help="Close the matching data_robot Chrome profile before starting.")
    parser.add_argument(
        "--profile-suffix",
        default="cdp",
        help="Profile suffix under data_robot/profiles. Use another value when the default profile is locked.",
    )
    parser.add_argument(
        "--profile-root",
        default=str(default_profile_root()),
        help="Root folder for browser user-data profiles.",
    )
    parser.add_argument("--log", default="", help="Optional browser stderr/stdout log path for diagnostics.")
    args = parser.parse_args()

    if args.restart:
        stop_chrome_for_task(args.task, profile_suffix=args.profile_suffix, profile_root=args.profile_root)
    process = (
        start_chrome_for_task_with_log(
            args.task,
            port=args.port,
            profile_suffix=args.profile_suffix,
            profile_root=args.profile_root,
            log_path=Path(args.log),
        )
        if args.log
        else start_chrome_for_task(
            args.task,
            port=args.port,
            profile_suffix=args.profile_suffix,
            profile_root=args.profile_root,
        )
    )
    if not wait_for_debug_port(args.port):
        print(
            f"Browser process {process.pid} started for {args.task}, but CDP did not become ready on "
            f"http://127.0.0.1:{args.port}. The profile may be locked or this browser may be blocked.",
            flush=True,
        )
        return 2
    print(f"Browser started for {args.task}. Attach with --cdp-url http://127.0.0.1:{args.port}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
