from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FAST_BATCH = ROOT / "scripts" / "run_douyin_creator_comment_fast_batch.py"
ROI_SCREEN = ROOT / "scripts" / "screen_douyin_creator_roi_candidates.py"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def valid_comment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = str(row.get("unique_key") or "")
        if not key or key in seen:
            continue
        try:
            real_comments = int(row.get("真实评论条数") or 0)
        except ValueError:
            real_comments = 0
        if real_comments <= 0:
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
        key = str(row.get("unique_key") or "")
        if not key:
            continue
        try:
            real_comments = int(row.get("真实评论条数") or 0)
        except ValueError:
            real_comments = 0
        if real_comments <= 0:
            continue
        by_key.setdefault(key, row)
    return list(by_key.values())[:target]


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
    parser.add_argument("--comments-per-creator", type=int, default=20)
    parser.add_argument("--round-timeout-seconds", type=int, default=900)
    parser.add_argument("--search-timeout-seconds", type=int, default=180)
    parser.add_argument("--comment-timeout-seconds", type=int, default=30)
    parser.add_argument("--max-rounds", type=int, default=5)
    parser.add_argument("--out-dir", type=Path, default=Path("docs/live-evidence"))
    parser.add_argument("--seed-rows", type=Path, default=None)
    args = parser.parse_args()

    pipeline_dir = args.out_dir / f"creator-roi-pipeline-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
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

    rounds: list[dict[str, Any]] = []
    for round_index in range(1, args.max_rounds + 1):
        if len(rows) >= args.target:
            break
        round_log = pipeline_dir / "logs" / f"round-{round_index:02d}.log"
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
        "status": "success" if len(rows) >= args.target and upload_summary and roi_exit == 0 else "partial",
        "target": args.target,
        "collected": len(rows),
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
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(summary_path, final_summary)
    print(json.dumps({k: final_summary[k] for k in ["status", "target", "collected", "total_real_comments", "pipeline_dir", "roi_outputs"]}, ensure_ascii=False, indent=2))
    return 0 if final_summary["status"] == "success" else 3


if __name__ == "__main__":
    raise SystemExit(main())
