from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    product_rules_from_records,
)
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


DATA_NOT_READY_CODE = 1254607


class FeishuReader:
    def __init__(self) -> None:
        _load_dotenv()
        settings = load_settings()
        self.app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
        if not self.app_token:
            raise RuntimeError("Missing FEISHU_APP_TOKEN or SHOPOPS_DATA_CENTER_APP_TOKEN")
        self.auth = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(8):
            response = self.session.request(
                method,
                f"{FEISHU_BASE_URL}{path}",
                headers=self.auth.headers(),
                json=payload,
                params=params,
                timeout=60,
            )
            body = response.json()
            if response.status_code < 400 and body.get("code") == 0:
                return body.get("data") or {}
            if body.get("code") == DATA_NOT_READY_CODE and attempt < 7:
                time.sleep(2 + attempt)
                continue
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        raise RuntimeError(f"Feishu API {method} {path} failed unexpectedly")

    def field_names(self, table_id: str) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items") or []:
                name = item.get("field_name")
                if name:
                    names.add(str(name))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def records(self, table_id: str, field_names: list[str] | None = None) -> list[dict[str, Any]]:
        if field_names:
            existing = self.field_names(table_id)
            field_names = [name for name in field_names if name in existing]
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            if field_names:
                params["field_names"] = json.dumps(field_names, ensure_ascii=False)
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")


def scalar(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") if isinstance(item, dict) else item) for item in value).strip()
    return "" if value is None else str(value).strip()


def number(value: Any) -> float:
    if isinstance(value, list) and value:
        value = value[0].get("text") if isinstance(value[0], dict) else value[0]
    try:
        text = str(value).replace(",", "").strip()
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def inspect(table_id: str, product_table_id: str, evidence: Path) -> dict[str, Any]:
    reader = FeishuReader()
    rules = product_rules_from_records(reader.records(product_table_id))
    product_fields = [field for rule in rules for field in (rule.quantity_field, rule.valid_sales_field)]
    context_fields = ["unique_key", "商品名称"]
    records = reader.records(table_id, [*context_fields, *product_fields])

    quantity_without_sales: dict[str, int] = {rule.name: 0 for rule in rules}
    sales_without_quantity: dict[str, int] = {rule.name: 0 for rule in rules}
    samples: list[dict[str, Any]] = []

    for record in records:
        fields = record.get("fields") or {}
        for rule in rules:
            quantity = number(fields.get(rule.quantity_field))
            valid_sales = number(fields.get(rule.valid_sales_field))
            quantity_problem = quantity > 0 and valid_sales <= 0
            sales_problem = valid_sales > 0 and quantity <= 0
            if quantity_problem:
                quantity_without_sales[rule.name] += 1
            if sales_problem:
                sales_without_quantity[rule.name] += 1
            if (quantity_problem or sales_problem) and len(samples) < 30:
                samples.append(
                    {
                        "record_id": record.get("record_id"),
                        "unique_key": scalar(fields.get("unique_key")),
                        "商品名称": scalar(fields.get("商品名称")),
                        "product": rule.name,
                        "quantity_field": rule.quantity_field,
                        "quantity": quantity,
                        "valid_sales_field": rule.valid_sales_field,
                        "valid_sales": valid_sales,
                        "problem": "quantity_without_sales" if quantity_problem else "sales_without_quantity",
                    }
                )

    result = {
        "status": "success",
        "table_id": table_id,
        "product_table_id": product_table_id,
        "record_count": len(records),
        "quantity_without_sales_total": sum(quantity_without_sales.values()),
        "sales_without_quantity_total": sum(sales_without_quantity.values()),
        "quantity_without_sales": quantity_without_sales,
        "sales_without_quantity": sales_without_quantity,
        "samples": samples,
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect product quantity fields gated by corresponding valid sales.")
    parser.add_argument("--table-id", required=True)
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.table_id, args.product_table_id, Path(args.evidence)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
