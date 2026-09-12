from __future__ import annotations

from pathlib import Path

from scripts.run_sample_benchmark import main


def test_sample_benchmark_script_generates_metrics_file() -> None:
    output_path = Path("outputs/benchmark/sample_metrics.json")
    if output_path.exists():
        output_path.unlink()

    main()

    assert output_path.exists()
    payload = output_path.read_text(encoding="utf-8")
    assert "precision" in payload
    assert "recall" in payload
    assert "f1_score" in payload
