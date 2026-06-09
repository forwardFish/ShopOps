from __future__ import annotations

import argparse
import json
import re
import sys
import time
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

AD_TABLE_ID = "tblXLtZsMTaikCeb"
SUMMARY_TABLE_ID = "tblepMIg19Ov1kSw"

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
F_DEAL_AMOUNT = "\u6210\u4ea4\u91d1\u989d"
F_IMPRESSIONS_EXISTING = "\u5c55\u73b0\u91cf"
F_CLICKS = "\u70b9\u51fb\u91cf"
F_CLICK_RATE = "\u70b9\u51fb\u7387"
F_CPC = "\u70b9\u51fb\u5355\u4ef7"
F_PLATFORM_ROI = "\u5e73\u53f0\u663e\u793aROI"
F_TRUE_ROI = "\u5e73\u53f0\u771f\u5b9eROI"
F_ROI = "ROI"
F_CART_USERS = "\u52a0\u8d2d\u4eba\u6570"
F_RAW = "\u539f\u59cb\u6570\u636e"

F_SUMMARY_STAT_DATE = "\u7edf\u8ba1\u65e5\u671f"

SOURCE_DATE = "\u65e5\u671f"
SOURCE_SPEND = "\u82b1\u8d39"
SOURCE_IMPRESSIONS = "\u5c55\u73b0\u91cf"
SOURCE_CLICKS = "\u70b9\u51fb\u91cf"
SOURCE_CLICK_RATE = "\u70b9\u51fb\u7387"
SOURCE_ROI = "\u6295\u5165\u4ea7\u51fa\u6bd4"
SOURCE_CART_USERS = "\u52a0\u8d2d\u4eba\u6570"
SOURCE_DEAL_AMOUNT = "\u603b\u6210\u4ea4\u91d1\u989d"

TMALL_AD_FIELDS = [
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
    (F_DEAL_AMOUNT, NUMBER_FIELD),
    (F_IMPRESSIONS_EXISTING, NUMBER_FIELD),
    (F_CLICKS, NUMBER_FIELD),
    (F_CLICK_RATE, NUMBER_FIELD),
    (F_CPC, NUMBER_FIELD),
    (F_PLATFORM_ROI, NUMBER_FIELD),
    (F_TRUE_ROI, NUMBER_FIELD),
    (F_ROI, NUMBER_FIELD),
    (F_CART_USERS, NUMBER_FIELD),
    (F_RAW, TEXT_FIELD),
]


class FeishuAdWriter(FeishuOrderWriter):
    def __init__(self, table_id: str = AD_TABLE_ID) -> None:
        settings = load_settings()
        super().__init__(settings)
        self.app_token = settings.shopops_data_center_app_token
        self.table_id = table_id

    def ensure_fields(self, fields: list[tuple[str, int]]) -> list[str]:
        existing = self._field_names()
        created: list[str] = []
        for field_name, field_type in fields:
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

    def write_rows(self, rows: list[dict[str, Any]]) -> int:
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


def load_tmall_ad_rows(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_excel(path, engine="openpyxl", header=None)
    header_index = find_header_index(frame)
    headers = [normalize_header(value) for value in frame.iloc[header_index].tolist()]
    data = frame.iloc[header_index + 1 :].copy()
    data.columns = headers
    data = data[[header for header in headers if header]]

    rows: list[dict[str, Any]] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _, source in data.iterrows():
        date_text = normalize_date(source.get(SOURCE_DATE))
        if not date_text:
            continue
        spend = number_value(source.get(SOURCE_SPEND))
        deal_amount = number_value(source.get(SOURCE_DEAL_AMOUNT))
        clicks = int_value(source.get(SOURCE_CLICKS))
        impressions = int_value(source.get(SOURCE_IMPRESSIONS))
        rows.append(
            {
                F_UNIQUE_KEY: f"\u5929\u732b{date_text}",
                F_PLATFORM: "\u5929\u732b",
                F_DATA_SOURCE: "\u5929\u732b\u6295\u6d41Excel\u5bfc\u5165",
                F_SHOP_ID: "",
                F_SHOP_NAME: "\u5929\u732b",
                F_FETCHED_AT: now,
                F_DATE: date_text,
                F_SPEND: spend,
                F_PROMOTION_SPEND: spend,
                F_ACTUAL_SPEND: spend,
                F_DEAL_AMOUNT: deal_amount,
                F_IMPRESSIONS_EXISTING: impressions,
                F_CLICKS: clicks,
                F_CLICK_RATE: number_value(source.get(SOURCE_CLICK_RATE)),
                F_CPC: ratio(spend, clicks),
                F_PLATFORM_ROI: number_value(source.get(SOURCE_ROI)),
                F_TRUE_ROI: ratio(deal_amount, spend),
                F_ROI: number_value(source.get(SOURCE_ROI)),
                F_CART_USERS: int_value(source.get(SOURCE_CART_USERS)),
                F_RAW: json.dumps(compact_raw(source.to_dict()), ensure_ascii=False, sort_keys=True, default=str),
            }
        )
    rows.sort(key=lambda item: item[F_DATE])
    return rows


def find_header_index(frame: pd.DataFrame) -> int:
    for index, row in frame.iterrows():
        headers = {normalize_header(value) for value in row.tolist()}
        if {SOURCE_DATE, SOURCE_SPEND, SOURCE_IMPRESSIONS, SOURCE_CLICKS}.issubset(headers):
            return int(index)
    raise RuntimeError("Cannot find Tmall ad export header row")


def normalize_header(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"[\ue000-\uf8ff].*$", "", text)
    return text.strip()


def normalize_date(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


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
        if not key or value is None or pd.isna(value):
            continue
        compact[str(key)] = value
    return compact


def ensure_summary_rows(rows: list[dict[str, Any]]) -> int:
    writer = FeishuAdWriter(SUMMARY_TABLE_ID)
    writer.ensure_fields([(F_UNIQUE_KEY, TEXT_FIELD), (F_SUMMARY_STAT_DATE, TEXT_FIELD), (F_PLATFORM, TEXT_FIELD)])
    summary_rows = [
        {F_UNIQUE_KEY: f"{row[F_DATE]}-\u5929\u732b", F_SUMMARY_STAT_DATE: row[F_DATE], F_PLATFORM: "\u5929\u732b"}
        for row in rows
    ]
    return writer.write_rows(summary_rows)


def readback(prefix: str = "\u5929\u732b") -> dict[str, Any]:
    writer = FeishuAdWriter(AD_TABLE_ID)
    records = []
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
            break
        page_token = data.get("page_token")
    rows = []
    for record in records:
        fields = record.get("fields") or {}
        if str(scalar(fields.get(F_UNIQUE_KEY)) or "").startswith(prefix):
            rows.append(fields)
    return {
        "rows": len(rows),
        "first_date": min((str(scalar(row.get(F_DATE))) for row in rows), default=None),
        "last_date": max((str(scalar(row.get(F_DATE))) for row in rows), default=None),
        "actual_spend": round(sum(number(row.get(F_ACTUAL_SPEND)) for row in rows), 2),
        "formula_spend": round(sum(number(row.get("\u516c\u5f0f_\u6295\u6d41\u6d88\u8017")) for row in rows), 2),
        "impressions": int(sum(number(row.get(F_IMPRESSIONS_EXISTING)) for row in rows)),
        "clicks": int(sum(number(row.get(F_CLICKS)) for row in rows)),
    }


def summary_readback(dates: set[str]) -> dict[str, Any]:
    writer = FeishuAdWriter(SUMMARY_TABLE_ID)
    records = []
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
            break
        page_token = data.get("page_token")
    rows = []
    for record in records:
        fields = record.get("fields") or {}
        if str(scalar(fields.get(F_PLATFORM))) == "\u5929\u732b" and str(scalar(fields.get(F_SUMMARY_STAT_DATE))) in dates:
            rows.append(fields)
    return {
        "rows": len(rows),
        "ad_cost": round(sum(number(row.get("\u6295\u6d41\u6d88\u8017")) for row in rows), 2),
        "ad_count": int(sum(number(row.get("\u6295\u6d41\u8bb0\u5f55\u6570")) for row in rows)),
        "impressions": int(sum(number(row.get("\u5c55\u73b0")) for row in rows)),
        "clicks": int(sum(number(row.get("\u70b9\u51fb")) for row in rows)),
    }


def scalar(value: Any) -> Any:
    if isinstance(value, list):
        return "".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in value)
    return value


def number(value: Any) -> float:
    value = scalar(value)
    if value in (None, ""):
        return 0.0
    return float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Tmall ad Excel into the ShopOps Feishu ad table.")
    parser.add_argument("source", type=Path, help="Tmall ad .xlsx export.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and summarize without writing Feishu.")
    args = parser.parse_args()

    rows = load_tmall_ad_rows(args.source)
    summary = {
        "status": "dry_run" if args.dry_run else "ready",
        "source": str(args.source),
        "rows": len(rows),
        "first_date": rows[0][F_DATE] if rows else None,
        "last_date": rows[-1][F_DATE] if rows else None,
        "total_spend": round(sum(float(row.get(F_ACTUAL_SPEND) or 0) for row in rows), 2),
        "total_deal_amount": round(sum(float(row.get(F_DEAL_AMOUNT) or 0) for row in rows), 2),
        "total_impressions": sum(int(row.get(F_IMPRESSIONS_EXISTING) or 0) for row in rows),
        "total_clicks": sum(int(row.get(F_CLICKS) or 0) for row in rows),
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    writer = FeishuAdWriter(AD_TABLE_ID)
    created_fields = writer.ensure_fields(TMALL_AD_FIELDS)
    saved = writer.write_rows(rows)
    summary_saved = ensure_summary_rows(rows)
    time.sleep(8)
    summary.update(
        {
            "status": "written",
            "saved": saved,
            "summary_rows_saved": summary_saved,
            "created_fields": created_fields,
            "ad_readback": readback(),
            "summary_readback": summary_readback({row[F_DATE] for row in rows}),
        }
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
