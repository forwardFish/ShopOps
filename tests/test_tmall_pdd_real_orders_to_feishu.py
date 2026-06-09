from __future__ import annotations

from datetime import datetime

from scripts.run_tmall_pdd_real_orders_to_feishu import PLATFORM_PDD, PLATFORM_TMALL, date_windows, normalize_pdd_order
from shopops.config import Settings


def test_platform_names_are_stable_chinese_literals():
    assert PLATFORM_TMALL == "天猫"
    assert PLATFORM_PDD == "拼多多"


def test_date_windows_split_more_than_seven_days():
    end_at = datetime(2026, 6, 4, 20, 0, 0)

    windows = date_windows(end_at, days=30, max_days=7)

    assert len(windows) == 5
    assert all((end - start).days <= 7 for start, end in windows)
    assert windows[0][1] == end_at
    assert windows[-1][0] == datetime(2026, 5, 5, 20, 0, 0)


def test_normalize_pdd_order_keeps_amount_and_order_id():
    settings = Settings(shop_id="21117355", shop_name="拼多多")

    row = normalize_pdd_order({"o_id": "P1", "shop_id": 21117355, "pay_amount": "12.5"}, settings, datetime(2026, 6, 4, 20, 0, 0))

    assert row["unique_key"] == "jushuitan_pdd_order_list_21117355_P1"
    assert row["order_id"] == "P1"
    assert row["paid_amount"] == 12.5
