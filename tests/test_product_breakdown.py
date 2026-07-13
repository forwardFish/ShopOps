from __future__ import annotations

from shopops.services.product_breakdown import (
    best_product_rule_for_order,
    best_product_rule_from_order_fields,
    effective_sales_amount,
    extract_product_code_from_raw,
    order_product_formula_fields,
    product_breakdown_values,
    product_rules_from_records,
    summary_product_formula_fields,
    total_product_formula_fields,
)


def test_product_rules_use_catalog_keywords_and_build_two_fields_per_product():
    rules = product_rules_from_records(
        [
            {"fields": {"商品名称": "喷壶", "搜索关键词": "喷壶"}},
            {"fields": {"商品名称": "两用喷壶", "搜索关键词": "两用喷壶, 双用"}},
        ]
    )

    assert [rule.name for rule in rules] == ["喷壶", "两用喷壶"]
    assert rules[1].keywords == ("两用喷壶", "双用")

    formulas = order_product_formula_fields(rules)

    assert set(formulas) == {"喷壶数量", "喷壶有效销售额", "两用喷壶数量", "两用喷壶有效销售额"}
    assert '[商品名称].CONTAIN("喷壶")' in formulas["喷壶数量"]["expression"]
    assert "[数量]" in formulas["喷壶数量"]["expression"]
    assert "[公式_实际卖出数量]" not in formulas["喷壶数量"]["expression"]
    assert "[公式_有效销售额]" in formulas["喷壶有效销售额"]["expression"]


def test_summary_and_total_product_formulas_sum_product_fields():
    rules = product_rules_from_records([{"fields": {"商品名称": "洗面奶", "搜索关键词": "洗面奶"}}])

    summary = summary_product_formula_fields(["订单明细-天猫", "订单明细-抖音"], rules)
    total = total_product_formula_fields("公式动态经营汇总表", rules)

    expression = summary["洗面奶数量"]["expression"]
    assert 'IFBLANK([商品名称],"")=""' in expression
    assert '[商品名称]="洗面奶"' in expression
    assert "CurrentValue.[商品名称]" not in expression
    assert ".[洗面奶数量].SUM()" in expression
    assert 'IFBLANK(CurrentValue.[商品名称],"")=""' in total["洗面奶有效销售额"]["expression"]


def test_product_breakdown_values_copy_existing_metrics_to_best_keyword_match():
    rules = product_rules_from_records(
        [
            {"fields": {"商品名称": "喷壶", "搜索关键词": "喷壶"}},
            {"fields": {"商品名称": "两用喷壶", "搜索关键词": "两用喷壶"}},
            {"fields": {"商品名称": "洗面奶", "搜索关键词": "洗面奶"}},
        ]
    )

    values = product_breakdown_values(
        rules,
        product_name="趣白全自动洗面奶打泡机感应泡沫机绵密泡沫礼品新品懒人洗脸神器",
        actual_quantity=2,
        valid_sales=338,
    )

    assert values["洗面奶数量"] == 2
    assert values["洗面奶有效销售额"] == 338
    assert values["喷壶数量"] == 0
    assert values["两用喷壶有效销售额"] == 0

    values = product_breakdown_values(rules, product_name="两用喷壶大容量", actual_quantity=1, valid_sales=99)

    assert values["两用喷壶数量"] == 1
    assert values["喷壶数量"] == 0


def test_product_code_takes_priority_when_title_is_blank_or_ambiguous():
    rules = product_rules_from_records(
        [
            {"fields": {"商品名称": "洗面奶", "商品编码": "QBPH004", "搜索关键词": "洗面奶"}},
            {"fields": {"商品名称": "皂液器", "商品编码": "QB006", "搜索关键词": "皂液器"}},
        ]
    )

    matched = best_product_rule_for_order(rules, product_name="", product_code="qbph004")
    values = product_breakdown_values(rules, product_name="", product_code="QBPH004", actual_quantity=2, valid_sales=338)
    formulas = order_product_formula_fields(rules)

    assert matched is not None
    assert matched.name == "洗面奶"
    assert values["洗面奶数量"] == 2
    assert values["洗面奶有效销售额"] == 338
    assert values["皂液器数量"] == 0
    assert extract_product_code_from_raw({"row": {"商家编码": "qbph004"}}) == "QBPH004"
    assert '[商品编码]="QBPH004"' in formulas["洗面奶数量"]["expression"]


def test_importer_owned_product_fields_take_priority_over_title_fallback():
    rules = product_rules_from_records(
        [
            {"fields": {"商品名称": "洗面奶", "搜索关键词": "洗面奶"}},
            {"fields": {"商品名称": "皂液器", "搜索关键词": "皂液器"}},
        ]
    )

    matched = best_product_rule_from_order_fields(
        rules,
        {"洗面奶数量": 2, "洗面奶有效销售额": 338},
        product_name="洁面产品",
    )

    assert matched is not None
    assert matched.name == "洗面奶"


def test_soap_dispenser_alias_matches_foaming_device_names():
    rules = product_rules_from_records(
        [
            {"fields": {"商品名称": "皂液器", "搜索关键词": "皂液器"}},
            {"fields": {"商品名称": "洗面奶", "搜索关键词": "洗面奶"}},
        ]
    )

    values = product_breakdown_values(
        rules,
        product_name="趣白洁面起泡器【达人专属】全自动感应打泡沫机绵密泡沫洗脸神器",
        actual_quantity=0,
        valid_sales=169,
    )

    assert rules[0].keywords == ("皂液器", "洁面起泡器")
    assert values["皂液器数量"] == 0
    assert values["皂液器有效销售额"] == 169
    assert values["洗面奶有效销售额"] == 0

def test_product_breakdown_quantity_uses_source_quantity_for_accessories_and_price_diff():
    rules = product_rules_from_records(
        [
            {"fields": {"商品名称": "配件", "搜索关键词": "配件"}},
            {"fields": {"商品名称": "补差价", "搜索关键词": "补差价"}},
        ]
    )

    values = product_breakdown_values(rules, product_name="洁面乳打泡机配件", actual_quantity=8, valid_sales=14)

    assert values["配件数量"] == 8
    assert values["配件有效销售额"] == 14

    values = product_breakdown_values(rules, product_name="补差价专用", actual_quantity=6, valid_sales=16)

    assert values["补差价数量"] == 6
    assert values["补差价有效销售额"] == 16


def test_price_difference_rule_matches_pdd_alias_product_names():
    rules = product_rules_from_records([{"fields": {"商品名称": "补差价", "搜索关键词": "补差价"}}])

    values = product_breakdown_values(rules, product_name="【购买前须联系客服确认】补收差价专用商品", actual_quantity=1, valid_sales=8)

    assert rules[0].keywords == ("补差价", "补收差价", "差价专用", "补差")
    assert values["补差价数量"] == 1
    assert values["补差价有效销售额"] == 8


def test_product_breakdown_quantity_requires_positive_valid_sales():
    rules = product_rules_from_records([{"fields": {"商品名称": "补差价", "搜索关键词": "补差价"}}])

    values = product_breakdown_values(rules, product_name="补差价专用", actual_quantity=800, valid_sales=0)

    assert values["补差价数量"] == 0
    assert values["补差价有效销售额"] == 0


def test_effective_sales_amount_matches_existing_formula_floor():
    assert effective_sales_amount(169, 0) == 169
    assert effective_sales_amount(100, 120) == 0
