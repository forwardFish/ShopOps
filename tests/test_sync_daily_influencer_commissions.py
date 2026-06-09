from __future__ import annotations

import csv

from openpyxl import Workbook

from scripts.sync_daily_influencer_commissions import (
    F_COMMISSION,
    F_COMMISSION_BASIS,
    F_INFLUENCER_ID,
    F_INFLUENCER_NICK,
    F_PRODUCT_NAME,
    F_QUANTITY,
    F_UNIQUE_KEY,
    build_rows_for_file,
    canonical_unique_key,
    collapse_rows_by_unique_key,
)


def test_canonical_unique_key_is_platform_plus_order_no():
    assert canonical_unique_key("抖音", "\t6953489890610190242") == "抖音6953489890610190242"
    assert canonical_unique_key("视频号", " 1001 ") == "视频号1001"


def test_builds_douyin_rows_from_order_export_influencer_columns(tmp_path):
    path = tmp_path / "douyin.csv"
    headers = [
        "主订单编号",
        "选购商品",
        "商品数量",
        "商品ID",
        "订单应付金额",
        "订单提交时间",
        "支付完成时间",
        "订单状态",
        "达人ID",
        "达人昵称",
        "达人实际承担优惠金额",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerow(
            {
                "主订单编号": "\tD1",
                "选购商品": "洗面奶",
                "商品数量": "1",
                "商品ID": "\tP1",
                "订单应付金额": "169.00",
                "订单提交时间": "2026-06-07 15:12:37",
                "支付完成时间": "2026-06-07 15:12:38",
                "订单状态": "待发货",
                "达人ID": "\tK1",
                "达人昵称": "Creator A",
                "达人实际承担优惠金额": "3.50",
            }
        )

    rows, info = build_rows_for_file("抖音", path, "2026-06-07 18:00:00")

    assert info["source_row_count"] == 1
    assert rows[0][F_UNIQUE_KEY] == "抖音D1"
    assert rows[0][F_INFLUENCER_ID] == "K1"
    assert rows[0][F_INFLUENCER_NICK] == "Creator A"
    assert rows[0][F_COMMISSION] == 3.5
    assert rows[0][F_COMMISSION_BASIS] == "达人实际承担优惠金额"


def test_builds_wechat_channels_rows_from_order_export_influencer_columns(tmp_path):
    path = tmp_path / "wechat.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    headers = [
        "订单号",
        "订单下单时间",
        "支付时间",
        "订单状态",
        "商品名称",
        "商品编码(平台)",
        "商品数量",
        "订单实际支付金额",
        "带货账号昵称",
        "带货费用",
        "带货佣金率",
        "带货费用类型",
    ]
    sheet.append(headers)
    sheet.append(["W1", "2026-06-07 15:00:00", "2026-06-07 15:01:00", "已付款", "洗面奶", "P1", 1, 169, "Creator B", 8.8, "5%", "佣金"])
    workbook.save(path)

    rows, info = build_rows_for_file("视频号", path, "2026-06-07 18:00:00")

    assert info["source_row_count"] == 1
    assert rows[0][F_UNIQUE_KEY] == "视频号W1"
    assert rows[0][F_INFLUENCER_NICK] == "Creator B"
    assert rows[0][F_COMMISSION] == 8.8
    assert rows[0][F_COMMISSION_BASIS] == "佣金"


def test_collapses_duplicate_order_rows_without_changing_unique_key(tmp_path):
    path = tmp_path / "douyin.csv"
    headers = ["主订单编号", "选购商品", "商品数量", "达人昵称", "达人实际承担优惠金额"]
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerow({"主订单编号": "D1", "选购商品": "商品A", "商品数量": "1", "达人昵称": "Creator A", "达人实际承担优惠金额": "2"})
        writer.writerow({"主订单编号": "D1", "选购商品": "商品B", "商品数量": "2", "达人昵称": "Creator A", "达人实际承担优惠金额": "3"})

    rows, _ = build_rows_for_file("抖音", path, "2026-06-07 18:00:00")
    collapsed = collapse_rows_by_unique_key(rows)

    assert len(collapsed) == 1
    assert collapsed[0][F_UNIQUE_KEY] == "抖音D1"
    assert collapsed[0][F_PRODUCT_NAME] == "商品A; 商品B"
    assert collapsed[0][F_QUANTITY] == 3
    assert collapsed[0][F_COMMISSION] == 5
