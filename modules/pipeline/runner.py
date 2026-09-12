"""Pipeline runner composed from explicit stage classes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib import import_module
import logging
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from config import settings
from modules.alignment.base import CandidateHit
from modules.alignment.diamond_runner import DiamondRunner
from modules.llm_reasoning.base import ValidationResult
from modules.retrieval.ontology_parser import GeneContext
from modules.scoring.base import ScoredHit, score_hits

logger = logging.getLogger(__name__)


def _validation_key(gene_id: str, raw_subject_id: str) -> str:
    return f"{gene_id}::{raw_subject_id}"


def _validation_class(final_confidence: float) -> str:
    if final_confidence >= 85:
        return "Confirmed ARG"
    if final_confidence >= settings.FINAL_CONFIDENCE_THRESHOLD:
        return "Probable ARG"
    if final_confidence >= 50:
        return "Review Required"
    return "Unlikely ARG"


def _downgrade_class(label: str) -> str:
    order = ["Confirmed ARG", "Probable ARG", "Review Required", "Unlikely ARG"]
    try:
        idx = order.index(label)
    except ValueError:
        return label
    return order[min(idx + 1, len(order) - 1)]


def _normalize_gene_family(gene_name: str) -> str:
    name = (gene_name or "").strip().lower()
    name = re.sub(r"^[a-z]{2,6}_", "", name)
    name = re.sub(r"\d+$", "", name)
    name = re.sub(r"[^a-z]", "", name)
    return name or (gene_name or "").strip().lower()


def _dedupe_by_family(hits: list[dict[str, object]]) -> list[dict[str, object]]:
    if not hits:
        return hits

    grouped: dict[str, list[tuple[int, dict[str, object]]]] = {}
    for idx, hit in enumerate(hits):
        raw_subject_id = str(hit.get("raw_subject_id", "") or "")
        if "|" in raw_subject_id:
            gene_name = raw_subject_id.split("|")[-1]
        else:
            gene_name = str(hit.get("gene_id", ""))
        family = _normalize_gene_family(gene_name)
        grouped.setdefault(family, []).append((idx, hit))

    deduped: list[tuple[int, dict[str, object]]] = []
    for family, items in grouped.items():
        if len(items) == 1:
            deduped.append(items[0])
            continue

        best_idx, best_hit = max(
            items,
            key=lambda pair: float(pair[1].get("alignment_score", 0.0) or 0.0),
        )
        alternatives = [item for _, item in items if item is not best_hit]
        best_hit["alternatives"] = alternatives
        best_hit["family_key"] = family
        deduped.append((best_idx, best_hit))

    return [item for _, item in sorted(deduped, key=lambda pair: pair[0])]


def _weighted_final_confidence(alignment_confidence: float, llm_confidence: float) -> float:
    weight_alignment = max(0.0, settings.ALIGNMENT_CONFIDENCE_WEIGHT)
    weight_llm = max(0.0, settings.LLM_CONFIDENCE_WEIGHT)
    total = weight_alignment + weight_llm
    if total <= 0:
        return alignment_confidence
    return (alignment_confidence * weight_alignment + llm_confidence * weight_llm) / total


@dataclass
class PipelineResult:
    """End-to-end pipeline output for one job."""

    hits: list[dict[str, object]]
    report: dict[str, object]
    text_summary: str


@dataclass
class PipelineData:
    """Mutable data container passed through pipeline stages."""

    fasta_path: str
    fasta_filename: str
    evalue: float
    program: str
    run_id: str | None = None
    raw_hits: list[CandidateHit] = field(default_factory=list)
    filtered_hits: list[CandidateHit] = field(default_factory=list)
    scored_hits: list[ScoredHit] = field(default_factory=list)
    contexts: dict[str, GeneContext] = field(default_factory=dict)
    validations: list[ValidationResult] = field(default_factory=list)
    serialized_hits: list[dict[str, object]] = field(default_factory=list)
    report: dict[str, object] = field(default_factory=dict)
    text_summary: str = ""
    benchmark: dict[str, object] | None = None
    run_manifest: dict[str, object] | None = None


class PipelineStage:
    """Base class for execution stages."""

    name = "stage"

    def run(self, data: PipelineData) -> PipelineData:
        raise NotImplementedError


class AlignmentStage(PipelineStage):
    name = "alignment"

    def run(self, data: PipelineData) -> PipelineData:
        runner = DiamondRunner(
            database_path=settings.DIAMOND_DB_PATH,
            threads=settings.DIAMOND_THREADS,
            evalue=data.evalue,
            program=data.program,
            max_hits=settings.MAX_HITS,
        )
        data.raw_hits = runner.run(data.fasta_path)
        for hit in data.raw_hits:
            if not hit.validation_pathway:
                hit.validation_pathway = ["alignment"]
        return data


class ScoringStage(PipelineStage):
    name = "scoring"

    def run(self, data: PipelineData) -> PipelineData:
        is_blastx = data.program.lower().startswith("blastx")
        if data.raw_hits:
            if is_blastx:
                aln_values = [hit.alignment_length for hit in data.raw_hits]
                logger.info(
                    "Pre-filter alignment length stats (aa): min=%d max=%d",
                    min(aln_values),
                    max(aln_values),
                )
            else:
                qcov_values = [hit.query_coverage for hit in data.raw_hits]
                logger.info(
                    "Pre-filter qcov stats: min=%.2f max=%.2f",
                    min(qcov_values),
                    max(qcov_values),
                )
        fail_counts = {"identity": 0, "scov": 0, "evalue": 0, "aln_len": 0}
        if not is_blastx:
            fail_counts["qcov"] = 0
        for hit in data.raw_hits:
            if hit.identity_pct < settings.IDENTITY_THRESHOLD:
                fail_counts["identity"] += 1
            if is_blastx:
                if hit.alignment_length < settings.MIN_ALIGNMENT_AA:
                    fail_counts["aln_len"] += 1
            elif hit.query_coverage < settings.QUERY_COVERAGE_THRESHOLD:
                fail_counts["qcov"] += 1
            if hit.subject_coverage < settings.SUBJECT_COVERAGE_THRESHOLD:
                fail_counts["scov"] += 1
            if hit.e_value > settings.FILTER_EVALUE_THRESHOLD:
                fail_counts["evalue"] += 1
        logger.info("Pre-filter failure counts: %s", fail_counts)

        data.filtered_hits = [
            hit
            for hit in data.raw_hits
            if hit.identity_pct >= settings.IDENTITY_THRESHOLD
            and (
                hit.alignment_length >= settings.MIN_ALIGNMENT_AA
                if is_blastx
                else hit.query_coverage >= settings.QUERY_COVERAGE_THRESHOLD
            )
            and hit.subject_coverage >= settings.SUBJECT_COVERAGE_THRESHOLD
            and hit.e_value <= settings.FILTER_EVALUE_THRESHOLD
        ]
        for hit in data.filtered_hits:
            hit.validation_pathway.append("scoring")
        data.scored_hits = score_hits(data.filtered_hits)
        return data


class RetrievalStage(PipelineStage):
    name = "retrieval"

    def __init__(self, retriever: Any) -> None:
        self._retriever = retriever

    def run(self, data: PipelineData) -> PipelineData:
        if self._retriever is None or not data.scored_hits:
            return data

        data.contexts = self._retriever.retrieve([item.candidate for item in data.scored_hits])
        for scored_hit in data.scored_hits:
            hit = scored_hit.candidate
            context = data.contexts.get(hit.raw_subject_id or hit.gene_id)
            if context and context.retrieval_method:
                hit.validation_pathway.append(context.retrieval_method)
            else:
                hit.validation_pathway.append("retrieval_missing")
        return data


class ReasoningStage(PipelineStage):
    name = "reasoning"

    def __init__(self, validator: Any, prompt_builder: Any, batch_prompt_builder: Any) -> None:
        self._validator = validator
        self._prompt_builder = prompt_builder
        self._batch_prompt_builder = batch_prompt_builder

    def run(self, data: PipelineData) -> PipelineData:
        if self._validator is None or self._prompt_builder is None or not data.scored_hits:
            for scored_hit in data.scored_hits:
                scored_hit.candidate.validation_pathway.append("reasoning_skipped")
            return data

        prepared: list[tuple[CandidateHit, GeneContext]] = []
        for scored_hit in data.scored_hits:
            hit = scored_hit.candidate
            context_key = hit.raw_subject_id or hit.gene_id
            context = data.contexts.get(
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
            prepared.append((hit, context))

        batch_size = max(1, settings.LLM_BATCH_SIZE)
        batches = [prepared[idx : idx + batch_size] for idx in range(0, len(prepared), batch_size)]

        async def _run_batch_validation() -> list[ValidationResult]:
            semaphore = asyncio.Semaphore(max(1, settings.LLM_PARALLELISM))

            async def _guarded(batch):
                async with semaphore:
                    if self._batch_prompt_builder:
                        system_prompt, user_prompt = self._batch_prompt_builder(batch)
                        return await asyncio.to_thread(
                            self._validator.validate_batch,
                            batch,
                            system_prompt,
                            user_prompt,
                        )
                    
                    hit, context = batch[0]
                    system_prompt, user_prompt = self._prompt_builder(hit, context)
                    return await asyncio.to_thread(
                        self._validator.validate,
                        hit,
                        context,
                        system_prompt,
                        user_prompt,
                    )

            tasks = [_guarded(batch) for batch in batches]
            values = await asyncio.gather(*tasks, return_exceptions=True)
            resolved: list[ValidationResult] = []
            for idx, result in enumerate(values):
                if isinstance(result, Exception):
                    logger.warning("Reasoning batch %d failed, using heuristic fallback: %s", idx + 1, result)
                    fallback = [_heuristic_validation_for_pair(item) for item in batches[idx]]
                    resolved.extend(fallback)
                    continue

                if isinstance(result, list):
                    resolved.extend(result)
                    continue

                resolved.append(result)

            return resolved

        validations = _run_async(_run_batch_validation())

        data.validations = validations
        return data


class FusionStage(PipelineStage):
    name = "fusion"

    def run(self, data: PipelineData) -> PipelineData:
        validation_index = {
            _validation_key(item.gene_id, item.raw_subject_id): item for item in data.validations
        }
        serialized: list[dict[str, object]] = []

        for scored_hit in data.scored_hits:
            hit = scored_hit.candidate
            key = _validation_key(hit.gene_id, hit.raw_subject_id)
            validation = validation_index.get(key)
            llm_confidence = validation.llm_confidence if validation else 0.0
            alignment_confidence = scored_hit.alignment_confidence
            if validation and getattr(validation, "arg_class", "") == "decoy":
                final_confidence = 0.0
                validation_class = "Rejected"
            elif llm_confidence < 40.0 and alignment_confidence > 70.0:
                final_confidence = round(alignment_confidence, 2)
                validation_class = _validation_class(final_confidence)
            else:
                final_confidence = round(
                    _weighted_final_confidence(alignment_confidence, llm_confidence),
                    2,
                )
                validation_class = _validation_class(final_confidence)
                
            contradiction_flag = _is_contradiction(
                alignment_confidence=final_confidence,
                validation=validation,
            )
            if contradiction_flag and validation_class != "Rejected":
                validation_class = _downgrade_class(validation_class)
            is_valid_hit = validation_class in {"Confirmed ARG", "Probable ARG"}

            if validation:
                validation.alignment_confidence = alignment_confidence
                validation.final_confidence = final_confidence
                validation.is_valid_hit = is_valid_hit
                hit.validation_pathway.append(_resolve_llm_pathway(validation))

            context = data.contexts.get(hit.raw_subject_id or hit.gene_id)
            hit.validation_pathway.append("fusion")
            serialized.append(
                {
                    "gene_id": hit.gene_id,
                    "identity_pct": hit.identity_pct,
                    "e_value": hit.e_value,
                    "alignment_score": hit.alignment_score,
                    "alignment_length": hit.alignment_length,
                    "query_length": hit.query_length,
                    "subject_length": hit.subject_length,
                    "query_coverage": hit.query_coverage,
                    "subject_coverage": hit.subject_coverage,
                    "raw_subject_id": hit.raw_subject_id,
                    "aro_accession": hit.aro_accession or "unknown",
                    "alignment_confidence": scored_hit.alignment_confidence,
                    "llm_confidence": llm_confidence,
                    "final_confidence": final_confidence,
                    "is_valid_hit": is_valid_hit,
                    "validation_class": validation_class,
                    "contradiction_flag": contradiction_flag,
                    "validation_pathway": list(hit.validation_pathway),
                    "reasoning": validation.reasoning if validation else "No LLM reasoning available.",
                    "resistance_summary": (
                        validation.resistance_summary if validation else "No resistance summary available."
                    ),
                    "drug_impacts": validation.drug_impacts if validation else [],
                    "limitations_and_fixes": (
                        validation.limitations_and_fixes
                        if validation
                        else "No limitations/fixes analysis available."
                    ),
                    "context": {
                        "aro_accession": context.aro_accession if context else "unknown",
                        "description": context.description if context else "",
                        "resistance_mechanism": context.resistance_mechanism if context else "unknown",
                        "drug_classes": context.drug_classes if context else [],
                        "antibiotics": context.antibiotics if context else [],
                        "similar_contexts": context.similar_contexts if context else [],
                        "retrieval_method": context.retrieval_method if context else "unknown",
                    },
                }
            )

        data.serialized_hits = _dedupe_by_family(serialized)
        return data


class ReportingStage(PipelineStage):
    name = "reporting"

    def __init__(self, build_json_report_func: Any, build_text_summary_func: Any) -> None:
        self._build_json_report = build_json_report_func
        self._build_text_summary = build_text_summary_func

    def run(self, data: PipelineData) -> PipelineData:
        for item in data.serialized_hits:
            pathway = item.get("validation_pathway")
            if isinstance(pathway, list):
                pathway.append("reporting")
        data.benchmark = _maybe_generate_benchmark(serialized_hits=data.serialized_hits)
        data.report = _build_report(
            build_json_report_func=self._build_json_report,
            fasta_filename=data.fasta_filename,
            serialized_hits=data.serialized_hits,
            filtered_hits=data.filtered_hits,
            total_raw_hits=len(data.raw_hits),
            benchmark=data.benchmark,
            run_manifest=data.run_manifest,
        )
        data.text_summary = _build_summary(self._build_text_summary, data.serialized_hits)
        return data


class PipelineRunner:
    """Coordinates staged execution for the ARG pipeline."""

    def __init__(self) -> None:
        self.retriever = None
        self.validator = None
        self.build_validation_prompts = None
        self.build_batch_validation_prompts = None
        self.build_json_report = None
        self.build_text_summary = None
        self.stages: list[PipelineStage] = []
        self.run_manifest = _build_run_manifest()

        self._init_optional_components()
        self._init_pipeline()

    def _init_optional_components(self) -> None:
        card_client_cls = _safe_import("modules.retrieval.card_client", "CardClient")
        card_retriever_cls = _safe_import("modules.retrieval.retriever", "CardRetriever")
        if card_client_cls and card_retriever_cls:
            try:
                card_client = card_client_cls(settings.CARD_ONTOLOGY_TSV_PATH)
                self.retriever = card_retriever_cls(card_client)
            except Exception as exc:
                logger.warning("Retrieval stage unavailable, continuing with alignment/scoring only: %s", exc)

        llm_validator_cls = _safe_import("modules.llm_reasoning.validator", "LLMValidator")
        self.build_validation_prompts = _safe_import(
            "modules.prompt_engineering.builder",
            "build_validation_prompts",
        )
        self.build_batch_validation_prompts = _safe_import(
            "modules.prompt_engineering.builder",
            "build_batch_validation_prompts",
        )
        if llm_validator_cls and self.build_validation_prompts:
            try:
                self.validator = llm_validator_cls(provider=_build_provider())
            except Exception as exc:
                logger.warning("Reasoning stage unavailable, continuing without LLM validation: %s", exc)

        self.build_json_report = _safe_import("modules.report_generation.json_formatter", "build_json_report")
        self.build_text_summary = _safe_import("modules.report_generation.text_formatter", "build_text_summary")

    def _init_pipeline(self) -> None:
        self.stages = [
            AlignmentStage(),
            ScoringStage(),
            RetrievalStage(self.retriever),
            ReasoningStage(self.validator, self.build_validation_prompts, self.build_batch_validation_prompts),
            FusionStage(),
            ReportingStage(self.build_json_report, self.build_text_summary),
        ]

    def run(
        self,
        *,
        run_id: str | None = None,
        fasta_path: str,
        fasta_filename: str,
        evalue: float,
        program: str,
        stage_callback: Callable[[str], None] | None = None,
    ) -> PipelineResult:
        """Execute the complete stage-based pipeline for a FASTA input."""
        import time
        start_time = time.perf_counter()

        log_context = run_id or fasta_filename
        logger.info("[%s] Pipeline started (program=%s, evalue=%s)", log_context, program, evalue)

        data = PipelineData(
            fasta_path=fasta_path,
            fasta_filename=fasta_filename,
            evalue=evalue,
            program=program,
            run_id=run_id,
            run_manifest=self.run_manifest,
        )

        for stage in self.stages:
            _set_stage(stage_callback, stage.name)
            logger.info("[%s] Stage %s started", log_context, stage.name)
            data = stage.run(data)
            logger.info("[%s] Stage %s completed", log_context, stage.name)

        end_time = time.perf_counter()
        execution_time_seconds = round(end_time - start_time, 2)
        data.run_manifest["execution_time_seconds"] = execution_time_seconds

        _set_stage(stage_callback, "complete")
        logger.info("[%s] Pipeline completed in %s seconds", log_context, execution_time_seconds)
        return PipelineResult(hits=data.serialized_hits, report=data.report, text_summary=data.text_summary)


def _build_provider():
    provider_name = settings.LLM_PROVIDER.lower().strip()
    if provider_name == "gemini":
        gemini_provider_cls = _safe_import("modules.llm_reasoning.gemini_provider", "GeminiProvider")
        if gemini_provider_cls is None:
            return None
        try:
            return gemini_provider_cls(api_key=settings.GEMINI_API_KEY, model=settings.LLM_MODEL)
        except Exception as exc:
            logger.warning("Gemini provider unavailable, falling back to heuristic validation: %s", exc)
            return None

    if provider_name == "local":
        local_provider_cls = _safe_import("modules.llm_reasoning.local_provider", "LocalProvider")
        if local_provider_cls is None:
            return None
        try:
            return local_provider_cls(base_url=settings.LOCAL_LLM_URL, model=settings.LLM_MODEL)
        except Exception as exc:
            logger.warning("Local provider unavailable, falling back to heuristic validation: %s", exc)
            return None

    if provider_name == "openai":
        openai_provider_cls = _safe_import("modules.llm_reasoning.openai_provider", "OpenAIProvider")
        if openai_provider_cls is None:
            return None
        try:
            return openai_provider_cls(api_key=settings.OPENAI_API_KEY, model=settings.LLM_MODEL)
        except Exception as exc:
            logger.warning("OpenAI provider unavailable, falling back to heuristic validation: %s", exc)
            return None

    if provider_name == "groq":
        groq_provider_cls = _safe_import("modules.llm_reasoning.groq_provider", "GroqProvider")
        if groq_provider_cls is None:
            return None
        try:
            return groq_provider_cls(api_key=settings.GROQ_API_KEY, model=settings.LLM_MODEL)
        except Exception as exc:
            logger.warning("Groq provider unavailable, falling back to heuristic validation: %s", exc)
            return None

    if provider_name == "deepseek":
        deepseek_provider_cls = _safe_import("modules.llm_reasoning.deepseek_provider", "DeepSeekProvider")
        if deepseek_provider_cls is None:
            return None
        try:
            return deepseek_provider_cls(api_key=settings.DEEPSEEK_API_KEY, model=settings.LLM_MODEL)
        except Exception as exc:
            logger.warning("DeepSeek provider unavailable, falling back to heuristic validation: %s", exc)
            return None

    logger.warning("Unknown LLM_PROVIDER=%s. Falling back to heuristic validation.", settings.LLM_PROVIDER)
    return None


def _set_stage(stage_callback: Callable[[str], None] | None, stage: str) -> None:
    if stage_callback:
        stage_callback(stage)


def _safe_import(module_name: str, symbol_name: str):
    try:
        module = import_module(module_name)
        return getattr(module, symbol_name)
    except (ImportError, AttributeError, ModuleNotFoundError) as exc:
        logger.warning("Optional component unavailable: %s.%s (%s)", module_name, symbol_name, exc)
        return None


def _build_report(
    build_json_report_func,
    fasta_filename: str,
    serialized_hits: list[dict[str, object]],
    filtered_hits: list[CandidateHit],
    total_raw_hits: int,
    benchmark: dict[str, object] | None,
    run_manifest: dict[str, object] | None,
) -> dict[str, object]:
    if build_json_report_func:
        try:
            return build_json_report_func(
                fasta_filename=fasta_filename,
                hits=serialized_hits,
                filtered_hits=filtered_hits,
                total_raw_hits=total_raw_hits,
                benchmark=benchmark,
                run_manifest=run_manifest,
            )
        except Exception as exc:
            logger.warning("JSON report builder failed, using fallback report: %s", exc)

    valid_hits = sum(1 for item in serialized_hits if bool(item.get("is_valid_hit")))
    avg_conf = (
        round(sum(float(item.get("final_confidence", 0.0)) for item in serialized_hits) / len(serialized_hits), 2)
        if serialized_hits
        else 0.0
    )
    return {
        "metadata": {
            "fasta_filename": fasta_filename,
            "total_raw_hits": total_raw_hits,
            "filtered_hits": len(filtered_hits),
            "valid_hits": valid_hits,
            "avg_final_confidence": avg_conf,
            "run_manifest": run_manifest or {},
        },
        "benchmark": benchmark,
        "results": serialized_hits,
    }


def _build_summary(build_text_summary_func, hits: list[dict[str, object]]) -> str:
    if build_text_summary_func:
        try:
            return build_text_summary_func(hits)
        except Exception as exc:
            logger.warning("Text summary builder failed, using fallback summary: %s", exc)

    return f"Pipeline completed. Filtered hits: {len(hits)}."


def _heuristic_validation_for_pair(pair: tuple[CandidateHit, GeneContext]) -> ValidationResult:
    hit, context = pair
    is_valid = (
        hit.identity_pct >= settings.IDENTITY_THRESHOLD
        and hit.query_coverage >= settings.QUERY_COVERAGE_THRESHOLD
        and hit.subject_coverage >= settings.SUBJECT_COVERAGE_THRESHOLD
        and hit.e_value <= settings.FILTER_EVALUE_THRESHOLD
    )
    confidence = 65.0 if is_valid else 35.0
    return ValidationResult(
        gene_id=hit.gene_id,
        raw_subject_id=hit.raw_subject_id,
        is_valid_hit=is_valid,
        llm_confidence=confidence,
        reasoning=(
            f"Fallback heuristic used in batch mode. identity_pct={hit.identity_pct:.2f}, "
            f"query_coverage={hit.query_coverage:.2f}, "
            f"subject_coverage={hit.subject_coverage:.2f}, e_value={hit.e_value:.2e}, "
            f"mechanism={context.resistance_mechanism}."
        ),
        resistance_summary=("Likely ARG hit" if is_valid else "Possible low-confidence hit")
        + " based on alignment strength and CARD context.",
        drug_impacts=context.antibiotics if context.antibiotics else context.drug_classes,
        limitations_and_fixes=(
            "Batch fallback may over-weight alignment and under-weight biological plausibility. "
            "Use model-backed response when available."
        ),
        raw_response="heuristic_batch_fallback",
    )


def _resolve_llm_pathway(validation: ValidationResult) -> str:
    if validation.raw_response.startswith("heuristic"):
        return "llm_heuristic_fallback"
    provider = settings.LLM_PROVIDER.lower().strip()
    return f"llm_{provider}" if provider else "llm_unknown"


def _is_contradiction(alignment_confidence: float, validation: ValidationResult | None) -> bool:
    if validation is None:
        return False
    alignment_is_strong = alignment_confidence >= settings.FINAL_CONFIDENCE_THRESHOLD
    if validation.is_valid_hit and not alignment_is_strong:
        return True
    if not validation.is_valid_hit and alignment_is_strong:
        return True
    return False


def _build_run_manifest() -> dict[str, object]:
    return {
        "pipeline_version": settings.PIPELINE_VERSION,
        "diamond_version": _get_diamond_version(),
        "card_db": _hash_manifest_entry(settings.DIAMOND_DB_PATH),
        "aro_tsv": _hash_manifest_entry(settings.CARD_ONTOLOGY_TSV_PATH),
        "calibration_model": _hash_manifest_entry(settings.CALIBRATION_MODEL_PATH),
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "thresholds": {
            "identity": settings.IDENTITY_THRESHOLD,
            "query_coverage": settings.QUERY_COVERAGE_THRESHOLD,
            "subject_coverage": settings.SUBJECT_COVERAGE_THRESHOLD,
            "filter_evalue": settings.FILTER_EVALUE_THRESHOLD,
            "final_confidence": settings.FINAL_CONFIDENCE_THRESHOLD,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _hash_manifest_entry(path_value: str) -> dict[str, object]:
    if not path_value:
        return {"path": "", "sha256": "missing"}

    path = Path(path_value)
    if not path.exists():
        return {"path": str(path), "sha256": "missing"}

    return {"path": str(path), "sha256": _sha256_file(path)}


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_diamond_version() -> str:
    try:
        result = subprocess.run(
            ["diamond", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or result.stderr or "").strip()
        return output or "unknown"
    except Exception:
        return "unknown"


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


def _maybe_generate_benchmark(serialized_hits: list[dict[str, object]]) -> dict[str, object] | None:
    if not settings.BENCHMARK_ENABLED:
        return None

    truth_path = Path(settings.BENCHMARK_TRUTH_PATH)
    if not truth_path.exists():
        logger.warning("Benchmark truth file not found: %s", truth_path)
        return None

    evaluator = _safe_import("modules.benchmarking.evaluator", "evaluate_predictions")
    save_report = _safe_import("modules.benchmarking.evaluator", "save_benchmark_report")
    if evaluator is None or save_report is None:
        return None

    try:
        truth_data = json.loads(truth_path.read_text(encoding="utf-8"))
        if not isinstance(truth_data, dict):
            logger.warning("Benchmark truth payload must be a JSON object mapping gene_id -> bool")
            return None

        predicted_by_gene: dict[str, bool] = {}
        for item in serialized_hits:
            gene_id = str(item.get("gene_id", "")).strip()
            if not gene_id:
                continue
            predicted_by_gene[gene_id] = predicted_by_gene.get(gene_id, False) or bool(item.get("is_valid_hit"))

        result = evaluator(truth_by_gene={k: bool(v) for k, v in truth_data.items()}, predicted_by_gene=predicted_by_gene)
        output_path = save_report(
            output_path=settings.BENCHMARK_OUTPUT_PATH,
            dataset_name=settings.BENCHMARK_DATASET_NAME,
            baseline_name=settings.BENCHMARK_BASELINE_NAME,
            result=result,
        )

        return {
            "dataset": settings.BENCHMARK_DATASET_NAME,
            "baseline": settings.BENCHMARK_BASELINE_NAME,
            "output_path": output_path,
            "metrics": {
                "precision": result.precision,
                "recall": result.recall,
                "f1_score": result.f1_score,
                "true_positive": result.true_positive,
                "false_positive": result.false_positive,
                "false_negative": result.false_negative,
                "true_negative": result.true_negative,
            },
        }
    except Exception as exc:
        logger.warning("Benchmark generation failed: %s", exc)
        return None
