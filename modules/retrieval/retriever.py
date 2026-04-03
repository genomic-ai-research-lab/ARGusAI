"""Retriever orchestration for candidate hits against CARD context."""

from __future__ import annotations

from modules.alignment.base import CandidateHit
from modules.retrieval.card_client import CardClient
from modules.retrieval.ontology_parser import GeneContext, parse_gene_context


class CardRetriever:
    """Retrieves and normalizes CARD context for candidate hits."""

    def __init__(self, client: CardClient) -> None:
        self.client = client

    def retrieve(self, hits: list[CandidateHit]) -> dict[str, GeneContext]:
        contexts: dict[str, GeneContext] = {}
        for hit in hits:
            context_key = _context_key(hit)
            if context_key in contexts:
                continue

            record = self.client.find_best_record(query_gene=hit.gene_id, subject_id=hit.raw_subject_id)
            if record is None:
                contexts[context_key] = GeneContext(
                    gene_id=hit.gene_id,
                    aro_accession="unknown",
                    description="No CARD ontology context found for this hit.",
                    resistance_mechanism="unknown",
                    drug_classes=[],
                    antibiotics=[],
                )
                continue

            contexts[context_key] = parse_gene_context(record)

        return contexts


def _context_key(hit: CandidateHit) -> str:
    return hit.raw_subject_id or hit.gene_id
