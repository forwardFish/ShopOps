from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.storage.feishu_bootstrap import FeishuOpenApiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Transfer ownership of the configured ShopOps Feishu Bitable.")
    parser.add_argument("--app-token", default="", help="Bitable app_token. Defaults to FEISHU_APP_TOKEN from .env.")
    parser.add_argument("--owner-open-id", required=True, help="Target Feishu open_id, usually starting with ou_.")
    parser.add_argument("--old-owner-perm", default="full_access", choices=["view", "edit", "full_access"])
    parser.add_argument("--stay-put", action="store_true", help="Keep the document in the old owner's folder when applicable.")
    args = parser.parse_args()

    settings = load_settings()
    app_token = args.app_token or settings.feishu_app_token
    client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
    result = client.transfer_bitable_owner(
        app_token=app_token,
        owner_open_id=args.owner_open_id,
        old_owner_perm=args.old_owner_perm,
        stay_put=args.stay_put,
    )
    print(
        json.dumps(
            {
                "app_token": app_token,
                "owner_open_id": args.owner_open_id,
                "old_owner_perm": args.old_owner_perm,
                "stay_put": args.stay_put,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
