"""Real service/SQLite/HTTP workload, separate from retrieval-only scaling."""
from __future__ import annotations

import json
import platform
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread
from time import perf_counter
from urllib.request import ProxyHandler, Request, build_opener

from .benchmark import _percentile
from .service import MemoryService
from .web_server import create_server


def workload_event(index):
    return {
        "id": f"load-{index}", "tenant_id": "load", "user_id": "operator",
        "source_type": "manual_config", "timestamp": "2026-01-01T00:00:00+00:00",
        "scene": "office",
        "content": f"专项 task{index:05d} 处理流程：登记输入编号，校验材料，完成审批并保留审计记录。",
        "metadata": {"title": f"专项 task{index:05d}", "topic": f"task{index:05d}"},
    }


def run_service_workload(sizes=(100, 1000), *, rounds=30, embedding_config=None):
    if not sizes or any(n <= 0 for n in sizes) or rounds < 3:
        raise ValueError("sizes must be positive and rounds >= 3")
    results = []
    for size in sizes:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.sqlite"
            kwargs = {"embedding_config": embedding_config} if embedding_config else {}
            service = MemoryService(database_path=path, **kwargs)
            start = perf_counter()
            service.ingest([workload_event(i) for i in range(size)])
            ingest_ms = (perf_counter() - start) * 1000
            start = perf_counter()
            service.ingest([workload_event(size)])
            incremental_ms = (perf_counter() - start) * 1000
            start = perf_counter()
            reloaded = MemoryService(database_path=path, **kwargs)
            reload_ms = (perf_counter() - start) * 1000
            def query(index):
                started = perf_counter()
                hits = reloaded.search(f"task{index % size:05d} 材料审批", tenant_id="load", user_id="operator")
                return (perf_counter() - started) * 1000, bool(hits)
            timings = [query(i) for i in range(rounds)]
            start = perf_counter()
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(query, i) for i in range(rounds)]
                writes = [pool.submit(reloaded.ingest, [workload_event(size + 1 + i)]) for i in range(3)]
                concurrent = [future.result() for future in futures]
                for future in writes:
                    future.result()
            concurrent_ms = (perf_counter() - start) * 1000
            server = create_server(reloaded, port=0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            http_timings = []
            opener = build_opener(ProxyHandler({}))
            try:
                for i in range(min(rounds, 10)):
                    body = json.dumps({"query": f"task{i % size:05d}", "tenant_id": "load", "user_id": "operator"}).encode()
                    request = Request(f"http://127.0.0.1:{server.server_port}/api/search",
                                      data=body, headers={"Content-Type": "application/json"})
                    start = perf_counter()
                    with opener.open(request, timeout=20) as response:
                        json.loads(response.read())
                    http_timings.append((perf_counter() - start) * 1000)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
            latencies = [row[0] for row in timings]
            results.append({
                "records": size, "service_ingest_ms": round(ingest_ms, 3),
                "single_add_ms": round(incremental_ms, 3), "restart_load_ms": round(reload_ms, 3),
                "mixed_query_p50_ms": round(_percentile(latencies, .5), 3),
                "mixed_query_p95_ms": round(_percentile(latencies, .95), 3),
                "mixed_query_p99_ms": round(_percentile(latencies, .99), 3),
                "http_query_p99_ms": round(_percentile(http_timings, .99), 3),
                "concurrent_operations": rounds + 3,
                "concurrent_operations_per_second": round((rounds + 3) * 1000 / concurrent_ms, 3),
                "all_queries_nonempty": all(row[1] for row in [*timings, *concurrent]),
                "persisted_knowledge": len(MemoryService(database_path=path, **kwargs).store.knowledge),
                "sqlite_bytes": path.stat().st_size,
                "retrieval_under_500ms": max(latencies + http_timings) <= 500,
            })
    return {
        "environment": {"system": platform.system(), "python": platform.python_version()},
        "rounds": rounds, "results": results,
        "method": "MemoryService ingestion including lifecycle, conflict detection and SQLite commit; diverse queries; restart; 4 threads mixed reads/writes; localhost HTTP",
        "limitations": ["Developer machine only; no real Kylin SDK evidence.",
                        "Service API is a single-process serialized writer; cross-process writers are unsupported.",
                        "Small samples describe this workload; p99 is empirical, not a production SLA."],
    }
