from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.product_breakdown import DEFAULT_PRODUCT_CATALOG_TABLE_ID, product_rules_from_records
from scripts.bootstrap_formula_dynamic_summary import FormulaSummaryBootstrap, actual_sold_quantity_expr


ORDER_TABLES = {
    "tmall": "tbl0gBiMcAKMCcwI",
    "douyin": "tblTbbFkEepZAGru",
    "pinduoduo": "tblFI9ZNPzrjR6Jm",
    "wechat_channels": "tblFlMuPnVEn8qkw",
}
TARGET_FIELD = "公式_实际卖出数量"
MOJIBAKE_TARGET_FIELDS = {"??_??????", "鍏紡_瀹為檯鍗栧嚭鏁伴噺"}


def update(evidence: Path, cleanup_mojibake: bool) -> dict[str, Any]:
    _load_dotenv()
    settings = load_settings()
    app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
    bootstrap = FormulaSummaryBootstrap(app_token, Path(".env"))
    product_rules = product_rules_from_records(bootstrap.helper.list_records(DEFAULT_PRODUCT_CATALOG_TABLE_ID))
    result: dict[str, Any] = {"status": "success", "updated": {}, "deleted_mojibake_fields": {}}
    for platform, table_id in ORDER_TABLES.items():
        if cleanup_mojibake:
            result["deleted_mojibake_fields"][platform] = delete_mojibake_fields(bootstrap, table_id)
        fields = bootstrap.field_index(table_id)
        expression = actual_sold_quantity_expr(fields, product_rules)
        bootstrap.ensure_formula_field(table_id, TARGET_FIELD, expression, formatter="0")
        refreshed = bootstrap.field_index(table_id)
        current = refreshed.get(TARGET_FIELD) or {}
        result["updated"][platform] = {
            "table_id": table_id,
            "field_id": current.get("field_id"),
            "field": TARGET_FIELD,
            "expression": expression,
            "type": current.get("type"),
        }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def delete_mojibake_fields(bootstrap: FormulaSummaryBootstrap, table_id: str) -> list[dict[str, str]]:
    deleted: list[dict[str, str]] = []
    for name, field in bootstrap.field_index(table_id).items():
        if name not in MOJIBAKE_TARGET_FIELDS:
            continue
        field_id = field.get("field_id")
        if not field_id:
            continue
        bootstrap.helper.request("DELETE", f"/bitable/v1/apps/{bootstrap.app_token}/tables/{table_id}/fields/{field_id}")
        deleted.append({"field": name, "field_id": str(field_id)})
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Update order table actual quantity formula with the unified effective-sales quantity logic.")
    parser.add_argument("--evidence", default="docs/live-evidence/product-breakdown/order-actual-quantity-formula-update.json")
    parser.add_argument("--cleanup-mojibake", action="store_true")
    args = parser.parse_args()
    print(json.dumps(update(Path(args.evidence), args.cleanup_mojibake), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
