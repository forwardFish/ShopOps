from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.storage.feishu_bootstrap import (
    bootstrap_douyin_influencer_table,
    douyin_influencer_commission_table_spec,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or reuse the Douyin influencer commission table in an existing Feishu Bitable.")
    parser.add_argument("--app-token", default="", help="Existing Feishu Bitable app token. Overrides FEISHU_APP_TOKEN for this run.")
    parser.add_argument("--write-env", default=".env", help="Env file to merge the new table id into.")
    parser.add_argument("--dry-run", action="store_true", help="Print table spec without calling Feishu.")
    args = parser.parse_args()

    if args.dry_run:
        spec = douyin_influencer_commission_table_spec()
        print(json.dumps(spec.__dict__, ensure_ascii=False, indent=2))
        return 0

    settings = load_settings()
    if args.app_token:
        settings = settings.__class__(**{**settings.__dict__, "feishu_app_token": args.app_token})
    result = bootstrap_douyin_influencer_table(settings=settings, env_path=args.write_env)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
