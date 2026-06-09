# ShopOps Goal Software Test Standard

## 基础命令
| 面 | 命令 | 证据 |
| --- | --- | --- |
| 全量测试 | `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\goal-full` | `docs/auto-execute/logs/T11/pytest.txt` |
| 飞书数据证明 | `python scripts\acceptance\verify_feishu_data.py` | `docs/auto-execute/external-data/T11/` |
| 密钥扫描 | `python scripts\acceptance\secret_guard.py` | `docs/auto-execute/logs/T12/secret-guard.txt` |

## 外部数据 PASS 条件
每个 P0 飞书表必须证明字段映射、payload、unique_key upsert、重复运行、失败缓存、replay、读回。缺真实凭据时只能写 `BLOCKED_BY_ENVIRONMENT` 或有明确限制的本地证明。

## Final Gate
任一 P0 需求缺证据、任一 required task 缺 result JSON/HANDOFF、任一外部数据读回缺失、任一失败写 0，最终都不能 pure PASS。
