"""Prompt builder that combines alignment hits and retrieval context."""

from __future__ import annotations

from modules.alignment.base import CandidateHit
from modules.prompt_engineering.templates import BATCH_VALIDATION_PROMPT, SYSTEM_PROMPT, VALIDATION_PROMPT
from modules.retrieval.ontology_parser import GeneContext


def build_validation_prompts(hit: CandidateHit, context: GeneContext) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) pair for validation."""

    user_prompt = VALIDATION_PROMPT.format(
        query_id=hit.query_id,
        gene_id=hit.gene_id,
        identity_pct=f"{hit.identity_pct:.2f}",
        query_coverage=f"{hit.query_coverage:.2f}",
        subject_coverage=f"{hit.subject_coverage:.2f}",
        e_value=hit.e_value,
        alignment_score=f"{hit.alignment_score:.2f}",
        alignment_length=hit.alignment_length,
        query_length=hit.query_length,
        subject_length=hit.subject_length,
        raw_subject_id=hit.raw_subject_id,
        description=context.description,
        resistance_mechanism=context.resistance_mechanism,
        drug_classes=", ".join(context.drug_classes) if context.drug_classes else "unknown",
        antibiotics=", ".join(context.antibiotics) if context.antibiotics else "unknown",
        similar_contexts=" | ".join(context.similar_contexts[:5]) if context.similar_contexts else "none",
    )
    return SYSTEM_PROMPT, user_prompt


def build_batch_validation_prompts(items: list[tuple[CandidateHit, GeneContext]]) -> tuple[str, str]:
    """Return one prompt for validating a group of candidate hits."""

    entries: list[str] = []
    for idx, (hit, context) in enumerate(items, start=1):
        entries.append(
            (
                f"[{idx}] query_id={hit.query_id}; gene_id={hit.gene_id}; raw_subject_id={hit.raw_subject_id}; "
                f"identity_pct={hit.identity_pct:.2f}; query_coverage={hit.query_coverage:.2f}; "
                f"subject_coverage={hit.subject_coverage:.2f}; "
                f"e_value={hit.e_value}; alignment_score={hit.alignment_score:.2f}; "
                f"alignment_length={hit.alignment_length}; query_length={hit.query_length}; "
                f"subject_length={hit.subject_length}; "
                f"description={context.description}; resistance_mechanism={context.resistance_mechanism}; "
                f"drug_classes={', '.join(context.drug_classes) if context.drug_classes else 'unknown'}; "
                f"antibiotics={', '.join(context.antibiotics) if context.antibiotics else 'unknown'}; "
                f"similar_contexts={' | '.join(context.similar_contexts[:5]) if context.similar_contexts else 'none'}"
            )
        )

    return SYSTEM_PROMPT, BATCH_VALIDATION_PROMPT.format(entries="\n".join(entries))
