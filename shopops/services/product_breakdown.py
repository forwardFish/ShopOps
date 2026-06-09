from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


DEFAULT_PRODUCT_CATALOG_TABLE_ID = "tblkHqQuzSCNh213"
PRODUCT_NAME_FIELD = "商品名称"
PRODUCT_KEYWORDS_FIELD = "搜索关键词"
ORDER_PRODUCT_NAME_FIELD = "商品名称"
ORDER_ACTUAL_QUANTITY_FORMULA_FIELD = "公式_实际卖出数量"
ORDER_VALID_SALES_FORMULA_FIELD = "公式_有效销售额"


@dataclass(frozen=True)
class ProductRule:
    name: str
    keywords: tuple[str, ...]

    @property
    def quantity_field(self) -> str:
        return f"{self.name}数量"

    @property
    def valid_sales_field(self) -> str:
        return f"{self.name}有效销售额"


def product_rules_from_records(records: list[dict[str, Any]]) -> list[ProductRule]:
    rules: list[ProductRule] = []
    seen: set[str] = set()
    for record in records:
        fields = record.get("fields") or record
        name = scalar_text(fields.get(PRODUCT_NAME_FIELD))
        if not name or name in seen:
            continue
        keyword_text = scalar_text(fields.get(PRODUCT_KEYWORDS_FIELD)) or name
        keywords = split_keywords(keyword_text)
        if not keywords:
            keywords = (name,)
        rules.append(ProductRule(name=name, keywords=keywords))
        seen.add(name)
    return rules


def split_keywords(value: str) -> tuple[str, ...]:
    parts = re.split(r"[,，;；|、\n\r]+", value)
    keywords: list[str] = []
    for part in parts:
        keyword = part.strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return tuple(keywords)


def order_product_formula_fields(rules: list[ProductRule]) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    for rule in rules:
        match = product_match_expr(rule)
        fields[rule.quantity_field] = {
            "expression": f"IF({match},IFBLANK([{ORDER_ACTUAL_QUANTITY_FORMULA_FIELD}],0),0)",
            "formatter": "0",
        }
        fields[rule.valid_sales_field] = {
            "expression": f"IF({match},IFBLANK([{ORDER_VALID_SALES_FORMULA_FIELD}],0),0)",
            "formatter": "0.00",
        }
    return fields


def product_breakdown_values(
    rules: list[ProductRule],
    *,
    product_name: Any,
    actual_quantity: Any,
    valid_sales: Any,
) -> dict[str, float]:
    matched = best_product_rule(rules, scalar_text(product_name))
    quantity = number_value(actual_quantity) or 0
    sales = number_value(valid_sales) or 0
    values: dict[str, float] = {}
    for rule in rules:
        is_match = matched is not None and matched.name == rule.name
        values[rule.quantity_field] = quantity if is_match else 0
        values[rule.valid_sales_field] = sales if is_match else 0
    return values


def best_product_rule(rules: list[ProductRule], product_name: str) -> ProductRule | None:
    best: tuple[int, int, ProductRule] | None = None
    for index, rule in enumerate(rules):
        matching_lengths = [len(keyword) for keyword in rule.keywords if keyword and keyword in product_name]
        if not matching_lengths:
            continue
        candidate = (max(matching_lengths), -index, rule)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return best[2] if best else None


def effective_sales_amount(paid_amount: Any, refund_amount: Any) -> float:
    value = (number_value(paid_amount) or 0) - (number_value(refund_amount) or 0)
    return round(max(value, 0), 6)


def summary_product_formula_fields(order_table_names: list[str], rules: list[ProductRule]) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    order_filters = [order_summary_filter_expr(table_name) for table_name in order_table_names]
    for rule in rules:
        fields[rule.quantity_field] = {
            "expression": sum_related_expr(order_filters, rule.quantity_field),
            "formatter": "0",
        }
        fields[rule.valid_sales_field] = {
            "expression": sum_related_expr(order_filters, rule.valid_sales_field),
            "formatter": "0.00",
        }
    return fields


def total_product_formula_fields(summary_table_name: str, rules: list[ProductRule]) -> dict[str, dict[str, str]]:
    summary_filter = total_summary_filter_expr(summary_table_name)
    fields: dict[str, dict[str, str]] = {}
    for rule in rules:
        fields[rule.quantity_field] = {
            "expression": f"{summary_filter}.[{rule.quantity_field}].SUM()",
            "formatter": "0",
        }
        fields[rule.valid_sales_field] = {
            "expression": f"{summary_filter}.[{rule.valid_sales_field}].SUM()",
            "formatter": "0.00",
        }
    return fields


def product_field_names(rules: list[ProductRule]) -> list[str]:
    names: list[str] = []
    for rule in rules:
        names.extend([rule.quantity_field, rule.valid_sales_field])
    return names


def product_match_expr(rule: ProductRule) -> str:
    checks = [
        f'[{ORDER_PRODUCT_NAME_FIELD}].CONTAIN("{escape_formula_string(keyword)}")'
        for keyword in rule.keywords
    ]
    return "||".join(checks) if checks else "false"


def order_summary_filter_expr(table_name: str) -> str:
    return (
        f"[{table_name}].FILTER("
        "CurrentValue.[公式_统计日期]=[统计日期]&&"
        '([平台]="全平台总计"||CurrentValue.[平台]=[平台])'
        ")"
    )


def total_summary_filter_expr(table_name: str) -> str:
    return f"[{table_name}].FILTER(CurrentValue.[平台]=[平台])"


def sum_related_expr(filters: list[str], field_name: str) -> str:
    if not filters:
        return "0"
    return "+".join(f"{item}.[{field_name}].SUM()" for item in filters)


def escape_formula_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(value).strip()


def number_value(value: Any) -> float | None:
    text = scalar_text(value).replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None
