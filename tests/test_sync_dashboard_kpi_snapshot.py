from __future__ import annotations

from datetime import date

from scripts.sync_dashboard_kpi_snapshot import (
    DashboardKpiSnapshotSync,
    TOTAL_PLATFORM,
    build_kpi_dimension_rows,
    kpi_formulas,
    period_filter_expr,
    period_platform_filter_expr,
)


def test_kpi_dimension_rows_include_today_last7_and_last30_only_as_dimensions():
    rows = build_kpi_dimension_rows(
        [
            {"fields": {"统计日期": "2026-06-07", "平台": "天猫", "销售额": 100}},
            {"fields": {"统计日期": "2026-06-07", "平台": "拼多多", "销售额": 200}},
            {"fields": {"统计日期": "2026-06-07", "平台": TOTAL_PLATFORM, "销售额": 300}},
        ],
        today=date(2026, 6, 7),
    )

    assert len(rows) == 9
    assert {
        (row["unique_key"], row["期间"], row["开始日期"], row["结束日期"], row["平台"])
        for row in rows
    } == {
        ("今日-天猫", "今日", "2026-06-07", "2026-06-07", "天猫"),
        ("今日-拼多多", "今日", "2026-06-07", "2026-06-07", "拼多多"),
        (f"今日-{TOTAL_PLATFORM}", "今日", "2026-06-07", "2026-06-07", TOTAL_PLATFORM),
        ("最近7天-天猫", "最近7天", "2026-06-01", "2026-06-07", "天猫"),
        ("最近7天-拼多多", "最近7天", "2026-06-01", "2026-06-07", "拼多多"),
        (f"最近7天-{TOTAL_PLATFORM}", "最近7天", "2026-06-01", "2026-06-07", TOTAL_PLATFORM),
        ("最近30天-天猫", "最近30天", "2026-05-09", "2026-06-07", "天猫"),
        ("最近30天-拼多多", "最近30天", "2026-05-09", "2026-06-07", "拼多多"),
        (f"最近30天-{TOTAL_PLATFORM}", "最近30天", "2026-05-09", "2026-06-07", TOTAL_PLATFORM),
    }
    assert all("销售额" not in row and "ROI" not in row for row in rows)


def test_kpi_dimension_keys_stay_fixed_when_today_changes():
    source = [{"fields": {"统计日期": "2026-06-07", "平台": "天猫"}}]

    june8_rows = build_kpi_dimension_rows(source, today=date(2026, 6, 8))
    june9_rows = build_kpi_dimension_rows(source, today=date(2026, 6, 9))

    assert {row["unique_key"] for row in june8_rows} == {row["unique_key"] for row in june9_rows}
    assert next(row for row in june9_rows if row["unique_key"] == "今日-天猫") == {
        "unique_key": "今日-天猫",
        "期间": "今日",
        "开始日期": "2026-06-09",
        "结束日期": "2026-06-09",
        "平台": "天猫",
        "来源表": "tblepMIg19Ov1kSw",
    }


def test_kpi_formulas_filter_source_summary_by_period_and_platform():
    formulas = kpi_formulas("公式动态经营汇总表")
    expected_filter = (
        "[公式动态经营汇总表].FILTER("
        "CurrentValue.[统计日期]>=[开始日期]&&"
        "CurrentValue.[统计日期]<=[结束日期]&&"
        "CurrentValue.[平台]=[平台]"
        ")"
    )

    assert period_filter_expr("公式动态经营汇总表") == expected_filter
    expected_tmall_refund_filter = (
        "[公式动态经营汇总表].FILTER("
        "CurrentValue.[统计日期]>=[开始日期]&&"
        "CurrentValue.[统计日期]<=[结束日期]&&"
        'CurrentValue.[平台]="天猫"'
        ")"
    )

    assert period_platform_filter_expr("公式动态经营汇总表", "天猫") == expected_tmall_refund_filter
    assert formulas["销售额"]["expression"] == (
        f'IF([平台]="{TOTAL_PLATFORM}",'
        f"{expected_filter}.[销售额].SUM()-{expected_tmall_refund_filter}.[退款金额].SUM(),"
        f"{expected_filter}.[销售额].SUM())"
    )
    assert formulas["实际卖出数量"]["expression"] == f"{expected_filter}.[实际卖出数量].SUM()"
    assert formulas["源表记录数"]["expression"] == f"{expected_filter}.[unique_key].COUNTA()"


def test_kpi_ratio_formulas_use_period_totals_not_daily_ratio_sums():
    formulas = kpi_formulas("公式动态经营汇总表")

    assert formulas["ROI"]["expression"] == "IF([投流记录数]=0,0,IF([投流消耗]=0,0,[有效销售额]/[投流消耗]))"
    assert formulas["平台ROI"]["expression"] == "IF([投流记录数]=0,0,IF([已知总投入]=0,0,[有效销售额]/[已知总投入]))"
    assert "SUM" not in formulas["ROI"]["expression"]
    assert "SUM" not in formulas["平台ROI"]["expression"]


def test_kpi_formula_sync_rejects_non_period_total_table():
    sync = object.__new__(DashboardKpiSnapshotSync)
    sync.field_index = lambda table_id: {"unique_key": {}, "统计范围": {}, "平台": {}}

    try:
        sync.assert_kpi_dimension_table("tblufREIgBB4VBAg")
    except RuntimeError as exc:
        assert "not a KPI period table" in str(exc)
        assert "开始日期" in str(exc)
    else:
        raise AssertionError("Expected non-KPI total table to be rejected")


def test_kpi_readback_uses_requested_today_for_total_samples():
    expected_keys = [
        "今日-全平台总计",
        "最近7天-全平台总计",
        "最近30天-全平台总计",
    ]

    class Helper:
        def list_records(self, table_id: str):
            return [{"fields": {"unique_key": key, "结束日期": "2026-06-09"}} for key in expected_keys]

    sync = object.__new__(DashboardKpiSnapshotSync)
    sync.helper = Helper()

    readback = sync.readback("table", expected_keys, today=date(2026, 6, 9))

    assert readback["matched_count"] == 3
    assert set(readback["total_platform_rows"]) == set(expected_keys)
