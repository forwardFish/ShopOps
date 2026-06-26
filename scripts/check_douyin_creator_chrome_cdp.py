from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime


def check_http(url: str, timeout: int) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url.rstrip('/') + '/json/version', timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
            return {
                'ok': response.status == 200,
                'status': response.status,
                'browser': body.get('Browser', ''),
                'web_socket_debugger_url': body.get('webSocketDebuggerUrl', ''),
            }
    except Exception as exc:
        return {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}


def check_tcp(host: str, port: int, timeout: int) -> dict[str, object]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {'ok': True, 'host': host, 'port': port}
    except Exception as exc:
        return {'ok': False, 'host': host, 'port': port, 'error': f'{type(exc).__name__}: {exc}'}


def main() -> int:
    parser = argparse.ArgumentParser(description='Check Google Chrome CDP readiness for Douyin creator collection.')
    parser.add_argument('--cdp-url', default='http://127.0.0.1:9224')
    parser.add_argument('--timeout-seconds', type=int, default=3)
    args = parser.parse_args()
    host_port = args.cdp_url.rsplit(':', 1)
    host = host_port[0].replace('http://', '').replace('https://', '').strip('/')
    try:
        port = int(host_port[1].split('/')[0])
    except Exception:
        port = 9224
    tcp = check_tcp(host, port, args.timeout_seconds)
    http = check_http(args.cdp_url, args.timeout_seconds)
    result = {
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'cdp_url': args.cdp_url,
        'ready': bool(tcp.get('ok') and http.get('ok')),
        'tcp': tcp,
        'http': http,
        'chrome_only': True,
        'run_when_ready': (
            'python scripts/run_douyin_creator_roi_pipeline.py --target 50 --keywords \u6d17\u9762\u5976 '
            '--collection-mode profile --comments-per-creator 50 --profile-video-limit 30 '
            f'--direct-cdp --cdp-url {args.cdp_url} --round-timeout-seconds 7200 --max-rounds 3'
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
