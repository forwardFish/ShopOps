from __future__ import annotations

from typing import Any

from shopops.collectors import create_order_collector
from shopops.collectors.jushuitan_order_api import (
    JushuitanOrderApiCollector,
    jushuitan_md5_sign,
    jushuitan_public_params,
)
from shopops.config import Settings


def test_jushuitan_source_factory_keeps_direct_api_source_separate():
    settings = Settings(order_source="jushuitan")

    collector = create_order_collector(settings)

    assert isinstance(collector, JushuitanOrderApiCollector)


def test_jushuitan_missing_credentials_fail_closed_without_zero_metrics():
    settings = Settings(order_source="jushuitan", use_mock_collectors=False)

    result = JushuitanOrderApiCollector(settings).fetch_today()

    assert result.success is False
    assert result.source == "jushuitan"
    assert result.order_count is None
    assert result.total_amount is None
    assert result.error_code == "jushuitan_credentials_missing"


def test_jushuitan_request_uses_signed_public_params_and_normalizes_orders():
    captured: list[tuple[dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, params, body):
        captured.append((params, body))
        assert method == "POST_JSON"
        assert url == "https://open.erp321.com/api/open/query.aspx"
        return {
            "code": 0,
            "data": {
                "orders": [
                    {"o_id": "J1", "shop_id": "shop-a", "shop_name": "Shop A", "status": "Sent", "pay_amount": 12.3},
                    {"o_id": "J2", "shop_id": "shop-a", "shop_name": "Shop A", "status": "WaitPay", "pay_amount": 99},
                ]
            },
        }

    settings = Settings(
        order_source="jushuitan",
        use_mock_collectors=False,
        jushuitan_partner_id="pid",
        jushuitan_partner_key="pkey",
        jushuitan_token="token",
        jushuitan_shop_ids="shop-a, shop-b",
    )

    result = JushuitanOrderApiCollector(settings, transport=transport, page_size=100).fetch_today()

    assert result.success is True
    assert result.source == "jushuitan"
    assert result.order_count == 1
    assert result.total_amount == 12.3
    assert result.orders[0]["provider"] == "jushuitan"
    assert result.orders[0]["order_id"] == "J1"
    assert result.orders[0]["shop_id"] == "shop-a"
    params, body = captured[0]
    assert params["method"] == "orders.single.query"
    assert params["partnerid"] == "pid"
    assert params["token"] == "token"
    assert params["sign"] == jushuitan_md5_sign({k: v for k, v in params.items() if k != "sign"}, "pkey")
    assert body["shop_ids"] == ["shop-a", "shop-b"]
    assert body["modified_begin"].endswith("00:00:00")


def test_jushuitan_fetches_multiple_pages_until_short_page():
    calls: list[int] = []

    def transport(method, url, params, body):
        page_index = body["page_index"]
        calls.append(page_index)
        if page_index == 1:
            return {"code": 0, "data": {"orders": [{"o_id": "J1", "status": "Sent", "pay_amount": 1}]}}
        return {"code": 0, "data": {"orders": []}}

    settings = Settings(
        order_source="jushuitan",
        use_mock_collectors=False,
        jushuitan_partner_id="pid",
        jushuitan_partner_key="pkey",
        jushuitan_token="token",
    )

    result = JushuitanOrderApiCollector(settings, transport=transport, page_size=1).fetch_today()

    assert result.success is True
    assert calls == [1, 2]
    assert result.order_count == 1


def test_jushuitan_public_params_signature_is_stable():
    params = jushuitan_public_params(
        partner_id="pid",
        partner_key="pkey",
        token="token",
        method="orders.single.query",
        ts=1780540000,
    )

    assert params["method"] == "orders.single.query"
    assert params["partnerid"] == "pid"
    assert params["token"] == "token"
    assert params["ts"] == 1780540000
    assert params["sign"] == jushuitan_md5_sign({k: v for k, v in params.items() if k != "sign"}, "pkey")
