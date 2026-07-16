from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.services.product_breakdown import DEFAULT_PRODUCT_CATALOG_TABLE_ID, product_rules_from_records
from scripts.reshape_formula_summary_by_product import (
    F_DATE,
    F_GRAIN,
    F_PLATFORM,
    F_PRODUCT,
    F_PRODUCT_QTY,
    F_PRODUCT_SALES,
    F_TOTAL_QTY,
    F_TOTAL_SALES,
    F_UNIQUE_KEY,
    PLATFORM_SUMMARY_GRAIN,
    PRODUCT_DETAIL_GRAIN,
    ProductSummaryReshaper,
    number_value,
    scalar,
)

FORMULA_FIELD = 20

F_SUMMARY_KEY = "\u6c47\u603bkey"
F_SUMMARY_TIME = "\u6c47\u603b\u65f6\u95f4"
F_DATA_STATUS = "\u6570\u636e\u72b6\u6001"
F_MISSING_ITEMS = "\u7f3a\u5931\u9879"
F_ORDER_COUNT = "\u8ba2\u5355\u6570"
F_GROSS_SALES = "\u9500\u552e\u989d"
F_PRODUCT_ORDER_COUNT = "\u4ea7\u54c1\u8ba2\u5355\u6570"
F_PRODUCT_GROSS_SALES = "\u4ea7\u54c1\u9500\u552e\u989d"
QTY_SUFFIX = "\u6570\u91cf"
VALID_SALES_SUFFIX = "\u6709\u6548\u9500\u552e\u989d"


def table_field_ref(table_id: str, field_id: str) -> str:
    return f"bitable::$table[{table_id}].$field[{field_id}]"


def formula_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def selected_record_fields(product_formula_names: list[str]) -> list[str]:
    return [
        F_UNIQUE_KEY,
        F_DATE,
        F_PLATFORM,
        F_PRODUCT,
        F_GRAIN,
        F_PRODUCT_QTY,
        F_PRODUCT_SALES,
        F_PRODUCT_ORDER_COUNT,
        F_PRODUCT_GROSS_SALES,
        F_TOTAL_QTY,
        F_TOTAL_SALES,
        F_ORDER_COUNT,
        F_GROSS_SALES,
        *product_formula_names,
    ]


class FormulaSummaryProductDetailFormulaRepair:
    def __init__(self, app_token: str, env_path: Path, target_table_id: str, product_table_id: str) -> None:
        self.app_token = app_token
        self.target_table_id = target_table_id
        self.product_table_id = product_table_id
        self.client = ProductSummaryReshaper(app_token, env_path)

    def run(self, *, evidence_dir: Path, dry_run: bool, poll_attempts: int) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fields = self.client.field_index(self.target_table_id)
        product_records = self.client.list_records(self.product_table_id)
        product_rules = product_rules_from_records(product_records)
        if not product_rules:
            raise RuntimeError(f"Product table {self.product_table_id} has no usable products")

        product_formula_names = []
        for rule in product_rules:
            product_formula_names.extend([f"{rule.name}{QTY_SUFFIX}", f"{rule.name}{VALID_SALES_SUFFIX}"])

        updates = self.build_formula_updates(fields, product_formula_names)
        before_audit = self.audit_product_detail_records(fields, product_formula_names)

        if not dry_run:
            for update in updates:
                self.client.request(
                    "PUT",
                    f"/bitable/v1/apps/{self.app_token}/tables/{self.target_table_id}/fields/{update['field_id']}",
                    update["payload"],
                )
                time.sleep(0.2)

        after_audit = before_audit
        if not dry_run:
            for attempt in range(1, poll_attempts + 1):
                time.sleep(min(20, attempt * 3))
                after_audit = self.audit_product_detail_records(fields, product_formula_names)
                if after_audit["status"] == "PASS":
                    break

        result = {
            "status": "success" if dry_run or after_audit["status"] == "PASS" else "failed",
            "mode": "dry_run" if dry_run else "live_write",
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "app_token": self.app_token,
            "target_table_id": self.target_table_id,
            "product_table_id": self.product_table_id,
            "products": [rule.name for rule in product_rules],
            "formula_updates_count": len(updates),
            "formula_updates": [
                {
                    "field_name": update["field_name"],
                    "field_id": update["field_id"],
                    "detail_behavior": update["detail_behavior"],
                }
                for update in updates
            ],
            "before_audit": before_audit,
            "after_audit": after_audit,
        }
        output = evidence_dir / (
            "product-detail-formula-repair-dry-run.json" if dry_run else "product-detail-formula-repair-result.json"
        )
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(output.resolve())
        return result

    def build_formula_updates(self, fields: dict[str, dict[str, Any]], product_formula_names: list[str]) -> list[dict[str, Any]]:
        required = [F_GRAIN, F_PRODUCT, F_PRODUCT_QTY, F_PRODUCT_SALES]
        missing = [name for name in required if name not in fields]
        if missing:
            raise RuntimeError("Target table is missing required product-detail fields: " + ", ".join(missing))

        grain_ref = table_field_ref(self.target_table_id, str(fields[F_GRAIN]["field_id"]))
        product_ref = table_field_ref(self.target_table_id, str(fields[F_PRODUCT]["field_id"]))
        product_qty_ref = table_field_ref(self.target_table_id, str(fields[F_PRODUCT_QTY]["field_id"]))
        product_sales_ref = table_field_ref(self.target_table_id, str(fields[F_PRODUCT_SALES]["field_id"]))
        product_order_ref = (
            table_field_ref(self.target_table_id, str(fields[F_PRODUCT_ORDER_COUNT]["field_id"]))
            if F_PRODUCT_ORDER_COUNT in fields
            else None
        )
        product_gross_sales_ref = (
            table_field_ref(self.target_table_id, str(fields[F_PRODUCT_GROSS_SALES]["field_id"]))
            if F_PRODUCT_GROSS_SALES in fields
            else None
        )

        updates: list[dict[str, Any]] = []
        product_formula_set = set(product_formula_names)
        for field_name, field in fields.items():
            if int(field.get("type") or 0) != FORMULA_FIELD:
                continue
            property_data = field.get("property") or {}
            expression = str(property_data.get("formula_expression") or "")
            formatter = str(property_data.get("formatter") or "")
            if not expression:
                continue
            if expression.startswith(f"IF({grain_ref}={formula_string(PRODUCT_DETAIL_GRAIN)},"):
                continue

            detail_expression: str | None = None
            detail_behavior: str | None = None
            product_name = self.product_name_for_formula(field_name, product_formula_set)
            if product_name and field_name.endswith(QTY_SUFFIX):
                detail_expression = f"IF({product_ref}={formula_string(product_name)},{product_qty_ref},0)"
                detail_behavior = f"matching {product_name} rows use {F_PRODUCT_QTY}; other product rows use 0"
            elif product_name and field_name.endswith(VALID_SALES_SUFFIX):
                detail_expression = f"IF({product_ref}={formula_string(product_name)},{product_sales_ref},0)"
                detail_behavior = f"matching {product_name} rows use {F_PRODUCT_SALES}; other product rows use 0"
            elif field_name == F_TOTAL_QTY:
                detail_expression = product_qty_ref
                detail_behavior = f"product detail rows use {F_PRODUCT_QTY}"
            elif field_name == F_TOTAL_SALES:
                detail_expression = product_sales_ref
                detail_behavior = f"product detail rows use {F_PRODUCT_SALES}"
            elif field_name == F_ORDER_COUNT and product_order_ref:
                detail_expression = product_order_ref
                detail_behavior = f"product detail rows use {F_PRODUCT_ORDER_COUNT}"
            elif field_name == F_GROSS_SALES and product_gross_sales_ref:
                detail_expression = product_gross_sales_ref
                detail_behavior = f"product detail rows use {F_PRODUCT_GROSS_SALES}"
            elif field_name == F_DATA_STATUS:
                detail_expression = formula_string(PRODUCT_DETAIL_GRAIN)
                detail_behavior = "product detail rows are labelled as product detail"
            elif field_name == F_MISSING_ITEMS:
                detail_expression = formula_string("")
                detail_behavior = "product detail rows do not inherit platform missing-item status"
            elif field_name in {F_SUMMARY_KEY, F_SUMMARY_TIME}:
                continue
            elif formatter in {"0", "0.00"}:
                detail_expression = "0"
                detail_behavior = "product detail rows use 0 because this platform metric is not product-allocated"

            if detail_expression is None:
                continue

            new_expression = f"IF({grain_ref}={formula_string(PRODUCT_DETAIL_GRAIN)},{detail_expression},{expression})"
            if new_expression == expression:
                continue
            payload = {
                "field_name": field_name,
                "type": FORMULA_FIELD,
                "property": {"formatter": formatter, "formula_expression": new_expression},
            }
            updates.append(
                {
                    "field_name": field_name,
                    "field_id": str(field["field_id"]),
                    "detail_behavior": detail_behavior,
                    "payload": payload,
                }
            )
        return updates

    @staticmethod
    def product_name_for_formula(field_name: str, product_formula_set: set[str]) -> str | None:
        if field_name not in product_formula_set:
            return None
        if field_name.endswith(VALID_SALES_SUFFIX):
            return field_name[: -len(VALID_SALES_SUFFIX)]
        if field_name.endswith(QTY_SUFFIX):
            return field_name[: -len(QTY_SUFFIX)]
        return None

    def audit_product_detail_records(self, fields: dict[str, dict[str, Any]], product_formula_names: list[str]) -> dict[str, Any]:
        available_fields = set(fields)
        field_names = [name for name in selected_record_fields(product_formula_names) if name in available_fields]
        records = self.list_records(field_names)
        product_detail_rows = [
            record
            for record in records
            if scalar((record.get("fields") or {}).get(F_GRAIN)) == PRODUCT_DETAIL_GRAIN
        ]

        mismatches: list[dict[str, Any]] = []
        duplicate_platform_formula_examples: list[dict[str, Any]] = []
        for record in product_detail_rows:
            row_fields = record.get("fields") or {}
            product = scalar(row_fields.get(F_PRODUCT))
            product_qty = number_value(row_fields.get(F_PRODUCT_QTY)) or 0
            product_sales = number_value(row_fields.get(F_PRODUCT_SALES)) or 0

            total_qty = number_value(row_fields.get(F_TOTAL_QTY))
            total_sales = number_value(row_fields.get(F_TOTAL_SALES))
            if total_qty is not None and abs(total_qty - product_qty) > 0.01:
                mismatches.append(self.row_mismatch(record, F_TOTAL_QTY, product_qty, total_qty))
            if total_sales is not None and abs(total_sales - product_sales) > 0.01:
                mismatches.append(self.row_mismatch(record, F_TOTAL_SALES, product_sales, total_sales))

            for formula_name in product_formula_names:
                actual = number_value(row_fields.get(formula_name)) or 0
                product_name = self.product_name_for_formula(formula_name, set(product_formula_names))
                if not product_name:
                    continue
                if formula_name.endswith(QTY_SUFFIX):
                    expected = product_qty if product == product_name else 0
                else:
                    expected = product_sales if product == product_name else 0
                if abs(actual - expected) > 0.01:
                    mismatches.append(self.row_mismatch(record, formula_name, expected, actual))
                    if product != product_name and abs(actual) > 0.01:
                        duplicate_platform_formula_examples.append(
                            self.row_mismatch(record, formula_name, expected, actual)
                        )
                if len(mismatches) >= 100:
                    break
            if len(mismatches) >= 100:
                break

        return {
            "status": "PASS" if not mismatches else "FAIL",
            "total_records_seen": len(records),
            "product_detail_rows_seen": len(product_detail_rows),
            "mismatch_count": len(mismatches),
            "mismatch_examples": mismatches[:20],
            "duplicate_platform_formula_examples": duplicate_platform_formula_examples[:20],
        }

    def row_mismatch(self, record: dict[str, Any], field_name: str, expected: float, actual: float | None) -> dict[str, Any]:
        row_fields = record.get("fields") or {}
        return {
            "record_id": record.get("record_id"),
            "unique_key": scalar(row_fields.get(F_UNIQUE_KEY)),
            "date": scalar(row_fields.get(F_DATE)),
            "platform": scalar(row_fields.get(F_PLATFORM)),
            "product": scalar(row_fields.get(F_PRODUCT)),
            "field_name": field_name,
            "expected": round(expected, 2),
            "actual": None if actual is None else round(actual, 2),
        }

    def list_records(self, field_names: list[str]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {
                "page_size": 500,
                "field_names": json.dumps(field_names, ensure_ascii=False),
            }
            if page_token:
                params["page_token"] = page_token
            data = self.client.request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.target_table_id}/records",
                params=params,
            )
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Guard formula summary fields so product-detail rows do not repeat platform totals.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--target-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID") or "tblepMIg19Ov1kSw")
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/product-summary-reshape")
    parser.add_argument("--poll-attempts", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = FormulaSummaryProductDetailFormulaRepair(
        args.app_token,
        Path(args.env_path),
        args.target_table_id,
        args.product_table_id,
    ).run(evidence_dir=Path(args.evidence_dir), dry_run=args.dry_run, poll_attempts=args.poll_attempts)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
