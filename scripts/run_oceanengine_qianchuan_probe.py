from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shopops.collectors.qianchuan_report_api import QianchuanReportClient, pick_access_token, pick_advertiser_id
from shopops.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe OceanEngine/Qianchuan OAuth and report APIs.")
    parser.add_argument("--date", default="", help="Report date in YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument("--start-date", default="", help="Report start date in YYYY-MM-DD.")
    parser.add_argument("--end-date", default="", help="Report end date in YYYY-MM-DD.")
    parser.add_argument("--advertiser-id", default="", help="Override QIANCHUAN_ADVERTISER_ID.")
    parser.add_argument("--access-token", default="", help="Override QIANCHUAN_ACCESS_TOKEN.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    args = parser.parse_args()

    settings = load_settings()
    client = QianchuanReportClient(settings)
    start_date, end_date = _date_range(args.date, args.start_date, args.end_date)

    calls = []
    access_token = args.access_token or settings.qianchuan_access_token

    if not access_token and settings.qianchuan_auth_code:
        auth_call = client.exchange_auth_code(settings.qianchuan_auth_code)
        calls.append(auth_call)
        access_token = pick_access_token(auth_call) or ""

    if not access_token and settings.qianchuan_refresh_token:
        refresh_call = client.refresh_access_token(settings.qianchuan_refresh_token)
        calls.append(refresh_call)
        access_token = pick_access_token(refresh_call) or ""

    if not access_token:
        calls.append(client.probe_client_credentials_token())
        access_token = pick_access_token(calls[-1]) or ""

    advertisers_call = client.get_authorized_advertisers(access_token)
    calls.append(advertisers_call)

    advertiser_id = args.advertiser_id or settings.qianchuan_advertiser_id or pick_advertiser_id(advertisers_call) or ""
    calls.append(client.get_advertiser_report(advertiser_id, start_date, end_date, access_token))
    calls.append(client.get_ad_report(advertiser_id, start_date, end_date, access_token))

    payload = {
        "mode": "oceanengine_qianchuan",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "has_access_token": bool(access_token),
        "advertiser_id": advertiser_id or None,
        "calls": [_call_dict(call) for call in calls],
    }

    output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    print(output)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output + "\n", encoding="utf-8")


def _date_range(single: str, start: str, end: str) -> tuple[date, date]:
    if start or end:
        start_date = date.fromisoformat(start or end)
        end_date = date.fromisoformat(end or start)
        return start_date, end_date
    if single:
        value = date.fromisoformat(single)
        return value, value
    yesterday = date.today() - timedelta(days=1)
    return yesterday, yesterday


def _call_dict(call: Any) -> dict[str, Any]:
    payload = call if isinstance(call, dict) else asdict(call)
    return _redact_sensitive(payload)


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"access_token", "refresh_token", "secret", "app_secret", "auth_code"} and item:
                redacted[key] = _mask(str(item))
            else:
                redacted[key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


if __name__ == "__main__":
    main()
