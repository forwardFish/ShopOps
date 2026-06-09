from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

from shopops.collectors.jushuitan_order_api import (
    find_first_list,
    first_value,
    jushuitan_public_params,
)
from shopops.config import Settings
from shopops.models import dt


JsonTransport = Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


@dataclass
class InfluencerCommissionCollectResult:
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


class JushuitanInfluencerCommissionCollector:
    def __init__(
        self,
        settings: Settings,
        transport: JsonTransport | None = None,
        page_size: int | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.page_size = page_size or settings.jushuitan_page_size

    def fetch_today(self) -> InfluencerCommissionCollectResult:
        fetched_at = datetime.now()
        start_at = fetched_at.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            missing = self._missing_credentials()
            if missing and not self.settings.use_mock_collectors:
                return self._failure(fetched_at, "jushuitan_credentials_missing", missing)

            if missing and self.transport is None:
                raw_rows = self._mock_rows(fetched_at)
            else:
                raw_rows = self._fetch_rows(start_at, fetched_at)

            rows = [self._normalize_row(row, fetched_at) for row in raw_rows]
            return InfluencerCommissionCollectResult(
                success=True,
                source="jushuitan",
                shop_id=self.settings.jushuitan_douyin_shop_id or self.settings.shop_id,
                shop_name=self.settings.shop_name,
                fetched_at=fetched_at,
                rows=rows,
                row_count=len(rows),
                total_estimated_commission=round(sum(float(row.get("预估佣金") or 0) for row in rows), 2),
                total_settled_commission=round(sum(float(row.get("结算佣金") or 0) for row in rows), 2),
                raw={
                    "provider": "jushuitan",
                    "method": self.settings.jushuitan_influencer_query_method,
                    "platform": "doudian",
                    "mock": bool(missing and self.transport is None),
                    "page_size": self.page_size,
                },
            )
        except Exception as exc:
            return self._failure(fetched_at, "jushuitan_influencer_api_failed", str(exc))

    def _missing_credentials(self) -> str | None:
        if not all([self.settings.jushuitan_partner_id, self.settings.jushuitan_partner_key, self.settings.jushuitan_token]):
            return "Jushuitan partner id, partner key, or token is missing"
        return None

    def _fetch_rows(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        page_index = 1
        all_rows: list[dict[str, Any]] = []
        while True:
            body = self._request_body(start_at, end_at, page_index)
            params = jushuitan_public_params(
                partner_id=self.settings.jushuitan_partner_id,
                partner_key=self.settings.jushuitan_partner_key,
                token=self.settings.jushuitan_token,
                method=self.settings.jushuitan_influencer_query_method,
                ts=int(end_at.timestamp()),
            )
            payload = self._request("POST_JSON", self.settings.jushuitan_api_url, params, body)
            self._raise_jushuitan_error(payload)
            rows = extract_influencer_commission_rows(payload)
            all_rows.extend(rows)
            if len(rows) < self.page_size:
                return all_rows
            page_index += 1

    def _request_body(self, start_at: datetime, end_at: datetime, page_index: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "page_index": page_index,
            "page_size": self.page_size,
            "modified_begin": dt(start_at),
            "modified_end": dt(end_at),
            "start_time": dt(start_at),
            "end_time": dt(end_at),
        }
        if self.settings.jushuitan_douyin_shop_id:
            body["shop_id"] = self.settings.jushuitan_douyin_shop_id
        return body

    def _request(self, method: str, url: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(method, url, params, body)
        if method != "POST_JSON":
            raise ValueError(f"Unsupported Jushuitan request method: {method}")
        response = requests.post(url, params=params, json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Jushuitan API response is not a JSON object")
        return data

    def _normalize_row(self, raw: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        shop_id = str(first_value(raw, "shop_id", "shopid") or self.settings.jushuitan_douyin_shop_id or self.settings.shop_id)
        order_id = str(first_value(raw, "order_id", "o_id", "so_id", "shop_order_id", "order_no") or "")
        influencer_id = str(first_value(raw, "influencer_id", "kol_id", "author_id", "author_buyin_id", "达人ID") or "")
        influencer_name = str(first_value(raw, "influencer_name", "kol_name", "author_name", "nickname", "达人昵称") or "")
        unique_tail = order_id or f"{influencer_id}_{dt(fetched_at)}"
        return {
            "unique_key": f"douyin_influencer_{shop_id}_{unique_tail}",
            "平台": "抖音",
            "数据来源": "聚水潭",
            "店铺ID": shop_id,
            "店铺名称": str(first_value(raw, "shop_name", "shopname") or self.settings.shop_name),
            "采集时间": dt(fetched_at),
            "订单号": order_id,
            "下单时间": first_value(raw, "order_time", "created", "created_at", "pay_time"),
            "达人ID": influencer_id,
            "达人昵称": influencer_name,
            "内容类型": first_value(raw, "content_type", "media_type", "order_source", "room_type"),
            "直播间/视频ID": first_value(raw, "room_id", "live_id", "video_id", "item_id"),
            "商品ID": first_value(raw, "product_id", "goods_id", "item_id", "sku_id"),
            "商品名称": first_value(raw, "product_name", "goods_name", "item_name", "sku_name"),
            "支付金额": normalize_money(raw, "pay_amount", "paid_amount", "order_amount", "payment", "total_amount"),
            "佣金率": normalize_rate(raw),
            "预估佣金": normalize_money(raw, "estimated_commission", "estimate_commission", "estimated_total_commission", "commission", "预估佣金"),
            "结算佣金": normalize_money(raw, "settled_commission", "settle_commission", "real_commission", "final_commission", "结算佣金"),
            "技术服务费": normalize_money(raw, "tech_service_fee", "estimated_tech_service_fee", "service_fee"),
            "结算状态": first_value(raw, "settle_status", "settlement_status", "commission_status", "status"),
            "原始数据": raw,
        }

    def _mock_rows(self, fetched_at: datetime) -> list[dict[str, Any]]:
        created = dt(fetched_at.replace(hour=10, minute=0, second=0, microsecond=0))
        return [
            {
                "order_id": "dy_mock_10001",
                "shop_id": self.settings.jushuitan_douyin_shop_id or self.settings.shop_id,
                "shop_name": self.settings.shop_name,
                "order_time": created,
                "author_id": "kol_001",
                "author_name": "抖音达人样例",
                "content_type": "live",
                "room_id": "room_001",
                "product_id": "goods_001",
                "product_name": "样例商品",
                "pay_amount": 299.0,
                "commission_rate": 0.1,
                "estimated_commission": 29.9,
                "settled_commission": 0,
                "tech_service_fee": 1.5,
                "settle_status": "pending",
            }
        ]

    def _failure(self, fetched_at: datetime, code: str, message: str) -> InfluencerCommissionCollectResult:
        return InfluencerCommissionCollectResult(
            success=False,
            source="jushuitan",
            shop_id=self.settings.jushuitan_douyin_shop_id or self.settings.shop_id,
            shop_name=self.settings.shop_name,
            fetched_at=fetched_at,
            row_count=None,
            total_estimated_commission=None,
            total_settled_commission=None,
            error_code=code,
            error_message=message,
            raw=None,
        )

    @staticmethod
    def _raise_jushuitan_error(payload: dict[str, Any]) -> None:
        code = payload.get("code")
        if code not in (None, 0, "0"):
            raise ValueError(f"{code}: {payload.get('msg') or payload.get('message')}")
        if payload.get("issuccess") is False:
            raise ValueError(str(payload.get("msg") or payload.get("message") or payload))


def extract_influencer_commission_rows(payload: Any) -> list[dict[str, Any]]:
    rows = find_first_list(payload, ("influencers", "commissions", "orders", "datas", "data", "items", "list", "rows"))
    return [row for row in (rows or []) if isinstance(row, dict)]


def normalize_money(raw: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = raw.get(key)
        if value in (None, ""):
            continue
        number = float(value)
        if key.endswith("_cent") or key.endswith("_fen") or key in {"estimated_total_commission", "estimated_tech_service_fee"}:
            number = number / 100
        return round(number, 2)
    return 0.0


def normalize_rate(raw: dict[str, Any]) -> float | None:
    value = first_value(raw, "commission_rate", "rate", "佣金率")
    if value in (None, ""):
        return None
    number = float(str(value).replace("%", ""))
    return round(number / 100, 4) if number > 1 else round(number, 4)
