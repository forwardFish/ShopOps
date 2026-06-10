from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    effective_sales_amount,
    product_breakdown_values,
    product_field_names,
    product_rules_from_records,
)
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient
from scripts.write_douyin_influencer_excel_to_feishu import (
    doudian_influencer_rows as doudian_commission_excel_rows,
    parse_doudian_xlsx as parse_doudian_commission_xlsx,
)


TEXT_FIELD = 1
NUMBER_FIELD = 2
FORMULA_FIELD = 20

PLATFORMS = ("天猫", "抖音", "拼多多", "视频号")
PLATFORM_CODES = {"天猫": "tmall", "抖音": "douyin", "拼多多": "pdd", "视频号": "wechat_channels"}
ORDER_TABLE_ENV = {
    "天猫": "SHOPOPS_ORDER_TABLE_TMALL_ID",
    "抖音": "SHOPOPS_ORDER_TABLE_DOUYIN_ID",
    "拼多多": "SHOPOPS_ORDER_TABLE_PINDUODUO_ID",
    "视频号": "SHOPOPS_ORDER_TABLE_WECHAT_CHANNELS_ID",
}

F_UNIQUE_KEY = "unique_key"
F_PLATFORM = "平台"
F_DATA_SOURCE = "数据来源"
F_SHOP_ID = "店铺ID"
F_SHOP_NAME = "店铺名称"
F_FETCHED_AT = "采集时间"
F_ORDER_NO = "订单号"
F_CREATED_AT = "创建时间"
F_BUYER_NICK = "买家昵称"
F_PRODUCT_NAME = "商品名称"
F_ACCESSORY_FLAG = "是否是配件"
F_UNIT_PRICE = "单价"
F_QUANTITY = "数量"
F_FULFILL_STATUS = "履约/售后状态"
F_TRADE_STATUS = "交易状态"
F_PAID_AMOUNT = "实收款"
F_REFUND_AMOUNT = "退款金额"
F_PRODUCT_COST = "商品成本"
F_FREIGHT_COST = "运费成本"
F_PLATFORM_FEE = "平台扣点"
F_OTHER_FEE = "其他费用"
F_OPERATION = "操作信息"
F_RAW = "原始数据"

F_DATE = "投放日期"
F_SPEND = "花费"
F_PROMOTION_SPEND = "推广花费(元)"
F_ACTUAL_SPEND = "实际消耗"
F_DEAL_AMOUNT = "成交金额"
F_IMPRESSIONS = "展现量"
F_EXPOSURES = "曝光量"
F_CLICKS = "点击量"
F_CLICK_RATE = "点击率"
F_CPC = "点击单价"
F_ROI = "ROI"
F_PLATFORM_ROI = "平台显示ROI"
F_TRUE_ROI = "平台真实ROI"
F_PRODUCT_ID = "商品ID"
F_DEAL_SPEND = "成交花费(元)"
F_TOTAL_SPEND = "总花费(元)"
F_TRADE_AMOUNT = "交易额(元)"
F_NET_TRADE_AMOUNT = "净交易额(元)"
F_NET_ACTUAL_ROI = "净实际投产比"
F_NET_DEAL_COUNT = "净成交笔数"
F_COST_PER_NET_DEAL = "每笔净成交花费(元)"
F_NET_TRADE_AMOUNT_RATE = "净交易额占比"
F_NET_DEAL_COUNT_RATE = "净成交笔数占比"
F_AMOUNT_PER_NET_DEAL = "每笔净成交金额(元)"
F_SETTLED_TRADE_AMOUNT = "结算交易额(元)"
F_SETTLED_ROI = "结算投产比"
F_SETTLED_DEAL_COUNT = "结算成交笔数"
F_REFUND_EXEMPTION_RATE = "退款豁免率"
F_REFUND_ORDER_EXEMPTION_RATE = "退单豁免率"
F_COST_PER_SETTLED_DEAL = "每笔结算成交花费(元)"
F_TRADE_AMOUNT_SETTLEMENT_RATE = "交易额结算率"
F_ORDER_SETTLEMENT_RATE = "订单结算率"
F_AMOUNT_PER_SETTLED_DEAL = "每笔结算成交金额(元)"
F_DEAL_COUNT = "成交笔数"
F_COST_PER_DEAL = "每笔成交花费(元)"
F_AMOUNT_PER_DEAL = "每笔成交金额(元)"
INTERNAL_PRODUCT_BREAKDOWN_QUANTITY = "__product_breakdown_quantity"

I_SOURCE = "数据来源"
I_CREATED_AT = "下单时间"
I_PAY_AT = "支付时间"
I_STATUS = "订单状态"
I_INFLUENCER_ID = "带货达人ID"
I_INFLUENCER_NICK = "带货达人昵称"
I_COMMISSION_RATE = "带货佣金率"
I_COMMISSION = "带货费用"
I_COMMISSION_BASIS = "带货费用口径"
I_COMMISSION_RATE_NUM = "佣金率"
I_ESTIMATED_COMMISSION = "预估佣金支出"
I_ACTUAL_COMMISSION = "实际佣金支出"
I_SOURCE_FILE = "来源文件"

ORDER_FIELDS = [
    F_UNIQUE_KEY,
    F_PLATFORM,
    F_DATA_SOURCE,
    F_SHOP_ID,
    F_SHOP_NAME,
    F_FETCHED_AT,
    F_ORDER_NO,
    F_CREATED_AT,
    F_BUYER_NICK,
    F_PRODUCT_NAME,
    F_ACCESSORY_FLAG,
    F_UNIT_PRICE,
    F_QUANTITY,
    F_FULFILL_STATUS,
    F_TRADE_STATUS,
    F_PAID_AMOUNT,
    F_REFUND_AMOUNT,
    F_PRODUCT_COST,
    F_FREIGHT_COST,
    F_PLATFORM_FEE,
    F_OTHER_FEE,
    F_OPERATION,
    F_RAW,
]
ORDER_UPDATE_FIELDS = set(ORDER_FIELDS)

AD_FIELDS = [
    F_UNIQUE_KEY,
    F_PLATFORM,
    F_DATA_SOURCE,
    F_SHOP_ID,
    F_SHOP_NAME,
    F_FETCHED_AT,
    F_DATE,
    F_PRODUCT_ID,
    F_PRODUCT_NAME,
    F_SPEND,
    F_PROMOTION_SPEND,
    F_ACTUAL_SPEND,
    F_DEAL_AMOUNT,
    F_DEAL_SPEND,
    F_TOTAL_SPEND,
    F_TRADE_AMOUNT,
    F_NET_TRADE_AMOUNT,
    F_NET_ACTUAL_ROI,
    F_NET_DEAL_COUNT,
    F_COST_PER_NET_DEAL,
    F_NET_TRADE_AMOUNT_RATE,
    F_NET_DEAL_COUNT_RATE,
    F_AMOUNT_PER_NET_DEAL,
    F_SETTLED_TRADE_AMOUNT,
    F_SETTLED_ROI,
    F_SETTLED_DEAL_COUNT,
    F_REFUND_EXEMPTION_RATE,
    F_REFUND_ORDER_EXEMPTION_RATE,
    F_COST_PER_SETTLED_DEAL,
    F_TRADE_AMOUNT_SETTLEMENT_RATE,
    F_ORDER_SETTLEMENT_RATE,
    F_AMOUNT_PER_SETTLED_DEAL,
    F_DEAL_COUNT,
    F_COST_PER_DEAL,
    F_AMOUNT_PER_DEAL,
    F_IMPRESSIONS,
    F_EXPOSURES,
    F_CLICKS,
    F_CLICK_RATE,
    F_CPC,
    F_ROI,
    F_PLATFORM_ROI,
    F_TRUE_ROI,
    F_RAW,
]

AD_FIELD_TYPES = {
    field: TEXT_FIELD
    for field in (F_UNIQUE_KEY, F_PLATFORM, F_DATA_SOURCE, F_SHOP_ID, F_SHOP_NAME, F_FETCHED_AT, F_DATE, F_PRODUCT_ID, F_PRODUCT_NAME, F_RAW)
} | {
    field: NUMBER_FIELD
    for field in AD_FIELDS
    if field not in {F_UNIQUE_KEY, F_PLATFORM, F_DATA_SOURCE, F_SHOP_ID, F_SHOP_NAME, F_FETCHED_AT, F_DATE, F_PRODUCT_ID, F_PRODUCT_NAME, F_RAW}
}

INFLUENCER_FIELDS = [
    F_UNIQUE_KEY,
    F_PLATFORM,
    I_SOURCE,
    F_ORDER_NO,
    I_CREATED_AT,
    I_PAY_AT,
    I_STATUS,
    F_PRODUCT_ID,
    F_PRODUCT_NAME,
    F_QUANTITY,
    F_PAID_AMOUNT,
    I_INFLUENCER_ID,
    I_INFLUENCER_NICK,
    I_COMMISSION_RATE,
    I_COMMISSION,
    I_COMMISSION_BASIS,
    I_COMMISSION_RATE_NUM,
    I_ESTIMATED_COMMISSION,
    I_ACTUAL_COMMISSION,
    F_SHOP_ID,
    F_SHOP_NAME,
    F_FETCHED_AT,
    I_SOURCE_FILE,
    F_RAW,
]

SENSITIVE_KEY_PARTS = (
    "收件",
    "收货",
    "手机",
    "电话",
    "地址",
    "消费者资料",
    "用户购买手机号",
    "详细地址",
    "receiver",
    "address",
    "phone",
    "mobile",
)


class FeishuDailyClient:
    def __init__(self) -> None:
        settings = load_settings()
        self.app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
        if not self.app_token:
            raise RuntimeError("Missing SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN")
        self.auth = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        max_attempts = 6
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.request(
                    method,
                    f"{FEISHU_BASE_URL}{path}",
                    headers=self.auth.headers(),
                    json=payload,
                    params=params,
                    timeout=(10, 90),
                )
                body = response.json()
                if not is_retryable_feishu_response(response.status_code, body):
                    break
                if attempt == max_attempts:
                    break
                time.sleep(min(30, attempt * 5))
            except requests.RequestException as exc:
                last_error = exc
                if attempt == max_attempts:
                    raise
                time.sleep(min(30, attempt * 5))
        else:
            raise RuntimeError(f"Feishu API request failed: {last_error}")
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def field_names(self, table_id: str) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items") or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

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

    def product_rules(self, product_table_id: str) -> list[Any]:
        return product_rules_from_records(list(self.iter_records(product_table_id)))

    def ensure_product_breakdown_fields(self, table_id: str, rules: list[Any]) -> dict[str, str]:
        existing = self.field_index(table_id)
        return {
            name: self.ensure_number_field_with_index(table_id, existing, name)
            for name in product_field_names(rules)
        }

    def iter_records(self, table_id: str, field_names: list[str] | None = None) -> Iterable[dict[str, Any]]:
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            if field_names:
                params["field_names"] = json.dumps(field_names, ensure_ascii=False)
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            yield from data.get("items") or []
            if not data.get("has_more"):
                return
            page_token = data.get("page_token")

    def upsert_rows(
        self,
        *,
        table_id: str,
        rows: list[dict[str, Any]],
        required_fields: list[str],
        fallback_match_fields: tuple[str, ...],
        allow_partial_fields: bool = True,
        update_existing_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        fields = self.field_names(table_id)
        missing_required = [field for field in required_fields if field not in fields]
        if missing_required:
            raise RuntimeError(f"Target table {table_id} is missing required existing fields: {missing_required}")

        unique_index: dict[str, str] = {}
        fallback_index: dict[tuple[str, ...], str] = {}
        index_fields = sorted({F_UNIQUE_KEY, *fallback_match_fields, *(update_existing_fields or set())})
        existing_by_record_id: dict[str, dict[str, Any]] = {}
        for record in self.iter_records(table_id, index_fields):
            record_id = str(record.get("record_id") or "")
            record_fields = record.get("fields") or {}
            if record_id:
                existing_by_record_id[record_id] = record_fields
            unique_key = scalar_text(record_fields.get(F_UNIQUE_KEY))
            if unique_key:
                unique_index[unique_key] = record_id
            fallback_key = tuple(scalar_text(record_fields.get(field)) for field in fallback_match_fields)
            if all(fallback_key):
                fallback_index[fallback_key] = record_id

        dropped_fields: Counter[str] = Counter()
        to_create: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        for row in rows:
            clean: dict[str, Any] = {}
            for key, value in row.items():
                if value in (None, ""):
                    continue
                if key in fields:
                    clean[key] = value
                else:
                    dropped_fields[key] += 1
            if not allow_partial_fields:
                missing = [key for key in row if row.get(key) not in (None, "") and key not in fields]
                if missing:
                    raise RuntimeError(f"Target table {table_id} does not contain fields used by import: {sorted(set(missing))}")

            unique_key = scalar_text(row.get(F_UNIQUE_KEY))
            record_id = unique_index.get(unique_key)
            if not record_id:
                fallback_key = tuple(scalar_text(row.get(field)) for field in fallback_match_fields)
                if all(fallback_key):
                    record_id = fallback_index.get(fallback_key)
            if record_id:
                if update_existing_fields is not None:
                    clean = {key: value for key, value in clean.items() if key in update_existing_fields}
                changed = {
                    key: value
                    for key, value in clean.items()
                    if not field_value_equal(existing_by_record_id.get(record_id, {}).get(key), value)
                }
                if changed:
                    to_update.append({"record_id": record_id, "fields": changed})
            else:
                to_create.append({"fields": clean})

        for chunk in chunks(to_create, 500):
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create", {"records": chunk})
        for chunk in chunks(to_update, 500):
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
        return {
            "created": len(to_create),
            "updated": len(to_update),
            "saved": len(to_create) + len(to_update),
            "dropped_nonexistent_fields": dict(dropped_fields),
        }

    def ensure_missing_fields_for_rows(self, table_id: str, rows: list[dict[str, Any]], field_types: dict[str, int]) -> list[str]:
        existing = self.field_names(table_id)
        needed = sorted(
            key
            for row in rows
            for key, value in row.items()
            if value not in (None, "") and key in field_types and key not in existing
        )
        created: list[str] = []
        for field_name in dict.fromkeys(needed):
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                {"field_name": field_name, "type": field_types[field_name]},
            )
            existing.add(field_name)
            created.append(field_name)
        return created

    def deduplicate_records(self, table_id: str, key_fields: tuple[str, ...]) -> dict[str, Any]:
        fields = self.field_names(table_id)
        missing_required = [field for field in key_fields if field not in fields]
        if missing_required:
            raise RuntimeError(f"Target table {table_id} is missing dedupe fields: {missing_required}")

        seen: set[tuple[str, ...]] = set()
        duplicate_record_ids: list[str] = []
        duplicate_keys: Counter[str] = Counter()
        for record in self.iter_records(table_id, list(key_fields)):
            record_id = str(record.get("record_id") or "")
            record_fields = record.get("fields") or {}
            key = tuple(scalar_text(record_fields.get(field)) for field in key_fields)
            if not record_id or not all(key):
                continue
            if key in seen:
                duplicate_record_ids.append(record_id)
                duplicate_keys["|".join(key)] += 1
            else:
                seen.add(key)

        for chunk in chunks([{"record_id": record_id} for record_id in duplicate_record_ids], 500):
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_delete",
                {"records": [item["record_id"] for item in chunk]},
            )
        return {
            "key_fields": list(key_fields),
            "deleted_duplicate_records": len(duplicate_record_ids),
            "duplicate_keys": len(duplicate_keys),
            "sample_duplicate_keys": list(duplicate_keys)[:20],
        }

    def canonicalize_ad_unique_keys(self, table_id: str) -> dict[str, Any]:
        fields = self.field_names(table_id)
        required = {F_UNIQUE_KEY, F_PLATFORM, F_DATE}
        missing_required = sorted(required - fields)
        if missing_required:
            raise RuntimeError(f"Target ad table {table_id} is missing fields for key canonicalization: {missing_required}")

        rows: list[tuple[str, str, str, str, str]] = []
        canonical_counts: Counter[str] = Counter()
        for record in self.iter_records(table_id, [F_UNIQUE_KEY, F_PLATFORM, F_DATE]):
            record_id = str(record.get("record_id") or "")
            record_fields = record.get("fields") or {}
            original_platform = scalar_text(record_fields.get(F_PLATFORM))
            platform = normalize_platform(original_platform)
            date_text = normalize_date(record_fields.get(F_DATE))
            unique_key = scalar_text(record_fields.get(F_UNIQUE_KEY))
            if not record_id or platform not in PLATFORM_CODES or not date_text:
                continue
            canonical = ad_unique_key(platform, date_text)
            rows.append((record_id, unique_key, canonical, original_platform, platform))
            canonical_counts[canonical] += 1

        to_update: list[dict[str, Any]] = []
        duplicate_record_ids: list[str] = []
        seen: set[str] = set()
        for record_id, unique_key, canonical, original_platform, platform in rows:
            if canonical in seen:
                duplicate_record_ids.append(record_id)
                continue
            seen.add(canonical)
            if unique_key != canonical or original_platform != platform:
                to_update.append({"record_id": record_id, "fields": {F_UNIQUE_KEY: canonical, F_PLATFORM: platform}})

        for chunk in chunks([{"record_id": record_id} for record_id in duplicate_record_ids], 500):
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_delete",
                {"records": [item["record_id"] for item in chunk]},
            )
        for chunk in chunks(to_update, 500):
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
        duplicates = {key: count for key, count in canonical_counts.items() if count > 1}
        return {
            "updated": len(to_update),
            "deleted_duplicate_records": len(duplicate_record_ids),
            "duplicate_canonical_keys": len(duplicates),
            "sample_duplicate_keys": list(duplicates)[:20],
        }

    def delete_platform_records(self, table_id: str, platform: str) -> dict[str, Any]:
        record_ids: list[str] = []
        for record in self.iter_records(table_id, [F_PLATFORM]):
            record_id = str(record.get("record_id") or "")
            record_fields = record.get("fields") or {}
            if record_id and scalar_text(record_fields.get(F_PLATFORM)) == platform:
                record_ids.append(record_id)
        for chunk in chunks([{"record_id": record_id} for record_id in record_ids], 500):
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_delete",
                {"records": [item["record_id"] for item in chunk]},
            )
        return {"platform": platform, "deleted_records": len(record_ids)}

    def readback_by_unique_key(self, table_id: str, unique_keys: set[str]) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        if not unique_keys:
            return found
        for record in self.iter_records(table_id, [F_UNIQUE_KEY]):
            fields = record.get("fields") or {}
            unique_key = scalar_text(fields.get(F_UNIQUE_KEY))
            if unique_key in unique_keys:
                found[unique_key] = fields
        return found


def is_retryable_feishu_response(status_code: int, body: dict[str, Any]) -> bool:
    return status_code in {429, 500, 502, 503, 504} or body.get("code") == 1254607


def discover_daily_files(batch_dir: Path) -> dict[str, dict[str, list[Path]]]:
    result: dict[str, dict[str, list[Path]]] = {platform: {"orders": [], "ads": [], "influencer": []} for platform in PLATFORMS}
    if not batch_dir.exists():
        raise FileNotFoundError(batch_dir)
    for platform_dir in batch_dir.iterdir():
        if not platform_dir.is_dir():
            continue
        platform = normalize_platform(platform_dir.name)
        if platform not in result:
            continue
        for path in platform_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
                continue
            if is_temporary_export_file(path):
                continue
            kind = classify_file(platform, path)
            if kind:
                result[platform][kind].append(path)
    for platform in result:
        for kind in result[platform]:
            result[platform][kind].sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return result


def is_temporary_export_file(path: Path) -> bool:
    return path.name.startswith(("~$", ".~"))


def classify_file(platform: str, path: Path) -> str | None:
    header_kind = classify_headers(peek_headers(path))
    if header_kind:
        return header_kind
    name = path.name.lower()
    if platform == "抖音" and any(token in name for token in ("达人佣金", "佣金", "daren", "commission")):
        return "influencer"
    if any(token in name for token in ("投流", "推广", "全域推广", "商品推广", "分天数据")):
        return "ads"
    if any(token in name for token in ("order", "订单", "exportorderlist", "orders_export")):
        return "orders"
    return "orders" if platform in {"抖音", "拼多多"} and path.suffix.lower() == ".csv" else None


def peek_headers(path: Path) -> set[str]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            for encoding in ("utf-8-sig", "gb18030", "utf-16"):
                try:
                    with path.open("r", encoding=encoding, newline="") as fh:
                        return {clean_header(value) for value in next(csv.reader(fh), [])}
                except UnicodeError:
                    continue
            return set()
        if suffix == ".xls":
            frame = pd.read_excel(path, engine="xlrd", header=None, nrows=20)
            rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
        else:
            workbook = load_workbook(path, data_only=True, read_only=True)
            sheet = workbook.active
            reset_worksheet_dimensions(sheet)
            rows = [tuple(row) for row in sheet.iter_rows(values_only=True, max_row=20)]
        if not rows:
            return set()
        header_index = find_header_index(rows)
        return {clean_header(value) for value in rows[header_index]}
    except Exception:
        return set()


def classify_headers(headers: set[str]) -> str | None:
    if not headers:
        return None
    douyin_commission_signals = {
        "订单id",
        "作者账号",
        "抖音/火山号",
        "支付金额",
        "佣金率",
        "预估佣金支出",
        "结算金额",
        "实际佣金支出",
        "流量来源",
        "APP渠道",
    }
    if "订单id" in headers and len(headers & douyin_commission_signals) >= 4:
        return "influencer"
    order_signals = {
        "订单号",
        "订单编号",
        "主订单编号",
        "子订单编号",
        "订单状态",
        "订单下单时间",
        "订单创建时间",
    }
    ad_signals = {
        "日期",
        "投放日期",
        "花费",
        "推广花费(元)",
        "实际消耗",
        "点击量",
        "展现量",
        "曝光量",
        "投入产出比",
        "ROI",
    }
    if len(headers & order_signals) >= 2 or (headers & {"订单号", "订单编号", "主订单编号"} and headers & {"订单状态"}):
        return "orders"
    if len(headers & ad_signals) >= 2 or ("日期" in headers and headers & {"花费", "点击量", "展现量", "投入产出比"}):
        return "ads"
    return None


def load_tabular(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".xls":
        return load_xls(path)
    return load_xlsx(path)


def load_csv(path: Path) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                reader = csv.DictReader(fh)
                return [
                    {clean_header(key): value for key, value in row.items()}
                    for row in reader
                    if any(value not in (None, "") for value in row.values())
                ]
        except UnicodeError as exc:
            last_error = exc
    raise UnicodeError(f"Cannot decode CSV file {path}: {last_error}")


def load_xlsx(path: Path) -> list[dict[str, Any]]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    sheet = workbook.active
    reset_worksheet_dimensions(sheet)
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    header_index = find_header_index(rows)
    headers = [clean_header(value) for value in rows[header_index]]
    result: list[dict[str, Any]] = []
    for values in rows[header_index + 1 :]:
        row = dict(zip(headers, values))
        if any(value not in (None, "") for value in row.values()):
            result.append(row)
    return result


def reset_worksheet_dimensions(sheet: Any) -> None:
    reset = getattr(sheet, "reset_dimensions", None)
    if callable(reset):
        reset()


def load_xls(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_excel(path, engine="xlrd", header=None)
    rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
    header_index = find_header_index(rows)
    headers = [clean_header(value) for value in rows[header_index]]
    result: list[dict[str, Any]] = []
    for values in rows[header_index + 1 :]:
        row = dict(zip(headers, values))
        if any(value not in (None, "") and not is_nan(value) for value in row.values()):
            result.append(row)
    return result


def find_header_index(rows: list[tuple[Any, ...]] | list[Any]) -> int:
    for index, row in enumerate(rows[:20]):
        headers = {clean_header(value) for value in row}
        if any(key in headers for key in ("订单号", "订单编号", "主订单编号", "日期", "商品", "商品ID")):
            return index
    return 0


def parse_order_rows(platform: str, path: Path) -> list[dict[str, Any]]:
    source_rows = load_tabular(path)
    if platform == "天猫":
        rows = [tmall_order_row(row, path) for row in source_rows]
    elif platform == "抖音":
        rows = [douyin_order_row(row, path) for row in source_rows]
    elif platform == "拼多多":
        rows = [pdd_order_row(row, path) for row in source_rows]
    elif platform == "视频号":
        rows = [wechat_order_row(row, path) for row in source_rows]
    else:
        rows = []
    return collapse_order_rows([row for row in rows if row])


def add_product_breakdown_to_orders(rows: list[dict[str, Any]], rules: list[Any]) -> list[dict[str, Any]]:
    if not rules:
        return rows
    for row in rows:
        row.update(
            product_breakdown_values(
                rules,
                product_name=row.get(F_PRODUCT_NAME),
                actual_quantity=row.get(INTERNAL_PRODUCT_BREAKDOWN_QUANTITY, row.get(F_QUANTITY)),
                valid_sales=effective_sales_amount(row.get(F_PAID_AMOUNT), row.get(F_REFUND_AMOUNT)),
            )
        )
        row.pop(INTERNAL_PRODUCT_BREAKDOWN_QUANTITY, None)
    return rows


def tmall_order_row(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    order_no = clean_text(first_present(row, "订单编号", "订单号"))
    if not order_no:
        return None
    quantity = number_value(first_present(row, "宝贝总数量", "数量", "商品数量"))
    refund = number_value(first_present(row, "退款金额")) or 0
    paid = number_value(first_present(row, "买家实付金额", "实收款", "总金额"))
    if refund > 0 and paid is not None and paid < refund:
        paid = round(paid + refund, 2)
    unit_price = ratio(paid if paid not in (None, 0) else number_value(first_present(row, "买家应付货款", "总金额")), quantity)
    return order_base(
        platform="天猫",
        source="天猫订单Excel导入",
        order_no=order_no,
        created_at=order_created_at("天猫", row, order_no),
        product=clean_text(first_present(row, "商品标题", "商品名称")),
        quantity=quantity,
        unit_price=unit_price,
        paid_amount=paid,
        refund_amount=refund,
        freight=number_value(first_present(row, "买家应付邮费")) or 0,
        platform_fee=number_value(first_present(row, "卖家服务费")) or 0,
        fulfill_status=clean_text(first_present(row, "订单关闭原因")),
        trade_status=clean_text(first_present(row, "订单状态")),
        operation="天猫订单Excel导入",
        source_file=path,
        raw=row,
        shop_id=clean_text(first_present(row, "店铺ID")),
        shop_name=clean_text(first_present(row, "店铺名称")) or "天猫",
    )


def douyin_order_row(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    order_no = clean_text(first_present(row, "主订单编号", "子订单编号", "订单id", "订单ID", "订单号"))
    if not order_no:
        return None
    quantity = number_value(first_present(row, "商品数量", "数量"))
    paid = number_value(first_present(row, "订单应付金额", "支付金额", "实收款"))
    status = clean_text(first_present(row, "订单状态"))
    aftersale = clean_text(first_present(row, "售后状态"))
    refund = refund_from_status(number_value(first_present(row, "退款金额", "已退款金额")), paid, f"{status}/{aftersale}")
    return order_base(
        platform="抖音",
        source="抖店订单CSV导入",
        order_no=order_no,
        created_at=order_created_at("抖音", row, order_no),
        product=clean_text(first_present(row, "选购商品", "商品名称")),
        quantity=quantity,
        unit_price=number_value(first_present(row, "商品单价", "单价")),
        paid_amount=paid,
        refund_amount=refund,
        freight=number_value(first_present(row, "运费")) or 0,
        platform_fee=number_value(first_present(row, "手续费")) or 0,
        fulfill_status=aftersale,
        trade_status=status,
        operation="抖店订单CSV导入",
        source_file=path,
        raw=row,
        shop_id=clean_text(first_present(row, "所属门店ID", "店铺id", "店铺ID")),
        shop_name="抖音",
    )


def pdd_order_row(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    order_no = clean_text(first_present(row, "订单号", "订单编号", "订单ID"))
    if not order_no:
        return None
    quantity = number_value(first_present(row, "商品数量(件)", "商品数量", "数量"))
    paid = number_value(first_present(row, "商家实收金额(元)", "用户实付金额(元)", "商品总价(元)", "实收款"))
    status = clean_text(first_present(row, "订单状态"))
    aftersale = clean_text(first_present(row, "售后状态"))
    refund = refund_from_status(number_value(first_present(row, "退款金额", "已退款金额")), paid, f"{status}/{aftersale}")
    return order_base(
        platform="拼多多",
        source="拼多多订单CSV导入",
        order_no=order_no,
        created_at=order_created_at("拼多多", row, order_no),
        product=clean_text(first_present(row, "商品", "商品名称")),
        quantity=quantity,
        unit_price=ratio(paid, quantity),
        paid_amount=paid,
        refund_amount=refund,
        freight=number_value(first_present(row, "邮费(元)", "运费")) or 0,
        platform_fee=0,
        fulfill_status="/".join(item for item in (status, aftersale) if item),
        trade_status=status,
        operation="拼多多订单CSV导入",
        source_file=path,
        raw=row,
        shop_name="拼多多",
    )


def wechat_order_row(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    order_no = clean_text(first_present(row, "订单号"))
    if not order_no:
        return None
    paid = number_value(first_present(row, "订单实际收款金额", "订单实际支付金额", "商品实际价格(总共)"))
    return order_base(
        platform="视频号",
        source="微信小店订单Excel导入",
        order_no=order_no,
        created_at=order_created_at("视频号", row, order_no),
        product=clean_text(first_present(row, "商品名称")),
        quantity=number_value(first_present(row, "商品数量")),
        unit_price=number_value(first_present(row, "商品实际价格(单件)", "商品价格(单件)")),
        paid_amount=paid,
        refund_amount=number_value(first_present(row, "商品已退款金额")) or 0,
        freight=number_value(first_present(row, "订单运费", "商品平均运费")) or 0,
        platform_fee=number_value(first_present(row, "技术服务费")) or 0,
        other_fee=number_value(first_present(row, "运费险预计投保费用")) or 0,
        fulfill_status=clean_text(first_present(row, "商品发货", "商品售后")),
        trade_status=clean_text(first_present(row, "订单状态")),
        operation="微信小店订单Excel导入",
        source_file=path,
        raw=redact_row(row),
        shop_name="视频号",
    )


def order_base(
    *,
    platform: str,
    source: str,
    order_no: str,
    created_at: str,
    product: str,
    quantity: float | None,
    unit_price: float | None,
    paid_amount: float | None,
    refund_amount: float | None,
    freight: float | None,
    platform_fee: float | None,
    fulfill_status: str,
    trade_status: str,
    operation: str,
    source_file: Path,
    raw: dict[str, Any],
    product_cost: float | None = 0,
    other_fee: float | None = 0,
    shop_id: str = "",
    shop_name: str = "",
) -> dict[str, Any]:
    product_breakdown_quantity = quantity
    quantity = actual_sold_quantity(
        quantity=quantity,
        product=product,
        unit_price=unit_price,
        refund_amount=refund_amount,
        trade_status=trade_status,
        fulfill_status=fulfill_status,
    )
    return {
        F_UNIQUE_KEY: order_unique_key(platform, order_no),
        F_PLATFORM: platform,
        F_DATA_SOURCE: source,
        F_SHOP_ID: shop_id,
        F_SHOP_NAME: shop_name or platform,
        F_FETCHED_AT: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        F_ORDER_NO: order_no,
        F_CREATED_AT: created_at,
        F_BUYER_NICK: "",
        F_PRODUCT_NAME: product,
        F_ACCESSORY_FLAG: "是" if is_accessory_product(product) else "否",
        INTERNAL_PRODUCT_BREAKDOWN_QUANTITY: product_breakdown_quantity,
        F_UNIT_PRICE: unit_price,
        F_QUANTITY: quantity,
        F_FULFILL_STATUS: fulfill_status,
        F_TRADE_STATUS: trade_status,
        F_PAID_AMOUNT: paid_amount,
        F_REFUND_AMOUNT: refund_amount,
        F_PRODUCT_COST: product_cost,
        F_FREIGHT_COST: freight,
        F_PLATFORM_FEE: platform_fee,
        F_OTHER_FEE: other_fee,
        F_OPERATION: operation,
        F_RAW: json.dumps({"source_file": str(source_file), "row": redact_row(raw)}, ensure_ascii=False, sort_keys=True, default=str),
    }


def collapse_order_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row[F_UNIQUE_KEY]
        current = merged.get(key)
        if current is None:
            merged[key] = dict(row)
            continue
        current[F_PRODUCT_NAME] = join_unique(current.get(F_PRODUCT_NAME), row.get(F_PRODUCT_NAME))
        current[F_ACCESSORY_FLAG] = "是" if current.get(F_ACCESSORY_FLAG) == "是" and row.get(F_ACCESSORY_FLAG) == "是" else "否"
        current[INTERNAL_PRODUCT_BREAKDOWN_QUANTITY] = round(
            (number_value(current.get(INTERNAL_PRODUCT_BREAKDOWN_QUANTITY)) or 0)
            + (number_value(row.get(INTERNAL_PRODUCT_BREAKDOWN_QUANTITY)) or 0),
            2,
        )
        for field in (F_QUANTITY, F_PAID_AMOUNT, F_REFUND_AMOUNT, F_PRODUCT_COST, F_FREIGHT_COST, F_PLATFORM_FEE, F_OTHER_FEE):
            current[field] = round((number_value(current.get(field)) or 0) + (number_value(row.get(field)) or 0), 2)
        current[F_FULFILL_STATUS] = join_unique(current.get(F_FULFILL_STATUS), row.get(F_FULFILL_STATUS), "/")
        current[F_TRADE_STATUS] = join_unique(current.get(F_TRADE_STATUS), row.get(F_TRADE_STATUS), "/")
    return list(merged.values())


def parse_ad_rows(platform: str, path: Path) -> list[dict[str, Any]]:
    source_rows = load_tabular(path)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in source_rows:
        date_text = normalize_date(first_present(source, "日期", "投放日期"))
        if not date_text or date_text in {"全部", "总计"}:
            continue
        grouped[date_text].append(source)
    rows: list[dict[str, Any]] = []
    for date_text, items in sorted(grouped.items()):
        rows.append(ad_row(platform, date_text, items, path))
    return rows


def ad_row(platform: str, date_text: str, items: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    deal_spend = sum_numbers(items, F_DEAL_SPEND)
    total_spend = sum_numbers(items, F_TOTAL_SPEND)
    spend = sum_numbers(items, "花费", "整体消耗", F_DEAL_SPEND, F_TOTAL_SPEND)
    deal_amount = sum_numbers(items, "总成交金额", "整体成交金额", F_TRADE_AMOUNT, "成交金额")
    impressions = sum_numbers(items, "展现量", "曝光量", "整体展示次数")
    clicks = sum_numbers(items, "点击量", "整体点击次数")
    roi_value = ratio(deal_amount, spend)
    pdd_fields = pdd_ad_extra_fields(items) if platform == "拼多多" else {}
    return {
        F_UNIQUE_KEY: ad_unique_key(platform, date_text),
        F_PLATFORM: platform,
        F_DATA_SOURCE: f"{platform}投流文件导入",
        F_SHOP_ID: "",
        F_SHOP_NAME: platform,
        F_FETCHED_AT: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        F_DATE: date_text,
        F_SPEND: spend,
        F_PROMOTION_SPEND: spend,
        F_ACTUAL_SPEND: spend,
        F_DEAL_AMOUNT: deal_amount,
        F_DEAL_SPEND: deal_spend if deal_spend else None,
        F_TOTAL_SPEND: total_spend if total_spend else None,
        F_TRADE_AMOUNT: deal_amount,
        **pdd_fields,
        F_IMPRESSIONS: impressions,
        F_EXPOSURES: impressions,
        F_CLICKS: clicks,
        F_CLICK_RATE: ratio(clicks, impressions),
        F_CPC: ratio(spend, clicks),
        F_ROI: roi_value,
        F_PLATFORM_ROI: first_number(items, "投入产出比", "整体支付ROI", "实际投产比") or roi_value,
        F_TRUE_ROI: roi_value,
        F_RAW: json.dumps({"source_file": str(path), "rows": items}, ensure_ascii=False, sort_keys=True, default=str),
    }


PDD_AD_SUM_FIELDS = (
    F_NET_TRADE_AMOUNT,
    F_NET_DEAL_COUNT,
    F_SETTLED_TRADE_AMOUNT,
    F_SETTLED_DEAL_COUNT,
    F_DEAL_COUNT,
)

PDD_AD_RATIO_OR_AVERAGE_FIELDS = (
    F_NET_ACTUAL_ROI,
    F_COST_PER_NET_DEAL,
    F_NET_TRADE_AMOUNT_RATE,
    F_NET_DEAL_COUNT_RATE,
    F_AMOUNT_PER_NET_DEAL,
    F_SETTLED_ROI,
    F_REFUND_EXEMPTION_RATE,
    F_REFUND_ORDER_EXEMPTION_RATE,
    F_COST_PER_SETTLED_DEAL,
    F_TRADE_AMOUNT_SETTLEMENT_RATE,
    F_ORDER_SETTLEMENT_RATE,
    F_AMOUNT_PER_SETTLED_DEAL,
    F_COST_PER_DEAL,
    F_AMOUNT_PER_DEAL,
)


def pdd_ad_extra_fields(items: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in PDD_AD_SUM_FIELDS:
        value = sum_numbers(items, field)
        if value:
            fields[field] = value
    for field in PDD_AD_RATIO_OR_AVERAGE_FIELDS:
        value = first_number(items, field)
        if value is not None:
            fields[field] = value
    return fields


def sample_ad_rows(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    sample_fields = [
        F_UNIQUE_KEY,
        F_PLATFORM,
        F_DATE,
        F_SPEND,
        F_PROMOTION_SPEND,
        F_ACTUAL_SPEND,
        F_DEAL_SPEND,
        F_TOTAL_SPEND,
        F_TRADE_AMOUNT,
        F_DEAL_AMOUNT,
        F_DEAL_COUNT,
        F_COST_PER_DEAL,
        F_AMOUNT_PER_DEAL,
        F_NET_TRADE_AMOUNT,
        F_NET_ACTUAL_ROI,
        F_NET_DEAL_COUNT,
        F_SETTLED_TRADE_AMOUNT,
        F_SETTLED_DEAL_COUNT,
        F_IMPRESSIONS,
        F_EXPOSURES,
        F_CLICKS,
        F_CLICK_RATE,
        F_CPC,
        F_ROI,
        F_PLATFORM_ROI,
        F_TRUE_ROI,
    ]
    return [
        {field: row.get(field) for field in sample_fields if row.get(field) not in (None, "")}
        for row in rows[:limit]
    ]


def parse_influencer_rows(platform: str, path: Path) -> list[dict[str, Any]]:
    if platform not in {"抖音", "视频号"}:
        return []
    if platform == "抖音" and classify_file(platform, path) != "influencer":
        return []
    if platform == "抖音":
        rows = doudian_commission_excel_rows(parse_doudian_commission_xlsx(path), path, [])
        for row in rows:
            actual_commission = number_value(row.get(I_ACTUAL_COMMISSION))
            estimated_commission = number_value(row.get(I_ESTIMATED_COMMISSION))
            commission = actual_commission if actual_commission and actual_commission > 0 else estimated_commission
            row.setdefault(I_INFLUENCER_ID, clean_text(row.get("抖音/火山号")))
            row.setdefault(I_INFLUENCER_NICK, clean_text(row.get("作者账号")))
            row.setdefault(I_COMMISSION_RATE, clean_text(row.get(I_COMMISSION_RATE_NUM)))
            row.setdefault(I_COMMISSION, commission)
            row.setdefault(I_COMMISSION_BASIS, "实际佣金支出" if actual_commission and actual_commission > 0 else "预估佣金支出")
        return rows
    rows = []
    for source in load_tabular(path):
        row = douyin_influencer_row(source, path) if platform == "抖音" else wechat_influencer_row(source, path)
        if row:
            rows.append(row)
    return collapse_influencer_rows(rows)


def douyin_influencer_row(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    order_no = clean_text(first_present(row, "订单id", "主订单编号", "订单ID", "订单号"))
    influencer_id = clean_text(first_present(row, "抖音/火山号", "达人ID"))
    influencer_nick = clean_text(first_present(row, "作者账号", "达人昵称"))
    actual_commission = first_number([row], "实际佣金支出", "达人实际承担优惠金额", "达人优惠")
    estimated_commission = first_number([row], "预估佣金支出")
    commission = actual_commission if actual_commission and actual_commission > 0 else estimated_commission
    if not order_no or not any((influencer_id, influencer_nick, commission)):
        return None
    return influencer_base(
        platform="抖音",
        source="抖音达人佣金Excel导入",
        order_no=order_no,
        created_at=normalize_datetime(first_present(row, "付款时间", "订单提交时间")),
        pay_at=normalize_datetime(first_present(row, "付款时间", "支付完成时间")),
        status=clean_text(first_present(row, "订单状态")),
        product_id=clean_text(first_present(row, "商品id", "商品ID")),
        product_name=clean_text(first_present(row, "商品名称", "选购商品")),
        quantity=number_value(first_present(row, "商品数量")),
        paid_amount=number_value(first_present(row, "支付金额", "订单应付金额")),
        influencer_id=influencer_id,
        influencer_nick=influencer_nick,
        commission_rate=clean_text(first_present(row, "佣金率")),
        commission=commission,
        commission_basis="实际佣金支出" if actual_commission and actual_commission > 0 else "预估佣金支出",
        commission_rate_number=number_value(first_present(row, "佣金率")),
        estimated_commission=estimated_commission,
        actual_commission=actual_commission,
        source_file=path,
        raw=row,
        shop_name=clean_text(first_present(row, "店铺名称")) or "抖音",
    )


def wechat_influencer_row(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    order_no = clean_text(first_present(row, "订单号"))
    influencer_nick = clean_text(first_present(row, "带货账号昵称"))
    commission = number_value(first_present(row, "带货费用"))
    mode = clean_text(first_present(row, "带货方式", "带货费用渠道"))
    if not order_no or not any((influencer_nick, commission, mode)):
        return None
    return influencer_base(
        platform="视频号",
        source="微信小店订单Excel导入",
        order_no=order_no,
        created_at=normalize_datetime(first_present(row, "订单下单时间")),
        pay_at=normalize_datetime(first_present(row, "支付时间")),
        status=clean_text(first_present(row, "订单状态")),
        product_id=clean_text(first_present(row, "商品编码(平台)", "商品ID")),
        product_name=clean_text(first_present(row, "商品名称")),
        quantity=number_value(first_present(row, "商品数量")),
        paid_amount=number_value(first_present(row, "订单实际支付金额")),
        influencer_id="",
        influencer_nick=influencer_nick,
        commission_rate=clean_text(first_present(row, "带货佣金率")),
        commission=commission,
        commission_basis=clean_text(first_present(row, "带货费用类型")) or "带货费用",
        commission_rate_number=number_value(first_present(row, "带货佣金率")),
        estimated_commission=commission,
        actual_commission=None,
        source_file=path,
        raw=redact_row(row),
        shop_name="视频号",
    )


def influencer_base(
    *,
    platform: str,
    source: str,
    order_no: str,
    created_at: str,
    pay_at: str,
    status: str,
    product_id: str,
    product_name: str,
    quantity: float | None,
    paid_amount: float | None,
    influencer_id: str,
    influencer_nick: str,
    commission_rate: str,
    commission: float | None,
    commission_basis: str,
    source_file: Path,
    raw: dict[str, Any],
    shop_name: str,
    commission_rate_number: float | None = None,
    estimated_commission: float | None = None,
    actual_commission: float | None = None,
) -> dict[str, Any]:
    return {
        F_UNIQUE_KEY: f"{platform}{order_no}",
        F_PLATFORM: platform,
        I_SOURCE: source,
        F_ORDER_NO: order_no,
        I_CREATED_AT: created_at,
        I_PAY_AT: pay_at,
        I_STATUS: status,
        F_PRODUCT_ID: product_id,
        F_PRODUCT_NAME: product_name,
        F_QUANTITY: quantity,
        F_PAID_AMOUNT: paid_amount,
        I_INFLUENCER_ID: influencer_id,
        I_INFLUENCER_NICK: influencer_nick,
        I_COMMISSION_RATE: commission_rate,
        I_COMMISSION: commission,
        I_COMMISSION_BASIS: commission_basis,
        I_COMMISSION_RATE_NUM: commission_rate_number,
        I_ESTIMATED_COMMISSION: estimated_commission,
        I_ACTUAL_COMMISSION: actual_commission,
        F_SHOP_ID: "",
        F_SHOP_NAME: shop_name,
        F_FETCHED_AT: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        I_SOURCE_FILE: str(source_file),
        F_RAW: json.dumps(redact_row(raw), ensure_ascii=False, sort_keys=True, default=str),
    }


def collapse_influencer_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row[F_UNIQUE_KEY]
        if key not in merged:
            merged[key] = dict(row)
            continue
        current = merged[key]
        current[F_PRODUCT_NAME] = join_unique(current.get(F_PRODUCT_NAME), row.get(F_PRODUCT_NAME))
        current[F_QUANTITY] = round((number_value(current.get(F_QUANTITY)) or 0) + (number_value(row.get(F_QUANTITY)) or 0), 4)
        current[I_COMMISSION] = round((number_value(current.get(I_COMMISSION)) or 0) + (number_value(row.get(I_COMMISSION)) or 0), 4)
        current[I_ESTIMATED_COMMISSION] = round((number_value(current.get(I_ESTIMATED_COMMISSION)) or 0) + (number_value(row.get(I_ESTIMATED_COMMISSION)) or 0), 4)
        current[I_ACTUAL_COMMISSION] = round((number_value(current.get(I_ACTUAL_COMMISSION)) or 0) + (number_value(row.get(I_ACTUAL_COMMISSION)) or 0), 4)
    return list(merged.values())


def run_import(
    batch_dir: Path,
    dry_run: bool,
    evidence: Path,
    platforms: set[str] | None = None,
    kinds: set[str] | None = None,
    dates: set[str] | None = None,
    ensure_missing_ad_fields: bool = False,
) -> dict[str, Any]:
    _load_dotenv()
    settings = load_settings()
    discovered = discover_daily_files(batch_dir)
    selected_platforms = set(platforms or PLATFORMS)
    selected_kinds = set(kinds or {"orders", "ads", "influencer"})
    selected_dates = {normalize_date(date) for date in dates or set()}
    selected_dates.discard("")
    order_rows_by_platform: dict[str, list[dict[str, Any]]] = {platform: [] for platform in PLATFORMS if platform in selected_platforms}
    ad_rows: list[dict[str, Any]] = []
    influencer_rows: list[dict[str, Any]] = []
    files: dict[str, Any] = {}

    for platform, kinds in discovered.items():
        if platform not in selected_platforms:
            continue
        platform_info: dict[str, Any] = {}
        for order_file in kinds["orders"] if "orders" in selected_kinds else []:
            rows = parse_order_rows(platform, order_file)
            if selected_dates:
                rows = [row for row in rows if normalize_date(row.get(F_CREATED_AT)) in selected_dates]
            order_rows_by_platform[platform].extend(rows)
            platform_info.setdefault("orders", []).append({"file": str(order_file), "rows": len(rows)})
        for influencer_file in kinds["influencer"] if "influencer" in selected_kinds else []:
            rows = parse_influencer_rows(platform, influencer_file)
            if selected_dates:
                rows = [row for row in rows if normalize_date(row.get(I_CREATED_AT) or row.get(I_PAY_AT)) in selected_dates]
            influencer_rows.extend(rows)
            platform_info.setdefault("influencer", []).append({"file": str(influencer_file), "rows": len(rows)})
        for ad_file in kinds["ads"] if "ads" in selected_kinds else []:
            rows = parse_ad_rows(platform, ad_file)
            if selected_dates:
                rows = [row for row in rows if row.get(F_DATE) in selected_dates]
            ad_rows.extend(rows)
            platform_info.setdefault("ads", []).append({"file": str(ad_file), "rows": len(rows)})
        files[platform] = platform_info

    summary: dict[str, Any] = {
        "status": "dry_run" if dry_run else "started",
        "batch_dir": str(batch_dir),
        "feishu_base_url": f"https://my.feishu.cn/base/{settings.shopops_data_center_app_token or settings.feishu_app_token}",
        "field_policy": (
            "create missing ad fields only when explicitly requested; existing records update changed cells only; orders may update order/import fields and product breakdown fields"
            if ensure_missing_ad_fields
            else "existing Feishu fields only; never create, delete, or update table fields during daily import; existing records update changed cells only; orders may update order/import fields and product breakdown fields"
        ),
        "platform_filter": sorted(selected_platforms),
        "kind_filter": sorted(selected_kinds),
        "date_filter": sorted(selected_dates),
        "unique_rules": {
            "orders": "platform_code + '_' + order_no; fallback match by order_no",
            "ads": "ads_platform_code_yyyy-mm-dd; fallback match by platform + date",
            "influencer": "Douyin influencer data must come from an explicit Douyin commission Excel, never from Douyin order exports; fallback match by platform + order_no",
        },
        "files": files,
        "order_counts": {platform: len(rows) for platform, rows in order_rows_by_platform.items()},
        "ad_count": len(ad_rows),
        "influencer_count": len(influencer_rows),
        "ad_dates": sorted({row[F_DATE] for row in ad_rows}),
        "sample_ad_rows": sample_ad_rows(ad_rows),
        "accessory_counts": {
            platform: sum(1 for row in rows if row.get(F_ACCESSORY_FLAG) == "是")
            for platform, rows in order_rows_by_platform.items()
        },
        "sample_accessory_order_keys": {
            platform: [row[F_UNIQUE_KEY] for row in rows if row.get(F_ACCESSORY_FLAG) == "是"][:10]
            for platform, rows in order_rows_by_platform.items()
        },
        "sample_order_keys": {platform: [row[F_UNIQUE_KEY] for row in rows[:10]] for platform, rows in order_rows_by_platform.items()},
    }
    if dry_run:
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
        summary["evidence_path"] = str(evidence.resolve())
        return summary

    client = FeishuDailyClient()
    product_table_id = os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID", DEFAULT_PRODUCT_CATALOG_TABLE_ID).strip()
    product_rules = client.product_rules(product_table_id)
    product_fields = product_field_names(product_rules)
    for platform, rows in order_rows_by_platform.items():
        order_rows_by_platform[platform] = add_product_breakdown_to_orders(rows, product_rules)
    writes: dict[str, Any] = {"orders": {}, "ads": {}, "influencer": {}}
    field_preflight: dict[str, Any] = {"orders": {}, "ads": {}, "influencer": {}}
    influencer_table_id = ""
    for platform, rows in order_rows_by_platform.items():
        if not rows:
            continue
        table_id = os.getenv(ORDER_TABLE_ENV[platform], "").strip()
        if not table_id:
            raise RuntimeError(f"Missing {ORDER_TABLE_ENV[platform]}")
        missing_fields = missing_row_fields(
            client.field_names(table_id),
            rows,
            [F_UNIQUE_KEY, F_ORDER_NO, F_ACCESSORY_FLAG, *product_fields],
        )
        field_preflight["orders"][platform] = {"table_id": table_id, "missing_fields": missing_fields}
        if missing_fields:
            raise RuntimeError(f"Target order table {table_id} is missing existing fields required by this import: {missing_fields}")
    if ad_rows:
        if not settings.shopops_ad_table_id:
            raise RuntimeError("Missing SHOPOPS_AD_TABLE_ID")
        missing_fields = missing_row_fields(client.field_names(settings.shopops_ad_table_id), ad_rows, [F_UNIQUE_KEY, F_PLATFORM, F_DATE])
        field_preflight["ads"] = {"table_id": settings.shopops_ad_table_id, "missing_fields": missing_fields}
        if missing_fields:
            raise RuntimeError(f"Target ad table {settings.shopops_ad_table_id} is missing existing fields required by this import: {missing_fields}")
    if influencer_rows:
        influencer_table_id = os.getenv("SHOPOPS_DOUYIN_INFLUENCER_EXCEL_TABLE_ID", "").strip() or settings.table_douyin_influencer_commission
        if not influencer_table_id or not influencer_table_id.startswith("tbl"):
            raise RuntimeError("Missing SHOPOPS_DOUYIN_INFLUENCER_EXCEL_TABLE_ID or FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION")
        missing_fields = missing_row_fields(client.field_names(influencer_table_id), influencer_rows, [F_UNIQUE_KEY, F_ORDER_NO])
        field_preflight["influencer"] = {"table_id": influencer_table_id, "missing_fields": missing_fields}
        if missing_fields:
            raise RuntimeError(f"Target influencer table {influencer_table_id} is missing existing fields required by this import: {missing_fields}")
    for platform, rows in order_rows_by_platform.items():
        if not rows:
            continue
        table_id = os.getenv(ORDER_TABLE_ENV[platform], "").strip()
        if not table_id:
            raise RuntimeError(f"Missing {ORDER_TABLE_ENV[platform]}")
        writes["orders"][platform] = client.upsert_rows(
            table_id=table_id,
            rows=rows,
            required_fields=[F_UNIQUE_KEY, F_ORDER_NO, F_ACCESSORY_FLAG, *product_fields],
            fallback_match_fields=(F_ORDER_NO,),
            allow_partial_fields=False,
            update_existing_fields={*ORDER_UPDATE_FIELDS, *product_fields},
        )
        writes["orders"][platform]["product_field_actions"] = {
            field: "validated_existing_no_field_changes" for field in product_fields
        }
        readback = client.readback_by_unique_key(table_id, {row[F_UNIQUE_KEY] for row in rows})
        writes["orders"][platform]["readback_count"] = len(readback)
        writes["orders"][platform]["missing_unique_keys"] = sorted(set(row[F_UNIQUE_KEY] for row in rows) - set(readback))[:50]

    if ad_rows:
        if not settings.shopops_ad_table_id:
            raise RuntimeError("Missing SHOPOPS_AD_TABLE_ID")
        created_ad_fields = []
        if ensure_missing_ad_fields:
            created_ad_fields = client.ensure_missing_fields_for_rows(settings.shopops_ad_table_id, ad_rows, AD_FIELD_TYPES)
        writes["ads"] = client.upsert_rows(
            table_id=settings.shopops_ad_table_id,
            rows=ad_rows,
            required_fields=[F_UNIQUE_KEY, F_PLATFORM, F_DATE],
            fallback_match_fields=(F_PLATFORM, F_DATE),
            allow_partial_fields=False,
        )
        writes["ads"]["created_missing_fields"] = created_ad_fields
        writes["ads"]["canonicalize_unique_keys"] = client.canonicalize_ad_unique_keys(settings.shopops_ad_table_id)
        readback = client.readback_by_unique_key(settings.shopops_ad_table_id, {row[F_UNIQUE_KEY] for row in ad_rows})
        writes["ads"]["readback_count"] = len(readback)
        writes["ads"]["missing_unique_keys"] = sorted(set(row[F_UNIQUE_KEY] for row in ad_rows) - set(readback))[:50]

    if influencer_rows:
        table_id = influencer_table_id
        douyin_excel_rows_present = any(row.get(F_PLATFORM) == "抖音" and row.get("作者账号") for row in influencer_rows)
        delete_existing_douyin = None
        if douyin_excel_rows_present:
            delete_existing_douyin = client.delete_platform_records(table_id, "抖音")
        dedupe_before = client.deduplicate_records(table_id, (F_PLATFORM, F_ORDER_NO))
        writes["influencer"] = client.upsert_rows(
            table_id=table_id,
            rows=influencer_rows,
            required_fields=[F_UNIQUE_KEY, F_ORDER_NO],
            fallback_match_fields=(F_PLATFORM, F_ORDER_NO),
            allow_partial_fields=False,
        )
        if delete_existing_douyin:
            writes["influencer"]["delete_existing_douyin"] = delete_existing_douyin
        writes["influencer"]["dedupe_before_import"] = dedupe_before
        writes["influencer"]["dedupe_after_import"] = client.deduplicate_records(table_id, (F_PLATFORM, F_ORDER_NO))
        readback = client.readback_by_unique_key(table_id, {row[F_UNIQUE_KEY] for row in influencer_rows})
        writes["influencer"]["readback_count"] = len(readback)
        writes["influencer"]["missing_unique_keys"] = sorted(set(row[F_UNIQUE_KEY] for row in influencer_rows) - set(readback))[:50]

    summary["field_preflight"] = field_preflight
    summary["writes"] = writes
    missing = []
    for section in ("orders", "ads", "influencer"):
        value = writes.get(section)
        if isinstance(value, dict):
            for item in value.values() if section == "orders" else [value]:
                if isinstance(item, dict):
                    missing.extend(item.get("missing_unique_keys") or [])
    summary["status"] = "success" if not missing else "readback_mismatch"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    summary["evidence_path"] = str(evidence.resolve())
    return summary


def normalize_platform(value: Any) -> str:
    text = clean_text(value).lower()
    if "抖音" in text or "douyin" in text or "doudian" in text:
        return "抖音"
    if "拼多多" in text or "pdd" in text or "pinduoduo" in text:
        return "拼多多"
    if "视频号" in text or "微信" in text or "wechat" in text:
        return "视频号"
    if "天猫" in text or "tmall" in text:
        return "天猫"
    return clean_text(value)


ORDER_CREATED_AT_ALIASES: dict[str, tuple[str, ...]] = {
    "天猫": ("订单创建时间", "创建时间", "下单时间", "订单下单时间", "订单付款时间", "支付时间"),
    "抖音": ("订单提交时间", "下单时间", "订单下单时间", "创建时间", "支付完成时间", "付款时间", "支付时间"),
    "拼多多": ("订单成交时间", "下单时间", "订单创建时间", "创建时间", "支付时间"),
    "视频号": ("订单下单时间", "下单时间", "订单创建时间", "创建时间", "支付时间"),
}


def order_created_at(platform: str, row: dict[str, Any], order_no: str) -> str:
    value = normalize_datetime(first_present(row, *ORDER_CREATED_AT_ALIASES.get(platform, ("创建时间", "下单时间"))))
    if value:
        return value
    if platform == "拼多多":
        return pdd_date_from_order_no(order_no)
    return ""


NON_SOLD_STATUS_KEYWORDS = ("退款", "交易关闭", "已关闭", "已取消", "订单关闭", "待付款", "等待买家付款", "未付款")
NON_SOLD_PRODUCT_KEYWORDS = ("补收差价", "差价专用", "购买前须联系客服", "联系客服确认")
ACCESSORY_PRODUCT_KEYWORDS = ("配件",)


def actual_sold_quantity(
    *,
    quantity: float | None,
    product: str,
    unit_price: float | None,
    refund_amount: float | None,
    trade_status: str,
    fulfill_status: str,
) -> float | None:
    if refund_amount and refund_amount > 0:
        return 0
    text = f"{trade_status}/{fulfill_status}".replace("无售后或售后取消", "")
    if any(keyword in text for keyword in NON_SOLD_STATUS_KEYWORDS):
        return 0
    if unit_price == 0 or any(keyword in product for keyword in NON_SOLD_PRODUCT_KEYWORDS) or is_accessory_product(product):
        return 0
    return quantity


def is_accessory_product(product: str) -> bool:
    return any(keyword in product for keyword in ACCESSORY_PRODUCT_KEYWORDS)


def pdd_date_from_order_no(order_no: str) -> str:
    prefix = clean_text(order_no).split("-", 1)[0]
    if len(prefix) != 6 or not prefix.isdigit():
        return ""
    month = int(prefix[2:4])
    day = int(prefix[4:6])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"20{prefix[:2]}-{month:02d}-{day:02d}"


def order_unique_key(platform: str, order_no: str) -> str:
    return f"{PLATFORM_CODES[platform]}_{clean_text(order_no)}"


def ad_unique_key(platform: str, date_text: str) -> str:
    return f"ads_{PLATFORM_CODES[platform]}_{date_text}"


def clean_header(value: Any) -> str:
    text = "" if value is None or is_nan(value) else str(value).strip()
    return re.sub(r"[\ue000-\uf8ff].*$", "", text).strip()


def clean_text(value: Any) -> str:
    if value in (None, "-", "--") or is_nan(value):
        return ""
    return str(value).strip().strip("\t").strip("'")


def scalar_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") if isinstance(item, dict) else item) for item in value).strip()
    return clean_text(value)


def field_value_equal(left: Any, right: Any) -> bool:
    if left in (None, "") and right in (None, ""):
        return True
    left_number = number_value(left)
    right_number = number_value(right)
    if left_number is not None and right_number is not None:
        return abs(left_number - right_number) < 0.000001
    return scalar_text(left) == scalar_text(right)


def missing_row_fields(existing_fields: set[str], rows: list[dict[str, Any]], required_fields: list[str]) -> list[str]:
    used_fields = {
        key
        for row in rows
        for key, value in row.items()
        if value not in (None, "")
    }
    return sorted(({*required_fields, *used_fields} - existing_fields))


def first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "") and not is_nan(row[key]):
            return row[key]
    return None


def number_value(value: Any) -> float | None:
    text = clean_text(value).replace(",", "").replace("元", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text), 6)
    except ValueError:
        return None


def sum_numbers(rows: list[dict[str, Any]], *keys: str) -> float:
    total = 0.0
    for row in rows:
        for key in keys:
            value = number_value(row.get(key))
            if value is not None:
                total += value
                break
    return round(total, 6)


def first_number(rows: list[dict[str, Any]], *keys: str) -> float | None:
    for row in rows:
        for key in keys:
            value = number_value(row.get(key))
            if value is not None:
                return value
    return None


def ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), 6)


def refund_from_status(explicit_refund: float | None, paid_amount: float | None, status: str) -> float:
    if explicit_refund is not None:
        return explicit_refund
    return paid_amount or 0 if "退款成功" in status else 0


def normalize_datetime(value: Any) -> str:
    text = clean_text(value).replace("/", "-")
    if not text:
        return ""
    for candidate in (text, text[:19], text[:16], text[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(candidate, fmt)
                return parsed.strftime("%Y-%m-%d" if fmt == "%Y-%m-%d" else "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
    return text


def normalize_date(value: Any) -> str:
    text = normalize_datetime(value)
    return text[:10] if text else ""


def redact_row(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if any(part in str(key) for part in SENSITIVE_KEY_PARTS):
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


def join_unique(left: Any, right: Any, separator: str = "; ") -> str:
    values: list[str] = []
    for value in (clean_text(left), clean_text(right)):
        if not value:
            continue
        for part in value.split(separator):
            item = part.strip()
            if item and item not in values:
                values.append(item)
    return separator.join(values)


def is_nan(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Import one ShopOps daily folder into existing Feishu Bitable tables.")
    parser.add_argument("--batch-dir", default=r"D:\lyh\ShopOps\0608", help="Daily folder such as D:\\lyh\\ShopOps\\0608.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate locally without writing Feishu.")
    parser.add_argument("--evidence", default="", help="Evidence JSON path.")
    parser.add_argument("--platform", action="append", choices=PLATFORMS, help="Only import one platform; repeat for multiple platforms.")
    parser.add_argument("--kind", action="append", choices=("orders", "ads", "influencer"), help="Only import one data kind; repeat for multiple kinds.")
    parser.add_argument("--date", action="append", help="Only import one normalized date (YYYY-MM-DD); repeat for multiple dates.")
    parser.add_argument("--ensure-missing-ad-fields", action="store_true", help="Create missing Feishu ad table fields that are present in imported rows.")
    args = parser.parse_args()

    batch_dir = Path(args.batch_dir)
    date_dir = batch_dir.name
    evidence = Path(args.evidence) if args.evidence else Path("docs/live-evidence") / f"daily-import-{date_dir}.json"
    summary = run_import(
        batch_dir=batch_dir,
        dry_run=args.dry_run,
        evidence=evidence,
        platforms=set(args.platform or []),
        kinds=set(args.kind or []),
        dates=set(args.date or []),
        ensure_missing_ad_fields=args.ensure_missing_ad_fields,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if summary["status"] in {"success", "dry_run"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
