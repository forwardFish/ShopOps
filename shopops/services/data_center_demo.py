from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import os
from pathlib import Path
from typing import Any

from shopops.config import Settings, load_settings
from shopops.storage.feishu_bootstrap import FeishuOpenApiClient, PlatformTableSpec, number_field, text_field
from shopops.storage.local_feishu import LocalFeishuBitableStorage


DATA_CENTER_NAME = "ShopOps \u5168\u5e73\u53f0\u6570\u636e\u4e2d\u5fc3"
AD_TABLE = "\u6295\u6d41\u6570\u636e\u8868"
ORDER_TABLE = "\u8ba2\u5355\u6570\u636e\u8868"
SUMMARY_TABLE = "\u5b9e\u65f6\u6c47\u603b\u770b\u677f"

PLATFORM_TMALL = "\u5929\u732b"
PLATFORM_DOUYIN = "\u6296\u97f3"
PLATFORM_PDD = "\u62fc\u591a\u591a"
PLATFORM_WECHAT_CHANNELS = "\u89c6\u9891\u53f7"
PLATFORMS = (PLATFORM_TMALL, PLATFORM_DOUYIN, PLATFORM_PDD, PLATFORM_WECHAT_CHANNELS)

F_UNIQUE_KEY = "unique_key"
F_STAT_DATE = "\u7edf\u8ba1\u65e5\u671f"
F_COLLECTED_AT = "\u91c7\u96c6\u65f6\u95f4"
F_PLATFORM = "\u5e73\u53f0"
F_TOTAL_ORDERS = "\u603b\u8ba2\u5355\u6570"
F_TOTAL_GMV = "\u603b\u6210\u4ea4\u91d1\u989d(\u5143)"
F_TOTAL_REFUND = "\u603b\u9000\u6b3e\u91d1\u989d(\u5143)"
F_NET_GMV = "\u51c0\u6210\u4ea4\u91d1\u989d(\u5143)"
F_AVG_ORDER_VALUE = "\u5ba2\u5355\u4ef7"
F_DATA_SOURCE = "\u6570\u636e\u6765\u6e90"
F_AD_COST = "\u63a8\u5e7f\u82b1\u8d39(\u5143)"
F_IMPRESSIONS = "\u5c55\u73b0\u91cf"
F_CLICKS = "\u70b9\u51fb\u91cf"
F_CTR = "\u70b9\u51fb\u7387"
F_CPC = "\u70b9\u51fb\u5355\u4ef7"
F_BACKEND_ROI = "\u5e73\u53f0\u663e\u793aROI"
F_TRUE_ROI = "\u5e73\u53f0\u771f\u5b9eROI"
F_TODAY_COST = "\u4eca\u65e5\u603b\u82b1\u8d39"
F_TODAY_GMV = "\u4eca\u65e5\u603b\u6210\u4ea4"
F_TODAY_ORDERS = "\u4eca\u65e5\u603b\u8ba2\u5355"
F_DIFF = "\u5dee\u503c"

SOURCE_JUSHUITAN_MOCK = "\u805a\u6c34\u6f6d\u6a21\u62df"
SOURCE_AD_BACKEND_MOCK = "\u6295\u6d41\u540e\u53f0\u6a21\u62df"
TOTAL_PLATFORM_NAME = "\u5168\u5e73\u53f0\u603b\u8ba1"


@dataclass(frozen=True)
class DataCenterWriteResult:
    mode: str
    app_token: str | None
    app_url: str | None
    table_ids: dict[str, str]
    saved_count: int
    local_path: str | None = None
    error: str | None = None


def demo_order_rows(today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    samples = {
        PLATFORM_TMALL: {"orders": 186, "gmv": 48260.0, "refund": 3210.0},
        PLATFORM_DOUYIN: {"orders": 143, "gmv": 39280.0, "refund": 1980.0},
        PLATFORM_PDD: {"orders": 228, "gmv": 31450.0, "refund": 2760.0},
        PLATFORM_WECHAT_CHANNELS: {"orders": 74, "gmv": 21360.0, "refund": 860.0},
    }
    rows: list[dict[str, Any]] = []
    stat_date = today.isoformat()
    for platform in PLATFORMS:
        item = samples[platform]
        net = round(item["gmv"] - item["refund"], 2)
        rows.append(
            {
                F_UNIQUE_KEY: f"order_{stat_date}_{platform}",
                F_STAT_DATE: stat_date,
                F_PLATFORM: platform,
                F_TOTAL_ORDERS: item["orders"],
                F_TOTAL_GMV: item["gmv"],
                F_TOTAL_REFUND: item["refund"],
                F_NET_GMV: net,
                F_AVG_ORDER_VALUE: round(net / item["orders"], 2),
                F_DATA_SOURCE: SOURCE_JUSHUITAN_MOCK,
            }
        )
    return rows


def demo_ad_rows(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    samples = {
        PLATFORM_TMALL: {"cost": 6280.0, "impressions": 268000, "clicks": 12680, "backend_roi": 6.7},
        PLATFORM_DOUYIN: {"cost": 7420.0, "impressions": 396000, "clicks": 18320, "backend_roi": 5.1},
        PLATFORM_PDD: {"cost": 5120.0, "impressions": 338000, "clicks": 21040, "backend_roi": 5.5},
        PLATFORM_WECHAT_CHANNELS: {"cost": 2860.0, "impressions": 128000, "clicks": 5940, "backend_roi": 7.0},
    }
    collected_at = now.strftime("%Y-%m-%d %H:%M:%S")
    minute_key = now.strftime("%Y%m%d%H%M")
    order_by_platform = {row[F_PLATFORM]: row for row in demo_order_rows(now.date())}
    rows: list[dict[str, Any]] = []
    for platform in PLATFORMS:
        item = samples[platform]
        clicks = item["clicks"]
        impressions = item["impressions"]
        cost = item["cost"]
        net = float(order_by_platform[platform][F_NET_GMV])
        rows.append(
            {
                F_UNIQUE_KEY: f"ad_{minute_key}_{platform}",
                F_COLLECTED_AT: collected_at,
                F_PLATFORM: platform,
                F_AD_COST: cost,
                F_IMPRESSIONS: impressions,
                F_CLICKS: clicks,
                F_CTR: round(clicks / impressions, 4),
                F_CPC: round(cost / clicks, 4),
                F_BACKEND_ROI: item["backend_roi"],
                F_TRUE_ROI: round(net / cost, 4),
                F_DATA_SOURCE: SOURCE_AD_BACKEND_MOCK,
            }
        )
    return rows


def demo_summary_rows(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now()
    stat_date = now.date().isoformat()
    order_by_platform = {row[F_PLATFORM]: row for row in demo_order_rows(now.date())}
    ad_by_platform = {row[F_PLATFORM]: row for row in demo_ad_rows(now)}
    rows: list[dict[str, Any]] = []
    total_cost = 0.0
    total_net = 0.0
    total_orders = 0
    for platform in PLATFORMS:
        order = order_by_platform[platform]
        ad = ad_by_platform[platform]
        cost = float(ad[F_AD_COST])
        net = float(order[F_NET_GMV])
        orders = int(order[F_TOTAL_ORDERS])
        real_roi = round(net / cost, 4)
        backend_roi = float(ad[F_BACKEND_ROI])
        rows.append(
            {
                F_UNIQUE_KEY: f"summary_{stat_date}_{platform}",
                F_PLATFORM: platform,
                F_TODAY_COST: cost,
                F_TODAY_GMV: net,
                F_TODAY_ORDERS: orders,
                F_TRUE_ROI: real_roi,
                F_BACKEND_ROI: backend_roi,
                F_DIFF: round(real_roi - backend_roi, 4),
                F_STAT_DATE: stat_date,
            }
        )
        total_cost += cost
        total_net += net
        total_orders += orders
    rows.append(
        {
            F_UNIQUE_KEY: f"summary_{stat_date}_{TOTAL_PLATFORM_NAME}",
            F_PLATFORM: TOTAL_PLATFORM_NAME,
            F_TODAY_COST: round(total_cost, 2),
            F_TODAY_GMV: round(total_net, 2),
            F_TODAY_ORDERS: total_orders,
            F_TRUE_ROI: round(total_net / total_cost, 4),
            F_BACKEND_ROI: None,
            F_DIFF: None,
            F_STAT_DATE: stat_date,
        }
    )
    return rows


def data_center_specs() -> list[PlatformTableSpec]:
    return [
        PlatformTableSpec(
            "SHOPOPS_TABLE_AD_DATA",
            "ad_data",
            AD_TABLE,
            [
                text_field(F_UNIQUE_KEY),
                text_field(F_COLLECTED_AT),
                text_field(F_PLATFORM),
                number_field(F_AD_COST),
                number_field(F_IMPRESSIONS),
                number_field(F_CLICKS),
                number_field(F_CTR),
                number_field(F_CPC),
                number_field(F_BACKEND_ROI),
                number_field(F_TRUE_ROI),
                text_field(F_DATA_SOURCE),
            ],
        ),
        PlatformTableSpec(
            "SHOPOPS_TABLE_ORDER_DATA",
            "order_data",
            ORDER_TABLE,
            [
                text_field(F_UNIQUE_KEY),
                text_field(F_STAT_DATE),
                text_field(F_PLATFORM),
                number_field(F_TOTAL_ORDERS),
                number_field(F_TOTAL_GMV),
                number_field(F_TOTAL_REFUND),
                number_field(F_NET_GMV),
                number_field(F_AVG_ORDER_VALUE),
                text_field(F_DATA_SOURCE),
            ],
        ),
        PlatformTableSpec(
            "SHOPOPS_TABLE_SUMMARY_DASHBOARD",
            "summary_dashboard",
            SUMMARY_TABLE,
            [
                text_field(F_UNIQUE_KEY),
                text_field(F_PLATFORM),
                number_field(F_TODAY_COST),
                number_field(F_TODAY_GMV),
                number_field(F_TODAY_ORDERS),
                number_field(F_TRUE_ROI),
                number_field(F_BACKEND_ROI),
                number_field(F_DIFF),
                text_field(F_STAT_DATE),
            ],
        ),
    ]


def demo_dataset(now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    now = now or datetime.now()
    return {
        "order_data": demo_order_rows(now.date()),
        "ad_data": demo_ad_rows(now),
        "summary_dashboard": demo_summary_rows(now),
    }


class FeishuDataCenterClient:
    def __init__(self, settings: Settings | None = None, base_name: str = DATA_CENTER_NAME) -> None:
        ensure_feishu_no_proxy()
        self.settings = settings or load_settings()
        self.base_name = base_name
        self.client = FeishuOpenApiClient(self.settings.feishu_app_id, self.settings.feishu_app_secret)

    def create_or_reuse_base(self) -> tuple[str, str | None]:
        app_token = self.settings.shopops_data_center_app_token or self.settings.feishu_app_token
        if app_token:
            return app_token, feishu_base_url(app_token)
        raise RuntimeError(
            "SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN is required; "
            "this script reuses an existing Feishu base and does not create a new one"
        )

    def ensure_tables(self, app_token: str) -> dict[str, str]:
        table_ids: dict[str, str] = {}
        if self.settings.shopops_ad_table_id:
            table_ids["ad_data"] = self.settings.shopops_ad_table_id
        if self.settings.shopops_order_table_id:
            table_ids["order_data"] = self.settings.shopops_order_table_id
        if self.settings.shopops_summary_table_id:
            table_ids["summary_dashboard"] = self.settings.shopops_summary_table_id
        if len(table_ids) == 3:
            return table_ids

        existing = self.client.list_tables(app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        for spec in data_center_specs():
            if spec.key in table_ids:
                continue
            table = self.client.ensure_table(app_token, spec, existing_by_name)
            table_id = table.get("table_id")
            if not table_id:
                raise RuntimeError(f"Feishu table {spec.name} did not return table_id")
            table_ids[spec.key] = str(table_id)
        self.ensure_table_fields(app_token, table_ids)
        return table_ids

    def ensure_table_fields(self, app_token: str, table_ids: dict[str, str]) -> None:
        specs = {spec.key: spec for spec in data_center_specs()}
        for table_key, table_id in table_ids.items():
            spec = specs[table_key]
            existing = self.list_field_names(app_token, table_id)
            for field in spec.fields:
                field_name = str(field.get("field_name"))
                if field_name in existing:
                    continue
                self.request(
                    "POST",
                    f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                    {"field_name": field_name, "type": field.get("type")},
                )
                existing.add(field_name)

    def list_field_names(self, app_token: str, table_id: str) -> set[str]:
        page_token = None
        names: set[str] = set()
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items", []) or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def upsert_record(self, app_token: str, table_id: str, fields: dict[str, Any]) -> int:
        unique_key = fields.get(F_UNIQUE_KEY)
        record_id = self.find_record_id(app_token, table_id, str(unique_key) if unique_key else "")
        payload = {"fields": fields}
        if record_id:
            self.request("PUT", f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}", payload)
        else:
            self.request("POST", f"/bitable/v1/apps/{app_token}/tables/{table_id}/records", payload)
        return 1

    def find_record_id(self, app_token: str, table_id: str, unique_key: str) -> str | None:
        if not unique_key:
            return None
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{app_token}/tables/{table_id}/records", params=params)
            for item in data.get("items", []) or []:
                fields = item.get("fields") or {}
                if fields.get(F_UNIQUE_KEY) == unique_key:
                    return str(item.get("record_id"))
            if not data.get("has_more"):
                return None
            page_token = data.get("page_token")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        import requests

        response = requests.request(
            method,
            f"{self.client.base_url}{path}",
            headers=self.client.headers(),
            json=payload,
            params=params,
            timeout=30,
        )
        body = response.json()
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def write_dataset(self, dataset: dict[str, list[dict[str, Any]]]) -> DataCenterWriteResult:
        app_token, app_url = self.create_or_reuse_base()
        table_ids = self.ensure_tables(app_token)
        saved = 0
        for table_key, rows in dataset.items():
            table_id = table_ids[table_key]
            for row in rows:
                saved += self.upsert_record(app_token, table_id, row)
        return DataCenterWriteResult("feishu", app_token, app_url, table_ids, saved)


def write_local_dataset(settings: Settings | None = None, now: datetime | None = None) -> DataCenterWriteResult:
    settings = settings or load_settings()
    storage = LocalFeishuBitableStorage(settings)
    dataset = demo_dataset(now)
    saved = 0
    for table_key, rows in dataset.items():
        for row in rows:
            saved += storage.upsert(table_key, row)
    return DataCenterWriteResult(
        mode="local",
        app_token=None,
        app_url=None,
        table_ids={spec.key: spec.name for spec in data_center_specs()},
        saved_count=saved,
        local_path=str(Path(settings.local_feishu_path).resolve()),
    )


def write_data_center(settings: Settings | None = None, now: datetime | None = None, allow_local_fallback: bool = True) -> DataCenterWriteResult:
    settings = settings or load_settings()
    dataset = demo_dataset(now)
    if settings.feishu_app_id and settings.feishu_app_secret:
        try:
            return FeishuDataCenterClient(settings).write_dataset(dataset)
        except Exception as exc:
            if not allow_local_fallback:
                raise
            local = write_local_dataset(settings, now)
            return DataCenterWriteResult(
                mode="local",
                app_token=None,
                app_url=None,
                table_ids=local.table_ids,
                saved_count=local.saved_count,
                local_path=local.local_path,
                error=str(exc),
            )
    return write_local_dataset(settings, now)


def feishu_base_url(app_token: str) -> str:
    return f"https://my.feishu.cn/base/{app_token}"


def ensure_feishu_no_proxy() -> None:
    for name in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(name, "")
        entries = [item.strip() for item in current.split(",") if item.strip()]
        if "open.feishu.cn" not in entries:
            entries.append("open.feishu.cn")
            os.environ[name] = ",".join(entries)
