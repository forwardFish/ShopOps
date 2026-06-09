from __future__ import annotations

from datetime import datetime

from shopops.services.dynamic_feishu_summary import SourceTableRows, TOTAL_PLATFORM, build_dynamic_summary


def test_dynamic_summary_groups_three_source_tables_by_date_and_platform():
    result = build_dynamic_summary(
        SourceTableRows(
            orders=[
                {
                    "fields": {
                        "创建时间": "2026-06-07 10:00:00",
                        "平台": "抖音",
                        "订单号": "DY1",
                        "支付金额": 1000,
                        "退款金额": 100,
                        "商品成本": 300,
                        "运费": 20,
                        "平台扣点": 30,
                    }
                },
                {
                    "fields": {
                        "创建时间": "2026-06-07 10:05:00",
                        "平台": "抖音",
                        "订单号": "DY2",
                        "支付金额": 500,
                        "退款金额": 0,
                        "商品成本": 120,
                    }
                },
                {
                    "fields": {
                        "创建时间": "2026-06-07 10:10:00",
                        "平台": "淘宝/天猫",
                        "订单号": "TB1",
                        "实收款": "800",
                    }
                },
            ],
            ads=[
                {"fields": {"投放日期": "2026-06-07", "平台": "抖音", "消耗金额": 300, "展现": 10000, "点击": 500}},
                {"fields": {"投放日期": "2026-06-07", "平台": "淘宝", "花费": 200}},
            ],
            commissions=[
                {"fields": {"结算日期": "2026-06-07", "平台": "抖音", "预估佣金": 150, "技术服务费": 15}},
            ],
        ),
        summary_time=datetime(2026, 6, 7, 12, 0, 0),
    )

    douyin = next(row for row in result.summary_rows if row["平台"] == "抖音")
    assert douyin["订单数"] == 2
    assert douyin["销售额"] == 1500
    assert douyin["退款金额"] == 100
    assert douyin["有效销售额"] == 1400
    assert douyin["达人佣金"] == 150
    assert douyin["投流消耗"] == 300
    assert douyin["商品成本"] == 420
    assert douyin["ROI"] == 4.6667
    assert douyin["平台ROI"] == 3.1111
    assert douyin["经营利润估算"] == 480
    assert douyin["利润率"] == 0.3429
    assert douyin["数据状态"] == "normal"

    total = next(row for row in result.summary_rows if row["平台"] == TOTAL_PLATFORM)
    assert total["订单数"] == 3
    assert total["有效销售额"] == 2200
    assert total["投流消耗"] == 500
    assert total["达人佣金"] == 150
    assert total["ROI"] == 4.4


def test_dynamic_summary_marks_missing_ad_data_partial_without_fake_zero_roi():
    result = build_dynamic_summary(
        SourceTableRows(
            orders=[
                {
                    "fields": {
                        "下单时间": "2026-06-07 09:10:11",
                        "平台": "视频号",
                        "支付金额": 600,
                        "商品成本": 200,
                    }
                }
            ],
            ads=[],
            commissions=[{"fields": {"支付时间": "2026-06-07 09:11:00", "平台": "视频号", "带货费用": 60}}],
        ),
        summary_time=datetime(2026, 6, 7, 12, 0, 0),
    )

    row = next(row for row in result.summary_rows if row["平台"] == "视频号")
    assert row["有效销售额"] == 600
    assert row["投流消耗"] is None
    assert row["ROI"] is None
    assert row["达人佣金"] == 60
    assert row["已知费用后利润"] == 340
    assert row["已知费用利润率"] == 0.5667
    assert row["经营利润估算"] is None
    assert row["数据状态"] == "partial"
    assert row["缺失项"] == "投流"


def test_dynamic_summary_accepts_real_feishu_commission_field_aliases():
    result = build_dynamic_summary(
        SourceTableRows(
            orders=[{"fields": {"创建时间": "2026-06-07 10:00:00", "平台": "抖音", "实收款": 1000}}],
            ads=[{"fields": {"采集时间": "2026-06-07 10:05:00", "平台": "抖音", "花费": 200}}],
            commissions=[
                {
                    "fields": {
                        "支付时间": "2026-06-07 10:01:00",
                        "平台": "抖音",
                        "带货费用": "88.5",
                        "技术服务费": "8.5",
                    }
                }
            ],
        ),
        summary_time=datetime(2026, 6, 7, 12, 0, 0),
    )

    row = next(row for row in result.summary_rows if row["平台"] == "抖音")
    assert row["达人佣金"] == 88.5
    assert row["已知总投入"] == 288.5
    assert row["平台ROI"] == 3.4662


def test_dynamic_summary_uses_order_created_time_not_payment_or_import_time():
    result = build_dynamic_summary(
        SourceTableRows(
            orders=[
                {
                    "fields": {
                        "创建时间": "2026-06-07 23:59:00",
                        "支付时间": "2026-06-08 00:01:00",
                        "采集时间": "2026-06-08 13:20:00",
                        "统计日期": "2026-06-08",
                        "平台": "拼多多",
                        "订单号": "P1",
                        "实收款": 100,
                    }
                }
            ],
            ads=[],
            commissions=[],
        ),
        summary_time=datetime(2026, 6, 8, 13, 30, 0),
    )

    pdd = next(row for row in result.summary_rows if row["平台"] == "拼多多")
    assert pdd["统计日期"] == "2026-06-07"
    assert pdd["订单数"] == 1
