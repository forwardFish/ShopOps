from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.crawl_douyin_creator_screening_to_feishu import CreatorScreeningFeishuClient
from scripts.screen_douyin_creator_roi_candidates import screen_row

CREATOR_NAME = "\u8fbe\u4eba\u540d\u79f0"
SEARCH_KEYWORD = "\u641c\u7d22\u5173\u952e\u8bcd"
COMMENTS_JSON = "\u8bc4\u8bba\u539f\u59cb\u6570\u636eJSON"
COMMENT_TOTAL = "\u8bc4\u8bba\u63a5\u53e3\u8fd4\u56de\u603b\u6570"
FOLLOWERS = "\u7c89\u4e1d\u6570"
PROFILE_URL = "\u4e3b\u9875\u94fe\u63a5"
DOUYIN_ID = "\u6296\u97f3\u53f7"
COLLECTED_AT = "\u91c7\u96c6\u65f6\u95f4"

ROI_TIER_RESULT = "ROI\u7b5b\u9009\u7b49\u7ea7"
ROI_SCORE_RESULT = "ROI\u7b5b\u9009\u5206"
COMMENT_QUALITY_RESULT = "\u8bc4\u8bba\u8d28\u91cf\u8bc4\u5206"
STABILITY_RESULT = "\u4e92\u52a8\u7a33\u5b9a\u6027\u8bc4\u5206"
WATER_RISK_RESULT = "\u6ce8\u6c34\u98ce\u9669\u8bc4\u5206"
MISMATCH_RISK_RESULT = "\u7c89\u8d5e\u9519\u914d\u98ce\u9669"
MISMATCH_LABEL_RESULT = "\u7c89\u8d5e\u98ce\u9669\u6807\u7b7e"
VIDEO_COUNT_RESULT = "\u666e\u901a\u89c6\u9891\u6837\u672c\u6570"
BLOCKERS_RESULT = "\u4e3b\u8981\u62e6\u622a\u539f\u56e0"
ACTION_RESULT = "\u5efa\u8bae\u52a8\u4f5c"
LIMITATIONS_RESULT = "\u6570\u636e\u9650\u5236"

ROI_SCORE_FIELD = "ROI\u7b5b\u9009\u5206"
ROI_TIER_FIELD = "ROI\u5206\u5c42"
STABILITY_FIELD = "\u4e92\u52a8\u7a33\u5b9a\u6027\u8bc4\u5206"
WATER_RISK_FIELD = "\u6ce8\u6c34\u98ce\u9669\u8bc4\u5206"
MISMATCH_RISK_FIELD = "\u7c89\u8d5e\u9519\u914d\u98ce\u9669"
FIRST_TEST_FIELD = "\u9996\u6d4b\u5efa\u8bae"
VIDEO_NOTE_FIELD = "\u666e\u901a\u89c6\u9891\u91c7\u6837\u8bf4\u660e"
SCORE_BASIS_FIELD = "\u8bc4\u5206\u4f9d\u636e"
SCORE_VERSION_FIELD = "\u8bc4\u5206\u516c\u5f0f\u7248\u672c"
SCORE_CONCLUSION_FIELD = "\u8bc4\u5206\u7ed3\u8bba"
MANUAL_STATUS_FIELD = "\u4eba\u5de5\u786e\u8ba4\u72b6\u6001"


def parse_comments(fields: dict[str, Any]) -> list[dict[str, Any]]:
    raw = fields.get(COMMENTS_JSON) or "[]"
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]


def record_quality(
    fields: dict[str, Any],
    screened: dict[str, Any],
    comments: list[dict[str, Any]],
) -> tuple[Any, ...]:
    tier = str(screened.get(ROI_TIER_RESULT) or "C")
    tier_rank = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}.get(tier[:1], 0)
    return (
        tier_rank,
        float(screened.get(ROI_SCORE_RESULT) or 0),
        len(comments),
        bool(fields.get(PROFILE_URL)),
        bool(fields.get(DOUYIN_ID)),
        str(fields.get(COLLECTED_AT) or ""),
    )


def update_payload(screened: dict[str, Any]) -> dict[str, Any]:
    tier = str(screened.get(ROI_TIER_RESULT) or "")
    limitations = str(screened.get(LIMITATIONS_RESULT) or "")
    blockers = str(screened.get(BLOCKERS_RESULT) or "")
    basis = (
        "\u5386\u53f2\u771f\u5b9e\u8bc4\u8bba\u6570\u636e\u91cd\u7b97\uff1a"
        f"ROI={screened.get(ROI_SCORE_RESULT)}\uff1b"
        f"\u8bc4\u8bba\u8d28\u91cf={screened.get(COMMENT_QUALITY_RESULT)}\uff1b"
        f"\u4e92\u52a8\u7a33\u5b9a={screened.get(STABILITY_RESULT)}\uff1b"
        f"\u6ce8\u6c34\u98ce\u9669={screened.get(WATER_RISK_RESULT)}\uff1b"
        f"\u62e6\u622a={blockers or '\u65e0'}\uff1b"
        f"\u9650\u5236={limitations or '\u65e0'}"
    )
    risk_parts = [
        str(screened.get(MISMATCH_LABEL_RESULT) or ""),
        f"\u98ce\u9669\u5206={screened.get(MISMATCH_RISK_RESULT)}",
    ]
    return {
        ROI_SCORE_FIELD: str(screened.get(ROI_SCORE_RESULT) or ""),
        ROI_TIER_FIELD: tier,
        STABILITY_FIELD: str(screened.get(STABILITY_RESULT) or ""),
        WATER_RISK_FIELD: str(screened.get(WATER_RISK_RESULT) or ""),
        MISMATCH_RISK_FIELD: "\uff1b".join(item for item in risk_parts if item),
        FIRST_TEST_FIELD: str(screened.get(ACTION_RESULT) or ""),
        VIDEO_NOTE_FIELD: limitations,
        SCORE_BASIS_FIELD: basis,
        SCORE_VERSION_FIELD: "creator-screening-v4-real-comment-backfill",
        SCORE_CONCLUSION_FIELD: tier,
        MANUAL_STATUS_FIELD: "\u6570\u636e\u521d\u7b5b\u5f85\u4eba\u5de5\u786e\u8ba4",
    }


def fetch_records(
    client: CreatorScreeningFeishuClient,
    table_id: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = client._request(
            "GET",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records",
            params=params,
        )
        records.extend(data.get("items") or [])
        page_token = str(data.get("page_token") or "")
        if not data.get("has_more") or not page_token:
            return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Select unique creators with real comments, score them, "
            "and backfill Feishu ROI fields."
        )
    )
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--min-comments", type=int, default=5)
    parser.add_argument("--evidence-dir", type=Path, default=Path("docs/live-evidence"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    started = datetime.now()
    evidence_dir = (
        args.evidence_dir
        / f"creator-feishu-roi-backfill-{started.strftime('%Y%m%d-%H%M%S')}"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)

    client = CreatorScreeningFeishuClient()
    table_id, reused = client.ensure_table()
    records = fetch_records(client, table_id)

    best_by_name: dict[str, dict[str, Any]] = {}
    for record in records:
        fields = record.get("fields") or {}
        name = str(fields.get(CREATOR_NAME) or "").strip()
        comments = parse_comments(fields)
        if not name or not comments:
            continue
        screened = screen_row(fields)
        candidate = {
            "record_id": str(record.get("record_id") or ""),
            "fields": fields,
            "comments": comments,
            "screened": screened,
            "quality": record_quality(fields, screened, comments),
        }
        current = best_by_name.get(name)
        if current is None or candidate["quality"] > current["quality"]:
            best_by_name[name] = candidate

    candidates = list(best_by_name.values())
    candidates.sort(key=lambda item: item["quality"], reverse=True)
    eligible = [
        item for item in candidates if len(item["comments"]) >= args.min_comments
    ]
    preferred = [
        item
        for item in eligible
        if not str(item["screened"].get(ROI_TIER_RESULT) or "").startswith("D")
    ]
    selected = preferred[: args.target]
    if len(selected) < args.target:
        remaining = [item for item in eligible if item not in selected]
        selected.extend(remaining[: args.target - len(selected)])

    updates = [
        {"record_id": item["record_id"], "fields": update_payload(item["screened"])}
        for item in selected
    ]
    if not args.dry_run:
        for offset in range(0, len(updates), 500):
            client._request(
                "POST",
                (
                    f"/bitable/v1/apps/{client.app_token}/tables/"
                    f"{table_id}/records/batch_update"
                ),
                {"records": updates[offset : offset + 500]},
            )

    readback_records = fetch_records(client, table_id) if not args.dry_run else records
    readback_by_id = {
        str(item.get("record_id") or ""): item.get("fields") or {}
        for item in readback_records
    }
    verified: list[bool] = []
    for item in selected:
        if args.dry_run:
            fields = {**item["fields"], **update_payload(item["screened"])}
        else:
            fields = readback_by_id.get(item["record_id"], {})
        verified.append(
            bool(fields.get(COMMENTS_JSON))
            and bool(fields.get(ROI_SCORE_FIELD))
            and bool(fields.get(ROI_TIER_FIELD))
            and bool(fields.get(FIRST_TEST_FIELD))
        )

    selected_index = []
    for item in selected:
        fields = item["fields"]
        screened = item["screened"]
        selected_index.append(
            {
                "record_id": item["record_id"],
                CREATOR_NAME: fields.get(CREATOR_NAME),
                SEARCH_KEYWORD: fields.get(SEARCH_KEYWORD),
                "\u771f\u5b9e\u8bc4\u8bba\u6761\u6570": len(item["comments"]),
                COMMENT_TOTAL: fields.get(COMMENT_TOTAL),
                FOLLOWERS: fields.get(FOLLOWERS),
                PROFILE_URL: fields.get(PROFILE_URL),
                DOUYIN_ID: fields.get(DOUYIN_ID),
                VIDEO_COUNT_RESULT: screened.get(VIDEO_COUNT_RESULT),
                ROI_SCORE_RESULT: screened.get(ROI_SCORE_RESULT),
                ROI_TIER_FIELD: screened.get(ROI_TIER_RESULT),
                WATER_RISK_RESULT: screened.get(WATER_RISK_RESULT),
                BLOCKERS_RESULT: screened.get(BLOCKERS_RESULT),
                LIMITATIONS_RESULT: screened.get(LIMITATIONS_RESULT),
            }
        )

    finished = datetime.now()
    complete = len(selected) == args.target and all(verified)
    summary = {
        "status": "dry_run_success" if args.dry_run and complete else (
            "success" if complete else "partial"
        ),
        "dry_run": args.dry_run,
        "table_id": table_id,
        "table_reused": reused,
        "total_records": len(records),
        "unique_real_comment_creators": len(candidates),
        "eligible_creators": len(eligible),
        "minimum_comments_required": args.min_comments,
        "selected": len(selected),
        "target": args.target,
        "readback_verified": sum(verified),
        "selected_with_profile_url": sum(
            bool(item["fields"].get(PROFILE_URL)) for item in selected
        ),
        "selected_with_douyin_id": sum(
            bool(item["fields"].get(DOUYIN_ID)) for item in selected
        ),
        "selected_with_30_videos": sum(
            int(item["screened"].get(VIDEO_COUNT_RESULT) or 0) >= 30
            for item in selected
        ),
        "selected_comments_total": sum(len(item["comments"]) for item in selected),
        "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round((finished - started).total_seconds(), 1),
        "token_note": (
            "This local Python/Feishu backfill does not consume model tokens; "
            "only agent inspection and summaries consume model tokens."
        ),
        "selected_index_path": str(evidence_dir / "selected-50-index.json"),
    }
    (evidence_dir / "selected-50-index.json").write_text(
        json.dumps(selected_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (evidence_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
