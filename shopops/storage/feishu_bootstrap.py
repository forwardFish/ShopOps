from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from shopops.config import Settings, load_settings
from shopops.models import Metric10Min, MonitorSnapshot, TaskRunLog
from shopops.storage.field_mapping import (
    PLATFORM_QIANNIU_TAOBAO,
    metric_10min_fields,
    monitor_snapshot_fields,
    promotion_item_fields,
    task_log_fields,
)


FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"
TEXT_FIELD = 1
NUMBER_FIELD = 2


class FeishuBootstrapError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlatformTableSpec:
    env_name: str
    key: str
    name: str
    fields: list[dict[str, Any]]


def text_field(name: str) -> dict[str, Any]:
    return {"field_name": name, "type": TEXT_FIELD}


def number_field(name: str) -> dict[str, Any]:
    return {"field_name": name, "type": NUMBER_FIELD}


def fields_from_payload(payload: dict[str, Any], number_keys: set[str] | None = None) -> list[dict[str, Any]]:
    number_keys = number_keys or set()
    fields: list[dict[str, Any]] = []
    for key, value in payload.items():
        if key in number_keys or isinstance(value, int | float):
            fields.append(number_field(key))
        else:
            fields.append(text_field(key))
    return fields


def order_table_fields() -> list[dict[str, Any]]:
    return [
        text_field("unique_key"),
        text_field("平台"),
        text_field("数据来源"),
        text_field("店铺ID"),
        text_field("店铺名称"),
        text_field("采集时间"),
        text_field("订单号"),
        text_field("创建时间"),
        text_field("买家昵称"),
        text_field("商品名称"),
        number_field("单价"),
        number_field("数量"),
        text_field("履约/售后状态"),
        text_field("交易状态"),
        number_field("实收款"),
        text_field("操作信息"),
        text_field("页面URL"),
        text_field("页面截图"),
        text_field("采集状态"),
        text_field("错误信息"),
        text_field("原始数据"),
    ]


def promotion_table_fields() -> list[dict[str, Any]]:
    sample = promotion_item_fields(
        "shop",
        "shop_name",
        datetime(2026, 1, 1, 0, 0, 0),
        type("PromotionSample", (), {"channel": "tuiguangcenter", "cost": 1.0, "raw": {}})(),
        PLATFORM_QIANNIU_TAOBAO,
    )
    return fields_from_payload(sample, {"花费"})


def monitor_snapshot_table_fields() -> list[dict[str, Any]]:
    sample = monitor_snapshot_fields(
        MonitorSnapshot(
            unique_key="sample",
            fetched_at=datetime(2026, 1, 1, 0, 0, 0),
            shop_id="shop",
            shop_name="shop_name",
            order_source="crawler",
            promotion_source="qianniu_pc",
            data_status="normal",
            promotion_center_cost=1.0,
            total_cost=1.0,
            order_count=1,
            paid_order_count=1,
            total_amount=1.0,
            roi=1.0,
            cac=1.0,
            error_message=None,
            alert_flag=False,
        )
    )
    return fields_from_payload(sample, {"推广中心花费", "总推广消耗", "今日订单数", "今日成交额", "实时ROI", "获客成本"})


def metrics_10min_table_fields() -> list[dict[str, Any]]:
    sample = metric_10min_fields(
        Metric10Min(
            unique_key="sample",
            window_start=datetime(2026, 1, 1, 0, 0, 0),
            window_end=datetime(2026, 1, 1, 0, 10, 0),
            shop_id="shop",
            shop_name="shop_name",
            delta_order_count=1,
            delta_total_amount=1.0,
            delta_cost=1.0,
            delta_roi=1.0,
            delta_cac=1.0,
            data_status="normal",
            abnormal_reason=None,
        )
    )
    return fields_from_payload(sample, {"新增订单数", "新增成交额", "推广消耗", "周期ROI", "周期获客成本"})


def task_log_table_fields() -> list[dict[str, Any]]:
    sample = task_log_fields(
        TaskRunLog(
            task_id="sample",
            task_type="full_collect",
            started_at=datetime(2026, 1, 1, 0, 0, 0),
            ended_at=datetime(2026, 1, 1, 0, 0, 1),
            duration_seconds=1.0,
            shop_id="shop",
            order_status="success",
            promotion_status="success",
            storage_status="success",
            total_status="success",
            fetched_count=1,
            saved_count=1,
            error_code=None,
            error_message=None,
            alerted=False,
        )
    )
    return fields_from_payload(sample, {"耗时秒", "拉取数量", "写入数量"})


def alert_log_table_fields() -> list[dict[str, Any]]:
    return [
        text_field("unique_key"),
        text_field("alert_id"),
        text_field("触发时间"),
        text_field("店铺ID"),
        text_field("告警类型"),
        text_field("告警级别"),
        text_field("告警内容"),
        number_field("当前值"),
        number_field("阈值"),
        text_field("是否已发送"),
        text_field("发送结果"),
    ]


def daily_report_table_fields() -> list[dict[str, Any]]:
    return [
        text_field("unique_key"),
        text_field("日期"),
        text_field("店铺ID"),
        text_field("店铺名称"),
        text_field("日报内容"),
        text_field("生成时间"),
        text_field("是否已发送"),
        text_field("发送结果"),
    ]


def douyin_influencer_commission_table_fields() -> list[dict[str, Any]]:
    return [
        text_field("unique_key"),
        text_field("平台"),
        text_field("数据来源"),
        text_field("店铺ID"),
        text_field("店铺名称"),
        text_field("采集时间"),
        text_field("订单号"),
        text_field("下单时间"),
        text_field("达人ID"),
        text_field("达人昵称"),
        text_field("内容类型"),
        text_field("直播间/视频ID"),
        text_field("商品ID"),
        text_field("商品名称"),
        number_field("支付金额"),
        number_field("佣金率"),
        number_field("预估佣金"),
        number_field("结算佣金"),
        number_field("技术服务费"),
        text_field("结算状态"),
        text_field("原始数据"),
    ]


def douyin_influencer_commission_table_spec() -> PlatformTableSpec:
    return PlatformTableSpec(
        "FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION",
        "douyin_influencer_commission",
        "抖音达人佣金明细表",
        douyin_influencer_commission_table_fields(),
    )


def platform_table_specs(platform_name: str = PLATFORM_QIANNIU_TAOBAO) -> list[PlatformTableSpec]:
    suffix = platform_name.strip() or PLATFORM_QIANNIU_TAOBAO
    return [
        PlatformTableSpec("FEISHU_TABLE_MONITOR_SNAPSHOT", "monitor_snapshot", f"实时监控快照表-{suffix}", monitor_snapshot_table_fields()),
        PlatformTableSpec("FEISHU_TABLE_ORDERS_RAW", "orders_raw", f"订单明细原始表-{suffix}", order_table_fields()),
        PlatformTableSpec("FEISHU_TABLE_PROMOTION_SNAPSHOT", "promotion_snapshot", f"推广数据表-{suffix}", promotion_table_fields()),
        PlatformTableSpec("FEISHU_TABLE_METRICS_10MIN", "metrics_10min", f"十分钟指标表-{suffix}", metrics_10min_table_fields()),
        PlatformTableSpec("FEISHU_TABLE_TASK_LOG", "task_run_log", f"任务运行日志表-{suffix}", task_log_table_fields()),
        PlatformTableSpec("FEISHU_TABLE_ALERT_LOG", "alert_log", f"告警日志表-{suffix}", alert_log_table_fields()),
        PlatformTableSpec("FEISHU_TABLE_DAILY_REPORT", "daily_report", f"每日报告表-{suffix}", daily_report_table_fields()),
    ]


def bootstrap_douyin_influencer_table(
    settings: Settings | None = None,
    env_path: str | Path = ".env",
) -> dict[str, Any]:
    settings = settings or load_settings()
    client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
    app_token = settings.feishu_app_token
    if not app_token:
        raise FeishuBootstrapError("FEISHU_APP_TOKEN is required to add the Douyin influencer table to an existing Bitable")

    spec = douyin_influencer_commission_table_spec()
    existing_tables = client.list_tables(app_token)
    existing_by_name = {str(item.get("name")): item for item in existing_tables if item.get("name")}
    table = client.ensure_table(app_token, spec, existing_by_name)
    table_id = str(table.get("table_id") or "")
    if not table_id:
        raise FeishuBootstrapError("Douyin influencer table response did not include table_id")

    merge_env_file(
        env_path,
        {
            "FEISHU_APP_TOKEN": app_token,
            spec.env_name: table_id,
            f"{spec.env_name}_NAME": spec.name,
        },
    )
    return {
        "app_token": app_token,
        "table": {
            "env_name": spec.env_name,
            "table_id": table_id,
            "table_name": spec.name,
            "reused": table.get("reused", False),
        },
        "env_path": str(env_path),
    }


class FeishuOpenApiClient:
    def __init__(self, app_id: str, app_secret: str, base_url: str = FEISHU_BASE_URL) -> None:
        if not app_id:
            raise FeishuBootstrapError("FEISHU_APP_ID or APP_ID is required")
        if not app_secret:
            raise FeishuBootstrapError("FEISHU_APP_SECRET or APP_SECRET is required")
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self._tenant_access_token: str | None = None

    def tenant_access_token(self) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        data = self._post(
            "/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
            auth=False,
        )
        token = data.get("tenant_access_token")
        if not token:
            raise FeishuBootstrapError("Feishu tenant access token response did not include tenant_access_token")
        self._tenant_access_token = str(token)
        return self._tenant_access_token

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tenant_access_token()}", "Content-Type": "application/json; charset=utf-8"}

    def create_base(self, name: str, folder_token: str = "", time_zone: str = "Asia/Shanghai") -> dict[str, Any]:
        payload = {"name": name, "time_zone": time_zone}
        if folder_token:
            payload["folder_token"] = folder_token
        return self._post("/bitable/v1/apps", payload)

    def transfer_bitable_owner(
        self,
        app_token: str,
        owner_open_id: str,
        old_owner_perm: str = "full_access",
        stay_put: bool = False,
    ) -> dict[str, Any]:
        if not app_token:
            raise FeishuBootstrapError("app_token is required before transferring Bitable ownership")
        if not owner_open_id:
            raise FeishuBootstrapError("owner_open_id is required before transferring Bitable ownership")
        return self._post(
            f"/drive/v1/permissions/{app_token}/members/transfer_owner",
            {"member_type": "openid", "member_id": owner_open_id},
            params={
                "type": "bitable",
                "remove_old_owner": "false",
                "old_owner_perm": old_owner_perm,
                "stay_put": str(stay_put).lower(),
            },
        )

    def list_tables(self, app_token: str) -> list[dict[str, Any]]:
        data = self._get(f"/bitable/v1/apps/{app_token}/tables", {"page_size": 100})
        return list(data.get("items") or [])

    def create_table(self, app_token: str, spec: PlatformTableSpec) -> dict[str, Any]:
        payload = {
            "table": {
                "name": spec.name,
                "default_view_name": "默认视图",
                "fields": spec.fields,
            }
        }
        data = self._post(f"/bitable/v1/apps/{app_token}/tables", payload)
        return {
            "table_id": data.get("table_id") or (data.get("table") or {}).get("table_id"),
            "default_view_id": data.get("default_view_id"),
            "field_id_list": data.get("field_id_list") or [],
        }

    def ensure_table(self, app_token: str, spec: PlatformTableSpec, existing_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
        existing = existing_by_name.get(spec.name)
        if existing:
            return {"table_id": existing.get("table_id"), "reused": True}
        created = self.create_table(app_token, spec)
        return created | {"reused": False}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}{path}", headers=self.headers(), params=params, timeout=30)
        return self._handle_response(response)

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        auth: bool = True,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = self.headers() if auth else {"Content-Type": "application/json; charset=utf-8"}
        kwargs = {"json": payload, "headers": headers, "timeout": 30}
        if params is not None:
            kwargs["params"] = params
        response = requests.post(f"{self.base_url}{path}", **kwargs)
        return self._handle_response(response)

    @staticmethod
    def _handle_response(response: requests.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as exc:
            raise FeishuBootstrapError(f"Feishu API returned non-JSON response: HTTP {response.status_code}") from exc
        if response.status_code >= 400:
            raise FeishuBootstrapError(f"Feishu API HTTP {response.status_code}: {body}")
        if body.get("code") != 0:
            raise FeishuBootstrapError(f"Feishu API error {body.get('code')}: {body.get('msg')}")
        return body.get("data") or body


def bootstrap_platform_tables(
    settings: Settings | None = None,
    platform_name: str = PLATFORM_QIANNIU_TAOBAO,
    base_name: str = "ShopOps 千牛淘宝数据中台",
    folder_token: str = "",
    owner_open_id: str = "",
    env_path: str | Path = ".env",
) -> dict[str, Any]:
    settings = settings or load_settings()
    client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
    app_token = settings.feishu_app_token
    created_base = None
    if not app_token:
        created_base = client.create_base(base_name, folder_token=folder_token)
        app = created_base.get("app") or created_base
        app_token = app.get("app_token")
        if not app_token:
            raise FeishuBootstrapError("create_base response did not include app_token")

    ownership_transfer = None
    if owner_open_id:
        ownership_transfer = client.transfer_bitable_owner(app_token, owner_open_id)

    existing_tables = client.list_tables(app_token)
    existing_by_name = {str(item.get("name")): item for item in existing_tables if item.get("name")}
    table_results: dict[str, Any] = {}
    for spec in platform_table_specs(platform_name):
        table = client.ensure_table(app_token, spec, existing_by_name)
        table_results[spec.key] = {
            "env_name": spec.env_name,
            "table_id": table.get("table_id"),
            "table_name": spec.name,
            "reused": table.get("reused", False),
        }

    env_updates = {"FEISHU_APP_TOKEN": app_token}
    for table in table_results.values():
        env_updates[table["env_name"]] = table["table_id"]
        env_updates[f'{table["env_name"]}_NAME'] = table["table_name"]
    merge_env_file(env_path, env_updates)
    return {
        "app_token": app_token,
        "created_base": created_base,
        "ownership_transfer": ownership_transfer,
        "platform": platform_name,
        "tables": table_results,
        "env_path": str(env_path),
    }


def merge_env_file(path: str | Path, updates: dict[str, str | None]) -> None:
    env_path = Path(path)
    current: dict[str, str] = {}
    order: list[str] = []
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            current[key] = value.strip()
            order.append(key)
    for key, value in updates.items():
        if value is None:
            continue
        if key not in current:
            order.append(key)
        current[key] = str(value)
    env_path.write_text("".join(f"{key}={current[key]}\n" for key in order), encoding="utf-8")
