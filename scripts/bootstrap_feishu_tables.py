from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.storage.feishu_bootstrap import bootstrap_platform_tables, merge_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Create ShopOps Feishu Bitable base/tables through Feishu OpenAPI.")
    parser.add_argument("--platform", default="千牛淘宝", help="Platform suffix used in table names.")
    parser.add_argument("--base-name", default="ShopOps 数据采集", help="New base name when FEISHU_APP_TOKEN is empty.")
    parser.add_argument("--folder-token", default="", help="Optional Feishu cloud folder token for a new base.")
    parser.add_argument("--owner-open-id", default="", help="Optional Feishu open_id to transfer the Bitable owner to.")
    parser.add_argument("--write-env", default=".env", help="Env file to merge FEISHU_APP_TOKEN and table ids into.")
    parser.add_argument("--dry-run", action="store_true", help="Print table specs without calling Feishu.")
    args = parser.parse_args()

    settings = load_settings()
    if args.dry_run:
        from shopops.storage.feishu_bootstrap import platform_table_specs

        print(json.dumps({"platform": args.platform, "tables": [spec.__dict__ for spec in platform_table_specs(args.platform)]}, ensure_ascii=False, indent=2))
        return 0

    result = bootstrap_platform_tables(
        settings=settings,
        platform_name=args.platform,
        base_name=args.base_name,
        folder_token=args.folder_token,
        owner_open_id=args.owner_open_id,
        env_path=args.write_env,
    )
    safe_result = {
        "app_token": result["app_token"],
        "created_base": bool(result["created_base"]),
        "ownership_transferred": bool(result.get("ownership_transfer")),
        "platform": result["platform"],
        "tables": result["tables"],
        "env_file": args.write_env,
    }
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
