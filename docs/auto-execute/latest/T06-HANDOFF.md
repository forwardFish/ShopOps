# T06 HANDOFF - qianniu-promotion-center-cost-crawler

Status: `BLOCKED_BY_ENVIRONMENT`

This run executed only T06 from `docs/auto-execute/shopops-goal-tasks/T06-qianniu-promotion-center-cost-crawler.md` for task pack `shopops-goal-2026-06-03`. It did not execute any other Txx task.

## Current Result

The local implementation path is covered by focused tests, but live acceptance is blocked by missing external environment. The result is not a pure PASS because there is no reachable Qianniu PC CDP session and no Feishu live credentials/table ids in this environment.

## Verification

Command:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T06-current tests\test_taobao_promotion_crawler.py tests\test_storage_and_scheduler.py tests\test_metric_scheduler_delta.py
```

Result: `12 passed in 0.26s`

Evidence:

- `docs/auto-execute/results/T06.json`
- `docs/auto-execute/logs/T06/verification-current.txt`
- `docs/auto-execute/logs/T06/environment-probe-current.json`

## Covered Locally

- Qianniu promotion center URL is `https://qn.taobao.com/home.htm/tuiguangcenter_new/`.
- The crawler extracts only promotion center cost and returns one promotion center item.
- Exposure, click, conversion, and channel split data are not captured into the promotion item.
- Login, permission, missing CDP, and cost-read failures return failure status with `None` cost values rather than numeric `0`.
- Scheduler writes one promotion snapshot and propagates promotion center cost to monitor snapshot when local collection succeeds.

## Blockers

- `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_APP_TOKEN`, `FEISHU_WEBHOOK`, `FEISHU_TABLE_PROMOTION_SNAPSHOT`, `FEISHU_TABLE_MONITOR_SNAPSHOT`, `FEISHU_TABLE_METRICS_10MIN`, and `FEISHU_TABLE_TASK_LOG` were absent, so live Feishu write/upsert/readback proof could not be attempted.
- `QIANNIU_CDP_URL` was absent and `http://127.0.0.1:9222/json/version` returned `无法连接到远程服务器`, so live Qianniu PC promotion-center collection could not be attempted.
- Missing `TAOBAO_APP_KEY`, `TAOBAO_APP_SECRET`, and `TAOBAO_SESSION_KEY` does not block this crawler-first T06 scope.

## Stop Condition

T06 result JSON, handoff, and logs are written. Stop after T06; do not continue into any other Txx task.
