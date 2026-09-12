"""Run a sample benchmark using bundled truth and prediction fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from modules.benchmarking.evaluator import evaluate_predictions, save_benchmark_report


def _load_bool_map(path: Path) -> dict[str, bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return {str(key): bool(value) for key, value in payload.items()}


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    truth_path = project_root / "data" / "benchmark" / "sample_truth.json"
    prediction_path = project_root / "data" / "benchmark" / "sample_predictions.json"

    truth_by_gene = _load_bool_map(truth_path)
    predicted_by_gene = _load_bool_map(prediction_path)

    result = evaluate_predictions(
        truth_by_gene=truth_by_gene,
        predicted_by_gene=predicted_by_gene,
    )

    output_path = save_benchmark_report(
        output_path=str(project_root / "outputs" / "benchmark" / "sample_metrics.json"),
        dataset_name="sample-benchmark",
        baseline_name="card-baseline",
        result=result,
    )

    print(f"Sample benchmark complete. Metrics written to: {output_path}")
    print(
        "precision={:.3f} recall={:.3f} f1={:.3f}".format(
            result.precision,
            result.recall,
            result.f1_score,
        )
    )


if __name__ == "__main__":
    main()
