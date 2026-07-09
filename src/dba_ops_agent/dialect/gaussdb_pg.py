"""GaussDB/PostgreSQL 采集方言。"""

from __future__ import annotations

from typing import Any

from ..models import MetricSample, MetricStatus
from . import Dialect


class GaussDBPgDialect(Dialect):
    name = "gaussdb_pg"

    def supported_metrics(self) -> list[str]:
        return [
            "connection_usage",
            "slow_queries",
            "lock_waits",
            "disk_usage",
            "replication_lag",
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
        cur_row = self.safe_query(conn, "SELECT count(*) FROM pg_stat_activity")
        current = cur_row[0][0] if cur_row else 0
        max_row = self.safe_query(conn, "SHOW max_connections")
        max_conn = 0
        if max_row:
            try:
                max_conn = int(max_row[0][0])
            except (ValueError, TypeError):
                max_conn = 0
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
            "SELECT pid, datname, now()-query_start AS duration, state, query "
            "FROM pg_stat_activity "
            "WHERE state='active' AND now()-query_start > %s::interval",
            (f"{threshold} seconds",),
        )
        sessions = [
            {
                "session_id": r[0],
                "database": r[1],
                "duration_sec": float(r[2].total_seconds()) if r[2] is not None else 0,
                "state": r[3],
                "sql_text": r[4],
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
            "SELECT pid, relation::regclass AS rel, mode, granted "
            "FROM pg_locks WHERE NOT granted",
        )
        blocked = [
            {"pid": r[0], "relation": r[1], "mode": r[2], "granted": r[3]}
            for r in rows
        ]
        return MetricSample(
            "lock_waits",
            len(blocked),
            unit="count",
            detail={"blocked_locks": blocked},
        )

    def _collect_disk_usage(self, conn: Any, **kwargs: Any) -> MetricSample:
        rows = self.safe_query(
            conn,
            "SELECT datname, pg_database_size(datname) FROM pg_database "
            "WHERE datname IS NOT NULL",
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
        repl_rows = self.safe_query(
            conn,
            "SELECT application_name, state, "
            "COALESCE(EXTRACT(EPOCH FROM write_lag),0) AS write_lag "
            "FROM pg_stat_replication",
        )
        detail: dict[str, Any] = {"role": "primary_or_unknown", "replicas": []}
        lag: float = 0.0
        if repl_rows:
            detail["role"] = "primary"
            detail["replicas"] = [
                {"name": r[0], "state": r[1], "write_lag_sec": float(r[2] or 0)}
                for r in repl_rows
            ]
            lag = max(float(r[2] or 0) for r in repl_rows)
        else:
            try:
                replay_row = self.safe_query(
                    conn,
                    "SELECT COALESCE(EXTRACT(EPOCH FROM now()-pg_last_xact_replay_timestamp()),0)",
                )
                if replay_row and replay_row[0][0] is not None:
                    detail["role"] = "standby"
                    lag = float(replay_row[0][0])
            except Exception:
                pass
        return MetricSample(
            "replication_lag",
            round(lag, 2),
            unit="sec",
            detail=detail,
        )

    def _collect_top_sql(self, conn: Any, **kwargs: Any) -> MetricSample:
        limit = kwargs.get("top_n", 10)
        rows = self.safe_query(
            conn,
            "SELECT query, calls, total_exec_time, rows "
            "FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT %s",
            (limit,),
        )
        top = [
            {
                "sql_text": r[0],
                "calls": r[1],
                "total_exec_time": r[2],
                "rows": r[3],
            }
            for r in rows
        ]
        return MetricSample(
            "top_sql",
            len(top),
            unit="count",
            detail={"top_sql": top},
        )
