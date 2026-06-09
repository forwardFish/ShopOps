from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests

from shopops.collectors.base import OrderCollector
from shopops.collectors.jushuitan_order_api import (
    extract_jushuitan_orders,
    first_value,
    is_unpaid,
    normalize_amount,
)
from shopops.config import Settings
from shopops.models import OrderCollectResult, dt


JsonTransport = Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


class JushuitanQimenOrderListCollector(OrderCollector):
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
            if missing:
                return self._failure(fetched_at, "jushuitan_qimen_credentials_missing", ", ".join(missing))
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
                    "provider": "jushuitan_qimen",
                    "method": self.settings.jushuitan_qimen_order_list_method,
                    "platform": self.settings.shop_platform,
                    "page_size": self.page_size,
                },
                orders=orders,
            )
        except Exception as exc:
            return self._failure(fetched_at, "jushuitan_qimen_api_failed", str(exc))

    def _missing_credentials(self) -> list[str]:
        missing: list[str] = []
        if not self.settings.jushuitan_qimen_app_key:
            missing.append("JUSHUITAN_QIMEN_APP_KEY")
        if not self.settings.jushuitan_qimen_app_secret:
            missing.append("JUSHUITAN_QIMEN_APP_SECRET")
        if not self.settings.jushuitan_qimen_customer_id:
            missing.append("JUSHUITAN_QIMEN_CUSTOMER_ID")
        return missing

    def _fetch_orders(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        page_index = 1
        all_orders: list[dict[str, Any]] = []
        while True:
            body = qimen_order_list_body(self.settings.shop_id, start_at, end_at, page_index, self.page_size)
            params = qimen_public_params(
                app_key=self.settings.jushuitan_qimen_app_key,
                app_secret=self.settings.jushuitan_qimen_app_secret,
                method=self.settings.jushuitan_qimen_order_list_method,
                customer_id=self.settings.jushuitan_qimen_customer_id,
                target_app_key=self.settings.jushuitan_qimen_target_app_key,
                session=self.settings.jushuitan_qimen_session,
                timestamp=dt(end_at),
                body=body,
            )
            payload = self._request("POST_FORM", self.settings.jushuitan_qimen_url, params, None)
            raise_qimen_error(payload)
            orders = extract_jushuitan_orders(payload)
            all_orders.extend(orders)
            if not has_next_page(payload, orders, self.page_size):
                return all_orders
            page_index += 1

    def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(method, url, params, body)
        if method != "POST_FORM":
            raise ValueError(f"Unsupported Qimen request method: {method}")
        response = requests.post(url, data=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Qimen API response is not a JSON object")
        return data

    def _normalize_order(self, raw_order: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        order_id = str(first_value(raw_order, "o_id", "so_id", "order_id", "shop_order_id", "outer_so_id") or "unknown")
        shop_id = str(first_value(raw_order, "shop_id", "shopid") or self.settings.shop_id)
        shop_name = str(first_value(raw_order, "shop_name", "shopname") or self.settings.shop_name)
        return {
            "unique_key": f"jushuitan_qimen_{shop_id}_{order_id}",
            "platform": self.settings.shop_platform,
            "provider": "jushuitan_qimen",
            "shop_id": shop_id,
            "shop_name": shop_name,
            "order_id": order_id,
            "order_status": first_value(raw_order, "shop_status", "status", "order_status", "so_status"),
            "created_at": first_value(raw_order, "order_date", "created", "created_at", "shop_order_date"),
            "paid_at": first_value(raw_order, "pay_date", "paid_at", "pay_time"),
            "paid_amount": normalize_amount(raw_order),
            "fetched_at": dt(fetched_at),
            "raw": raw_order,
        }

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


def qimen_order_list_body(shop_id: str, start_at: datetime, end_at: datetime, page_index: int, page_size: int) -> dict[str, Any]:
    return {
        "page_index": page_index,
        "page_size": page_size,
        "shop_id": int(shop_id),
        "date_type": 1,
        "start_time": dt(start_at),
        "end_time": dt(end_at),
        "is_paid": True,
        "is_get_total": True,
        "archive": False,
    }


def qimen_public_params(
    app_key: str,
    app_secret: str,
    method: str,
    customer_id: str,
    target_app_key: str,
    session: str,
    timestamp: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "app_key": app_key,
        "method": method,
        "timestamp": timestamp,
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "target_app_key": target_app_key,
        "customer_id": customer_id,
    }
    if session:
        params["session"] = session
    params.update(body)
    params["sign"] = qimen_md5_sign(params, app_secret)
    return params


def qimen_md5_sign(params: dict[str, Any], app_secret: str) -> str:
    pieces = [app_secret]
    for key in sorted(params):
        if key == "sign":
            continue
        value = params[key]
        if value in (None, ""):
            continue
        pieces.append(str(key))
        pieces.append(str(value))
    pieces.append(app_secret)
    return hashlib.md5("".join(pieces).encode("utf-8")).hexdigest().upper()


def raise_qimen_error(payload: dict[str, Any]) -> None:
    response = payload.get("response")
    if isinstance(response, dict) and response.get("flag") == "failure":
        raise ValueError(f"{response.get('code')}: {response.get('sub_code') or response.get('message')}")
    error_response = payload.get("error_response")
    if isinstance(error_response, dict):
        raise ValueError(str(error_response.get("sub_msg") or error_response.get("msg") or error_response))
    code = payload.get("code")
    if code not in (None, 0, "0"):
        raise ValueError(f"{code}: {payload.get('msg') or payload.get('message')}")
    if payload.get("issuccess") is False:
        raise ValueError(str(payload.get("msg") or payload.get("message") or payload))


def has_next_page(payload: dict[str, Any], orders: list[dict[str, Any]], page_size: int) -> bool:
    for key in ("has_next", "has_more"):
        value = payload.get(key)
        if value in (True, 1, "1", "true", "True"):
            return True
        if value in (False, 0, "0", "false", "False"):
            return False
    return len(orders) >= page_size
