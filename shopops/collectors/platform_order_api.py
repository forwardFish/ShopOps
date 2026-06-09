from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

import requests

from shopops.collectors.base import OrderCollector
from shopops.config import Settings
from shopops.models import OrderCollectResult, dt


JsonTransport = Callable[[str, str, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]


class MarketplaceOrderApiCollector(OrderCollector):
    def __init__(
        self,
        settings: Settings,
        transport: JsonTransport | None = None,
        page_size: int = 100,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.page_size = page_size

    def fetch_today(self) -> OrderCollectResult:
        fetched_at = datetime.now()
        start_at = fetched_at.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            missing = self._missing_credentials()
            if missing and not self.settings.use_mock_collectors:
                return self._failure(fetched_at, f"{self.settings.shop_platform}_credentials_missing", missing)

            if missing and self.transport is None:
                raw_orders = self._mock_orders(fetched_at)
            else:
                raw_orders = self._fetch_platform_orders(start_at, fetched_at)

            paid_orders = [order for order in raw_orders if not self._is_unpaid(order)]
            orders = [self._normalize_order(order, fetched_at) for order in paid_orders]
            total_amount = round(sum(float(order.get("paid_amount") or 0) for order in orders), 2)
            return OrderCollectResult(
                success=True,
                source="api",
                shop_id=self.settings.shop_id,
                shop_name=self.settings.shop_name,
                order_count=len(orders),
                paid_order_count=len(orders),
                total_amount=total_amount,
                fetched_at=fetched_at,
                raw={
                    "platform": self.settings.shop_platform,
                    "mock": bool(missing and self.transport is None),
                    "page_size": self.page_size,
                },
                orders=orders,
            )
        except Exception as exc:
            return self._failure(fetched_at, f"{self.settings.shop_platform}_api_failed", str(exc))

    def _missing_credentials(self) -> str | None:
        platform = self.settings.shop_platform
        if platform == "taobao" and not all([self.settings.taobao_app_key, self.settings.taobao_app_secret, self.settings.taobao_session_key]):
            return "Taobao app key, app secret, or session key is missing"
        if platform == "pinduoduo" and not all([self.settings.pdd_client_id, self.settings.pdd_client_secret, self.settings.pdd_access_token]):
            return "Pinduoduo client id, client secret, or access token is missing"
        if platform == "doudian" and not all([self.settings.doudian_app_key, self.settings.doudian_app_secret, self.settings.doudian_access_token]):
            return "Doudian app key, app secret, or access token is missing"
        if platform == "wechat_channels" and not (
            self.settings.wechat_channels_access_token
            or all([self.settings.wechat_channels_app_id, self.settings.wechat_channels_app_secret])
        ):
            return "Wechat Channels app id/app secret or access token is missing"
        return None

    def _fetch_platform_orders(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        platform = self.settings.shop_platform
        if platform == "taobao":
            return self._fetch_taobao(start_at, end_at)
        if platform == "pinduoduo":
            return self._fetch_pinduoduo(start_at, end_at)
        if platform == "doudian":
            return self._fetch_doudian(start_at, end_at)
        if platform == "wechat_channels":
            return self._fetch_wechat_channels(start_at, end_at)
        raise ValueError(f"Unsupported SHOP_PLATFORM: {platform}")

    def _request(self, method: str, url: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.transport is not None:
            return self.transport(method, url, params, body)
        if method == "GET":
            response = requests.get(url, params=params, timeout=20)
        elif method == "POST_FORM":
            response = requests.post(url, data=params, timeout=20)
        else:
            response = requests.post(url, params=params, json=body, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("API response is not a JSON object")
        return data

    def _fetch_taobao(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "method": self.settings.taobao_order_list_method,
            "app_key": self.settings.taobao_app_key,
            "session": self.settings.taobao_session_key,
            "timestamp": dt(end_at),
            "v": "2.0",
            "format": "json",
            "sign_method": "md5",
            "fields": "tid,status,payment,total_fee,created,pay_time,title",
            "start_created": dt(start_at),
            "end_created": dt(end_at),
            "page_no": 1,
            "page_size": self.page_size,
        }
        params["sign"] = top_md5_sign(params, self.settings.taobao_app_secret)
        payload = self._request("POST_FORM", self.settings.taobao_api_url, params, None)
        self._raise_top_error(payload)
        return self._extract_orders(payload)

    def _fetch_pinduoduo(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "type": self.settings.pdd_order_list_type,
            "client_id": self.settings.pdd_client_id,
            "access_token": self.settings.pdd_access_token,
            "timestamp": str(int(end_at.timestamp())),
            "data_type": "JSON",
            "start_updated_at": int(start_at.timestamp()),
            "end_updated_at": int(end_at.timestamp()),
            "page": 1,
            "page_size": self.page_size,
        }
        params["sign"] = pdd_md5_sign(params, self.settings.pdd_client_secret)
        payload = self._request("POST_FORM", self.settings.pdd_api_url, params, None)
        self._raise_pdd_error(payload)
        orders = self._extract_orders(payload)
        order_ids = [str(order) for order in orders if not isinstance(order, dict)]
        detail_orders = [order for order in orders if isinstance(order, dict)]
        for order_id in order_ids:
            detail_orders.append(self._fetch_pinduoduo_detail(order_id))
        return detail_orders

    def _fetch_pinduoduo_detail(self, order_sn: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "type": self.settings.pdd_order_detail_type,
            "client_id": self.settings.pdd_client_id,
            "access_token": self.settings.pdd_access_token,
            "timestamp": str(int(datetime.now().timestamp())),
            "data_type": "JSON",
            "order_sn": order_sn,
        }
        params["sign"] = pdd_md5_sign(params, self.settings.pdd_client_secret)
        payload = self._request("POST_FORM", self.settings.pdd_api_url, params, None)
        self._raise_pdd_error(payload)
        orders = self._extract_orders(payload)
        return orders[0] if orders else {"order_sn": order_sn, "raw_response": payload}

    def _fetch_doudian(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        body = {
            "update_time_start": int(start_at.timestamp()),
            "update_time_end": int(end_at.timestamp()),
            "page": 0,
            "size": min(self.page_size, 100),
            "order_by": "update_time",
            "order_asc": False,
        }
        param_json = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        params: dict[str, Any] = {
            "method": "order.searchList",
            "app_key": self.settings.doudian_app_key,
            "access_token": self.settings.doudian_access_token,
            "param_json": param_json,
            "timestamp": dt(end_at),
            "v": "2",
            "sign_method": self.settings.doudian_sign_method,
        }
        params["sign"] = doudian_sign(params, self.settings.doudian_app_secret, self.settings.doudian_sign_method)
        payload = self._request("POST", f"{self.settings.doudian_api_url.rstrip('/')}/order/searchList", params, None)
        self._raise_common_error(payload)
        return self._extract_orders(payload)

    def _fetch_wechat_channels(self, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        token = self.settings.wechat_channels_access_token or self._fetch_wechat_token()
        body = {
            "create_time_range": {"start_time": int(start_at.timestamp()), "end_time": int(end_at.timestamp())},
            "page_size": min(self.page_size, 100),
        }
        params = {"access_token": token}
        list_url = f"{self.settings.wechat_channels_api_url.rstrip('/')}/channels/ec/order/list/get"
        payload = self._request("POST", list_url, params, body)
        self._raise_wechat_error(payload)
        orders = self._extract_orders(payload)
        order_ids = [str(order) for order in orders if not isinstance(order, dict)]
        detail_orders = [order for order in orders if isinstance(order, dict)]
        for order_id in order_ids:
            detail_orders.append(self._fetch_wechat_order_detail(token, order_id))
        return detail_orders

    def _fetch_wechat_token(self) -> str:
        params = {
            "grant_type": "client_credential",
            "appid": self.settings.wechat_channels_app_id,
            "secret": self.settings.wechat_channels_app_secret,
        }
        url = f"{self.settings.wechat_channels_api_url.rstrip('/')}/cgi-bin/token"
        payload = self._request("GET", url, params, None)
        self._raise_wechat_error(payload)
        token = payload.get("access_token")
        if not token:
            raise ValueError("Wechat token response did not include access_token")
        return str(token)

    def _fetch_wechat_order_detail(self, token: str, order_id: str) -> dict[str, Any]:
        url = f"{self.settings.wechat_channels_api_url.rstrip('/')}/channels/ec/order/get"
        payload = self._request("POST", url, {"access_token": token}, {"order_id": order_id})
        self._raise_wechat_error(payload)
        order = payload.get("order") or payload.get("data", {}).get("order")
        return order if isinstance(order, dict) else {"order_id": order_id, "raw_response": payload}

    def _extract_orders(self, payload: Any) -> list[Any]:
        found = find_first_list(
            payload,
            (
                "trades",
                "trade",
                "order_list",
                "orders",
                "order_sn_list",
                "order_id_list",
                "shop_order_list",
            ),
        )
        if found is None:
            found_dict = find_first_dict(payload, ("trade", "order", "order_info"))
            if found_dict is not None:
                return [found_dict]
            return []
        return found

    def _normalize_order(self, raw_order: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        order_id = self._order_id(raw_order)
        return {
            "unique_key": f"{self.settings.shop_platform}_{self.settings.shop_id}_{order_id}",
            "platform": self.settings.shop_platform,
            "shop_id": self.settings.shop_id,
            "shop_name": self.settings.shop_name,
            "order_id": order_id,
            "order_status": self._status(raw_order),
            "created_at": first_value(raw_order, "created", "created_at", "create_time", "order_create_time"),
            "paid_at": first_value(raw_order, "pay_time", "paid_at", "confirm_time", "pay_time_str"),
            "paid_amount": normalize_amount(self.settings.shop_platform, raw_order),
            "fetched_at": dt(fetched_at),
            "raw": raw_order,
        }

    def _order_id(self, raw_order: dict[str, Any]) -> str:
        return str(first_value(raw_order, "tid", "order_sn", "shop_order_id", "order_id", "id") or "unknown")

    def _status(self, raw_order: dict[str, Any]) -> str | None:
        status = first_value(raw_order, "status", "order_status", "main_status", "status_str")
        return str(status) if status is not None else None

    def _is_unpaid(self, raw_order: dict[str, Any]) -> bool:
        status = self._status(raw_order)
        return status in {"WAIT_BUYER_PAY", "0", "1", "100"}

    def _mock_orders(self, fetched_at: datetime) -> list[dict[str, Any]]:
        created = dt(fetched_at.replace(hour=9, minute=0, second=0, microsecond=0))
        return [
            {
                "order_id": f"{self.settings.shop_platform}_mock_10001",
                "payment": "188.50",
                "status": "PAID",
                "created": created,
                "pay_time": created,
                "title": "mock order",
            }
        ]

    def _failure(self, fetched_at: datetime, code: str, message: str) -> OrderCollectResult:
        return OrderCollectResult(
            success=False,
            source="api",
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
    def _raise_top_error(payload: dict[str, Any]) -> None:
        if "error_response" in payload:
            error = payload["error_response"]
            raise ValueError(f"{error.get('code')}: {error.get('msg') or error.get('sub_msg')}")

    @staticmethod
    def _raise_pdd_error(payload: dict[str, Any]) -> None:
        if "error_response" in payload:
            error = payload["error_response"]
            raise ValueError(f"{error.get('error_code')}: {error.get('error_msg')}")

    @staticmethod
    def _raise_wechat_error(payload: dict[str, Any]) -> None:
        errcode = payload.get("errcode", 0)
        if errcode not in (0, "0"):
            raise ValueError(f"{errcode}: {payload.get('errmsg')}")

    @staticmethod
    def _raise_common_error(payload: dict[str, Any]) -> None:
        code = payload.get("code")
        if code not in (None, 0, "0", 10000, "10000"):
            raise ValueError(f"{code}: {payload.get('msg') or payload.get('message')}")


def top_md5_sign(params: dict[str, Any], secret: str) -> str:
    sign_body = "".join(f"{key}{params[key]}" for key in sorted(params) if key != "sign" and params[key] is not None)
    return hashlib.md5(f"{secret}{sign_body}{secret}".encode("utf-8")).hexdigest().upper()


def pdd_md5_sign(params: dict[str, Any], secret: str) -> str:
    sign_body = "".join(f"{key}{params[key]}" for key in sorted(params) if key != "sign" and params[key] is not None)
    return hashlib.md5(f"{secret}{sign_body}{secret}".encode("utf-8")).hexdigest().upper()


def doudian_sign(params: dict[str, Any], secret: str, sign_method: str = "hmac-sha256") -> str:
    sign_body = "".join(f"{key}{params[key]}" for key in sorted(params) if key != "sign" and params[key] is not None)
    pattern = f"{secret}{sign_body}{secret}"
    if sign_method.lower() == "md5":
        return hashlib.md5(pattern.encode("utf-8")).hexdigest()
    return hmac.new(secret.encode("utf-8"), pattern.encode("utf-8"), hashlib.sha256).hexdigest()


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


def find_first_dict(payload: Any, candidate_keys: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    for value in payload.values():
        nested = find_first_dict(value, candidate_keys)
        if nested is not None:
            return nested
    return None


def first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def normalize_amount(platform: str, raw_order: dict[str, Any]) -> float:
    value = first_value(raw_order, "paid_amount", "payment", "total_fee", "pay_amount", "order_amount", "total_amount")
    if value is None:
        return 0.0
    amount = float(value)
    if platform in {"doudian", "wechat_channels"} and amount > 10000:
        return round(amount / 100, 2)
    return round(amount, 2)
