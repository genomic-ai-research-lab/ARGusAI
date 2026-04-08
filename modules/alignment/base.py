"""Abstract base interfaces for alignment tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CandidateHit:
    """Normalized candidate hit returned by any alignment tool."""

    gene_id: str
    identity_pct: float
    e_value: float
    alignment_score: float
    coverage_pct: float
    alignment_length: int
    subject_length: int
    raw_subject_id: str


class AlignmentTool(ABC):
    """Contract for alignment tool implementations."""

    @abstractmethod
    def run(self, fasta_path: str) -> list[CandidateHit]:
        """Run alignment and return parsed candidate hits."""
