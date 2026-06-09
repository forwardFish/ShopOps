from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

from shopops.collectors.platform_order_api import doudian_sign, first_value, find_first_list
from shopops.config import Settings
from shopops.models import dt


JsonTransport = Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


@dataclass
class DoudianAllianceCollectResult:
    success: bool
    source: str
    shop_id: str
    shop_name: str
    fetched_at: datetime
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int | None = 0
    total_estimated_commission: float | None = 0.0
    total_settled_commission: float | None = 0.0
    error_code: str | None = None
    error_message: str | None = None
    raw: Any | None = None


class DoudianAllianceOrderCollector:
    """Fetch Douyin Selected Alliance creator commission details from Doudian OpenAPI."""

    method = "alliance.getOrderList"
    path = "/alliance/getOrderList"

    def __init__(
        self,
        settings: Settings,
        order_ids: list[str] | None = None,
        transport: JsonTransport | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.order_ids = order_ids if order_ids is not None else parse_order_ids(settings.doudian_alliance_order_ids)
        self.transport = transport
        self.now = now or datetime.now

    def fetch(self) -> DoudianAllianceCollectResult:
        fetched_at = self.now()
        try:
            missing = self._missing_credentials()
            if missing and not self.settings.use_mock_collectors:
                return self._failure(fetched_at, "doudian_credentials_missing", missing)

            if missing and self.transport is None:
                raw_rows = self._mock_rows()
            else:
                if not self.order_ids:
                    return self._failure(fetched_at, "doudian_alliance_order_ids_missing", "DOUDIAN_ALLIANCE_ORDER_IDS or --order-ids is required")
                raw_rows = self._fetch_order_details(fetched_at)

            rows = [normalize_alliance_row(raw, fetched_at, self.settings) for raw in raw_rows]
            return DoudianAllianceCollectResult(
                success=True,
                source="doudian",
                shop_id=self.settings.shop_id,
                shop_name=self.settings.shop_name,
                fetched_at=fetched_at,
                rows=rows,
                row_count=len(rows),
                total_estimated_commission=round(sum(float(row.get("预估佣金") or 0) for row in rows), 2),
                total_settled_commission=round(sum(float(row.get("结算佣金") or 0) for row in rows), 2),
                raw={
                    "provider": "doudian",
                    "method": self.method,
                    "endpoint": self.path,
                    "order_ids": self.order_ids,
                    "mock": bool(missing and self.transport is None),
                },
            )
        except Exception as exc:
            return self._failure(fetched_at, "doudian_alliance_api_failed", str(exc))

    def _missing_credentials(self) -> str | None:
        if not all([self.settings.doudian_app_key, self.settings.doudian_app_secret, self.settings.doudian_access_token]):
            return "Doudian app key, app secret, or access token is missing"
        return None

    def _fetch_order_details(self, fetched_at: datetime) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        for chunk in chunked(self.order_ids, 5):
            body = {"order_ids": chunk}
            params = self._signed_params(body, fetched_at)
            payload = self._request("POST", f"{self.settings.doudian_api_url.rstrip('/')}{self.path}", params, body)
            raise_doudian_common_error(payload)
            all_rows.extend(extract_alliance_rows(payload))
        return all_rows

    def _signed_params(self, body: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        param_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        params: dict[str, Any] = {
            "method": self.method,
            "app_key": self.settings.doudian_app_key,
            "access_token": self.settings.doudian_access_token,
            "param_json": param_json,
            "timestamp": dt(fetched_at),
            "v": "2",
            "sign_method": self.settings.doudian_sign_method,
        }
        params["sign"] = doudian_sign(params, self.settings.doudian_app_secret, self.settings.doudian_sign_method)
        return params

    def _request(self, method: str, url: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(method, url, params, body)
        response = requests.post(url, params=params, json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Doudian API response is not a JSON object")
        return data

    def _mock_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "alliance_biz_type": "COMMON",
                "author_account": "抖音达人样例",
                "commission_rate": "300",
                "estimated_comission": "810",
                "order_id": "dy_alliance_mock_10001",
                "order_status": "支付成功",
                "phase_id": "1",
                "product_id": "3475285904548040556",
                "real_comission": "0",
                "shop_id": self.settings.shop_id,
                "short_id": "1068048",
                "total_pay_amount": "31000",
            }
        ]

    def _failure(self, fetched_at: datetime, code: str, message: str) -> DoudianAllianceCollectResult:
        return DoudianAllianceCollectResult(
            success=False,
            source="doudian",
            shop_id=self.settings.shop_id,
            shop_name=self.settings.shop_name,
            fetched_at=fetched_at,
            row_count=None,
            total_estimated_commission=None,
            total_settled_commission=None,
            error_code=code,
            error_message=message,
            raw=None,
        )


def parse_order_ids(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def extract_alliance_rows(payload: Any) -> list[dict[str, Any]]:
    rows = find_first_list(payload, ("datas", "data", "items", "list", "rows"))
    return [row for row in (rows or []) if isinstance(row, dict)]


def normalize_alliance_row(raw: dict[str, Any], fetched_at: datetime, settings: Settings) -> dict[str, Any]:
    shop_id = str(first_value(raw, "shop_id") or settings.shop_id)
    order_id = str(first_value(raw, "order_id", "shop_order_id", "id") or "")
    author_id = str(first_value(raw, "author_id", "short_id", "kol_id", "达人ID") or "")
    author_name = str(first_value(raw, "author_account", "author_name", "kol_name", "达人昵称") or "")
    return {
        "unique_key": f"douyin_influencer_{shop_id}_{order_id or author_id}",
        "平台": "抖音",
        "数据来源": "抖店开放平台",
        "店铺ID": shop_id,
        "店铺名称": settings.shop_name,
        "采集时间": dt(fetched_at),
        "订单号": order_id,
        "下单时间": first_value(raw, "order_time", "pay_time", "create_time", "create_time_str"),
        "达人ID": author_id,
        "达人昵称": author_name,
        "内容类型": first_value(raw, "alliance_biz_type", "content_type"),
        "直播间/视频ID": first_value(raw, "room_id", "live_id", "video_id", "phase_id"),
        "商品ID": first_value(raw, "product_id", "goods_id", "item_id"),
        "商品名称": first_value(raw, "product_name", "goods_name", "item_name"),
        "支付金额": cents_to_yuan(first_value(raw, "total_pay_amount", "pay_amount", "paid_amount", "payment")),
        "佣金率": normalize_doudian_rate(first_value(raw, "commission_rate", "rate")),
        "预估佣金": cents_to_yuan(first_value(raw, "estimated_comission", "estimated_commission", "estimate_commission")),
        "结算佣金": cents_to_yuan(first_value(raw, "real_comission", "real_commission", "settled_commission")),
        "技术服务费": cents_to_yuan(first_value(raw, "tech_service_fee", "service_fee")),
        "结算状态": first_value(raw, "settle_status", "settlement_status", "order_status", "status"),
        "原始数据": json.dumps(raw, ensure_ascii=False, sort_keys=True),
    }


def cents_to_yuan(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return round(float(value) / 100, 2)


def normalize_doudian_rate(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(str(value).replace("%", ""))
    if number > 100:
        return round(number / 10000, 4)
    if number > 1:
        return round(number / 100, 4)
    return round(number, 4)


def raise_doudian_common_error(payload: dict[str, Any]) -> None:
    code = payload.get("code")
    if code not in (None, 0, "0", 10000, "10000"):
        raise ValueError(f"{code}: {payload.get('msg') or payload.get('message') or payload.get('sub_msg')}")
    data = payload.get("data")
    if isinstance(data, dict):
        nested_code = data.get("code")
        if nested_code not in (None, 0, "0", 100000, "100000"):
            raise ValueError(f"{nested_code}: {data.get('code_msg') or data.get('msg')}")
