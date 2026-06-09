# ShopOps Goal External Data Validation Matrix

| Data ID | 中文表名 | Internal Key | Env Var | 字段 | 幂等规则 | 失败缓存 | 读回证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DATA-001 | 系统配置表 | `system_config` | `FEISHU_TABLE_SYSTEM_CONFIG` | config_key, config_value, enabled, remark, updated_at | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-002 | 店铺配置表 | `shop_config` | `FEISHU_TABLE_SHOP_CONFIG` | shop_id, shop_name, platform, qianniu_cdp_url, order_source, promotion_source, status, remark | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-003 | 实时监控快照表 | `monitor_snapshot` | `FEISHU_TABLE_MONITOR_SNAPSHOT` | unique_key, 采集时间, 店铺ID, 店铺名称, 订单来源, 推广来源, 数据状态, 推广中心花费(元), 总推广消耗(元), 今日订单数, 今日成交额(元), 实时ROI, 获客成本(元), 错误信息, 是否告警 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-004 | 订单明细原始表 | `orders_raw` | `FEISHU_TABLE_ORDERS_RAW` | unique_key, 数据来源, 店铺ID, 店铺名称, 订单号, 下单时间, 支付时间, 订单状态, 支付金额, 商品名称, 采集时间, 原始数据 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-005 | 推广数据快照表 | `promotion_snapshot` | `FEISHU_TABLE_PROMOTION_SNAPSHOT` | unique_key, 采集时间, 店铺ID, 店铺名称, 推广渠道, 今日累计消耗(元), 曝光, 点击, 转化, 状态, 错误信息, 原始数据 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-006 | 十分钟指标表 | `metrics_10min` | `FEISHU_TABLE_METRICS_10MIN` | unique_key, 时间开始, 时间结束, 店铺ID, 店铺名称, 新增订单数, 新增成交额(元), 推广消耗(元), 周期ROI, 周期获客成本(元), 数据状态, 异常原因 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-007 | 任务运行日志表 | `task_run_log` | `FEISHU_TABLE_TASK_LOG` | task_id, 任务类型, 开始时间, 结束时间, 耗时秒, 店铺ID, 订单状态, 推广状态, 飞书写入状态, 总状态, 拉取数量, 写入数量, 错误码, 错误信息, 是否已告警 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-008 | 告警日志表 | `alert_log` | `FEISHU_TABLE_ALERT_LOG` | alert_id, 触发时间, 店铺ID, 告警类型, 告警级别, 告警内容, 当前值, 阈值, 是否已发送, 发送结果 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |
| DATA-009 | 每日报告表 | `daily_report` | `FEISHU_TABLE_DAILY_REPORT` | report_date, 店铺ID, 店铺名称, 今日订单数, 今日成交额(元), 推广中心花费(元), 总推广消耗(元), 今日ROI, 获客成本(元), 异常统计, 数据状态 | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |

## 必测用例
| Case ID | 范围 | 动作 | 期望 | 证据 |
| --- | --- | --- | --- | --- |
| EXT-001 | 所有表 | 合法 payload 写入 | 字段名和值正确 | `external-data/T03/` |
| EXT-002 | 快照/日志表 | 相同 unique_key 重复写入 | 更新而非新增重复行 | `external-data/T03/` |
| EXT-003 | 飞书失败 | 写入异常 | pending_records.jsonl 有记录 | `external-data/T03/` |
| EXT-004 | pending replay | 下轮重放 | 成功后 pending 清空或减少 | `external-data/T03/` |
| EXT-005 | 采集失败 | 订单或推广失败 | 指标为 null，状态为失败，不写 0 | `external-data/T08/` |
