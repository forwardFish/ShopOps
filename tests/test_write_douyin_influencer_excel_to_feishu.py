from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from scripts.write_douyin_influencer_excel_to_feishu import (
    F_APP_CHANNEL,
    F_AUTHOR_ACCOUNT,
    F_ORDER_NO,
    F_TRAFFIC_SOURCE,
    F_UNIQUE_KEY,
    doudian_influencer_rows,
    parse_doudian_xlsx,
)


def test_parse_doudian_xlsx_and_build_rows_from_commission_export(tmp_path: Path):
    path = tmp_path / "douyin-commission.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["订单id", "商品id", "商品名称", "作者账号", "抖音/火山号", "支付金额", "佣金率", "预估佣金支出", "结算金额", "实际佣金支出", "订单状态", "付款时间", "店铺id", "店铺名称", "商品数量", "订单来源", "流量来源"])
    sheet.append(["6953547102608758621\t", "3810515145814311090\t", "商品A", "作者A", "66799442664", "169.00", "32.00%", "54.08", "0.00", "0.00", "订单付款", "2026-06-09 21:25:25", "272308913\t", "趣白", "1", "抖音", "视频"])
    workbook.save(path)

    source = parse_doudian_xlsx(path)
    rows = doudian_influencer_rows(source, path, [])

    assert rows[0][F_UNIQUE_KEY] == "douyin_6953547102608758621"
    assert rows[0][F_ORDER_NO] == "6953547102608758621"
    assert rows[0][F_AUTHOR_ACCOUNT] == "作者A"
    assert rows[0][F_APP_CHANNEL] == "抖音"
    assert rows[0][F_TRAFFIC_SOURCE] == "视频"


def test_doudian_rows_keep_excel_rows_without_author_account(tmp_path: Path):
    path = tmp_path / "douyin-commission.xlsx"
    source = [
        {
            "订单id": "6953547102608758621\t",
            "商品id": "3810515145814311090\t",
            "商品名称": "商品A",
            "作者账号": "-",
            "抖音/火山号": "-",
            "支付金额": "169.00",
            "佣金率": "0.00%",
            "预估佣金支出": "0.00",
            "结算金额": "169.00",
            "实际佣金支出": "0.00",
            "订单状态": "订单付款",
            "付款时间": "2026-06-09 21:25:25",
            "订单来源": "抖音",
        }
    ]

    rows = doudian_influencer_rows(source, path, [])

    assert len(rows) == 1
    assert rows[0][F_UNIQUE_KEY] == "douyin_6953547102608758621"
    assert rows[0][F_AUTHOR_ACCOUNT] == ""
