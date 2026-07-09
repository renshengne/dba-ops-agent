"""dialect 各库采集单元测试。"""

from dba_ops_agent.dialect import is_read_only_query
from dba_ops_agent.dialect.gaussdb_pg import GaussDBPgDialect
from dba_ops_agent.dialect.mysql import MySQLDialect
from dba_ops_agent.dialect.oracle import OracleDialect
from dba_ops_agent.models import MetricStatus

from .conftest import ErrorConnection, MockConnection


def test_is_read_only_query_allows_select():
    assert is_read_only_query("SELECT * FROM t")
    assert is_read_only_query("SHOW STATUS LIKE 'x'")
    assert is_read_only_query("WITH cte AS (SELECT 1) SELECT * FROM cte")


def test_is_read_only_query_blocks_writes():
    assert not is_read_only_query("DELETE FROM t")
    assert not is_read_only_query("UPDATE t SET a=1")
    assert not is_read_only_query("DROP TABLE t")
    assert not is_read_only_query("INSERT INTO t VALUES(1)")


def test_mysql_connection_usage():
    conn = MockConnection({
        "Threads_connected": [("Threads_connected", "10")],
        "max_connections": [("max_connections", "100")],
    })
    sample = MySQLDialect().collect("connection_usage", conn)
    assert sample.status is MetricStatus.OK
    assert sample.value == 10.0
    assert sample.detail["current"] == 10
    assert sample.detail["max"] == 100


def test_mysql_slow_queries():
    conn = MockConnection({
        "processlist": [(1, "db1", "u1", "Query", 5, "executing", "SELECT * FROM big")],
    })
    sample = MySQLDialect().collect("slow_queries", conn, slow_threshold=1)
    assert sample.value == 1
    assert sample.detail["slow_sessions"][0]["session_id"] == 1


def test_mysql_collect_error_isolated():
    sample = MySQLDialect().collect("connection_usage", ErrorConnection())
    assert sample.status is MetricStatus.ERROR
    assert sample.error is not None


def test_mysql_unsupported_metric():
    conn = MockConnection()
    sample = MySQLDialect().collect("not_exist", conn)
    assert sample.status is MetricStatus.ERROR


def test_gaussdb_connection_usage():
    conn = MockConnection({
        "pg_stat_activity": [(5,)],
        "max_connections": [("100",)],
    })
    sample = GaussDBPgDialect().collect("connection_usage", conn)
    assert sample.value == 5.0
    assert sample.detail["max"] == 100


def test_gaussdb_lock_waits():
    conn = MockConnection({
        "pg_locks": [(123, "t1", "AccessExclusiveLock", False)],
    })
    sample = GaussDBPgDialect().collect("lock_waits", conn)
    assert sample.value == 1
    assert sample.detail["blocked_locks"][0]["pid"] == 123


def test_oracle_connection_usage():
    conn = MockConnection({
        "v$session": [(3,)],
        "processes": [("50",)],
    })
    sample = OracleDialect().collect("connection_usage", conn)
    assert sample.value == 6.0
    assert sample.detail["current"] == 3


def test_oracle_disk_usage():
    conn = MockConnection({
        "dba_data_files": [("USERS", 104857600)],
    })
    sample = OracleDialect().collect("disk_usage", conn)
    assert sample.value == 100.0
    assert sample.detail["per_tablespace"]["USERS"] == 100.0
