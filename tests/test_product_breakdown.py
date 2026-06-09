from __future__ import annotations

from shopops.services.product_breakdown import (
    effective_sales_amount,
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
    assert "[公式_实际卖出数量]" in formulas["喷壶数量"]["expression"]
    assert "[公式_有效销售额]" in formulas["喷壶有效销售额"]["expression"]


def test_summary_and_total_product_formulas_sum_product_fields():
    rules = product_rules_from_records([{"fields": {"商品名称": "洗面奶", "搜索关键词": "洗面奶"}}])

    summary = summary_product_formula_fields(["订单明细-天猫", "订单明细-抖音"], rules)
    total = total_product_formula_fields("公式动态经营汇总表", rules)

    assert summary["洗面奶数量"]["expression"] == (
        '[订单明细-天猫].FILTER(CurrentValue.[公式_统计日期]=[统计日期]&&'
        '([平台]="全平台总计"||CurrentValue.[平台]=[平台])).[洗面奶数量].SUM()+'
        '[订单明细-抖音].FILTER(CurrentValue.[公式_统计日期]=[统计日期]&&'
        '([平台]="全平台总计"||CurrentValue.[平台]=[平台])).[洗面奶数量].SUM()'
    )
    assert total["洗面奶有效销售额"]["expression"] == (
        "[公式动态经营汇总表].FILTER(CurrentValue.[平台]=[平台]).[洗面奶有效销售额].SUM()"
    )


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


def test_effective_sales_amount_matches_existing_formula_floor():
    assert effective_sales_amount(169, 0) == 169
    assert effective_sales_amount(100, 120) == 0
