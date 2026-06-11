import json
from pathlib import Path

import pytest

from benchmarks.run_airp_benchmark import run_benchmark


@pytest.mark.asyncio
async def test_airp_benchmark_smoke(tmp_path: Path) -> None:
    report = await run_benchmark(smoke=True, report_dir=tmp_path)

    assert report["summary"]["total_cases"] == 3
    assert report["summary"]["failed_cases"] == 0
    assert report["summary"]["recall_accuracy"] == 1.0
    assert report["summary"]["false_positive_rate"] == 0.0
    assert (tmp_path / "airp_benchmark.json").exists()
    assert (tmp_path / "airp_benchmark.md").exists()


@pytest.mark.asyncio
async def test_airp_benchmark_full_case_set(tmp_path: Path) -> None:
    report = await run_benchmark(smoke=False, report_dir=tmp_path)

    assert report["summary"]["total_cases"] == 10
    assert report["summary"]["failed_cases"] == 0
    assert report["summary"]["recall_accuracy"] == 1.0
    assert report["summary"]["false_positive_rate"] == 0.0


@pytest.mark.asyncio
async def test_airp_benchmark_compares_with_previous_report(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    baseline = {
        "summary": {
            "total_cases": 3,
            "passed_cases": 2,
            "failed_cases": 1,
            "recall_accuracy": 0.667,
            "false_positive_rate": 0.250,
            "avg_injected_tokens": 4.0,
        },
        "results": [
            {"case_id": "nickname_memory", "passed": False},
            {"case_id": "character_isolation", "passed": True},
            {"case_id": "removed_case", "passed": True},
        ],
    }
    (baseline_dir / "airp_benchmark.json").write_text(
        json.dumps(baseline, ensure_ascii=False),
        encoding="utf-8",
    )

    report_dir = tmp_path / "current"
    report = await run_benchmark(smoke=True, report_dir=report_dir, compare_to=baseline_dir)

    comparison = report["comparison"]
    assert comparison["metrics"]["failed_cases"]["delta"] == -1
    assert comparison["metrics"]["recall_accuracy"]["delta"] == pytest.approx(0.333)
    assert comparison["improved_cases"] == ["nickname_memory"]
    assert comparison["regressed_cases"] == []
    assert comparison["added_cases"] == ["library_isolation"]
    assert comparison["removed_cases"] == ["removed_case"]
    assert "Compared With Previous Report" in (report_dir / "airp_benchmark.md").read_text(encoding="utf-8")
