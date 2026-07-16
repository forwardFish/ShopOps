from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    ORDER_PRODUCT_CODE_FIELD,
    ORDER_RAW_FIELD,
    ProductRule,
    UNCLASSIFIED_PRODUCT_NAME,
    best_product_rule_for_order,
    extract_order_product_code,
    independent_order_metrics,
    product_rules_from_records,
)
from shopops.services.dynamic_feishu_summary import (
    AD_COST_FIELDS,
    CLICK_FIELDS,
    COMMISSION_AMOUNT_FIELDS,
    COMMISSION_ESTIMATED_FIELDS,
    COMMISSION_SETTLED_FIELDS,
    IMPRESSION_FIELDS,
)
from scripts.bootstrap_formula_dynamic_summary import (
    FORMULA_DATE_FIELD,
    FORMULA_PLATFORM_FIELD,
    PLATFORMS,
    TOTAL_PLATFORM,
    normalize_platform_value,
    parse_date,
)
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient


ORDER_TABLE_ENVS = (
    "SHOPOPS_ORDER_TABLE_TMALL_ID",
    "SHOPOPS_ORDER_TABLE_DOUYIN_ID",
    "SHOPOPS_ORDER_TABLE_PINDUODUO_ID",
    "SHOPOPS_ORDER_TABLE_WECHAT_CHANNELS_ID",
)
ORDER_METRICS = {
    "订单数": "unique_key",
    "实际卖出数量": "数量",
    "销售额": "实收款",
    "退款金额": "退款金额",
    "有效销售额": "有效销售额",
}
AD_METRICS = {
    "投流记录数": "unique_key",
    "投流消耗": "花费",
    "展现": "展现量",
    "点击": "点击量",
}
COMMISSION_METRICS = {
    "达人佣金": "带货费用",
    "预估佣金支出": "预估佣金支出",
    "实际佣金支出": "实际佣金支出",
}
METRICS = {**ORDER_METRICS, **AD_METRICS, **COMMISSION_METRICS}
PRODUCT_NAME_FIELD = "商品名称"
ORDER_DATE_FIELDS = ("创建时间", "订单创建时间", "订单下单时间", "下单时间", "订单提交时间", "订单成交时间", FORMULA_DATE_FIELD)
AD_DATE_FIELDS = ("统计日期", "投放日期", "日期", "采集时间", "更新时间", "投放时间", FORMULA_DATE_FIELD)
COMMISSION_DATE_FIELDS = ("统计日期", "结算日期", "下单日期", "日期", "支付时间", "订单下单时间", "下单时间", "采集时间", "更新时间", FORMULA_DATE_FIELD)
PLATFORM_FIELDS = ("平台", "来源平台", "店铺平台", FORMULA_PLATFORM_FIELD)
ORDER_BASE_FIELDS = ("数量", "实收款", "退款金额", "交易状态", "履约/售后状态")


def text_value(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") or "") for item in value if isinstance(item, dict)).strip()
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return str(value or "").strip()


def number_value(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(text_value(value).replace(",", ""))
    except ValueError:
        return 0.0


def date_range(start: date, end: date) -> set[date]:
    return {start + timedelta(days=offset) for offset in range((end - start).days + 1)}


def first_value(fields: dict[str, Any], aliases: Iterable[str]) -> Any:
    return next((fields.get(name) for name in aliases if fields.get(name) not in (None, "", [])), None)


def first_number(fields: dict[str, Any], aliases: Iterable[str]) -> float:
    return number_value(first_value(fields, aliases))


def source_dimension(
    fields: dict[str, Any],
    start: date,
    end: date,
    date_fields: Iterable[str] = ORDER_DATE_FIELDS,
) -> tuple[str, str] | None:
    stat_date = parse_date(first_value(fields, date_fields))
    platform = normalize_platform_value(text_value(first_value(fields, PLATFORM_FIELDS)))
    if not stat_date or platform not in PLATFORMS or not start <= stat_date <= end:
        return None
    return stat_date.isoformat(), platform


def zero_metrics() -> dict[str, float]:
    return {metric: 0.0 for metric in METRICS}


def initialize_main_dimensions(
    rows: dict[tuple[str, str], dict[str, float]],
    dates: Iterable[date],
) -> None:
    for stat_date in dates:
        for platform in PLATFORMS:
            _ = rows[(stat_date.isoformat(), platform)]


def add_order_metrics(
    rows: dict[tuple[str, str], dict[str, float]],
    records: Iterable[dict[str, Any]],
    start: date,
    end: date,
    source_dimensions: set[tuple[str, str]],
) -> None:
    for record in records:
        fields = record.get("fields") or {}
        dimension = source_dimension(fields, start, end, ORDER_DATE_FIELDS)
        if not dimension:
            continue
        source_dimensions.add(dimension)
        values = rows[dimension]
        metrics = independent_order_metrics(fields)
        values["订单数"] += 1
        values["实际卖出数量"] += metrics["quantity"]
        values["销售额"] += metrics["sales"]
        values["退款金额"] += metrics["refund"]
        values["有效销售额"] += metrics["valid_sales"]


def add_ad_metrics(
    rows: dict[tuple[str, str], dict[str, float]],
    records: Iterable[dict[str, Any]],
    start: date,
    end: date,
    source_dimensions: set[tuple[str, str]],
) -> None:
    for record in records:
        fields = record.get("fields") or {}
        dimension = source_dimension(fields, start, end, AD_DATE_FIELDS)
        if not dimension:
            continue
        source_dimensions.add(dimension)
        values = rows[dimension]
        values["投流记录数"] += 1
        values["投流消耗"] += first_number(fields, (*AD_COST_FIELDS, "推广花费(元)"))
        values["展现"] += first_number(fields, IMPRESSION_FIELDS)
        values["点击"] += first_number(fields, CLICK_FIELDS)


def add_commission_metrics(
    rows: dict[tuple[str, str], dict[str, float]],
    records: Iterable[dict[str, Any]],
    start: date,
    end: date,
    source_dimensions: set[tuple[str, str]],
) -> None:
    for record in records:
        fields = record.get("fields") or {}
        dimension = source_dimension(fields, start, end, COMMISSION_DATE_FIELDS)
        if not dimension:
            continue
        source_dimensions.add(dimension)
        estimated = first_number(fields, COMMISSION_ESTIMATED_FIELDS)
        settled = first_number(fields, COMMISSION_SETTLED_FIELDS)
        amount = settled if settled > 0 else estimated
        if amount == 0:
            amount = first_number(fields, COMMISSION_AMOUNT_FIELDS)
        values = rows[dimension]
        values["达人佣金"] += amount
        values["预估佣金支出"] += estimated
        values["实际佣金支出"] += settled


def add_total_platform_rows(rows: dict[tuple[str, str], dict[str, float]], dates: Iterable[str]) -> None:
    for stat_date in dates:
        total = rows[(stat_date, TOTAL_PLATFORM)]
        for platform in PLATFORMS:
            if platform == TOTAL_PLATFORM:
                continue
            source = rows[(stat_date, platform)]
            for metric in METRICS:
                total[metric] += source[metric]


def expected_rows(
    records_by_table: list[list[dict[str, Any]]],
    start: date,
    end: date,
    *,
    target_dates: set[date] | None = None,
    ad_records: list[dict[str, Any]] | None = None,
    commission_records: list[dict[str, Any]] | None = None,
) -> dict[tuple[str, str], dict[str, float]]:
    rows: dict[tuple[str, str], dict[str, float]] = defaultdict(zero_metrics)
    source_dimensions: set[tuple[str, str]] = set()
    for records in records_by_table:
        add_order_metrics(rows, records, start, end, source_dimensions)
    add_ad_metrics(rows, ad_records or [], start, end, source_dimensions)
    add_commission_metrics(rows, commission_records or [], start, end, source_dimensions)

    if target_dates is not None:
        initialize_main_dimensions(rows, target_dates)
        dates = {value.isoformat() for value in target_dates}
    else:
        dates = {stat_date for stat_date, _platform in source_dimensions}
    add_total_platform_rows(rows, dates)
    return rows


def actual_index(records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        fields = record.get("fields") or {}
        key = text_value(fields.get("unique_key"))
        if key:
            indexed[key].append(fields)
    duplicates = sorted(key for key, values in indexed.items() if len(values) > 1)
    return {key: values[0] for key, values in indexed.items()}, duplicates


def compare_rows(expected: dict[tuple[str, str], dict[str, float]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actual, _duplicates = actual_index(records)
    result: list[dict[str, Any]] = []
    for (stat_date, platform), expected_values in sorted(expected.items()):
        key = f"{stat_date}-{platform}"
        fields = actual.get(key)
        actual_values = {metric: number_value((fields or {}).get(metric)) for metric in METRICS}
        rounded_expected = {metric: round(value, 2) for metric, value in expected_values.items()}
        mismatches: dict[str, dict[str, Any]] = {}
        if fields is None:
            mismatches["dimension_row"] = {"expected": "present", "actual": "missing"}
        mismatches.update(
            {
                metric: {"expected": rounded_expected[metric], "actual": actual_values[metric]}
                for metric in METRICS
                if abs(rounded_expected[metric] - actual_values[metric]) > 0.01
            }
        )
        result.append(
            {
                "date": stat_date,
                "platform": platform,
                "unique_key": key,
                "exists": fields is not None,
                "expected": rounded_expected,
                "actual": actual_values,
                "matches": not mismatches,
                "mismatches": mismatches,
            }
        )
    return result


def expected_product_rows(
    records_by_table: list[list[dict[str, Any]]],
    start: date,
    end: date,
    rules: list[ProductRule],
    *,
    target_dates: set[date] | None = None,
) -> dict[tuple[str, str, str], dict[str, float]]:
    rows: dict[tuple[str, str, str], dict[str, float]] = defaultdict(zero_metrics)
    source_dimensions: set[tuple[str, str]] = set()
    product_names = [*(rule.name for rule in rules), UNCLASSIFIED_PRODUCT_NAME]
    for records in records_by_table:
        for record in records:
            fields = record.get("fields") or {}
            dimension = source_dimension(fields, start, end, ORDER_DATE_FIELDS)
            if not dimension:
                continue
            date_text, platform = dimension
            source_dimensions.add(dimension)
            for product_name in product_names:
                _ = rows[(date_text, platform, product_name)]
            rule = best_product_rule_for_order(
                rules,
                product_name=text_value(fields.get(PRODUCT_NAME_FIELD)),
                product_code=extract_order_product_code(fields),
            )
            product_name = rule.name if rule else UNCLASSIFIED_PRODUCT_NAME
            target = rows[(date_text, platform, product_name)]
            metrics = independent_order_metrics(fields)
            target["订单数"] += 1
            target["实际卖出数量"] += metrics["quantity"]
            target["销售额"] += metrics["sales"]
            target["退款金额"] += metrics["refund"]
            target["有效销售额"] += metrics["valid_sales"]

    if target_dates is not None:
        for stat_date in target_dates:
            for platform in PLATFORMS:
                for product_name in product_names:
                    _ = rows[(stat_date.isoformat(), platform, product_name)]
        dates = {value.isoformat() for value in target_dates}
    else:
        dates = {value[0] for value in source_dimensions}
    for date_text in dates:
        for product_name in product_names:
            total = rows[(date_text, TOTAL_PLATFORM, product_name)]
            for platform in PLATFORMS:
                if platform == TOTAL_PLATFORM:
                    continue
                source = rows[(date_text, platform, product_name)]
                for metric in METRICS:
                    total[metric] += source[metric]
    return rows


def compare_product_rows(
    expected: dict[tuple[str, str, str], dict[str, float]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actual, _duplicates = actual_index(records)
    result: list[dict[str, Any]] = []
    product_metrics = ("订单数", "实际卖出数量", "销售额", "退款金额", "有效销售额")
    for (stat_date, platform, product_name), expected_values in sorted(expected.items()):
        key = f"{stat_date}-{platform}-{product_name}"
        fields = actual.get(key)
        actual_values = {metric: number_value((fields or {}).get(metric)) for metric in product_metrics}
        rounded_expected = {metric: round(expected_values[metric], 2) for metric in product_metrics}
        mismatches: dict[str, dict[str, Any]] = {}
        if fields is None:
            mismatches["dimension_row"] = {"expected": "present", "actual": "missing"}
        mismatches.update(
            {
                metric: {"expected": rounded_expected[metric], "actual": actual_values[metric]}
                for metric in product_metrics
                if abs(rounded_expected[metric] - actual_values[metric]) > 0.01
            }
        )
        result.append(
            {
                "date": stat_date,
                "platform": platform,
                "product": product_name,
                "unique_key": key,
                "exists": fields is not None,
                "expected": rounded_expected,
                "actual": actual_values,
                "matches": not mismatches,
                "mismatches": mismatches,
            }
        )
    return result


def list_records_with_retry(
    client: DynamicSummaryFeishuClient,
    table_id: str,
    field_names: list[str] | None = None,
    filter_formula: str | None = None,
) -> list[dict[str, Any]]:
    for attempt in range(1, 6):
        try:
            if filter_formula:
                return client.list_records(table_id, field_names, filter_formula=filter_formula)
            return client.list_records(table_id, field_names)
        except Exception as exc:
            message = str(exc).lower()
            if attempt == 5 or not ("1254607" in message or "timed out" in message or "connectionerror" in type(exc).__name__.lower()):
                raise
            import time
            time.sleep(attempt * 10)
    raise AssertionError("unreachable")


def existing_field_names(
    client: DynamicSummaryFeishuClient,
    table_id: str,
    desired: Iterable[str],
) -> list[str]:
    available = client.list_field_names(table_id)
    return [name for name in dict.fromkeys(desired) if name in available]


def require_fields(table_id: str, available: set[str], required: Iterable[str]) -> None:
    missing = sorted(set(required) - available)
    if missing:
        raise RuntimeError(f"Source table {table_id} is missing independent verification fields: {missing}")


def require_any_field(table_id: str, available: set[str], aliases: Iterable[str], purpose: str) -> str:
    field_name = next((name for name in aliases if name != FORMULA_DATE_FIELD and name in available), "")
    if not field_name:
        raise RuntimeError(f"Source table {table_id} has no base field for independent {purpose} verification")
    return field_name


def base_date_filter(field_name: str, dates: Iterable[date]) -> str:
    clauses = [f'LEFT(CurrentValue.[{field_name}],10)="{value.isoformat()}"' for value in sorted(dates)]
    if not clauses:
        raise ValueError("At least one target date is required")
    return clauses[0] if len(clauses) == 1 else "(" + "||".join(clauses) + ")"


def list_records_for_base_dates(
    client: DynamicSummaryFeishuClient,
    table_id: str,
    field_names: list[str],
    date_field: str,
    dates: Iterable[date],
) -> list[dict[str, Any]]:
    ordered_dates = sorted(set(dates))
    records: list[dict[str, Any]] = []
    for index in range(0, len(ordered_dates), 7):
        date_batch = ordered_dates[index : index + 7]
        records.extend(
            list_records_with_retry(
                client,
                table_id,
                field_names,
                base_date_filter(date_field, date_batch),
            )
        )
    return records


def source_table_id(*names: str) -> str:
    return next((os.getenv(name, "").strip() for name in names if os.getenv(name, "").strip()), "")


def source_date_filter(dates: Iterable[date]) -> str:
    clauses = [f'CurrentValue.[{FORMULA_DATE_FIELD}]="{value.isoformat()}"' for value in sorted(dates)]
    if not clauses:
        raise ValueError("At least one target date is required")
    return clauses[0] if len(clauses) == 1 else "(" + "||".join(clauses) + ")"


def summary_date_filter(dates: Iterable[date]) -> str:
    # 汇总key is a formula text field shared by platform-main and product rows.
    # Filtering the date field directly is unreliable when the Bitable column is
    # stored as a timestamp, while this value is explicitly YYYY-MM-DD-platform.
    clauses = [
        f'CurrentValue.[汇总key]="{value.isoformat()}-{platform}"'
        for value in sorted(dates)
        for platform in PLATFORMS
    ]
    if not clauses:
        raise ValueError("At least one target date is required")
    return clauses[0] if len(clauses) == 1 else "(" + "||".join(clauses) + ")"


def list_summary_records_for_dates(
    client: DynamicSummaryFeishuClient,
    table_id: str,
    field_names: list[str],
    dates: Iterable[date],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for target_date in sorted(set(dates)):
        records.extend(
            list_records_with_retry(
                client,
                table_id,
                field_names,
                summary_date_filter([target_date]),
            )
        )
    return records


def failure_categories(rows: list[dict[str, Any]], product_rows: list[dict[str, Any]], duplicate_keys: list[str]) -> list[str]:
    categories: set[str] = set()
    all_rows = [*rows, *product_rows]
    if any(not row["exists"] for row in all_rows):
        categories.add("missing_dimension_rows")
    if any(row["exists"] and not row["matches"] for row in all_rows):
        categories.add("metric_mismatch")
    if duplicate_keys:
        categories.add("duplicate_dimension_rows")
    return sorted(categories)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify formula dynamic summary rows against Feishu order, ad, and commission sources.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--summary-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID"))
    parser.add_argument("--product-catalog-table-id", default=os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID", DEFAULT_PRODUCT_CATALOG_TABLE_ID))
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence", default="docs/live-evidence/formula-dynamic-summary/source-summary-verification.json")
    args = parser.parse_args()

    env_path = Path(args.env_path)
    _load_dotenv(env_path)
    args.app_token = args.app_token or os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN")
    args.summary_table_id = args.summary_table_id or os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID")
    if not args.app_token or not args.summary_table_id:
        raise RuntimeError("Missing Feishu app token or formula summary table id")
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if end < start:
        raise ValueError("end-date must not be before start-date")

    client = DynamicSummaryFeishuClient(args.app_token, env_path)
    order_ids = [os.getenv(name, "").strip() for name in ORDER_TABLE_ENVS]
    ad_table_id = source_table_id("SHOPOPS_AD_TABLE_ID", "FEISHU_TABLE_PROMOTION_SNAPSHOT")
    commission_table_id = source_table_id("SHOPOPS_COMMISSION_TABLE_ID", "FEISHU_TABLE_DOUYIN_INFLUENCER_EXCEL_TABLE_ID", "FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION")
    missing = [name for name, value in {"order source tables": all(order_ids), "ad source table": ad_table_id, "commission source table": commission_table_id}.items() if not value]
    if missing:
        raise RuntimeError("Missing " + ", ".join(missing))

    rules = product_rules_from_records(list_records_with_retry(client, args.product_catalog_table_id))
    if not rules:
        raise RuntimeError("Product catalog has no usable product classification rules")
    order_fields = [
        "unique_key", *ORDER_DATE_FIELDS, *PLATFORM_FIELDS, PRODUCT_NAME_FIELD, ORDER_PRODUCT_CODE_FIELD, ORDER_RAW_FIELD,
        *ORDER_BASE_FIELDS,
    ]
    ad_fields = ["unique_key", *AD_DATE_FIELDS, *PLATFORM_FIELDS, *AD_COST_FIELDS, "推广花费(元)", *IMPRESSION_FIELDS, *CLICK_FIELDS]
    commission_fields = [
        "unique_key", *COMMISSION_DATE_FIELDS, *PLATFORM_FIELDS,
        *COMMISSION_AMOUNT_FIELDS, *COMMISSION_ESTIMATED_FIELDS, *COMMISSION_SETTLED_FIELDS,
    ]
    target_dates = date_range(start, end)
    summary_records = list_summary_records_for_dates(
        client,
        args.summary_table_id,
        ["unique_key", *METRICS],
        target_dates,
    )
    order_records = []
    for table_id in order_ids:
        available = client.list_field_names(table_id)
        require_fields(
            table_id,
            available,
            ("unique_key", "创建时间", "平台", PRODUCT_NAME_FIELD, ORDER_PRODUCT_CODE_FIELD, ORDER_RAW_FIELD, *ORDER_BASE_FIELDS),
        )
        order_records.append(
            list_records_for_base_dates(
                client,
                table_id,
                [field for field in dict.fromkeys(order_fields) if field in available],
                "创建时间",
                target_dates,
            )
        )
    ad_available = client.list_field_names(ad_table_id)
    ad_date_field = require_any_field(ad_table_id, ad_available, AD_DATE_FIELDS, "date")
    require_any_field(ad_table_id, ad_available, PLATFORM_FIELDS, "platform")
    require_any_field(ad_table_id, ad_available, (*AD_COST_FIELDS, "推广花费(元)"), "spend")
    ad_records = list_records_for_base_dates(
        client,
        ad_table_id,
        [field for field in dict.fromkeys(ad_fields) if field in ad_available],
        ad_date_field,
        target_dates,
    )
    commission_available = client.list_field_names(commission_table_id)
    commission_date_field = require_any_field(commission_table_id, commission_available, COMMISSION_DATE_FIELDS, "date")
    require_any_field(commission_table_id, commission_available, PLATFORM_FIELDS, "platform")
    require_any_field(
        commission_table_id,
        commission_available,
        (*COMMISSION_AMOUNT_FIELDS, *COMMISSION_ESTIMATED_FIELDS, *COMMISSION_SETTLED_FIELDS),
        "amount",
    )
    commission_records = list_records_for_base_dates(
        client,
        commission_table_id,
        [field for field in dict.fromkeys(commission_fields) if field in commission_available],
        commission_date_field,
        target_dates,
    )
    expected = expected_rows(order_records, start, end, target_dates=target_dates, ad_records=ad_records, commission_records=commission_records)
    expected_products = expected_product_rows(order_records, start, end, rules, target_dates=target_dates)
    comparison = compare_rows(expected, summary_records)
    product_comparison = compare_product_rows(expected_products, summary_records)
    _actual, duplicate_keys = actual_index(summary_records)
    relevant_duplicate_keys = [key for key in duplicate_keys if key[:10] in {value.isoformat() for value in target_dates}]
    missing_platform_keys = [row["unique_key"] for row in comparison if not row["exists"]]
    missing_product_keys = [row["unique_key"] for row in product_comparison if not row["exists"]]
    categories = failure_categories(comparison, product_comparison, relevant_duplicate_keys)
    payload = {
        "status": "success" if not categories else "mismatch",
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "impact_dates": sorted(value.isoformat() for value in target_dates),
        "source_table_ids": {"orders": order_ids, "ads": ad_table_id, "commissions": commission_table_id},
        "source_record_counts": {"orders": [len(records) for records in order_records], "ads": len(ad_records), "commissions": len(commission_records)},
        "summary_table_id": args.summary_table_id,
        "checked_rows": len(comparison),
        "matched_rows": sum(1 for row in comparison if row["matches"]),
        "missing_platform_keys": missing_platform_keys,
        "rows": comparison,
        "product_rules": [rule.name for rule in rules],
        "checked_product_rows": len(product_comparison),
        "matched_product_rows": sum(1 for row in product_comparison if row["matches"]),
        "missing_product_keys": missing_product_keys,
        "product_rows": product_comparison,
        "duplicate_unique_keys": relevant_duplicate_keys,
        "failure_categories": categories,
    }
    evidence = Path(args.evidence)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "success" else 4


if __name__ == "__main__":
    raise SystemExit(main())
