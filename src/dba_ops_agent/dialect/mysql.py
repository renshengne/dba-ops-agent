"""MySQL/MariaDB 采集方言。"""

from __future__ import annotations

from typing import Any

from ..models import MetricSample, MetricStatus
from . import Dialect


class MySQLDialect(Dialect):
    name = "mysql"

    def supported_metrics(self) -> list[str]:
        return [
            "connection_usage",
            "slow_queries",
            "lock_waits",
            "disk_usage",
            "replication_lag",
            "buffer_pool_hit_rate",
        ]

    def collect(self, metric: str, conn: Any, **kwargs: Any) -> MetricSample:
        try:
            handler = getattr(self, f"_collect_{metric}", None)
            if handler is None:
                return MetricSample(
                    metric, None, status=MetricStatus.ERROR, error=f"unsupported metric: {metric}"
                )
            return handler(conn, **kwargs)
        except Exception as e:
            return MetricSample(metric, None, status=MetricStatus.ERROR, error=str(e))

    def _collect_connection_usage(self, conn: Any, **kwargs: Any) -> MetricSample:
        threads_row = self.safe_query(conn, "SHOW STATUS LIKE 'Threads_connected'")
        threads = int(threads_row[0][1]) if threads_row else 0
        max_row = self.safe_query(conn, "SHOW VARIABLES LIKE 'max_connections'")
        max_conn = int(max_row[0][1]) if max_row else 0
        usage = (threads / max_conn * 100) if max_conn else 0.0
        return MetricSample(
            "connection_usage",
            round(usage, 2),
            unit="%",
            threshold_ref={"current": threads, "max": max_conn},
            detail={"current": threads, "max": max_conn},
        )

    def _collect_slow_queries(self, conn: Any, **kwargs: Any) -> MetricSample:
        threshold = kwargs.get("slow_threshold", 1)
        rows = self.safe_query(
            conn,
            "SELECT id, db, user, command, time, state, info "
            "FROM information_schema.processlist "
            "WHERE command='Query' AND time > %s",
            (threshold,),
        )
        sessions = [
            {
                "session_id": r[0],
                "database": r[1],
                "user": r[2],
                "duration_sec": r[4],
                "state": r[5],
                "sql_text": r[6],
            }
            for r in rows
        ]
        return MetricSample(
            "slow_queries",
            len(sessions),
            unit="count",
            detail={"slow_sessions": sessions, "threshold_sec": threshold},
        )

    def _collect_lock_waits(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SELECT id, user, host, db, command, time, state, info "
            "FROM information_schema.processlist "
            "WHERE state LIKE 'Waiting for%' OR state LIKE '%lock%'",
        )
        blocked = [
            {
                "session_id": r[0],
                "user": r[1],
                "database": r[3],
                "duration_sec": r[5],
                "state": r[6],
                "sql_text": r[7],
            }
            for r in rows
        ]
        return MetricSample(
            "lock_waits",
            len(blocked),
            unit="count",
            detail={"blocked_sessions": blocked},
        )

    def _collect_disk_usage(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SELECT TABLE_SCHEMA, SUM(DATA_LENGTH + INDEX_LENGTH) "
            "FROM information_schema.tables WHERE TABLE_SCHEMA NOT IN ('information_schema','performance_schema','mysql','sys') "
            "GROUP BY TABLE_SCHEMA",
        )
        per_db = {r[0]: round(r[1] / 1024 / 1024, 2) for r in rows}
        total = sum(per_db.values())
        return MetricSample(
            "disk_usage",
            round(total, 2),
            unit="MB",
            detail={"per_database": per_db},
        )

    def _collect_replication_lag(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(conn, "SHOW SLAVE STATUS")
        if not rows:
            rows = self.safe_query(conn, "SHOW REPLICA STATUS")
        lag = 0
        detail: dict[str, Any] = {"is_replica": False}
        if rows:
            row = rows[0]
            lag = row[12] if len(row) > 12 and row[12] is not None else 0
            try:
                lag = int(lag)
            except (TypeError, ValueError):
                lag = 0
            detail = {"is_replica": True, "seconds_behind_master": lag}
        return MetricSample(
            "replication_lag",
            lag,
            unit="sec",
            detail=detail,
        )

    def _collect_buffer_pool_hit_rate(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SHOW STATUS LIKE 'Innodb_buffer_pool_read%'",
        )
        stats = {r[0]: int(r[1]) for r in rows}
        read_req = stats.get("Innodb_buffer_pool_read_requests", 0)
        read_phys = stats.get("Innodb_buffer_pool_reads", 0)
        hit = ((read_req - read_phys) / read_req * 100) if read_req else 100.0
        return MetricSample(
            "buffer_pool_hit_rate",
            round(hit, 2),
            unit="%",
            detail={"read_requests": read_req, "physical_reads": read_phys},
        )
