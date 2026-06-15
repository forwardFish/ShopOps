from __future__ import annotations

from pathlib import Path

import data_robot.status as status_module
from data_robot.status import build_status, selected_task_keys
from data_robot.tasks import TASKS


def test_status_selected_task_keys_filters_by_platform():
    assert selected_task_keys(["pinduoduo"], None) == ["pinduoduo_orders", "pinduoduo_ads"]
    assert selected_task_keys(["pinduoduo"], ["pinduoduo_orders", "tmall_orders"]) == ["pinduoduo_orders"]


def test_build_status_reports_ready_for_complete_archive_without_cdp(tmp_path: Path):
    task = TASKS["pinduoduo_orders"]
    platform_dir = tmp_path / "0613" / task.platform
    platform_dir.mkdir(parents=True)
    data_file = platform_dir / "20260613-010000_pinduoduo_orders_orders.csv"
    manifest = platform_dir / "20260613-010000_pinduoduo_orders_orders_manifest.json"
    data_file.write_text("order_no,amount\nO1,1\n", encoding="utf-8")
    manifest.write_text('{"task":"pinduoduo_orders"}', encoding="utf-8")

    summary = build_status(
        date_token="0613",
        archive_root=tmp_path,
        platforms=["pinduoduo"],
        task_keys=["pinduoduo_orders"],
        min_task_interval_seconds=0,
        include_cdp=False,
    )

    assert summary["status"] == "archive_complete"
    assert summary["can_collect"] is True
    assert summary["archive_status"]["status"] == "complete"
    assert summary["blocked_by_cooldown"] == []
    assert summary["cdp_status"] is None


def test_build_status_reports_not_ready_for_missing_archive_without_cdp(tmp_path: Path):
    summary = build_status(
        date_token="0613",
        archive_root=tmp_path,
        platforms=["pinduoduo"],
        task_keys=["pinduoduo_orders"],
        min_task_interval_seconds=0,
        include_cdp=False,
    )

    assert summary["status"] == "archive_incomplete"
    assert summary["can_collect"] is True
    assert summary["archive_status"]["status"] == "incomplete"
    assert summary["archive_status"]["missing_tasks"] == ["pinduoduo_orders"]


def test_build_status_blocks_collection_during_cooldown(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(status_module, "cooldown_remaining", lambda task_key, seconds: 120)

    summary = build_status(
        date_token="0613",
        archive_root=tmp_path,
        platforms=["pinduoduo"],
        task_keys=["pinduoduo_orders"],
        min_task_interval_seconds=300,
        include_cdp=False,
    )

    assert summary["status"] == "archive_incomplete"
    assert summary["can_collect"] is False
    assert summary["blocked_by_cooldown"] == ["pinduoduo_orders"]
