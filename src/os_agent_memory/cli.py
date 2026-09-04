from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .evaluation import run_evaluation_suite, run_smoke_evaluation
from .ingestion import DataIngestionPipeline
from .knowledge import KnowledgeExtractor
from .memory_store import MemoryStore
from .persistence import SQLiteMemoryPersistence
from .preference import PreferenceExtractor
from .service import MemoryService


def build_store(input_path: Path) -> MemoryStore:
    ingestion = DataIngestionPipeline()
    raw_records = ingestion.load_jsonl(input_path)
    records = ingestion.ingest(raw_records)

    preference_extractor = PreferenceExtractor()
    knowledge_extractor = KnowledgeExtractor()
    store = MemoryStore()

    for memory in preference_extractor.extract(records):
        store.upsert_preference(memory)
    for memory in knowledge_extractor.extract(records):
        store.upsert_knowledge(memory)

    return store


def run_demo(input_path: Path) -> None:
    store = build_store(input_path)
    print("== Memory Stats ==")
    print(json.dumps(store.stats(), ensure_ascii=False, indent=2))

    print("\n== Preferences ==")
    for preference in store.preferences.values():
        print(
            json.dumps(
                {
                    "user_id": preference.user_id,
                    "key": preference.key,
                    "value": preference.value,
                    "confidence": preference.confidence,
                    "version": preference.version,
                    "scenes": preference.scenes,
                    "status": preference.status.value,
                },
                ensure_ascii=False,
            )
        )

    print("\n== Search: 报销流程模板 ==")
    for result in store.search_knowledge("报销流程模板", top_k=3):
        print(json.dumps(asdict(result), ensure_ascii=False))

    print("\n== Forget: 删除报销模板相关记忆 ==")
    forget_result = store.forget("删除报销模板相关记忆")
    print(json.dumps(asdict(forget_result), ensure_ascii=False, indent=2))

    print("\n== Smoke Evaluation ==")
    print(json.dumps(run_smoke_evaluation(store), ensure_ascii=False, indent=2))


def run_build_store(input_path: Path, output_path: Path) -> None:
    store = build_store(input_path)
    SQLiteMemoryPersistence(output_path).save(store)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "stats": store.stats(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_evaluate(suite_path: Path, top_k: int, summary_only: bool = False, output_path: Path | None = None) -> None:
    result = run_evaluation_suite(suite_path, top_k=top_k)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = _evaluation_summary(result) if summary_only else result
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _evaluation_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        "suite": result["suite"],
        "top_k": result["top_k"],
        "metrics": result["metrics"],
        "counts": result["counts"],
        "targets": result["targets"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OS Agent memory optimization prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="Run the sample memory pipeline")
    demo.add_argument("--input", required=True, type=Path, help="Path to JSONL event file")

    evaluate = subparsers.add_parser("evaluate", help="Run a labeled evaluation suite")
    evaluate.add_argument("--suite", required=True, type=Path, help="Path to evaluation suite JSON")
    evaluate.add_argument("--top-k", default=3, type=int, help="Number of results used for recall")
    evaluate.add_argument("--summary-only", action="store_true", help="Print only summary metrics and counts")
    evaluate.add_argument("--output", type=Path, help="Write full JSON evaluation report to this path")

    build_store_command = subparsers.add_parser("build-store", help="Build a SQLite memory store from JSONL events")
    build_store_command.add_argument("--input", required=True, type=Path, help="Path to JSONL event file")
    build_store_command.add_argument("--output", required=True, type=Path, help="Path to SQLite output file")

    serve_command = subparsers.add_parser("serve", help="Run the local browser demonstration dashboard")
    serve_command.add_argument("--input", type=Path, help="Optional JSONL events loaded at startup")
    serve_command.add_argument("--database", type=Path, help="Optional persistent SQLite database")
    serve_command.add_argument("--host", default="127.0.0.1", help="Bind address (default: localhost only)")
    serve_command.add_argument("--port", default=8765, type=int, help="HTTP port")

    args = parser.parse_args()
    if args.command == "demo":
        run_demo(args.input)
    elif args.command == "evaluate":
        run_evaluate(args.suite, top_k=args.top_k, summary_only=args.summary_only, output_path=args.output)
    elif args.command == "build-store":
        run_build_store(args.input, args.output)
    elif args.command == "serve":
        from .web_server import serve

        service = MemoryService(database_path=args.database)
        if args.input:
            raw_records = service.ingestion.load_jsonl(args.input)
            service.ingest(raw_records)
        serve(service, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
