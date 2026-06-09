from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.models import PromotionItem, dt
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient
from shopops.storage.field_mapping import PROMOTION_CENTER_CHANNEL, PROMOTION_CENTER_NAME, promotion_item_fields


API_URL = "https://1bp.taobao.com/report/query.json"
TEXT_FIELD = 1
NUMBER_FIELD = 2

F_UNIQUE_KEY = "unique_key"
F_PLATFORM = "平台"
F_STAT_DATE = "投放日期"
F_FETCHED_AT = "采集时间"
F_SOURCE = "数据来源"
F_ACTUAL_COST = "实际消耗"
F_COST = "花费"
F_IMPRESSIONS = "展现量"
F_CLICKS = "点击量"
F_ROI = "ROI"
F_GMV = "成交金额"
F_RAW = "原始数据"

DAILY_PROMOTION_FIELDS = [
    (F_UNIQUE_KEY, TEXT_FIELD),
    (F_PLATFORM, TEXT_FIELD),
    (F_STAT_DATE, TEXT_FIELD),
    (F_FETCHED_AT, TEXT_FIELD),
    (F_SOURCE, TEXT_FIELD),
    (F_ACTUAL_COST, NUMBER_FIELD),
    (F_COST, NUMBER_FIELD),
    (F_IMPRESSIONS, NUMBER_FIELD),
    (F_CLICKS, NUMBER_FIELD),
    (F_ROI, NUMBER_FIELD),
    (F_GMV, NUMBER_FIELD),
    (F_RAW, TEXT_FIELD),
]


@dataclass(frozen=True)
class PromotionApiResult:
    fetched_at: datetime
    query_date: str
    cost: float
    api_fields: dict[str, Any]
    raw_status: dict[str, Any]


class PromotionApiError(RuntimeError):
    pass


def _load_promotion_env() -> None:
    _load_dotenv()
    local_path = ROOT / ".env.local"
    if not local_path.exists():
        return
    for line in local_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in {"TAOBAO_PROMOTION_COOKIE", "TAOBAO_PROMOTION_CSRF_ID", "TAOBAO_PROMOTION_LOGIN_POINT_ID"}:
            os.environ[key] = value.strip().strip('"').strip("'")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PromotionApiError(f"{name} is required")
    return value


def parse_promotion_api_response(body: dict[str, Any], fetched_at: datetime, query_date: str) -> PromotionApiResult:
    rows = (body.get("data") or {}).get("list") or []
    info = body.get("info") or {}
    if info.get("ok") is True and rows:
        row = rows[0]
    elif body.get("success") is True and (body.get("data") or {}).get("summary"):
        row = (body.get("data") or {}).get("summary") or {}
    else:
        message = info.get("message") or body.get("message") or body.get("msg") or "promotion API returned no data"
        raise PromotionApiError(str(message))

    cost = row.get("charge")
    if cost is None:
        raise PromotionApiError("promotion API response did not include charge")
    return PromotionApiResult(
        fetched_at=fetched_at,
        query_date=query_date,
        cost=round(float(cost), 2),
        api_fields={
            "charge": row.get("charge"),
            "adPv": row.get("adPv"),
            "click": row.get("click"),
            "roi": row.get("roi"),
            "alipayInshopAmt": row.get("alipayInshopAmt"),
        },
        raw_status={
            "http_shape": "info.data.list" if info else "success.data.summary",
            "info_ok": info.get("ok"),
            "message": info.get("message") or body.get("message") or body.get("msg"),
        },
    )


def fetch_promotion_from_cookie(query_date: str | None = None) -> PromotionApiResult:
    _load_promotion_env()
    query_date = query_date or date.today().isoformat()
    cookie = _required_env("TAOBAO_PROMOTION_COOKIE")
    csrf_id = _required_env("TAOBAO_PROMOTION_CSRF_ID")
    login_point_id = _required_env("TAOBAO_PROMOTION_LOGIN_POINT_ID")
    fetched_at = datetime.now()

    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://qn.taobao.com",
        "pragma": "no-cache",
        "referer": "https://qn.taobao.com/home.htm/tuiguangcenter_new/",
        "sec-ch-ua": '"Chromium";v="117", "Not;A=Brand";v="8"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Qianniu/9.95.01N Safari/537.36",
        "cookie": cookie,
    }
    params = {"csrfId": csrf_id, "bizCode": "universalBP"}
    payload = {
        "source": "home",
        "fromRealTime": True,
        "splitType": "sum",
        "allDay": True,
        "fromHourTable": True,
        "startTime": query_date,
        "endTime": query_date,
        "queryFieldIn": ["charge", "adPv", "click", "roi", "alipayInshopAmt"],
        "csrfId": csrf_id,
        "bizCode": "universalBP",
        "loginPointId": login_point_id,
    }
    response = requests.post(API_URL, params=params, headers=headers, json=payload, timeout=30)
    try:
        body = response.json()
    except ValueError as exc:
        raise PromotionApiError(f"promotion API returned non-JSON HTTP {response.status_code}") from exc
    if response.status_code != 200:
        raise PromotionApiError(f"promotion API HTTP {response.status_code}: {body}")
    return parse_promotion_api_response(body, fetched_at, query_date)


class PromotionFeishuWriter:
    def __init__(self) -> None:
        self.settings = load_settings()
        if not self.settings.feishu_app_token:
            raise PromotionApiError("FEISHU_APP_TOKEN is required")
        if not self.settings.table_promotion_snapshot.startswith("tbl"):
            raise PromotionApiError("FEISHU_TABLE_PROMOTION_SNAPSHOT must be a real tbl... table id")
        self.client = FeishuOpenApiClient(self.settings.feishu_app_id, self.settings.feishu_app_secret)
        self.base_url = FEISHU_BASE_URL.rstrip("/")

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.client.tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.request(method, f"{self.base_url}{path}", headers=self.headers(), json=payload, params=params, timeout=30)
        try:
            body = response.json()
        except ValueError as exc:
            raise PromotionApiError(f"Feishu API returned non-JSON HTTP {response.status_code}") from exc
        if response.status_code >= 400 or body.get("code") != 0:
            raise PromotionApiError(f"Feishu API error HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def find_record(self, unique_key: str) -> tuple[str | None, dict[str, Any] | None]:
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{self.settings.table_promotion_snapshot}/records",
                params=params,
            )
            for item in data.get("items", []) or []:
                fields = item.get("fields") or {}
                if fields.get("unique_key") == unique_key:
                    return str(item.get("record_id")), fields
            if not data.get("has_more"):
                return None, None
            page_token = data.get("page_token")

    def upsert_and_readback(self, result: PromotionApiResult) -> dict[str, Any]:
        item = PromotionItem(
            PROMOTION_CENTER_CHANNEL,
            PROMOTION_CENTER_NAME,
            result.cost,
            None,
            None,
            None,
            "success",
            raw={"source_url": API_URL, "api_fields": result.api_fields},
        )
        fields = promotion_item_fields(
            self.settings.shop_id,
            self.settings.shop_name,
            result.fetched_at,
            item,
            self.settings.feishu_platform_name,
        )
        record_id, _ = self.find_record(str(fields["unique_key"]))
        payload = {"fields": fields}
        if record_id:
            self._request(
                "PUT",
                f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{self.settings.table_promotion_snapshot}/records/{record_id}",
                payload,
            )
        else:
            data = self._request(
                "POST",
                f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{self.settings.table_promotion_snapshot}/records",
                payload,
            )
            record_id = str((data.get("record") or {}).get("record_id") or "")
        _, readback = self.find_record(str(fields["unique_key"]))
        if not readback:
            raise PromotionApiError("Feishu readback did not find the written promotion record")
        return {"record_id": record_id, "written_fields": fields, "readback_fields": readback}


class DailyPromotionFeishuWriter:
    def __init__(self, table_id: str | None = None, platform: str = "天猫") -> None:
        self.settings = load_settings()
        self.app_token = self.settings.shopops_data_center_app_token or self.settings.feishu_app_token
        if not self.app_token:
            raise PromotionApiError("SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN is required")
        self.table_id = table_id or self.settings.table_promotion_snapshot
        if not self.table_id.startswith("tbl"):
            raise PromotionApiError("promotion table id must be a real tbl... table id")
        self.platform = platform
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"
        self.client = FeishuOpenApiClient(self.settings.feishu_app_id, self.settings.feishu_app_secret)
        self.base_url = FEISHU_BASE_URL.rstrip("/")

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.client.tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_duplicate_field: bool = False,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers=self.headers(),
            json=payload,
            params=params,
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise PromotionApiError(f"Feishu API returned non-JSON HTTP {response.status_code}") from exc
        if allow_duplicate_field and body.get("code") == 1254014:
            return {}
        if response.status_code >= 400 or body.get("code") != 0:
            raise PromotionApiError(f"Feishu API error HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def ensure_fields(self) -> list[str]:
        existing = self.field_names()
        created: list[str] = []
        for field_name, field_type in DAILY_PROMOTION_FIELDS:
            if field_name in existing:
                continue
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
                {"field_name": field_name, "type": field_type},
                allow_duplicate_field=True,
            )
            existing.add(field_name)
            created.append(field_name)
        return created

    def field_names(self) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields", params=params)
            for item in data.get("items") or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def find_record(self, unique_key: str) -> tuple[str | None, dict[str, Any] | None]:
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records", params=params)
            for item in data.get("items") or []:
                fields = item.get("fields") or {}
                if scalar_text(fields.get(F_UNIQUE_KEY)) == unique_key:
                    return str(item.get("record_id")), fields
            if not data.get("has_more"):
                return None, None
            page_token = data.get("page_token")

    def upsert_and_readback(self, result: PromotionApiResult) -> dict[str, Any]:
        created_fields = self.ensure_fields()
        fields = daily_promotion_fields(self.platform, result)
        unique_key = fields[F_UNIQUE_KEY]
        record_id, _ = self.find_record(unique_key)
        action = "updated" if record_id else "created"
        payload = {"fields": clean_fields(fields)}
        if record_id:
            self.request("PUT", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}", payload)
        else:
            data = self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records", payload)
            record_id = str((data.get("record") or {}).get("record_id") or "")
        _, readback = self.find_record(unique_key)
        if not readback:
            raise PromotionApiError("Feishu readback did not find the written daily promotion record")
        return {
            "action": action,
            "created_fields": created_fields,
            "record_id": record_id,
            "written_fields": fields,
            "readback_fields": readback,
        }


def daily_unique_key(platform: str, query_date: str) -> str:
    return f"{platform}{query_date}"


def daily_promotion_fields(platform: str, result: PromotionApiResult) -> dict[str, Any]:
    return {
        F_UNIQUE_KEY: daily_unique_key(platform, result.query_date),
        F_PLATFORM: platform,
        F_STAT_DATE: result.query_date,
        F_FETCHED_AT: dt(result.fetched_at),
        F_SOURCE: "千牛推广中心Cookie API",
        F_ACTUAL_COST: result.cost,
        F_COST: result.cost,
        F_IMPRESSIONS: result.api_fields.get("adPv"),
        F_CLICKS: result.api_fields.get("click"),
        F_ROI: result.api_fields.get("roi"),
        F_GMV: result.api_fields.get("alipayInshopAmt"),
        F_RAW: json.dumps({"api_url": API_URL, "api_fields": result.api_fields, "raw_status": result.raw_status}, ensure_ascii=False, sort_keys=True),
    }


def clean_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in (None, "")}


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    return str(value).strip()


def run_cycle(
    evidence_dir: Path,
    cycle: int,
    query_date: str | None = None,
    table_id: str | None = None,
    platform: str = "天猫",
    daily_unique: bool = False,
) -> dict[str, Any]:
    result = fetch_promotion_from_cookie(query_date)
    writer = DailyPromotionFeishuWriter(table_id=table_id, platform=platform) if daily_unique else PromotionFeishuWriter()
    feishu = writer.upsert_and_readback(result)
    readback_cost = feishu["readback_fields"].get(F_COST) if daily_unique else feishu["readback_fields"].get("花费")
    matched = round(float(readback_cost), 2) == result.cost if readback_cost is not None else False
    comparison = {
        "cycle": cycle,
        "captured_at": dt(result.fetched_at),
        "query_date": result.query_date,
        "platform": platform if daily_unique else None,
        "api_cost": result.cost,
        "api_fields": result.api_fields,
        "feishu_action": feishu.get("action"),
        "created_fields": feishu.get("created_fields", []),
        "feishu_record_id": feishu["record_id"],
        "feishu_unique_key": feishu["written_fields"]["unique_key"],
        "feishu_cost": readback_cost,
        "matched": matched,
        "raw_status": result.raw_status,
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"promotion-api-feishu-cycle-{cycle}.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not matched:
        raise PromotionApiError(f"Feishu readback mismatch: API 花费={result.cost}, 飞书 花费={readback_cost}")
    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Qianniu promotion API cost and write it to Feishu Bitable.")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval-seconds", type=int, default=600)
    parser.add_argument("--query-date", default=None)
    parser.add_argument("--evidence-dir", default="docs/live-evidence/promotion-api-feishu")
    parser.add_argument("--target-table", default=None)
    parser.add_argument("--platform", default="天猫")
    parser.add_argument(
        "--daily-unique",
        action="store_true",
        help="Write one detail row per platform/date using unique_key=平台+日期, updating today's row on repeated runs.",
    )
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    results: list[dict[str, Any]] = []
    for cycle in range(1, args.cycles + 1):
        comparison = run_cycle(
            evidence_dir,
            cycle,
            args.query_date,
            table_id=args.target_table,
            platform=args.platform,
            daily_unique=args.daily_unique,
        )
        results.append(comparison)
        print(json.dumps(comparison, ensure_ascii=False))
        if cycle < args.cycles:
            time.sleep(args.interval_seconds)
    (evidence_dir / "latest-run.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
