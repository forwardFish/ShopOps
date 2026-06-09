from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_jushuitan_orders_to_feishu import FeishuOrderWriter, chunks, clean_feishu_fields
from shopops.config import load_settings


TEXT_FIELD = 1
NUMBER_FIELD = 2

F_UNIQUE_KEY = "unique_key"
F_PLATFORM = "\u5e73\u53f0"
F_DATA_SOURCE = "\u6570\u636e\u6765\u6e90"
F_SHOP_ID = "\u5e97\u94faID"
F_SHOP_NAME = "\u5e97\u94fa\u540d\u79f0"
F_FETCHED_AT = "\u91c7\u96c6\u65f6\u95f4"
F_DATE = "\u6295\u653e\u65e5\u671f"
F_SPEND = "\u82b1\u8d39"
F_PROMOTION_SPEND = "\u63a8\u5e7f\u82b1\u8d39(\u5143)"
F_ACTUAL_SPEND = "\u5b9e\u9645\u6d88\u8017"
F_IMPRESSIONS_EXISTING = "\u5c55\u73b0\u91cf"
F_IMPRESSIONS = "\u66dd\u5149\u91cf"
F_CLICKS = "\u70b9\u51fb\u91cf"
F_CLICK_RATE = "\u70b9\u51fb\u7387"
F_CPC = "\u70b9\u51fb\u5355\u4ef7"
F_PLATFORM_ROI = "\u5e73\u53f0\u663e\u793aROI"
F_TRUE_ROI = "\u5e73\u53f0\u771f\u5b9eROI"
F_ROI = "ROI"
F_DEAL_AMOUNT = "\u6210\u4ea4\u91d1\u989d"
F_PRODUCT_ID = "\u5546\u54c1ID"
F_PRODUCT_NAME = "\u5546\u54c1\u540d\u79f0"
F_OVERALL_IMPRESSIONS = "\u6574\u4f53\u5c55\u793a\u6b21\u6570"
F_OVERALL_CLICKS = "\u6574\u4f53\u70b9\u51fb\u6b21\u6570"
F_OVERALL_CLICK_RATE = "\u6574\u4f53\u70b9\u51fb\u7387"
F_OVERALL_CONVERSION_RATE = "\u6574\u4f53\u8f6c\u5316\u7387"
F_OVERALL_SPEND = "\u6574\u4f53\u6d88\u8017"
F_OVERALL_DEAL_AMOUNT = "\u6574\u4f53\u6210\u4ea4\u91d1\u989d"
F_OVERALL_PAY_ROI = "\u6574\u4f53\u652f\u4ed8ROI"
F_OVERALL_ORDER_COST = "\u6574\u4f53\u6210\u4ea4\u8ba2\u5355\u6210\u672c"
F_USER_PAID_AMOUNT = "\u7528\u6237\u5b9e\u9645\u652f\u4ed8\u91d1\u989d"
F_PLATFORM_SUBSIDY = "\u7535\u5546\u5e73\u53f0\u8865\u8d34\u91d1\u989d"
F_NET_ROI = "\u51c0\u6210\u4ea4ROI"
F_NET_DEAL_AMOUNT = "\u51c0\u6210\u4ea4\u91d1\u989d"
F_NET_ORDER_COST = "\u51c0\u6210\u4ea4\u8ba2\u5355\u6210\u672c"
F_NET_SETTLEMENT_RATE = "\u51c0\u6210\u4ea4\u91d1\u989d\u7ed3\u7b97\u7387"
F_ONE_HOUR_REFUND_RATE = "1\u5c0f\u65f6\u5185\u9000\u6b3e\u7387"
F_RAW = "\u539f\u59cb\u6570\u636e"

DOUYIN_AD_FIELDS = [
    (F_UNIQUE_KEY, TEXT_FIELD),
    (F_PLATFORM, TEXT_FIELD),
    (F_DATA_SOURCE, TEXT_FIELD),
    (F_SHOP_ID, TEXT_FIELD),
    (F_SHOP_NAME, TEXT_FIELD),
    (F_FETCHED_AT, TEXT_FIELD),
    (F_DATE, TEXT_FIELD),
    (F_PRODUCT_ID, TEXT_FIELD),
    (F_PRODUCT_NAME, TEXT_FIELD),
    (F_SPEND, NUMBER_FIELD),
    (F_PROMOTION_SPEND, NUMBER_FIELD),
    (F_ACTUAL_SPEND, NUMBER_FIELD),
    (F_DEAL_AMOUNT, NUMBER_FIELD),
    (F_IMPRESSIONS_EXISTING, NUMBER_FIELD),
    (F_IMPRESSIONS, NUMBER_FIELD),
    (F_CLICKS, NUMBER_FIELD),
    (F_CLICK_RATE, NUMBER_FIELD),
    (F_CPC, NUMBER_FIELD),
    (F_PLATFORM_ROI, NUMBER_FIELD),
    (F_TRUE_ROI, NUMBER_FIELD),
    (F_ROI, NUMBER_FIELD),
    (F_OVERALL_IMPRESSIONS, NUMBER_FIELD),
    (F_OVERALL_CLICKS, NUMBER_FIELD),
    (F_OVERALL_CLICK_RATE, NUMBER_FIELD),
    (F_OVERALL_CONVERSION_RATE, NUMBER_FIELD),
    (F_OVERALL_SPEND, NUMBER_FIELD),
    (F_OVERALL_DEAL_AMOUNT, NUMBER_FIELD),
    (F_OVERALL_PAY_ROI, NUMBER_FIELD),
    (F_OVERALL_ORDER_COST, NUMBER_FIELD),
    (F_USER_PAID_AMOUNT, NUMBER_FIELD),
    (F_PLATFORM_SUBSIDY, NUMBER_FIELD),
    (F_NET_ROI, NUMBER_FIELD),
    (F_NET_DEAL_AMOUNT, NUMBER_FIELD),
    (F_NET_ORDER_COST, NUMBER_FIELD),
    (F_NET_SETTLEMENT_RATE, NUMBER_FIELD),
    (F_ONE_HOUR_REFUND_RATE, NUMBER_FIELD),
    (F_RAW, TEXT_FIELD),
]


class FeishuAdWriter(FeishuOrderWriter):
    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.app_token = settings.shopops_data_center_app_token
        self.table_id = settings.shopops_ad_table_id

    def ensure_ad_fields(self) -> list[str]:
        existing = self._field_names()
        created: list[str] = []
        for field_name, field_type in DOUYIN_AD_FIELDS:
            if field_name in existing:
                continue
            self._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
                {"field_name": field_name, "type": field_type},
                allow_duplicate=True,
            )
            existing.add(field_name)
            created.append(field_name)
        return created

    def write_ads(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        existing = self._existing_record_ids()
        to_create: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        for row in rows:
            record_id = existing.get(str(row[F_UNIQUE_KEY]))
            fields = clean_feishu_fields(row)
            if record_id:
                to_update.append({"record_id": record_id, "fields": fields})
            else:
                to_create.append({"fields": fields})

        saved = 0
        for chunk in chunks(to_create, 500):
            self._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_create",
                {"records": chunk},
            )
            saved += len(chunk)
        for chunk in chunks(to_update, 500):
            self._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_update",
                {"records": chunk},
            )
            saved += len(chunk)
        return saved


def load_douyin_ad_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_excel(path, engine="openpyxl")
    rows: list[dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, source in frame.iterrows():
        raw_date = source.get("\u65e5\u671f")
        if raw_date in (None, "") or str(raw_date).strip() == "\u5168\u90e8":
            continue
        date_text = normalize_date(raw_date)
        product_id = clean_text(source.get(F_PRODUCT_ID))
        spend = number_value(source.get(F_OVERALL_SPEND))
        deal_amount = number_value(source.get(F_OVERALL_DEAL_AMOUNT))
        impressions = int_value(source.get(F_OVERALL_IMPRESSIONS))
        clicks = int_value(source.get(F_OVERALL_CLICKS))
        rows.append(
            {
                F_UNIQUE_KEY: f"douyin_ads_{product_id}_{date_text}",
                F_PLATFORM: "\u6296\u97f3",
                F_DATA_SOURCE: "\u6296\u97f3\u5168\u57df\u63a8\u5e7f\u5546\u54c1Excel\u5bfc\u5165",
                F_SHOP_ID: "",
                F_SHOP_NAME: "\u6296\u97f3",
                F_FETCHED_AT: now,
                F_DATE: date_text,
                F_PRODUCT_ID: product_id,
                F_PRODUCT_NAME: clean_text(source.get(F_PRODUCT_NAME)),
                F_SPEND: spend,
                F_PROMOTION_SPEND: spend,
                F_ACTUAL_SPEND: spend,
                F_DEAL_AMOUNT: deal_amount,
                F_IMPRESSIONS_EXISTING: impressions,
                F_IMPRESSIONS: impressions,
                F_CLICKS: clicks,
                F_CLICK_RATE: number_value(source.get(F_OVERALL_CLICK_RATE)),
                F_CPC: ratio(spend, clicks),
                F_PLATFORM_ROI: number_value(source.get(F_OVERALL_PAY_ROI)),
                F_TRUE_ROI: ratio(deal_amount, spend),
                F_ROI: number_value(source.get(F_OVERALL_PAY_ROI)),
                F_OVERALL_IMPRESSIONS: impressions,
                F_OVERALL_CLICKS: clicks,
                F_OVERALL_CLICK_RATE: number_value(source.get(F_OVERALL_CLICK_RATE)),
                F_OVERALL_CONVERSION_RATE: number_value(source.get(F_OVERALL_CONVERSION_RATE)),
                F_OVERALL_SPEND: spend,
                F_OVERALL_DEAL_AMOUNT: deal_amount,
                F_OVERALL_PAY_ROI: number_value(source.get(F_OVERALL_PAY_ROI)),
                F_OVERALL_ORDER_COST: number_value(source.get(F_OVERALL_ORDER_COST)),
                F_USER_PAID_AMOUNT: number_value(source.get(F_USER_PAID_AMOUNT)),
                F_PLATFORM_SUBSIDY: number_value(source.get(F_PLATFORM_SUBSIDY)),
                F_NET_ROI: number_value(source.get(F_NET_ROI)),
                F_NET_DEAL_AMOUNT: number_value(source.get(F_NET_DEAL_AMOUNT)),
                F_NET_ORDER_COST: number_value(source.get(F_NET_ORDER_COST)),
                F_NET_SETTLEMENT_RATE: number_value(source.get(F_NET_SETTLEMENT_RATE)),
                F_ONE_HOUR_REFUND_RATE: number_value(source.get(F_ONE_HOUR_REFUND_RATE)),
                F_RAW: json.dumps(compact_raw(source.to_dict()), ensure_ascii=False, sort_keys=True, default=str),
            }
        )
    rows.sort(key=lambda item: (item[F_DATE], item[F_PRODUCT_ID]))
    return rows


def normalize_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text
    return parsed.strftime("%Y-%m-%d")


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def number_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    if text.endswith("%"):
        return round(float(text[:-1]) / 100, 6)
    return round(float(text), 6)


def int_value(value: Any) -> int | None:
    number = number_value(value)
    return None if number is None else int(round(number))


def ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), 6)


def compact_raw(row: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in row.items():
        if value is None or pd.isna(value):
            continue
        compact[str(key)] = value
    return compact


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Douyin Global Promotion product Excel into the ShopOps Feishu ad table.")
    parser.add_argument("source", type=Path, help="Douyin Global Promotion product .xlsx export.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing Feishu.")
    args = parser.parse_args()

    settings = load_settings()
    missing = []
    if not settings.feishu_app_id:
        missing.append("FEISHU_APP_ID")
    if not settings.feishu_app_secret:
        missing.append("FEISHU_APP_SECRET")
    if not settings.shopops_data_center_app_token:
        missing.append("SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN")
    if not settings.shopops_ad_table_id:
        missing.append("SHOPOPS_AD_TABLE_ID or FEISHU_TABLE_PROMOTION_SNAPSHOT")
    if missing:
        print(json.dumps({"status": "missing_inputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    rows = load_douyin_ad_rows(args.source)
    summary = {
        "status": "dry_run" if args.dry_run else "ready",
        "source": str(args.source),
        "rows": len(rows),
        "first_date": rows[0][F_DATE] if rows else None,
        "last_date": rows[-1][F_DATE] if rows else None,
        "total_spend": round(sum(float(row.get(F_OVERALL_SPEND) or 0) for row in rows), 2),
        "total_deal_amount": round(sum(float(row.get(F_OVERALL_DEAL_AMOUNT) or 0) for row in rows), 2),
        "total_user_paid_amount": round(sum(float(row.get(F_USER_PAID_AMOUNT) or 0) for row in rows), 2),
        "total_impressions": sum(int(row.get(F_OVERALL_IMPRESSIONS) or 0) for row in rows),
        "total_clicks": sum(int(row.get(F_OVERALL_CLICKS) or 0) for row in rows),
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    writer = FeishuAdWriter(settings)
    created_fields = writer.ensure_ad_fields()
    saved = writer.write_ads(rows)
    summary.update({"status": "written", "saved": saved, "created_fields": created_fields})
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
