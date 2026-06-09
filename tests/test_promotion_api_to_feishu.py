from __future__ import annotations

from datetime import datetime

import pytest

from scripts.run_promotion_api_to_feishu import PromotionApiError, parse_promotion_api_response
from scripts.run_promotion_api_to_feishu import (
    F_ACTUAL_COST,
    F_COST,
    F_PLATFORM,
    F_STAT_DATE,
    F_UNIQUE_KEY,
    daily_promotion_fields,
    daily_unique_key,
)


def test_parse_real_qianniu_promotion_api_shape():
    body = {
        "data": {
            "list": [
                {
                    "alipayInshopAmt": 9802.0,
                    "charge": 3188.690990000018,
                    "adPv": 31407,
                    "click": 1346,
                    "roi": 3.073988677717544,
                }
            ]
        },
        "info": {"ok": True, "message": None},
    }

    result = parse_promotion_api_response(body, datetime(2026, 6, 3, 22, 0, 0), "2026-06-03")

    assert result.cost == 3188.69
    assert result.api_fields["adPv"] == 31407
    assert result.raw_status["http_shape"] == "info.data.list"


def test_parse_legacy_summary_shape_for_compatibility():
    body = {
        "success": True,
        "data": {
            "summary": {
                "charge": 12.3,
                "adPv": 10,
                "click": 2,
                "roi": 1.5,
                "alipayInshopAmt": 18.45,
            }
        },
    }

    result = parse_promotion_api_response(body, datetime(2026, 6, 3, 22, 0, 0), "2026-06-03")

    assert result.cost == 12.3
    assert result.raw_status["http_shape"] == "success.data.summary"


def test_parse_promotion_api_response_rejects_missing_charge():
    with pytest.raises(PromotionApiError, match="charge"):
        parse_promotion_api_response({"data": {"list": [{}]}, "info": {"ok": True}}, datetime(2026, 6, 3), "2026-06-03")


def test_daily_promotion_unique_key_and_fields_are_platform_date_based():
    result = parse_promotion_api_response(
        {
            "data": {"list": [{"charge": 88.8, "adPv": 100, "click": 5, "roi": 2.5, "alipayInshopAmt": 222.0}]},
            "info": {"ok": True},
        },
        datetime(2026, 6, 7, 10, 5, 0),
        "2026-06-07",
    )

    fields = daily_promotion_fields("天猫", result)

    assert daily_unique_key("天猫", "2026-06-07") == "天猫2026-06-07"
    assert fields[F_UNIQUE_KEY] == "天猫2026-06-07"
    assert fields[F_PLATFORM] == "天猫"
    assert fields[F_STAT_DATE] == "2026-06-07"
    assert fields[F_ACTUAL_COST] == 88.8
    assert fields[F_COST] == 88.8
