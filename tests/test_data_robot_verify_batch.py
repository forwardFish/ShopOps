from __future__ import annotations

import json
from pathlib import Path

from data_robot.tasks import TASKS
import data_robot.verify_batch as verify_batch_module
from data_robot.verify_batch import verify_batch


def test_verify_batch_reports_missing_tasks(tmp_path: Path):
    batch = tmp_path / "0611"

    summary = verify_batch(batch, ["pinduoduo_orders"])

    assert summary["status"] == "incomplete"
    assert summary["missing_tasks"] == ["pinduoduo_orders"]
    assert summary["legacy_only_tasks"] == []
    assert summary["tasks"]["pinduoduo_orders"]["files"] == []


def test_verify_batch_finds_archived_file_and_manifest(tmp_path: Path):
    task = TASKS["pinduoduo_orders"]
    platform_dir = tmp_path / "0611" / task.platform
    platform_dir.mkdir(parents=True)
    data_file = platform_dir / "20260612-120000_pinduoduo_orders_orders.csv"
    manifest = platform_dir / "20260612-120000_pinduoduo_orders_orders_manifest.json"
    data_file.write_text("order_no,amount\nO1,1\n", encoding="utf-8")
    manifest.write_text(json.dumps({"task": task.key}), encoding="utf-8")

    summary = verify_batch(tmp_path / "0611", ["pinduoduo_orders"])

    assert summary["status"] == "complete"
    assert summary["missing_tasks"] == []
    assert summary["legacy_only_tasks"] == []
    assert summary["tasks"]["pinduoduo_orders"]["files"] == [str(data_file)]
    assert summary["tasks"]["pinduoduo_orders"]["manifests"] == [str(manifest)]


def test_verify_batch_default_skips_legacy_scan(tmp_path: Path, monkeypatch):
    batch = tmp_path / "0611"

    def fail_if_called(_batch_dir: Path, _task_key: str) -> list[Path]:
        raise AssertionError("legacy scan should be opt-in")

    monkeypatch.setattr(verify_batch_module, "legacy_task_files", fail_if_called)

    summary = verify_batch(batch, ["pinduoduo_orders"])

    assert summary["status"] == "incomplete"
    assert summary["tasks"]["pinduoduo_orders"]["legacy_files"] == []


def test_verify_batch_can_include_legacy_scan(tmp_path: Path, monkeypatch):
    batch = tmp_path / "0611"
    legacy_file = batch / "legacy-order.xlsx"

    monkeypatch.setattr(
        verify_batch_module,
        "legacy_task_files",
        lambda _batch_dir, _task_key: [legacy_file],
    )

    summary = verify_batch(batch, ["pinduoduo_orders"], include_legacy=True)

    assert summary["status"] == "legacy_present"
    assert summary["missing_tasks"] == []
    assert summary["legacy_only_tasks"] == ["pinduoduo_orders"]
    assert summary["tasks"]["pinduoduo_orders"]["legacy_files"] == [str(legacy_file)]
