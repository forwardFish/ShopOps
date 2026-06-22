from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_robot.hourly_ad_interval_summary import (
    PLATFORM_NAMES,
    TOTAL_PLATFORM,
    ORDER_DETAIL_NUMBER_FIELDS,
    ORDER_DETAIL_PREFIXES,
    OrderWindowSummary,
    build_order_detail_fields,
    configured_interval_table_id,
    first_number,
    format_dt,
    parse_datetime,
    prefix_detail_fields,
    safe_div,
    summarize_orders_for_window,
)
from scripts.import_daily_files_to_feishu import F_PLATFORM, FeishuDailyClient, chunks, scalar_text

F_STAT_DATE = "\u91c7\u96c6\u65e5\u671f"
F_WINDOW_START = "\u7a97\u53e3\u5f00\u59cb"
F_WINDOW_END = "\u7a97\u53e3\u7ed3\u675f"

F_INCREMENTAL_AD_SPEND = "\u65b0\u589e\u6295\u6d41\u6d88\u8017"
F_INCREMENTAL_AD_DEAL = "\u65b0\u589e\u6295\u6d41\u6210\u4ea4\u91d1\u989d"
F_INCREMENTAL_PLATFORM_ROI = "\u65b0\u589e\u5e73\u53f0ROI"
F_INCREMENTAL_AD_ROI = "\u65b0\u589e\u6295\u6d41ROI"
F_TODAY_AD_SPEND = "\u4eca\u65e5\u7d2f\u8ba1\u6295\u6d41\u6d88\u8017"
F_TODAY_AD_DEAL = "\u4eca\u65e5\u7d2f\u8ba1\u6295\u6d41\u6210\u4ea4\u91d1\u989d"
F_TODAY_PLATFORM_ROI = "\u4eca\u65e5\u7d2f\u8ba1\u5e73\u53f0ROI"
F_TODAY_AD_ROI = "\u4eca\u65e5\u7d2f\u8ba1\u6295\u6d41ROI"

DEFAULT_FIELDS = [
    F_PLATFORM,
    F_STAT_DATE,
    F_WINDOW_START,
    F_WINDOW_END,
    F_INCREMENTAL_AD_SPEND,
    F_INCREMENTAL_AD_DEAL,
    F_INCREMENTAL_PLATFORM_ROI,
    F_INCREMENTAL_AD_ROI,
    F_TODAY_AD_SPEND,
    F_TODAY_AD_DEAL,
    F_TODAY_PLATFORM_ROI,
    F_TODAY_AD_ROI,
]
ORDER_COMPARE_FIELDS = [f"{prefix}{name}" for prefix in ORDER_DETAIL_PREFIXES for name in ORDER_DETAIL_NUMBER_FIELDS]


def combine_order_summaries(summaries: Iterable[OrderWindowSummary]) -> OrderWindowSummary:
    items = list(summaries)
    product_metrics: dict[str, float] = {}
    for item in items:
        for key, value in item.product_metrics.items():
            product_metrics[key] = round(product_metrics.get(key, 0.0) + value, 6)
    return OrderWindowSummary(
        count=sum(item.count for item in items),
        actual_sold_quantity=round(sum(item.actual_sold_quantity for item in items), 6),
        sales_amount=round(sum(item.sales_amount for item in items), 6),
        paid_amount=round(sum(item.paid_amount for item in items), 6),
        refund_amount=round(sum(item.refund_amount for item in items), 6),
        valid_sales_override=round(sum(item.valid_sales_amount for item in items), 6),
        product_cost=round(sum(item.product_cost for item in items), 6),
        freight_cost=round(sum(item.freight_cost for item in items), 6),
        platform_fee=round(sum(item.platform_fee for item in items), 6),
        other_fee=round(sum(item.other_fee for item in items), 6),
        estimated_commission=round(sum(item.estimated_commission for item in items), 6),
        actual_commission=round(sum(item.actual_commission for item in items), 6),
        refund_order_count=sum(item.refund_order_count for item in items),
        product_metrics=product_metrics,
    )


def platform_names_for_row(platform: str) -> list[str]:
    if platform == TOTAL_PLATFORM:
        return [PLATFORM_NAMES["tmall"], PLATFORM_NAMES["douyin"]]
    return [platform]


def recompute_row_fields(client: FeishuDailyClient, row: dict[str, Any]) -> dict[str, Any]:
    window_start = parse_datetime(row.get(F_WINDOW_START))
    window_end = parse_datetime(row.get(F_WINDOW_END))
    if not window_start or not window_end:
        return {}

    platform = scalar_text(row.get(F_PLATFORM))
    platform_names = platform_names_for_row(platform)
    today_start = datetime.combine(window_end.date(), datetime.min.time()) - timedelta(microseconds=1)

    incremental = combine_order_summaries(
        summarize_orders_for_window(client, name, window_start, window_end) for name in platform_names
    )
    cumulative = combine_order_summaries(
        summarize_orders_for_window(client, name, today_start, window_end) for name in platform_names
    )

    incremental_spend = first_number(row, F_INCREMENTAL_AD_SPEND) or 0.0
    incremental_deal = first_number(row, F_INCREMENTAL_AD_DEAL) or 0.0
    today_spend = first_number(row, F_TODAY_AD_SPEND) or 0.0
    today_deal = first_number(row, F_TODAY_AD_DEAL) or 0.0

    incremental_roi = first_number(row, F_INCREMENTAL_PLATFORM_ROI, F_INCREMENTAL_AD_ROI)
    today_roi = first_number(row, F_TODAY_PLATFORM_ROI, F_TODAY_AD_ROI)
    if incremental_roi is None:
        incremental_roi = safe_div(incremental_deal, incremental_spend)
    if today_roi is None:
        today_roi = safe_div(today_deal, today_spend)

    return {
        **prefix_detail_fields(
            "\u65b0\u589e",
            build_order_detail_fields(
                incremental,
                ad_spend=incremental_spend,
                ad_deal_amount=incremental_deal,
                platform_roi=incremental_roi,
            ),
        ),
        **prefix_detail_fields(
            "\u4eca\u65e5\u7d2f\u8ba1",
            build_order_detail_fields(
                cumulative,
                ad_spend=today_spend,
                ad_deal_amount=today_deal,
                platform_roi=today_roi,
            ),
        ),
    }


def changed_fields(current: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key, value in updated.items():
        if value in (None, ""):
            continue
        current_value = first_number(current, key)
        if isinstance(value, float):
            value = round(value, 6)
        if current_value is not None and isinstance(value, int | float):
            if round(float(current_value), 6) == round(float(value), 6):
                continue
        elif scalar_text(current.get(key)) == scalar_text(value):
            continue
        changes[key] = value
    return changes


def repair_interval_order_metrics(
    *,
    date_text: str,
    table_id: str,
    platforms: set[str],
    dry_run: bool = False,
) -> dict[str, Any]:
    client = FeishuDailyClient()
    original_field_names = client.field_names
    field_name_cache: dict[str, set[str]] = {}

    def cached_field_names(target_table_id: str) -> set[str]:
        if target_table_id not in field_name_cache:
            field_name_cache[target_table_id] = original_field_names(target_table_id)
        return field_name_cache[target_table_id]

    original_iter_records = client.iter_records
    record_cache: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}

    def cached_iter_records(target_table_id: str, field_names: list[str] | None = None) -> Iterable[dict[str, Any]]:
        key = (target_table_id, tuple(field_names or ()))
        if key not in record_cache:
            record_cache[key] = list(original_iter_records(target_table_id, field_names))
        yield from record_cache[key]

    client.field_names = cached_field_names  # type: ignore[method-assign]
    client.iter_records = cached_iter_records  # type: ignore[method-assign]

    existing_fields = client.field_names(table_id)
    field_names = [field for field in [*DEFAULT_FIELDS, *ORDER_COMPARE_FIELDS] if field in existing_fields]
    records = list(client.iter_records(table_id, field_names))
    to_update: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []

    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        platform = scalar_text(fields.get(F_PLATFORM))
        if scalar_text(fields.get(F_STAT_DATE)) != date_text:
            continue
        if platforms and platform not in platforms:
            continue
        if platform not in {TOTAL_PLATFORM, *PLATFORM_NAMES.values()}:
            continue
        recalculated = {key: value for key, value in recompute_row_fields(client, fields).items() if key in existing_fields}
        changes = changed_fields(fields, recalculated)
        checked.append(
            {
                "record_id": record_id,
                "platform": platform,
                "window_start": scalar_text(fields.get(F_WINDOW_START)),
                "window_end": scalar_text(fields.get(F_WINDOW_END)),
                "changed_fields": sorted(changes),
            }
        )
        if record_id and changes:
            to_update.append({"record_id": record_id, "fields": changes})

    if not dry_run:
        for chunk in chunks(to_update, 500):
            client.request(
                "POST",
                f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records/batch_update",
                {"records": chunk},
            )

    return {
        "status": "dry_run" if dry_run else "success",
        "date": date_text,
        "table_id": table_id,
        "platforms": sorted(platforms) if platforms else "all",
        "checked_rows": len(checked),
        "updated_rows": len(to_update),
        "updated_fields": sum(len(item["fields"]) for item in to_update),
        "sample": checked[:20],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair hourly interval order metrics from current Feishu order tables.")
    parser.add_argument("--date", default=datetime.now().date().isoformat(), help="Stat date to repair, YYYY-MM-DD.")
    parser.add_argument("--table-id", default="", help="Hourly interval table id. Defaults to configured table id.")
    parser.add_argument("--platform", action="append", default=[], help="Platform name to repair. Repeatable; defaults to all.")
    parser.add_argument("--evidence", default="", help="Write repair evidence JSON to this path.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    table_id = args.table_id or configured_interval_table_id()
    if not table_id:
        raise SystemExit("Missing hourly interval table id; pass --table-id or configure SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID.")
    result = repair_interval_order_metrics(
        date_text=args.date,
        table_id=table_id,
        platforms=set(args.platform),
        dry_run=args.dry_run,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.evidence:
        path = Path(args.evidence)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
