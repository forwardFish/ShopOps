from __future__ import annotations

from shopops.config import Settings
from scripts.run_jushuitan_orders_to_feishu import (
    F_PAID_AMOUNT,
    F_PLATFORM,
    F_PRODUCT,
    F_QUANTITY,
    F_RAW,
    F_UNIT_PRICE,
    feishu_order_fields,
    missing_runtime_inputs,
    redact_sensitive,
)


def test_missing_runtime_inputs_names_token_and_platform_shop_ids(monkeypatch):
    for name in [
        "JUSHUITAN_SHOP_ID_TMALL",
        "JUSHUITAN_SHOP_ID_DOUYIN",
        "JUSHUITAN_SHOP_ID_WECHAT_CHANNELS",
        "JUSHUITAN_SHOP_ID_PINDUODUO",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = Settings(
        jushuitan_partner_id="app-key",
        jushuitan_partner_key="app-secret",
        jushuitan_token="",
        feishu_app_id="cli_x",
        feishu_app_secret="secret",
        shopops_data_center_app_token="app_token",
        shopops_order_table_id="table_id",
    )

    missing = missing_runtime_inputs(settings)

    assert "JUSHUITAN_TOKEN" in missing
    assert "JUSHUITAN_SHOP_ID_TMALL" in missing
    assert "JUSHUITAN_SHOP_ID_DOUYIN" in missing
    assert "JUSHUITAN_SHOP_ID_WECHAT_CHANNELS" in missing
    assert "JUSHUITAN_SHOP_ID_PINDUODUO" in missing


def test_feishu_order_fields_extracts_product_and_redacts_private_raw():
    row = feishu_order_fields(
        "\u5929\u732b",
        {
            "unique_key": "jushuitan_shop_o1",
            "shop_id": "shop",
            "shop_name": "Shop",
            "order_id": "o1",
            "order_status": "Sent",
            "created_at": "2026-06-04 10:00:00",
            "paid_amount": 169,
            "fetched_at": "2026-06-04 11:00:00",
            "raw": {
                "buyer_nick": "q**",
                "receiver_mobile": "13800000000",
                "receiver_address": "Somewhere",
                "items": [{"name": "Foam maker", "qty": 1, "price": 199}],
            },
        },
    )

    assert row[F_PLATFORM] == "\u5929\u732b"
    assert row[F_PRODUCT] == "Foam maker"
    assert row[F_UNIT_PRICE] == 199
    assert row[F_QUANTITY] == 1
    assert row[F_PAID_AMOUNT] == 169
    assert "13800000000" not in row[F_RAW]
    assert "Somewhere" not in row[F_RAW]


def test_redact_sensitive_recurses_through_nested_payloads():
    redacted = redact_sensitive({"items": [{"phone": "123", "safe": "ok"}], "address": "hidden"})

    assert redacted == {"items": [{"phone": "[REDACTED]", "safe": "ok"}], "address": "[REDACTED]"}
