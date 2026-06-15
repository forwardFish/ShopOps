from __future__ import annotations

import pytest

from data_robot.ocr_ads_snapshot import (
    default_dashboard_url,
    detect_manual_intervention_required,
    direct_cdp_text_has_metric_anchor,
    direct_cdp_text_has_parseable_metric,
    parse_ad_snapshot_text,
)
from scripts.import_daily_files_to_feishu import (
    F_ACTUAL_SPEND,
    F_CLICKS,
    F_DATE,
    F_DEAL_AMOUNT,
    F_IMPRESSIONS,
    F_PLATFORM,
    F_UNIQUE_KEY,
)


def test_parse_douyin_ad_snapshot_from_ocr_text():
    text = """
    数据概览
    整体展示次数 13,781 -62.59%
    整体点击次数 576 -65.09%
    整体点击率 4.18%
    整体转化率 3.47%
    整体消耗(元) 1,261.97 -68.63%
    """

    row = parse_ad_snapshot_text("douyin", text, "2026-06-15")

    assert row[F_PLATFORM] == "抖音"
    assert row[F_DATE] == "2026-06-15"
    assert row[F_IMPRESSIONS] == 13781
    assert row[F_CLICKS] == 576
    assert row[F_ACTUAL_SPEND] == 1261.97


def test_parse_tmall_ad_snapshot_from_ocr_text():
    text = """
    经营概览 当前日期：2026-06-15
    花费 3,114.30
    展现量 40,537
    点击量 1,556
    投入产出比 1.57
    总成交金额 4,901.00
    """

    row = parse_ad_snapshot_text("tmall", text, "2026-06-15")

    assert row[F_PLATFORM] == "天猫"
    assert row[F_ACTUAL_SPEND] == 3114.30
    assert row[F_IMPRESSIONS] == 40537
    assert row[F_CLICKS] == 1556
    assert row[F_DEAL_AMOUNT] == 4901.00


def test_parse_douyin_business_home_prefers_overview_spend():
    text = """
    \u5de8\u91cf\u5343\u5ddd
    \u8da3\u767d\u4f01\u4e1a\u5e97
    0.00
    \u4eca\u65e5\u6d88\u8017
    0
    \u5c55\u793a\u6570
    \u5168\u57df\u6295\u653e
    \u6807\u51c6\u6295\u653e
    \u6709\u6d88\u8017\u8d26\u6237\u6570
    1
    \u6d88\u8017
    1,536.41
    \u6574\u4f53\u6210\u4ea4\u8ba2\u5355\u6570
    24
    \u6574\u4f53\u6210\u4ea4\u91d1\u989d(\u5143)
    4,394
    \u6574\u4f53\u652f\u4ed8ROI
    2.86
    """

    row = parse_ad_snapshot_text("douyin", text, "2026-06-15")

    assert row[F_ACTUAL_SPEND] == 1536.41
    assert row[F_DEAL_AMOUNT] == 4394.0


def test_parse_douyin_global_delivery_snapshot_from_user_screenshot():
    text = """
    数据概览
    账户整体消耗(元)
    1,658.20
    全域投放消耗(元)
    1,658.20
    净成交ROI
    2.47
    净成交金额(元)
    4,091.00
    净成交订单数
    22
    """

    row = parse_ad_snapshot_text("douyin", text, "2026-06-15")

    assert row[F_ACTUAL_SPEND] == 1658.20
    assert row[F_DEAL_AMOUNT] == 4091.0


def test_parse_ad_snapshot_fails_when_spend_is_missing():
    with pytest.raises(RuntimeError, match="spend metric"):
        parse_ad_snapshot_text("tmall", "展现量 100 点击量 2", "2026-06-15")


def test_ad_snapshot_unique_key_overwrites_same_platform_date_only():
    first = parse_ad_snapshot_text("tmall", "花费 10 展现量 100", "2026-06-15")
    second = parse_ad_snapshot_text("tmall", "花费 20 展现量 200", "2026-06-15")
    next_day = parse_ad_snapshot_text("tmall", "花费 20 展现量 200", "2026-06-16")

    assert first[F_UNIQUE_KEY] == second[F_UNIQUE_KEY]
    assert first[F_UNIQUE_KEY] != next_day[F_UNIQUE_KEY]


def test_detect_manual_login_and_captcha_text():
    assert detect_manual_intervention_required("请拖动滑块完成安全验证", "https://login.taobao.com/")
    assert detect_manual_intervention_required("SMS captcha required", "https://example.com")
    assert not detect_manual_intervention_required("经营概览 花费 3,114.30 展现量 40,537", "https://myseller.taobao.com/")


def test_tmall_default_dashboard_url_is_today_promotion_center():
    assert default_dashboard_url("tmall", "2026-06-15") == "https://myseller.taobao.com/home.htm/tuiguangcenter_new/"


def test_direct_cdp_metric_ready_requires_parseable_values():
    pending_text = "\n".join(
        [
            "\u7ecf\u8425\u6982\u89c8",
            "\u82b1\u8d39 -",
            "\u5c55\u73b0\u91cf -",
            "\u70b9\u51fb\u91cf -",
            "\u603b\u6210\u4ea4\u91d1\u989d -",
        ]
    )
    ready_text = "\n".join(
        [
            "\u7ecf\u8425\u6982\u89c8",
            "\u82b1\u8d39 38.39",
            "\u5c55\u73b0\u91cf 647",
            "\u70b9\u51fb\u91cf 25",
        ]
    )

    assert direct_cdp_text_has_metric_anchor(pending_text, "tmall")
    assert not direct_cdp_text_has_parseable_metric(pending_text, "tmall")
    assert direct_cdp_text_has_parseable_metric(ready_text, "tmall")


def test_qianchuan_source_login_query_is_not_login_page():
    url = "https://business.oceanengine.com/site/index?source=ecp_login"
    text = "巨量千川 趣白企业店 今日消耗 0.00 展示数 0 前往平台"

    assert not detect_manual_intervention_required(text, url)
