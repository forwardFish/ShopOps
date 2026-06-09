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
F_DATE = "\u6295\u653e\u65e5\u671f"
F_DEAL_SPEND = "\u6210\u4ea4\u82b1\u8d39(\u5143)"
F_TOTAL_SPEND = "\u603b\u82b1\u8d39(\u5143)"
F_DEAL_AMOUNT = "\u4ea4\u6613\u989d(\u5143)"
F_DEAL_COUNT = "\u6210\u4ea4\u7b14\u6570"
F_COST_PER_DEAL = "\u6bcf\u7b14\u6210\u4ea4\u82b1\u8d39(\u5143)"
F_AMOUNT_PER_DEAL = "\u6bcf\u7b14\u6210\u4ea4\u91d1\u989d(\u5143)"
F_RAW = "\u539f\u59cb\u6570\u636e"

PDD_AD_FIELDS = [
    (F_UNIQUE_KEY, TEXT_FIELD),
    (F_PLATFORM, TEXT_FIELD),
    (F_DATA_SOURCE, TEXT_FIELD),
    (F_SHOP_ID, TEXT_FIELD),
    (F_SHOP_NAME, TEXT_FIELD),
    (F_FETCHED_AT, TEXT_FIELD),
    (F_DATE, TEXT_FIELD),
    (F_SPEND, NUMBER_FIELD),
    (F_PROMOTION_SPEND, NUMBER_FIELD),
    (F_ACTUAL_SPEND, NUMBER_FIELD),
    (F_DEAL_SPEND, NUMBER_FIELD),
    (F_TOTAL_SPEND, NUMBER_FIELD),
    (F_DEAL_AMOUNT, NUMBER_FIELD),
    (F_DEAL_COUNT, NUMBER_FIELD),
    (F_COST_PER_DEAL, NUMBER_FIELD),
    (F_AMOUNT_PER_DEAL, NUMBER_FIELD),
    (F_IMPRESSIONS_EXISTING, NUMBER_FIELD),
    (F_IMPRESSIONS, NUMBER_FIELD),
    (F_CLICKS, NUMBER_FIELD),
    (F_CLICK_RATE, NUMBER_FIELD),
    (F_CPC, NUMBER_FIELD),
    (F_PLATFORM_ROI, NUMBER_FIELD),
    (F_TRUE_ROI, NUMBER_FIELD),
    (F_ROI, NUMBER_FIELD),
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
        for field_name, field_type in PDD_AD_FIELDS:
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


def load_pdd_ad_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_excel(path, engine="xlrd")
    rows: list[dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, source in frame.iterrows():
        raw_date = source.get("\u65e5\u671f")
        if raw_date in (None, "") or str(raw_date).strip() == "\u603b\u8ba1":
            continue
        date_text = normalize_date(raw_date)
        if not date_text:
            continue
        deal_spend = number_value(source.get(F_DEAL_SPEND))
        total_spend = number_value(source.get(F_TOTAL_SPEND))
        deal_amount = number_value(source.get(F_DEAL_AMOUNT))
        clicks = int_value(source.get(F_CLICKS))
        impressions = int_value(source.get(F_IMPRESSIONS))
        deal_count = int_value(source.get(F_DEAL_COUNT))
        spend_for_roi = deal_spend if deal_spend is not None else total_spend
        rows.append(
            {
                F_UNIQUE_KEY: f"pdd_ads_{date_text}",
                F_PLATFORM: "\u62fc\u591a\u591a",
                F_DATA_SOURCE: "\u62fc\u591a\u591a\u5546\u54c1\u63a8\u5e7fExcel\u5bfc\u5165",
                F_SHOP_ID: "",
                F_SHOP_NAME: "\u62fc\u591a\u591a",
                F_FETCHED_AT: now,
                F_DATE: date_text,
                F_SPEND: spend_for_roi,
                F_PROMOTION_SPEND: spend_for_roi,
                F_ACTUAL_SPEND: spend_for_roi,
                F_DEAL_SPEND: deal_spend,
                F_TOTAL_SPEND: total_spend,
                F_DEAL_AMOUNT: deal_amount,
                F_DEAL_COUNT: deal_count,
                F_COST_PER_DEAL: number_value(source.get(F_COST_PER_DEAL)),
                F_AMOUNT_PER_DEAL: number_value(source.get(F_AMOUNT_PER_DEAL)),
                F_IMPRESSIONS_EXISTING: impressions,
                F_IMPRESSIONS: impressions,
                F_CLICKS: clicks,
                F_CLICK_RATE: ratio(clicks, impressions),
                F_CPC: ratio(spend_for_roi, clicks),
                F_PLATFORM_ROI: number_value(source.get("\u5b9e\u9645\u6295\u4ea7\u6bd4")),
                F_TRUE_ROI: ratio(deal_amount, spend_for_roi),
                F_ROI: ratio(deal_amount, spend_for_roi),
                F_RAW: json.dumps(compact_raw(source.to_dict()), ensure_ascii=False, sort_keys=True, default=str),
            }
        )
    rows.sort(key=lambda item: item[F_DATE])
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


def number_value(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text == "-":
        return None
    if text.endswith("%"):
        return round(float(text[:-1]) / 100, 6)
    return round(float(text), 4)


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
    parser = argparse.ArgumentParser(description="Import Pinduoduo ad daily Excel into the ShopOps Feishu ad table.")
    parser.add_argument("source", type=Path, help="Pinduoduo ad daily .xls export.")
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

    rows = load_pdd_ad_rows(args.source)
    summary = {
        "status": "dry_run" if args.dry_run else "ready",
        "source": str(args.source),
        "rows": len(rows),
        "first_date": rows[0][F_DATE] if rows else None,
        "last_date": rows[-1][F_DATE] if rows else None,
        "total_deal_spend": round(sum(float(row.get(F_DEAL_SPEND) or 0) for row in rows), 2),
        "total_deal_amount": round(sum(float(row.get(F_DEAL_AMOUNT) or 0) for row in rows), 2),
        "total_impressions": sum(int(row.get(F_IMPRESSIONS) or 0) for row in rows),
        "total_clicks": sum(int(row.get(F_CLICKS) or 0) for row in rows),
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
