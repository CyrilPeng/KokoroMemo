"""Run deterministic AIRP memory benchmark cases without external APIs."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.memory.card_retriever import retrieve_cards
from app.memory.query_builder import RetrievalQuery
from app.storage.sqlite_cards import (
    create_memory_library,
    init_cards_db,
    insert_card,
    set_conversation_mounts,
)
from benchmarks.metrics import evaluate_case, summarize


SUMMARY_METRICS = (
    "total_cases",
    "passed_cases",
    "failed_cases",
    "recall_accuracy",
    "false_positive_rate",
    "avg_injected_tokens",
)


class FakeEmbeddingProvider:
    async def embed_text(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


class FakeVectorStore:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def search(self, _vector: list[float], where: str | None = None, top_k: int = 30) -> list[dict[str, Any]]:
        return [row for row in self.rows if _matches_where(row, where or "")][:top_k]


def _matches_where(row: dict[str, Any], where: str) -> bool:
    user_match = re.search(r"user_id = '([^']+)'", where)
    if user_match and row.get("user_id") != user_match.group(1):
        return False

    library_match = re.search(r"library_id IN \(([^)]+)\)", where)
    if library_match:
        allowed = {item.strip().strip("'") for item in library_match.group(1).split(",")}
        if row.get("library_id") not in allowed:
            return False

    scope = row.get("scope")
    if scope == "global":
        return "scope = 'global'" in where
    if scope == "character":
        character_id = row.get("character_id")
        return f"scope = 'character' AND character_id = '{character_id}'" in where
    if scope == "conversation":
        conversation_id = row.get("conversation_id")
        return f"scope = 'conversation' AND conversation_id = '{conversation_id}'" in where
    return False


def _case_files(smoke: bool) -> list[Path]:
    cases_dir = Path(__file__).resolve().parent / "airp_cases"
    files = sorted(cases_dir.glob("*.json"))
    return files[:3] if smoke else files


def _resolve_compare_path(compare_to: Path) -> Path:
    return compare_to / "airp_benchmark.json" if compare_to.is_dir() else compare_to


def _format_metric_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, int):
        return str(value)
    return "-"


def _compare_reports(report: dict, compare_to: Path) -> dict:
    baseline_path = _resolve_compare_path(compare_to)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_summary = baseline.get("summary", {})
    current_summary = report.get("summary", {})
    metrics = {}
    for key in SUMMARY_METRICS:
        previous = baseline_summary.get(key)
        current = current_summary.get(key)
        can_compare = isinstance(previous, (int, float)) and isinstance(current, (int, float))
        metrics[key] = {
            "previous": previous,
            "current": current,
            "delta": current - previous if can_compare else None,
        }

    baseline_results = {
        result["case_id"]: result
        for result in baseline.get("results", [])
        if isinstance(result, dict) and "case_id" in result
    }
    current_results = {
        result["case_id"]: result
        for result in report.get("results", [])
        if isinstance(result, dict) and "case_id" in result
    }
    shared_ids = set(baseline_results) & set(current_results)
    return {
        "baseline_path": str(baseline_path),
        "metrics": metrics,
        "regressed_cases": sorted(
            case_id
            for case_id in shared_ids
            if baseline_results[case_id].get("passed") and not current_results[case_id].get("passed")
        ),
        "improved_cases": sorted(
            case_id
            for case_id in shared_ids
            if not baseline_results[case_id].get("passed") and current_results[case_id].get("passed")
        ),
        "added_cases": sorted(set(current_results) - set(baseline_results)),
        "removed_cases": sorted(set(baseline_results) - set(current_results)),
    }


def _comparison_markdown(comparison: dict) -> list[str]:
    lines = [
        "",
        "## Compared With Previous Report",
        "",
        f"- Baseline: `{comparison['baseline_path']}`",
        f"- Regressed cases: {', '.join(comparison['regressed_cases']) or '-'}",
        f"- Improved cases: {', '.join(comparison['improved_cases']) or '-'}",
        f"- Added cases: {', '.join(comparison['added_cases']) or '-'}",
        f"- Removed cases: {', '.join(comparison['removed_cases']) or '-'}",
        "",
        "| Metric | Previous | Current | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key in SUMMARY_METRICS:
        metric = comparison["metrics"][key]
        delta = metric["delta"]
        lines.append(
            f"| {key} | {_format_metric_value(metric['previous'])} | "
            f"{_format_metric_value(metric['current'])} | {_format_metric_value(delta)} |"
        )
    return lines


async def _run_case(case_path: Path, work_root: Path):
    case = json.loads(case_path.read_text(encoding="utf-8"))
    db_path = str(work_root / f"{case['id']}.sqlite")
    await init_cards_db(db_path)

    for library in case.get("libraries", []):
        if library["library_id"] != "lib_default":
            await create_memory_library(
                db_path,
                library["name"],
                library.get("description", ""),
                library_id=library["library_id"],
            )

    context = case["context"]
    await set_conversation_mounts(
        db_path,
        context["conversation_id"],
        context["mounted_library_ids"],
        write_library_id=context.get("write_library_id"),
        user_id=context["user_id"],
        character_id=context.get("character_id"),
    )

    vector_rows = []
    for card in case["cards"]:
        await insert_card(
            db_path,
            card_id=card["card_id"],
            library_id=card.get("library_id", "lib_default"),
            user_id=card.get("user_id", context["user_id"]),
            character_id=card.get("character_id"),
            conversation_id=card.get("conversation_id"),
            scope=card["scope"],
            card_type=card["card_type"],
            content=card["content"],
            importance=card.get("importance", 0.8),
            confidence=card.get("confidence", 0.9),
            status="approved",
        )
        vector_rows.append({
            "memory_id": card["card_id"],
            "library_id": card.get("library_id", "lib_default"),
            "user_id": card.get("user_id", context["user_id"]),
            "character_id": card.get("character_id"),
            "conversation_id": card.get("conversation_id"),
            "scope": card["scope"],
            "status": "active",
            "_distance": card.get("distance", 0.1),
        })

    query = RetrievalQuery(
        query_text=case["query"],
        latest_user_text=case["query"],
        recent_context_text=f"user: {case['query']}",
        scope_filter={
            "user_id": context["user_id"],
            "character_id": context.get("character_id"),
            "conversation_id": context["conversation_id"],
        },
    )
    candidates = await retrieve_cards(
        query,
        FakeEmbeddingProvider(),
        FakeVectorStore(vector_rows),
        cards_db_path=db_path,
        vector_top_k=20,
        final_top_k=case.get("final_top_k", 6),
        allowed_scopes={"global", "character", "conversation"},
    )
    injected_ids = [candidate.card_id for candidate in candidates]
    injected_text = "\n".join(candidate.content for candidate in candidates)
    return evaluate_case(
        case_id=case["id"],
        injected_card_ids=injected_ids,
        injected_text=injected_text,
        expected_card_ids=case.get("expect_injected", []),
        forbidden_card_ids=case.get("expect_not_injected", []),
    )


async def run_benchmark(
    smoke: bool = False,
    report_dir: Path | None = None,
    compare_to: Path | None = None,
) -> dict:
    work_root = Path(mkdtemp(prefix="kokoromemo_benchmark_"))
    try:
        results = [await _run_case(path, work_root) for path in _case_files(smoke)]
        summary = summarize(results)
        report = {
            "summary": summary,
            "results": [asdict(result) for result in results],
        }
        if compare_to:
            report["comparison"] = _compare_reports(report, compare_to)
        if report_dir:
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "airp_benchmark.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            lines = [
                "# AIRP Benchmark Report",
                "",
                f"- Total cases: {summary['total_cases']}",
                f"- Passed cases: {summary['passed_cases']}",
                f"- Recall accuracy: {summary['recall_accuracy']:.3f}",
                f"- False positive rate: {summary['false_positive_rate']:.3f}",
                f"- Avg injected tokens: {summary['avg_injected_tokens']:.1f}",
                "",
                "| Case | Result | Missing | Leaked |",
                "|---|---:|---|---|",
            ]
            for result in report["results"]:
                lines.append(
                    f"| {result['case_id']} | {'PASS' if result['passed'] else 'FAIL'} | "
                    f"{', '.join(result['missing_card_ids']) or '-'} | "
                    f"{', '.join(result['leaked_card_ids']) or '-'} |"
                )
            if "comparison" in report:
                lines.extend(_comparison_markdown(report["comparison"]))
            (report_dir / "airp_benchmark.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return report
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run the minimal smoke case set")
    parser.add_argument("--report-dir", default="benchmarks/reports", help="Directory for JSON/Markdown reports")
    parser.add_argument(
        "--compare-to",
        default=None,
        help="Previous airp_benchmark.json or report directory to compare against",
    )
    args = parser.parse_args()
    report = asyncio.run(
        run_benchmark(
            smoke=args.smoke,
            report_dir=Path(args.report_dir),
            compare_to=Path(args.compare_to) if args.compare_to else None,
        )
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0 if report["summary"]["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
