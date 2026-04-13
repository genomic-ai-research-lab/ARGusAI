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

        async def _retrieve_one(hit: CandidateHit) -> tuple[str, GeneContext]:
            context_key = _context_key(hit)
            record = await asyncio.to_thread(
                self.client.find_best_record,
                query_gene=hit.gene_id,
                subject_id=hit.raw_subject_id,
            )

            if record is None:
                return (
                    context_key,
                    GeneContext(
                        gene_id=hit.gene_id,
                        aro_accession="unknown",
                        description="No CARD ontology context found for this hit.",
                        resistance_mechanism="unknown",
                        drug_classes=[],
                        antibiotics=[],
                        similar_contexts=[],
                    ),
                )

            description = (record.get("Description") or "").strip()
            similar_contexts = await asyncio.to_thread(
                self._vector_store.query,
                query_text=f"{hit.gene_id} {hit.raw_subject_id} {description}",
                top_k=3,
            )
            return context_key, parse_gene_context(record, similar_contexts=similar_contexts)

        async def _retrieve_all() -> list[tuple[str, GeneContext]]:
            semaphore = asyncio.Semaphore(max(1, settings.RETRIEVAL_PARALLELISM))

            async def _guarded(hit: CandidateHit) -> tuple[str, GeneContext]:
                async with semaphore:
                    return await _retrieve_one(hit)

            tasks = [_guarded(hit) for hit in unique_hits]
            return await asyncio.gather(*tasks)

        results = _run_async(_retrieve_all())
        return {key: value for key, value in results}


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
