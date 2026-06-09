from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.collectors.doudian_alliance_api import DoudianAllianceOrderCollector, parse_order_ids
from shopops.config import load_settings
from shopops.storage.feishu_bitable import FeishuBitableStorage
from shopops.storage.local_feishu import LocalFeishuBitableStorage


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Doudian Selected Alliance creator commission details and upsert them into Feishu Bitable.")
    parser.add_argument("--order-ids", default="", help="Comma-separated Doudian order ids. Overrides DOUDIAN_ALLIANCE_ORDER_IDS.")
    parser.add_argument("--storage", choices=["local", "feishu"], default="", help="Override STORAGE_BACKEND for this run.")
    parser.add_argument("--local-path", default="", help="Optional local Feishu double path.")
    args = parser.parse_args()

    settings = load_settings()
    storage_backend = args.storage or settings.storage_backend
    order_ids = parse_order_ids(args.order_ids) if args.order_ids else None
    collector = DoudianAllianceOrderCollector(settings, order_ids=order_ids)
    result = collector.fetch()

    saved_count = 0
    if result.success and result.rows:
        if storage_backend == "feishu":
            storage = FeishuBitableStorage(settings)
        else:
            storage = LocalFeishuBitableStorage(settings, path=args.local_path or None)
        saved_count = storage.save_douyin_influencer_commission(result.rows)

    summary = {
        "success": result.success,
        "source": result.source,
        "shop_id": result.shop_id,
        "row_count": result.row_count,
        "saved_count": saved_count,
        "total_estimated_commission": result.total_estimated_commission,
        "total_settled_commission": result.total_settled_commission,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "method": DoudianAllianceOrderCollector.method,
        "endpoint": DoudianAllianceOrderCollector.path,
        "storage": storage_backend,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(main())
