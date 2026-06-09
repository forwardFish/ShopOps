# ShopOps Goal Standard Test Plan

| Test ID | Layer | Target | Case | Command/Action | Expected | Evidence | Required |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TEST-001 | unit | config/models | defaults and validation | pytest | pass | T11 logs | yes |
| TEST-002 | integration | local Feishu storage | upsert/duplicate/pending/replay | pytest | pass | T03/T11 logs | yes |
| TEST-003 | external | real Feishu | write/update/readback | verify_feishu_data.py | PASS or env blocker | external-data/T03/T11 | yes |
| TEST-004 | crawler | Qianniu order center | live CDP or env blocker | T04 worker | orders_raw proof or blocker | external-data/T04 | yes |
| TEST-005 | crawler | Qianniu promotion center | live CDP or env blocker | T06 worker | 花费 proof or blocker | external-data/T06 | yes |
| TEST-006 | business | metrics/delta | edge cases | pytest | pass | T07/T11 logs | yes |
| TEST-007 | reliability | failure-as-null | collector/storage failures | pytest | no zero pollution | T08 logs | yes |
| TEST-008 | scheduler | full_collect | pending replay + task log | pytest | pass | T09/T11 logs | yes |
| TEST-009 | docs | runbook/env | operator docs | review | complete | T10 | yes |
| TEST-010 | guard | secret/report integrity | scan | secret_guard.py | pass | T12 | yes |
| TEST-011 | final | all durable evidence | aggregate | T13 | fail closed | verification-results.md | yes |
