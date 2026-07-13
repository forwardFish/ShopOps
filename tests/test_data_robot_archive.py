from __future__ import annotations

import zipfile
from pathlib import Path
import os
import time

from data_robot.common import (
    archive_downloads,
    copy_when_stable,
    evidence_token,
    files_created_since,
    hourly_batch_token,
    matches_task_filename,
    rejected_download_reasons,
    task_download_status,
    task_filename_reject_reason,
    wait_for_watched_files,
    write_archive_manifest,
)
from data_robot.tasks import TASKS


def test_archive_download_uses_date_platform_and_normalized_name(tmp_path: Path):
    source = tmp_path / "orders_export2026-06-12-22-01-40.csv"
    source.write_text("订单号,金额\nO1,1\n", encoding="utf-8")

    archived = archive_downloads(
        TASKS["pinduoduo_orders"],
        [source],
        tmp_path / "archive",
        date_token="0612",
        run_token="20260612-120000",
    )

    assert len(archived) == 1
    target = archived[0].archived
    assert target.parent == tmp_path / "archive" / "0612" / "拼多多"
    assert target.name == "20260612-120000_pinduoduo_orders_orders_orders_export2026-06-12-22-01-40.csv"
    assert target.read_text(encoding="utf-8") == "订单号,金额\nO1,1\n"


def test_archive_download_extracts_zip_tabular_files(tmp_path: Path):
    source = tmp_path / "微信小店订单_wx8248933f80e464e7_2026年06月12日22时04分13秒.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("inside/orders.xlsx", b"fake-xlsx")
        archive.writestr("inside/readme.txt", "skip")

    archived = archive_downloads(
        TASKS["wechat_channels_orders"],
        [source],
        tmp_path / "archive",
        date_token="0612",
        run_token="20260612-130000",
    )

    assert [item.archived.name for item in archived] == [
        "20260612-130000_wechat_channels_orders_orders.xlsx"
    ]
    assert archived[0].archived.read_bytes() == b"fake-xlsx"


def test_archive_download_accepts_hourly_batch_token(tmp_path: Path):
    source = tmp_path / "orders_export2026-06-12-22-01-40.csv"
    source.write_text("ok\n", encoding="utf-8")

    archived = archive_downloads(
        TASKS["pinduoduo_orders"],
        [source],
        tmp_path / "archive",
        date_token=hourly_batch_token("0612", "23"),
        run_token="20260612-230000",
    )

    assert len(archived) == 1
    assert archived[0].archived.parent == tmp_path / "archive" / "0612" / "23点下载" / TASKS["pinduoduo_orders"].platform
    assert evidence_token("0612/23点下载") == "0612-23点下载"


def test_pinduoduo_ads_requires_daily_report_file():
    assert matches_task_filename(TASKS["pinduoduo_ads"], "商品推广_账户_分天数据_20260606至20260612.xls")
    assert not matches_task_filename(TASKS["pinduoduo_ads"], "商品推广_账户_汇总数据_商品_20260606至20260612.xls")


def test_pinduoduo_ads_reject_reason_identifies_summary_report():
    assert (
        task_filename_reject_reason(
            TASKS["pinduoduo_ads"],
            "\u5546\u54c1\u63a8\u5e7f_\u8d26\u6237_\u6c47\u603b\u6570\u636e_\u5546\u54c1_20260627\u81f320260703.xls",
        )
        == "pinduoduo_ads_summary_report_not_daily_report"
    )


def test_downloaded_unmatched_status_keeps_wrong_files_out_of_success(tmp_path: Path):
    source = tmp_path / "\u5546\u54c1\u63a8\u5e7f_\u8d26\u6237_\u6c47\u603b\u6570\u636e_\u5546\u54c1_20260627\u81f320260703.xls"
    source.write_bytes(b"summary")
    archived = archive_downloads(
        TASKS["pinduoduo_ads"],
        [source],
        tmp_path / "archive",
        date_token="0704",
        run_token="20260704-120000",
    )

    assert archived == []
    assert task_download_status([source], archived) == "downloaded_unmatched"
    assert rejected_download_reasons(TASKS["pinduoduo_ads"], [source], archived) == [
        {"path": str(source), "reason": "pinduoduo_ads_summary_report_not_daily_report"}
    ]


def test_archive_download_skips_non_tabular_files(tmp_path: Path):
    source = tmp_path / "screenshot.png"
    source.write_bytes(b"png")

    archived = archive_downloads(
        TASKS["pinduoduo_orders"],
        [source],
        tmp_path / "archive",
        date_token="0612",
        run_token="20260612-140000",
    )

    assert archived == []


def test_archive_download_skips_files_for_other_tasks(tmp_path: Path):
    source = tmp_path / "商品推广_账户_分天数据_20260605至20260611.xls"
    source.write_bytes(b"pdd-ad")

    archived = archive_downloads(
        TASKS["tmall_orders"],
        [source],
        tmp_path / "archive",
        date_token="0612",
        run_token="20260612-160000",
    )

    assert archived == []


def test_matches_task_filename_accepts_expected_patterns():
    assert matches_task_filename(TASKS["tmall_orders"], "ExportOrderList26619229374.xlsx")
    assert matches_task_filename(TASKS["pinduoduo_ads"], "商品推广_账户_分天数据_20260605至20260611.xls")
    assert matches_task_filename(TASKS["douyin_influencer"], "cc30b787-efdc-2106-e16d-c649ab2a3de7_3825214922515152922.xlsx")
    assert not matches_task_filename(TASKS["tmall_orders"], "商品推广_账户_分天数据_20260605至20260611.xls")
    assert not matches_task_filename(TASKS["douyin_influencer"], "全域推广数据_商品_2026-06-05 00_00_00-2026-06-11 23_59_59.xlsx")


def test_files_created_since_returns_only_new_complete_tabular_files(tmp_path: Path):
    old_file = tmp_path / "old.csv"
    old_file.write_text("old", encoding="utf-8")
    old_timestamp = time.time() - 3600
    os.utime(old_file, (old_timestamp, old_timestamp))

    marker = time.time()
    new_file = tmp_path / "new.xlsx"
    partial = tmp_path / "new.xlsx.crdownload"
    image = tmp_path / "screenshot.png"
    new_file.write_bytes(b"xlsx")
    partial.write_bytes(b"partial")
    image.write_bytes(b"png")

    assert files_created_since(tmp_path, marker) == [new_file]


def test_wait_for_watched_files_returns_new_complete_file(tmp_path: Path):
    marker = time.time()
    new_file = tmp_path / "new.csv"
    new_file.write_text("ok", encoding="utf-8")

    assert wait_for_watched_files(tmp_path, marker, timeout_seconds=0) == [new_file]


def test_copy_when_stable_copies_file(tmp_path: Path):
    source = tmp_path / "source.csv"
    target = tmp_path / "target.csv"
    source.write_text("ok", encoding="utf-8")

    copy_when_stable(source, target, attempts=2, delay_seconds=0)

    assert target.read_text(encoding="utf-8") == "ok"


def test_write_archive_manifest_records_archived_files(tmp_path: Path):
    source = tmp_path / "orders_export2026-06-12-22-01-40.csv"
    source.write_text("ok", encoding="utf-8")
    archived = archive_downloads(
        TASKS["pinduoduo_orders"],
        [source],
        tmp_path / "archive",
        date_token="0612",
        run_token="20260612-150000",
    )

    manifest = write_archive_manifest(
        TASKS["pinduoduo_orders"],
        archived,
        tmp_path / "archive",
        date_token="0612",
        run_token="20260612-150000",
        downloaded=[source],
    )

    assert manifest is not None
    text = manifest.read_text(encoding="utf-8")
    assert "pinduoduo_orders" in text
    assert "20260612-150000_pinduoduo_orders_orders_orders_export2026-06-12-22-01-40.csv" in text
