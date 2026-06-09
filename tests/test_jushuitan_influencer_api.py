from __future__ import annotations

from typing import Any

from shopops.collectors.jushuitan_influencer_api import (
    JushuitanInfluencerCommissionCollector,
    extract_influencer_commission_rows,
)
from shopops.collectors.jushuitan_order_api import jushuitan_md5_sign
from shopops.config import Settings


def test_jushuitan_influencer_missing_credentials_fail_closed_without_zero_metrics():
    settings = Settings(use_mock_collectors=False)

    result = JushuitanInfluencerCommissionCollector(settings).fetch_today()

    assert result.success is False
    assert result.row_count is None
    assert result.total_estimated_commission is None
    assert result.error_code == "jushuitan_credentials_missing"
    assert result.rows == []


def test_jushuitan_influencer_request_uses_signed_params_and_normalizes_commission_rows():
    captured: list[tuple[dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, params, body):
        captured.append((params, body))
        assert method == "POST_JSON"
        return {
            "code": 0,
            "data": {
                "orders": [
                    {
                        "order_id": "DY1",
                        "shop_id": "douyin-shop",
                        "shop_name": "Douyin Shop",
                        "author_id": "kol_1",
                        "author_name": "Creator A",
                        "product_id": "goods_1",
                        "product_name": "Product A",
                        "pay_amount": 88.8,
                        "commission_rate": "10%",
                        "estimated_total_commission": 580,
                        "settled_commission": 5.2,
                        "estimated_tech_service_fee": 58,
                        "settle_status": "settled",
                    }
                ]
            },
        }

    settings = Settings(
        use_mock_collectors=False,
        jushuitan_partner_id="pid",
        jushuitan_partner_key="pkey",
        jushuitan_token="token",
        jushuitan_douyin_shop_id="douyin-shop",
        jushuitan_influencer_query_method="custom.influencer.query",
    )

    result = JushuitanInfluencerCommissionCollector(settings, transport=transport).fetch_today()

    assert result.success is True
    assert result.row_count == 1
    assert result.total_estimated_commission == 5.8
    assert result.total_settled_commission == 5.2
    row = result.rows[0]
    assert row["unique_key"] == "douyin_influencer_douyin-shop_DY1"
    assert row["平台"] == "抖音"
    assert row["数据来源"] == "聚水潭"
    assert row["达人ID"] == "kol_1"
    assert row["达人昵称"] == "Creator A"
    assert row["佣金率"] == 0.1
    assert row["预估佣金"] == 5.8
    assert row["技术服务费"] == 0.58
    params, body = captured[0]
    assert params["method"] == "custom.influencer.query"
    assert params["sign"] == jushuitan_md5_sign({k: v for k, v in params.items() if k != "sign"}, "pkey")
    assert body["shop_id"] == "douyin-shop"
    assert body["page_index"] == 1


def test_jushuitan_influencer_fetches_multiple_pages_until_short_page():
    calls: list[int] = []

    def transport(method, url, params, body):
        page_index = body["page_index"]
        calls.append(page_index)
        if page_index == 1:
            return {"code": 0, "data": {"orders": [{"order_id": "DY1", "estimated_commission": 1}]}}
        return {"code": 0, "data": {"orders": []}}

    settings = Settings(
        use_mock_collectors=False,
        jushuitan_partner_id="pid",
        jushuitan_partner_key="pkey",
        jushuitan_token="token",
    )

    result = JushuitanInfluencerCommissionCollector(settings, transport=transport, page_size=1).fetch_today()

    assert result.success is True
    assert calls == [1, 2]
    assert result.row_count == 1


def test_extract_influencer_commission_rows_accepts_common_response_shapes():
    assert extract_influencer_commission_rows({"data": {"items": [{"order_id": "DY1"}]}}) == [{"order_id": "DY1"}]
