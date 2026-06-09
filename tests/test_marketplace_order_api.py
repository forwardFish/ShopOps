from __future__ import annotations

from typing import Any

from shopops.collectors import create_order_collector
from shopops.collectors.platform_order_api import (
    MarketplaceOrderApiCollector,
    doudian_sign,
    pdd_md5_sign,
    top_md5_sign,
)
from shopops.config import Settings


def test_non_taobao_api_source_factory_uses_marketplace_collector():
    settings = Settings(order_source="api", shop_platform="pinduoduo")

    collector = create_order_collector(settings)

    assert isinstance(collector, MarketplaceOrderApiCollector)


def test_pinduoduo_missing_credentials_fail_closed_without_zero_metrics():
    settings = Settings(order_source="api", shop_platform="pinduoduo", use_mock_collectors=False)

    result = MarketplaceOrderApiCollector(settings).fetch_today()

    assert result.success is False
    assert result.order_count is None
    assert result.total_amount is None
    assert result.error_code == "pinduoduo_credentials_missing"


def test_taobao_request_is_signed_and_orders_are_normalized():
    captured: list[dict[str, Any] | None] = []

    def transport(method, url, params, body):
        captured.append(params)
        assert method == "POST_FORM"
        return {
            "taobao_open_trades_sold_get_response": {
                "trades": {
                    "trade": [
                        {"tid": "T1", "status": "WAIT_SELLER_SEND_GOODS", "payment": "12.30", "created": "2026-06-04 09:00:00"},
                        {"tid": "T2", "status": "WAIT_BUYER_PAY", "payment": "99.00", "created": "2026-06-04 09:01:00"},
                    ]
                }
            }
        }

    settings = Settings(
        order_source="api",
        shop_platform="taobao",
        use_mock_collectors=False,
        taobao_app_key="ak",
        taobao_app_secret="secret",
        taobao_session_key="session",
    )

    result = MarketplaceOrderApiCollector(settings, transport=transport).fetch_today()

    assert result.success is True
    assert result.order_count == 1
    assert result.total_amount == 12.3
    assert result.orders[0]["order_id"] == "T1"
    assert captured[0]["sign"] == top_md5_sign({k: v for k, v in captured[0].items() if k != "sign"}, "secret")


def test_pinduoduo_list_ids_fetches_details_with_signed_requests():
    captured: list[dict[str, Any] | None] = []

    def transport(method, url, params, body):
        captured.append(params)
        if params["type"].endswith("increment.get"):
            return {"order_sn_list_get_response": {"order_sn_list": ["P1"]}}
        return {"order_info_get_response": {"order_info": {"order_sn": "P1", "order_status": "2", "pay_amount": "88.00"}}}

    settings = Settings(
        order_source="api",
        shop_platform="pinduoduo",
        use_mock_collectors=False,
        pdd_client_id="cid",
        pdd_client_secret="secret",
        pdd_access_token="token",
    )

    result = MarketplaceOrderApiCollector(settings, transport=transport).fetch_today()

    assert result.success is True
    assert result.orders[0]["order_id"] == "P1"
    assert result.total_amount == 88.0
    assert captured[0]["sign"] == pdd_md5_sign({k: v for k, v in captured[0].items() if k != "sign"}, "secret")
    assert captured[1]["type"] == "pdd.order.information.get"


def test_doudian_search_list_uses_hmac_signature_and_cent_amounts():
    captured: list[dict[str, Any] | None] = []

    def transport(method, url, params, body):
        captured.append(params)
        assert url.endswith("/order/searchList")
        return {
            "code": 10000,
            "data": {
                "shop_order_list": [
                    {"shop_order_id": "D1", "order_status": "2", "pay_amount": 12345, "create_time": 1780540000}
                ]
            },
        }

    settings = Settings(
        order_source="api",
        shop_platform="doudian",
        use_mock_collectors=False,
        doudian_app_key="ak",
        doudian_app_secret="secret",
        doudian_access_token="token",
    )

    result = MarketplaceOrderApiCollector(settings, transport=transport).fetch_today()

    assert result.success is True
    assert result.orders[0]["order_id"] == "D1"
    assert result.total_amount == 123.45
    assert captured[0]["sign"] == doudian_sign({k: v for k, v in captured[0].items() if k != "sign"}, "secret", "hmac-sha256")


def test_wechat_channels_fetches_token_list_and_details():
    calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, params, body):
        calls.append((method, url, params, body))
        if url.endswith("/cgi-bin/token"):
            return {"errcode": 0, "access_token": "wx-token"}
        if url.endswith("/channels/ec/order/list/get"):
            return {"errcode": 0, "order_id_list": ["W1"]}
        return {"errcode": 0, "order": {"order_id": "W1", "status": "20", "order_amount": 45678}}

    settings = Settings(
        order_source="api",
        shop_platform="wechat_channels",
        use_mock_collectors=False,
        wechat_channels_app_id="appid",
        wechat_channels_app_secret="secret",
    )

    result = MarketplaceOrderApiCollector(settings, transport=transport).fetch_today()

    assert result.success is True
    assert result.orders[0]["order_id"] == "W1"
    assert result.total_amount == 456.78
    assert calls[0][0] == "GET"
    assert calls[1][2] == {"access_token": "wx-token"}
