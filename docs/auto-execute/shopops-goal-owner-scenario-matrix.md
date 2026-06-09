# ShopOps Goal Owner Scenario Matrix

| Scenario ID | Persona | Preconditions | Exact Action | Expected Storage/API | Expected Visible Result | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OWNER-001 | 商家老板 | 千牛和飞书配置可用 | 执行一次 full_collect | 写 monitor_snapshot/orders_raw/promotion_snapshot/metrics_10min/task_run_log | 飞书看板可读到今日订单、成交额、花费、ROI、获客成本 | T11/T13 | PLANNED |
| OWNER-002 | 运营人员 | 千牛未运行 | 执行一次 full_collect | 写失败 task_run_log/alert_log，不写 0 | 飞书告警或 blocker 显示千牛不可用 | T04/T09 | PLANNED |
| OWNER-003 | 运营人员 | 飞书写入失败 | 执行一次 full_collect | pending_records.jsonl 记录，后续 replay | 不丢数据，不误报成功 | T03/T09 | PLANNED |
| OWNER-004 | 商家老板 | 到达日报时间 | 触发日报 | 写 daily_report，调用 webhook | 群里出现日报或环境 blocker | T10 | PLANNED |
