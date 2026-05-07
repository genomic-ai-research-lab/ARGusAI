"""Parsers for raw alignment output files."""

from __future__ import annotations

import csv
from pathlib import Path
import re

from modules.alignment.base import CandidateHit

ARO_PATTERN = re.compile(r"ARO:(\d+)")


def parse_diamond_tsv(
    tsv_path: str,
    max_hits: int | None = None,
    program: str | None = None,
) -> list[CandidateHit]:
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
            query_length = int(float(row[12]))
            subject_length = int(float(row[13]))

            query_coverage = 0.0
            if query_length > 0:
                length_for_cov = query_length
                if program and program.lower().startswith("blastx"):
                    # blastx reports query length in nucleotides; alignment length is in amino acids.
                    length_for_cov = max(1, query_length // 3)
                query_coverage = min(100.0, (alignment_length / length_for_cov) * 100.0)

            subject_coverage = 0.0
            if subject_length > 0:
                subject_coverage = min(100.0, (alignment_length / subject_length) * 100.0)

            subject_gene = _extract_subject_gene(subject_id)

            hits.append(
                CandidateHit(
                    gene_id=subject_gene or query_id,
                    identity_pct=identity_pct,
                    e_value=e_value,
                    alignment_score=bit_score,
                    alignment_length=alignment_length,
                    query_length=query_length,
                    subject_length=subject_length,
                    query_coverage=query_coverage,
                    subject_coverage=subject_coverage,
                    raw_subject_id=subject_id,
                    aro_accession=_extract_aro_accession(subject_id),
                    validation_pathway=["alignment"],
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


def _extract_aro_accession(subject_id: str) -> str | None:
    match = ARO_PATTERN.search(subject_id)
    if not match:
        return None
    return f"ARO:{match.group(1)}"
