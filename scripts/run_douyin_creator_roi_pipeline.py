from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FAST_BATCH = ROOT / "scripts" / "run_douyin_creator_comment_fast_batch.py"
PROFILE_CRAWLER = ROOT / "scripts" / "crawl_douyin_creator_screening_to_feishu.py"
ROI_SCREEN = ROOT / "scripts" / "screen_douyin_creator_roi_candidates.py"

DEFAULT_KEYWORDS = [
    "\u6d17\u9762\u5976",
    "\u6d17\u9762\u5976\u6d4b\u8bc4",
    "\u6d17\u9762\u5976\u63a8\u8350",
    "\u6c28\u57fa\u9178\u6d17\u9762\u5976",
    "\u7537\u58eb\u6d17\u9762\u5976",
    "\u6cb9\u76ae\u6d17\u9762\u5976",
    "\u654f\u611f\u808c\u6d17\u9762\u5976",
    "\u6d01\u9762\u4e73",
    "\u63a7\u6cb9\u6d17\u9762\u5976",
    "\u5b66\u751f\u515a\u6d17\u9762\u5976",
    "\u6d17\u9762\u5976\u7ea2\u9ed1\u699c",
    "\u6d01\u9762\u6d4b\u8bc4",
]

def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def cdp_url_from_args(args: argparse.Namespace) -> str:
    url = str(args.cdp_url or "").strip()
    if url:
        return url.rstrip("/")
    return f"http://127.0.0.1:{int(args.cdp_port or 9224)}"


def cdp_is_ready(cdp_url: str, timeout_seconds: int = 3) -> tuple[bool, str]:
    try:
        host_port = cdp_url.rsplit(":", 1)
        host = host_port[0].replace("http://", "").replace("https://", "").strip("/")
        port = int(host_port[1].split("/")[0])
    except Exception as exc:
        return False, f"invalid CDP URL {cdp_url}: {exc}"
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
    except Exception as exc:
        return False, f"tcp not ready: {type(exc).__name__}: {exc}"
    try:
        with urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=timeout_seconds) as response:
            if response.status == 200:
                return True, "ready"
            return False, f"/json/version returned HTTP {response.status}"
    except Exception as exc:
        return False, f"http not ready: {type(exc).__name__}: {exc}"


def creator_identity_key(row: dict[str, Any]) -> str:
    for field in ("\u4e3b\u9875\u94fe\u63a5", "\u6296\u97f3\u53f7", "\u8fbe\u4eba\u540d\u79f0"):
        value = str(row.get(field) or "").strip()
        if value and value not in {"\u641c\u7d22\u5361\u7247\u672a\u63d0\u4f9b", "\u672a\u91c7\u96c6", "None"}:
            return f"{field}:{value.lower()}"
    return f"unique_key:{str(row.get('unique_key') or '').strip()}"


def real_comment_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get("\u771f\u5b9e\u8bc4\u8bba\u6761\u6570") or 0)
    except (TypeError, ValueError):
        return 0


def valid_comment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = creator_identity_key(row)
        if not key or key in seen:
            continue
        if real_comment_count(row) <= 0:
            continue
        seen.add(key)
        result.append(row)
    return result

def best_rows_file(root: Path) -> Path | None:
    candidates = [*root.rglob("rows.json"), *root.rglob("rows.partial.json")]
    best_path: Path | None = None
    best_count = -1
    for path in candidates:
        try:
            rows = valid_comment_rows(read_json(path).get("rows") or [])
        except Exception:
            continue
        if len(rows) > best_count:
            best_count = len(rows)
            best_path = path
    return best_path


def merge_rows(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in [*existing, *incoming]:
        key = creator_identity_key(row)
        if not key or real_comment_count(row) <= 0:
            continue
        current = by_key.get(key)
        if current is None or real_comment_count(row) > real_comment_count(current):
            by_key[key] = row
    return list(by_key.values())[:target]

def split_keywords(raw: str) -> list[str]:
    value = (raw or "").strip()
    if not value:
        return DEFAULT_KEYWORDS[:]
    keywords = [item.strip() for item in value.replace("\uff0c", ",").split(",") if item.strip()]
    if keywords == ["\u6d17\u9762\u5976"]:
        return DEFAULT_KEYWORDS[:]
    return keywords


def feishu_upload_ok(upload_summary: dict[str, Any] | None, expected_count: int) -> bool:
    if not upload_summary or upload_summary.get("status") != "success":
        return False
    feishu = upload_summary.get("feishu") or {}
    return int(feishu.get("readback_count") or 0) >= expected_count and not feishu.get("missing_unique_keys")

def append_browser_args(command: list[str], args: argparse.Namespace) -> None:
    if args.cdp_url:
        command.extend(["--cdp-url", args.cdp_url])
    if args.launch_cdp_browser:
        command.append("--launch-cdp-browser")
    if args.cdp_port:
        command.extend(["--cdp-port", str(args.cdp_port)])
    if args.cdp_profile_root:
        command.extend(["--cdp-profile-root", str(args.cdp_profile_root)])
    if args.cdp_wait_seconds:
        command.extend(["--cdp-wait-seconds", str(args.cdp_wait_seconds)])
    if args.browser:
        command.extend(["--browser", args.browser])
    if args.browser_channel:
        command.extend(["--browser-channel", args.browser_channel])
    if args.headed:
        command.append("--headed")
    if args.direct_cdp:
        command.append("--direct-cdp")


def kill_process_tree(pid: int) -> None:
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["kill", "-TERM", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_command(command: list[str], timeout_seconds: int, cwd: Path, log_path: Path) -> int | str:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            return process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            kill_process_tree(process.pid)
            return "timeout"


def newest_summary(root: Path) -> dict[str, Any] | None:
    summaries = sorted(root.rglob("summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in summaries:
        try:
            payload = read_json(path)
        except Exception:
            continue
        payload["_summary_path"] = str(path)
        return payload
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run resumable Douyin creator collection and ROI screening.")
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--keywords", default="")
    parser.add_argument("--per-keyword-candidates", type=int, default=14)
    parser.add_argument("--comments-per-creator", type=int, default=50)
    parser.add_argument("--profile-video-limit", type=int, default=30)
    parser.add_argument("--collection-mode", choices=["profile", "fast"], default="profile", help="profile collects creator homepage and up to 30 non-pinned normal videos; fast only uses search-card authors/comments.")
    parser.add_argument("--round-timeout-seconds", type=int, default=900)
    parser.add_argument("--search-timeout-seconds", type=int, default=180)
    parser.add_argument("--comment-timeout-seconds", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=Path("docs/live-evidence"))
    parser.add_argument("--seed-rows", type=Path, default=None)
    parser.add_argument("--cdp-url", default="", help="Attach to an existing Chrome CDP URL, e.g. http://127.0.0.1:9224.")
    parser.add_argument("--launch-cdp-browser", action="store_true", help="Start visible Chrome/CDP before collecting.")
    parser.add_argument("--cdp-port", type=int, default=9224)
    parser.add_argument("--cdp-profile-root", default="")
    parser.add_argument("--cdp-wait-seconds", type=int, default=45)
    parser.add_argument("--browser", default="chrome")
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--direct-cdp", action="store_true", help="Use the native CDP client in the crawler, avoiding the Playwright driver.")
    args = parser.parse_args()
    keywords = split_keywords(args.keywords)

    pipeline_started = datetime.now()
    pipeline_dir = args.out_dir / f"creator-roi-pipeline-{pipeline_started.strftime('%Y%m%d-%H%M%S')}"
    batch_root = pipeline_dir / "batches"
    upload_root = pipeline_dir / "upload"
    roi_root = pipeline_dir / "roi-screening"
    master_path = pipeline_dir / "master-rows.json"
    summary_path = pipeline_dir / "pipeline-summary.json"
    pipeline_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    if args.seed_rows and args.seed_rows.exists():
        rows = valid_comment_rows(read_json(args.seed_rows).get("rows") or [])
    write_json(master_path, {"rows": rows})

    if args.direct_cdp and args.cdp_url and not args.launch_cdp_browser:
        cdp_url = cdp_url_from_args(args)
        cdp_ready, cdp_reason = cdp_is_ready(cdp_url)
        if not cdp_ready:
            final_summary = {
                "status": "blocked_chrome_cdp_not_ready",
                "target": args.target,
                "collected": len(rows),
                "collection_mode": args.collection_mode,
                "comments_per_creator": args.comments_per_creator,
                "profile_video_limit": args.profile_video_limit,
                "total_real_comments": sum(int(row.get("真实评论条数") or 0) for row in rows),
                "pipeline_dir": str(pipeline_dir),
                "master_rows_path": str(master_path),
                "chrome_cdp": {
                    "cdp_url": cdp_url,
                    "ready": False,
                    "reason": cdp_reason,
                    "check_command": f"python scripts/check_douyin_creator_chrome_cdp.py --cdp-url {cdp_url}",
                    "start_command": f"powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_douyin_creator_cdp_browser.ps1 -Port {int(args.cdp_port or 9224)} -Keyword {keywords[0] if keywords else '洗面奶'}",
                },
                "rounds": [],
                "started_at": pipeline_started.strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_seconds": round((datetime.now() - pipeline_started).total_seconds(), 1),
                "token_note": "本地 Python/Chrome CDP 采集不消耗模型 token；当前没有进入采集循环，因为 Chrome CDP 不可用。",
            }
            write_json(summary_path, final_summary)
            print(json.dumps({
                "status": final_summary["status"],
                "target": final_summary["target"],
                "collected": final_summary["collected"],
                "chrome_cdp": final_summary["chrome_cdp"],
                "pipeline_dir": final_summary["pipeline_dir"],
            }, ensure_ascii=False, indent=2))
            return 4

    rounds: list[dict[str, Any]] = []
    for round_index in range(1, args.max_rounds + 1):
        if len(rows) >= args.target:
            break
        round_log = pipeline_dir / "logs" / f"round-{round_index:02d}.log"
        if args.collection_mode == "profile":
            keyword = keywords[(round_index - 1) % len(keywords)]
            command = [
                sys.executable,
                str(PROFILE_CRAWLER),
                "--target",
                str(args.target),
                "--keyword",
                keyword,
                "--comments-per-creator",
                str(args.comments_per_creator),
                "--profile-video-limit",
                str(args.profile_video_limit),
                "--evidence-dir",
                str(batch_root),
                "--seed-rows",
                str(master_path),
            ]
        else:
            command = [
                sys.executable,
                str(FAST_BATCH),
                "--target",
                str(args.target),
                "--per-keyword-candidates",
                str(args.per_keyword_candidates),
                "--comments-per-creator",
                str(args.comments_per_creator),
                "--search-timeout-seconds",
                str(args.search_timeout_seconds),
                "--comment-timeout-seconds",
                str(args.comment_timeout_seconds),
                "--evidence-dir",
                str(batch_root),
                "--seed-rows",
                str(master_path),
            ]
            if args.keywords:
                command.extend(["--keywords", args.keywords])
        append_browser_args(command, args)
        started = datetime.now()
        exit_code = run_command(command, args.round_timeout_seconds, ROOT, round_log)
        best_path = best_rows_file(batch_root)
        incoming: list[dict[str, Any]] = []
        if best_path:
            incoming = valid_comment_rows(read_json(best_path).get("rows") or [])
            rows = merge_rows(rows, incoming, args.target)
            write_json(master_path, {"rows": rows})
        round_summary = newest_summary(batch_root)
        rounds.append(
            {
                "round": round_index,
                "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
                "ended_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "exit_code": exit_code,
                "command": command,
                "log_path": str(round_log),
                "best_rows_path": str(best_path) if best_path else "",
                "incoming_valid_rows": len(incoming),
                "master_valid_rows": len(rows),
                "batch_summary": round_summary,
            }
        )
        write_json(
            summary_path,
            {
                "status": "collecting" if len(rows) < args.target else "collected",
                "target": args.target,
                "collected": len(rows),
                "collection_mode": args.collection_mode,
                "comments_per_creator": args.comments_per_creator,
                "profile_video_limit": args.profile_video_limit,
                "pipeline_dir": str(pipeline_dir),
                "master_rows_path": str(master_path),
                "rounds": rounds,
            },
        )

    upload_summary: dict[str, Any] | None = None
    if rows:
        upload_log = pipeline_dir / "logs" / "upload.log"
        upload_command = [
            sys.executable,
            str(FAST_BATCH),
            "--target",
            str(len(rows)),
            "--seed-rows",
            str(master_path),
            "--evidence-dir",
            str(upload_root),
            "--upload-only",
        ]
        upload_exit = run_command(upload_command, max(300, args.round_timeout_seconds), ROOT, upload_log)
        upload_summary = newest_summary(upload_root) or {"exit_code": upload_exit, "log_path": str(upload_log)}

    roi_exit: int | str | None = None
    roi_log = pipeline_dir / "logs" / "roi-screening.log"
    if rows:
        roi_exit = run_command(
            [
                sys.executable,
                str(ROI_SCREEN),
                "--rows",
                str(master_path),
                "--out-dir",
                str(roi_root),
            ],
            300,
            ROOT,
            roi_log,
        )

    final_summary = {
        "status": "success" if len(rows) >= args.target and feishu_upload_ok(upload_summary, len(rows)) and roi_exit == 0 else "partial",
        "target": args.target,
        "collected": len(rows),
        "collection_mode": args.collection_mode,
        "comments_per_creator": args.comments_per_creator,
        "profile_video_limit": args.profile_video_limit,
        "total_real_comments": sum(int(row.get("真实评论条数") or 0) for row in rows),
        "pipeline_dir": str(pipeline_dir),
        "master_rows_path": str(master_path),
        "roi_outputs": {
            "summary": str(roi_root / "summary.json"),
            "report": str(roi_root / "roi-screening-report.md"),
            "csv": str(roi_root / "roi-screened-candidates.csv"),
            "json": str(roi_root / "roi-screened-candidates.json"),
            "log": str(roi_log),
        },
        "upload_summary": upload_summary,
        "rounds": rounds,
        "started_at": pipeline_started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round((datetime.now() - pipeline_started).total_seconds(), 1),
        "token_note": "本地 Python/Playwright 采集不消耗模型 token；token 主要消耗在模型读取日志、总结和人工监控时。低 token 监控只读本 summary。",
    }
    write_json(summary_path, final_summary)
    print(json.dumps({k: final_summary[k] for k in ["status", "target", "collected", "total_real_comments", "pipeline_dir", "roi_outputs"]}, ensure_ascii=False, indent=2))
    return 0 if final_summary["status"] == "success" else 3


if __name__ == "__main__":
    raise SystemExit(main())
