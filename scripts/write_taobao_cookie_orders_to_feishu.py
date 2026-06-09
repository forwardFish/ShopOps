from __future__ import annotations

import argparse
import ast
import json
import os
import random
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_jushuitan_orders_to_feishu import (
    F_BUYER_NICK,
    F_CREATED_AT,
    F_DATA_SOURCE,
    F_FETCHED_AT,
    F_FULFILL_STATUS,
    F_OPERATION,
    F_ORDER_NO,
    F_PAID_AMOUNT,
    F_PLATFORM,
    F_PRODUCT,
    F_QUANTITY,
    F_RAW,
    F_SHOP_ID,
    F_SHOP_NAME,
    F_TRADE_STATUS,
    F_UNIQUE_KEY,
    F_UNIT_PRICE,
    FeishuOrderWriter,
    redact_sensitive,
)
from shopops.config import load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy


API_URL = "https://trade.taobao.com/trade/itemlist/asyncSold.htm"
TEXT_FIELD = 1
NO_PROXY_HOSTS = ["trade.taobao.com", "qn.taobao.com", ".taobao.com", ".tmall.com"]

FIELD_PAGE_URL = "\u9875\u9762URL"
FIELD_PAGE_SCREENSHOT = "\u9875\u9762\u622a\u56fe"
FIELD_SHIP_DEADLINE = "\u53d1\u8d27\u622a\u6b62\u65f6\u95f4"
FIELD_SHIP_COUNTDOWN = "\u53d1\u8d27\u5012\u8ba1\u65f6"
FIELD_IMAGE_DESC = "\u5546\u54c1\u56fe\u7247\u8bf4\u660e"

DATA_SOURCE = "\u5343\u725b\u8ba2\u5355\u63a5\u53e3(cookie)"
PLATFORM = "\u5929\u732b"
MERCHANT_CODE = "\u5546\u5bb6\u7f16\u7801"


def ensure_taobao_no_proxy() -> None:
    for name in ("NO_PROXY", "no_proxy"):
        current = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
        for host in NO_PROXY_HOSTS:
            if host not in current:
                current.append(host)
        os.environ[name] = ",".join(current)


def parse_snippet(path: Path) -> dict[str, Any]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    values: dict[str, Any] = {}
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name in {"cookies", "headers", "params", "data"}:
            values[name] = ast.literal_eval(node.value)
    missing = sorted({"cookies", "headers", "params", "data"} - set(values))
    if missing:
        raise RuntimeError(f"source file is missing required literals: {', '.join(missing)}")
    return values


def fetch_page_from_values(values: dict[str, Any], page_num: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = deepcopy(values["data"])
    data["pageNum"] = str(page_num)
    data["prePageNo"] = str(page_num)
    ensure_taobao_no_proxy()
    last_exc: Exception | None = None
    response: requests.Response | None = None
    for attempt in range(1, 4):
        try:
            response = requests.post(
                API_URL,
                params=values["params"],
                cookies=values["cookies"],
                headers=values["headers"],
                data=data,
                timeout=30,
            )
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= 3:
                raise
            time.sleep(random.uniform(20 * attempt, 45 * attempt))
    if response is None:
        raise RuntimeError(f"page {page_num} request failed") from last_exc
    response.raise_for_status()
    body = response.json()
    orders = body.get("mainOrders") or []
    if not orders:
        raise RuntimeError(f"Taobao order API returned no mainOrders for page {page_num}")
    return body, orders


def fetch_page(source_file: Path, page_num: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return fetch_page_from_values(parse_snippet(source_file), page_num)


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return round(float(value), 2)


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def join_text(values: list[str]) -> str:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return "; ".join(seen)


def detail_url(order: dict[str, Any]) -> str:
    for op in (order.get("statusInfo") or {}).get("operations") or []:
        params = op.get("params") or {}
        url = params.get("qianNiuPCDetailUrl") or params.get("solutionPCDetailUrl") or op.get("url")
        if not url:
            continue
        text = str(url)
        if text.startswith("//"):
            return "https:" + text
        if text.startswith("/"):
            return "https://trade.taobao.com" + text
        return text
    return ""


def order_to_row(order: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
    settings = load_settings()
    order_id = str(order.get("id") or (order.get("orderInfo") or {}).get("id") or "")
    order_info = order.get("orderInfo") or {}
    buyer = order.get("buyer") or {}
    pay = order.get("payInfo") or {}
    status = order.get("statusInfo") or {}
    sub_orders = order.get("subOrders") or []

    product_names: list[str] = []
    quantities: list[int] = []
    unit_prices: list[float] = []
    fulfill_statuses: list[str] = []
    item_pics: list[str] = []
    merchant_codes: list[str] = []
    for sub in sub_orders:
        item = sub.get("itemInfo") or {}
        if item.get("title"):
            product_names.append(str(item.get("title")))
        if item.get("pic"):
            pic = str(item.get("pic"))
            item_pics.append("https:" + pic if pic.startswith("//") else pic)
        quantity = as_int(sub.get("quantity"))
        if quantity is not None:
            quantities.append(quantity)
        price = as_float((sub.get("priceInfo") or {}).get("realTotal"))
        if price is not None:
            unit_prices.append(price)
        for op in sub.get("operations") or []:
            if op.get("text"):
                fulfill_statuses.append(str(op.get("text")))
        for extra in item.get("extra") or []:
            if extra.get("name") == MERCHANT_CODE and extra.get("value"):
                merchant_codes.append(str(extra.get("value")))

    op_texts: list[str] = []
    for op in order.get("operations") or []:
        if op.get("text"):
            op_texts.append(str(op.get("text")))
    for op in status.get("operations") or []:
        if op.get("text"):
            op_texts.append(str(op.get("text")))
    for op in pay.get("operations") or []:
        if op.get("text"):
            op_texts.append(str(op.get("text")))
    if merchant_codes:
        op_texts.append(MERCHANT_CODE + ": " + ",".join(sorted(set(merchant_codes))))
    if pay.get("postType"):
        op_texts.append(str(pay.get("postType")))

    row = {
        F_UNIQUE_KEY: f"taobao_{settings.shop_id}_{order_id}",
        F_PLATFORM: PLATFORM,
        F_DATA_SOURCE: DATA_SOURCE,
        F_SHOP_ID: settings.shop_id,
        F_SHOP_NAME: settings.shop_name,
        F_FETCHED_AT: fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
        F_ORDER_NO: order_id,
        F_CREATED_AT: str(order_info.get("createTime") or ""),
        F_BUYER_NICK: str(buyer.get("nick") or buyer.get("encodeNick") or ""),
        F_PRODUCT: join_text(product_names),
        F_UNIT_PRICE: unit_prices[0] if unit_prices else None,
        F_QUANTITY: sum(quantities) if quantities else None,
        F_FULFILL_STATUS: join_text(fulfill_statuses),
        F_TRADE_STATUS: str(status.get("text") or ""),
        F_PAID_AMOUNT: as_float(pay.get("actualFee")),
        F_OPERATION: join_text(op_texts),
        FIELD_PAGE_URL: detail_url(order),
        FIELD_PAGE_SCREENSHOT: "",
        FIELD_SHIP_DEADLINE: "",
        FIELD_SHIP_COUNTDOWN: join_text(fulfill_statuses),
        FIELD_IMAGE_DESC: join_text(item_pics),
        F_RAW: json.dumps(redact_sensitive(order), ensure_ascii=False, sort_keys=True),
    }
    return {key: value for key, value in row.items() if value is not None}


def ensure_extra_fields(writer: FeishuOrderWriter) -> None:
    existing = writer._field_names()
    for field_name in [FIELD_PAGE_URL, FIELD_PAGE_SCREENSHOT, FIELD_SHIP_DEADLINE, FIELD_SHIP_COUNTDOWN, FIELD_IMAGE_DESC]:
        if field_name in existing:
            continue
        writer._request(
            "POST",
            f"/bitable/v1/apps/{writer.app_token}/tables/{writer.table_id}/fields",
            {"field_name": field_name, "type": TEXT_FIELD},
        )
        existing.add(field_name)


def write_rows_to_feishu(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_feishu_no_proxy()
    settings = load_settings()
    writer = FeishuOrderWriter(settings)
    writer.ensure_fields()
    ensure_extra_fields(writer)
    before = writer._existing_record_ids()
    created_count = sum(1 for row in rows if str(row[F_UNIQUE_KEY]) not in before)
    saved_count = writer.write_orders(rows)
    after = writer._existing_record_ids()
    missing = [row[F_UNIQUE_KEY] for row in rows if str(row[F_UNIQUE_KEY]) not in after]

    return {
        "status": "success" if saved_count == len(rows) and not missing else "partial",
        "saved_count": saved_count,
        "created_count": created_count,
        "updated_count": len(rows) - created_count,
        "readback_count": len(rows) - len(missing),
        "missing_after_readback": missing,
        "feishu_base_url": "https://my.feishu.cn/base/" + (settings.shopops_data_center_app_token or settings.feishu_app_token),
        "order_table_id": settings.shopops_order_table_id,
        "field_extras_used": [
            F_PLATFORM,
            F_DATA_SOURCE,
            F_SHOP_ID,
            F_SHOP_NAME,
            F_FETCHED_AT,
            FIELD_PAGE_URL,
            F_RAW,
            FIELD_SHIP_COUNTDOWN,
            FIELD_IMAGE_DESC,
        ],
        "rows": [
            {
                "order_no": row[F_ORDER_NO],
                "created_at": row[F_CREATED_AT],
                "buyer_nick": row[F_BUYER_NICK],
                "trade_status": row[F_TRADE_STATUS],
                "fulfill_status": row.get(F_FULFILL_STATUS, ""),
                "paid_amount": row[F_PAID_AMOUNT],
                "unit_price": row.get(F_UNIT_PRICE),
                "quantity": row.get(F_QUANTITY),
                "data_source": row[F_DATA_SOURCE],
                "unique_key": row[F_UNIQUE_KEY],
            }
            for row in rows
        ],
    }


def write_single_page(source_file: Path, page_num: int) -> dict[str, Any]:
    fetched_at = datetime.now()
    body, orders = fetch_page(source_file, page_num)
    rows = [order_to_row(order, fetched_at) for order in orders]
    result = write_rows_to_feishu(rows)
    result["page"] = body.get("page")
    result["fetched_count"] = len(rows)
    return result


def read_seen_pages(output_file: Path) -> set[int]:
    if not output_file.exists():
        return set()
    seen: set[int] = set()
    with output_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            if "page_num" in item:
                seen.add(int(item["page_num"]))
    return seen


def read_seen_order_ids(output_file: Path) -> set[str]:
    if not output_file.exists():
        return set()
    seen: set[str] = set()
    with output_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            for order in item.get("orders") or []:
                order_id = str(order.get("id") or (order.get("orderInfo") or {}).get("id") or "")
                if order_id:
                    seen.add(order_id)
    return seen


def crawl_to_local(
    source_file: Path,
    output_file: Path,
    start_page: int,
    end_page: int | None,
    delay_min: float,
    delay_max: float,
    max_empty_pages: int,
    skip_seen_pages: bool = True,
    pass_name: str = "main",
) -> dict[str, Any]:
    values = parse_snippet(source_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    seen_pages = read_seen_pages(output_file)
    seen_order_ids = read_seen_order_ids(output_file)
    fetched_pages = 0
    fetched_orders = 0
    new_orders_total = 0
    skipped_pages = 0
    empty_pages = 0
    first_page_meta: dict[str, Any] | None = None
    current_page = start_page
    final_page = end_page

    while True:
        if final_page is not None and current_page > final_page:
            break
        if skip_seen_pages and current_page in seen_pages:
            skipped_pages += 1
            current_page += 1
            continue

        fetched_at = datetime.now()
        try:
            body, orders = fetch_page_from_values(values, current_page)
        except Exception as exc:
            raise RuntimeError(f"page {current_page} failed; checkpoint is preserved at {output_file}: {exc}") from exc

        page_meta = body.get("page") or {}
        if first_page_meta is None:
            first_page_meta = page_meta
            if final_page is None:
                total_page = page_meta.get("totalPage")
                final_page = int(total_page) if total_page else current_page

        new_orders: list[dict[str, Any]] = []
        duplicate_orders = 0
        for order in orders:
            order_id = str(order.get("id") or (order.get("orderInfo") or {}).get("id") or "")
            if order_id and order_id in seen_order_ids:
                duplicate_orders += 1
                continue
            if order_id:
                seen_order_ids.add(order_id)
            new_orders.append(order)

        with output_file.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "pass": pass_name,
                        "page_num": current_page,
                        "fetched_at": fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                        "page": page_meta,
                        "order_count": len(orders),
                        "new_order_count": len(new_orders),
                        "duplicate_order_count": duplicate_orders,
                        "orders": new_orders,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )

        fetched_pages += 1
        fetched_orders += len(orders)
        new_orders_total += len(new_orders)
        empty_pages = empty_pages + 1 if not orders else 0
        print(
            json.dumps(
                {
                    "event": "page_saved",
                    "pass": pass_name,
                    "page_num": current_page,
                    "orders": len(orders),
                    "new_orders": len(new_orders),
                    "duplicates": duplicate_orders,
                    "final_page": final_page,
                    "output_file": str(output_file),
                    "time": fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if empty_pages >= max_empty_pages:
            break
        if final_page is not None and current_page >= final_page:
            break
        current_page += 1
        time.sleep(random.uniform(delay_min, delay_max))

    return {
        "status": "success",
        "output_file": str(output_file),
        "start_page": start_page,
        "end_page": final_page,
        "skipped_pages": skipped_pages,
        "fetched_pages": fetched_pages,
        "fetched_orders": fetched_orders,
        "new_orders": new_orders_total,
        "page": first_page_meta,
    }


def stabilize_head_pages(
    source_file: Path,
    output_file: Path,
    pages: int,
    rounds: int,
    delay_min: float,
    delay_max: float,
) -> dict[str, Any]:
    total_new = 0
    round_results: list[dict[str, Any]] = []
    for round_index in range(1, rounds + 1):
        result = crawl_to_local(
            source_file,
            output_file,
            1,
            pages,
            delay_min,
            delay_max,
            1,
            skip_seen_pages=False,
            pass_name=f"stabilize-{round_index}",
        )
        round_results.append(result)
        total_new += int(result["new_orders"])
        if int(result["new_orders"]) == 0:
            break
        time.sleep(random.uniform(delay_min, delay_max))
    return {"status": "success", "rounds": len(round_results), "new_orders": total_new, "round_results": round_results}


def load_rows_from_local(input_file: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    with input_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            fetched_at = datetime.strptime(item["fetched_at"], "%Y-%m-%d %H:%M:%S")
            for order in item.get("orders") or []:
                row = order_to_row(order, fetched_at)
                unique_key = str(row[F_UNIQUE_KEY])
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)
                rows.append(row)
    return rows


def local_summary(input_file: Path) -> dict[str, Any]:
    pages = 0
    raw_orders = 0
    order_ids: set[str] = set()
    with input_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            pages += 1
            orders = item.get("orders") or []
            raw_orders += len(orders)
            for order in orders:
                order_id = str(order.get("id") or (order.get("orderInfo") or {}).get("id") or "")
                if order_id:
                    order_ids.add(order_id)
    return {"pages": pages, "raw_orders": raw_orders, "unique_orders": len(order_ids)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Taobao/Qianniu cookie order API rows to the existing ShopOps Feishu order table.")
    subparsers = parser.add_subparsers(dest="command")

    single = subparsers.add_parser("single-page", help="Fetch one page and write it to Feishu.")
    single.add_argument("--source-file", required=True, help="Python snippet containing cookies, headers, params, and data literals.")
    single.add_argument("--page-num", type=int, default=1)

    crawl = subparsers.add_parser("crawl", help="Fetch pages slowly and save raw API responses to a local JSONL checkpoint.")
    crawl.add_argument("--source-file", required=True)
    crawl.add_argument("--output-file", required=True)
    crawl.add_argument("--start-page", type=int, default=1)
    crawl.add_argument("--end-page", type=int, default=None)
    crawl.add_argument("--delay-min", type=float, default=4.0)
    crawl.add_argument("--delay-max", type=float, default=9.0)
    crawl.add_argument("--max-empty-pages", type=int, default=1)
    crawl.add_argument("--pass-name", default="main")
    crawl.add_argument("--no-skip-seen-pages", action="store_true")

    stabilize = subparsers.add_parser("stabilize", help="Re-crawl head pages without page skipping until no new order IDs appear.")
    stabilize.add_argument("--source-file", required=True)
    stabilize.add_argument("--output-file", required=True)
    stabilize.add_argument("--pages", type=int, default=10)
    stabilize.add_argument("--rounds", type=int, default=3)
    stabilize.add_argument("--delay-min", type=float, default=4.0)
    stabilize.add_argument("--delay-max", type=float, default=9.0)

    upload = subparsers.add_parser("upload", help="Load local JSONL checkpoint rows and upsert them to Feishu.")
    upload.add_argument("--input-file", required=True)

    run_all = subparsers.add_parser("run-all", help="Crawl locally, stabilize head pages, then upload deduplicated rows to Feishu.")
    run_all.add_argument("--source-file", required=True)
    run_all.add_argument("--output-file", required=True)
    run_all.add_argument("--start-page", type=int, default=1)
    run_all.add_argument("--end-page", type=int, default=None)
    run_all.add_argument("--delay-min", type=float, default=5.0)
    run_all.add_argument("--delay-max", type=float, default=9.0)
    run_all.add_argument("--stabilize-pages", type=int, default=10)
    run_all.add_argument("--stabilize-rounds", type=int, default=3)

    args = parser.parse_args()
    if args.command in (None, "single-page"):
        source_file = Path(args.source_file) if args.command else Path(getattr(args, "source_file", ""))
        page_num = int(getattr(args, "page_num", 1))
        result = write_single_page(source_file, page_num)
    elif args.command == "crawl":
        result = crawl_to_local(
            Path(args.source_file),
            Path(args.output_file),
            args.start_page,
            args.end_page,
            args.delay_min,
            args.delay_max,
            args.max_empty_pages,
            skip_seen_pages=not args.no_skip_seen_pages,
            pass_name=args.pass_name,
        )
    elif args.command == "stabilize":
        result = stabilize_head_pages(
            Path(args.source_file),
            Path(args.output_file),
            args.pages,
            args.rounds,
            args.delay_min,
            args.delay_max,
        )
    elif args.command == "upload":
        input_file = Path(args.input_file)
        rows = load_rows_from_local(input_file)
        result = write_rows_to_feishu(rows)
        result["local_summary"] = local_summary(input_file)
        result["fetched_count"] = len(rows)
    elif args.command == "run-all":
        output_file = Path(args.output_file)
        crawl_result = crawl_to_local(
            Path(args.source_file),
            output_file,
            args.start_page,
            args.end_page,
            args.delay_min,
            args.delay_max,
            1,
            skip_seen_pages=True,
            pass_name="main",
        )
        stabilize_result = stabilize_head_pages(
            Path(args.source_file),
            output_file,
            args.stabilize_pages,
            args.stabilize_rounds,
            args.delay_min,
            args.delay_max,
        )
        rows = load_rows_from_local(output_file)
        upload_result = write_rows_to_feishu(rows)
        result = {
            "status": upload_result["status"],
            "crawl": crawl_result,
            "stabilize": stabilize_result,
            "upload": upload_result,
            "local_summary": local_summary(output_file),
        }
    else:
        parser.error("unknown command")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
