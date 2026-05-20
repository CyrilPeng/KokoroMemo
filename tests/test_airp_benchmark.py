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
