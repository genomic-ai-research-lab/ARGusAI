"""Parsers for raw alignment output files."""

from __future__ import annotations

import csv
from pathlib import Path
import re

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
            if len(row) < 14:
                continue

            query_id = row[0]
            subject_id = row[1]
            identity_pct = float(row[2])
            alignment_length = int(float(row[3]))
            e_value = float(row[10])
            bit_score = float(row[11])
            subject_length = int(float(row[13]))

            coverage_pct = 0.0
            if subject_length > 0:
                coverage_pct = min(100.0, (alignment_length / subject_length) * 100.0)

            subject_gene = _extract_subject_gene(subject_id)

            hits.append(
                CandidateHit(
                    gene_id=subject_gene or query_id,
                    identity_pct=identity_pct,
                    e_value=e_value,
                    alignment_score=bit_score,
                    coverage_pct=coverage_pct,
                    alignment_length=alignment_length,
                    subject_length=subject_length,
                    raw_subject_id=subject_id,
                )
            )

            if max_hits is not None and len(hits) >= max_hits:
                break

    return hits


def _extract_subject_gene(subject_id: str) -> str:
    parts = [part.strip() for part in subject_id.split("|") if part.strip()]
    if not parts:
        return ""

    for part in reversed(parts):
        if re.match(r"^ARO:\d+", part):
            continue
        if re.match(r"^[A-Za-z]{1,3}_?\d+(?:\.\d+)?$", part):
            continue
        return part

    return parts[-1]
