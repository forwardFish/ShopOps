from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = ROOT / "docs" / "live-evidence" / "data-robot"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_hourly_evidence(evidence_root: Path) -> Path:
    files = sorted(evidence_root.glob("hourly-shopops-import-*.json"), key=lambda path: path.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"No hourly-shopops-import evidence under {evidence_root}")
    return files[-1]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def seconds_between(start: str | None, end: str | None) -> int | None:
    started = parse_time(start)
    ended = parse_time(end)
    if not started or not ended:
        return None
    return max(0, int((ended - started).total_seconds()))


def format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    minutes, sec = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m{sec:02d}s"
    return f"{sec}s"


def progress_events(order_evidence: dict[str, Any], stage: str, platform: str | None = None) -> list[dict[str, Any]]:
    events = []
    for item in order_evidence.get("progress") or []:
        if item.get("stage") != stage:
            continue
        detail = item.get("detail") or {}
        if platform is not None and detail.get("platform") != platform:
            continue
        events.append(item)
    return events


def stage_duration(order_evidence: dict[str, Any], start_stage: str, end_stage: str, platform: str | None = None) -> int | None:
    starts = progress_events(order_evidence, start_stage, platform)
    ends = progress_events(order_evidence, end_stage, platform)
    if not starts or not ends:
        return None
    return seconds_between(starts[0].get("at"), ends[-1].get("at"))


def summarize_order_evidence(order_evidence_path: Path | None) -> dict[str, Any]:
    if not order_evidence_path or not order_evidence_path.exists():
        return {"available": False, "path": str(order_evidence_path) if order_evidence_path else ""}
    data = load_json(order_evidence_path)
    progress = data.get("progress") or []
    started_at = progress[0].get("at") if progress else None
    finished_at = progress[-1].get("at") if progress else None
    platforms: dict[str, Any] = {}
    for platform, result in ((data.get("writes") or {}).get("orders") or {}).items():
        platforms[platform] = {
            "created": result.get("created"),
            "updated": result.get("updated"),
            "saved": result.get("saved"),
            "readback_count": result.get("readback_count"),
            "missing_unique_keys": result.get("missing_unique_keys") or [],
            "upsert_duration": format_duration(stage_duration(data, "upsert_orders_started", "upsert_orders_done", platform)),
            "prune_duration": format_duration(stage_duration(data, "prune_stale_orders_started", "prune_stale_orders_done", platform)),
            "readback_duration": format_duration(stage_duration(data, "readback_orders_started", "readback_orders_done", platform)),
        }
    return {
        "available": True,
        "path": str(order_evidence_path),
        "status": data.get("status"),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration": format_duration(seconds_between(started_at, finished_at)),
        "platforms": platforms,
    }


def summarize_hourly(path: Path) -> dict[str, Any]:
    data = load_json(path)
    orders = data.get("orders") or {}
    order_evidence = orders.get("import_evidence")
    order_evidence_path = Path(order_evidence) if order_evidence else None
    if order_evidence_path and not order_evidence_path.is_absolute():
        order_evidence_path = ROOT / order_evidence_path
    summary_rows = (data.get("hourly_interval_summary") or {}).get("rows") or []
    compact_rows = []
    for row in summary_rows:
        compact_rows.append(
            {
                "unique_key": row.get("unique_key"),
                "平台": row.get("平台"),
                "今日累计订单数": row.get("今日累计订单数"),
                "新增订单数": row.get("新增订单数"),
                "今日累计订单销售额": row.get("今日累计订单销售额"),
                "新增订单销售额": row.get("新增订单销售额"),
                "今日累计投流消耗": row.get("今日累计投流消耗"),
                "新增投流消耗": row.get("新增投流消耗"),
                "窗口开始": row.get("窗口开始"),
                "窗口结束": row.get("窗口结束"),
                "本次采集时间": row.get("本次采集时间"),
            }
        )
    return {
        "hourly_evidence": str(path),
        "run_token": data.get("run_token"),
        "status": data.get("status"),
        "stat_date": data.get("stat_date"),
        "orders_status": orders.get("status"),
        "tmall_excel_ready": orders.get("tmall_excel_ready"),
        "tmall_excel_required": orders.get("tmall_excel_required"),
        "order_import": summarize_order_evidence(order_evidence_path),
        "hourly_interval_summary": {
            "status": (data.get("hourly_interval_summary") or {}).get("status"),
            "row_count": (data.get("hourly_interval_summary") or {}).get("row_count"),
            "readback_count": (data.get("hourly_interval_summary") or {}).get("readback_count"),
            "rows": compact_rows,
        },
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    evidence_root = Path(args.evidence_root)
    path = Path(args.evidence) if args.evidence else latest_hourly_evidence(evidence_root)
    print(json.dumps(summarize_hourly(path), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
