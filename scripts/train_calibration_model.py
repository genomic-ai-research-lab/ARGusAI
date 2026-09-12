"""Train a Platt-scaling calibration model for alignment confidence."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from modules.alignment.base import CandidateHit
from modules.scoring.base import _raw_alignment_confidence  # noqa: SLF001 - training helper


@dataclass
class _Sample:
    identity_pct: float
    query_coverage: float
    subject_coverage: float
    e_value: float
    label: int
    gene_id: str
    raw_subject_id: str
    aro_accession: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train alignment confidence calibration model")
    parser.add_argument("--dataset", required=True, help="CSV with identity_pct, query_coverage, subject_coverage, e_value, label")
    parser.add_argument("--output", required=True, help="Path to write calibration JSON")
    parser.add_argument("--exclude-accessions", help="Optional file with ARO accessions to exclude")
    parser.add_argument("--min-samples", type=int, default=500)
    parser.add_argument("--min-bin-samples", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=0.15)
    parser.add_argument("--epochs", type=int, default=1200)
    return parser.parse_args()


def _load_samples(path: str) -> list[_Sample]:
    rows: list[_Sample] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                _Sample(
                    identity_pct=float(row.get("identity_pct", 0.0)),
                    query_coverage=float(row.get("query_coverage", 0.0)),
                    subject_coverage=float(row.get("subject_coverage", 0.0)),
                    e_value=float(row.get("e_value", 1.0)),
                    label=int(float(row.get("label", 0))),
                    gene_id=str(row.get("gene_id", "sample")),
                    raw_subject_id=str(row.get("raw_subject_id", "")),
                    aro_accession=str(row.get("aro_accession", "")),
                )
            )
    return rows


def _quality_gates(samples: list[_Sample], min_samples: int, min_bin_samples: int) -> None:
    if len(samples) < min_samples:
        raise ValueError(f"Need at least {min_samples} samples, got {len(samples)}")

    positives = sum(1 for sample in samples if sample.label == 1)
    negatives = sum(1 for sample in samples if sample.label == 0)
    if positives == 0 or negatives == 0:
        raise ValueError("Dataset must include both positive and negative samples")

    min_balance = int(len(samples) * 0.3)
    if positives < min_balance or negatives < min_balance:
        raise ValueError("Dataset must be reasonably balanced across positives/negatives")

    bins = {
        "40-60": 0,
        "60-80": 0,
        "80-90": 0,
        "90-100": 0,
    }
    for sample in samples:
        pct = sample.identity_pct
        if 40 <= pct < 60:
            bins["40-60"] += 1
        elif 60 <= pct < 80:
            bins["60-80"] += 1
        elif 80 <= pct < 90:
            bins["80-90"] += 1
        elif 90 <= pct <= 100:
            bins["90-100"] += 1

    missing_bins = [name for name, count in bins.items() if count < min_bin_samples]
    if missing_bins:
        missing = ", ".join(missing_bins)
        raise ValueError(f"Identity bins below minimum samples ({min_bin_samples}): {missing}")


def _load_exclusions(path: str | None) -> set[str]:
    if not path:
        return set()
    entries = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value:
            entries.add(value)
    return entries


def _apply_exclusions(samples: list[_Sample], excluded: set[str]) -> list[_Sample]:
    if not excluded:
        return samples
    filtered = [sample for sample in samples if sample.aro_accession not in excluded]
    if len(filtered) != len(samples):
        removed = len(samples) - len(filtered)
        raise ValueError(f"Excluded {removed} samples due to ARO leakage")
    return filtered


def _compute_alignment_scores(samples: list[_Sample]) -> list[float]:
    hits = [
        CandidateHit(
            gene_id=sample.gene_id,
            identity_pct=sample.identity_pct,
            e_value=sample.e_value,
            alignment_score=0.0,
            alignment_length=0,
            query_length=0,
            subject_length=0,
            query_coverage=sample.query_coverage,
            subject_coverage=sample.subject_coverage,
            raw_subject_id=sample.raw_subject_id,
            aro_accession=sample.aro_accession,
            validation_pathway=["alignment"],
        )
        for sample in samples
    ]

    raw_scores = [_raw_alignment_confidence(hit) for hit in hits]
    min_score = min(raw_scores)
    max_score = max(raw_scores)

    normalized: list[float] = []
    for raw in raw_scores:
        if max_score == min_score:
            normalized.append(1.0 if raw > 0 else 0.0)
        else:
            normalized.append((raw - min_score) / (max_score - min_score))
    return normalized


def _train_platt(scores: list[float], labels: list[int], lr: float, epochs: int) -> tuple[float, float]:
    a = 0.0
    b = 0.0
    last_loss = None
    patience = 0

    for _ in range(epochs):
        grad_a = 0.0
        grad_b = 0.0
        loss = 0.0

        for x, y in zip(scores, labels, strict=False):
            z = a + b * x
            p = 1.0 / (1.0 + math.exp(-z))
            p = min(max(p, 1e-6), 1.0 - 1e-6)
            loss += -(y * math.log(p) + (1 - y) * math.log(1 - p))
            grad_a += p - y
            grad_b += (p - y) * x

        n = max(len(scores), 1)
        grad_a /= n
        grad_b /= n
        loss /= n

        a -= lr * grad_a
        b -= lr * grad_b

        if last_loss is not None and abs(last_loss - loss) < 1e-6:
            patience += 1
            if patience >= 10:
                break
        else:
            patience = 0
        last_loss = loss

    return a, b


def main() -> None:
    args = _parse_args()

    samples = _load_samples(args.dataset)
    samples = _apply_exclusions(samples, _load_exclusions(args.exclude_accessions))
    _quality_gates(samples, args.min_samples, args.min_bin_samples)

    scores = _compute_alignment_scores(samples)
    labels = [sample.label for sample in samples]

    a, b = _train_platt(scores, labels, lr=args.learning_rate, epochs=args.epochs)

    output = {
        "type": "platt",
        "a": a,
        "b": b,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(args.dataset),
            "samples": len(samples),
            "positives": sum(labels),
            "negatives": len(labels) - sum(labels),
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
