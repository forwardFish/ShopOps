from __future__ import annotations

from typing import Any

from scripts.bootstrap_formula_dynamic_summary import (
    FormulaSummaryBootstrap,
    ORDER_FORMULA_DATE_ALIASES,
    actual_sold_quantity_expr,
    accessory_adjusted_quantity_expr,
    dimension_row_matches,
    formula_date_expr,
    summary_formulas,
    total_dimension_row_matches,
    total_summary_formulas,
)
from shopops.services.product_breakdown import ProductRule


def test_summary_formulas_reference_source_tables_with_filter_expressions():
    formulas = summary_formulas(
        {
            "orders": "订单明细原始表",
            "ads": "推广数据表",
            "commissions": "达人佣金明细表",
        }
    )

    assert "订单明细原始表].FILTER(" in formulas["订单数"]["expression"]
    assert "CurrentValue.[公式_统计日期]=[统计日期]" in formulas["订单数"]["expression"]
    assert '([平台]="全平台总计"||CurrentValue.[平台]=[平台])' in formulas["订单数"]["expression"]
    assert "CurrentValue.[店铺名称]" not in formulas["订单数"]["expression"]
    assert "CurrentValue.[商品名称]" not in formulas["订单数"]["expression"]
    assert formulas["实际卖出数量"]["expression"].endswith("[公式_实际卖出数量].SUM()")
    assert formulas["销售额"]["expression"].endswith("[公式_销售额].SUM()")
    assert formulas["退款金额"]["expression"].endswith("[公式_退款金额].SUM()")
    assert formulas["有效销售额"]["expression"].endswith("[公式_有效销售额].SUM()")
    assert formulas["投流记录数"]["expression"].endswith("[unique_key].COUNTA()")
    assert formulas["投流消耗"]["expression"].endswith("[公式_投流消耗].SUM()")
    assert formulas["展现"]["expression"].endswith("[公式_展现].SUM()")
    assert formulas["点击"]["expression"].endswith("[公式_点击].SUM()")
    assert formulas["达人佣金"]["expression"].endswith("[公式_达人费用].SUM()")
    assert formulas["预估佣金支出"]["expression"].endswith("[公式_预估佣金支出].SUM()")
    assert formulas["实际佣金支出"]["expression"].endswith("[公式_实际佣金支出].SUM()")
    assert "[有效销售额]/[投流消耗]" in formulas["ROI"]["expression"]
    assert "[有效销售额]/[已知总投入]" in formulas["平台ROI"]["expression"]
    assert formulas["数据状态"]["expression"] == 'IF([订单数]=0,"partial",IF([投流记录数]=0,"partial","normal"))'
    assert formulas["缺失项"]["expression"] == 'IF([订单数]=0,IF([投流记录数]=0,"订单,投流","订单"),IF([投流记录数]=0,"投流",""))'


def test_summary_formulas_sum_all_platform_order_tables():
    formulas = summary_formulas(
        {
            "orders": ["订单明细-天猫", "订单明细-抖音", "订单明细-拼多多", "订单明细-视频号"],
            "ads": "推广数据表",
            "commissions": "达人佣金明细表",
        }
    )

    order_count = formulas["订单数"]["expression"]
    assert "订单明细-天猫].FILTER(" in order_count
    assert "订单明细-抖音].FILTER(" in order_count
    assert "订单明细-拼多多].FILTER(" in order_count
    assert "订单明细-视频号].FILTER(" in order_count
    assert order_count.count(".COUNTA()") == 4
    assert formulas["销售额"]["expression"].count(".[公式_销售额].SUM()") == 4


def test_dimension_row_matches_only_plain_dimension_fields():
    expected = {"unique_key": "2026-06-07-淘宝", "统计日期": "2026-06-07", "平台": "淘宝", "店铺名称": "", "商品名称": ""}
    existing = {**expected, "订单数": 10, "销售额": 1000}

    assert dimension_row_matches(existing, expected)
    assert not dimension_row_matches({**existing, "平台": "抖音"}, expected)
    assert not dimension_row_matches({**existing, "商品名称": "新商品"}, expected)


def test_total_summary_formulas_aggregate_all_dates_by_platform():
    formulas = total_summary_formulas("公式动态经营汇总表")

    order_count = formulas["订单数"]["expression"]
    assert "公式动态经营汇总表].FILTER(" in order_count
    assert "CurrentValue.[公式_统计日期]=[统计日期]" not in order_count
    assert "CurrentValue.[平台]=[平台]" in order_count
    assert "订单明细原始表" not in order_count
    assert "推广数据表" not in "".join(config["expression"] for config in formulas.values())
    assert "达人佣金明细表" not in "".join(config["expression"] for config in formulas.values())
    assert formulas["汇总key"]["expression"] == '[统计范围]&"-"&[平台]'
    assert formulas["订单数"]["expression"].endswith("[订单数].SUM()")
    assert formulas["实际卖出数量"]["expression"].endswith("[实际卖出数量].SUM()")
    assert formulas["销售额"]["expression"].endswith("[销售额].SUM()")
    assert formulas["退款金额"]["expression"].endswith("[退款金额].SUM()")
    assert formulas["投流消耗"]["expression"].endswith("[投流消耗].SUM()")
    assert formulas["达人佣金"]["expression"].endswith("[达人佣金].SUM()")
    assert formulas["预估佣金支出"]["expression"].endswith("[预估佣金支出].SUM()")
    assert formulas["实际佣金支出"]["expression"].endswith("[实际佣金支出].SUM()")
    assert "[有效销售额]/[投流消耗]" in formulas["ROI"]["expression"]


def test_total_dimension_row_matches_only_total_dimension_fields():
    expected = {"unique_key": "all-days-抖音", "统计范围": "所有天数", "平台": "抖音", "店铺名称": "", "商品名称": ""}
    existing = {**expected, "订单数": 10, "销售额": 1000}

    assert total_dimension_row_matches(existing, expected)
    assert not total_dimension_row_matches({**existing, "统计范围": "今天"}, expected)
    assert not total_dimension_row_matches({**existing, "店铺名称": "新店"}, expected)


def test_order_formula_date_aliases_use_created_time_before_payment_or_import_time():
    expression = formula_date_expr(
        {
            "创建时间": {},
            "支付时间": {},
            "采集时间": {},
            "订单成交时间": {},
        },
        ORDER_FORMULA_DATE_ALIASES,
    )

    assert expression == "LEFT(IFBLANK([创建时间],[订单成交时间]),10)"
    assert "支付时间" not in expression
    assert "采集时间" not in expression


def test_actual_quantity_formula_uses_valid_sales_gate():
    expression = accessory_adjusted_quantity_expr({"是否是配件": {}, "数量": {}, "公式_有效销售额": {}})

    assert expression == "IF((IFBLANK([公式_有效销售额],0))>0,IFBLANK([数量],0),0)"


def test_actual_sold_quantity_formula_uses_main_product_quantities_when_available():
    rules = [
        ProductRule("洗面奶", ("洗面奶",)),
        ProductRule("皂液器", ("皂液器",)),
        ProductRule("配件", ("配件",)),
        ProductRule("补差价", ("补差价",)),
    ]
    expression = actual_sold_quantity_expr(
        {
            "数量": {},
            "公式_有效销售额": {},
            "洗面奶数量": {},
            "皂液器数量": {},
            "配件数量": {},
            "补差价数量": {},
        },
        rules,
    )

    assert expression == "IFBLANK([洗面奶数量],0)+IFBLANK([皂液器数量],0)"


def test_upsert_dimension_rows_skips_unchanged_existing_rows():
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class Helper:
        def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            calls.append((method, path, payload))
            return {}

    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.app_token = "app_token"
    bootstrap.helper = Helper()
    bootstrap.record_index = lambda table_id: {
        "2026-06-07-淘宝": {
            "record_id": "rec_1",
            "fields": {"unique_key": "2026-06-07-淘宝", "统计日期": "2026-06-07", "平台": "淘宝"},
        },
        "2026-06-07-抖音": {
            "record_id": "rec_2",
            "fields": {"unique_key": "2026-06-07-抖音", "统计日期": "2026-06-07", "平台": "旧平台"},
        },
    }

    saved = bootstrap.upsert_dimension_rows(
        "summary_table",
        [
            {"unique_key": "2026-06-07-淘宝", "统计日期": "2026-06-07", "平台": "淘宝"},
            {"unique_key": "2026-06-07-抖音", "统计日期": "2026-06-07", "平台": "抖音"},
            {"unique_key": "2026-06-07-全平台总计", "统计日期": "2026-06-07", "平台": "全平台总计"},
        ],
    )

    assert saved == 2
    assert len(calls) == 2
    assert calls[0][1].endswith("/records/batch_create")
    assert calls[0][2] == {
        "records": [{"fields": {"unique_key": "2026-06-07-全平台总计", "统计日期": "2026-06-07", "平台": "全平台总计"}}]
    }
    assert calls[1][1].endswith("/records/batch_update")
    assert calls[1][2] == {
        "records": [{"record_id": "rec_2", "fields": {"unique_key": "2026-06-07-抖音", "统计日期": "2026-06-07", "平台": "抖音"}}]
    }


def test_upsert_total_dimension_rows_skips_unchanged_existing_rows():
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class Helper:
        def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            calls.append((method, path, payload))
            return {}

    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.app_token = "app_token"
    bootstrap.helper = Helper()
    bootstrap.record_index = lambda table_id: {
        "all-days-淘宝": {
            "record_id": "rec_1",
            "fields": {"unique_key": "all-days-淘宝", "统计范围": "所有天数", "平台": "淘宝"},
        },
        "all-days-抖音": {
            "record_id": "rec_2",
            "fields": {"unique_key": "all-days-抖音", "统计范围": "历史", "平台": "抖音"},
        },
    }

    saved = bootstrap.upsert_total_dimension_rows(
        "total_summary_table",
        [
            {"unique_key": "all-days-淘宝", "统计范围": "所有天数", "平台": "淘宝"},
            {"unique_key": "all-days-抖音", "统计范围": "所有天数", "平台": "抖音"},
            {"unique_key": "all-days-全平台总计", "统计范围": "所有天数", "平台": "全平台总计"},
        ],
    )

    assert saved == 2
    assert len(calls) == 2
    assert calls[0][1].endswith("/records/batch_create")
    assert calls[0][2] == {
        "records": [{"fields": {"unique_key": "all-days-全平台总计", "统计范围": "所有天数", "平台": "全平台总计"}}]
    }
    assert calls[1][1].endswith("/records/batch_update")
    assert calls[1][2] == {
        "records": [{"record_id": "rec_2", "fields": {"unique_key": "all-days-抖音", "统计范围": "所有天数", "平台": "抖音"}}]
    }


def test_dimension_rows_from_summary_reuses_existing_dates_and_platforms():
    class Helper:
        def list_records(self, table_id: str) -> list[dict[str, Any]]:
            return [
                {"fields": {"统计日期": "2026-06-01", "平台": "淘宝"}},
                {"fields": {"统计日期": "2026-06-01", "平台": "小红书"}},
            ]

    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.helper = Helper()

    rows = bootstrap.dimension_rows_from_summary("summary_table", days_ahead=-1)

    assert {"unique_key": "2026-06-01-淘宝", "统计日期": "2026-06-01", "平台": "淘宝", "店铺名称": "", "商品名称": ""} in rows
    assert {"unique_key": "2026-06-01-全平台总计", "统计日期": "2026-06-01", "平台": "全平台总计", "店铺名称": "", "商品名称": ""} in rows
    assert {"unique_key": "2026-06-01-小红书", "统计日期": "2026-06-01", "平台": "小红书", "店铺名称": "", "商品名称": ""} in rows


def test_total_dimension_rows_from_summary_reuses_platforms_without_dates():
    class Helper:
        def list_records(self, table_id: str) -> list[dict[str, Any]]:
            return [
                {"fields": {"统计日期": "2026-06-01", "平台": "淘宝"}},
                {"fields": {"统计日期": "2026-06-02", "平台": "小红书"}},
            ]

    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.helper = Helper()

    rows = bootstrap.total_dimension_rows_from_summary("summary_table")

    assert {"unique_key": "all-days-淘宝", "统计范围": "所有天数", "平台": "淘宝", "店铺名称": "", "商品名称": ""} in rows
    assert {"unique_key": "all-days-抖音", "统计范围": "所有天数", "平台": "抖音", "店铺名称": "", "商品名称": ""} in rows
    assert {"unique_key": "all-days-全平台总计", "统计范围": "所有天数", "平台": "全平台总计", "店铺名称": "", "商品名称": ""} in rows
    assert {"unique_key": "all-days-小红书", "统计范围": "所有天数", "平台": "小红书", "店铺名称": "", "商品名称": ""} in rows


def test_total_dimension_rows_uses_default_platforms_without_summary_table():
    bootstrap = object.__new__(FormulaSummaryBootstrap)

    rows = bootstrap.total_dimension_rows()

    assert rows == [
        {"unique_key": "all-days-天猫", "统计范围": "所有天数", "平台": "天猫", "店铺名称": "", "商品名称": ""},
        {"unique_key": "all-days-抖音", "统计范围": "所有天数", "平台": "抖音", "店铺名称": "", "商品名称": ""},
        {"unique_key": "all-days-拼多多", "统计范围": "所有天数", "平台": "拼多多", "店铺名称": "", "商品名称": ""},
        {"unique_key": "all-days-视频号", "统计范围": "所有天数", "平台": "视频号", "店铺名称": "", "商品名称": ""},
        {"unique_key": "all-days-全平台总计", "统计范围": "所有天数", "平台": "全平台总计", "店铺名称": "", "商品名称": ""},
    ]
