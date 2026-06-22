from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawl_douyin_creator_screening_to_feishu import (
    CreatorScreeningFeishuClient,
    MOBILE_USER_AGENT,
    TABLE_NAME,
    ai_screen,
    collect_search_candidates,
    comment_signal_summary,
    fetch_real_comments,
    score_creator,
    write_json,
)


DEFAULT_KEYWORDS = [
    "洗面奶",
    "洗面奶测评",
    "洗面奶推荐",
    "氨基酸洗面奶",
    "男士洗面奶",
    "油皮洗面奶",
    "敏感肌洗面奶",
    "洁面乳",
    "控油洗面奶",
    "学生党洗面奶",
    "洗面奶红黑榜",
    "洁面测评",
]


def parse_card_counts(raw_card: str) -> dict[str, str]:
    lines = [line.strip() for line in raw_card.splitlines() if line.strip()]
    counts = [line for line in lines[-6:] if any(ch.isdigit() for ch in line)]
    return {
        "video_visible_count_1": counts[-4] if len(counts) >= 4 else "",
        "video_visible_count_2": counts[-3] if len(counts) >= 3 else "",
        "video_visible_count_3": counts[-2] if len(counts) >= 2 else "",
        "video_visible_count_4": counts[-1] if counts else "",
    }


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_row(keyword: str, candidate: Any, comments: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw_comments = comments.get("comments") or []
    comment_text = "\n".join(str(item.get("text") or "") for item in raw_comments)
    comment_summary = comment_signal_summary(keyword, "\n".join([candidate.raw_card, comment_text]))
    real_comment_count = len(raw_comments)
    if comments.get("status") == "success" and real_comment_count:
        comment_summary["评论采样状态"] = "已抓取真实公开评论"
        comment_summary["评论证据等级"] = "L3-真实评论接口抽样"
        comment_summary["评论样本数"] = str(real_comment_count)
        comment_summary["评论评分依据"] = "已通过 so.douyin.com 公开评论接口抓取真实评论文本抽样；评分按评论文本中的购买意图、使用问题、质疑风险和无效比例信号计算。"
        comment_summary["评论采样限制"] = "当前为公开接口首批评论抽样，不翻评论用户主页，不保存用户UID/头像；授权后可扩大到多页评论和回复链。"
    videos = [{"heat": parse_card_counts(candidate.raw_card).get("video_visible_count_2", "")}]
    scoring = score_creator(keyword, candidate.name, candidate.source_video_title, "", "", "", comment_summary, videos)
    level, reason = ai_screen(keyword, candidate.name, candidate.source_video_title, "", videos)
    unique_source = f"fast-comment|{keyword}|{candidate.name}|{candidate.aweme_id}|{now}"
    unique_key = "creator_comment_" + hashlib.sha1(unique_source.encode("utf-8")).hexdigest()[:16]
    row = {
        "unique_key": unique_key,
        "搜索关键词": keyword,
        "平台": "抖音",
        "来源": "so.douyin.com 移动端综合搜索视频作者；快速评论模式，未进入达人主页",
        "搜索排名": str(candidate.rank),
        "达人名称": candidate.name,
        "抖音号": "",
        "粉丝数": "搜索卡片未提供",
        "获赞数": "",
        "关注数": "",
        "认证/身份": "",
        "简介": candidate.source_video_title,
        "主页链接": "",
        "主页截图": "",
        "评论来源作品ID": candidate.aweme_id,
        "评论来源作品标题": candidate.source_video_title,
        "评论接口状态": str(comments.get("status") or ""),
        "评论抓取时间": now,
        "评论抓取失败原因": str(comments.get("error") or ""),
        "真实评论条数": str(real_comment_count),
        "评论接口返回总数": str(comments.get("total") or real_comment_count),
        "评论原始数据JSON": compact_json(raw_comments),
        "评论原始数据范围": "so.douyin.com 评论接口首批公开评论；字段保留 cid/text/create_time/digg_count/reply_comment_total/commenter_nickname，不保存用户UID/头像/主页。",
        **comment_summary,
        **scoring,
        "AI初筛等级": level,
        "AI初筛原因": reason,
        "人工确认状态": "待确认",
        "采集时间": now,
        "原始搜索卡片": candidate.raw_card,
        "原始主页文本": "",
    }
    for index in range(1, 4):
        row[f"视频{index}封面截图"] = ""
        row[f"视频{index}获赞/热度"] = parse_card_counts(candidate.raw_card).get(f"video_visible_count_{index}", "")
        row[f"视频{index}封面URL"] = ""
        row[f"视频{index}标题/可见文案"] = candidate.source_video_title if index == 1 else ""
        row[f"评论首屏截图{index}"] = ""
    return row


async def async_main(args: argparse.Namespace) -> int:
    from playwright.async_api import async_playwright

    keywords = [item.strip() for item in (args.keywords or ",".join(DEFAULT_KEYWORDS)).split(",") if item.strip()]
    evidence_dir = Path(args.evidence_dir) / f"creator-comment-fast-batch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_aweme: set[str] = set()
    seed_count = 0
    if args.seed_rows:
        seed_payload = json.loads(Path(args.seed_rows).read_text(encoding="utf-8"))
        for row in seed_payload.get("rows") or []:
            rows.append(row)
            if row.get("达人名称"):
                seen_names.add(str(row.get("达人名称")))
            if row.get("评论来源作品ID"):
                seen_aweme.add(str(row.get("评论来源作品ID")))
        seed_count = len(rows)
    keyword_runs: list[dict[str, Any]] = []

    if not args.upload_only:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="chrome", headless=True)
            page = await browser.new_page(viewport={"width": 390, "height": 844}, user_agent=MOBILE_USER_AGENT)
            for keyword_index, keyword in enumerate(keywords, 1):
                if len(rows) >= args.target:
                    break
                keyword_dir = evidence_dir / f"keyword-{keyword_index:02d}"
                try:
                    candidates = await asyncio.wait_for(
                        collect_search_candidates(page, keyword, args.per_keyword_candidates, keyword_dir),
                        timeout=args.search_timeout_seconds,
                    )
                except Exception as exc:
                    keyword_runs.append(
                        {
                            "keyword": keyword,
                            "candidate_count": 0,
                            "accepted": 0,
                            "accepted_total": len(rows),
                            "error": repr(exc),
                        }
                    )
                    write_json(evidence_dir / "keyword-runs.partial.json", {"keyword_runs": keyword_runs})
                    continue
                accepted = 0
                for candidate in candidates:
                    if len(rows) >= args.target:
                        break
                    if not candidate.aweme_id or candidate.aweme_id in seen_aweme or candidate.name in seen_names:
                        continue
                    try:
                        comments = await asyncio.wait_for(fetch_real_comments(page, candidate.aweme_id, args.comments_per_creator), timeout=args.comment_timeout_seconds)
                    except Exception as exc:
                        comments = {"status": "comment_fetch_timeout", "comments": [], "total": 0, "error": repr(exc)}
                    row = build_row(keyword, candidate, comments)
                    if args.require_comments and int(row.get("真实评论条数") or 0) <= 0:
                        seen_names.add(candidate.name)
                        seen_aweme.add(candidate.aweme_id)
                        continue
                    rows.append(row)
                    seen_names.add(candidate.name)
                    seen_aweme.add(candidate.aweme_id)
                    accepted += 1
                    write_json(evidence_dir / "rows.partial.json", {"rows": rows})
                keyword_runs.append(
                    {
                        "keyword": keyword,
                        "candidate_count": len(candidates),
                        "accepted": accepted,
                        "accepted_total": len(rows),
                        "candidates": [asdict(candidate) for candidate in candidates],
                    }
                )
                write_json(evidence_dir / "keyword-runs.partial.json", {"keyword_runs": keyword_runs})
            await browser.close()

    write_json(evidence_dir / "rows.json", {"rows": rows})
    feishu = CreatorScreeningFeishuClient()
    table_id, reused = feishu.ensure_table()
    keys = {row["unique_key"] for row in rows}
    existing_before = feishu.readback_by_unique_keys(table_id, keys) if keys else []
    existing_keys = {(item.get("fields") or {}).get("unique_key") for item in existing_before}
    rows_to_write = [row for row in rows if row.get("unique_key") not in existing_keys]
    record_ids = feishu.create_records(table_id, rows_to_write) if rows_to_write else []
    readback = feishu.readback_by_unique_keys(table_id, keys) if keys else []
    readback_keys = {(item.get("fields") or {}).get("unique_key") for item in readback}
    rows_with_comments = sum(1 for row in rows if int(row.get("真实评论条数") or 0) > 0)
    total_real_comments = sum(int(row.get("真实评论条数") or 0) for row in rows)
    summary = {
        "status": "success" if len(rows) == args.target and rows_with_comments == args.target and not (keys - readback_keys) else "partial",
        "target": args.target,
        "collected": len(rows),
        "rows_with_real_comments": rows_with_comments,
        "total_real_comments": total_real_comments,
        "keywords": keywords,
        "keyword_runs": keyword_runs,
        "feishu": {
            "table_name": TABLE_NAME,
            "table_id": table_id,
            "table_reused": reused,
            "seed_count": seed_count,
            "existing_before_count": len(existing_before),
            "missing_rows_to_write": len(rows_to_write),
            "created_count": len(record_ids),
            "created_record_ids": record_ids,
            "readback_count": len(readback),
            "missing_unique_keys": sorted(keys - readback_keys),
        },
        "rows_path": str(evidence_dir / "rows.json"),
        "written_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(evidence_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["status"] == "success" else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast Douyin creator comment batch using search-card authors and real comment API samples.")
    parser.add_argument("--target", type=int, default=50)
    parser.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS))
    parser.add_argument("--per-keyword-candidates", type=int, default=12)
    parser.add_argument("--comments-per-creator", type=int, default=20)
    parser.add_argument("--search-timeout-seconds", type=int, default=120)
    parser.add_argument("--comment-timeout-seconds", type=int, default=20)
    parser.add_argument("--evidence-dir", default="docs/live-evidence")
    parser.add_argument("--seed-rows", default="")
    parser.add_argument("--upload-only", action="store_true")
    parser.add_argument("--allow-empty-comments", action="store_true")
    args = parser.parse_args()
    args.require_comments = not args.allow_empty_comments
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
