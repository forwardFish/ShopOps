from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from crawl_douyin_creator_screening_to_feishu import (  # noqa: E402
    CreatorScreeningFeishuClient,
    TABLE_NAME,
    comment_credibility_fields,
    concise_decision_fields,
    write_json,
)

CONCISE_FIELDS = [
    "\u5185\u5bb9\u76f8\u5173\u5ea6",
    "\u666e\u901a\u89c6\u9891\u4e92\u52a8\u60c5\u51b5",
    "\u8bc4\u8bba\u539f\u59cb\u6837\u672c",
    "\u8bc4\u8bba\u5206\u6790",
    "\u8bc4\u8bba\u53ef\u4fe1\u5ea6\u8bc4\u5206",
    "\u8bc4\u8bba\u53ef\u4fe1\u5ea6\u7b49\u7ea7",
    "\u6700\u7ec8\u7ed3\u8bba",
]


def load_json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def video_samples(row: dict[str, Any]) -> list[dict[str, str]]:
    samples = load_json_list(row.get("\u666e\u901a\u89c6\u9891\u6837\u672cJSON"))
    if samples:
        return samples  # type: ignore[return-value]
    fallback: list[dict[str, str]] = []
    for index in range(1, 4):
        heat = str(row.get(f"\u89c6\u9891{index}\u83b7\u8d5e/\u70ed\u5ea6") or "")
        if heat:
            fallback.append({"heat": heat})
    return fallback


def enriched_fields(row: dict[str, Any]) -> dict[str, str]:
    comments = load_json_list(row.get("\u8bc4\u8bba\u539f\u59cb\u6570\u636eJSON"))
    keyword = str(row.get("\u641c\u7d22\u5173\u952e\u8bcd") or "")
    context = "\n".join(
        str(row.get(name) or "")
        for name in ["\u539f\u59cb\u641c\u7d22\u5361\u7247", "\u539f\u59cb\u4e3b\u9875\u6587\u672c", "\u8bc4\u8bba\u6765\u6e90\u4f5c\u54c1\u6807\u9898"]
    )
    comment_fields = comment_credibility_fields(keyword, comments, context)
    scoring = {
        "\u5185\u5bb9\u76f8\u5173\u8bc4\u5206": str(row.get("\u5185\u5bb9\u76f8\u5173\u8bc4\u5206") or "0"),
        "\u4e92\u52a8\u7a33\u5b9a\u6027\u8bc4\u5206": str(row.get("\u4e92\u52a8\u7a33\u5b9a\u6027\u8bc4\u5206") or "0"),
        "\u6ce8\u6c34\u98ce\u9669\u8bc4\u5206": str(row.get("\u6ce8\u6c34\u98ce\u9669\u8bc4\u5206") or "0"),
    }
    return concise_decision_fields(scoring, comment_fields, video_samples(row))


def batch_update(client: CreatorScreeningFeishuClient, table_id: str, updates: list[dict[str, Any]]) -> int:
    saved = 0
    for offset in range(0, len(updates), 500):
        chunk = updates[offset : offset + 500]
        client._request(
            "POST",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records/batch_update",
            {"records": chunk},
        )
        saved += len(chunk)
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill concise comment credibility fields to Feishu creator table.")
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, default=Path("docs/live-evidence"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    started = datetime.now()
    evidence_dir = args.evidence_dir / f"creator-comment-credibility-backfill-{started.strftime('%Y%m%d-%H%M%S')}"
    payload = json.loads(args.rows.read_text(encoding="utf-8"))
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    enriched = [{**row, **enriched_fields(row)} for row in rows]
    keys = {str(row.get("unique_key") or "") for row in enriched if row.get("unique_key")}

    client = CreatorScreeningFeishuClient()
    table_id, reused = client.ensure_table()
    records = client.readback_by_unique_keys(table_id, keys) if keys else []
    by_key = {(item.get("fields") or {}).get("unique_key"): item for item in records}
    updates: list[dict[str, Any]] = []
    for row in enriched:
        item = by_key.get(row.get("unique_key"))
        record_id = str((item or {}).get("record_id") or "")
        if not record_id:
            continue
        updates.append({"record_id": record_id, "fields": {field: row.get(field, "") for field in CONCISE_FIELDS}})

    saved = 0 if args.dry_run else batch_update(client, table_id, updates)
    readback = client.readback_by_unique_keys(table_id, keys) if keys and not args.dry_run else records
    complete = len(readback) >= len(keys) and len(updates) == len(keys)
    summary = {
        "status": "dry_run_success" if args.dry_run and complete else "success" if complete else "partial",
        "table_name": TABLE_NAME,
        "table_id": table_id,
        "table_reused": reused,
        "source_rows": str(args.rows),
        "input_rows": len(rows),
        "unique_keys": len(keys),
        "matched_records": len(updates),
        "updated_records": saved,
        "readback_count": len(readback),
        "fields": CONCISE_FIELDS,
        "evidence_dir": str(evidence_dir),
        "written_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_json(evidence_dir / "enriched-rows.json", {"rows": enriched})
    write_json(evidence_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())