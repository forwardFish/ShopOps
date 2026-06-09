from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import requests

from shopops.config import Settings


JsonTransport = Callable[[str, str, dict[str, str] | None, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]

REPORT_FIELDS = ["stat_cost", "show_cnt", "click_cnt", "pay_order_count", "pay_order_amount", "roi"]


@dataclass
class OceanEngineApiCall:
    name: str
    method: str
    url: str
    success: bool
    request_headers: dict[str, str] = field(default_factory=dict)
    request_params: dict[str, Any] | None = None
    request_body: dict[str, Any] | None = None
    status_code: int | None = None
    response: Any | None = None
    error: str | None = None


class QianchuanReportClient:
    def __init__(
        self,
        settings: Settings,
        transport: JsonTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    def exchange_auth_code(self, auth_code: str) -> OceanEngineApiCall:
        body = {
            "app_id": self.settings.qianchuan_app_id,
            "secret": self.settings.qianchuan_app_secret,
            "grant_type": "auth_code",
            "auth_code": auth_code,
        }
        return self._request(
            "exchange_auth_code",
            "POST_FORM",
            self._auth_url("/open_api/oauth2/access_token/"),
            headers=None,
            params=None,
            body=body,
        )

    def refresh_access_token(self, refresh_token: str) -> OceanEngineApiCall:
        body = {
            "app_id": self.settings.qianchuan_app_id,
            "secret": self.settings.qianchuan_app_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        return self._request(
            "refresh_access_token",
            "POST_FORM",
            self._auth_url("/open_api/oauth2/refresh_token/"),
            headers=None,
            params=None,
            body=body,
        )

    def probe_client_credentials_token(self) -> OceanEngineApiCall:
        body = {
            "app_id": self.settings.qianchuan_app_id,
            "secret": self.settings.qianchuan_app_secret,
            "grant_type": "client_credentials",
        }
        return self._request(
            "probe_client_credentials_token",
            "POST_FORM",
            self._auth_url("/open_api/oauth2/access_token/"),
            headers=None,
            params=None,
            body=body,
        )

    def get_authorized_advertisers(self, access_token: str | None = None) -> OceanEngineApiCall:
        return self._request(
            "get_authorized_advertisers",
            "GET",
            self._api_url("/open_api/oauth2/advertiser/get/"),
            headers=self._access_headers(access_token),
            params=None,
            body=None,
        )

    def get_advertiser_report(
        self,
        advertiser_id: str,
        start_date: date,
        end_date: date,
        access_token: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> OceanEngineApiCall:
        params = self._report_params(advertiser_id, start_date, end_date, page, page_size)
        return self._request(
            "get_qianchuan_advertiser_report",
            "GET",
            self._api_url("/open_api/v1.0/qianchuan/report/advertiser/get/"),
            headers=self._access_headers(access_token),
            params=params,
            body=None,
        )

    def get_ad_report(
        self,
        advertiser_id: str,
        start_date: date,
        end_date: date,
        access_token: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> OceanEngineApiCall:
        params = self._report_params(advertiser_id, start_date, end_date, page, page_size)
        return self._request(
            "get_qianchuan_ad_report",
            "GET",
            self._api_url("/open_api/v1.0/qianchuan/report/ad/get/"),
            headers=self._access_headers(access_token),
            params=params,
            body=None,
        )

    def _report_params(
        self,
        advertiser_id: str,
        start_date: date,
        end_date: date,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return {
            "advertiser_id": advertiser_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "fields": json.dumps(REPORT_FIELDS, separators=(",", ":")),
            "time_granularity": "TIME_GRANULARITY_DAILY",
            "page": page,
            "page_size": page_size,
        }

    def _access_headers(self, access_token: str | None = None) -> dict[str, str]:
        token = access_token if access_token is not None else self.settings.qianchuan_access_token
        return {"Access-Token": token} if token else {}

    def _api_url(self, path: str) -> str:
        return f"{self.settings.oceanengine_api_url.rstrip('/')}{path}"

    def _auth_url(self, path: str) -> str:
        return f"{self.settings.oceanengine_auth_api_url.rstrip('/')}{path}"

    def _request(
        self,
        name: str,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> OceanEngineApiCall:
        safe_headers = _redact_headers(headers or {})
        try:
            if self.transport is not None:
                payload = self.transport(method, url, headers, params, body)
                return OceanEngineApiCall(name, method, url, True, safe_headers, params, _redact_body(body), response=payload)

            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=20)
            elif method == "POST_FORM":
                response = requests.post(url, headers=headers, data=body, timeout=20)
            else:
                response = requests.post(url, headers=headers, params=params, json=body, timeout=20)

            payload = _response_payload(response)
            return OceanEngineApiCall(
                name=name,
                method=method,
                url=response.url,
                success=response.ok and _payload_success(payload),
                request_headers=safe_headers,
                request_params=params,
                request_body=_redact_body(body),
                status_code=response.status_code,
                response=payload,
            )
        except Exception as exc:
            return OceanEngineApiCall(
                name=name,
                method=method,
                url=url,
                success=False,
                request_headers=safe_headers,
                request_params=params,
                request_body=_redact_body(body),
                error=str(exc),
            )


def pick_access_token(*calls: OceanEngineApiCall) -> str | None:
    for call in calls:
        token = _find_key(call.response, "access_token")
        if token:
            return str(token)
    return None


def pick_advertiser_id(call: OceanEngineApiCall) -> str | None:
    candidates = _find_lists(call.response)
    for rows in candidates:
        for row in rows:
            if isinstance(row, dict):
                value = row.get("advertiser_id") or row.get("id")
                if value:
                    return str(value)
    return None


def _response_payload(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _payload_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return True
    code = payload.get("code")
    if code in (None, 0, "0"):
        return True
    return False


def _find_key(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if payload.get(key):
            return payload[key]
        for value in payload.values():
            found = _find_key(value, key)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_key(item, key)
            if found:
                return found
    return None


def _find_lists(payload: Any) -> list[list[Any]]:
    found: list[list[Any]] = []
    if isinstance(payload, list):
        found.append(payload)
    elif isinstance(payload, dict):
        for value in payload.values():
            found.extend(_find_lists(value))
    return found


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    redacted = dict(headers)
    if redacted.get("Access-Token"):
        redacted["Access-Token"] = _mask(redacted["Access-Token"])
    return redacted


def _redact_body(body: dict[str, Any] | None) -> dict[str, Any] | None:
    if body is None:
        return None
    redacted = dict(body)
    for key in ("secret", "app_secret", "access_token", "refresh_token", "auth_code"):
        if redacted.get(key):
            redacted[key] = _mask(str(redacted[key]))
    return redacted


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
