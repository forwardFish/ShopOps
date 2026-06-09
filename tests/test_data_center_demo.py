from __future__ import annotations

from datetime import datetime

from shopops.config import Settings
from shopops.services.data_center_demo import (
    AD_TABLE,
    F_AD_COST,
    F_AVG_ORDER_VALUE,
    F_BACKEND_ROI,
    F_CLICKS,
    F_COLLECTED_AT,
    F_CPC,
    F_CTR,
    F_DIFF,
    F_IMPRESSIONS,
    F_NET_GMV,
    F_PLATFORM,
    F_STAT_DATE,
    F_TODAY_COST,
    F_TODAY_GMV,
    F_TODAY_ORDERS,
    F_TOTAL_GMV,
    F_TOTAL_ORDERS,
    F_TOTAL_REFUND,
    F_TRUE_ROI,
    ORDER_TABLE,
    PLATFORMS,
    SUMMARY_TABLE,
    TOTAL_PLATFORM_NAME,
    data_center_specs,
    demo_ad_rows,
    demo_dataset,
    demo_order_rows,
    demo_summary_rows,
    write_local_dataset,
)


def test_demo_orders_cover_all_requested_platforms_and_compute_net_metrics():
    rows = demo_order_rows(datetime(2026, 6, 4).date())

    assert [row[F_PLATFORM] for row in rows] == list(PLATFORMS)
    assert all(row[F_STAT_DATE] == "2026-06-04" for row in rows)
    for row in rows:
        assert row[F_NET_GMV] == round(row[F_TOTAL_GMV] - row[F_TOTAL_REFUND], 2)
        assert row[F_AVG_ORDER_VALUE] == round(row[F_NET_GMV] / row[F_TOTAL_ORDERS], 2)


def test_demo_ads_compute_click_metrics_and_true_roi_from_orders():
    now = datetime(2026, 6, 4, 15, 30)
    orders = {row[F_PLATFORM]: row for row in demo_order_rows(now.date())}
    rows = demo_ad_rows(now)

    assert [row[F_PLATFORM] for row in rows] == list(PLATFORMS)
    for row in rows:
        assert row[F_COLLECTED_AT] == "2026-06-04 15:30:00"
        assert row[F_CTR] == round(row[F_CLICKS] / row[F_IMPRESSIONS], 4)
        assert row[F_CPC] == round(row[F_AD_COST] / row[F_CLICKS], 4)
        assert row[F_TRUE_ROI] == round(orders[row[F_PLATFORM]][F_NET_GMV] / row[F_AD_COST], 4)


def test_summary_rows_include_platforms_and_total_roi():
    now = datetime(2026, 6, 4, 15, 30)
    rows = demo_summary_rows(now)

    assert [row[F_PLATFORM] for row in rows] == [*PLATFORMS, TOTAL_PLATFORM_NAME]
    total = rows[-1]
    platform_rows = rows[:-1]
    assert total[F_TODAY_COST] == round(sum(row[F_TODAY_COST] for row in platform_rows), 2)
    assert total[F_TODAY_GMV] == round(sum(row[F_TODAY_GMV] for row in platform_rows), 2)
    assert total[F_TODAY_ORDERS] == sum(row[F_TODAY_ORDERS] for row in platform_rows)
    assert total[F_TRUE_ROI] == round(total[F_TODAY_GMV] / total[F_TODAY_COST], 4)
    assert total[F_BACKEND_ROI] is None
    assert total[F_DIFF] is None


def test_data_center_has_three_tables_only_with_chinese_runtime_names():
    specs = data_center_specs()

    assert [spec.name for spec in specs] == [AD_TABLE, ORDER_TABLE, SUMMARY_TABLE]
    assert [spec.key for spec in specs] == ["ad_data", "order_data", "summary_dashboard"]
    assert AD_TABLE == "投流数据表"
    assert ORDER_TABLE == "订单数据表"
    assert SUMMARY_TABLE == "实时汇总看板"


def test_write_local_dataset_writes_all_three_tables(tmp_path):
    settings = Settings(
        local_feishu_path=str(tmp_path / "local_feishu.json"),
        pending_records_path=str(tmp_path / "pending.jsonl"),
    )

    result = write_local_dataset(settings, datetime(2026, 6, 4, 15, 30))
    dataset = demo_dataset(datetime(2026, 6, 4, 15, 30))

    assert result.mode == "local"
    assert result.saved_count == sum(len(rows) for rows in dataset.values())
    assert result.local_path is not None
