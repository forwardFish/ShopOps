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
from shopops.services.product_breakdown import DEFAULT_PRODUCT_CATALOG_TABLE_ID, product_field_names, product_rules_from_records
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


BASE_FIELDS = ["商品名称", "数量", "公式_实际卖出数量", "公式_有效销售额"]
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

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
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

    def field_names(self, table_id: str) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items") or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")


def number(value: Any) -> float:
    if isinstance(value, list) and value:
        value = value[0].get("text") if isinstance(value[0], dict) else value[0]
    try:
        text = str(value).replace(",", "").strip()
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def verify(table_id: str, product_table_id: str, evidence: Path) -> dict[str, Any]:
    reader = FeishuReader()
    rules = product_rules_from_records(reader.records(product_table_id))
    fields = product_field_names(rules)
    records = reader.records(table_id, [*BASE_FIELDS, *fields])
    totals = {field: 0.0 for field in fields}
    nonzero_rows = {field: 0 for field in fields}
    samples: list[dict[str, Any]] = []
    for record in records:
        values = record.get("fields") or {}
        row_nonzero = False
        for field in fields:
            value = number(values.get(field))
            totals[field] += value
            if value:
                nonzero_rows[field] += 1
                row_nonzero = True
        if row_nonzero and len(samples) < 10:
            samples.append({"record_id": record.get("record_id"), **{name: values.get(name) for name in [*BASE_FIELDS, *fields] if number(values.get(name)) or name == "商品名称"}})
    result = {
        "status": "success",
        "table_id": table_id,
        "product_table_id": product_table_id,
        "record_count": len(records),
        "product_fields": fields,
        "nonzero_rows": nonzero_rows,
        "totals": {field: round(value, 2) for field, value in totals.items()},
        "sample_nonzero_rows": samples,
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify product breakdown numeric fields in an order table.")
    parser.add_argument("--table-id", required=True)
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--evidence", default="docs/live-evidence/product-breakdown/product-breakdown-verify.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.table_id, args.product_table_id, Path(args.evidence)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
