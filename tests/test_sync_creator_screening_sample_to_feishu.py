from __future__ import annotations

from scripts.sync_creator_screening_sample_to_feishu import (
    F_FETCHED_AT,
    F_REVIEW_STATUS,
    F_SOURCE,
    build_updates,
    scalar_text,
)


def test_scalar_text_accepts_feishu_text_segments():
    assert scalar_text([{"text": "达人"}, {"text": "A"}]) == "达人A"
    assert scalar_text(None) == ""


def test_build_updates_preserves_existing_fields_and_fills_defaults():
    rows = [
        {
            "record_id": "rec1",
            "fields": {
                "unique_key": "creator_1",
                "达人名称": "达人A",
            },
        }
    ]

    updates = build_updates(rows, "2026-06-22 10:00:00")

    assert updates == [
        {
            "record_id": "rec1",
            "fields": {
                "unique_key": "creator_1",
                "达人名称": "达人A",
                F_SOURCE: "达人筛选表历史候选复核",
                F_REVIEW_STATUS: "待确认",
                F_FETCHED_AT: "2026-06-22 10:00:00",
            },
        }
    ]
