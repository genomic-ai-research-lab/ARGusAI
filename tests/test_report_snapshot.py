from __future__ import annotations

import json
from pathlib import Path

from modules.report_generation.json_formatter import build_json_report


def test_json_report_matches_snapshot() -> None:
    hits = [
        {
            "gene_id": "geneA",
            "identity_pct": 92.4,
            "e_value": 1e-20,
            "alignment_score": 155.0,
            "alignment_confidence": 82.2,
            "llm_confidence": 88.0,
            "final_confidence": 85.68,
            "is_valid_hit": True,
            "reasoning": "Strong evidence",
            "drug_impacts": ["beta-lactam"],
            "query_coverage": 85.1,
            "subject_coverage": 87.0,
            "query_length": 500,
            "subject_length": 500,
        }
    ]

    report = build_json_report(
        fasta_filename="sample.fasta",
        hits=hits,
        filtered_hits=[{"gene_id": "geneA"}],
        total_raw_hits=3,
        benchmark={
            "dataset": "snapshot-dataset",
            "baseline": "card-baseline",
            "metrics": {"precision": 1.0, "recall": 1.0, "f1_score": 1.0},
        },
        run_manifest={
            "pipeline_version": "test",
            "diamond_version": "diamond v2.1.0",
            "card_db": {"path": "card_db.dmnd", "sha256": "test"},
            "aro_tsv": {"path": "card-ontology/aro.tsv", "sha256": "test"},
            "calibration_model": {"path": "", "sha256": "missing"},
            "llm_provider": "gemini",
            "llm_model": "gemini-1.5-flash",
            "thresholds": {
                "identity": 40.0,
                "query_coverage": 70.0,
                "subject_coverage": 70.0,
                "filter_evalue": 1e-5,
                "final_confidence": 70.0,
            },
            "timestamp": "<timestamp>",
        },
    )

    report["metadata"]["generated_at"] = "<timestamp>"

    snapshot_path = Path(__file__).parent / "snapshots" / "report_snapshot.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert report == expected
