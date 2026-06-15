from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from data_robot.common import print_json
from data_robot.daily_download import PLATFORM_PORTS, cdp_base_url


@dataclass(frozen=True)
class CdpEndpoint:
    platform: str
    port: int

    @property
    def base_url(self) -> str:
        return cdp_base_url(self.platform)


def fetch_json(url: str, *, timeout_seconds: float = 2.0) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def check_endpoint(endpoint: CdpEndpoint) -> dict[str, Any]:
    try:
        version = fetch_json(f"{endpoint.base_url}/json/version")
        pages = fetch_json(f"{endpoint.base_url}/json/list")
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "platform": endpoint.platform,
            "port": endpoint.port,
            "status": "offline",
            "error": str(exc),
            "pages": [],
        }

    visible_pages = [
        {
            "title": page.get("title", ""),
            "url": page.get("url", ""),
            "type": page.get("type", ""),
        }
        for page in pages
        if page.get("type") == "page"
    ]
    return {
        "platform": endpoint.platform,
        "port": endpoint.port,
        "status": "online",
        "browser": version.get("Browser", ""),
        "pages": visible_pages,
    }


def check_platforms(platforms: list[str] | None = None) -> dict[str, Any]:
    selected = platforms or list(PLATFORM_PORTS)
    checks = [check_endpoint(CdpEndpoint(platform, PLATFORM_PORTS[platform])) for platform in selected]
    offline = [item["platform"] for item in checks if item["status"] != "online"]
    return {
        "status": "ready" if not offline else "not_ready",
        "offline_platforms": offline,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Chrome CDP sessions used by data_robot.")
    parser.add_argument("--platform", action="append", choices=sorted(PLATFORM_PORTS), help="Only check selected platform; repeatable.")
    args = parser.parse_args()

    summary = check_platforms(args.platform)
    print_json(summary)
    return 0 if summary["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
