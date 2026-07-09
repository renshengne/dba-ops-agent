"""测试用 mock 数据库连接。"""

from __future__ import annotations

from typing import Any


class MockCursor:
    def __init__(self, results_map: dict[str, list[tuple]]) -> None:
        self.results_map = results_map
        self.last_sql: str | None = None
        self.last_params: Any = None

    def execute(self, sql: str, params: Any = ()) -> None:
        self.last_sql = sql
        self.last_params = params

    def fetchall(self) -> list[tuple]:
        if self.last_sql is None:
            return []
        for key, rows in self.results_map.items():
            if key.upper() in self.last_sql.upper():
                return list(rows)
        return []

    def close(self) -> None:
        pass


class MockConnection:
    def __init__(self, results_map: dict[str, list[tuple]] | None = None) -> None:
        self.results_map = results_map or {}

    def cursor(self) -> MockCursor:
        return MockCursor(self.results_map)

    def close(self) -> None:
        pass


class ErrorConnection:
    def cursor(self) -> Any:
        raise RuntimeError("connection broken")

    def close(self) -> None:
        pass
