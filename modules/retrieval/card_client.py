"""Local CARD knowledge lookup client used by retrieval module."""

from __future__ import annotations

import csv
from pathlib import Path
import re


class CardClient:
    """Load and query local CARD ontology TSV data."""

    def __init__(self, ontology_tsv_path: str) -> None:
        self.ontology_tsv_path = ontology_tsv_path
        self._records = self._load_records(ontology_tsv_path)
        self._cache: dict[tuple[str, str, str], tuple[dict[str, str] | None, str]] = {}

    @property
    def records(self) -> list[dict[str, str]]:
        return self._records

    @staticmethod
    def _load_records(path: str) -> list[dict[str, str]]:
        tsv_path = Path(path)
        if not tsv_path.exists():
            return []

        with tsv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            return [dict(row) for row in reader]

    def find_best_record(
        self,
        query_gene: str,
        subject_id: str,
        aro_accession: str | None = None,
    ) -> tuple[dict[str, str] | None, str]:
        """Find best matching CARD ontology row for a query gene and subject id."""

        query_norm = _normalize_gene(query_gene)
        subject_norm = _normalize_gene(subject_id)
        cache_key = (query_norm, subject_norm, aro_accession or "")
        if cache_key in self._cache:
            return self._cache[cache_key]

        if aro_accession:
            for row in self._records:
                if (row.get("Accession") or "").strip() == aro_accession:
                    self._cache[cache_key] = (row, "retrieval_aro_exact")
                    return row, "retrieval_aro_exact"

        if subject_norm:
            for row in self._records:
                name_norm = _normalize_gene(row.get("Name", ""))
                short_norm = _normalize_gene(row.get("CARD Short Name", ""))
                if subject_norm in {name_norm, short_norm}:
                    self._cache[cache_key] = (row, "retrieval_lexical_subject")
                    return row, "retrieval_lexical_subject"

        if query_norm:
            for row in self._records:
                name_norm = _normalize_gene(row.get("Name", ""))
                short_norm = _normalize_gene(row.get("CARD Short Name", ""))
                if query_norm in {name_norm, short_norm}:
                    self._cache[cache_key] = (row, "retrieval_lexical_query")
                    return row, "retrieval_lexical_query"

        self._cache[cache_key] = (None, "retrieval_missing")
        return None, "retrieval_missing"


def _normalize_gene(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = cleaned.split("|")[-1]
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9()'+-]", "", cleaned)
    return cleaned
