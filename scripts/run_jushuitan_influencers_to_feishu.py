from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.collectors.jushuitan_influencer_api import JushuitanInfluencerCommissionCollector
from shopops.config import load_settings
from shopops.storage.feishu_bitable import FeishuBitableStorage
from shopops.storage.local_feishu import LocalFeishuBitableStorage


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Douyin influencer commission rows from Jushuitan and upsert them into Feishu Bitable.")
    parser.add_argument("--storage", choices=["local", "feishu"], default="", help="Override STORAGE_BACKEND for this run.")
    parser.add_argument("--local-path", default="", help="Optional local Feishu double path.")
    args = parser.parse_args()

    settings = load_settings()
    storage_backend = args.storage or settings.storage_backend
    collector = JushuitanInfluencerCommissionCollector(settings)
    result = collector.fetch_today()

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
        "method": settings.jushuitan_influencer_query_method,
        "storage": storage_backend,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(main())
