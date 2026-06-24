from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from crawl_douyin_creator_screening_to_feishu import (
    CreatorScreeningFeishuClient,
    TABLE_NAME,
    crawl,
    row_profile_key,
    write_json,
)


def load_rows(path: str) -> list[dict[str, Any]]:
    if not path:
        return []
    payload_path = Path(path)
    if not payload_path.exists():
        return []
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    return list(payload.get("rows") or [])


async def async_main(args: argparse.Namespace) -> int:
    keywords = [item.strip() for item in (args.keywords or args.keyword).split(",") if item.strip()]
    evidence_dir = Path(args.evidence_dir) / f"creator-comment-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    exclude_rows = load_rows(args.exclude_rows)
    exclude_profiles = {row_profile_key(row) for row in exclude_rows if row_profile_key(row)}

    rows: list[dict[str, Any]] = []
    crawl_meta: dict[str, Any] = {"keyword_runs": []}
    for index, keyword in enumerate(keywords, 1):
        if len(rows) >= args.target:
            break
        batch_target = min(args.per_keyword_target, args.target - len(rows))
        keyword_dir = evidence_dir / f"keyword-{index:02d}"
        batch_rows, batch_meta = await crawl(keyword, batch_target, keyword_dir, exclude_profiles)
        for row in batch_rows:
            profile_key = row_profile_key(row)
            if profile_key and profile_key not in exclude_profiles:
                rows.append(row)
                exclude_profiles.add(profile_key)
            if len(rows) >= args.target:
                break
        write_json(evidence_dir / "rows.partial.json", {"rows": rows})
        crawl_meta["keyword_runs"].append(
            {
                "keyword": keyword,
                "requested": batch_target,
                "collected": len(batch_rows),
                "accepted_total": len(rows),
                "meta": batch_meta,
            }
        )
    write_json(evidence_dir / "rows.json", {"rows": rows})

    feishu_summary: dict[str, Any] = {}
    if rows:
        feishu = CreatorScreeningFeishuClient()
        table_id, reused = feishu.ensure_table()
        record_ids = feishu.create_records(table_id, rows)
        keys = {row["unique_key"] for row in rows}
        readback = feishu.readback_by_unique_keys(table_id, keys)
        readback_keys = {(item.get("fields") or {}).get("unique_key") for item in readback}
        comment_json_field = "评论原始数据JSON"
        readback_comment_rows = sum(1 for item in readback if (item.get("fields") or {}).get(comment_json_field))
        feishu_summary = {
            "table_name": TABLE_NAME,
            "table_id": table_id,
            "table_reused": reused,
            "created_record_ids": record_ids,
            "created_count": len(record_ids),
            "readback_count": len(readback),
            "readback_comment_rows": readback_comment_rows,
            "missing_unique_keys": sorted(keys - readback_keys),
        }

    rows_with_comments = sum(1 for row in rows if int(row.get("真实评论条数") or 0) > 0)
    total_real_comments = sum(int(row.get("真实评论条数") or 0) for row in rows)
    summary = {
        "status": "success"
        if len(rows) == args.target
        and rows_with_comments == args.target
        and not feishu_summary.get("missing_unique_keys")
        else "partial",
        "keywords": keywords,
        "target": args.target,
        "excluded_existing_profiles": len(exclude_profiles),
        "collected": len(rows),
        "rows_with_real_comments": rows_with_comments,
        "total_real_comments": total_real_comments,
        "crawl_meta": crawl_meta,
        "feishu": feishu_summary,
        "rows_path": str(evidence_dir / "rows.json"),
        "written_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(evidence_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["status"] == "success" else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl Douyin creators with real public comment samples and write to Feishu.")
    parser.add_argument("--keyword", default="洗面奶")
    parser.add_argument(
        "--keywords",
        default="洗面奶,洗面奶测评,洗面奶推荐,氨基酸洗面奶,男士洗面奶,油皮洗面奶,敏感肌洗面奶,洁面乳,控油洗面奶,学生党洗面奶",
    )
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--per-keyword-target", type=int, default=12)
    parser.add_argument("--evidence-dir", default="docs/live-evidence")
    parser.add_argument("--exclude-rows", default="")
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
