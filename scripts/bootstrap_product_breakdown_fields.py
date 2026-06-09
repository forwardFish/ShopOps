from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    ProductRule,
    product_field_names,
    product_rules_from_records,
    summary_product_formula_fields,
    total_product_formula_fields,
)
from shopops.storage.feishu_bootstrap import FeishuOpenApiClient, NUMBER_FIELD
from scripts.bootstrap_formula_dynamic_summary import FORMULA_FIELD
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient


ORDER_TABLE_ENV_NAMES = (
    "SHOPOPS_ORDER_TABLE_TMALL_ID",
    "SHOPOPS_ORDER_TABLE_DOUYIN_ID",
    "SHOPOPS_ORDER_TABLE_PINDUODUO_ID",
    "SHOPOPS_ORDER_TABLE_WECHAT_CHANNELS_ID",
)


class ProductBreakdownBootstrap:
    def __init__(self, app_token: str, env_path: Path) -> None:
        ensure_feishu_no_proxy()
        settings = load_settings()
        self.app_token = app_token
        self.env_path = env_path
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.helper = DynamicSummaryFeishuClient(app_token, env_path)

    def run(
        self,
        *,
        product_table_id: str,
        order_table_ids: list[str],
        summary_table_id: str,
        total_summary_table_id: str,
        evidence_path: Path,
    ) -> dict[str, Any]:
        table_names = self.table_names_by_id([*order_table_ids, summary_table_id, total_summary_table_id])
        rules = self.product_rules(product_table_id)
        order_product_fields = product_field_names(rules)
        summary_formula_fields = summary_product_formula_fields(
            [table_names[table_id] for table_id in order_table_ids],
            rules,
        )
        total_formula_fields = total_product_formula_fields(table_names[summary_table_id], rules)

        order_updates: dict[str, list[str]] = {}
        order_field_actions: dict[str, dict[str, str]] = {}
        for table_id in order_table_ids:
            actions = self.ensure_number_fields(table_id, order_product_fields)
            order_updates[table_id] = order_product_fields
            order_field_actions[table_id] = actions

        self.ensure_formula_fields(summary_table_id, summary_formula_fields)
        self.ensure_formula_fields(total_summary_table_id, total_formula_fields)

        result = {
            "status": "success",
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "product_table_id": product_table_id,
            "products": [{"name": rule.name, "keywords": list(rule.keywords)} for rule in rules],
            "product_fields": product_field_names(rules),
            "order_tables": {
                table_id: {
                    "name": table_names[table_id],
                    "fields": order_updates[table_id],
                    "field_actions": order_field_actions[table_id],
                }
                for table_id in order_table_ids
            },
            "summary_table": {
                "table_id": summary_table_id,
                "name": table_names[summary_table_id],
                "fields": list(summary_formula_fields),
            },
            "total_summary_table": {
                "table_id": total_summary_table_id,
                "name": table_names[total_summary_table_id],
                "fields": list(total_formula_fields),
            },
        }
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(evidence_path.resolve())
        return result

    def product_rules(self, product_table_id: str) -> list[ProductRule]:
        rules = product_rules_from_records(self.helper.list_records(product_table_id))
        if not rules:
            raise RuntimeError(f"Product catalog table {product_table_id} has no usable 商品名称/搜索关键词 records")
        return rules

    def table_names_by_id(self, table_ids: list[str]) -> dict[str, str]:
        tables = self.client.list_tables(self.app_token)
        result = {str(item.get("table_id")): str(item.get("name")) for item in tables if item.get("table_id") and item.get("name")}
        missing = [table_id for table_id in table_ids if table_id not in result]
        if missing:
            raise RuntimeError("Cannot find Feishu table names for ids: " + ", ".join(missing))
        return result

    def field_index(self, table_id: str) -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items") or []:
                if item.get("field_name"):
                    fields[str(item["field_name"])] = item
            if not data.get("has_more"):
                return fields
            page_token = data.get("page_token")

    def ensure_formula_field(self, table_id: str, name: str, expression: str, formatter: str) -> None:
        existing = self.field_index(table_id)
        self.ensure_formula_field_with_index(table_id, existing, name, expression, formatter)

    def ensure_formula_fields(self, table_id: str, fields: dict[str, dict[str, str]]) -> None:
        existing = self.field_index(table_id)
        for name, config in fields.items():
            self.ensure_formula_field_with_index(table_id, existing, name, config["expression"], config["formatter"])

    def ensure_number_fields(self, table_id: str, field_names: list[str]) -> dict[str, str]:
        existing = self.field_index(table_id)
        return {
            name: self.ensure_number_field_with_index(table_id, existing, name)
            for name in field_names
        }

    def ensure_number_field_with_index(self, table_id: str, existing: dict[str, dict[str, Any]], name: str) -> str:
        current = existing.get(name)
        if not current:
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", {"field_name": name, "type": NUMBER_FIELD})
            existing[name] = {"field_name": name, "type": NUMBER_FIELD}
            return "created"
        if int(current.get("type") or 0) == NUMBER_FIELD:
            return "reused"
        field_id = current.get("field_id")
        self.request("DELETE", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields/{field_id}")
        self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", {"field_name": name, "type": NUMBER_FIELD})
        existing[name] = {"field_name": name, "type": NUMBER_FIELD}
        return "replaced"

    def ensure_formula_field_with_index(
        self,
        table_id: str,
        existing: dict[str, dict[str, Any]],
        name: str,
        expression: str,
        formatter: str,
    ) -> None:
        payload = {
            "field_name": name,
            "type": FORMULA_FIELD,
            "property": {"formatter": formatter, "formula_expression": expression},
        }
        current = existing.get(name)
        if not current:
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", payload)
            existing[name] = {"field_name": name, "type": FORMULA_FIELD}
            return
        if int(current.get("type") or 0) != FORMULA_FIELD:
            raise RuntimeError(f"Field {name} exists in table {table_id}, but it is not a formula field")
        current_property = current.get("property") or {}
        if (
            current_property.get("formula_expression") == expression
            and str(current_property.get("formatter") or "") == str(formatter or "")
        ):
            return
        self.request("PUT", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields/{current['field_id']}", payload)

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


def default_order_table_ids() -> list[str]:
    return [os.getenv(name, "").strip() for name in ORDER_TABLE_ENV_NAMES if os.getenv(name, "").strip()]


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Create/update product breakdown formula fields from the product catalog table.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--order-table-id", action="append", default=None, help="Repeat to override the four order table ids from .env.")
    parser.add_argument("--summary-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID") or "tblepMIg19Ov1kSw")
    parser.add_argument("--total-summary-table-id", default=os.getenv("SHOPOPS_FORMULA_TOTAL_SUMMARY_TABLE_ID") or "tblufREIgBB4VBAg")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence", default="docs/live-evidence/product-breakdown/product-breakdown-fields.json")
    args = parser.parse_args()

    order_table_ids = args.order_table_id or default_order_table_ids()
    required = {
        "app-token": args.app_token,
        "product-table-id": args.product_table_id,
        "order-table-id": order_table_ids,
        "summary-table-id": args.summary_table_id,
        "total-summary-table-id": args.total_summary_table_id,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing required inputs: " + ", ".join(missing))
    result = ProductBreakdownBootstrap(args.app_token, Path(args.env_path)).run(
        product_table_id=args.product_table_id,
        order_table_ids=order_table_ids,
        summary_table_id=args.summary_table_id,
        total_summary_table_id=args.total_summary_table_id,
        evidence_path=Path(args.evidence),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
