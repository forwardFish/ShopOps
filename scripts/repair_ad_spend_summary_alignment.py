from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_jushuitan_orders_to_feishu import FeishuOrderWriter, chunks, clean_feishu_fields
from scripts.write_douyin_ads_excel_to_feishu import load_douyin_ad_rows
from scripts.write_pinduoduo_ads_excel_to_feishu import load_pdd_ad_rows
from shopops.config import load_settings


AD_TABLE_ID = "tblXLtZsMTaikCeb"
SUMMARY_TABLE_ID = "tblepMIg19Ov1kSw"

F_UNIQUE_KEY = "unique_key"
F_PLATFORM = "\u5e73\u53f0"
F_DATE = "\u6295\u653e\u65e5\u671f"
F_SPEND = "\u82b1\u8d39"
F_PROMOTION_SPEND = "\u63a8\u5e7f\u82b1\u8d39(\u5143)"
F_ACTUAL_SPEND = "\u5b9e\u9645\u6d88\u8017"
F_DEAL_AMOUNT = "\u6210\u4ea4\u91d1\u989d"
F_IMPRESSIONS_EXISTING = "\u5c55\u73b0\u91cf"
F_CLICKS = "\u70b9\u51fb\u91cf"

F_PDD_DEAL_SPEND = "\u6210\u4ea4\u82b1\u8d39(\u5143)"
F_PDD_DEAL_AMOUNT = "\u4ea4\u6613\u989d(\u5143)"
F_PDD_IMPRESSIONS = "\u66dd\u5149\u91cf"

F_DOUYIN_OVERALL_SPEND = "\u6574\u4f53\u6d88\u8017"
F_DOUYIN_DEAL_AMOUNT = "\u6574\u4f53\u6210\u4ea4\u91d1\u989d"
F_DOUYIN_IMPRESSIONS = "\u6574\u4f53\u5c55\u793a\u6b21\u6570"
F_DOUYIN_CLICKS = "\u6574\u4f53\u70b9\u51fb\u6b21\u6570"

F_STAT_DATE = "\u7edf\u8ba1\u65e5\u671f"
F_SUMMARY_AD_COST = "\u6295\u6d41\u6d88\u8017"
F_SUMMARY_AD_COUNT = "\u6295\u6d41\u8bb0\u5f55\u6570"
F_SUMMARY_IMPRESSIONS = "\u5c55\u73b0"
F_SUMMARY_CLICKS = "\u70b9\u51fb"


def scalar(value: Any) -> Any:
    if isinstance(value, list):
        return "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in value)
    return value


def number(value: Any) -> float:
    value = scalar(value)
    if value in (None, ""):
        return 0.0
    return float(value)


def make_writer(table_id: str) -> FeishuOrderWriter:
    settings = load_settings()
    writer = FeishuOrderWriter(settings)
    writer.app_token = settings.shopops_data_center_app_token
    writer.table_id = table_id
    return writer


def field_index(writer: FeishuOrderWriter) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    page_token = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        data = writer._request(
            "GET",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/fields",
            params=params,
        )
        for item in data.get("items", []) or []:
            if item.get("field_name"):
                fields[str(item["field_name"])] = item
        if not data.get("has_more"):
            return fields
        page_token = data.get("page_token")


def list_records(writer: FeishuOrderWriter) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_token = None
    while True:
        params: dict[str, Any] = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = writer._request(
            "GET",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/records",
            params=params,
        )
        records.extend(data.get("items") or [])
        if not data.get("has_more"):
            return records
        page_token = data.get("page_token")


def update_ad_formulas(writer: FeishuOrderWriter) -> dict[str, str]:
    fields = field_index(writer)
    table = writer.table_id
    formulas = {
        "\u516c\u5f0f_\u7edf\u8ba1\u65e5\u671f": (
            f"LEFT(IFBLANK(bitable::$table[{table}].$field[{fields[F_DATE]['field_id']}],"
            f"bitable::$table[{table}].$field[{fields['\u91c7\u96c6\u65f6\u95f4']['field_id']}]),10)"
        ),
        "\u516c\u5f0f_\u6295\u6d41\u6d88\u8017": (
            f"IFBLANK(bitable::$table[{table}].$field[{fields[F_ACTUAL_SPEND]['field_id']}],"
            f"IFBLANK(bitable::$table[{table}].$field[{fields[F_SPEND]['field_id']}],"
            f"IFBLANK(bitable::$table[{table}].$field[{fields[F_PROMOTION_SPEND]['field_id']}],0)))"
        ),
    }
    updated: dict[str, str] = {}
    for field_name, expression in formulas.items():
        current = fields[field_name]
        payload = {
            "field_name": field_name,
            "type": 20,
            "property": {"formatter": "" if field_name.endswith("\u65e5\u671f") else "0.00", "formula_expression": expression},
        }
        writer._request(
            "PUT",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/fields/{current['field_id']}",
            payload,
        )
        updated[field_name] = expression
    return updated


def record_index(writer: FeishuOrderWriter) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in list_records(writer):
        key = scalar((record.get("fields") or {}).get(F_UNIQUE_KEY))
        if key:
            result[str(key)] = {"record_id": str(record.get("record_id")), "fields": record.get("fields") or {}}
    return result


def update_ad_rows(writer: FeishuOrderWriter, pdd_path: Path, douyin_path: Path) -> dict[str, Any]:
    source_rows = load_pdd_ad_rows(pdd_path) + load_douyin_ad_rows(douyin_path)
    normalized: list[dict[str, Any]] = []
    for row in source_rows:
        key = str(row[F_UNIQUE_KEY])
        if key.startswith("pdd_ads_"):
            spend = row.get(F_PDD_DEAL_SPEND)
            deal_amount = row.get(F_PDD_DEAL_AMOUNT)
            impressions = row.get(F_PDD_IMPRESSIONS)
        else:
            spend = row.get(F_DOUYIN_OVERALL_SPEND)
            deal_amount = row.get(F_DOUYIN_DEAL_AMOUNT)
            impressions = row.get(F_DOUYIN_IMPRESSIONS)
        patch = {
            F_UNIQUE_KEY: key,
            F_PLATFORM: row[F_PLATFORM],
            F_DATE: row[F_DATE],
            F_SPEND: spend,
            F_PROMOTION_SPEND: spend,
            F_ACTUAL_SPEND: spend,
            F_DEAL_AMOUNT: deal_amount,
            F_IMPRESSIONS_EXISTING: impressions,
            F_CLICKS: row.get(F_CLICKS) or row.get(F_DOUYIN_CLICKS),
        }
        full_row = dict(row)
        full_row.update(patch)
        normalized.append(clean_feishu_fields(full_row))

    existing = record_index(writer)
    to_create: list[dict[str, Any]] = []
    to_update: list[dict[str, Any]] = []
    for row in normalized:
        record = existing.get(str(row[F_UNIQUE_KEY]))
        if not record:
            to_create.append({"fields": row})
            continue
        to_update.append({"record_id": record["record_id"], "fields": row})

    saved = 0
    created = 0
    for chunk in chunks(to_create, 500):
        writer._request(
            "POST",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/records/batch_create",
            {"records": chunk},
        )
        created += len(chunk)
    for chunk in chunks(to_update, 500):
        writer._request(
            "POST",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/records/batch_update",
            {"records": chunk},
        )
        saved += len(chunk)
    return {"source_rows": len(source_rows), "created": created, "updated": saved}


def ensure_summary_dimension_rows(writer: FeishuOrderWriter, dates_by_platform: dict[str, set[str]]) -> int:
    existing = record_index(writer)
    rows: list[dict[str, Any]] = []
    all_dates = sorted(set().union(*dates_by_platform.values()))
    for platform, dates in dates_by_platform.items():
        for date_text in sorted(dates):
            rows.append({F_UNIQUE_KEY: f"{date_text}-{platform}", F_STAT_DATE: date_text, F_PLATFORM: platform})
    for date_text in all_dates:
        rows.append({F_UNIQUE_KEY: f"{date_text}-\u5168\u5e73\u53f0\u603b\u8ba1", F_STAT_DATE: date_text, F_PLATFORM: "\u5168\u5e73\u53f0\u603b\u8ba1"})

    to_create: list[dict[str, Any]] = []
    to_update: list[dict[str, Any]] = []
    for row in rows:
        record = existing.get(row[F_UNIQUE_KEY])
        item = {"fields": row}
        if record:
            item["record_id"] = record["record_id"]
            to_update.append(item)
        else:
            to_create.append(item)

    saved = 0
    for chunk in chunks(to_create, 500):
        writer._request(
            "POST",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/records/batch_create",
            {"records": chunk},
        )
        saved += len(chunk)
    for chunk in chunks(to_update, 500):
        writer._request(
            "POST",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/records/batch_update",
            {"records": chunk},
        )
        saved += len(chunk)
    return saved


def summarize_ad_source(writer: FeishuOrderWriter, prefix: str) -> dict[str, Any]:
    rows = []
    for record in list_records(writer):
        fields = record.get("fields") or {}
        key = str(scalar(fields.get(F_UNIQUE_KEY)) or "")
        if key.startswith(prefix):
            rows.append(fields)
    return {
        "rows": len(rows),
        "first_date": min((str(scalar(row.get(F_DATE))) for row in rows), default=None),
        "last_date": max((str(scalar(row.get(F_DATE))) for row in rows), default=None),
        "actual_spend": round(sum(number(row.get(F_ACTUAL_SPEND)) for row in rows), 2),
        "formula_spend": round(sum(number(row.get("\u516c\u5f0f_\u6295\u6d41\u6d88\u8017")) for row in rows), 2),
        "formula_dates": sorted({str(scalar(row.get("\u516c\u5f0f_\u7edf\u8ba1\u65e5\u671f"))) for row in rows})[:3],
    }


def summarize_summary_table(writer: FeishuOrderWriter, dates_by_platform: dict[str, set[str]]) -> dict[str, Any]:
    wanted: set[tuple[str, str]] = set()
    for platform, dates in dates_by_platform.items():
        wanted.update((date_text, platform) for date_text in dates)
    wanted.update((date_text, "\u5168\u5e73\u53f0\u603b\u8ba1") for date_text in set().union(*dates_by_platform.values()))
    rows = []
    for record in list_records(writer):
        fields = record.get("fields") or {}
        key = (str(scalar(fields.get(F_STAT_DATE))), str(scalar(fields.get(F_PLATFORM))))
        if key in wanted:
            rows.append(fields)
    by_platform: dict[str, dict[str, Any]] = {}
    for platform in sorted({item[1] for item in wanted}):
        platform_rows = [row for row in rows if str(scalar(row.get(F_PLATFORM))) == platform]
        by_platform[platform] = {
            "rows": len(platform_rows),
            "ad_cost": round(sum(number(row.get(F_SUMMARY_AD_COST)) for row in platform_rows), 2),
            "ad_count": int(sum(number(row.get(F_SUMMARY_AD_COUNT)) for row in platform_rows)),
            "impressions": int(sum(number(row.get(F_SUMMARY_IMPRESSIONS)) for row in platform_rows)),
            "clicks": int(sum(number(row.get(F_SUMMARY_CLICKS)) for row in platform_rows)),
        }
    return by_platform


def main() -> int:
    pdd_path = Path("D:/lyh/ShopOps/\u62fc\u591a\u591a/0607/\u5546\u54c1\u63a8\u5e7f_\u8d26\u6237_\u5206\u5929\u6570\u636e_20260309\u81f320260606.xls")
    douyin_path = Path("D:/lyh/ShopOps/\u6296\u97f3/0607/\u5168\u57df\u63a8\u5e7f\u6570\u636e_\u5546\u54c1_2026-03-01 00_00_00-2026-06-07 23_59_59-7648823471602008090.xlsx")

    ad_writer = make_writer(AD_TABLE_ID)
    summary_writer = make_writer(SUMMARY_TABLE_ID)
    formula_updates = update_ad_formulas(ad_writer)
    ad_update = update_ad_rows(ad_writer, pdd_path, douyin_path)

    pdd_rows = load_pdd_ad_rows(pdd_path)
    douyin_rows = load_douyin_ad_rows(douyin_path)
    dates_by_platform = {
        "\u62fc\u591a\u591a": {row[F_DATE] for row in pdd_rows},
        "\u6296\u97f3": {row[F_DATE] for row in douyin_rows},
    }
    summary_saved = ensure_summary_dimension_rows(summary_writer, dates_by_platform)
    time.sleep(8)

    result = {
        "formula_updates": formula_updates,
        "ad_update": ad_update,
        "summary_dimension_saved": summary_saved,
        "ad_readback": {
            "pinduoduo": summarize_ad_source(ad_writer, "pdd_ads_"),
            "douyin": summarize_ad_source(ad_writer, "douyin_ads_"),
        },
        "summary_readback": summarize_summary_table(summary_writer, dates_by_platform),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
