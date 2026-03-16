"""Parsers for raw alignment output files."""

from __future__ import annotations

import csv
from pathlib import Path

from modules.alignment.base import CandidateHit


def parse_diamond_tsv(tsv_path: str, max_hits: int | None = None) -> list[CandidateHit]:
    """Parse DIAMOND outfmt 6 TSV into CandidateHit records."""

    path = Path(tsv_path)
    if not path.exists() or path.stat().st_size == 0:
        return []

    hits: list[CandidateHit] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if len(row) < 12:
                continue

            query_id = row[0]
            subject_id = row[1]
            identity_pct = float(row[2])
            e_value = float(row[10])
            bit_score = float(row[11])

            hits.append(
                CandidateHit(
                    gene_id=query_id,
                    identity_pct=identity_pct,
                    e_value=e_value,
                    alignment_score=bit_score,
                    raw_subject_id=subject_id,
                )
            )

            if max_hits is not None and len(hits) >= max_hits:
                break

    return hits
