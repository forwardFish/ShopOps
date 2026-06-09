from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    ORDER_ACTUAL_QUANTITY_FORMULA_FIELD,
    ORDER_PRODUCT_NAME_FIELD,
    ORDER_VALID_SALES_FORMULA_FIELD,
    product_breakdown_values,
    product_field_names,
    product_rules_from_records,
)
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient, chunks


ORDER_TABLE_ENV_NAMES = {
    "tmall": "SHOPOPS_ORDER_TABLE_TMALL_ID",
    "douyin": "SHOPOPS_ORDER_TABLE_DOUYIN_ID",
    "pinduoduo": "SHOPOPS_ORDER_TABLE_PINDUODUO_ID",
    "wechat_channels": "SHOPOPS_ORDER_TABLE_WECHAT_CHANNELS_ID",
}


class ProductBreakdownBackfill:
    def __init__(self, app_token: str, env_path: Path) -> None:
        ensure_feishu_no_proxy()
        self.app_token = app_token
        self.helper = DynamicSummaryFeishuClient(app_token, env_path)

    def run(self, product_table_id: str, order_tables: dict[str, str], evidence_path: Path) -> dict[str, Any]:
        rules = product_rules_from_records(self.list_records(product_table_id))
        product_fields = product_field_names(rules)
        read_fields = [
            ORDER_PRODUCT_NAME_FIELD,
            ORDER_ACTUAL_QUANTITY_FORMULA_FIELD,
            ORDER_VALID_SALES_FORMULA_FIELD,
        ]
        result: dict[str, Any] = {
            "status": "running",
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "product_table_id": product_table_id,
            "products": [{"name": rule.name, "keywords": list(rule.keywords)} for rule in rules],
            "product_fields": product_fields,
            "tables": {},
        }
        for platform, table_id in order_tables.items():
            stats = self.backfill_table(table_id, read_fields, product_fields, rules)
            result["tables"][platform] = {"table_id": table_id, **stats}
        result["status"] = "success"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(evidence_path.resolve())
        return result

    def backfill_table(
        self,
        table_id: str,
        read_fields: list[str],
        product_fields: list[str],
        rules: list[Any],
    ) -> dict[str, Any]:
        updates: list[dict[str, Any]] = []
        scanned = 0
        matched = 0
        nonzero_rows = 0
        samples: list[dict[str, Any]] = []
        query_fields = [*read_fields, *product_fields]
        for record in self.iter_records(table_id, query_fields):
            scanned += 1
            fields = record.get("fields") or {}
            values = product_breakdown_values(
                rules,
                product_name=fields.get(ORDER_PRODUCT_NAME_FIELD),
                actual_quantity=fields.get(ORDER_ACTUAL_QUANTITY_FORMULA_FIELD),
                valid_sales=fields.get(ORDER_VALID_SALES_FORMULA_FIELD),
            )
            if any(value for value in values.values()):
                matched += 1
            if any(values.get(field, 0) for field in product_fields):
                nonzero_rows += 1
                if len(samples) < 5:
                    samples.append(
                        {
                            "record_id": record.get("record_id"),
                            ORDER_PRODUCT_NAME_FIELD: fields.get(ORDER_PRODUCT_NAME_FIELD),
                            ORDER_ACTUAL_QUANTITY_FORMULA_FIELD: fields.get(ORDER_ACTUAL_QUANTITY_FORMULA_FIELD),
                            ORDER_VALID_SALES_FORMULA_FIELD: fields.get(ORDER_VALID_SALES_FORMULA_FIELD),
                            **{field: value for field, value in values.items() if value},
                        }
                    )
            updates.append({"record_id": str(record.get("record_id")), "fields": values})
        saved = 0
        for chunk in chunks(updates, 500):
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
            saved += len(chunk)
        return {
            "scanned": scanned,
            "matched_rows": matched,
            "nonzero_rows": nonzero_rows,
            "updated": saved,
            "sample_nonzero_rows": samples,
        }

    def list_records(self, table_id: str) -> list[dict[str, Any]]:
        return list(self.iter_records(table_id))

    def iter_records(self, table_id: str, field_names: list[str] | None = None) -> Iterable[dict[str, Any]]:
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            if field_names:
                params["field_names"] = json.dumps(field_names, ensure_ascii=False)
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            yield from data.get("items") or []
            if not data.get("has_more"):
                return
            page_token = data.get("page_token")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, 7):
            try:
                return self.helper.request(method, path, payload, params)
            except RuntimeError as exc:
                last_error = exc
                text = str(exc)
                if not any(token in text for token in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504", "Gateway timeout")):
                    raise
                if attempt == 6:
                    raise
                time.sleep(min(30, attempt * 5))
        raise RuntimeError(f"Feishu API request failed after retries: {last_error}")


def default_order_tables() -> dict[str, str]:
    return {
        platform: table_id
        for platform, env_name in ORDER_TABLE_ENV_NAMES.items()
        if (table_id := os.getenv(env_name, "").strip())
    }


def main() -> int:
    _load_dotenv()
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Backfill numeric product breakdown fields from existing order formula values.")
    parser.add_argument("--app-token", default=settings.shopops_data_center_app_token or settings.feishu_app_token)
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence", default="docs/live-evidence/product-breakdown/product-breakdown-backfill.json")
    args = parser.parse_args()
    order_tables = default_order_tables()
    missing = [name for name, value in {"app-token": args.app_token, "product-table-id": args.product_table_id, "order-tables": order_tables}.items() if not value]
    if missing:
        raise RuntimeError("Missing required inputs: " + ", ".join(missing))
    result = ProductBreakdownBackfill(args.app_token, Path(args.env_path)).run(
        product_table_id=args.product_table_id,
        order_tables=order_tables,
        evidence_path=Path(args.evidence),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
