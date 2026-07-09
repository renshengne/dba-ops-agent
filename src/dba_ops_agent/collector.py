"""采集编排器：按任务编排多指标采集，聚合为 MetricBundle。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .db.pool import ConnectionPool
from .dialect import Dialect
from .models import MetricBundle, MetricSample


class Collector:
    """按指标列表编排采集，支持并发与串行。"""

    def __init__(self, dialect: Dialect, pool: ConnectionPool, max_workers: int = 4) -> None:
        self.dialect = dialect
        self.pool = pool
        self.max_workers = max_workers

    def run(
        self,
        database: str,
        task: str,
        metrics: list[str] | None = None,
        collect_kwargs: dict[str, Any] | None = None,
        parallel: bool = True,
    ) -> MetricBundle:
        metrics = metrics or self.dialect.supported_metrics()
        kwargs = collect_kwargs or {}
        bundle = MetricBundle(database=database, task=task)

        if parallel and len(metrics) > 1:
            samples = self._collect_parallel(metrics, kwargs)
        else:
            samples = self._collect_serial(metrics, kwargs)

        for _, s in zip(metrics, samples, strict=False):
            bundle.samples.append(s)
        return bundle

    def _collect_serial(self, metrics: list[str], kwargs: dict[str, Any]) -> list[MetricSample]:
        out: list[MetricSample] = []
        for m in metrics:
            with self.pool.get_conn() as conn:
                out.append(self.dialect.collect(m, conn, **kwargs))
        return out

    def _collect_parallel(self, metrics: list[str], kwargs: dict[str, Any]) -> list[MetricSample]:
        results: dict[str, MetricSample] = {}
        results_lock = threading.Lock()

        def _do(metric: str) -> tuple[str, MetricSample]:
            with self.pool.get_conn() as conn:
                return metric, self.dialect.collect(metric, conn, **kwargs)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(metrics))) as ex:
            futures = {ex.submit(_do, m): m for m in metrics}
            for fut in as_completed(futures):
                metric, sample = fut.result()
                with results_lock:
                    results[metric] = sample
        return [results[m] for m in metrics]
