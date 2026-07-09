"""Oracle 采集方言。"""

from __future__ import annotations

from typing import Any

from ..models import MetricSample, MetricStatus
from . import Dialect


class OracleDialect(Dialect):
    name = "oracle"

    def supported_metrics(self) -> list[str]:
        return [
            "connection_usage",
            "slow_queries",
            "lock_waits",
            "disk_usage",
            "top_wait_events",
            "top_sql",
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
        cur_row = self.safe_query(conn, "SELECT count(*) FROM v$session WHERE type='USER'")
        current = cur_row[0][0] if cur_row else 0
        max_row = self.safe_query(conn, "SELECT value FROM v$parameter WHERE name='processes'")
        max_conn = int(max_row[0][0]) if max_row and max_row[0][0] else 0
        usage = (current / max_conn * 100) if max_conn else 0.0
        return MetricSample(
            "connection_usage",
            round(usage, 2),
            unit="%",
            detail={"current": current, "max": max_conn},
        )

    def _collect_slow_queries(self, conn: Any, **kwargs: Any) -> MetricSample:
        threshold = kwargs.get("slow_threshold", 1)
        rows = self.safe_query(
            conn,
            "SELECT s.sid, s.serial#, s.username, sq.sql_text, "
            "(sysdate - s.sql_exec_start)*86400 AS elapsed_sec "
            "FROM v$session s LEFT JOIN v$sql sq ON s.sql_id = sq.sql_id "
            "WHERE s.status='ACTIVE' AND s.username IS NOT NULL "
            "AND (sysdate - s.sql_exec_start)*86400 > :thr",
            {"thr": threshold},
        )
        sessions = [
            {
                "session_id": r[0],
                "serial": r[1],
                "user": r[2],
                "sql_text": r[3],
                "duration_sec": float(r[4] or 0),
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
            "SELECT count(*) FROM v$session "
            "WHERE wait_class='Application' OR state='WAITING'",
        )
        count = rows[0][0] if rows else 0
        detail_rows = self.safe_query(
            conn,
            "SELECT event, count(*) FROM v$session "
            "WHERE wait_class='Application' OR state='WAITING' GROUP BY event",
        )
        events = {r[0]: r[1] for r in detail_rows}
        return MetricSample(
            "lock_waits",
            int(count),
            unit="count",
            detail={"blocked_sessions": count, "events": events},
        )

    def _collect_disk_usage(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SELECT tablespace_name, sum(bytes) AS bytes "
            "FROM dba_data_files GROUP BY tablespace_name",
        )
        per_ts = {r[0]: round(r[1] / 1024 / 1024, 2) for r in rows}
        total = sum(per_ts.values())
        return MetricSample(
            "disk_usage",
            round(total, 2),
            unit="MB",
            detail={"per_tablespace": per_ts},
        )

    def _collect_top_wait_events(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SELECT event, total_waits, time_waited "
            "FROM v$system_event ORDER BY time_waited DESC FETCH FIRST 10 ROWS ONLY",
        )
        events = [
            {"event": r[0], "total_waits": r[1], "time_waited": r[2]}
            for r in rows
        ]
        return MetricSample(
            "top_wait_events",
            len(events),
            unit="count",
            detail={"wait_events": events},
        )

    def _collect_top_sql(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SELECT sql_text, executions, elapsed_time, disk_reads "
            "FROM v$sql ORDER BY elapsed_time DESC FETCH FIRST 10 ROWS ONLY",
        )
        top = [
            {
                "sql_text": r[0],
                "executions": r[1],
                "elapsed_time": r[2],
                "disk_reads": r[3],
            }
            for r in rows
        ]
        return MetricSample(
            "top_sql",
            len(top),
            unit="count",
            detail={"top_sql": top},
        )
