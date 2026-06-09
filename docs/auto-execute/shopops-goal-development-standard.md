# ShopOps Goal Development Standard

## Source Of Truth
优先级：用户本轮目标 > AGENTS.md > `docs/taobao_mvp_requirements.md` > `docs/taobao_mvp_development.md` > 现有代码 > 历史执行证据。

## 业务边界
- 当前 MVP 只支持淘宝单平台。
- 当前订单来源默认 `ORDER_SOURCE=crawler`，真实淘宝 API 是后续阶段预留，不阻塞当前 crawler MVP。
- 当前推广来源只允许 `PROMOTION_SOURCE=qianniu_pc`。
- 千牛 PC 当前只允许订单中心和推广中心两个只读页面。
- 推广中心只读“花费”指标，不拆分直通车/万相台/引力魔方，不做投放修改。

## 数据与存储
- 业务层只能依赖 `Storage` 抽象。
- 飞书表名和字段必须保持中文业务含义。
- 所有快照/日志类写入必须有 `unique_key` upsert。
- 写入失败必须进入 pending cache，并在下轮任务开始前 replay。
- 采集失败必须写状态和错误，不能写 0 污染指标。

## 安全
- 不绕过验证码、登录、权限或平台安全机制。
- 不保存淘宝主账号密码、买家手机号、姓名、地址等 PII。
- 不把密钥写入代码、日志、报告。
