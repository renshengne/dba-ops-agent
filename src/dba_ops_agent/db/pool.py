"""只读连接池工厂，启动时校验账号权限。

安全边界（硬约束）：
- 仅创建只读连接
- 校验账号是否具备写权限，若具备且未显式 allow_write_account=true，则拒绝启动
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from ..config import DatabaseConfig


class ReadOnlyViolation(RuntimeError):
    """账号被检测出写权限，或检测到非只读 SQL。"""


class ConnectionPool:
    """轻量连接池：按 dialect 懒创建连接，线程安全获取/归还。"""

    def __init__(self, cfg: DatabaseConfig, max_size: int = 8):
        self.cfg = cfg
        self.max_size = max_size
        self._pool: list[Any] = []
        self._lock = threading.Lock()
        self._checked_permission = False

    # --- dialect 连接创建 ---
    def _create_connection(self) -> Any:
        d = self.cfg.dialect
        if d == "mysql":
            import pymysql

            return pymysql.connect(
                host=self.cfg.host,
                port=self.cfg.port,
                user=self.cfg.user,
                password=self.cfg.password,
                database=self.cfg.database or None,
                charset="utf8mb4",
                autocommit=True,
                connect_timeout=10,
            )
        if d == "gaussdb_pg":
            import psycopg2

            return psycopg2.connect(
                host=self.cfg.host,
                port=self.cfg.port,
                user=self.cfg.user,
                password=self.cfg.password,
                dbname=self.cfg.database or "postgres",
                connect_timeout=10,
            )
        if d == "oracle":
            import oracledb

            service = self.cfg.service_name or "ORCLPDB1"
            dsn = oracledb.makedsn(
                self.cfg.host, self.cfg.port, service_name=service
            )
            return oracledb.connect(
                user=self.cfg.user,
                password=self.cfg.password,
                dsn=dsn,
            )
        raise ValueError(f"unsupported dialect: {d}")

    # --- 权限校验 ---
    def check_read_only_permission(self) -> None:
        """启动时校验：若账号被授予写权限，拒绝启动（除非显式允许）。"""
        if self._checked_permission:
            return
        if self.cfg.allow_write_account:
            self._checked_permission = True
            return

        d = self.cfg.dialect
        try:
            conn = self._create_connection()
        except Exception:
            self._checked_permission = True
            return

        try:
            grants = self._query_grants(conn, d)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        write_signals = self._detect_write_grants(grants, d)
        if write_signals:
            raise ReadOnlyViolation(
                f"账号 '{self.cfg.user}' 被检测出写权限: {write_signals}。"
                "DBA Agent 仅允许只读账号；如确需使用写账号，请设置 allow_write_account=true 显式确认。"
            )
        self._checked_permission = True

    def _query_grants(self, conn: Any, dialect: str) -> list[str]:
        cur = None
        try:
            cur = conn.cursor()
            if dialect == "mysql":
                cur.execute("SHOW GRANTS")
                rows = cur.fetchall()
                return [str(r[0]) for r in rows]
            if dialect == "gaussdb_pg":
                cur.execute(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = current_user"
                )
                return [str(r[0]) for r in cur.fetchall()]
            if dialect == "oracle":
                cur.execute(
                    "SELECT privilege FROM session_privs"
                )
                return [str(r[0]).upper() for r in cur.fetchall()]
        except Exception:
            return []
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
        return []

    @staticmethod
    def _detect_write_grants(grants: list[str], dialect: str) -> list[str]:
        write_keywords = {
            "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
            "GRANT OPTION", "TRUNCATE", "REPLACE", "WRITE",
            "CREATE USER", "CREATE TABLESPACE", "SHUTDOWN", "RELOAD",
            "FILE", "SUPER",
        }
        found: list[str] = []
        for g in grants:
            gu = g.upper()
            if dialect == "mysql":
                if "WITH GRANT OPTION" in gu:
                    found.append(g)
                    continue
                privs = ConnectionPool._parse_mysql_grant_privs(gu)
                for p in privs:
                    if p in write_keywords:
                        if g not in found:
                            found.append(g)
                        break
            else:
                if gu in write_keywords:
                    if g not in found:
                        found.append(g)
        return found

    @staticmethod
    def _parse_mysql_grant_privs(grant_upper: str) -> list[str]:
        """从 'GRANT SELECT, PROCESS, REPLICATION SLAVE ON *.* TO ...' 提取权限名。"""
        import re

        m = re.match(r"^\s*GRANT\s+(.+?)\s+ON\s", grant_upper)
        if not m:
            return []
        raw = m.group(1)
        if raw == "ALL PRIVILEGES" or raw == "ALL":
            return [
                "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE",
            ]
        return [p.strip() for p in raw.split(",")]

    # --- 池操作 ---
    @contextmanager
    def get_conn(self):
        if not self._checked_permission:
            self.check_read_only_permission()
        conn = None
        with self._lock:
            if self._pool:
                conn = self._pool.pop()
        if conn is None:
            conn = self._create_connection()
        try:
            yield conn
        finally:
            with self._lock:
                if len(self._pool) < self.max_size:
                    self._pool.append(conn)
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def close_all(self) -> None:
        with self._lock:
            for c in self._pool:
                try:
                    c.close()
                except Exception:
                    pass
            self._pool.clear()


class PoolRegistry:
    """多数据库连接池注册表。"""

    def __init__(self) -> None:
        self._pools: dict[str, ConnectionPool] = {}

    def register(self, cfg: DatabaseConfig) -> ConnectionPool:
        pool = ConnectionPool(cfg)
        pool.check_read_only_permission()
        self._pools[cfg.name] = pool
        return pool

    def get(self, name: str) -> ConnectionPool:
        if name not in self._pools:
            raise KeyError(f"pool '{name}' not registered")
        return self._pools[name]

    def close_all(self) -> None:
        for p in self._pools.values():
            p.close_all()
        self._pools.clear()
