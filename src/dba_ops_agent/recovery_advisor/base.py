"""恢复建议器：生成动作脚本+影响评估+回滚预案，绝不执行。"""

from __future__ import annotations

from ..models import Finding, RecoveryPlan, RecoveryStep, Severity

_HUMAN_NOTE = "需 DBA 人工执行，Agent 不自动执行任何写操作"


class RecoveryAdvisor:
    def advise(self, findings: list[Finding], db: str) -> list[RecoveryPlan]:
        plans: list[RecoveryPlan] = []
        for f in findings:
            if f.severity not in (Severity.WARN, Severity.CRITICAL):
                continue
            plan = self._build_plan(f, db)
            if plan is not None:
                plans.append(plan)
        return plans

    def _build_plan(self, f: Finding, db: str) -> RecoveryPlan | None:
        metric = f.metric
        if metric == "lock_waits":
            return self._plan_kill_blocked(f, db)
        if metric == "connection_usage":
            return self._plan_scale_connections(f, db)
        if metric == "slow_queries":
            return self._plan_tune_slow_sql(f, db)
        if metric == "replication_lag":
            return self._plan_failover(f, db)
        if metric == "disk_usage":
            return self._plan_cleanup_or_expand(f, db)
        return None

    def _plan_kill_blocked(self, f: Finding, db: str) -> RecoveryPlan:
        blocked = 0
        if f.raw and isinstance(f.raw.get("detail"), dict):
            d = f.raw["detail"]
            lst = d.get("blocked_sessions") or d.get("blocked_locks") or []
            blocked = len(lst) if isinstance(lst, list) else lst
        return RecoveryPlan(
            finding_id=f.id,
            action_type="kill_blocked_session",
            steps=[
                RecoveryStep(
                    title="定位阻塞源会话",
                    script="SELECT * FROM <阻塞会话视图> WHERE state LIKE 'Waiting%'; -- 替换为实际会话ID",
                    note="只读查询定位阻塞源",
                ),
                RecoveryStep(
                    title="kill 阻塞源会话",
                    script="KILL <session_id>; -- 需替换为实际会话ID，由 DBA 执行",
                    note=_HUMAN_NOTE,
                ),
            ],
            impact=f"kill 会话将终止其事务，被阻塞 {blocked} 个会话将恢复；被 kill 的事务无法恢复，需评估业务影响",
            rollback="kill 会话不可回滚；执行前确认该会话事务可被放弃，必要时先备份相关数据",
            requires_human=True,
        )

    def _plan_scale_connections(self, f: Finding, db: str) -> RecoveryPlan:
        return RecoveryPlan(
            finding_id=f.id,
            action_type="scale_connections",
            steps=[
                RecoveryStep(
                    title="评估当前连接来源分布",
                    script="SELECT user, host, count(*) FROM information_schema.processlist GROUP BY user, host; -- 示例SQL，按实际库调整",
                    note="只读诊断，先确认是否为泄漏",
                ),
                RecoveryStep(
                    title="调整 max_connections（如确需扩容）",
                    script="SET GLOBAL max_connections = <new_value>; -- 建议值需 DBA 评估内存后确定",
                    note=_HUMAN_NOTE,
                ),
            ],
            impact="提高 max_connections 会增加内存占用，需评估实例内存余量；若为连接池泄漏，扩容仅延缓而非根治",
            rollback="回滚: SET GLOBAL max_connections = <old_value>; -- 恢复原值",
            requires_human=True,
        )

    def _plan_tune_slow_sql(self, f: Finding, db: str) -> RecoveryPlan:
        return RecoveryPlan(
            finding_id=f.id,
            action_type="tune_slow_sql",
            steps=[
                RecoveryStep(
                    title="获取执行计划",
                    script="EXPLAIN <慢SQL>; -- 由 DBA 填入慢SQL文本",
                    note="只读分析",
                ),
                RecoveryStep(
                    title="评估并创建索引（需人工验证）",
                    script="CREATE INDEX <idx_name> ON <table>(<columns>); -- 需 DBA 评估写性能影响后执行",
                    note=_HUMAN_NOTE,
                ),
            ],
            impact="新增索引会占用存储并可能降低写入性能，需评估业务写入量",
            rollback="回滚: DROP INDEX <idx_name> ON <table>; -- 删除新增索引",
            requires_human=True,
        )

    def _plan_failover(self, f: Finding, db: str) -> RecoveryPlan:
        return RecoveryPlan(
            finding_id=f.id,
            action_type="failover_check",
            steps=[
                RecoveryStep(
                    title="切换前检查",
                    script="# 1. 确认主库状态\n# 2. 确认备库同步位点与延迟\n# 3. 通知相关业务方",
                    note="检查清单，只读",
                ),
                RecoveryStep(
                    title="执行主备切换",
                    script="# 按数据库类型执行切换命令（如 MySQL: CHANGE MASTER TO / GaussDB: switchover）\n# 具体 SQL/命令由 DBA 按预案执行",
                    note=_HUMAN_NOTE,
                ),
                RecoveryStep(
                    title="切换后验证",
                    script="# 1. 验证新主可读写\n# 2. 验证应用连接正常\n# 3. 监控复制状态",
                    note="验证清单，只读",
                ),
            ],
            impact="主备切换期间写入不可用，需在维护窗口执行；切换错误可能导致数据不一致",
            rollback="切回原主库预案：在原主恢复后，按反向切换流程切回，需确认数据已同步",
            requires_human=True,
        )

    def _plan_cleanup_or_expand(self, f: Finding, db: str) -> RecoveryPlan:
        return RecoveryPlan(
            finding_id=f.id,
            action_type="cleanup_or_expand",
            steps=[
                RecoveryStep(
                    title="评估可清理的历史数据",
                    script="SELECT table_schema, sum(data_length)/1024/1024 AS mb FROM information_schema.tables GROUP BY table_schema ORDER BY mb DESC; -- 只读",
                    note="先定位大库大表",
                ),
                RecoveryStep(
                    title="清理或归档（需人工执行）",
                    script="-- 按业务保留期执行 DELETE/归档，DBA 执行前先备份",
                    note=_HUMAN_NOTE,
                ),
                RecoveryStep(
                    title="扩容表空间（如需）",
                    script="-- ALTER TABLESPACE ... ADD DATAFILE / 扩容磁盘，由 DBA 执行",
                    note=_HUMAN_NOTE,
                ),
            ],
            impact="删除数据不可恢复，需先备份并确认保留期；扩容需确认存储配额",
            rollback="删除操作不可回滚；执行前必须备份相关数据",
            requires_human=True,
        )
