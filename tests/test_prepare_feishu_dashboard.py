from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.prepare_feishu_dashboard import (
    FeishuDashboardReadOnlyClient,
    build_dashboard_prompt,
    build_field_source_audit,
    parse_bitable_url,
    write_html_dashboard,
    write_markdown,
)


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict[str, Any]:
        return self.payload


def test_parse_bitable_url_extracts_app_table_and_view():
    parsed = parse_bitable_url(
        "https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe?table=tblepMIg19Ov1kSw&view=vewQvBlgJF"
    )

    assert parsed == {
        "url": "https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe?table=tblepMIg19Ov1kSw&view=vewQvBlgJF",
        "app_token": "KhbEbksLbauw0fssL6EcKAnlnOe",
        "table_id": "tblepMIg19Ov1kSw",
        "view_id": "vewQvBlgJF",
    }


def test_dashboard_prompt_keeps_source_tables_read_only():
    prompt = build_dashboard_prompt(
        {"table_name": "公式动态经营汇总表"},
        "经营驾驶舱_图表版",
    )

    assert "不要修改任何数据表、字段、公式、记录或视图" in prompt
    assert "公式动态经营汇总表" in prompt
    assert "唯一数据源" in prompt
    assert "经营驾驶舱_图表版" in prompt
    assert "日期切片器" in prompt
    assert "平台切片器" in prompt


def test_read_only_client_uses_get_for_fields_records_and_dashboards(monkeypatch, tmp_path):
    calls: list[dict[str, Any]] = []

    def fake_load_settings():
        return type("Settings", (), {"feishu_app_id": "app_id", "feishu_app_secret": "secret"})()

    class FakeOpenApiClient:
        base_url = "https://open.feishu.cn/open-apis"

        def __init__(self, app_id: str, app_secret: str) -> None:
            self.app_id = app_id
            self.app_secret = app_secret

        def headers(self) -> dict[str, str]:
            return {"Authorization": "Bearer token"}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if url.endswith("/fields"):
            return FakeResponse({"code": 0, "data": {"items": [{"field_name": "ROI"}]}})
        if url.endswith("/records"):
            return FakeResponse({"code": 0, "data": {"items": [{"fields": {"ROI": 1.2}}]}})
        if url.endswith("/dashboards"):
            return FakeResponse({"code": 0, "data": {"items": [{"name": "old dashboard"}]}})
        raise AssertionError(url)

    monkeypatch.setattr("scripts.prepare_feishu_dashboard.load_settings", fake_load_settings)
    monkeypatch.setattr("scripts.prepare_feishu_dashboard.FeishuOpenApiClient", FakeOpenApiClient)
    monkeypatch.setattr("scripts.prepare_feishu_dashboard.ensure_feishu_no_proxy", lambda: None)
    monkeypatch.setattr("scripts.prepare_feishu_dashboard.requests.get", fake_get)

    client = FeishuDashboardReadOnlyClient("app_token", tmp_path / ".env")

    assert client.list_fields("tbl_a") == [{"field_name": "ROI"}]
    assert client.list_records("tbl_a") == [{"fields": {"ROI": 1.2}}]
    assert client.list_dashboards() == [{"name": "old dashboard"}]
    assert len(calls) == 3
    assert all(call["url"].startswith("https://open.feishu.cn/open-apis/bitable/v1/apps/app_token/") for call in calls)


def test_write_markdown_contains_prompt_and_field_snapshot(tmp_path):
    output = tmp_path / "dashboard.md"
    report = {
        "dashboard_name": "经营驾驶舱_图表版",
        "dashboard_prompt": "请创建仪表盘",
        "sources": [
            {
                "table_name": "公式动态经营汇总表",
                "table_id": "tblepMIg19Ov1kSw",
                "view_id": "vewQvBlgJF",
                "field_count": 2,
                "sample_record_count": 1,
                "field_names": ["日期", "ROI"],
            },
        ],
    }

    write_markdown(report, output)

    data = Path(output).read_text(encoding="utf-8")
    assert "本文件基于只读 Feishu OpenAPI 校验生成" in data
    assert "```text\n请创建仪表盘\n```" in data
    assert "tblepMIg19Ov1kSw" in data
    assert "- ROI" in data


def test_field_source_audit_checks_every_field_against_expected_source():
    report = {
        "app_token": "KhbEbksLbauw0fssL6EcKAnlnOe",
        "app_url": "https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe",
        "generated_at": "2026-06-07T18:00:00",
        "sources": [
            {
                "table_name": "公式动态经营汇总表",
                "table_id": "tblepMIg19Ov1kSw",
                "view_id": "vewQvBlgJF",
                "url": "https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe?table=tblepMIg19Ov1kSw&view=vewQvBlgJF",
                "field_count": 5,
                "dashboard_record_count": 1,
                "field_names": ["统计日期", "平台", "销售额", "退款金额", "ROI"],
                "dashboard_records": [
                    {"统计日期": "2026-06-07", "平台": "全平台总计", "销售额": 100, "退款金额": 12, "ROI": 2}
                ],
            },
        ],
    }

    audit = build_field_source_audit(report)

    assert audit["status"] == "PASS"
    assert audit["actual_source_count"] == 1
    assert audit["expected_source"]["table_id"] == "tblepMIg19Ov1kSw"
    assert audit["expected_source"]["view_id"] == "vewQvBlgJF"
    assert audit["field_count_checked"] == 5
    assert {field["field_name"] for field in audit["fields"]} == {"统计日期", "平台", "销售额", "退款金额", "ROI"}
    assert all(field["source_table_id"] == "tblepMIg19Ov1kSw" for field in audit["fields"])
    assert all(field["source_view_id"] == "vewQvBlgJF" for field in audit["fields"])
    assert all(field["status"] == "PASS" for field in audit["fields"])
    refund_field = next(field for field in audit["fields"] if field["field_name"] == "退款金额")
    assert refund_field["sample_values"] == [12]


def test_write_html_dashboard_embeds_read_only_source_data(tmp_path):
    output = tmp_path / "dashboard.html"
    report = {
        "dashboard_name": "经营驾驶舱_图表版",
        "app_url": "https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe",
        "generated_at": "2026-06-07T18:00:00",
        "sources": [
            {
                "table_name": "公式动态经营汇总表",
                "table_id": "tblepMIg19Ov1kSw",
                "view_id": "vewQvBlgJF",
                "field_names": ["统计日期", "平台", "销售额", "退款金额", "ROI"],
                "dashboard_records": [{"统计日期": "2026-06-07", "平台": "全平台总计", "销售额": 100, "退款金额": 12, "ROI": 2}],
            },
        ],
    }

    write_html_dashboard(report, output)

    html = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in html
    assert "经营驾驶舱_图表版" in html
    assert "tblepMIg19Ov1kSw" in html
    assert "tblufREIgBB4VBAg" not in html
    assert "本仪表盘不写入飞书，不修改表数据或字段" in html
    assert "销售额趋势" in html
    assert "dateWarning" in html
    assert "未来日期" in html
    assert "activeDates" in html
