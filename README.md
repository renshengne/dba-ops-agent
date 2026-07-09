# DBA 智能运维 Agent

只读型 DBA 智能运维 Agent，面向 MySQL/MariaDB、Oracle、GaussDB/PostgreSQL，提供智能巡检、异常诊断、性能诊断、快速恢复（方案生成，不自动执行）。

## 安全边界（硬约束）

- Agent 对数据库仅持有只读账号，启动时校验权限
- 任何变更/恢复类操作一律输出"动作脚本+影响评估+回滚预案"由人工执行，Agent 不自动执行任何写操作

## 安装

```bash
cd dba-ops-agent
pip install -e ".[dev]"
```

## 配置

参考 `config/config.example.yaml`，配置数据库连接、LLM、告警 webhook、巡检模板。

## 使用

```bash
# 巡检
dba patrol --db prod-mysql

# 异常诊断
dba diagnose --db prod-mysql --topic "大量锁等待"

# 性能诊断
dba perf --db prod-mysql

# 快速恢复建议
dba recovery --db prod-mysql --finding <id>

# Web 控制台
dba web

# 启动定时巡检
dba schedule
```
