from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from data_robot.hourly_ad_interval_summary import summarize_hourly_interval
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
    assert rows["天猫"]["区间投流消耗"] == 60
    assert rows["天猫"]["区间投流成交金额"] == 150
    assert rows["天猫"]["区间订单数"] == 1
    assert rows["天猫"]["区间实收款"] == 80
    assert rows["天猫"]["区间退款金额"] == 10
    assert rows["天猫"]["区间订单销售额"] == 70
    assert rows["天猫"]["新增订单数"] == 1
    assert rows["天猫"]["新增销售额"] == 80
    assert rows["天猫"]["新增有效销售额"] == 70
    assert rows["天猫"]["新增投流消耗"] == 60
    assert rows["天猫"]["新增投流成交金额"] == 150
    assert rows["天猫"]["新增投流ROI"] == 2.5
    assert rows["天猫"]["今日累计订单数"] == 2
    assert rows["天猫"]["今日累计销售额"] == 1079
    assert rows["天猫"]["今日累计退款金额"] == 10
    assert rows["天猫"]["今日累计有效销售额"] == 1069
    assert rows["天猫"]["今日累计投流消耗"] == 160
    assert rows["天猫"]["今日累计投流成交金额"] == 350
    assert rows["天猫"]["今日累计投流ROI"] == round(350 / 160, 6)
    assert rows["天猫"]["订单数"] == 1
    assert rows["天猫"]["实际卖出数量"] == 2
    assert rows["天猫"]["销售额"] == 80
    assert rows["天猫"]["退款金额"] == 10
    assert rows["天猫"]["有效销售额"] == 70
    assert rows["天猫"]["商品成本"] == 20
    assert rows["天猫"]["运费成本"] == 5
    assert rows["天猫"]["平台扣点"] == 2
    assert rows["天猫"]["其他费用"] == 1
    assert rows["天猫"]["预估佣金支出"] == 3
    assert rows["天猫"]["达人佣金"] == 3
    assert rows["天猫"]["已知费用后利润"] == 39
    assert rows["天猫"]["已知总投入"] == 91
    assert rows["天猫"]["投流后毛利"] == -21
    assert rows["天猫"]["喷壶数量"] == 2
    assert rows["天猫"]["喷壶有效销售额"] == 70
    assert rows["抖音"]["区间投流消耗"] == 30
    assert rows["抖音"]["区间订单数"] == 1
    assert rows["总计"]["区间投流消耗"] == 90
    assert rows["总计"]["区间订单数"] == 2
    assert rows["总计"]["区间订单销售额"] == 100
    assert rows["总计"]["实际卖出数量"] == 3
    assert rows["总计"]["销售额"] == 110
    assert rows["总计"]["退款金额"] == 10
    assert rows["总计"]["有效销售额"] == 100
    assert rows["总计"]["商品成本"] == 20
    assert rows["总计"]["喷壶数量"] == 2
    assert rows["总计"]["ROI"] == round(100 / 90, 6)
    assert rows["总计"]["新增订单数"] == 2
    assert rows["总计"]["新增销售额"] == 110
    assert rows["总计"]["新增有效销售额"] == 100
    assert rows["总计"]["新增投流消耗"] == 90
    assert rows["总计"]["新增投流成交金额"] == 240
    assert rows["总计"]["新增ROI"] == round(100 / 90, 6)
    assert rows["总计"]["新增投流ROI"] == round(240 / 90, 6)
    assert rows["总计"]["今日累计订单数"] == 3
    assert rows["总计"]["今日累计销售额"] == 1109
    assert rows["总计"]["今日累计有效销售额"] == 1099
    assert rows["总计"]["今日累计投流消耗"] == 190
    assert rows["总计"]["今日累计投流成交金额"] == 440
    assert rows["总计"]["今日累计ROI"] == round(1099 / 190, 6)
    assert rows["总计"]["今日累计投流ROI"] == round(440 / 190, 6)


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
