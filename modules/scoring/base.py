"""Deterministic biological scoring for alignment candidates."""

from __future__ import annotations

from dataclasses import dataclass
import math

from config import settings
from modules.alignment.base import CandidateHit
from modules.scoring.calibration import apply_calibration


@dataclass
class ScoredHit:
    """Alignment candidate paired with deterministic confidence values."""

    candidate: CandidateHit
    alignment_confidence: float


def _alignment_terms(hit: CandidateHit) -> tuple[float, float, float, float]:
    id_term = max(0.0, min(hit.identity_pct, 100.0)) / 100.0
    scov_term = max(0.0, min(hit.subject_coverage, 100.0)) / 100.0

    e_value = max(hit.e_value, 0.0)
    eval_term = min(40.0, -math.log10(e_value + 1e-300)) / 40.0

    w_id = settings.ALIGN_SCORE_IDENTITY_WEIGHT
    w_scov = settings.ALIGN_SCORE_SCOV_WEIGHT
    w_eval = settings.ALIGN_SCORE_EVALUE_WEIGHT
    raw = (w_id * id_term) + (w_scov * scov_term) + (w_eval * eval_term)

    return raw, id_term, scov_term, eval_term


def _raw_alignment_confidence(hit: CandidateHit) -> float:
    """Compute raw confidence using weighted linear terms.

    raw = w_id * identity_pct + w_scov * subject_coverage + w_eval * eval_term
    """

    raw, _, _, _ = _alignment_terms(hit)
    return raw


def compute_alignment_confidence(hit: CandidateHit) -> float:
    raw, _, _, _ = _alignment_terms(hit)
    bounded = max(0.0, min(raw, 1.0))
    return apply_calibration(bounded * 100.0)


def score_hits(hits: list[CandidateHit]) -> list[ScoredHit]:
    """Return scored hits with normalized alignment confidence in [0, 100]."""

    if not hits:
        return []

    scored: list[ScoredHit] = []
    for hit in hits:
        calibrated = compute_alignment_confidence(hit)
        scored.append(ScoredHit(candidate=hit, alignment_confidence=round(calibrated, 2)))

    return scored
