"""Metrics for deterministic AIRP memory benchmarks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    injected_card_ids: list[str]
    expected_card_ids: list[str]
    forbidden_card_ids: list[str]
    missing_card_ids: list[str]
    leaked_card_ids: list[str]
    avg_injected_tokens: int


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 2.5)) if text else 0


def evaluate_case(
    *,
    case_id: str,
    injected_card_ids: list[str],
    injected_text: str,
    expected_card_ids: list[str],
    forbidden_card_ids: list[str],
) -> CaseResult:
    injected_set = set(injected_card_ids)
    expected_set = set(expected_card_ids)
    forbidden_set = set(forbidden_card_ids)
    missing = sorted(expected_set - injected_set)
    leaked = sorted(forbidden_set & injected_set)
    return CaseResult(
        case_id=case_id,
        passed=not missing and not leaked,
        injected_card_ids=injected_card_ids,
        expected_card_ids=expected_card_ids,
        forbidden_card_ids=forbidden_card_ids,
        missing_card_ids=missing,
        leaked_card_ids=leaked,
        avg_injected_tokens=estimate_tokens(injected_text),
    )


def summarize(results: list[CaseResult]) -> dict:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    expected_total = sum(len(result.expected_card_ids) for result in results)
    recalled_total = sum(
        len(set(result.expected_card_ids) & set(result.injected_card_ids))
        for result in results
    )
    forbidden_total = sum(len(result.forbidden_card_ids) for result in results)
    leaked_total = sum(len(result.leaked_card_ids) for result in results)
    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "recall_accuracy": recalled_total / expected_total if expected_total else 1.0,
        "false_positive_rate": leaked_total / forbidden_total if forbidden_total else 0.0,
        "avg_injected_tokens": (
            sum(result.avg_injected_tokens for result in results) / total if total else 0.0
        ),
    }

