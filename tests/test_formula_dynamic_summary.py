from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import scripts.bootstrap_formula_dynamic_summary as formula_bootstrap
from scripts.bootstrap_formula_dynamic_summary import (
    FormulaSummaryBootstrap,
    ORDER_FORMULA_DATE_ALIASES,
    actual_sold_quantity_expr,
    accessory_adjusted_quantity_expr,
    dimension_rows_for_dates,
    dimension_row_matches,
    effective_sales_expr,
    formula_date_expr,
    refund_amount_expr,
    summary_formulas,
    total_dimension_row_matches,
    total_summary_formulas,
)
from scripts.verify_formula_dynamic_summary import compare_product_rows, compare_rows, expected_product_rows, expected_rows, text_value
from scripts.repair_formula_summary_product_order_sales import (
    F_GRAIN,
    F_PLATFORM,
    F_PRODUCT,
    F_PRODUCT_GROSS_SALES,
    F_PRODUCT_ORDER_COUNT,
    F_PRODUCT_QUANTITY,
    F_PRODUCT_REFUND_AMOUNT,
    F_PRODUCT_VALID_SALES,
    F_UNIQUE_KEY,
    PRODUCT_DETAIL_GRAIN,
    ProductOrderSalesRepair,
    TOTAL_PLATFORM,
)
from shopops.services.product_breakdown import ProductRule, UNCLASSIFIED_PRODUCT_NAME


def test_summary_formulas_reference_source_tables_with_filter_expressions():
    formulas = summary_formulas(
        {
            "orders": "订单明细原始表",
            "ads": "推广数据表",
            "commissions": "达人佣金明细表",
        }
    )

    assert "订单明细原始表].FILTER(" in formulas["订单数"]["expression"]
    assert 'CurrentValue.[公式_统计日期]=TEXT([统计日期],"YYYY-MM-DD")' in formulas["订单数"]["expression"]
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
    assert formulas["已知总投入"]["expression"] == "[投流消耗]+[达人佣金]"
    assert formulas["ROI"]["expression"] == "IF([投流消耗]=0,IF([达人佣金]=0,0,[有效销售额]/[达人佣金]),[有效销售额]/[投流消耗])"
    assert "[有效销售额]/[已知总投入]" in formulas["平台ROI"]["expression"]
    assert formulas["数据状态"]["expression"] == 'IF([订单数]=0,"partial",IF([投流记录数]=0&&[达人佣金]=0,"partial","normal"))'
    assert formulas["缺失项"]["expression"] == 'IF([订单数]=0,IF([投流记录数]=0&&[达人佣金]=0,"订单,投入","订单"),IF([投流记录数]=0&&[达人佣金]=0,"投入",""))'


def test_summary_list_records_retries_feishu_data_not_ready(monkeypatch):
    calls = 0

    class Helper:
        def list_records(self, table_id, field_names):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("Feishu API failed HTTP 400: {'code': 1254607}")
            return [{"fields": {"unique_key": "ok"}}]

    bootstrap = FormulaSummaryBootstrap.__new__(FormulaSummaryBootstrap)
    bootstrap.helper = Helper()
    monkeypatch.setattr(formula_bootstrap.time, "sleep", lambda seconds: None)

    assert bootstrap.list_records("table", ["unique_key"]) == [{"fields": {"unique_key": "ok"}}]
    assert calls == 3


def test_summary_list_records_retries_feishu_connection_timeout(monkeypatch):
    calls = 0

    class Helper:
        def list_records(self, table_id, field_names):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("HTTPSConnectionPool: Read timed out")
            return []

    bootstrap = FormulaSummaryBootstrap.__new__(FormulaSummaryBootstrap)
    bootstrap.helper = Helper()
    monkeypatch.setattr(formula_bootstrap.time, "sleep", lambda seconds: None)

    assert bootstrap.list_records("table") == []
    assert calls == 2


def test_dimension_readback_keeps_expected_count_after_confirming_rows():
    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.record_index_for_unique_keys = lambda table_id, field_names, keys: {
        key: {"record_id": f"rec-{key}", "fields": {"unique_key": key}}
        for key in keys
    }

    result = bootstrap.wait_for_dimension_rows(
        "summary_table",
        [{"unique_key": "2026-07-13-天猫"}, {"unique_key": "2026-07-13-全平台总计"}],
    )

    assert result == {"expected": 2, "missing_unique_keys": [], "attempts": 1}


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


def test_summary_formulas_keep_platform_aggregation_separate_from_product_detail_rows():
    rules = [ProductRule("洗面奶", ("洗面奶",), ("QBPH004",))]
    formulas = summary_formulas(
        {
            "orders": ["订单明细-天猫"],
            "ads": "推广数据表",
            "commissions": "达人佣金明细表",
        },
        rules,
    )

    order_count = formulas["订单数"]["expression"]
    assert '[商品名称]="洗面奶"' not in order_count
    assert 'CurrentValue.[洗面奶数量]>0||CurrentValue.[洗面奶有效销售额]>0' not in order_count
    assert '.[unique_key].COUNTA()' in order_count
    assert '.[公式_销售额].SUM()' in formulas["销售额"]["expression"]
    assert "CurrentValue.[商品编码]" not in order_count
    assert 'IFBLANK([商品名称],"")=""' not in formulas["投流消耗"]["expression"]
    assert "CurrentValue.[商品名称]" not in formulas["投流消耗"]["expression"]


def test_dimension_row_matches_only_plain_dimension_fields():
    expected = {"unique_key": "2026-06-07-淘宝", "统计日期": "2026-06-07", "平台": "淘宝", "店铺名称": "", "商品名称": ""}
    existing = {**expected, "订单数": 10, "销售额": 1000}

    assert dimension_row_matches(existing, expected)
    assert not dimension_row_matches({**existing, "平台": "抖音"}, expected)
    assert not dimension_row_matches({**existing, "商品名称": "新商品"}, expected)


def test_dimension_rows_for_dates_create_main_and_all_product_rows():
    rows = dimension_rows_for_dates(
        {date(2026, 7, 6)},
        [ProductRule("喷壶", ("喷壶",)), ProductRule("洗面奶", ("洗面奶",))],
        ("抖音",),
    )

    assert {row["unique_key"] for row in rows} == {
        "2026-07-06-抖音",
        "2026-07-06-抖音-喷壶",
        "2026-07-06-抖音-洗面奶",
        "2026-07-06-抖音-无商品信息订单",
    }


def test_parse_date_accepts_feishu_millisecond_timestamps():
    from scripts.bootstrap_formula_dynamic_summary import parse_date

    assert parse_date(1783180800000).isoformat() == "2026-07-05"


def test_parse_date_accepts_feishu_formula_rich_text():
    from scripts.bootstrap_formula_dynamic_summary import parse_date

    assert parse_date([{"text": "2026-07-05", "type": "text"}]).isoformat() == "2026-07-05"


def test_source_summary_verification_normalizes_formula_rich_text():
    source_records = [[
        {"fields": {"unique_key": "one", "公式_统计日期": [{"text": "2026-07-05"}], "公式_汇总平台": [{"text": "天猫"}], "公式_实际卖出数量": 2, "公式_销售额": 30, "公式_退款金额": 5, "公式_有效销售额": 25}},
    ]]
    expected = expected_rows(source_records, date(2026, 7, 5), date(2026, 7, 5))
    summary_records = [
        {"fields": {"unique_key": "2026-07-05-天猫", "订单数": 1, "实际卖出数量": 2, "销售额": 30, "退款金额": 5, "有效销售额": 25}},
        {"fields": {"unique_key": "2026-07-05-抖音", "订单数": 0, "实际卖出数量": 0, "销售额": 0, "退款金额": 0, "有效销售额": 0}},
        {"fields": {"unique_key": "2026-07-05-拼多多", "订单数": 0, "实际卖出数量": 0, "销售额": 0, "退款金额": 0, "有效销售额": 0}},
        {"fields": {"unique_key": "2026-07-05-视频号", "订单数": 0, "实际卖出数量": 0, "销售额": 0, "退款金额": 0, "有效销售额": 0}},
        {"fields": {"unique_key": "2026-07-05-全平台总计", "订单数": 1, "实际卖出数量": 2, "销售额": 30, "退款金额": 5, "有效销售额": 25}},
    ]

    comparison = compare_rows(expected, summary_records)

    assert text_value([{"text": "天猫"}]) == "天猫"
    assert all(row["matches"] for row in comparison)


def test_source_summary_product_verification_uses_importer_owned_product_fields():
    rules = [ProductRule("洗面奶", ("洗面奶",))]
    source_records = [[
        {"fields": {"unique_key": "one", "公式_统计日期": "2026-07-05", "公式_汇总平台": "天猫", "商品名称": "洁面产品", "洗面奶数量": 2, "洗面奶有效销售额": 30, "公式_实际卖出数量": 2, "公式_销售额": 30, "公式_退款金额": 5, "公式_有效销售额": 25}},
    ]]
    expected = expected_product_rows(source_records, date(2026, 7, 5), date(2026, 7, 5), rules)
    summary_records = [
        {"fields": {"unique_key": "2026-07-05-天猫-洗面奶", "订单数": 1, "实际卖出数量": 2, "销售额": 30, "退款金额": 5, "有效销售额": 25}},
        {"fields": {"unique_key": "2026-07-05-全平台总计-洗面奶", "订单数": 1, "实际卖出数量": 2, "销售额": 30, "退款金额": 5, "有效销售额": 25}},
        {"fields": {"unique_key": "2026-07-05-天猫-无商品信息订单", "订单数": 0, "实际卖出数量": 0, "销售额": 0, "退款金额": 0, "有效销售额": 0}},
        {"fields": {"unique_key": "2026-07-05-全平台总计-无商品信息订单", "订单数": 0, "实际卖出数量": 0, "销售额": 0, "退款金额": 0, "有效销售额": 0}},
    ]
    for platform in ("抖音", "拼多多", "视频号"):
        for product in ("洗面奶", "无商品信息订单"):
            summary_records.append(
                {"fields": {"unique_key": f"2026-07-05-{platform}-{product}", "订单数": 0, "实际卖出数量": 0, "销售额": 0, "退款金额": 0, "有效销售额": 0}}
            )

    comparison = compare_product_rows(expected, summary_records)

    assert len(comparison) == 10
    assert all(row["matches"] for row in comparison)


def test_source_summary_verification_requires_zero_value_platform_rows_for_impact_date():
    source_records = [[
        {"fields": {"unique_key": "one", "公式_统计日期": "2026-07-05", "公式_汇总平台": "天猫"}},
    ]]
    expected = expected_rows(
        source_records,
        date(2026, 7, 5),
        date(2026, 7, 5),
        target_dates={date(2026, 7, 5)},
    )
    comparison = compare_rows(
        expected,
        [
            {"fields": {"unique_key": "2026-07-05-天猫", "订单数": 1}},
            {"fields": {"unique_key": "2026-07-05-全平台总计", "订单数": 1}},
        ],
    )

    assert len(comparison) == 5
    assert {row["platform"] for row in comparison if not row["exists"]} == {"抖音", "拼多多", "视频号"}
    assert all("dimension_row" in row["mismatches"] for row in comparison if not row["exists"])


def test_source_summary_verification_aggregates_ad_and_commission_metrics():
    ad_records = [
        {"fields": {"unique_key": "ad_1", "公式_统计日期": "2026-07-05", "公式_汇总平台": "抖音", "公式_投流消耗": 12.5, "公式_展现": 100, "公式_点击": 8}},
    ]
    commission_records = [
        {"fields": {"unique_key": "commission_1", "公式_统计日期": "2026-07-05", "公式_汇总平台": "抖音", "公式_达人费用": 3, "公式_预估佣金支出": 4, "公式_实际佣金支出": 2}},
    ]

    expected = expected_rows(
        [],
        date(2026, 7, 5),
        date(2026, 7, 5),
        target_dates={date(2026, 7, 5)},
        ad_records=ad_records,
        commission_records=commission_records,
    )

    assert expected[("2026-07-05", "抖音")]["投流记录数"] == 1
    assert expected[("2026-07-05", "抖音")]["投流消耗"] == 12.5
    assert expected[("2026-07-05", "抖音")]["达人佣金"] == 3
    assert expected[("2026-07-05", "全平台总计")]["实际佣金支出"] == 2


def test_prepare_dimension_rows_converts_date_fields_to_unix_milliseconds():
    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.field_index = lambda table_id: {"统计日期": {"type": 5}}

    rows = bootstrap.prepare_dimension_rows(
        "summary_table",
        [{"unique_key": "2026-07-10-天猫", "统计日期": "2026-07-10", "平台": "天猫"}],
    )

    assert rows[0]["统计日期"] == 1783641600000


def test_total_summary_formulas_aggregate_all_dates_by_platform():
    formulas = total_summary_formulas("公式动态经营汇总表")

    order_count = formulas["订单数"]["expression"]
    assert "公式动态经营汇总表].FILTER(" in order_count
    assert "CurrentValue.[公式_统计日期]=[统计日期]" not in order_count
    assert "CurrentValue.[平台]=[平台]" in order_count
    assert 'IFBLANK(CurrentValue.[商品名称],"")=""' in order_count
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
    assert formulas["已知总投入"]["expression"] == "[投流消耗]+[达人佣金]"
    assert formulas["ROI"]["expression"] == "IF([投流消耗]=0,IF([达人佣金]=0,0,[有效销售额]/[达人佣金]),[有效销售额]/[投流消耗])"
    assert formulas["平台ROI"]["expression"] == "IF([已知总投入]=0,0,[有效销售额]/[已知总投入])"


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





def test_refund_amount_expr_uses_paid_amount_for_douyin_cancelled_refund_success():
    refund_field = "\u9000\u6b3e\u91d1\u989d"
    paid_field = "\u5b9e\u6536\u6b3e"
    trade_field = "\u4ea4\u6613\u72b6\u6001"
    fulfill_field = "\u5c65\u7ea6/\u552e\u540e\u72b6\u6001"
    expression = refund_amount_expr({refund_field: {}, paid_field: {}, trade_field: {}, fulfill_field: {}})

    assert f"[{refund_field}]" in expression
    assert f"[{paid_field}]" in expression
    assert f"[{trade_field}]" in expression
    assert f"[{fulfill_field}]" in expression
    assert "Cancelled" in expression
    assert "\u9000\u6b3e\u6210\u529f" in expression


def test_effective_sales_formula_zeros_non_sold_trade_statuses():
    expression = effective_sales_expr({"交易状态": {}, "履约/售后状态": {}, "有效销售额": {}})

    assert 'IFBLANK([交易状态],"")&"/"&IFBLANK([履约/售后状态],"")' in expression
    assert '.CONTAIN("已关闭")' in expression
    assert '.CONTAIN("已取消")' in expression
    assert '.CONTAIN("待付款")' in expression
    assert expression.endswith(",0,IFBLANK([有效销售额],[公式_销售额]-[公式_退款金额]))")


def test_actual_quantity_formula_zeros_non_sold_status_before_quantity_gate():
    expression = accessory_adjusted_quantity_expr({"交易状态": {}, "数量": {}, "公式_有效销售额": {}})

    assert '.CONTAIN("已关闭")' in expression
    assert '.CONTAIN("待付款")' in expression
    assert expression.endswith(",0,IF((IFBLANK([公式_有效销售额],0))>0,IFBLANK([数量],0),0))")

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
            "交易状态": {},
            "公式_有效销售额": {},
            "洗面奶数量": {},
            "皂液器数量": {},
            "配件数量": {},
            "补差价数量": {},
        },
        rules,
    )

    assert ' .CONTAIN("已关闭")'.strip() in expression
    assert expression.endswith(",0,IFBLANK([洗面奶数量],0)+IFBLANK([皂液器数量],0))")


def test_product_breakdown_bootstrap_preserves_importer_owned_numeric_fields():
    calls: list[tuple[str, str, str, str]] = []

    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.field_index = lambda table_id: {"喷壶数量": {"type": 2}}
    bootstrap.ensure_formula_field = lambda table_id, name, expression, formatter: calls.append(
        (table_id, name, expression, formatter)
    )

    bootstrap.ensure_product_breakdown_field("orders", "喷壶数量", "IF(...) ", "0")

    assert calls == []


def test_upsert_dimension_rows_skips_unchanged_existing_rows():
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class Helper:
        def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            calls.append((method, path, payload))
            return {}

    bootstrap = object.__new__(FormulaSummaryBootstrap)
    bootstrap.app_token = "app_token"
    bootstrap.helper = Helper()
    bootstrap.field_index = lambda table_id: {"统计日期": {"type": 1}}
    bootstrap.record_index_for_unique_keys = lambda table_id, field_names, unique_keys: {
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
    bootstrap.field_index = lambda table_id: {"统计日期": {"type": 1}}
    bootstrap.record_index_for_unique_keys = lambda table_id, field_names, unique_keys: {
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
        def list_records(self, table_id: str, field_names: list[str] | None = None) -> list[dict[str, Any]]:
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
        def list_records(self, table_id: str, field_names: list[str] | None = None) -> list[dict[str, Any]]:
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


def test_product_source_verification_uses_product_code_when_name_is_blank():
    rules = [ProductRule("洗面奶", ("洗面奶",), ("QBPH004",))]
    source_records = [[
        {
            "fields": {
                "unique_key": "tmall_1",
                "公式_统计日期": "2026-07-05",
                "公式_汇总平台": "天猫",
                "商品名称": "",
                "商品编码": "QBPH004",
                "公式_实际卖出数量": 2,
                "公式_销售额": 338,
                "公式_退款金额": 0,
                "公式_有效销售额": 338,
            }
        }
    ]]

    expected = expected_product_rows(source_records, date(2026, 7, 5), date(2026, 7, 5), rules)

    assert expected[("2026-07-05", "天猫", "洗面奶")]["订单数"] == 1
    assert expected[("2026-07-05", "天猫", "洗面奶")]["实际卖出数量"] == 2
    assert expected[("2026-07-05", "天猫", "无商品信息订单")]["订单数"] == 0


def test_product_repair_builds_all_platform_product_totals_from_platform_rows():
    aggregates = {
        ("2026-07-05", "天猫", "洗面奶"): {
            "order_keys": {"tmall_1"}, "quantity": 2.0, "sales": 338.0,
            "refund": 0.0, "valid_sales": 338.0, "source_rows": 1,
        },
        ("2026-07-05", "抖音", "洗面奶"): {
            "order_keys": {"douyin_1"}, "quantity": 1.0, "sales": 169.0,
            "refund": 0.0, "valid_sales": 169.0, "source_rows": 1,
        },
    }

    ProductOrderSalesRepair.add_total_platform_aggregates(aggregates)

    total = aggregates[("2026-07-05", TOTAL_PLATFORM, "洗面奶")]
    assert total["source_rows"] == 2
    assert total["quantity"] == 3.0
    assert total["sales"] == 507.0


def test_product_repair_normalizes_existing_zero_value_unclassified_detail_row():
    repair = ProductOrderSalesRepair("app", Path(".env"), "target", "product")
    key = ("2026-07-05", TOTAL_PLATFORM, UNCLASSIFIED_PRODUCT_NAME)
    rows = [
        {
            "record_id": "rec-old",
            "fields": {
                F_UNIQUE_KEY: f"{key[0]}-{key[1]}-{key[2]}",
                F_PLATFORM: TOTAL_PLATFORM,
                F_PRODUCT: "",
                F_GRAIN: "",
                F_PRODUCT_ORDER_COUNT: 0,
                F_PRODUCT_QUANTITY: 0,
                F_PRODUCT_GROSS_SALES: 0,
                F_PRODUCT_REFUND_AMOUNT: 0,
                F_PRODUCT_VALID_SALES: 0,
            },
        }
    ]

    updates, creates, _ = repair.build_row_updates(
        rows,
        {},
        {UNCLASSIFIED_PRODUCT_NAME},
    )

    assert not creates
    assert len(updates) == 1
    assert updates[0]["fields"][F_PRODUCT] == UNCLASSIFIED_PRODUCT_NAME
    assert updates[0]["fields"][F_GRAIN] == PRODUCT_DETAIL_GRAIN
