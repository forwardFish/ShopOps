from __future__ import annotations

from typing import Any

from shopops.collectors.jushuitan_qimen_order_api import (
    JushuitanQimenOrderListCollector,
    qimen_md5_sign,
    qimen_public_params,
)
from shopops.config import Settings


def test_qimen_missing_credentials_fail_closed_without_zero_metrics():
    settings = Settings(order_source="jushuitan", use_mock_collectors=False, shop_id="21117357")

    result = JushuitanQimenOrderListCollector(settings).fetch_today()

    assert result.success is False
    assert result.order_count is None
    assert result.total_amount is None
    assert result.error_code == "jushuitan_qimen_credentials_missing"
    assert "JUSHUITAN_QIMEN_APP_KEY" in str(result.error_message)
    assert "JUSHUITAN_QIMEN_APP_SECRET" in str(result.error_message)
    assert "JUSHUITAN_QIMEN_CUSTOMER_ID" in str(result.error_message)


def test_qimen_public_params_include_customer_route_and_stable_sign():
    body = {"page_index": 1, "page_size": 10, "shop_id": 21117357}

    params = qimen_public_params(
        app_key="qimen-key",
        app_secret="qimen-secret",
        method="jushuitan.order.list.query",
        customer_id="customer-1",
        target_app_key="23060081",
        session="",
        timestamp="2026-06-04 12:00:00",
        body=body,
    )

    assert params["app_key"] == "qimen-key"
    assert params["method"] == "jushuitan.order.list.query"
    assert params["customer_id"] == "customer-1"
    assert params["target_app_key"] == "23060081"
    assert params["shop_id"] == 21117357
    assert params["sign"] == qimen_md5_sign({key: value for key, value in params.items() if key != "sign"}, "qimen-secret")


def test_qimen_collector_posts_form_and_normalizes_orders():
    captured: list[tuple[str, dict[str, Any] | None]] = []

    def transport(method, url, params, body):
        captured.append((method, params))
        return {
            "orders": [
                {
                    "o_id": 123,
                    "shop_id": 21117357,
                    "shop_name": "天猫-趣白旗舰店",
                    "shop_status": "WAIT_SELLER_SEND_GOODS",
                    "created": "2026-06-04 10:00:00",
                    "pay_amount": 169,
                }
            ],
            "has_next": False,
        }

    settings = Settings(
        order_source="jushuitan",
        use_mock_collectors=False,
        shop_id="21117357",
        shop_name="天猫",
        jushuitan_qimen_app_key="qimen-key",
        jushuitan_qimen_app_secret="qimen-secret",
        jushuitan_qimen_customer_id="customer-1",
    )

    result = JushuitanQimenOrderListCollector(settings, transport=transport).fetch_today()

    assert result.success is True
    assert result.order_count == 1
    assert result.total_amount == 169
    assert result.orders[0]["provider"] == "jushuitan_qimen"
    assert result.orders[0]["order_id"] == "123"
    assert captured[0][0] == "POST_FORM"
    assert captured[0][1]["customer_id"] == "customer-1"
