from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from data_robot.common import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_EVIDENCE_ROOT,
    parse_common_args,
    print_json,
    run_platform,
    summarize_platform_results,
    write_json,
)


PLATFORMS = ("pinduoduo", "wechat_channels", "douyin", "tmall")


async def run(args: argparse.Namespace) -> dict:
    selected = args.platform or list(PLATFORMS)
    results = []
    for platform in selected:
        results.append(await run_platform(platform, args))
    date_token = args.date_token or datetime.now().strftime("%m%d")
    batch_token = date_token if args.flat_date_folder else hourly_batch_token(date_token, args.batch_hour)
    summary = {
        "status": summarize_platform_results(results),
        "date_token": date_token,
        "batch_token": batch_token,
        "platforms": selected,
        "results": results,
    }
    evidence_root = Path(args.evidence_root)
    evidence = evidence_root / f"run-all-{evidence_token(batch_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({"evidence": str(evidence), **summary})
    return summary


def main() -> int:
    parser = parse_common_args("Collect all ShopOps platform exports.")
    parser.add_argument("--platform", action="append", choices=PLATFORMS, help="Only run selected platform; repeatable.")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT), help="Evidence output root.")
    parser.set_defaults(archive_root=str(DEFAULT_ARCHIVE_ROOT))
    args = parser.parse_args()
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    evidence_token,
    hourly_batch_token,
