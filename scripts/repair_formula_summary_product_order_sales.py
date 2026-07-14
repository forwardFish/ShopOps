from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    LEGACY_UNCLASSIFIED_PRODUCT_NAMES,
    best_product_rule_from_order_fields,
    extract_order_product_code,
    ORDER_RAW_FIELD,
    ORDER_PRODUCT_CODE_FIELD,
    UNCLASSIFIED_PRODUCT_NAME,
    product_rules_from_records,
)
from shopops.storage.feishu_bootstrap import NUMBER_FIELD
from scripts.reshape_formula_summary_by_product import (
    F_DATE,
    F_GRAIN,
    F_ITEM_NAME,
    F_PLATFORM,
    F_PRODUCT,
    F_UNIQUE_KEY,
    PRODUCT_DETAIL_GRAIN,
    ProductSummaryReshaper,
    chunks,
    number_value,
    scalar,
)

FORMULA_FIELD = 20
TOTAL_PLATFORM = "全平台总计"

F_ORDER_COUNT = "\u8ba2\u5355\u6570"
F_ACTUAL_QUANTITY = "\u5b9e\u9645\u5356\u51fa\u6570\u91cf"
F_GROSS_SALES = "\u9500\u552e\u989d"
F_VALID_SALES = "\u6709\u6548\u9500\u552e\u989d"
F_REFUND_AMOUNT = "\u9000\u6b3e\u91d1\u989d"
F_PRODUCT_ORDER_COUNT = "\u4ea7\u54c1\u8ba2\u5355\u6570"
F_PRODUCT_QUANTITY = "\u4ea7\u54c1\u6570\u91cf"
F_PRODUCT_GROSS_SALES = "\u4ea7\u54c1\u9500\u552e\u989d"
F_PRODUCT_REFUND_AMOUNT = "\u4ea7\u54c1\u9000\u6b3e\u91d1\u989d"
F_PRODUCT_VALID_SALES = "\u4ea7\u54c1\u6709\u6548\u9500\u552e\u989d"
F_DATE_TEXT = "\u7edf\u8ba1\u65e5\u671f\u6587\u672c"

ORDER_DATE_FIELD = "\u516c\u5f0f_\u7edf\u8ba1\u65e5\u671f"
ORDER_PLATFORM_FIELD = "\u5e73\u53f0"
ORDER_PRODUCT_NAME_FIELD = "\u5546\u54c1\u540d\u79f0"
ORDER_GROSS_SALES_FIELD = "\u516c\u5f0f_\u9500\u552e\u989d"
ORDER_REFUND_AMOUNT_FIELD = "\u516c\u5f0f_\u9000\u6b3e\u91d1\u989d"
ORDER_ACTUAL_QUANTITY_FIELD = "\u516c\u5f0f_\u5b9e\u9645\u5356\u51fa\u6570\u91cf"
ORDER_VALID_SALES_FIELD = "\u516c\u5f0f_\u6709\u6548\u9500\u552e\u989d"


def canonical_product_name(value: Any) -> str:
    product = scalar(value)
    if product in LEGACY_UNCLASSIFIED_PRODUCT_NAMES:
        return UNCLASSIFIED_PRODUCT_NAME
    return product


def table_field_ref(table_id: str, field_id: str) -> str:
    return f"bitable::$table[{table_id}].$field[{field_id}]"


def formula_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def source_date_filter(dates: set[str]) -> str:
    clauses = [f'CurrentValue.[{ORDER_DATE_FIELD}]={formula_string(value)}' for value in sorted(dates)]
    return clauses[0] if len(clauses) == 1 else "(" + "||".join(clauses) + ")"


def summary_date_filter(dates: set[str]) -> str:
    clauses = [
        f'CurrentValue.[汇总key]={formula_string(f"{value}-{platform}")}'
        for value in sorted(dates)
        for platform in ("天猫", "抖音", "拼多多", "视频号", TOTAL_PLATFORM)
    ]
    return clauses[0] if len(clauses) == 1 else "(" + "||".join(clauses) + ")"


def split_top_level_args(value: str) -> list[str]:
    args: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(value):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(value[start:index])
            start = index + 1
    args.append(value[start:])
    return args


def unwrap_product_detail_guard(expression: str, grain_ref: str) -> str:
    if not expression.startswith("IF(") or not expression.endswith(")"):
        return expression
    inner = expression[3:-1]
    args = split_top_level_args(inner)
    condition = f"{grain_ref}={formula_string(PRODUCT_DETAIL_GRAIN)}"
    if len(args) == 3 and args[0] == condition:
        return args[2]
    return expression


def summary_date_timestamp(date_text: str) -> int:
    parsed = datetime.strptime(date_text, "%Y-%m-%d")
    return int(parsed.replace(tzinfo=timezone.utc).timestamp() * 1000)


class ProductOrderSalesRepair:
    def __init__(self, app_token: str, env_path: Path, target_table_id: str, product_table_id: str) -> None:
        self.app_token = app_token
        self.target_table_id = target_table_id
        self.product_table_id = product_table_id
        self.client = ProductSummaryReshaper(app_token, env_path)

    def run(
        self,
        *,
        evidence_dir: Path,
        dry_run: bool,
        poll_attempts: int,
        impact_dates: set[str] | None = None,
    ) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        fields = self.client.field_index(self.target_table_id)
        field_actions = self.ensure_target_number_fields(fields, dry_run=dry_run)
        if field_actions and not dry_run:
            fields = self.client.field_index(self.target_table_id)

        rules = product_rules_from_records(self.client.list_records(self.product_table_id))
        if not rules:
            raise RuntimeError(f"Product table {self.product_table_id} has no usable products")

        source_table_ids = self.discover_order_source_tables(fields)
        normalized_impact_dates = {value for value in impact_dates or set() if value}
        aggregates, source_stats = self.aggregate_product_order_sales(
            source_table_ids,
            rules,
            impact_dates=normalized_impact_dates or None,
        )
        requested_target_fields = [
                F_UNIQUE_KEY,
                F_DATE,
                F_DATE_TEXT,
                F_PLATFORM,
                F_ITEM_NAME,
                F_PRODUCT,
                F_GRAIN,
                F_PRODUCT_ORDER_COUNT,
                F_PRODUCT_QUANTITY,
                F_PRODUCT_GROSS_SALES,
                F_PRODUCT_REFUND_AMOUNT,
                F_PRODUCT_VALID_SALES,
                F_ORDER_COUNT,
                F_ACTUAL_QUANTITY,
                F_GROSS_SALES,
                F_REFUND_AMOUNT,
                F_VALID_SALES,
            ]
        existing_target_fields = [name for name in requested_target_fields if name in fields]
        target_rows = self.list_records(
            self.target_table_id,
            existing_target_fields,
            summary_date_filter(normalized_impact_dates) if normalized_impact_dates else None,
        )
        known_product_names = {rule.name for rule in rules}
        known_product_names.add(UNCLASSIFIED_PRODUCT_NAME)
        row_updates, row_creates, before_audit = self.build_row_updates(
            target_rows,
            aggregates,
            known_product_names,
        )

        formula_updates = []
        formula_fields_ready = all(
            name in fields
            for name in (F_GRAIN, F_PRODUCT_ORDER_COUNT, F_PRODUCT_GROSS_SALES, F_PRODUCT_REFUND_AMOUNT, F_ORDER_COUNT, F_GROSS_SALES, F_REFUND_AMOUNT)
        )
        if formula_fields_ready:
            formula_updates = self.build_formula_updates(fields)
        elif not dry_run:
            raise RuntimeError("Product order/sales fields were not available after creation")
        if not dry_run:
            for chunk in chunks(row_creates, 500):
                if chunk:
                    self.client.request(
                        "POST",
                        f"/bitable/v1/apps/{self.app_token}/tables/{self.target_table_id}/records/batch_create",
                        {"records": chunk},
                    )
            for chunk in chunks(row_updates, 500):
                if chunk:
                    self.client.request(
                        "POST",
                        f"/bitable/v1/apps/{self.app_token}/tables/{self.target_table_id}/records/batch_update",
                        {"records": chunk},
                    )
            for update in formula_updates:
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
                current_rows = self.list_records(
                    self.target_table_id,
                    requested_target_fields,
                    summary_date_filter(normalized_impact_dates) if normalized_impact_dates else None,
                )
                after_audit = self.audit_rows(current_rows, aggregates)
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
            "source_table_ids": source_table_ids,
            "impact_dates": sorted(normalized_impact_dates),
            "source_stats": source_stats,
            "field_actions": field_actions,
            "row_updates_count": len(row_updates),
            "row_creates_count": len(row_creates),
            "formula_updates": [
                {"field_name": update["field_name"], "field_id": update["field_id"]}
                for update in formula_updates
            ],
            "before_audit": before_audit,
            "after_audit": after_audit,
        }
        output = evidence_dir / (
            "product-order-sales-repair-dry-run.json" if dry_run else "product-order-sales-repair-result.json"
        )
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(output.resolve())
        return result

    def ensure_target_number_fields(self, fields: dict[str, dict[str, Any]], *, dry_run: bool) -> dict[str, str]:
        actions: dict[str, str] = {}
        for name in (F_PRODUCT_ORDER_COUNT, F_PRODUCT_QUANTITY, F_PRODUCT_GROSS_SALES, F_PRODUCT_REFUND_AMOUNT, F_PRODUCT_VALID_SALES):
            current = fields.get(name)
            if current:
                if int(current.get("type") or 0) != NUMBER_FIELD:
                    raise RuntimeError(f"Target field {name} exists but is not a number field")
                actions[name] = "reused"
                continue
            actions[name] = "created" if not dry_run else "would_create"
            if not dry_run:
                self.client.request(
                    "POST",
                    f"/bitable/v1/apps/{self.app_token}/tables/{self.target_table_id}/fields",
                    {"field_name": name, "type": NUMBER_FIELD},
                )
        return actions

    def discover_order_source_tables(self, fields: dict[str, dict[str, Any]]) -> list[str]:
        order_field = fields.get(F_ORDER_COUNT)
        grain_field = fields.get(F_GRAIN)
        if not order_field or not grain_field:
            raise RuntimeError(f"Target table is missing {F_ORDER_COUNT} or {F_GRAIN}")
        grain_ref = table_field_ref(self.target_table_id, str(grain_field["field_id"]))
        expression = str((order_field.get("property") or {}).get("formula_expression") or "")
        base_expression = unwrap_product_detail_guard(expression, grain_ref)
        source_table_ids: list[str] = []
        for table_id in re.findall(r"bitable::\$table\[([^\]]+)\]", base_expression):
            if table_id != self.target_table_id and table_id not in source_table_ids:
                source_table_ids.append(table_id)
        if not source_table_ids:
            raise RuntimeError("Could not discover order source tables from order-count formula")
        return source_table_ids

    def aggregate_product_order_sales(
        self,
        source_table_ids: list[str],
        rules: list[Any],
        *,
        impact_dates: set[str] | None = None,
    ) -> tuple[dict[tuple[str, str, str], dict[str, Any]], list[dict[str, Any]]]:
        aggregates: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
            lambda: {"order_keys": set(), "quantity": 0.0, "sales": 0.0, "refund": 0.0, "valid_sales": 0.0, "source_rows": 0}
        )
        source_stats: list[dict[str, Any]] = []
        for table_id in source_table_ids:
            table_fields = self.client.field_index(table_id)
            required = [
                F_UNIQUE_KEY,
                ORDER_DATE_FIELD,
                ORDER_PLATFORM_FIELD,
                ORDER_PRODUCT_NAME_FIELD,
                ORDER_GROSS_SALES_FIELD,
                ORDER_REFUND_AMOUNT_FIELD,
                ORDER_ACTUAL_QUANTITY_FIELD,
                ORDER_VALID_SALES_FIELD,
            ]
            missing = [name for name in required if name not in table_fields]
            if missing:
                raise RuntimeError(f"Order source table {table_id} is missing fields: {', '.join(missing)}")
            optional = [
                name
                for name in (
                    ORDER_PRODUCT_CODE_FIELD,
                    ORDER_RAW_FIELD,
                    *(field for rule in rules for field in (rule.quantity_field, rule.valid_sales_field)),
                )
                if name in table_fields and name not in required
            ]
            records = self.list_records(
                table_id,
                [*required, *optional],
                source_date_filter(impact_dates) if impact_dates else None,
            )
            matched_rows = 0
            for record in records:
                fields = record.get("fields") or {}
                date_text = scalar(fields.get(ORDER_DATE_FIELD))
                platform = scalar(fields.get(ORDER_PLATFORM_FIELD))
                product_name = scalar(fields.get(ORDER_PRODUCT_NAME_FIELD))
                product_code = extract_order_product_code(fields)
                rule = best_product_rule_from_order_fields(
                    rules,
                    fields,
                    product_name=product_name,
                    product_code=product_code,
                )
                if not date_text or not platform:
                    continue
                product_name_for_summary = rule.name if rule else UNCLASSIFIED_PRODUCT_NAME
                key = (date_text, platform, product_name_for_summary)
                order_key = scalar(fields.get(F_UNIQUE_KEY)) or str(record.get("record_id") or "")
                if order_key:
                    aggregates[key]["order_keys"].add(order_key)
                aggregates[key]["sales"] += number_value(fields.get(ORDER_GROSS_SALES_FIELD)) or 0
                aggregates[key]["refund"] += number_value(fields.get(ORDER_REFUND_AMOUNT_FIELD)) or 0
                aggregates[key]["source_rows"] += 1
                aggregates[key]["quantity"] += number_value(fields.get(ORDER_ACTUAL_QUANTITY_FIELD)) or 0
                aggregates[key]["valid_sales"] += number_value(fields.get(ORDER_VALID_SALES_FIELD)) or 0
                matched_rows += 1
            source_stats.append({"table_id": table_id, "records": len(records), "matched_rows": matched_rows})
        self.add_total_platform_aggregates(aggregates)
        return aggregates, source_stats

    @staticmethod
    def add_total_platform_aggregates(aggregates: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        platform_items = [
            (key, value)
            for key, value in aggregates.items()
            if key[1] != TOTAL_PLATFORM
        ]
        for key in [key for key in aggregates if key[1] == TOTAL_PLATFORM]:
            del aggregates[key]
        for (date_text, _platform, product), source in platform_items:
            total = aggregates.setdefault(
                (date_text, TOTAL_PLATFORM, product),
                {"order_keys": set(), "quantity": 0.0, "sales": 0.0, "refund": 0.0, "valid_sales": 0.0, "source_rows": 0},
            )
            total["order_keys"].update(source["order_keys"])
            total["quantity"] += source["quantity"]
            total["sales"] += source["sales"]
            total["refund"] += source["refund"]
            total["valid_sales"] += source["valid_sales"]
            total["source_rows"] += source["source_rows"]

    def build_row_updates(
        self,
        target_rows: list[dict[str, Any]],
        aggregates: dict[tuple[str, str, str], dict[str, Any]],
        known_product_names: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        creates: list[dict[str, Any]] = []
        existing_keys: set[tuple[str, str, str]] = set()
        for record in target_rows:
            fields = record.get("fields") or {}
            key = self.row_aggregate_key(fields)
            is_product_detail = scalar(fields.get(F_GRAIN)) == PRODUCT_DETAIL_GRAIN
            if not key:
                continue
            # A legacy row can have a product-shaped unique key while its product
            # and grain fields are blank. Normalize known zero-value product rows
            # too, otherwise their formulas fall through to the platform branch.
            if not is_product_detail and key not in aggregates and key[2] not in known_product_names:
                continue
            if key:
                existing_keys.add(key)
            expected_orders, expected_quantity, expected_sales, expected_refund, expected_valid_sales = self.expected_values(fields, aggregates)
            current_orders = number_value(fields.get(F_PRODUCT_ORDER_COUNT)) or 0
            current_quantity = number_value(fields.get(F_PRODUCT_QUANTITY)) or 0
            current_sales = number_value(fields.get(F_PRODUCT_GROSS_SALES)) or 0
            current_refund = number_value(fields.get(F_PRODUCT_REFUND_AMOUNT)) or 0
            current_valid_sales = number_value(fields.get(F_PRODUCT_VALID_SALES)) or 0
            expected_unique_key = f"{key[0]}-{key[1]}-{key[2]}" if key else ""
            current_product = scalar(fields.get(F_PRODUCT))
            current_unique_key = scalar(fields.get(F_UNIQUE_KEY))
            identity_mismatch = bool(key) and (
                current_product != key[2]
                or current_unique_key != expected_unique_key
                or scalar(fields.get(F_GRAIN)) != PRODUCT_DETAIL_GRAIN
            )
            if (
                identity_mismatch
                or abs(current_orders - expected_orders) > 0.01
                or abs(current_quantity - expected_quantity) > 0.01
                or abs(current_sales - expected_sales) > 0.01
                or abs(current_refund - expected_refund) > 0.01
                or abs(current_valid_sales - expected_valid_sales) > 0.01
            ):
                update_fields = {
                    F_PRODUCT_ORDER_COUNT: expected_orders,
                    F_PRODUCT_QUANTITY: round(expected_quantity, 6),
                    F_PRODUCT_GROSS_SALES: round(expected_sales, 2),
                    F_PRODUCT_REFUND_AMOUNT: round(expected_refund, 2),
                    F_PRODUCT_VALID_SALES: round(expected_valid_sales, 2),
                }
                if identity_mismatch:
                    update_fields.update(
                        {
                            F_UNIQUE_KEY: expected_unique_key,
                            F_ITEM_NAME: key[2],
                            F_PRODUCT: key[2],
                            F_GRAIN: PRODUCT_DETAIL_GRAIN,
                        }
                    )
                updates.append(
                    {
                        "record_id": str(record.get("record_id")),
                        "fields": update_fields,
                    }
                )
        for key, aggregate in sorted(aggregates.items()):
            if key in existing_keys:
                continue
            date_text, platform, product = key
            if not date_text or not platform or not product:
                continue
            creates.append(
                {
                    "fields": {
                        F_UNIQUE_KEY: f"{date_text}-{platform}-{product}",
                        F_DATE: summary_date_timestamp(date_text),
                        F_DATE_TEXT: date_text,
                        F_PLATFORM: platform,
                        F_ITEM_NAME: product,
                        F_PRODUCT: product,
                        F_GRAIN: PRODUCT_DETAIL_GRAIN,
                        F_PRODUCT_ORDER_COUNT: int(aggregate["source_rows"]),
                        F_PRODUCT_QUANTITY: round(float(aggregate["quantity"]), 6),
                        F_PRODUCT_GROSS_SALES: round(float(aggregate["sales"]), 2),
                        F_PRODUCT_REFUND_AMOUNT: round(float(aggregate["refund"]), 2),
                        F_PRODUCT_VALID_SALES: round(float(aggregate["valid_sales"]), 2),
                    }
                }
            )
        return updates, creates, self.audit_rows(target_rows, aggregates)

    def row_aggregate_key(self, fields: dict[str, Any]) -> tuple[str, str, str] | None:
        unique_key = str(scalar(fields.get(F_UNIQUE_KEY)) or "")
        date_text = (
            unique_key[:10]
            if len(unique_key) >= 10 and unique_key[4:5] == "-" and unique_key[7:8] == "-"
            else ""
        )
        if not date_text:
            date_text = scalar(fields.get(F_DATE_TEXT)) or scalar(fields.get(F_DATE))
        platform = scalar(fields.get(F_PLATFORM))
        product = canonical_product_name(fields.get(F_PRODUCT))
        if not platform or not product:
            parts = unique_key.split("-", 3)
            if len(parts) == 4:
                platform = platform or parts[3].split("-", 1)[0]
                product = product or canonical_product_name(parts[3].split("-", 1)[1] if "-" in parts[3] else "")
        if not date_text or not platform or not product:
            return None
        return (date_text, platform, product)

    def expected_values(
        self,
        fields: dict[str, Any],
        aggregates: dict[tuple[str, str, str], dict[str, Any]],
    ) -> tuple[int, float, float, float, float]:
        key = self.row_aggregate_key(fields)
        if not key:
            return 0, 0.0, 0.0, 0.0, 0.0
        aggregate = aggregates.get(key)
        if not aggregate:
            return 0, 0.0, 0.0, 0.0, 0.0
        return (
            int(aggregate["source_rows"]),
            round(float(aggregate["quantity"]), 6),
            round(float(aggregate["sales"]), 2),
            round(float(aggregate["refund"]), 2),
            round(float(aggregate["valid_sales"]), 2),
        )

    def build_formula_updates(self, fields: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        required = [F_GRAIN, F_PRODUCT_ORDER_COUNT, F_PRODUCT_GROSS_SALES, F_PRODUCT_REFUND_AMOUNT, F_ORDER_COUNT, F_GROSS_SALES, F_REFUND_AMOUNT]
        missing = [name for name in required if name not in fields]
        if missing:
            raise RuntimeError("Target table is missing required fields after ensure step: " + ", ".join(missing))
        grain_ref = table_field_ref(self.target_table_id, str(fields[F_GRAIN]["field_id"]))
        order_ref = table_field_ref(self.target_table_id, str(fields[F_PRODUCT_ORDER_COUNT]["field_id"]))
        gross_sales_ref = table_field_ref(self.target_table_id, str(fields[F_PRODUCT_GROSS_SALES]["field_id"]))
        refund_ref = table_field_ref(self.target_table_id, str(fields[F_PRODUCT_REFUND_AMOUNT]["field_id"]))
        updates: list[dict[str, Any]] = []
        for field_name, detail_ref in ((F_ORDER_COUNT, order_ref), (F_GROSS_SALES, gross_sales_ref), (F_REFUND_AMOUNT, refund_ref)):
            current = fields[field_name]
            property_data = current.get("property") or {}
            formatter = str(property_data.get("formatter") or "")
            expression = str(property_data.get("formula_expression") or "")
            base_expression = unwrap_product_detail_guard(expression, grain_ref)
            new_expression = f"IF({grain_ref}={formula_string(PRODUCT_DETAIL_GRAIN)},{detail_ref},{base_expression})"
            if new_expression == expression:
                continue
            updates.append(
                {
                    "field_name": field_name,
                    "field_id": str(current["field_id"]),
                    "payload": {
                        "field_name": field_name,
                        "type": FORMULA_FIELD,
                        "property": {"formatter": formatter, "formula_expression": new_expression},
                    },
                }
            )
        return updates

    def audit_rows(
        self,
        target_rows: list[dict[str, Any]],
        aggregates: dict[tuple[str, str, str], dict[str, Any]],
    ) -> dict[str, Any]:
        product_rows = 0
        mismatch_count = 0
        mismatch_examples: list[dict[str, Any]] = []
        samples: list[dict[str, Any]] = []
        sample_keys = {
            "2026-06-25-\u6296\u97f3-\u6d17\u9762\u5976",
            "2026-06-25-\u6296\u97f3-\u914d\u4ef6",
            "2026-06-25-\u6296\u97f3-\u55b7\u58f6",
        }
        for record in target_rows:
            fields = record.get("fields") or {}
            if scalar(fields.get(F_GRAIN)) != PRODUCT_DETAIL_GRAIN:
                continue
            product_rows += 1
            expected_orders, expected_quantity, expected_sales, expected_refund, expected_valid_sales = self.expected_values(fields, aggregates)
            product_orders = number_value(fields.get(F_PRODUCT_ORDER_COUNT)) or 0
            product_quantity = number_value(fields.get(F_PRODUCT_QUANTITY)) or 0
            product_sales = number_value(fields.get(F_PRODUCT_GROSS_SALES)) or 0
            product_refund = number_value(fields.get(F_PRODUCT_REFUND_AMOUNT)) or 0
            product_valid_sales = number_value(fields.get(F_PRODUCT_VALID_SALES)) or 0
            formula_orders = number_value(fields.get(F_ORDER_COUNT)) or 0
            formula_quantity = number_value(fields.get(F_ACTUAL_QUANTITY)) or 0
            formula_sales = number_value(fields.get(F_GROSS_SALES)) or 0
            formula_refund = number_value(fields.get(F_REFUND_AMOUNT)) or 0
            formula_valid_sales = number_value(fields.get(F_VALID_SALES)) or 0
            row = {
                "record_id": record.get("record_id"),
                "unique_key": scalar(fields.get(F_UNIQUE_KEY)),
                "expected_orders": expected_orders,
                "product_orders": product_orders,
                "formula_orders": formula_orders,
                "expected_quantity": round(expected_quantity, 6),
                "product_quantity": round(product_quantity, 6),
                "formula_quantity": round(formula_quantity, 6),
                "expected_sales": round(expected_sales, 2),
                "product_sales": round(product_sales, 2),
                "formula_sales": round(formula_sales, 2),
                "expected_refund": round(expected_refund, 2),
                "product_refund": round(product_refund, 2),
                "formula_refund": round(formula_refund, 2),
                "expected_valid_sales": round(expected_valid_sales, 2),
                "product_valid_sales": round(product_valid_sales, 2),
                "formula_valid_sales": round(formula_valid_sales, 2),
            }
            if row["unique_key"] in sample_keys:
                samples.append(row)
            if (
                abs(product_orders - expected_orders) > 0.01
                or abs(product_quantity - expected_quantity) > 0.01
                or abs(product_sales - expected_sales) > 0.01
                or abs(product_refund - expected_refund) > 0.01
                or abs(product_valid_sales - expected_valid_sales) > 0.01
                or abs(formula_orders - expected_orders) > 0.01
                or abs(formula_quantity - expected_quantity) > 0.01
                or abs(formula_sales - expected_sales) > 0.01
                or abs(formula_refund - expected_refund) > 0.01
                or abs(formula_valid_sales - expected_valid_sales) > 0.01
            ):
                mismatch_count += 1
                if len(mismatch_examples) < 20:
                    mismatch_examples.append(row)
        return {
            "status": "PASS" if not mismatch_count else "FAIL",
            "product_detail_rows_seen": product_rows,
            "mismatch_count": mismatch_count,
            "mismatch_examples": mismatch_examples,
            "sample_rows": samples,
        }

    def list_records(
        self,
        table_id: str,
        field_names: list[str],
        filter_formula: str | None = None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {
                "page_size": 500,
                "field_names": json.dumps(field_names, ensure_ascii=False),
            }
            if page_token:
                params["page_token"] = page_token
            if filter_formula:
                params["filter"] = filter_formula
            data = self.client.request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
                params=params,
            )
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Backfill product order count, quantity, gross sales, and valid sales into formula summary product rows.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN") or "KhbEbksLbauw0fssL6EcKAnlnOe")
    parser.add_argument("--target-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID") or "tblepMIg19Ov1kSw")
    parser.add_argument("--product-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID") or DEFAULT_PRODUCT_CATALOG_TABLE_ID)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/product-summary-reshape")
    parser.add_argument("--poll-attempts", type=int, default=8)
    parser.add_argument("--impact-date", action="append", default=[], help="Limit source, target, and audit reads to YYYY-MM-DD; repeatable.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = ProductOrderSalesRepair(
        args.app_token,
        Path(args.env_path),
        args.target_table_id,
        args.product_table_id,
    ).run(
        evidence_dir=Path(args.evidence_dir),
        dry_run=args.dry_run,
        poll_attempts=args.poll_attempts,
        impact_dates=set(args.impact_date),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
