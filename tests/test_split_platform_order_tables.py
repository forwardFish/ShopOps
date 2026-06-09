from __future__ import annotations

from pathlib import Path

from scripts.split_platform_order_tables import (
    F_CREATED_AT,
    F_FULFILL_STATUS,
    F_PAID_AMOUNT,
    F_QUANTITY,
    F_REFUND_AMOUNT,
    douyin_export_row,
    pdd_export_row,
    tmall_export_row,
    unified_row_from_source,
)
from scripts.write_pinduoduo_orders_excel_to_feishu import F_REFUND_AMOUNT as PDD_IMPORT_REFUND_AMOUNT
from scripts.write_pinduoduo_orders_excel_to_feishu import pdd_feishu_rows


def test_douyin_refund_success_uses_paid_amount_when_export_has_no_refund_column():
    row = douyin_export_row(
        {
            "主订单编号": "\t6953489890610190242",
            "子订单编号": "\t6953489890610190242",
            "选购商品": "趣白全自动洗面奶打泡机",
            "商品数量": "1",
            "商品单价": "169.00",
            "订单应付金额": "169.00",
            "订单提交时间": "2026-06-07 15:12:37",
            "订单状态": "已关闭",
            "售后状态": "退款成功",
        },
        Path(r"D:\lyh\ShopOps\抖音\0607\orders.csv"),
    )

    assert row is not None
    assert row[F_PAID_AMOUNT] == 169.0
    assert row[F_QUANTITY] == 0
    assert row[F_REFUND_AMOUNT] == 169.0


def test_douyin_normal_order_keeps_zero_refund_without_refund_signal():
    row = douyin_export_row(
        {
            "主订单编号": "\t6953481223815305121",
            "子订单编号": "\t6953481223815305121",
            "选购商品": "趣白全自动洗面奶打泡机",
            "商品数量": "1",
            "商品单价": "169.00",
            "订单应付金额": "169.00",
            "订单提交时间": "2026-06-07 15:11:49",
            "订单状态": "待发货",
            "售后状态": "-",
        },
        Path(r"D:\lyh\ShopOps\抖音\0607\orders.csv"),
    )

    assert row is not None
    assert row[F_PAID_AMOUNT] == 169.0
    assert row[F_QUANTITY] == 1.0
    assert row[F_REFUND_AMOUNT] == 0


def test_source_split_repairs_zero_refund_when_fulfill_status_is_refund_success():
    row = unified_row_from_source(
        {
            "unique_key": "douyin_6953489890610190242",
            "平台": "抖音",
            "订单号": "6953489890610190242",
            "履约/售后状态": "退款成功",
            "交易状态": "已关闭",
            "实收款": 169.0,
            "退款金额": 0,
        },
        "抖音",
    )

    assert row[F_FULFILL_STATUS] == "退款成功"
    assert row[F_PAID_AMOUNT] == 169.0
    assert row[F_REFUND_AMOUNT] == 169.0


def test_pdd_refund_success_uses_paid_amount_when_export_has_no_refund_column():
    row = pdd_export_row(
        {
            "订单号": "260607-400000294410900",
            "商品": "趣白全自动洗面奶打泡机",
            "商品数量(件)": "1\t",
            "订单状态": "未发货，退款成功",
            "售后状态": "退款成功",
            "订单成交时间": "2026/6/6 13:41",
            "支付时间": "2026/6/7 13:41",
            "商家实收金额(元)": "168.99\t",
        },
        Path(r"D:\lyh\ShopOps\拼多多\0607\orders.csv"),
    )

    assert row is not None
    assert row[F_CREATED_AT] == "2026-06-06 13:41:00"
    assert row[F_QUANTITY] == 0
    assert row[F_PAID_AMOUNT] == 168.99
    assert row[F_REFUND_AMOUNT] == 168.99


def test_tmall_refund_row_uses_gross_sales_when_paid_is_net_after_refund():
    row = tmall_export_row(
        {
            "订单编号": "5119111586217093519",
            "商品标题": "趣白全自动洗面奶打泡机",
            "数量": "1",
            "买家实付金额": "0",
            "退款金额": "169",
            "订单创建时间": "2026-06-07 10:00:00",
        },
        Path(r"D:\lyh\ShopOps\天猫\0607\orders.xlsx"),
    )

    assert row is not None
    assert row[F_PAID_AMOUNT] == 169.0
    assert row[F_QUANTITY] == 0
    assert row[F_REFUND_AMOUNT] == 169.0


def test_pdd_single_import_refund_success_writes_refund_amount():
    headers = [
        "商品",
        "订单号",
        "订单状态",
        "商品数量(件)",
        "订单成交时间",
        "支付时间",
        "承诺发货时间",
        "售后状态",
        "商家实收金额(元)",
        "用户实付金额(元)",
        "快递单号",
    ]
    rows = pdd_feishu_rows(
        headers,
        [
            {
                "商品": "趣白全自动洗面奶打泡机",
                "订单号": "260607-400000294410900",
                "订单状态": "未发货，退款成功",
                "商品数量(件)": "1\t",
                "订单成交时间": "2026/6/6 13:41",
                "支付时间": "2026/6/7 13:41",
                "承诺发货时间": "2026/6/9 13:41",
                "售后状态": "退款成功",
                "商家实收金额(元)": "168.99\t",
                "用户实付金额(元)": "143.65\t",
                "快递单号": "\t",
            }
        ],
        Path(r"D:\lyh\ShopOps\拼多多\0607\orders.csv"),
    )

    assert rows[0][PDD_IMPORT_REFUND_AMOUNT] == 168.99
    assert rows[0]["创建时间"] == "2026-06-06 13:41:00"
    assert rows[0]["数量"] == 0


def test_pdd_export_row_falls_back_to_order_no_date_when_trade_time_is_blank():
    row = pdd_export_row(
        {
            "订单号": "260607-400000294410900",
            "商品": "趣白全自动洗面奶打泡机",
            "商品数量(件)": "1\t",
            "订单状态": "待付款",
            "售后状态": "无售后或售后取消",
            "订单成交时间": "",
            "支付时间": "",
            "商家实收金额(元)": "",
        },
        Path(r"D:\lyh\ShopOps\拼多多\0608\orders.csv"),
    )

    assert row is not None
    assert row[F_CREATED_AT] == "2026-06-07"
    assert row[F_QUANTITY] == 0


def test_pdd_price_difference_product_has_zero_actual_quantity():
    row = pdd_export_row(
        {
            "订单号": "260608-400000294410900",
            "商品": "【购买前须联系客服确认】补收差价专用商品",
            "商品数量(件)": "1200\t",
            "订单状态": "已收货",
            "售后状态": "无售后或售后取消",
            "订单成交时间": "2026/6/8 09:00",
            "支付时间": "2026/6/8 09:00",
            "商家实收金额(元)": "0",
        },
        Path(r"D:\lyh\ShopOps\拼多多\0608\orders.csv"),
    )

    assert row is not None
    assert row[F_QUANTITY] == 0
