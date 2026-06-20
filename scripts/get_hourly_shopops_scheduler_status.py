from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "docs" / "live-evidence" / "data-robot"
SCHEDULER_DIR = EVIDENCE_ROOT / "scheduler"
PID_FILE = SCHEDULER_DIR / "hourly-shopops-scheduler.pid"
CURRENT_STATE_FILE = EVIDENCE_ROOT / "hourly-shopops-current-state.json"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def is_pid_running(pid: str) -> bool:
    if not pid.strip():
        return False
    try:
        import subprocess

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"if (Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue) {{ '1' }} else {{ '0' }}",
            ],
            text=True,
            capture_output=True,
            timeout=5,
        )
        return completed.stdout.strip() == "1"
    except Exception:
        return False


def latest_file(root: Path, pattern: str) -> Path | None:
    try:
        files = list(root.glob(pattern))
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def file_info(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "path": str(path),
        "last_write": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "length": stat.st_size,
    }


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def tail_lines(path: Path | None, limit: int = 80) -> list[str]:
    if not path:
        return []
    text = read_text(path)
    if not text:
        return []
    return text.splitlines()[-limit:]


def next_run_hint(lines: list[str]) -> str:
    markers = (
        "Next ShopOps scheduled import starts at ",
        "First ShopOps scheduled import starts in ",
        "Recent successful ShopOps import found; first run starts in ",
        "Outside collection window; sleeping ",
    )
    for line in reversed(lines):
        if any(marker in line for marker in markers):
            return line
    return ""


def parse_scheduler_wait(hint: str, stdout_info: dict[str, Any] | None) -> dict[str, Any]:
    if not hint:
        return {"status": "unknown", "reason": "no scheduler wait marker in stdout tail"}
    now = datetime.now()
    if match := re.search(r"starts at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \(in (\d+) seconds", hint):
        try:
            next_run_at = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            next_run_at = None
        if next_run_at:
            remaining = max(0, int((next_run_at - now).total_seconds()))
            return {
                "status": "waiting" if remaining else "due_or_running",
                "next_run_at": next_run_at.strftime("%Y-%m-%d %H:%M:%S"),
                "remaining_seconds": remaining,
                "source": "next_run_at_log_marker",
            }
    if match := re.search(r"starts in (\d+) seconds", hint):
        if stdout_info and stdout_info.get("last_write"):
            try:
                logged_at = datetime.strptime(str(stdout_info["last_write"]), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logged_at = None
            if logged_at:
                next_run_at = logged_at + timedelta(seconds=int(match.group(1)))
                remaining = max(0, int((next_run_at - now).total_seconds()))
                return {
                    "status": "waiting" if remaining else "due_or_running",
                    "next_run_at": next_run_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "remaining_seconds": remaining,
                    "source": "first_delay_log_marker_plus_stdout_mtime",
                }
        return {
            "status": "waiting_unknown_remaining",
            "original_seconds": int(match.group(1)),
            "source": "first_delay_log_marker_without_stdout_mtime",
        }
    if match := re.search(r"sleeping (\d+) seconds", hint):
        return {
            "status": "outside_collection_window",
            "original_seconds": int(match.group(1)),
            "source": "outside_window_log_marker",
        }
    return {"status": "unknown", "hint": hint}


def seconds_since_file_write(info: dict[str, Any] | None) -> int | None:
    if not info or not info.get("last_write"):
        return None
    try:
        last_write = datetime.strptime(str(info["last_write"]), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return max(0, int((datetime.now() - last_write).total_seconds()))


def cdp_pages(url: str) -> list[dict[str, Any]]:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/json/list", timeout=5) as response:
            targets = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return [{"error": f"{type(exc).__name__}: {exc}"}]
    pages = []
    for target in targets:
        if isinstance(target, dict) and target.get("type") == "page":
            pages.append(
                {
                    "id": target.get("id"),
                    "title": target.get("title"),
                    "url": target.get("url"),
                }
            )
    return pages


def main() -> int:
    pid = read_text(PID_FILE).strip() if PID_FILE.exists() else ""
    latest_stdout = latest_file(SCHEDULER_DIR, "*.out.log")
    latest_stderr = latest_file(SCHEDULER_DIR, "*.err.log")
    latest_import = latest_file(EVIDENCE_ROOT, "hourly-shopops-import-*.json")
    log_tail = tail_lines(latest_stdout)
    douyin_pages = cdp_pages("http://127.0.0.1:9224")
    tmall_pages = cdp_pages("http://127.0.0.1:9225")
    stdout_info = file_info(latest_stdout)
    stderr_info = file_info(latest_stderr)
    hint = next_run_hint(log_tail)
    status = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scheduler": {
            "pid_file": str(PID_FILE),
            "pid": pid,
            "running": is_pid_running(pid),
            "latest_stdout": stdout_info,
            "latest_stdout_age_seconds": seconds_since_file_write(stdout_info),
            "latest_stderr": stderr_info,
            "latest_stderr_age_seconds": seconds_since_file_write(stderr_info),
            "next_run_hint": hint,
            "scheduler_wait": parse_scheduler_wait(hint, stdout_info),
        },
        "current_state": read_json_file(CURRENT_STATE_FILE),
        "latest_import": file_info(latest_import),
        "chrome": {
            "douyin_page_count": len([page for page in douyin_pages if "error" not in page]),
            "douyin_pages": douyin_pages,
            "tmall_page_count": len([page for page in tmall_pages if "error" not in page]),
            "tmall_pages": tmall_pages,
        },
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
