from __future__ import annotations

from datetime import date
from typing import Any

from shopops.collectors.qianchuan_report_api import QianchuanReportClient, pick_access_token, pick_advertiser_id
from shopops.config import Settings


def test_qianchuan_advertiser_get_uses_oceanengine_access_token_header():
    captured: list[tuple[str, str, dict[str, str] | None, dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, headers, params, body):
        captured.append((method, url, headers, params, body))
        return {"code": 0, "data": {"list": [{"advertiser_id": 12345}]}}

    settings = Settings(qianchuan_access_token="access-token")

    call = QianchuanReportClient(settings, transport=transport).get_authorized_advertisers()

    assert call.success is True
    assert captured == [
        (
            "GET",
            "https://api.oceanengine.com/open_api/oauth2/advertiser/get/",
            {"Access-Token": "access-token"},
            None,
            None,
        )
    ]
    assert call.request_headers == {"Access-Token": "acce...oken"}
    assert pick_advertiser_id(call) == "12345"


def test_qianchuan_report_calls_use_report_fields_and_advertiser_id():
    captured: list[tuple[str, str, dict[str, str] | None, dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, headers, params, body):
        captured.append((method, url, headers, params, body))
        return {"code": 0, "data": {"list": []}}

    settings = Settings(qianchuan_access_token="token")
    client = QianchuanReportClient(settings, transport=transport)

    client.get_advertiser_report("9876", date(2026, 6, 1), date(2026, 6, 1))
    client.get_ad_report("9876", date(2026, 6, 1), date(2026, 6, 1))

    assert captured[0][1] == "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/advertiser/get/"
    assert captured[1][1] == "https://api.oceanengine.com/open_api/v1.0/qianchuan/report/ad/get/"
    for _, _, headers, params, body in captured:
        assert headers == {"Access-Token": "token"}
        assert body is None
        assert params["advertiser_id"] == "9876"
        assert params["start_date"] == "2026-06-01"
        assert params["end_date"] == "2026-06-01"
        assert params["fields"] == '["stat_cost","show_cnt","click_cnt","pay_order_count","pay_order_amount","roi"]'
        assert params["time_granularity"] == "TIME_GRANULARITY_DAILY"
        assert params["page"] == 1
        assert params["page_size"] == 100


def test_qianchuan_auth_code_exchange_redacts_secret_and_extracts_token():
    captured: list[tuple[str, str, dict[str, str] | None, dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, headers, params, body):
        captured.append((method, url, headers, params, body))
        return {"code": 0, "data": {"access_token": "access-123", "refresh_token": "refresh-123"}}

    settings = Settings(qianchuan_app_id="app-id", qianchuan_app_secret="app-secret")

    call = QianchuanReportClient(settings, transport=transport).exchange_auth_code("auth-code")

    assert captured[0] == (
        "POST_FORM",
        "https://ad.oceanengine.com/open_api/oauth2/access_token/",
        None,
        None,
        {"app_id": "app-id", "secret": "app-secret", "grant_type": "auth_code", "auth_code": "auth-code"},
    )
    assert call.request_body["secret"] == "app-...cret"
    assert call.request_body["auth_code"] == "auth...code"
    assert pick_access_token(call) == "access-123"
