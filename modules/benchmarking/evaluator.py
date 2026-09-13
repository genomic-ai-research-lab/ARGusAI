"""Benchmark metrics utilities for ARG model validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass
class BenchmarkResult:
    """Stores confusion counts and derived quality metrics."""

    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: float
    recall: float
    f1_score: float


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def evaluate_predictions(
    *,
    truth_by_gene: dict[str, bool],
    predicted_by_gene: dict[str, bool],
) -> BenchmarkResult:
    """Compute precision, recall, and F1 from truth/prediction mappings."""

    genes = set(truth_by_gene) | set(predicted_by_gene)
    tp = fp = fn = tn = 0

    for gene in genes:
        truth = bool(truth_by_gene.get(gene, False))
        predicted = bool(predicted_by_gene.get(gene, False))

        if predicted and truth:
            tp += 1
        elif predicted and not truth:
            fp += 1
        elif not predicted and truth:
            fn += 1
        else:
            tn += 1

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1_score = _safe_div(2 * (precision * recall), precision + recall)

    return BenchmarkResult(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1_score=round(f1_score, 6),
    )


def save_benchmark_report(
    *,
    output_path: str,
    dataset_name: str,
    baseline_name: str,
    result: BenchmarkResult,
) -> str:
    """Persist benchmark metrics in JSON format."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": dataset_name,
            "baseline": baseline_name,
        },
        "metrics": asdict(result),
    }

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)
