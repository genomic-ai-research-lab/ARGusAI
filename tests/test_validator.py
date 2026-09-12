from __future__ import annotations

import json
import time

from modules.alignment.base import CandidateHit
from modules.llm_reasoning.base import LLMProvider
from modules.llm_reasoning.validator import LLMValidator
from modules.retrieval.ontology_parser import GeneContext


class InvalidJsonProvider(LLMProvider):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return "this is not json"


class BatchJsonProvider(LLMProvider):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = [
            {
                "gene_id": "geneA",
                "raw_subject_id": "subA",
                "is_valid_hit": True,
                "confidence": 88,
                "reasoning": "Strong direct mechanism evidence.",
                "resistance_summary": "Likely ARG.",
                "drug_impacts": ["beta-lactam"],
                "limitations_and_fixes": "No major issues.",
            },
            {
                "gene_id": "geneB",
                "raw_subject_id": "subB",
                "is_valid_hit": False,
                "confidence": 34,
                "reasoning": "Weak mechanism evidence.",
                "resistance_summary": "Not a confident ARG.",
                "drug_impacts": [],
                "limitations_and_fixes": "Need better context.",
            },
        ]
        return json.dumps(payload)


class SlowProvider(LLMProvider):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        time.sleep(1.2)
        return "{}"


def _hit(gene_id: str, subject_id: str) -> CandidateHit:
    return CandidateHit(
        gene_id=gene_id,
        identity_pct=86.0,
        e_value=1e-20,
        alignment_score=120.0,
        alignment_length=410,
        query_length=500,
        subject_length=500,
        query_coverage=82.0,
        subject_coverage=82.0,
        raw_subject_id=subject_id,
        aro_accession="ARO:3000001",
        validation_pathway=["alignment"],
    )


def _context(gene_id: str) -> GeneContext:
    return GeneContext(
        gene_id=gene_id,
        aro_accession="ARO:3000001",
        description="Test description",
        resistance_mechanism="efflux",
        drug_classes=["beta-lactam"],
        antibiotics=["amoxicillin"],
        similar_contexts=["similar entry 1"],
    )


def test_single_validation_falls_back_on_invalid_json() -> None:
    validator = LLMValidator(provider=InvalidJsonProvider())

    hit = _hit("geneA", "subA")
    context = _context("geneA")

    result = validator.validate(hit, context, "system", "user")

    assert result.gene_id == "geneA"
    assert result.raw_subject_id == "subA"
    assert result.llm_confidence >= 0
    assert "Fallback heuristic used" in result.reasoning


def test_batch_validation_parses_json_array() -> None:
    validator = LLMValidator(provider=BatchJsonProvider())

    items = [(_hit("geneA", "subA"), _context("geneA")), (_hit("geneB", "subB"), _context("geneB"))]
    results = validator.validate_batch(items, "system", "user")

    assert len(results) == 2

    first = next(item for item in results if item.gene_id == "geneA")
    second = next(item for item in results if item.gene_id == "geneB")

    assert first.is_valid_hit is True
    assert first.llm_confidence == 88
    assert second.is_valid_hit is False
    assert second.llm_confidence == 34


def test_single_validation_falls_back_on_timeout() -> None:
    validator = LLMValidator(provider=SlowProvider())
    validator.request_timeout_seconds = 1

    hit = _hit("geneA", "subA")
    context = _context("geneA")

    result = validator.validate(hit, context, "system", "user")

    assert result.gene_id == "geneA"
    assert "Fallback heuristic used" in result.reasoning
