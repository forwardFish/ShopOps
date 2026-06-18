from __future__ import annotations

import json
from datetime import date

import pytest

from scripts.sync_ad_effect_dashboard_data import (
    dashboard_view_filter_property,
    ensure_dashboard_views,
    build_dashboard_rows,
    load_local_hourly_rows,
    merge_source_rows,
)


def source_row(
    stat_date: str,
    time: str,
    platform: str,
    *,
    spend: float,
    deal: float,
    orders: int,
    valid_sales: float,
    refund: float = 0,
    delta_spend: float | None = None,
    delta_deal: float | None = None,
    delta_orders: int | None = None,
    delta_valid_sales: float | None = None,
) -> dict:
    delta_spend = spend if delta_spend is None else delta_spend
    delta_deal = deal if delta_deal is None else delta_deal
    delta_orders = orders if delta_orders is None else delta_orders
    delta_valid_sales = valid_sales if delta_valid_sales is None else delta_valid_sales
    return {
        "fields": {
            "unique_key": f"{stat_date}-{time}-{platform}",
            "采集日期": stat_date,
            "平台": platform,
            "本次采集时间": f"{stat_date} {time}",
            "今日累计投流消耗": spend,
            "今日累计投流成交金额": deal,
            "今日累计投流ROI": deal / spend if spend else 0,
            "今日累计订单数": orders,
            "今日累计销售额": valid_sales + refund,
            "今日累计有效销售额": valid_sales,
            "今日累计退款金额": refund,
            "今日累计退款率": refund / (valid_sales + refund) if valid_sales + refund else 0,
            "新增投流消耗": delta_spend,
            "新增投流成交金额": delta_deal,
            "新增投流ROI": delta_deal / delta_spend if delta_spend else 0,
            "新增订单数": delta_orders,
            "新增销售额": delta_valid_sales + refund,
            "新增有效销售额": delta_valid_sales,
            "新增退款金额": 0,
            "新增退款率": 0,
        }
    }


def test_default_overview_uses_latest_total_only_not_sum_of_hourly_snapshots():
    records = [
        source_row(
            "2026-06-18",
            "10:00:00",
            "总计",
            spend=1500,
            deal=3300,
            orders=15,
            valid_sales=3000,
            refund=300,
            delta_spend=500,
            delta_deal=1300,
            delta_orders=5,
            delta_valid_sales=1200,
        ),
        source_row("2026-06-18", "09:00:00", "总计", spend=1000, deal=2000, orders=10, valid_sales=1800),
    ]

    rows = build_dashboard_rows(records, today=date(2026, 6, 18))
    overview = next(row for row in rows if row["展示粒度"] == "默认总览")

    assert overview["投流消耗"] == 1500
    assert overview["投流成交金额"] == 3300
    assert overview["有效销售额"] == 3000
    assert overview["订单数"] == 15
    assert overview["单订单投流成本"] == 100
    assert overview["退款率"] == pytest.approx(300 / 3300)
    assert "有效销售额 3000.00" in overview["今日投流结论"]


def test_hour_rows_keep_all_dates_so_previous_day_can_be_filtered():
    records = [
        source_row("2026-06-17", "09:00:00", "总计", spend=800, deal=1000, orders=4, valid_sales=900),
        source_row("2026-06-18", "09:00:00", "总计", spend=1000, deal=2000, orders=10, valid_sales=1800),
    ]

    rows = build_dashboard_rows(records, today=date(2026, 6, 18))
    hour_rows = [row for row in rows if row["展示粒度"] == "按小时"]

    assert {row["采集日期"] for row in hour_rows} == {"2026-06-17", "2026-06-18"}
    assert {row["数据口径"] for row in hour_rows} == {"按小时看：每次采集相对上一轮的新增/区间值"}


def test_platform_rows_use_each_dates_latest_collection_time():
    records = [
        source_row("2026-06-18", "09:00:00", "天猫", spend=800, deal=1000, orders=4, valid_sales=900),
        source_row("2026-06-18", "10:00:00", "天猫", spend=1200, deal=1800, orders=8, valid_sales=1600),
        source_row("2026-06-18", "10:00:00", "抖音", spend=300, deal=1500, orders=7, valid_sales=1400),
        source_row("2026-06-18", "10:00:00", "总计", spend=1500, deal=3300, orders=15, valid_sales=3000),
    ]

    rows = build_dashboard_rows(records, today=date(2026, 6, 18))
    platform_rows = [row for row in rows if row["展示粒度"] == "按平台"]

    assert {row["平台"] for row in platform_rows} == {"天猫", "抖音", "总计"}
    tmall = next(row for row in platform_rows if row["平台"] == "天猫")
    assert tmall["本次采集时间"] == "2026-06-18 10:00:00"
    assert tmall["投流消耗"] == 1200


def test_local_hourly_evidence_can_supply_latest_overview_when_feishu_list_lags(tmp_path):
    evidence = tmp_path / "hourly-shopops-import-20260618-141143.json"
    evidence.write_text(
        json.dumps(
            {
                "hourly_interval_summary": {
                    "rows": [
                        source_row(
                            "2026-06-18",
                            "14:11:43",
                            "总计",
                            spend=3261.72,
                            deal=7605,
                            orders=90,
                            valid_sales=13520,
                        )["fields"]
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    feishu_records = [
        source_row("2026-06-18", "03:58:09", "总计", spend=500, deal=900, orders=8, valid_sales=1200),
    ]

    local_rows = load_local_hourly_rows(tmp_path)
    merged_rows = merge_source_rows(feishu_records, local_rows)
    rows = build_dashboard_rows(merged_rows, today=date(2026, 6, 18))
    overview = next(row for row in rows if row["展示粒度"] == "默认总览")

    assert len(local_rows) == 1
    assert overview["本次采集时间"] == "2026-06-18 14:11:43"
    assert overview["投流消耗"] == 3261.72
    assert overview["投流成交金额"] == 7605
    assert overview["订单数"] == 90
    assert overview["有效销售额"] == 13520


def test_dashboard_view_filter_property_filters_by_display_grain():
    prop = dashboard_view_filter_property({"field_id": "fldGrain", "type": 1}, "默认总览")

    condition = prop["filter_info"]["conditions"][0]
    assert condition["field_id"] == "fldGrain"
    assert condition["field_type"] == 1
    assert condition["operator"] == "is"
    assert json.loads(condition["value"]) == ["默认总览"]


def test_ensure_dashboard_views_patches_grain_filters():
    class FakeClient:
        app_token = "app"

        def __init__(self):
            self.views = [
                {"view_id": "vew_default", "view_name": "默认总览", "view_type": "grid"},
                {"view_id": "vew_hour", "view_name": "按小时变化", "view_type": "grid"},
                {"view_id": "vew_day", "view_name": "按天汇总", "view_type": "grid"},
                {"view_id": "vew_platform", "view_name": "按平台最新", "view_type": "grid"},
            ]
            self.patches = []

        def field_index(self, table_id):
            assert table_id == "tbl"
            return {"展示粒度": {"field_id": "fldGrain", "type": 1}}

        def request(self, method, path, payload=None, params=None):
            if method == "GET" and path.endswith("/views"):
                return {"items": list(self.views)}
            if method == "PATCH":
                self.patches.append((path, payload))
                return {"view": {}}
            raise AssertionError((method, path, payload, params))

    fake = FakeClient()
    ensure_dashboard_views(fake, "tbl")

    values_by_view = {
        path.rsplit("/", 1)[-1]: json.loads(payload["property"]["filter_info"]["conditions"][0]["value"])[0]
        for path, payload in fake.patches
    }
    assert values_by_view == {
        "vew_default": "默认总览",
        "vew_hour": "按小时",
        "vew_day": "按天",
        "vew_platform": "按平台",
    }
