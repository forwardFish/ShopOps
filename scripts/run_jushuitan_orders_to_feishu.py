from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.collectors.jushuitan_order_api import JushuitanOrderApiCollector, first_value
from shopops.config import Settings, load_settings
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


PLATFORMS = {
    "tmall": {
        "display": "\u5929\u732b",
        "shop_env": "JUSHUITAN_SHOP_ID_TMALL",
        "platform_code": "taobao",
    },
    "douyin": {
        "display": "\u6296\u97f3",
        "shop_env": "JUSHUITAN_SHOP_ID_DOUYIN",
        "platform_code": "doudian",
    },
    "wechat_channels": {
        "display": "\u89c6\u9891\u53f7",
        "shop_env": "JUSHUITAN_SHOP_ID_WECHAT_CHANNELS",
        "platform_code": "wechat_channels",
    },
    "pinduoduo": {
        "display": "\u62fc\u591a\u591a",
        "shop_env": "JUSHUITAN_SHOP_ID_PINDUODUO",
        "platform_code": "pinduoduo",
    },
}

TEXT_FIELD = 1
NUMBER_FIELD = 2

F_UNIQUE_KEY = "unique_key"
F_PLATFORM = "\u5e73\u53f0"
F_DATA_SOURCE = "\u6570\u636e\u6765\u6e90"
F_SHOP_ID = "\u5e97\u94faID"
F_SHOP_NAME = "\u5e97\u94fa\u540d\u79f0"
F_FETCHED_AT = "\u91c7\u96c6\u65f6\u95f4"
F_ORDER_NO = "\u8ba2\u5355\u53f7"
F_CREATED_AT = "\u521b\u5efa\u65f6\u95f4"
F_BUYER_NICK = "\u4e70\u5bb6\u6635\u79f0"
F_PRODUCT = "\u5546\u54c1\u540d\u79f0"
F_UNIT_PRICE = "\u5355\u4ef7"
F_QUANTITY = "\u6570\u91cf"
F_FULFILL_STATUS = "\u5c65\u7ea6/\u552e\u540e\u72b6\u6001"
F_TRADE_STATUS = "\u4ea4\u6613\u72b6\u6001"
F_PAID_AMOUNT = "\u5b9e\u6536\u6b3e"
F_OPERATION = "\u64cd\u4f5c\u4fe1\u606f"
F_RAW = "\u539f\u59cb\u6570\u636e"

ORDER_FIELDS = [
    (F_UNIQUE_KEY, TEXT_FIELD),
    (F_PLATFORM, TEXT_FIELD),
    (F_DATA_SOURCE, TEXT_FIELD),
    (F_SHOP_ID, TEXT_FIELD),
    (F_SHOP_NAME, TEXT_FIELD),
    (F_FETCHED_AT, TEXT_FIELD),
    (F_ORDER_NO, TEXT_FIELD),
    (F_CREATED_AT, TEXT_FIELD),
    (F_BUYER_NICK, TEXT_FIELD),
    (F_PRODUCT, TEXT_FIELD),
    (F_UNIT_PRICE, NUMBER_FIELD),
    (F_QUANTITY, NUMBER_FIELD),
    (F_FULFILL_STATUS, TEXT_FIELD),
    (F_TRADE_STATUS, TEXT_FIELD),
    (F_PAID_AMOUNT, NUMBER_FIELD),
    (F_OPERATION, TEXT_FIELD),
    (F_RAW, TEXT_FIELD),
]

SENSITIVE_KEY_PARTS = (
    "phone",
    "mobile",
    "tel",
    "address",
    "addr",
    "receiver",
    "consignee",
    "\u624b\u673a",
    "\u7535\u8bdd",
    "\u5730\u5740",
    "\u6536\u4ef6",
    "\u6536\u8d27",
)


def missing_runtime_inputs(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.jushuitan_partner_id:
        missing.append("JUSHUITAN_PARTNER_ID")
    if not settings.jushuitan_partner_key:
        missing.append("JUSHUITAN_PARTNER_KEY")
    if not settings.jushuitan_token:
        missing.append("JUSHUITAN_TOKEN")
    if not settings.feishu_app_id:
        missing.append("FEISHU_APP_ID")
    if not settings.feishu_app_secret:
        missing.append("FEISHU_APP_SECRET")
    if not settings.shopops_data_center_app_token:
        missing.append("SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN")
    if not settings.shopops_order_table_id:
        missing.append("SHOPOPS_ORDER_TABLE_ID")
    for config in PLATFORMS.values():
        if not os.getenv(config["shop_env"], "").strip():
            missing.append(config["shop_env"])
    return missing


def settings_for_platform(settings: Settings, platform_key: str) -> Settings:
    config = PLATFORMS[platform_key]
    shop_id = os.getenv(config["shop_env"], "").strip()
    return replace(
        settings,
        order_source="jushuitan",
        use_mock_collectors=False,
        shop_platform=config["platform_code"],
        shop_id=shop_id,
        shop_name=config["display"],
        jushuitan_shop_ids=shop_id,
    )


class FeishuOrderWriter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.app_token = settings.shopops_data_center_app_token
        self.table_id = settings.shopops_order_table_id

    def ensure_fields(self) -> None:
        existing = self._field_names()
        for field_name, field_type in ORDER_FIELDS:
            if field_name in existing:
                continue
            self._request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
                {"field_name": field_name, "type": field_type},
                allow_duplicate=True,
            )
            existing.add(field_name)

    def write_orders(self, rows: list[dict[str, Any]]) -> int:
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

    def _field_names(self) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
                params=params,
            )
            for item in data.get("items", []) or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def _existing_record_ids(self) -> dict[str, str]:
        ids: dict[str, str] = {}
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
                params=params,
            )
            for item in data.get("items", []) or []:
                fields = item.get("fields") or {}
                unique_key = fields.get(F_UNIQUE_KEY)
                if unique_key:
                    ids[str(unique_key)] = str(item.get("record_id"))
            if not data.get("has_more"):
                return ids
            page_token = data.get("page_token")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_duplicate: bool = False,
    ) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{FEISHU_BASE_URL}{path}",
            headers=self.client.headers(),
            json=payload,
            params=params,
            timeout=30,
        )
        body = response.json()
        if allow_duplicate and body.get("code") == 1254014:
            return {}
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}


def feishu_order_fields(platform_display: str, order: dict[str, Any]) -> dict[str, Any]:
    raw = order.get("raw") if isinstance(order.get("raw"), dict) else {}
    product_names, quantity, unit_price = product_summary(raw)
    paid_amount = float(order.get("paid_amount") or 0)
    if unit_price is None and quantity:
        unit_price = round(paid_amount / quantity, 2)
    return {
        F_UNIQUE_KEY: str(order.get("unique_key") or ""),
        F_PLATFORM: platform_display,
        F_DATA_SOURCE: "\u805a\u6c34\u6f6d\u771f\u5b9e\u63a5\u53e3",
        F_SHOP_ID: str(order.get("shop_id") or ""),
        F_SHOP_NAME: str(order.get("shop_name") or platform_display),
        F_FETCHED_AT: str(order.get("fetched_at") or ""),
        F_ORDER_NO: str(order.get("order_id") or ""),
        F_CREATED_AT: str(order.get("created_at") or ""),
        F_BUYER_NICK: str(first_value(raw, "buyer_nick", "buyer_account", "buyer_id") or ""),
        F_PRODUCT: product_names,
        F_UNIT_PRICE: unit_price,
        F_QUANTITY: quantity,
        F_FULFILL_STATUS: str(first_value(raw, "shipping_status", "send_status", "logistics_status") or ""),
        F_TRADE_STATUS: str(order.get("order_status") or ""),
        F_PAID_AMOUNT: paid_amount,
        F_OPERATION: "\u805a\u6c34\u6f6dAPI\u771f\u5b9e\u62c9\u53d6",
        F_RAW: json.dumps(redact_sensitive(raw), ensure_ascii=False, sort_keys=True),
    }


def clean_feishu_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}


def chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def product_summary(raw: dict[str, Any]) -> tuple[str, int | None, float | None]:
    items = first_list(raw, ("items", "order_items", "products", "skus", "details", "drp_co_id_froms"))
    if not items:
        name = first_value(raw, "product_name", "item_name", "sku_name", "goods_name")
        qty = as_int(first_value(raw, "qty", "quantity", "num"))
        price = as_float(first_value(raw, "price", "unit_price", "sale_price"))
        return str(name or ""), qty, price
    names: list[str] = []
    total_qty = 0
    first_price: float | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        name = first_value(item, "name", "product_name", "item_name", "sku_name", "goods_name")
        if name:
            names.append(str(name))
        qty = as_int(first_value(item, "qty", "quantity", "num")) or 0
        total_qty += qty
        if first_price is None:
            first_price = as_float(first_value(item, "price", "unit_price", "sale_price"))
    return "; ".join(names), total_qty or None, first_price


def first_list(payload: dict[str, Any], keys: tuple[str, ...]) -> list[Any] | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return round(float(value), 2)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def main() -> int:
    settings = load_settings()
    missing = missing_runtime_inputs(settings)
    if missing:
        print(json.dumps({"status": "missing_inputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    all_rows: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    for platform_key, config in PLATFORMS.items():
        platform_settings = settings_for_platform(settings, platform_key)
        result = JushuitanOrderApiCollector(platform_settings).fetch_today()
        results[config["display"]] = {
            "success": result.success,
            "shop_id": platform_settings.shop_id,
            "order_count": result.order_count,
            "total_amount": result.total_amount,
            "error_code": result.error_code,
            "error_message": result.error_message,
        }
        if result.success and result.orders:
            all_rows.extend(feishu_order_fields(config["display"], order) for order in result.orders)

    failed = {platform: item for platform, item in results.items() if not item["success"]}
    if failed:
        print(json.dumps({"status": "jushuitan_failed", "platforms": results}, ensure_ascii=False, indent=2))
        return 3

    writer = FeishuOrderWriter(settings)
    writer.ensure_fields()
    saved_count = writer.write_orders(all_rows)
    print(
        json.dumps(
            {
                "status": "success",
                "platforms": results,
                "saved_count": saved_count,
                "feishu_base_url": f"https://feishu.cn/base/{settings.shopops_data_center_app_token}",
                "order_table_id": settings.shopops_order_table_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
