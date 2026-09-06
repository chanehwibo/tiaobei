from __future__ import annotations

import json
import math
import platform
import statistics
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .memory_store import MemoryStore
from .persistence import SQLiteMemoryPersistence
from .schemas import KnowledgeMemory, stable_id
from .provider_config import create_provider, provider_identity


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(math.ceil(quantile * len(ordered)) - 1, len(ordered) - 1))
    return ordered[index]


def _benchmark_memory(index: int) -> KnowledgeMemory:
    topic = index % 97
    timestamp = "2026-01-01T00:00:00+00:00"
    return KnowledgeMemory(
        id=stable_id("benchmark", str(index)),
        title=f"办公知识 {index:05d}",
        content=(
            f"专项主题 topic{topic:03d} 的办公处理流程：先校验输入编号 {index:05d}，"
            "再生成结构化表格，最后提交审批并保留审计记录。"
        ),
        tags=["workflow", f"topic-{topic:03d}"],
        source_ids=[f"benchmark-{index:05d}"],
        version=1,
        created_at=timestamp,
        updated_at=timestamp,
        tenant_id="benchmark",
        user_id="benchmark-user",
        scene="benchmark",
        authority=0.75,
        valid_from=timestamp,
    )


def run_scale_benchmark(
    sizes: Iterable[int] = (100, 1000, 5000, 10000),
    *,
    rounds: int = 30,
    top_k: int = 5,
    embedding_config=None,
) -> dict[str, object]:
    normalized_sizes = [int(size) for size in sizes]
    if not normalized_sizes or any(size <= 0 for size in normalized_sizes):
        raise ValueError("benchmark sizes must be positive")
    if rounds <= 0 or top_k <= 0:
        raise ValueError("rounds and top_k must be positive")

    rows: list[dict[str, object]] = []
    for size in normalized_sizes:
        tracemalloc.start()
        store = MemoryStore(embedding=create_provider(embedding_config))
        start = time.perf_counter()
        for index in range(size):
            memory = _benchmark_memory(index)
            store.knowledge[memory.id] = memory
        store.rebuild_index()
        index_build_ms = (time.perf_counter() - start) * 1000

        query = f"专项主题 topic{(size // 2) % 97:03d} 办公审批流程"
        search_args = {
            "top_k": top_k,
            "tenant_id": "benchmark",
            "user_id": "benchmark-user",
            "scene": "benchmark",
        }
        start = time.perf_counter()
        cold_results = store.search_knowledge(query, **search_args)
        cold_query_ms = (time.perf_counter() - start) * 1000

        hot_timings: list[float] = []
        for _round in range(rounds):
            start = time.perf_counter()
            store.search_knowledge(query, **search_args)
            hot_timings.append((time.perf_counter() - start) * 1000)
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / f"memory-{size}.sqlite"
            SQLiteMemoryPersistence(database_path).save(store)
            sqlite_bytes = database_path.stat().st_size

        mean_ms = statistics.fmean(hot_timings)
        p99_ms = _percentile(hot_timings, 0.99)
        rows.append(
            {
                "records": size,
                "top_k": top_k,
                "index_build_ms": round(index_build_ms, 3),
                "cold_query_ms": round(cold_query_ms, 3),
                "hot_query_p50_ms": round(_percentile(hot_timings, 0.50), 3),
                "hot_query_p95_ms": round(_percentile(hot_timings, 0.95), 3),
                "hot_query_p99_ms": round(p99_ms, 3),
                "throughput_qps": round(1000 / mean_ms, 2) if mean_ms else 0.0,
                "peak_python_memory_mb": round(peak_bytes / 1024 / 1024, 3),
                "sqlite_disk_mb": round(sqlite_bytes / 1024 / 1024, 3),
                "returned_results": len(cold_results),
                "meets_500ms": max(cold_query_ms, p99_ms) <= 500.0,
            }
        )

    return {
        "benchmark": "hash_embedding_hybrid_retrieval" if embedding_config is None else "configured_hybrid_retrieval",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "kylin_os": False,
            "embedding_provider": provider_identity(store.embedding),
        },
        "method": {
            "rounds_per_size": rounds,
            "cold_definition": "first query after vector/index construction",
            "hot_definition": "subsequent repeated in-process queries",
            "memory_definition": "tracemalloc peak Python allocations during build and queries",
            "disk_definition": "SQLite v2 file size after complete persistence",
            "pass_rule": "max(cold query, hot p99) <= 500ms",
        },
        "results": rows,
        "all_meet_500ms": all(bool(row["meets_500ms"]) for row in rows),
        "limitations": [
            "Development-machine benchmark; not a real Galaxy Kylin OS result.",
            "Uses deterministic HashEmbedding; real Kylin SDK must be benchmarked separately.",
            "Synthetic records measure retrieval scaling, not end-user task completion quality.",
        ],
    }


def write_benchmark_report(
    result: dict[str, object],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_target = Path(json_path)
    markdown_target = Path(markdown_path)
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    environment = result["environment"]
    rows = result["results"]
    lines = [
        "# 检索规模性能报告（开发机）",
        "",
        f"生成时间（UTC）：{result['generated_at_utc']}",
        "",
        f"环境：{environment['system']} {environment['release']} / {environment['machine']} / Python {environment['python']}",
        "",
        "> 本报告使用 HashEmbedding 且不在银河麒麟系统运行，不能替代真实 SDK/麒麟环境报告。",
        "",
        "| 记录数 | 建索引 ms | 冷查询 ms | 热 p50 ms | 热 p95 ms | 热 p99 ms | QPS | 峰值内存 MB | SQLite MB | 500ms |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for row in rows:
        lines.append(
            "| {records} | {index_build_ms} | {cold_query_ms} | {hot_query_p50_ms} | "
            "{hot_query_p95_ms} | {hot_query_p99_ms} | {throughput_qps} | "
            "{peak_python_memory_mb} | {sqlite_disk_mb} | {status} |".format(
                **row,
                status="是" if row["meets_500ms"] else "否",
            )
        )
    lines.extend(
        [
            "",
            "判定口径：冷查询与热查询 p99 的较大值不超过 500ms。数据、方法和原始精确值见同目录 JSON。",
            "",
        ]
    )
    markdown_target.write_text("\n".join(lines), encoding="utf-8")
