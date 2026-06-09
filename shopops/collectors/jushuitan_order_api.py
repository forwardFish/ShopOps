from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests

from shopops.collectors.base import OrderCollector
from shopops.config import Settings
from shopops.models import OrderCollectResult, dt


JsonTransport = Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


class JushuitanOrderApiCollector(OrderCollector):
    def __init__(
        self,
        settings: Settings,
        transport: JsonTransport | None = None,
        page_size: int | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.page_size = page_size or settings.jushuitan_page_size

    def fetch_today(self) -> OrderCollectResult:
        fetched_at = datetime.now()
        start_at = fetched_at.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            missing = self._missing_credentials()
            if missing and not self.settings.use_mock_collectors:
                return self._failure(fetched_at, "jushuitan_credentials_missing", missing)

            if missing and self.transport is None:
                raw_orders = self._mock_orders(fetched_at)
            else:
                raw_orders = self._fetch_orders(start_at, fetched_at)

            paid_orders = [order for order in raw_orders if not is_unpaid(order)]
            orders = [self._normalize_order(order, fetched_at) for order in paid_orders]
            total_amount = round(sum(float(order.get("paid_amount") or 0) for order in orders), 2)
            return OrderCollectResult(
                success=True,
                source="jushuitan",
                shop_id=self.settings.shop_id,
                shop_name=self.settings.shop_name,
                order_count=len(orders),
                paid_order_count=len(orders),
                total_amount=total_amount,
                fetched_at=fetched_at,
                raw={
                    "provider": "jushuitan",
                    "method": self.settings.jushuitan_order_query_method,
                    "platform": self.settings.shop_platform,
                    "mock": bool(missing and self.transport is None),
                    "page_size": self.page_size,
                },
                orders=orders,
            )
        except Exception as exc:
            return self._failure(fetched_at, "jushuitan_api_failed", str(exc))

    def _missing_credentials(self) -> str | None:
        if not all([self.settings.jushuitan_partner_id, self.settings.jushuitan_partner_key, self.settings.jushuitan_token]):
            return "Jushuitan partner id, partner key, or token is missing"
        return None

    def _fetch_orders(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        page_index = 1
        all_orders: list[dict[str, Any]] = []
        while True:
            body = self._request_body(start_at, end_at, page_index)
            params = jushuitan_public_params(
                partner_id=self.settings.jushuitan_partner_id,
                partner_key=self.settings.jushuitan_partner_key,
                token=self.settings.jushuitan_token,
                method=self.settings.jushuitan_order_query_method,
                ts=int(end_at.timestamp()),
            )
            payload = self._request("POST_JSON", self.settings.jushuitan_api_url, params, body)
            self._raise_jushuitan_error(payload)
            orders = extract_jushuitan_orders(payload)
            all_orders.extend(orders)
            if len(orders) < self.page_size:
                return all_orders
            page_index += 1

    def _request_body(self, start_at: datetime, end_at: datetime, page_index: int) -> dict[str, Any]:
        body: dict[str, Any] = {
            "page_index": page_index,
            "page_size": self.page_size,
            "modified_begin": dt(start_at),
            "modified_end": dt(end_at),
        }
        shop_ids = [item.strip() for item in self.settings.jushuitan_shop_ids.split(",") if item.strip()]
        if len(shop_ids) == 1:
            body["shop_id"] = shop_ids[0]
        elif shop_ids:
            body["shop_ids"] = shop_ids
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

    def _normalize_order(self, raw_order: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        order_id = str(first_value(raw_order, "o_id", "so_id", "order_id", "shop_order_id", "outer_so_id") or "unknown")
        shop_id = str(first_value(raw_order, "shop_id", "shopid") or self.settings.shop_id)
        shop_name = str(first_value(raw_order, "shop_name", "shopname") or self.settings.shop_name)
        return {
            "unique_key": f"jushuitan_{shop_id}_{order_id}",
            "platform": self.settings.shop_platform,
            "provider": "jushuitan",
            "shop_id": shop_id,
            "shop_name": shop_name,
            "order_id": order_id,
            "order_status": first_value(raw_order, "status", "order_status", "so_status"),
            "created_at": first_value(raw_order, "order_date", "created", "created_at", "shop_order_date"),
            "paid_at": first_value(raw_order, "pay_date", "paid_at", "pay_time"),
            "paid_amount": normalize_amount(raw_order),
            "fetched_at": dt(fetched_at),
            "raw": raw_order,
        }

    def _mock_orders(self, fetched_at: datetime) -> list[dict[str, Any]]:
        created = dt(fetched_at.replace(hour=9, minute=0, second=0, microsecond=0))
        return [
            {
                "o_id": "jst_mock_10001",
                "shop_id": self.settings.shop_id,
                "shop_name": self.settings.shop_name,
                "status": "Sent",
                "order_date": created,
                "pay_date": created,
                "pay_amount": 188.5,
            }
        ]

    def _failure(self, fetched_at: datetime, code: str, message: str) -> OrderCollectResult:
        return OrderCollectResult(
            success=False,
            source="jushuitan",
            shop_id=self.settings.shop_id,
            shop_name=self.settings.shop_name,
            order_count=None,
            paid_order_count=None,
            total_amount=None,
            fetched_at=fetched_at,
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


def jushuitan_public_params(
    partner_id: str,
    partner_key: str,
    token: str,
    method: str,
    ts: int,
) -> dict[str, Any]:
    params = {
        "partnerid": partner_id,
        "token": token,
        "method": method,
        "ts": ts,
    }
    params["sign"] = jushuitan_md5_sign(params, partner_key)
    return params


def jushuitan_md5_sign(params: dict[str, Any], partner_key: str) -> str:
    method = params.get("method") or ""
    partner_id = params.get("partnerid") or ""
    token = params.get("token") or ""
    ts = params.get("ts") or ""
    return hashlib.md5(f"{method}{partner_id}token{token}ts{ts}{partner_key}".encode("utf-8")).hexdigest()


def extract_jushuitan_orders(payload: Any) -> list[dict[str, Any]]:
    found = find_first_list(payload, ("orders", "datas", "data", "items", "list"))
    return [order for order in (found or []) if isinstance(order, dict)]


def find_first_list(payload: Any, candidate_keys: tuple[str, ...]) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = find_first_list(value, candidate_keys)
            if nested is not None:
                return nested
    for value in payload.values():
        nested = find_first_list(value, candidate_keys)
        if nested is not None:
            return nested
    return None


def first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def normalize_amount(raw_order: dict[str, Any]) -> float:
    value = first_value(raw_order, "paid_amount", "pay_amount", "amount", "paid", "total_amount", "order_amount")
    if value is None:
        return 0.0
    return round(float(value), 2)


def is_unpaid(raw_order: dict[str, Any]) -> bool:
    status = first_value(raw_order, "status", "order_status", "so_status")
    return str(status) in {"WaitPay", "WAIT_BUYER_PAY", "unpaid", "0", "待付款"}
