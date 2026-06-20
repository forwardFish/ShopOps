from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from data_robot.hourly_ad_interval_summary import (
    PreviousSnapshot,
    Snapshot,
    latest_previous_snapshot,
    previous_window_start,
    summarize_orders_for_window,
    summarize_hourly_interval,
)
from scripts.import_daily_files_to_feishu import (
    F_ACTUAL_SPEND,
    F_CREATED_AT,
    F_DATE,
    F_DEAL_AMOUNT,
    F_FETCHED_AT,
    F_ORDER_NO,
    F_PAID_AMOUNT,
    F_PLATFORM,
    F_FREIGHT_COST,
    F_OTHER_FEE,
    F_PLATFORM_FEE,
    F_PRODUCT_NAME,
    F_PRODUCT_COST,
    F_QUANTITY,
    F_REFUND_AMOUNT,
    F_UNIQUE_KEY,
)


def test_summarize_hourly_interval_writes_platform_and_total_rows(monkeypatch):
    monkeypatch.setenv("SHOPOPS_ORDER_TABLE_TMALL_ID", "tmall_orders")
    monkeypatch.setenv("SHOPOPS_ORDER_TABLE_DOUYIN_ID", "douyin_orders")
    evidence_dir = Path(".tmp") / "tests" / "hourly_ad_interval_summary" / uuid.uuid4().hex
    evidence_dir.mkdir(parents=True, exist_ok=True)

    tmall_evidence = write_ad_evidence(
        evidence_dir / "tmall.json",
        "tmall",
        {
            F_UNIQUE_KEY: "ads_tmall_2026-06-17",
            F_PLATFORM: "天猫",
            F_DATE: "2026-06-17",
            F_FETCHED_AT: "2026-06-17 02:00:00",
            F_ACTUAL_SPEND: 160,
            F_DEAL_AMOUNT: 350,
        },
    )
    douyin_evidence = write_ad_evidence(
        evidence_dir / "douyin.json",
        "douyin",
        {
            F_UNIQUE_KEY: "ads_douyin_2026-06-17",
            F_PLATFORM: "抖音",
            F_DATE: "2026-06-17",
            F_FETCHED_AT: "2026-06-17 02:00:00",
            F_ACTUAL_SPEND: 30,
            F_DEAL_AMOUNT: 90,
        },
    )
    client = FakeClient()

    result = summarize_hourly_interval(
        [
            {"platform": "tmall", "result": {"returncode": 0}, "evidence": str(tmall_evidence)},
            {"platform": "douyin", "result": {"returncode": 0}, "evidence": str(douyin_evidence)},
        ],
        stat_date="2026-06-17",
        run_token="20260617-020000",
        table_id="interval_table",
        client=client,
    )

    assert result["status"] == "success"
    assert result["row_count"] == 3
    rows = {row[F_PLATFORM]: row for row in client.saved_rows}
    assert "区间投流消耗" not in rows["天猫"]
    assert "区间订单数" not in rows["天猫"]
    assert "订单数" not in rows["天猫"]
    assert rows["天猫"]["新增订单数"] == 1
    assert rows["天猫"]["新增订单销售额"] == 70
    assert rows["天猫"]["新增实收款"] == 80
    assert "新增销售额" not in rows["天猫"]
    assert "新增有效销售额" not in rows["天猫"]
    assert rows["天猫"]["新增投流消耗"] == 60
    assert rows["天猫"]["新增投流成交金额"] == 150
    assert rows["天猫"]["新增投流ROI"] == 2.5
    assert rows["天猫"]["今日累计订单数"] == 2
    assert "今日累计销售额" not in rows["天猫"]
    assert rows["天猫"]["今日累计退款金额"] == 10
    assert "今日累计有效销售额" not in rows["天猫"]
    assert rows["天猫"]["今日累计投流消耗"] == 160
    assert rows["天猫"]["今日累计投流成交金额"] == 350
    assert rows["天猫"]["今日累计投流ROI"] == round(350 / 160, 6)
    assert "本次投流消耗" not in rows["天猫"]
    assert "本次投流成交金额" not in rows["天猫"]
    assert rows["天猫"]["今日累计订单销售额"] == 1069
    assert rows["天猫"]["今日累计实收款"] == 1079
    assert rows["天猫"]["新增实际卖出数量"] == 2
    assert rows["天猫"]["新增商品成本"] == 20
    assert rows["天猫"]["新增喷壶数量"] == 2
    assert rows["天猫"]["新增喷壶有效销售额"] == 70
    assert rows["抖音"]["新增投流消耗"] == 30
    assert rows["抖音"]["新增订单数"] == 1
    assert rows["总计"]["新增投流消耗"] == 90
    assert rows["总计"]["新增订单数"] == 2
    assert rows["总计"]["新增订单销售额"] == 100
    assert rows["总计"]["新增实收款"] == 110
    assert "新增销售额" not in rows["总计"]
    assert "新增有效销售额" not in rows["总计"]
    assert rows["总计"]["新增投流消耗"] == 90
    assert rows["总计"]["新增投流成交金额"] == 240
    assert rows["总计"]["新增ROI"] == round(100 / 90, 6)
    assert rows["总计"]["新增投流ROI"] == round(240 / 90, 6)
    assert rows["总计"]["上次采集时间"] == "2026-06-17 01:00:00"
    assert rows["总计"]["今日累计订单数"] == 3
    assert rows["总计"]["今日累计订单销售额"] == 1099
    assert rows["总计"]["今日累计实收款"] == 1109
    assert "今日累计销售额" not in rows["总计"]
    assert "今日累计有效销售额" not in rows["总计"]
    assert rows["总计"]["今日累计投流消耗"] == 190
    assert rows["总计"]["今日累计投流成交金额"] == 440
    assert rows["总计"]["今日累计ROI"] == round(1099 / 190, 6)
    assert rows["总计"]["今日累计投流ROI"] == round(440 / 190, 6)


def test_summarize_hourly_interval_falls_back_to_product_rules_when_order_product_metrics_are_blank(monkeypatch):
    monkeypatch.setenv("SHOPOPS_ORDER_TABLE_TMALL_ID", "fallback_orders")
    evidence_dir = Path(".tmp") / "tests" / "hourly_ad_interval_summary" / uuid.uuid4().hex
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tmall_evidence = write_ad_evidence(
        evidence_dir / "tmall.json",
        "tmall",
        {
            F_UNIQUE_KEY: "ads_tmall_2026-06-17",
            F_PLATFORM: "天猫",
            F_DATE: "2026-06-17",
            F_FETCHED_AT: "2026-06-17 10:00:00",
            F_ACTUAL_SPEND: 100,
            F_DEAL_AMOUNT: 300,
        },
    )
    client = FakeClient()

    result = summarize_hourly_interval(
        [{"platform": "tmall", "result": {"returncode": 0}, "evidence": str(tmall_evidence)}],
        stat_date="2026-06-17",
        run_token="20260617-100000",
        table_id="interval_table",
        client=client,
    )

    rows = {row[F_PLATFORM]: row for row in client.saved_rows}
    assert result["status"] == "success"
    assert "洗面奶数量" not in rows["天猫"]
    assert rows["天猫"]["新增洗面奶数量"] == 2
    assert rows["天猫"]["新增洗面奶有效销售额"] == 338


def test_summarize_hourly_interval_adds_order_only_douyin_platform_to_total(monkeypatch):
    monkeypatch.setenv("SHOPOPS_ORDER_TABLE_TMALL_ID", "tmall_orders")
    monkeypatch.setenv("SHOPOPS_ORDER_TABLE_DOUYIN_ID", "douyin_orders")
    evidence_dir = Path(".tmp") / "tests" / "hourly_ad_interval_summary" / uuid.uuid4().hex
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tmall_evidence = write_ad_evidence(
        evidence_dir / "tmall.json",
        "tmall",
        {
            F_UNIQUE_KEY: "ads_tmall_2026-06-17",
            F_PLATFORM: "天猫",
            F_DATE: "2026-06-17",
            F_FETCHED_AT: "2026-06-17 02:00:00",
            F_ACTUAL_SPEND: 160,
            F_DEAL_AMOUNT: 350,
        },
    )
    client = FakeClient()

    result = summarize_hourly_interval(
        [{"platform": "tmall", "result": {"returncode": 0}, "evidence": str(tmall_evidence)}],
        stat_date="2026-06-17",
        run_token="20260617-020000",
        table_id="interval_table",
        client=client,
        order_platform_codes=["tmall", "douyin"],
    )

    rows = {row[F_PLATFORM]: row for row in client.saved_rows}
    assert result["status"] == "success"
    assert result["platforms"] == ["douyin", "tmall"]
    assert rows["抖音"]["新增订单数"] == 1
    assert rows["抖音"]["新增订单销售额"] == 30
    assert rows["抖音"]["新增投流消耗"] == 0
    assert rows["总计"]["新增订单数"] == 2
    assert rows["总计"]["新增订单销售额"] == 100
    assert rows["总计"]["新增投流消耗"] == 60


def test_previous_window_start_clamps_to_collection_start_hour():
    snapshot = Snapshot(
        platform_code="tmall",
        platform_name="天猫",
        fetched_at=datetime(2026, 6, 18, 8, 30, 0),
        stat_date="2026-06-18",
        spend=100,
        deal_amount=200,
    )
    previous = PreviousSnapshot(
        fetched_at=datetime(2026, 6, 18, 7, 45, 0),
        spend=50,
        deal_amount=80,
    )

    window_start, baseline = previous_window_start(
        snapshot,
        previous,
        60,
        collection_start_hour=8,
    )

    assert window_start == datetime(2026, 6, 18, 8, 0, 0)
    assert baseline == "上一轮采集"


def test_summarize_orders_for_window_prefers_created_at_over_paid_time(monkeypatch):
    monkeypatch.setenv("SHOPOPS_ORDER_TABLE_DOUYIN_ID", "time_priority_orders")
    client = FakeClient()

    summary = summarize_orders_for_window(
        client,
        "抖音",
        datetime(2026, 6, 19, 8, 0, 0),
        datetime(2026, 6, 19, 9, 0, 0),
    )

    assert summary.count == 1
    assert summary.paid_amount == 169


def test_latest_previous_snapshot_falls_back_to_today_ad_totals():
    client = FakePreviousSnapshotClient()

    previous = latest_previous_snapshot(
        client,
        "interval_table",
        "天猫",
        "2026-06-18",
        datetime(2026, 6, 18, 14, 11, 43),
    )

    assert previous is not None
    assert previous.fetched_at == datetime(2026, 6, 18, 13, 53, 47)
    assert previous.spend == 3133.55
    assert previous.deal_amount == 7436


def write_ad_evidence(path: Path, platform: str, row: dict[str, Any]) -> Path:
    payload = {"status": "success", "platform": platform, "date": row[F_DATE], "row": row}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class FakeClient:
    app_token = "app"

    def __init__(self) -> None:
        self.saved_rows: list[dict[str, Any]] = []

    def ensure_missing_fields_for_rows(self, table_id: str, rows: list[dict[str, Any]], field_types: dict[str, int]) -> list[str]:
        return []

    def upsert_rows(
        self,
        *,
        table_id: str,
        rows: list[dict[str, Any]],
        required_fields: list[str],
        fallback_match_fields: tuple[str, ...],
        allow_partial_fields: bool = True,
        update_existing_fields: set[str] | None = None,
    ) -> dict[str, Any]:
        self.saved_rows = rows
        return {"created": len(rows), "updated": 0, "saved": len(rows), "dropped_nonexistent_fields": {}}

    def readback_by_unique_key(self, table_id: str, unique_keys: set[str]) -> dict[str, dict[str, Any]]:
        return {row[F_UNIQUE_KEY]: row for row in self.saved_rows if row[F_UNIQUE_KEY] in unique_keys}

    def product_rules(self, product_table_id: str):
        from shopops.services.product_breakdown import product_rules_from_records

        return product_rules_from_records([{"fields": {"商品名称": "洗面奶", "搜索关键词": "洗面奶"}}])

    def iter_records(self, table_id: str, field_names: list[str] | None = None):
        if table_id == "interval_table":
            yield {
                "record_id": "prev_tmall",
                "fields": {
                    F_PLATFORM: "天猫",
                    "采集日期": "2026-06-17",
                    "本次采集时间": "2026-06-17 01:00:00",
                    "本次投流消耗": 100,
                    "本次投流成交金额": 200,
                },
            }
        elif table_id == "tmall_orders":
            yield {
                "record_id": "tmall_in_window",
                "fields": {
                    F_ORDER_NO: "T1",
                    F_CREATED_AT: "2026-06-17 01:30:00",
                    F_PAID_AMOUNT: 80,
                    F_REFUND_AMOUNT: 10,
                    F_QUANTITY: 2,
                    F_PRODUCT_COST: 20,
                    F_FREIGHT_COST: 5,
                    F_PLATFORM_FEE: 2,
                    F_OTHER_FEE: 1,
                    "预估佣金支出": 3,
                    "喷壶数量": 2,
                    "喷壶有效销售额": 70,
                },
            }
            yield {
                "record_id": "tmall_before_window",
                "fields": {
                    F_ORDER_NO: "T0",
                    F_CREATED_AT: "2026-06-17 00:30:00",
                    F_PAID_AMOUNT: 999,
                    F_REFUND_AMOUNT: 0,
                },
            }
        elif table_id == "douyin_orders":
            yield {
                "record_id": "douyin_in_window",
                "fields": {
                    F_ORDER_NO: "D1",
                    F_CREATED_AT: "2026-06-17 01:45:00",
                    F_PAID_AMOUNT: 30,
                    F_REFUND_AMOUNT: 0,
                    F_QUANTITY: 1,
                },
            }
        elif table_id == "fallback_orders":
            yield {
                "record_id": "fallback_tmall",
                "fields": {
                    F_ORDER_NO: "T2",
                    F_CREATED_AT: "2026-06-17 09:30:00",
                    F_PRODUCT_NAME: "趣白全自动洗面奶打泡机",
                    F_PAID_AMOUNT: 338,
                    F_REFUND_AMOUNT: 0,
                    F_QUANTITY: 2,
                    "洗面奶数量": 0,
                    "洗面奶有效销售额": 0,
                },
            }
        elif table_id == "time_priority_orders":
            yield {
                "record_id": "created_in_window_paid_later",
                "fields": {
                    F_ORDER_NO: "D-created",
                    F_CREATED_AT: "2026-06-19 08:30:00",
                    "支付时间": "2026-06-19 10:30:00",
                    F_PAID_AMOUNT: 169,
                    F_REFUND_AMOUNT: 0,
                    F_QUANTITY: 1,
                },
            }


class FakePreviousSnapshotClient:
    def iter_records(self, table_id: str, field_names: list[str] | None = None):
        yield {
            "record_id": "prev_old",
            "fields": {
                F_PLATFORM: "天猫",
                "采集日期": "2026-06-18",
                "本次采集时间": "2026-06-18 12:52:39",
                "本次投流消耗": 3000,
                "本次投流成交金额": 7000,
            },
        }
        yield {
            "record_id": "prev_latest_cumulative_only",
            "fields": {
                F_PLATFORM: "天猫",
                "采集日期": "2026-06-18",
                "本次采集时间": "2026-06-18 13:53:47",
                "今日累计投流消耗": 3133.55,
                "今日累计投流成交金额": 7436,
            },
        }
        yield {
            "record_id": "future_row",
            "fields": {
                F_PLATFORM: "天猫",
                "采集日期": "2026-06-18",
                "本次采集时间": "2026-06-18 14:11:43",
                "今日累计投流消耗": 3261.72,
                "今日累计投流成交金额": 7605,
            },
        }
