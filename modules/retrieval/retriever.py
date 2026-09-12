"""Retriever orchestration for candidate hits against CARD context."""

from __future__ import annotations

import asyncio

from config import settings
from modules.alignment.base import CandidateHit
from modules.retrieval.card_client import CardClient
from modules.retrieval.ontology_parser import GeneContext, parse_gene_context
from modules.retrieval.vector_store import VectorContextStore


class CardRetriever:
    """Retrieves and normalizes CARD context for candidate hits."""

    def __init__(self, client: CardClient) -> None:
        self.client = client
        self._vector_store = VectorContextStore(client.records)

    def retrieve(self, hits: list[CandidateHit]) -> dict[str, GeneContext]:
        unique_hits: list[CandidateHit] = []
        seen: set[str] = set()
        for hit in hits:
            key = _context_key(hit)
            if key in seen:
                continue
            seen.add(key)
            unique_hits.append(hit)

        # 1. Find best records synchronously (it's fast enough in a single thread, avoiding GIL thrash)
        records = []
        queries_for_vector = []
        for hit in unique_hits:
            record, retrieval_method = self.client.find_best_record(
                query_gene=hit.gene_id,
                subject_id=hit.raw_subject_id,
                aro_accession=hit.aro_accession,
            )
            records.append((hit, record, retrieval_method))
            if record:
                description = (record.get("Description") or "").strip()
                queries_for_vector.append(f"{hit.gene_id} {hit.raw_subject_id} {description}")

        # 2. Batch query ChromaDB
        similar_contexts_list = []
        if queries_for_vector:
            similar_contexts_list = self._vector_store.query_batch(queries_for_vector, top_k=3)

        # 3. Assemble results
        results = {}
        vector_idx = 0
        for hit, record, retrieval_method in records:
            context_key = _context_key(hit)
            if record is None:
                results[context_key] = GeneContext(
                    gene_id=hit.gene_id,
                    aro_accession="unknown",
                    description="No CARD ontology context found for this hit.",
                    resistance_mechanism="unknown",
                    drug_classes=[],
                    antibiotics=[],
                    similar_contexts=[],
                    retrieval_method=retrieval_method,
                )
            else:
                similar_contexts = similar_contexts_list[vector_idx] if vector_idx < len(similar_contexts_list) else []
                vector_idx += 1
                results[context_key] = parse_gene_context(
                    record,
                    similar_contexts=similar_contexts,
                    retrieval_method=retrieval_method,
                )

        return results


def _context_key(hit: CandidateHit) -> str:
    return hit.raw_subject_id or hit.gene_id


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # If already in an event loop, run in a worker thread.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()
