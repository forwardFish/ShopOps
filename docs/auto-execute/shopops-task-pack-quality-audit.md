# ShopOps shopops-task-pack-quality-audit.md

本项目是中文项目。所有文档、页面显示、飞书表名和字段名都必须使用中文。
飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。
当前版本只要求真实飞书多维表格和真实千牛 PC 页面采集；淘宝开放平台 API 仅作为后续阶段预留，缺少 TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_SESSION_KEY 不得阻塞当前 crawler 版本。必须仅使用环境变量凭据和已登录授权会话，缺失真实飞书或千牛 PC 会话时写入 BLOCKED_BY_ENVIRONMENT，不得冒充 PASS。

## Verdict
`READY_FOR_AUTO_EXECUTE`


