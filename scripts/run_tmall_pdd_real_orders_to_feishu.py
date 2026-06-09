from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_jushuitan_orders_to_feishu import FeishuOrderWriter, feishu_order_fields
from shopops.collectors.jushuitan_order_api import (
    JushuitanOrderApiCollector,
    extract_jushuitan_orders,
    jushuitan_public_params,
)
from shopops.collectors.jushuitan_qimen_order_api import JushuitanQimenOrderListCollector
from shopops.config import Settings, load_settings
from shopops.services.data_center_demo import (
    F_AD_COST,
    F_BACKEND_ROI,
    F_DIFF,
    F_PLATFORM,
    F_STAT_DATE,
    F_TODAY_COST,
    F_TODAY_GMV,
    F_TODAY_ORDERS,
    F_TRUE_ROI,
    F_UNIQUE_KEY,
    FeishuDataCenterClient,
    demo_ad_rows,
)


PLATFORM_TMALL = "\u5929\u732b"
PLATFORM_PDD = "\u62fc\u591a\u591a"


def required_common_missing(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.feishu_app_id:
        missing.append("FEISHU_APP_ID")
    if not settings.feishu_app_secret:
        missing.append("FEISHU_APP_SECRET")
    if not settings.shopops_data_center_app_token:
        missing.append("SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN")
    if not settings.shopops_order_table_id:
        missing.append("SHOPOPS_ORDER_TABLE_ID")
    if not os.getenv("JUSHUITAN_SHOP_ID_TMALL", "").strip():
        missing.append("JUSHUITAN_SHOP_ID_TMALL")
    if not os.getenv("JUSHUITAN_SHOP_ID_PINDUODUO", "").strip():
        missing.append("JUSHUITAN_SHOP_ID_PINDUODUO")
    return missing


def qimen_missing(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.jushuitan_qimen_app_key:
        missing.append("JUSHUITAN_QIMEN_APP_KEY")
    if not settings.jushuitan_qimen_app_secret:
        missing.append("JUSHUITAN_QIMEN_APP_SECRET")
    if not settings.jushuitan_qimen_customer_id:
        missing.append("JUSHUITAN_QIMEN_CUSTOMER_ID")
    return missing


def openapi_missing(settings: Settings) -> list[str]:
    missing: list[str] = []
    if not settings.jushuitan_partner_id:
        missing.append("JUSHUITAN_PARTNER_ID")
    if not settings.jushuitan_partner_key:
        missing.append("JUSHUITAN_PARTNER_KEY")
    if not settings.jushuitan_token:
        missing.append("JUSHUITAN_TOKEN")
    return missing


def tmall_settings(settings: Settings) -> Settings:
    shop_id = os.getenv("JUSHUITAN_SHOP_ID_TMALL", "").strip()
    return replace(
        settings,
        order_source="jushuitan",
        use_mock_collectors=False,
        shop_platform="taobao",
        shop_id=shop_id,
        shop_name=PLATFORM_TMALL,
        jushuitan_shop_ids=shop_id,
    )


def pdd_settings(settings: Settings, method: str) -> Settings:
    shop_id = os.getenv("JUSHUITAN_SHOP_ID_PINDUODUO", "").strip()
    return replace(
        settings,
        order_source="jushuitan",
        use_mock_collectors=False,
        shop_platform="pinduoduo",
        shop_id=shop_id,
        shop_name=PLATFORM_PDD,
        jushuitan_shop_ids=shop_id,
        jushuitan_order_query_method=method,
    )


def fetch_tmall_qimen(settings: Settings) -> dict[str, Any]:
    missing = qimen_missing(settings)
    if missing:
        return {"success": False, "platform": PLATFORM_TMALL, "blocked_by": "missing_qimen_inputs", "missing": missing}
    platform_settings = tmall_settings(settings)
    result = JushuitanQimenOrderListCollector(platform_settings).fetch_today()
    return {
        "success": result.success,
        "platform": PLATFORM_TMALL,
        "shop_id": platform_settings.shop_id,
        "order_count": result.order_count,
        "total_amount": result.total_amount,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "orders": result.orders,
    }


def fetch_pdd_openapi(settings: Settings) -> dict[str, Any]:
    missing = openapi_missing(settings)
    if missing:
        return {"success": False, "platform": PLATFORM_PDD, "blocked_by": "missing_openapi_inputs", "missing": missing}
    attempts: list[dict[str, Any]] = []
    qimen_style = fetch_pdd_order_list_openapi(settings, days=30)
    attempts.append({key: value for key, value in qimen_style.items() if key != "orders"})
    if qimen_style.get("success") and qimen_style.get("orders"):
        return {
            "success": True,
            "platform": PLATFORM_PDD,
            "shop_id": os.getenv("JUSHUITAN_SHOP_ID_PINDUODUO", "").strip(),
            "method": "jushuitan.order.list.query",
            "order_count": qimen_style.get("order_count"),
            "total_amount": qimen_style.get("total_amount"),
            "orders": qimen_style["orders"],
            "attempts": attempts,
        }

    for method in ("orders.single.query", "orders.out.simple.query"):
        platform_settings = pdd_settings(settings, method)
        result = JushuitanOrderApiCollector(platform_settings).fetch_today()
        attempts.append(
            {
                "method": method,
                "success": result.success,
                "order_count": result.order_count,
                "total_amount": result.total_amount,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "orders": result.orders,
            }
        )
        if result.success and result.orders:
            return {
                "success": True,
                "platform": PLATFORM_PDD,
                "shop_id": platform_settings.shop_id,
                "method": method,
                "order_count": result.order_count,
                "total_amount": result.total_amount,
                "orders": result.orders,
                "attempts": strip_orders(attempts),
            }
    return {
        "success": False,
        "platform": PLATFORM_PDD,
        "shop_id": os.getenv("JUSHUITAN_SHOP_ID_PINDUODUO", "").strip(),
        "blocked_by": "no_pdd_orders_from_available_jushuitan_methods",
        "message": (
            "Current Jushuitan OpenAPI credentials returned no Pinduoduo order records from available tested methods; "
            "do not treat this as true zero GMV without platform-side confirmation."
        ),
        "attempts": strip_orders(attempts),
    }


def fetch_pdd_order_list_openapi(settings: Settings, days: int = 30) -> dict[str, Any]:
    method = "jushuitan.order.list.query"
    platform_settings = pdd_settings(settings, method)
    fetched_at = datetime.now()
    windows = date_windows(fetched_at, days, max_days=7)
    all_orders: list[dict[str, Any]] = []
    window_results: list[dict[str, Any]] = []
    try:
        for start_at, end_at in windows:
            body = {
                "page_index": 1,
                "page_size": settings.jushuitan_page_size,
                "shop_id": int(platform_settings.shop_id),
                "date_type": 1,
                "start_time": start_at.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time": end_at.strftime("%Y-%m-%d %H:%M:%S"),
                "is_paid": True,
                "is_get_total": True,
                "archive": False,
            }
            params = jushuitan_public_params(
                settings.jushuitan_partner_id,
                settings.jushuitan_partner_key,
                settings.jushuitan_token,
                method,
                int(fetched_at.timestamp()),
            )
            response = requests.post(settings.jushuitan_api_url, params=params, json=body, timeout=30)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Jushuitan response is not a JSON object")
            window_result = {
                "start_time": body["start_time"],
                "end_time": body["end_time"],
                "code": payload.get("code"),
                "success": payload.get("code") in (None, 0, "0"),
                "message": payload.get("msg") or payload.get("message"),
                "data_count": payload.get("data_count"),
            }
            window_results.append(window_result)
            if payload.get("code") not in (None, 0, "0"):
                continue
            all_orders.extend(extract_jushuitan_orders(payload))
        normalized = [normalize_pdd_order(order, platform_settings, fetched_at) for order in all_orders]
        return {
            "method": method,
            "success": True,
            "window_days": days,
            "windows": window_results,
            "order_count": len(normalized),
            "total_amount": round(sum(float(order.get("paid_amount") or 0) for order in normalized), 2),
            "orders": normalized,
        }
    except Exception as exc:
        return {
            "method": method,
            "success": False,
            "window_days": days,
            "windows": window_results,
            "order_count": None,
            "total_amount": None,
            "error_code": "jushuitan_pdd_order_list_failed",
            "error_message": str(exc),
        }


def date_windows(end_at: datetime, days: int, max_days: int) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor_end = end_at
    remaining = days
    while remaining > 0:
        span = min(max_days, remaining)
        cursor_start = cursor_end - timedelta(days=span)
        windows.append((cursor_start, cursor_end))
        cursor_end = cursor_start
        remaining -= span
    return windows


def normalize_pdd_order(order: dict[str, Any], settings: Settings, fetched_at: datetime) -> dict[str, Any]:
    order_id = str(order.get("o_id") or order.get("so_id") or order.get("outer_so_id") or "unknown")
    return {
        "unique_key": f"jushuitan_pdd_order_list_{order.get('shop_id') or settings.shop_id}_{order_id}",
        "platform": "pinduoduo",
        "provider": "jushuitan",
        "shop_id": str(order.get("shop_id") or settings.shop_id),
        "shop_name": str(order.get("shop_name") or PLATFORM_PDD),
        "order_id": order_id,
        "order_status": order.get("shop_status") or order.get("status"),
        "created_at": order.get("order_date") or order.get("created"),
        "paid_at": order.get("pay_date"),
        "paid_amount": float(order.get("pay_amount") or order.get("paid_amount") or 0),
        "fetched_at": fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
        "raw": order,
    }


def strip_orders(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in attempt.items() if key != "orders"} for attempt in attempts]


def write_successful_orders(settings: Settings, results: list[dict[str, Any]]) -> int:
    rows: list[dict[str, Any]] = []
    for item in results:
        if not item.get("success"):
            continue
        platform = str(item["platform"])
        rows.extend(feishu_order_fields(platform, order) for order in item.get("orders", []))
    if not rows:
        return 0
    writer = FeishuOrderWriter(settings)
    writer.ensure_fields()
    return writer.write_orders(rows)


def write_successful_summary(settings: Settings, results: list[dict[str, Any]], now: datetime | None = None) -> int:
    now = now or datetime.now()
    ad_by_platform = {row[F_PLATFORM]: row for row in demo_ad_rows(now)}
    rows: list[dict[str, Any]] = []
    for item in results:
        if not item.get("success"):
            continue
        platform = str(item["platform"])
        order_count = int(item.get("order_count") or 0)
        total_amount = float(item.get("total_amount") or 0)
        ad = ad_by_platform.get(platform, {})
        cost = float(ad.get(F_AD_COST) or 0)
        backend_roi = ad.get(F_BACKEND_ROI)
        true_roi = round(total_amount / cost, 4) if cost else None
        row: dict[str, Any] = {
            F_UNIQUE_KEY: f"summary_{now.date().isoformat()}_{platform}",
            F_PLATFORM: platform,
            F_TODAY_GMV: round(total_amount, 2),
            F_TODAY_ORDERS: order_count,
            F_STAT_DATE: now.date().isoformat(),
        }
        if cost:
            row[F_TODAY_COST] = round(cost, 2)
        if true_roi is not None:
            row[F_TRUE_ROI] = true_roi
        if backend_roi is not None:
            row[F_BACKEND_ROI] = backend_roi
        if true_roi is not None and backend_roi is not None:
            row[F_DIFF] = round(true_roi - float(backend_roi), 4)
        rows.append(row)
    if not rows:
        return 0
    client = FeishuDataCenterClient(settings)
    result = client.write_dataset({"summary_dashboard": rows})
    return result.saved_count


def main() -> int:
    settings = load_settings()
    missing = required_common_missing(settings)
    if missing:
        print(json.dumps({"status": "missing_inputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    results = [fetch_tmall_qimen(settings), fetch_pdd_openapi(settings)]
    saved_count = write_successful_orders(settings, results)
    summary_saved_count = write_successful_summary(settings, results)
    blocked = [item for item in results if not item.get("success")]
    print(
        json.dumps(
            {
                "status": "partial_success" if blocked else "success",
                "saved_count": saved_count,
                "summary_saved_count": summary_saved_count,
                "platforms": [{key: value for key, value in item.items() if key != "orders"} for item in results],
                "feishu_base_url": f"https://feishu.cn/base/{settings.shopops_data_center_app_token}",
                "order_table_id": settings.shopops_order_table_id,
                "summary_table_id": settings.shopops_summary_table_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 3 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
