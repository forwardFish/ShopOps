from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.services.data_center_demo import feishu_base_url
from shopops.services.product_breakdown import DEFAULT_PRODUCT_CATALOG_TABLE_ID, ProductRule, product_rules_from_records
from shopops.storage.feishu_bootstrap import NUMBER_FIELD, TEXT_FIELD
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient, chunks


TOTAL_PRODUCT = "全产品总计"
PLATFORM_SUMMARY_GRAIN = "平台汇总"
PRODUCT_DETAIL_GRAIN = "产品明细"

F_UNIQUE_KEY = "unique_key"
F_DATE = "统计日期"
F_PLATFORM = "平台"
F_SHOP = "店铺名称"
F_ITEM_NAME = "商品名称"
F_PRODUCT = "产品"
F_PRODUCT_QTY = "产品数量"
F_PRODUCT_SALES = "产品有效销售额"
F_GRAIN = "数据粒度"
F_TOTAL_QTY = "实际卖出数量"
F_TOTAL_SALES = "有效销售额"

REQUIRED_TARGET_FIELDS = {
    F_PRODUCT: TEXT_FIELD,
    F_PRODUCT_QTY: NUMBER_FIELD,
    F_PRODUCT_SALES: NUMBER_FIELD,
    F_GRAIN: TEXT_FIELD,
}


class ProductSummaryReshaper:
    def __init__(self, app_token: str, env_path: Path) -> None:
        self.app_token = app_token
        self.helper = DynamicSummaryFeishuClient(app_token, env_path)

    def run(
        self,
        *,
        backup_table_id: str,
        target_table_id: str,
        product_table_id: str,
        evidence_dir: Path,
        include_zero_products: bool,
        dry_run: bool,
    ) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        backup_records = self.list_records(backup_table_id)
        target_before_records = self.list_records(target_table_id)
        product_records = self.list_records(product_table_id)
        product_rules = product_rules_from_records(product_records)
        if not product_rules:
            raise RuntimeError(f"Product table {product_table_id} has no usable products")

        target_fields_before = self.field_index(target_table_id)
        missing_source_fields = missing_product_source_fields(backup_records, product_rules)
        if missing_source_fields:
            raise RuntimeError("Backup table is missing product metric fields: " + ", ".join(missing_source_fields))

        summary_updates, detail_rows = build_target_rows(
            backup_records,
            product_rules,
            include_zero_products=include_zero_products,
        )
        expected_rows = [*summary_updates, *detail_rows]
        before_parity = compare_backup_target_existing_rows(backup_records, target_before_records)

        field_actions: dict[str, str] = {}
        saved_count = 0
        verification: dict[str, Any]
        if not dry_run:
            field_actions = self.ensure_target_fields(target_table_id)
            saved_count = self.upsert_rows(target_table_id, expected_rows)
            time.sleep(3)
            target_after_records = self.list_records(target_table_id)
            verification = verify_target(backup_records, target_after_records, product_rules, include_zero_products)
        else:
            target_after_records = target_before_records
            verification = {
                "status": "DRY_RUN_SKIPPED",
                "reason": "No live writes were made, so post-write target verification was intentionally skipped.",
            }
        target_fields_after = self.field_index(target_table_id)

        result = {
            "status": "success"
            if before_parity["status"] == "PASS" and (dry_run or verification["status"] == "PASS")
            else "failed",
            "mode": "dry_run" if dry_run else "live_write",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "backup_table_id": backup_table_id,
            "target_table_id": target_table_id,
            "product_table_id": product_table_id,
            "products": [
                {
                    "name": rule.name,
                    "keywords": list(rule.keywords),
                    "quantity_field": rule.quantity_field,
                    "valid_sales_field": rule.valid_sales_field,
                }
                for rule in product_rules
            ],
            "target_fields_before": sorted(target_fields_before),
            "target_fields_after": sorted(target_fields_after),
            "field_actions": field_actions,
            "source_record_count": len(backup_records),
            "target_record_count_before": len(target_before_records),
            "target_record_count_after": len(target_after_records),
            "expected_platform_summary_rows": len(summary_updates),
            "expected_product_detail_rows": len(detail_rows),
            "expected_upsert_rows": len(expected_rows),
            "saved_count": saved_count,
            "include_zero_products": include_zero_products,
            "before_parity": before_parity,
            "verification": verification,
        }
        output = evidence_dir / ("product-summary-reshape-dry-run.json" if dry_run else "product-summary-reshape-result.json")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(output.resolve())
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

    def ensure_target_fields(self, table_id: str) -> dict[str, str]:
        existing = self.field_index(table_id)
        actions: dict[str, str] = {}
        for name, field_type in REQUIRED_TARGET_FIELDS.items():
            current = existing.get(name)
            if current:
                if int(current.get("type") or 0) != field_type:
                    raise RuntimeError(f"Target field {name} exists but has type {current.get('type')}, expected {field_type}")
                actions[name] = "reused"
                continue
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                {"field_name": name, "type": field_type},
            )
            actions[name] = "created"
        return actions

    def upsert_rows(self, table_id: str, rows: list[dict[str, Any]]) -> int:
        index = records_by_key(self.list_records(table_id))
        to_create: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        for row in rows:
            key = str(row[F_UNIQUE_KEY])
            current = index.get(key)
            if not current:
                to_create.append({"fields": row})
                continue
            current_fields = current.get("fields") or {}
            if row_matches(current_fields, row):
                continue
            to_update.append({"record_id": str(current["record_id"]), "fields": row})

        saved = 0
        for chunk in chunks(to_create, 500):
            if chunk:
                self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create", {"records": chunk})
                saved += len(chunk)
        for chunk in chunks(to_update, 500):
            if chunk:
                self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
                saved += len(chunk)
        return saved

    def list_records(self, table_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                return records
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
            except Exception as exc:
                last_error = exc
                text = str(exc)
                retryable = isinstance(
                    exc,
                    (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ReadTimeout,
                        requests.exceptions.Timeout,
                    ),
                ) or any(token in text for token in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504", "Gateway timeout", "Data not ready"))
                if not retryable or attempt == 6:
                    raise
                time.sleep(min(30, attempt * 5))
        raise RuntimeError(f"Feishu API request failed after retries: {last_error}")


def build_target_rows(
    backup_records: list[dict[str, Any]],
    product_rules: list[ProductRule],
    *,
    include_zero_products: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    for record in backup_records:
        fields = record.get("fields") or {}
        date_text = scalar(fields.get(F_DATE))
        platform = scalar(fields.get(F_PLATFORM))
        if not date_text or not platform:
            continue
        unique_key = scalar(fields.get(F_UNIQUE_KEY)) or f"{date_text}-{platform}"
        summary_rows.append(
            {
                F_UNIQUE_KEY: unique_key,
                F_PRODUCT: TOTAL_PRODUCT,
                F_PRODUCT_QTY: number_value(fields.get(F_TOTAL_QTY)) or 0,
                F_PRODUCT_SALES: number_value(fields.get(F_TOTAL_SALES)) or 0,
                F_GRAIN: PLATFORM_SUMMARY_GRAIN,
            }
        )
        shop = scalar(fields.get(F_SHOP))
        if platform == "全平台总计":
            continue
        for rule in product_rules:
            quantity = number_value(fields.get(rule.quantity_field)) or 0
            sales = number_value(fields.get(rule.valid_sales_field)) or 0
            if not include_zero_products and quantity == 0 and sales == 0:
                continue
            detail_rows.append(
                {
                    F_UNIQUE_KEY: f"{date_text}-{platform}-{rule.name}",
                    F_DATE: date_text,
                    F_PLATFORM: platform,
                    F_SHOP: shop,
                    F_ITEM_NAME: rule.name,
                    F_PRODUCT: rule.name,
                    F_PRODUCT_QTY: quantity,
                    F_PRODUCT_SALES: sales,
                    F_GRAIN: PRODUCT_DETAIL_GRAIN,
                }
            )
    return summary_rows, detail_rows


def missing_product_source_fields(records: list[dict[str, Any]], product_rules: list[ProductRule]) -> list[str]:
    seen: set[str] = set()
    for record in records:
        seen.update((record.get("fields") or {}).keys())
    required: list[str] = []
    for rule in product_rules:
        required.extend([rule.quantity_field, rule.valid_sales_field])
    return [field for field in required if field not in seen]


def verify_target(
    backup_records: list[dict[str, Any]],
    target_records: list[dict[str, Any]],
    product_rules: list[ProductRule],
    include_zero_products: bool,
) -> dict[str, Any]:
    summary_expected, detail_expected = build_target_rows(
        backup_records,
        product_rules,
        include_zero_products=include_zero_products,
    )
    target = records_by_key(target_records)
    summary_check = compare_expected_rows(summary_expected, target, [F_PRODUCT, F_PRODUCT_QTY, F_PRODUCT_SALES, F_GRAIN])
    detail_check = compare_expected_rows(
        detail_expected,
        target,
        [F_DATE, F_PLATFORM, F_ITEM_NAME, F_PRODUCT, F_PRODUCT_QTY, F_PRODUCT_SALES, F_GRAIN],
    )
    aggregate_check = compare_product_detail_aggregates(backup_records, target, product_rules, include_zero_products)
    status = "PASS" if all(item["status"] == "PASS" for item in (summary_check, detail_check, aggregate_check)) else "FAIL"
    return {
        "status": status,
        "summary_row_check": summary_check,
        "product_detail_row_check": detail_check,
        "product_detail_aggregate_check": aggregate_check,
        "target_product_detail_rows_seen": sum(1 for record in target_records if scalar((record.get("fields") or {}).get(F_GRAIN)) == PRODUCT_DETAIL_GRAIN),
        "target_platform_summary_rows_seen": sum(1 for record in target_records if scalar((record.get("fields") or {}).get(F_GRAIN)) == PLATFORM_SUMMARY_GRAIN),
    }


def compare_expected_rows(
    expected_rows: list[dict[str, Any]],
    target_by_key: dict[str, dict[str, Any]],
    fields: list[str],
) -> dict[str, Any]:
    missing: list[str] = []
    mismatches: list[dict[str, Any]] = []
    for row in expected_rows:
        key = str(row[F_UNIQUE_KEY])
        current = target_by_key.get(key)
        if not current:
            missing.append(key)
            continue
        current_fields = current.get("fields") or {}
        row_mismatches = {}
        for field in fields:
            if not values_equal(current_fields.get(field), row.get(field)):
                row_mismatches[field] = {"expected": row.get(field), "actual": scalar(current_fields.get(field))}
        if row_mismatches:
            mismatches.append({"unique_key": key, "fields": row_mismatches})
    return {
        "status": "PASS" if not missing and not mismatches else "FAIL",
        "expected_count": len(expected_rows),
        "missing_count": len(missing),
        "mismatch_count": len(mismatches),
        "missing_examples": missing[:20],
        "mismatch_examples": mismatches[:20],
    }


def compare_product_detail_aggregates(
    backup_records: list[dict[str, Any]],
    target_by_key: dict[str, dict[str, Any]],
    product_rules: list[ProductRule],
    include_zero_products: bool,
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for record in backup_records:
        fields = record.get("fields") or {}
        date_text = scalar(fields.get(F_DATE))
        platform = scalar(fields.get(F_PLATFORM))
        if not date_text or not platform:
            continue
        if platform == "全平台总计":
            continue
        expected_qty = 0.0
        expected_sales = 0.0
        actual_qty = 0.0
        actual_sales = 0.0
        for rule in product_rules:
            source_qty = number_value(fields.get(rule.quantity_field)) or 0
            source_sales = number_value(fields.get(rule.valid_sales_field)) or 0
            if not include_zero_products and source_qty == 0 and source_sales == 0:
                continue
            expected_qty += source_qty
            expected_sales += source_sales
            target = target_by_key.get(f"{date_text}-{platform}-{rule.name}")
            if target:
                target_fields = target.get("fields") or {}
                actual_qty += number_value(target_fields.get(F_PRODUCT_QTY)) or 0
                actual_sales += number_value(target_fields.get(F_PRODUCT_SALES)) or 0
        checked += 1
        if abs(expected_qty - actual_qty) > 0.000001 or abs(expected_sales - actual_sales) > 0.01:
            mismatches.append(
                {
                    "source_unique_key": scalar(fields.get(F_UNIQUE_KEY)) or f"{date_text}-{platform}",
                    "expected_product_quantity_sum": round(expected_qty, 6),
                    "actual_product_quantity_sum": round(actual_qty, 6),
                    "expected_product_sales_sum": round(expected_sales, 2),
                    "actual_product_sales_sum": round(actual_sales, 2),
                }
            )
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "checked_source_rows": checked,
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches[:20],
    }


def compare_backup_target_existing_rows(
    backup_records: list[dict[str, Any]],
    target_records: list[dict[str, Any]],
) -> dict[str, Any]:
    target = records_by_key(target_records)
    fields_to_compare = [
        F_DATE,
        F_PLATFORM,
        "订单数",
        F_TOTAL_QTY,
        "销售额",
        "退款金额",
        F_TOTAL_SALES,
        "投流消耗",
        "达人佣金",
        "已知费用后利润",
    ]
    missing: list[str] = []
    mismatches: list[dict[str, Any]] = []
    for record in backup_records:
        backup_fields = record.get("fields") or {}
        key = scalar(backup_fields.get(F_UNIQUE_KEY))
        if not key:
            continue
        current = target.get(key)
        if not current:
            missing.append(key)
            continue
        current_fields = current.get("fields") or {}
        row_mismatches = {}
        for field in fields_to_compare:
            if not values_equal(backup_fields.get(field), current_fields.get(field)):
                row_mismatches[field] = {"backup": scalar(backup_fields.get(field)), "target": scalar(current_fields.get(field))}
        if row_mismatches:
            mismatches.append({"unique_key": key, "fields": row_mismatches})
    return {
        "status": "PASS" if not missing and not mismatches else "FAIL",
        "checked_count": len(backup_records),
        "missing_count": len(missing),
        "mismatch_count": len(mismatches),
        "missing_examples": missing[:20],
        "mismatch_examples": mismatches[:20],
    }


def records_by_key(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        fields = record.get("fields") or {}
        key = scalar(fields.get(F_UNIQUE_KEY))
        if key:
            result[key] = {"record_id": str(record.get("record_id")), "fields": fields}
    return result


def row_matches(current: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(values_equal(current.get(field), value) for field, value in expected.items())


def values_equal(left: Any, right: Any) -> bool:
    left_number = number_value(left)
    right_number = number_value(right)
    if left_number is not None or right_number is not None:
        return left_number is not None and right_number is not None and abs(left_number - right_number) <= 0.01
    return scalar(left) == scalar(right)


def scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(value).strip()


def number_value(value: Any) -> float | None:
    text = scalar(value).replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text), 6)
    except ValueError:
        return None


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Reshape the formula summary table to date-platform-product rows from a backup wide table.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--backup-table-id", default="tblAJdiVXWbKtGFt")
    parser.add_argument("--target-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID") or "tblepMIg19Ov1kSw")
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/product-summary-reshape")
    parser.add_argument("--skip-zero-products", action="store_true", help="Only create product rows where quantity or effective sales is non-zero.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = ProductSummaryReshaper(args.app_token, Path(args.env_path)).run(
        backup_table_id=args.backup_table_id,
        target_table_id=args.target_table_id,
        product_table_id=args.product_table_id,
        evidence_dir=Path(args.evidence_dir),
        include_zero_products=not args.skip_zero_products,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
