"""BLAST runner placeholder for modular compatibility."""

from __future__ import annotations

from modules.alignment.base import AlignmentTool, CandidateHit


class BlastRunner(AlignmentTool):
    """Stub implementation to preserve swappable tool architecture."""

    def run(self, fasta_path: str) -> list[CandidateHit]:
        raise NotImplementedError("BLAST runner is not implemented in the alignment-only milestone.")
