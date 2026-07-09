"""方言层公共接口与多库实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import MetricSample

_READ_ONLY_PREFIXES = ("SELECT", "SHOW", "DESC", "DESCRIBE", "EXPLAIN", "WITH")
_WRITE_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE",
    "GRANT", "REPLACE", "MERGE", "CALL", "EXEC",
)


def is_read_only_query(sql: str) -> bool:
    s = sql.strip().lstrip("(").strip()
    upper = s.upper()
    if not any(upper.startswith(p) for p in _READ_ONLY_PREFIXES):
        return False
    for kw in _WRITE_KEYWORDS:
        if kw in upper.split():
            return False
    return True


class Dialect(ABC):
    """多库方言抽象基类。"""

    name: str = "base"

    @abstractmethod
    def supported_metrics(self) -> list[str]:
        ...

    @abstractmethod
    def collect(self, metric: str, conn: Any, **kwargs: Any) -> MetricSample:
        ...

    def safe_query(self, conn: Any, sql: str, params: tuple[Any, ...] | dict[str, Any] | None = None) -> list[tuple]:
        if not is_read_only_query(sql):
            raise PermissionError(f"refused non-read-only SQL: {sql[:80]}")
        cur = conn.cursor()
        try:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            rows = cur.fetchall()
            return list(rows)
        finally:
            try:
                cur.close()
            except Exception:
                pass


def get_dialect(name: str) -> Dialect:
    if name == "mysql":
        from .mysql import MySQLDialect

        return MySQLDialect()
    if name == "gaussdb_pg":
        from .gaussdb_pg import GaussDBPgDialect

        return GaussDBPgDialect()
    if name == "oracle":
        from .oracle import OracleDialect

        return OracleDialect()
    raise ValueError(f"unsupported dialect: {name}")
