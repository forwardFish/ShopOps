from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.storage.feishu_bootstrap import FeishuOpenApiClient


DEFAULT_DASHBOARD_NAME = "经营驾驶舱_图表版"
FORMULA_SUMMARY_NAME = "公式动态经营汇总表"
EXPECTED_SOURCE_TABLE_ID = "tblepMIg19Ov1kSw"
EXPECTED_SOURCE_VIEW_ID = "vewQvBlgJF"
HTML_TEMPLATE_VERSION = "2026-06-07"


class FeishuDashboardReadOnlyClient:
    def __init__(self, app_token: str, env_path: Path) -> None:
        ensure_feishu_no_proxy()
        self.app_token = app_token
        self.env_path = env_path
        self.settings = load_settings()
        self.client = FeishuOpenApiClient(self.settings.feishu_app_id, self.settings.feishu_app_secret)

    def request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(
            f"{self.client.base_url}{path}",
            headers=self.client.headers(),
            params=params,
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError as exc:
            text = response.text[:1000]
            raise RuntimeError(f"Feishu API GET {path} returned non-JSON HTTP {response.status_code}: {text}") from exc
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API GET {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def list_tables(self) -> list[dict[str, Any]]:
        return self.client.list_tables(self.app_token)

    def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request(f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            fields.extend(data.get("items", []) or [])
            if not data.get("has_more"):
                return fields
            page_token = data.get("page_token")

    def list_records(self, table_id: str, limit: int = 5) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while len(records) < limit:
            params: dict[str, Any] = {"page_size": min(500, max(1, limit - len(records)))}
            if page_token:
                params["page_token"] = page_token
            data = self.request(f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items", []) or [])
            if not data.get("has_more"):
                return records[:limit]
            page_token = data.get("page_token")
        return records[:limit]

    def list_records_for_dashboard(self, table_id: str, max_records: int = 500) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while len(records) < max_records:
            params: dict[str, Any] = {"page_size": min(500, max(1, max_records - len(records)))}
            if page_token:
                params["page_token"] = page_token
            data = self.request(f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items", []) or [])
            if not data.get("has_more"):
                return records[:max_records]
            page_token = data.get("page_token")
        return records[:max_records]

    def list_dashboards(self) -> list[dict[str, Any]]:
        dashboards: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request(f"/bitable/v1/apps/{self.app_token}/dashboards", params=params)
            dashboards.extend(data.get("items", []) or [])
            if not data.get("has_more"):
                return dashboards
            page_token = data.get("page_token")


def parse_bitable_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    match = re.search(r"/base/([^/?#]+)", parsed.path)
    app_token = match.group(1) if match else ""
    query = parse_qs(parsed.query)
    return {
        "url": url,
        "app_token": app_token,
        "table_id": (query.get("table") or [""])[0],
        "view_id": (query.get("view") or [""])[0],
    }


def field_names(fields: list[dict[str, Any]]) -> list[str]:
    return [str(field.get("field_name") or field.get("name") or "") for field in fields if field.get("field_name") or field.get("name")]


def table_name(table_id: str, tables: list[dict[str, Any]]) -> str:
    for table in tables:
        if table.get("table_id") == table_id:
            return str(table.get("name") or table_id)
    return table_id


def build_dashboard_prompt(source: dict[str, Any], dashboard_name: str) -> str:
    table_a = source["table_name"]
    return f"""请在当前飞书多维表格 Base 里创建一个名为「{dashboard_name}」的仪表盘。不要修改任何数据表、字段、公式、记录或视图，只基于已有字段配置图表。

数据源：
1. 「{table_a}」：用于按日期、平台查看经营趋势、当日平台对比和全周期汇总。所有图表和指标卡都以这张表作为唯一数据源，不再用其他总计表替代。

顶部放 4 个指标卡，数据源优先选择「{table_a}」：
1. 今日销售额：字段优先用「销售额」，没有则用「有效销售额」，筛选日期=今天，平台=全平台总计。
2. 今日投流消耗：字段用「投流消耗」，筛选日期=今天，平台=全平台总计。
3. 今日利润：字段优先用「利润」，没有则用「投流后毛利」或「经营利润估算」，筛选日期=今天，平台=全平台总计。
4. 今日 ROI：字段用「ROI」或「平台ROI」，筛选日期=今天，平台=全平台总计。

第二行放趋势图，数据源使用「{table_a}」，X 轴为日期字段，按日期升序：
1. 每日销售额趋势折线图，Y 轴为销售额/有效销售额，筛选平台=全平台总计。
2. 每日投流消耗趋势折线图，Y 轴为投流消耗，筛选平台=全平台总计。
3. 每日 ROI 趋势折线图，Y 轴为 ROI/平台ROI，筛选平台=全平台总计。
4. 每日利润趋势折线图，Y 轴为利润/投流后毛利/经营利润估算，筛选平台=全平台总计。

第三行放平台对比图：
1. 各平台 ROI 柱状图：维度=平台，指标=ROI/平台ROI，排除平台=全平台总计，按 ROI 从高到低排序。
2. 各平台利润条形图：维度=平台，指标=利润/投流后毛利/经营利润估算，排除平台=全平台总计，按利润从高到低排序。
3. 各平台投流消耗柱状图：维度=平台，指标=投流消耗，排除平台=全平台总计，按投流消耗从高到低排序。

第四行放数据质量和经营辅助图：
1. 数据状态占比饼图：维度=数据状态，指标=记录数。
2. 缺失项排行榜：维度=缺失项，指标=记录数。

添加 2 个切片器并尽量联动所有相关图表：
1. 日期切片器：字段选择日期/统计日期。
2. 平台切片器：字段选择平台。

整体风格要像老板经营驾驶舱，突出销售额、投流消耗、利润、ROI；布局紧凑，优先让移动端也能看清关键指标。"""


def build_report(
    app_token: str,
    sources: list[dict[str, str]],
    client: FeishuDashboardReadOnlyClient,
    dashboard_name: str,
    dashboard_record_limit: int = 500,
) -> dict[str, Any]:
    tables = client.list_tables()
    dashboards = client.list_dashboards()
    enriched_sources: list[dict[str, Any]] = []
    for source in sources:
        fields = client.list_fields(source["table_id"])
        samples = client.list_records(source["table_id"], limit=3)
        dashboard_records = client.list_records_for_dashboard(source["table_id"], max_records=dashboard_record_limit)
        enriched_sources.append(
            {
                **source,
                "table_name": table_name(source["table_id"], tables),
                "field_count": len(fields),
                "field_names": field_names(fields),
                "sample_record_count": len(samples),
                "sample_fields": [(item.get("fields") or {}) for item in samples],
                "dashboard_record_count": len(dashboard_records),
                "dashboard_records": [(item.get("fields") or {}) for item in dashboard_records],
            }
        )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "read_only_dashboard_preparation",
        "app_token": app_token,
        "app_url": feishu_base_url(app_token),
        "dashboard_name": dashboard_name,
        "openapi_boundary": "Feishu OpenAPI currently exposes dashboard listing for this flow; dashboard creation/configuration must be completed in the Feishu UI or Bitable AI.",
        "source_tables_seen": [
            {"table_id": item.get("table_id"), "name": item.get("name")}
            for item in tables
            if item.get("table_id") in {source["table_id"] for source in enriched_sources}
        ],
        "dashboards_seen": dashboards,
        "sources": enriched_sources,
        "dashboard_prompt": build_dashboard_prompt(enriched_sources[0], dashboard_name),
    }


def build_field_source_audit(report: dict[str, Any]) -> dict[str, Any]:
    sources = report["sources"]
    source = sources[0] if sources else {}
    fields = source.get("field_names") or []
    records = source.get("dashboard_records") or []
    table_id = source.get("table_id")
    view_id = source.get("view_id")
    table_name = source.get("table_name")
    source_url = source.get("url")
    source_matches_expected = (
        len(sources) == 1 and table_id == EXPECTED_SOURCE_TABLE_ID and view_id == EXPECTED_SOURCE_VIEW_ID
    )
    field_results = []
    for field_name in fields:
        values = [record.get(field_name) for record in records if record.get(field_name) not in (None, "")]
        field_results.append(
            {
                "field_name": field_name,
                "source_table_id": table_id,
                "source_view_id": view_id,
                "source_table_name": table_name,
                "source_url": source_url,
                "record_count_checked": len(records),
                "nonblank_count": len(values),
                "sample_values": values[:3],
                "status": "PASS" if source_matches_expected else "FAIL",
            }
        )
    return {
        "generated_at": report["generated_at"],
        "status": "PASS" if source_matches_expected and all(item["status"] == "PASS" for item in field_results) else "FAIL",
        "expected_source": {
            "app_token": report["app_token"],
            "table_id": EXPECTED_SOURCE_TABLE_ID,
            "view_id": EXPECTED_SOURCE_VIEW_ID,
            "url": f"{report['app_url']}?table={EXPECTED_SOURCE_TABLE_ID}&view={EXPECTED_SOURCE_VIEW_ID}",
        },
        "actual_source_count": len(sources),
        "actual_sources": [
            {
                "table_id": item.get("table_id"),
                "view_id": item.get("view_id"),
                "table_name": item.get("table_name"),
                "url": item.get("url"),
                "field_count": item.get("field_count"),
                "dashboard_record_count": item.get("dashboard_record_count"),
            }
            for item in sources
        ],
        "field_count_checked": len(field_results),
        "fields": field_results,
    }


def write_field_source_audit(report: dict[str, Any], path: Path) -> None:
    audit = build_field_source_audit(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_markdown(report: dict[str, Any], path: Path) -> None:
    sources = report["sources"]
    lines = [
        f"# {report['dashboard_name']}",
        "",
        "## 边界",
        "",
        "- 本文件基于只读 Feishu OpenAPI 校验生成。",
        "- 不修改原始表数据、字段、公式、记录或视图。",
        "- 飞书仪表盘组件创建需要在飞书 UI 或多维表格 AI 中完成；本文件提供可直接粘贴的配置文本。",
        "",
        "## 数据源",
        "",
    ]
    for source in sources:
        lines.extend(
            [
                f"- {source['table_name']}",
                f"  - table_id: `{source['table_id']}`",
                f"  - view_id: `{source['view_id']}`",
                f"  - 字段数: {source['field_count']}",
                f"  - 样例记录数: {source['sample_record_count']}",
            ]
        )
    lines.extend(
        [
            "",
            "## 飞书仪表盘 AI 提示词",
            "",
            "```text",
            report["dashboard_prompt"],
            "```",
            "",
            "## 字段快照",
            "",
        ]
    )
    for source in sources:
        lines.extend([f"### {source['table_name']}", ""])
        lines.extend(f"- {name}" for name in source["field_names"])
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html_dashboard(report: dict[str, Any], path: Path) -> None:
    payload = {
        "dashboardName": report["dashboard_name"],
        "appUrl": report["app_url"],
        "generatedAt": report["generated_at"],
        "templateVersion": HTML_TEMPLATE_VERSION,
        "sources": [
            {
                "tableName": source["table_name"],
                "tableId": source["table_id"],
                "viewId": source["view_id"],
                "fields": source["field_names"],
                "records": source["dashboard_records"],
            }
            for source in report["sources"]
        ],
    }
    html = HTML_TEMPLATE.replace("__DASHBOARD_DATA__", json.dumps(payload, ensure_ascii=False))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ShopOps 经营驾驶舱</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #1f2329;
      --muted: #646a73;
      --line: #dee0e3;
      --blue: #2b6de5;
      --green: #1f9d68;
      --red: #d83931;
      --amber: #b7791f;
      --violet: #7b61ff;
      font-family: Inter, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--ink); }
    header { padding: 20px 24px 14px; background: var(--panel); border-bottom: 1px solid var(--line); }
    main { padding: 20px 24px 28px; display: grid; gap: 16px; }
    h1 { margin: 0; font-size: 24px; line-height: 1.25; font-weight: 700; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 16px; line-height: 1.35; }
    .sub { margin-top: 6px; color: var(--muted); font-size: 13px; }
    .warning { display: none; margin-top: 12px; padding: 9px 11px; border: 1px solid #f3c969; background: #fff8e6; color: #7a4d00; border-radius: 6px; font-size: 13px; }
    .filters { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; align-items: center; }
    label { color: var(--muted); font-size: 13px; display: grid; gap: 4px; }
    select { min-width: 150px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--ink); }
    .grid { display: grid; gap: 16px; }
    .cards { grid-template-columns: repeat(4, minmax(150px, 1fr)); }
    .two { grid-template-columns: repeat(2, minmax(260px, 1fr)); }
    .three { grid-template-columns: repeat(3, minmax(220px, 1fr)); }
    .card, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    .metric-label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
    .metric-value { font-size: 25px; line-height: 1.15; font-weight: 720; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .metric-note { margin-top: 8px; color: var(--muted); font-size: 12px; }
    svg { width: 100%; height: 260px; display: block; overflow: visible; }
    .axis { stroke: #b7bcc7; stroke-width: 1; }
    .gridline { stroke: #edf0f5; stroke-width: 1; }
    .line { fill: none; stroke: var(--blue); stroke-width: 2.5; }
    .bar { fill: var(--blue); }
    .bar.green { fill: var(--green); }
    .bar.amber { fill: var(--amber); }
    .bar.red { fill: var(--red); }
    .label { fill: var(--muted); font-size: 11px; }
    .empty { color: var(--muted); font-size: 13px; padding: 34px 0; text-align: center; border: 1px dashed var(--line); border-radius: 6px; }
    .table-wrap { overflow: auto; max-height: 340px; border: 1px solid var(--line); border-radius: 6px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }
    th, td { padding: 8px 10px; border-bottom: 1px solid #edf0f5; text-align: left; white-space: nowrap; }
    th { position: sticky; top: 0; background: #f2f4f8; color: #333842; font-weight: 650; }
    footer { color: var(--muted); font-size: 12px; padding: 0 24px 22px; }
    @media (max-width: 980px) {
      header, main, footer { padding-left: 14px; padding-right: 14px; }
      .cards, .two, .three { grid-template-columns: 1fr; }
      svg { height: 230px; }
      .metric-value { font-size: 22px; }
    }
  </style>
</head>
<body>
  <header>
    <h1 id="title">ShopOps 经营驾驶舱</h1>
    <div class="sub" id="meta"></div>
    <div class="warning" id="dateWarning"></div>
    <div class="filters">
      <label>日期<select id="dateFilter"></select></label>
      <label>平台<select id="platformFilter"></select></label>
    </div>
  </header>
  <main>
    <section class="grid cards" id="metrics"></section>
    <section class="grid two">
      <div class="panel"><h2>销售额趋势</h2><div id="salesTrend"></div></div>
      <div class="panel"><h2>投流消耗趋势</h2><div id="spendTrend"></div></div>
      <div class="panel"><h2>ROI 趋势</h2><div id="roiTrend"></div></div>
      <div class="panel"><h2>利润趋势</h2><div id="profitTrend"></div></div>
    </section>
    <section class="grid three">
      <div class="panel"><h2>平台 ROI 对比</h2><div id="platformRoi"></div></div>
      <div class="panel"><h2>平台利润对比</h2><div id="platformProfit"></div></div>
      <div class="panel"><h2>平台投流消耗</h2><div id="platformSpend"></div></div>
    </section>
    <section class="grid two">
      <div class="panel"><h2>数据状态</h2><div id="statusTable"></div></div>
      <div class="panel"><h2>源表字段与记录</h2><div id="sourceTable"></div></div>
    </section>
  </main>
  <footer id="footer"></footer>
  <script>
    const DASHBOARD_DATA = __DASHBOARD_DATA__;
    const dailySource = DASHBOARD_DATA.sources[0] || { records: [] };

    const fieldChoices = {
      date: ["统计日期", "日期", "统计范围"],
      platform: ["平台"],
      sales: ["销售额", "有效销售额"],
      spend: ["投流消耗"],
      profit: ["利润", "投流后毛利", "经营利润估算", "已知费用后利润"],
      roi: ["ROI", "平台ROI"],
      status: ["数据状态"],
      missing: ["缺失项"]
    };

    function pick(row, names) {
      for (const name of names) {
        if (row[name] !== undefined && row[name] !== null && row[name] !== "") return row[name];
      }
      return null;
    }
    function num(value) {
      if (Array.isArray(value)) value = value.map(v => typeof v === "object" ? (v.text || "") : String(v)).join("");
      if (value === null || value === undefined || value === "") return null;
      const n = Number(String(value).replace(/,/g, ""));
      return Number.isFinite(n) ? n : null;
    }
    function str(value) {
      if (Array.isArray(value)) return value.map(v => typeof v === "object" ? (v.text || "") : String(v)).join("");
      return value === null || value === undefined ? "" : String(value);
    }
    function rowDate(row) { return str(pick(row, fieldChoices.date)); }
    function rowPlatform(row) { return str(pick(row, fieldChoices.platform)); }
    function formatMoney(value) {
      const n = num(value);
      if (n === null) return "-";
      return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }
    function formatRatio(value) {
      const n = num(value);
      if (n === null) return "-";
      return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }
    function unique(items) { return [...new Set(items.filter(Boolean))].sort(); }
    function selectedRows() {
      const date = document.getElementById("dateFilter").value;
      const platform = document.getElementById("platformFilter").value;
      return dailySource.records.filter(row => {
        const okDate = date === "__all__" || rowDate(row) === date;
        const okPlatform = platform === "__all__" || rowPlatform(row) === platform;
        return okDate && okPlatform;
      });
    }
    function allPlatformRows() {
      const date = document.getElementById("dateFilter").value;
      return dailySource.records.filter(row => {
        const platform = rowPlatform(row);
        return platform && platform !== "全平台总计" && (date === "__all__" || rowDate(row) === date);
      });
    }
    function metricRow(rows) {
      return rows.find(row => rowPlatform(row) === "全平台总计") || rows[0] || {};
    }
    function initFilters() {
      const dates = unique(dailySource.records.map(rowDate));
      const platforms = unique(dailySource.records.map(rowPlatform));
      const generatedDate = (DASHBOARD_DATA.generatedAt || "").slice(0, 10);
      const activeDates = unique(dailySource.records.filter(row => {
        return [fieldChoices.sales, fieldChoices.spend, fieldChoices.profit, fieldChoices.roi].some(names => (num(pick(row, names)) || 0) !== 0);
      }).map(rowDate));
      const defaultDate = dates.includes(generatedDate) ? generatedDate : (activeDates.at(-1) || dates.at(-1) || "__all__");
      fillSelect("dateFilter", [["__all__", "全部日期"], ...dates.map(v => [v, v])], defaultDate);
      fillSelect("platformFilter", [["__all__", "全部平台"], ...platforms.map(v => [v, v])], platforms.includes("全平台总计") ? "全平台总计" : "__all__");
      renderDateWarning(dates, generatedDate);
      document.getElementById("dateFilter").addEventListener("change", render);
      document.getElementById("platformFilter").addEventListener("change", render);
    }
    function renderDateWarning(dates, generatedDate) {
      const futureDates = dates.filter(date => /^\d{4}-\d{2}-\d{2}$/.test(date) && generatedDate && date > generatedDate);
      const el = document.getElementById("dateWarning");
      if (!futureDates.length) return;
      el.style.display = "block";
      const first = futureDates[0], last = futureDates[futureDates.length - 1];
      el.textContent = `检测到 ${futureDates.length} 个未来日期（${first} 至 ${last}），默认优先显示当前日期或最近有数据日期；请核对源表日期口径。`;
    }
    function fillSelect(id, options, selected) {
      const el = document.getElementById(id);
      el.innerHTML = options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
      el.value = selected;
    }
    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
    }
    function renderMetrics(rows) {
      const row = metricRow(rows);
      const cards = [
        ["销售额", formatMoney(pick(row, fieldChoices.sales)), "销售额/有效销售额"],
        ["投流消耗", formatMoney(pick(row, fieldChoices.spend)), "广告投放花费"],
        ["利润", formatMoney(pick(row, fieldChoices.profit)), "利润/毛利/估算利润"],
        ["ROI", formatRatio(pick(row, fieldChoices.roi)), "销售额 ÷ 投流消耗"]
      ];
      document.getElementById("metrics").innerHTML = cards.map(([label, value, note]) => `
        <div class="card">
          <div class="metric-label">${escapeHtml(label)}</div>
          <div class="metric-value">${escapeHtml(value)}</div>
          <div class="metric-note">${escapeHtml(note)}</div>
        </div>`).join("");
    }
    function series(fieldNames) {
      const platform = document.getElementById("platformFilter").value;
      const rows = dailySource.records.filter(row => platform === "__all__" || rowPlatform(row) === platform);
      const byDate = new Map();
      for (const row of rows) {
        const date = rowDate(row);
        const value = num(pick(row, fieldNames));
        if (!date || value === null) continue;
        byDate.set(date, (byDate.get(date) || 0) + value);
      }
      return [...byDate.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([label, value]) => ({ label, value }));
    }
    function platformSeries(fieldNames) {
      const rows = allPlatformRows();
      const byPlatform = new Map();
      for (const row of rows) {
        const platform = rowPlatform(row);
        const value = num(pick(row, fieldNames));
        if (!platform || value === null) continue;
        byPlatform.set(platform, (byPlatform.get(platform) || 0) + value);
      }
      return [...byPlatform.entries()].sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label, value }));
    }
    function renderLine(target, data) {
      if (!data.length) return empty(target);
      const width = 640, height = 260, pad = 34;
      const values = data.map(d => d.value);
      const min = Math.min(0, ...values), max = Math.max(...values, 1);
      const x = i => pad + (data.length === 1 ? 0 : i * (width - pad * 2) / (data.length - 1));
      const y = v => height - pad - ((v - min) / (max - min || 1)) * (height - pad * 2);
      const points = data.map((d, i) => `${x(i)},${y(d.value)}`).join(" ");
      document.getElementById(target).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img">
        <line class="axis" x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"></line>
        <line class="axis" x1="${pad}" y1="${pad}" x2="${pad}" y2="${height-pad}"></line>
        <polyline class="line" points="${points}"></polyline>
        ${data.map((d, i) => `<circle cx="${x(i)}" cy="${y(d.value)}" r="3" fill="var(--blue)"><title>${escapeHtml(d.label)}: ${formatMoney(d.value)}</title></circle>`).join("")}
        ${data.map((d, i) => i % Math.ceil(data.length / 6 || 1) === 0 ? `<text class="label" x="${x(i)}" y="${height-10}" text-anchor="middle">${escapeHtml(d.label.slice(5) || d.label)}</text>` : "").join("")}
        <text class="label" x="${pad}" y="18">${formatMoney(max)}</text>
      </svg>`;
    }
    function renderBars(target, data, tone = "blue") {
      if (!data.length) return empty(target);
      const width = 640, height = 260, pad = 34;
      const max = Math.max(...data.map(d => Math.abs(d.value)), 1);
      const barW = Math.max(18, (width - pad * 2) / data.length - 12);
      document.getElementById(target).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img">
        <line class="axis" x1="${pad}" y1="${height-pad}" x2="${width-pad}" y2="${height-pad}"></line>
        ${data.map((d, i) => {
          const x = pad + i * ((width - pad * 2) / data.length) + 6;
          const h = Math.max(2, Math.abs(d.value) / max * (height - pad * 2));
          const y = height - pad - h;
          return `<rect class="bar ${tone}" x="${x}" y="${y}" width="${barW}" height="${h}"><title>${escapeHtml(d.label)}: ${formatMoney(d.value)}</title></rect>
            <text class="label" x="${x + barW / 2}" y="${height-10}" text-anchor="middle">${escapeHtml(d.label.slice(0, 4))}</text>`;
        }).join("")}
      </svg>`;
    }
    function empty(target) {
      document.getElementById(target).innerHTML = '<div class="empty">当前筛选下没有可展示数据</div>';
    }
    function renderStatus(rows) {
      const counts = new Map();
      for (const row of rows) {
        const key = str(pick(row, fieldChoices.status)) || "未标记";
        counts.set(key, (counts.get(key) || 0) + 1);
      }
      const data = [...counts.entries()].map(([status, count]) => ({ status, count }));
      document.getElementById("statusTable").innerHTML = table(["状态", "记录数"], data.map(d => [d.status, d.count]));
    }
    function renderSources() {
      document.getElementById("sourceTable").innerHTML = table(
        ["数据源", "表 ID", "字段数", "拉取记录数"],
        DASHBOARD_DATA.sources.map(s => [s.tableName, s.tableId, s.fields.length, s.records.length])
      );
    }
    function table(headers, rows) {
      return `<div class="table-wrap"><table><thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }
    function render() {
      const rows = selectedRows();
      renderMetrics(rows);
      renderLine("salesTrend", series(fieldChoices.sales));
      renderLine("spendTrend", series(fieldChoices.spend));
      renderLine("roiTrend", series(fieldChoices.roi));
      renderLine("profitTrend", series(fieldChoices.profit));
      renderBars("platformRoi", platformSeries(fieldChoices.roi), "green");
      renderBars("platformProfit", platformSeries(fieldChoices.profit), "amber");
      renderBars("platformSpend", platformSeries(fieldChoices.spend), "blue");
      renderStatus(rows);
      renderSources();
    }
    document.getElementById("title").textContent = DASHBOARD_DATA.dashboardName;
    document.getElementById("meta").textContent = `只读数据源：${dailySource.tableName || "-"}，生成时间：${DASHBOARD_DATA.generatedAt}`;
    document.getElementById("footer").textContent = `数据来自 ${DASHBOARD_DATA.appUrl}；本仪表盘不写入飞书，不修改表数据或字段。`;
    initFilters();
    render();
  </script>
</body>
</html>
"""


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Prepare a read-only Feishu dashboard implementation pack for existing summary tables.")
    parser.add_argument("urls", nargs="*", help="Feishu Base table URLs. Defaults to the two ShopOps formula summary tables.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--dashboard-name", default=DEFAULT_DASHBOARD_NAME)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--output-json", default="docs/live-evidence/feishu-dashboard/dashboard-readiness.json")
    parser.add_argument("--output-md", default="docs/feishu-dashboard-setup.md")
    parser.add_argument("--output-html", default="docs/live-evidence/feishu-dashboard/shopops-dashboard.html")
    parser.add_argument("--output-field-audit", default="docs/live-evidence/feishu-dashboard/field-source-audit.json")
    parser.add_argument("--dashboard-record-limit", type=int, default=500)
    args = parser.parse_args()

    default_urls = [
        f"https://my.feishu.cn/base/{args.app_token}?table={EXPECTED_SOURCE_TABLE_ID}&view={EXPECTED_SOURCE_VIEW_ID}",
    ]
    urls = args.urls or default_urls
    sources = [parse_bitable_url(url) for url in urls]
    app_tokens = {source["app_token"] for source in sources if source["app_token"]}
    app_token = args.app_token or next(iter(app_tokens), "")
    if not app_token:
        raise RuntimeError("Missing Feishu app token")
    if any(source["app_token"] and source["app_token"] != app_token for source in sources):
        raise RuntimeError("All source URLs must belong to the same Feishu Base")
    for source in sources:
        if not source["table_id"]:
            source["table_id"] = EXPECTED_SOURCE_TABLE_ID
            source["view_id"] = EXPECTED_SOURCE_VIEW_ID
            source["url"] = f"https://my.feishu.cn/base/{app_token}?table={EXPECTED_SOURCE_TABLE_ID}&view={EXPECTED_SOURCE_VIEW_ID}"
    if len(sources) != 1:
        raise RuntimeError("This dashboard pack expects exactly one source table URL: the formula summary table")
    if sources[0]["table_id"] != EXPECTED_SOURCE_TABLE_ID or sources[0]["view_id"] != EXPECTED_SOURCE_VIEW_ID:
        raise RuntimeError(
            "This dashboard pack expects source table "
            f"{EXPECTED_SOURCE_TABLE_ID} and view {EXPECTED_SOURCE_VIEW_ID}"
        )

    client = FeishuDashboardReadOnlyClient(app_token, Path(args.env_path))
    report = build_report(app_token, sources, client, args.dashboard_name, dashboard_record_limit=args.dashboard_record_limit)
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(report, Path(args.output_md))
    write_html_dashboard(report, Path(args.output_html))
    output_field_audit = Path(args.output_field_audit)
    write_field_source_audit(report, output_field_audit)
    print(
        json.dumps(
            {
                "status": "PASS",
                "output_json": str(output_json.resolve()),
                "output_md": str(Path(args.output_md).resolve()),
                "output_html": str(Path(args.output_html).resolve()),
                "output_field_audit": str(output_field_audit.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
