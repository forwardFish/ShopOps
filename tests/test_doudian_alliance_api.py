from __future__ import annotations

from datetime import datetime
from typing import Any

from shopops.collectors.doudian_alliance_api import (
    DoudianAllianceOrderCollector,
    cents_to_yuan,
    normalize_doudian_rate,
    parse_order_ids,
)
from shopops.collectors.platform_order_api import doudian_sign
from shopops.config import Settings


def test_doudian_alliance_missing_credentials_fail_closed_without_zero_metrics():
    settings = Settings(use_mock_collectors=False, doudian_alliance_order_ids="D1")

    result = DoudianAllianceOrderCollector(settings).fetch()

    assert result.success is False
    assert result.row_count is None
    assert result.total_estimated_commission is None
    assert result.error_code == "doudian_credentials_missing"
    assert result.rows == []


def test_doudian_alliance_requires_order_ids_for_real_request():
    settings = Settings(
        use_mock_collectors=False,
        doudian_app_key="ak",
        doudian_app_secret="secret",
        doudian_access_token="token",
    )

    result = DoudianAllianceOrderCollector(settings).fetch()

    assert result.success is False
    assert result.error_code == "doudian_alliance_order_ids_missing"


def test_doudian_alliance_request_is_signed_chunked_and_normalized():
    captured: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    def transport(method, url, params, body):
        captured.append((method, url, params, body))
        assert method == "POST"
        assert url == "https://openapi-fxg.jinritemai.com/alliance/getOrderList"
        return {
            "code": 10000,
            "msg": "success",
            "data": {
                "code": "100000",
                "code_msg": "success",
                "datas": [
                    {
                        "alliance_biz_type": "COMMON",
                        "author_account": "Creator A",
                        "commission_rate": "300",
                        "estimated_comission": "810",
                        "order_id": body["order_ids"][0],
                        "order_status": "支付成功",
                        "phase_id": "1",
                        "product_id": "3475285904548040556",
                        "real_comission": "100",
                        "shop_id": "1111115516",
                        "short_id": "1068048",
                        "total_pay_amount": "31000",
                    }
                ],
            },
        }

    settings = Settings(
        use_mock_collectors=False,
        shop_name="抖音店铺A",
        doudian_app_key="ak",
        doudian_app_secret="secret",
        doudian_access_token="token",
    )

    result = DoudianAllianceOrderCollector(
        settings,
        order_ids=["D1", "D2", "D3", "D4", "D5", "D6"],
        transport=transport,
        now=lambda: datetime(2026, 6, 4, 12, 0, 0),
    ).fetch()

    assert result.success is True
    assert result.row_count == 2
    assert result.total_estimated_commission == 16.2
    assert result.total_settled_commission == 2.0
    assert [call[3]["order_ids"] for call in captured] == [["D1", "D2", "D3", "D4", "D5"], ["D6"]]
    params = captured[0][2]
    assert params["method"] == "alliance.getOrderList"
    assert params["app_key"] == "ak"
    assert params["access_token"] == "token"
    assert params["sign_method"] == "hmac-sha256"
    assert params["sign"] == doudian_sign({k: v for k, v in params.items() if k != "sign"}, "secret", "hmac-sha256")
    row = result.rows[0]
    assert row["unique_key"] == "douyin_influencer_1111115516_D1"
    assert row["数据来源"] == "抖店开放平台"
    assert row["达人ID"] == "1068048"
    assert row["达人昵称"] == "Creator A"
    assert row["支付金额"] == 310.0
    assert row["佣金率"] == 0.03
    assert row["预估佣金"] == 8.1
    assert row["结算佣金"] == 1.0
    assert '"order_id": "D1"' in row["原始数据"]


def test_doudian_alliance_mock_path_writes_meaningful_rows_without_credentials():
    settings = Settings(use_mock_collectors=True)

    result = DoudianAllianceOrderCollector(settings, now=lambda: datetime(2026, 6, 4, 12, 0, 0)).fetch()

    assert result.success is True
    assert result.row_count == 1
    assert result.rows[0]["达人昵称"] == "抖音达人样例"
    assert result.rows[0]["预估佣金"] == 8.1


def test_parse_order_ids_and_amount_helpers():
    assert parse_order_ids(" A, B\nC ") == ["A", "B", "C"]
    assert cents_to_yuan("31000") == 310.0
    assert normalize_doudian_rate("300") == 0.03
    assert normalize_doudian_rate("10%") == 0.1
