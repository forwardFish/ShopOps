from __future__ import annotations

from datetime import date, datetime

from shopops.config import Settings
from shopops.services.roi_summary_simulation import (
    AD_COST_RAW,
    DASHBOARD_TODAY,
    INFLUENCER_COMMISSION_RAW,
    ORDERS_RAW,
    PLATFORM_COMPARE,
    ROI_DAILY_SUMMARY,
    simulate_roi_cycles,
    summary_row,
)
from scripts.simulate_existing_feishu_roi_summary import parse_time


def test_simulation_generates_six_cycles_and_all_six_tables(tmp_path):
    result = simulate_roi_cycles(
        Settings(),
        start_at=datetime(2026, 6, 4, 10, 0, 0),
        cycles=6,
        interval_minutes=5,
        evidence_dir=tmp_path / "roi-evidence",
    )

    assert [cycle.summary_time for cycle in result.cycles] == [
        "2026-06-04 10:05:00",
        "2026-06-04 10:10:00",
        "2026-06-04 10:15:00",
        "2026-06-04 10:20:00",
        "2026-06-04 10:25:00",
        "2026-06-04 10:30:00",
    ]
    assert result.table_counts == {
        ORDERS_RAW: 24,
        AD_COST_RAW: 24,
        INFLUENCER_COMMISSION_RAW: 6,
        DASHBOARD_TODAY: 30,
        ROI_DAILY_SUMMARY: 30,
        PLATFORM_COMPARE: 30,
    }


def test_final_total_roi_includes_influencer_commission(tmp_path):
    result = simulate_roi_cycles(
        Settings(),
        start_at=datetime(2026, 6, 4, 10, 0, 0),
        evidence_dir=tmp_path / "roi-evidence",
    )

    total = result.cycles[-1].total_row
    assert total["平台"] == "全平台总计"
    assert total["今日达人佣金"] > 0
    assert total["真实ROI_含佣金"] < total["真实ROI_仅广告"]
    expected = round(
        (total["今日净成交额"] - total["今日广告消耗"] - total["今日达人佣金"])
        / total["今日广告消耗"]
        * 1000,
        2,
    )
    assert total["每投1000已知贡献"] == expected


def test_missing_ad_cost_keeps_roi_empty_instead_of_zero():
    row = summary_row(
        "淘宝",
        orders=[
            {
                "平台": "淘宝",
                "统计日期": "2026-06-04",
                "数据状态": "normal",
                "支付金额": 1000,
                "退款金额": 0,
                "净成交额": 1000,
            }
        ],
        ads=[],
        commissions=[],
        stat_date=date(2026, 6, 4),
        summary_time=datetime(2026, 6, 4, 10, 5, 0),
        cycle=1,
    )

    assert row["广告消耗"] is None
    assert row["真实ROI_仅广告"] is None
    assert row["每投1000净成交"] is None
    assert row["数据状态"] == "partial"


def test_existing_feishu_time_parser_accepts_seconds_precision():
    assert parse_time("2026-06-04 13:57:39").strftime("%Y-%m-%d %H:%M:%S") == "2026-06-04 13:57:39"
    assert parse_time("2026-06-04 13:57").strftime("%Y-%m-%d %H:%M:%S") == "2026-06-04 13:57:00"
