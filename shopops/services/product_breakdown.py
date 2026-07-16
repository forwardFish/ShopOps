from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


DEFAULT_PRODUCT_CATALOG_TABLE_ID = "tblkHqQuzSCNh213"
UNCLASSIFIED_PRODUCT_NAME = "\u65e0\u5546\u54c1\u4fe1\u606f\u8ba2\u5355"
LEGACY_UNCLASSIFIED_PRODUCT_NAMES = ("\u672a\u5f52\u7c7b",)
PRODUCT_NAME_FIELD = "\u5546\u54c1\u540d\u79f0"
PRODUCT_CODE_FIELD = "\u5546\u54c1\u7f16\u7801"
PRODUCT_KEYWORDS_FIELD = "\u641c\u7d22\u5173\u952e\u8bcd"
ORDER_PRODUCT_NAME_FIELD = "\u5546\u54c1\u540d\u79f0"
ORDER_PRODUCT_CODE_FIELD = "\u5546\u54c1\u7f16\u7801"
ORDER_RAW_FIELD = "\u539f\u59cb\u6570\u636e"
ORDER_PRODUCT_CODE_FIELDS = ("\u5546\u54c1\u7f16\u7801", "\u5546\u54c1\u7f16\u7801(\u5e73\u53f0)", "\u5546\u54c1ID", "\u5546\u5bb6\u7f16\u7801")
RAW_PRODUCT_CODE_FIELDS = (
    "\u5546\u54c1\u7f16\u7801",
    "\u5546\u54c1\u7f16\u7801(\u5e73\u53f0)",
    "\u5546\u54c1ID",
    "\u5546\u5bb6\u7f16\u7801",
    "i_id",
    "sku_id",
    "outer_i_id",
    "outer_sku_id",
    "item_id",
    "product_id",
)
ORDER_QUANTITY_FIELD = "\u6570\u91cf"
ORDER_ACTUAL_QUANTITY_FORMULA_FIELD = "\u516c\u5f0f_\u5b9e\u9645\u5356\u51fa\u6570\u91cf"
ORDER_VALID_SALES_FORMULA_FIELD = "\u516c\u5f0f_\u6709\u6548\u9500\u552e\u989d"


@dataclass(frozen=True)
class ProductRule:
    name: str
    keywords: tuple[str, ...]
    codes: tuple[str, ...] = ()

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
        keywords = merge_keywords(split_keywords(keyword_text), product_alias_keywords(name))
        codes = split_product_codes(fields.get(PRODUCT_CODE_FIELD))
        if not keywords:
            keywords = (name,)
        rules.append(ProductRule(name=name, keywords=keywords, codes=codes))
        seen.add(name)
    return rules


def merge_keywords(*groups: tuple[str, ...]) -> tuple[str, ...]:
    keywords: list[str] = []
    for group in groups:
        for keyword in group:
            if keyword and keyword not in keywords:
                keywords.append(keyword)
    return tuple(keywords)


def product_alias_keywords(name: str) -> tuple[str, ...]:
    if name == "皂液器":
        return ("洁面起泡器",)
    if name == "补差价":
        return ("补收差价", "差价专用", "补差")
    return ()


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
            "expression": f"IF({match}&&IFBLANK([{ORDER_VALID_SALES_FORMULA_FIELD}],0)>0,IFBLANK([{ORDER_QUANTITY_FIELD}],0),0)",
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
    product_code: Any = None,
    actual_quantity: Any,
    valid_sales: Any,
) -> dict[str, float]:
    matched = best_product_rule_for_order(rules, product_name=product_name, product_code=product_code)
    quantity = number_value(actual_quantity) or 0
    sales = number_value(valid_sales) or 0
    values: dict[str, float] = {}
    for rule in rules:
        is_match = matched is not None and matched.name == rule.name
        values[rule.valid_sales_field] = sales if is_match else 0
        values[rule.quantity_field] = quantity if is_match and values[rule.valid_sales_field] > 0 else 0
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


def best_product_rule_for_order(
    rules: list[ProductRule],
    *,
    product_name: Any,
    product_code: Any = None,
) -> ProductRule | None:
    code_rule = best_product_rule_by_code(rules, product_code)
    if code_rule:
        return code_rule
    return best_product_rule(rules, scalar_text(product_name))


def best_product_rule_from_order_fields(
    rules: list[ProductRule],
    fields: dict[str, Any],
    *,
    product_name: Any,
    product_code: Any = None,
) -> ProductRule | None:
    """Prefer the importer-owned product fields; use source identifiers as fallback."""
    field_matches = [
        rule
        for rule in rules
        if (number_value(fields.get(rule.quantity_field)) or 0) > 0
        or (number_value(fields.get(rule.valid_sales_field)) or 0) > 0
    ]
    if len(field_matches) == 1:
        return field_matches[0]
    matched = best_product_rule_for_order(rules, product_name=product_name, product_code=product_code)
    if matched and (not field_matches or matched in field_matches):
        return matched
    return field_matches[0] if field_matches else matched


def best_product_rule_by_code(rules: list[ProductRule], product_code: Any) -> ProductRule | None:
    codes = split_product_codes(product_code)
    if not codes:
        return None
    wanted = set(codes)
    for rule in rules:
        if wanted.intersection(rule.codes):
            return rule
    return None


def split_product_codes(value: Any) -> tuple[str, ...]:
    text = scalar_text(value)
    if not text:
        return ()
    codes: list[str] = []
    for part in re.split(r"[,\uFF0C;\uFF1B|\u3001\n\r\s]+", text):
        code = normalize_product_code(part)
        if code and code not in codes:
            codes.append(code)
    return tuple(codes)


def normalize_product_code(value: Any) -> str:
    return scalar_text(value).strip().upper()


def extract_order_product_code(fields: dict[str, Any], *, raw_field: str = ORDER_RAW_FIELD) -> str:
    for field_name in ORDER_PRODUCT_CODE_FIELDS:
        codes = split_product_codes(fields.get(field_name))
        if codes:
            return "; ".join(codes)
    return extract_product_code_from_raw(fields.get(raw_field))


def extract_product_code_from_raw(raw_value: Any) -> str:
    if isinstance(raw_value, dict):
        raw = raw_value
    else:
        raw_text = scalar_text(raw_value)
        if not raw_text:
            return ""
        try:
            raw = json.loads(raw_text)
        except (TypeError, ValueError):
            return ""
    codes: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for field_name in RAW_PRODUCT_CODE_FIELDS:
                for code in split_product_codes(value.get(field_name)):
                    if code not in codes:
                        codes.append(code)
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    collect(nested)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(raw)
    return "; ".join(codes)


def effective_sales_amount(paid_amount: Any, refund_amount: Any) -> float:
    value = (number_value(paid_amount) or 0) - (number_value(refund_amount) or 0)
    return round(max(value, 0), 6)


def independent_order_metrics(fields: dict[str, Any]) -> dict[str, float]:
    """Calculate summary metrics only from importer-owned base fields."""
    quantity = number_value(fields.get(ORDER_QUANTITY_FIELD)) or 0
    paid = number_value(fields.get("\u5b9e\u6536\u6b3e")) or 0
    refund = number_value(fields.get("\u9000\u6b3e\u91d1\u989d")) or 0
    trade_status = scalar_text(fields.get("\u4ea4\u6613\u72b6\u6001"))
    fulfill_status = scalar_text(fields.get("\u5c65\u7ea6/\u552e\u540e\u72b6\u6001"))
    if refund <= 0 and "cancelled" in trade_status.casefold() and "\u9000\u6b3e\u6210\u529f" in fulfill_status:
        refund = paid
    valid_sales = effective_sales_amount(paid, refund) if quantity > 0 else 0
    return {
        "quantity": round(quantity, 6),
        "sales": round(paid, 6),
        "refund": round(refund, 6),
        "valid_sales": round(valid_sales, 6),
    }


def summary_product_formula_fields(order_table_names: list[str], rules: list[ProductRule]) -> dict[str, dict[str, str]]:
    fields: dict[str, dict[str, str]] = {}
    order_filters = [order_summary_filter_expr(table_name) for table_name in order_table_names]
    for rule in rules:
        row_match = f'IFBLANK([商品名称],"")=""||[商品名称]="{escape_formula_string(rule.name)}"'
        fields[rule.quantity_field] = {
            "expression": f"IF({row_match},{sum_related_expr(order_filters, rule.quantity_field)},0)",
            "formatter": "0",
        }
        fields[rule.valid_sales_field] = {
            "expression": f"IF({row_match},{sum_related_expr(order_filters, rule.valid_sales_field)},0)",
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
    code_checks = [
        f'[{ORDER_PRODUCT_CODE_FIELD}]="{escape_formula_string(code)}"'
        for code in rule.codes
    ]
    name_checks = [
        f'[{ORDER_PRODUCT_NAME_FIELD}].CONTAIN("{escape_formula_string(keyword)}")'
        for keyword in rule.keywords
    ]
    checks = [*code_checks, *name_checks]
    return "||".join(checks) if checks else "false"


def order_summary_filter_expr(table_name: str) -> str:
    return (
        f"[{table_name}].FILTER("
        'CurrentValue.[公式_统计日期]=TEXT([统计日期],"YYYY-MM-DD")&&'
        '([平台]="全平台总计"||CurrentValue.[平台]=[平台])'
        ")"
    )


def total_summary_filter_expr(table_name: str) -> str:
    return f'[{table_name}].FILTER(CurrentValue.[平台]=[平台]&&IFBLANK(CurrentValue.[商品名称],"")="")'


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
