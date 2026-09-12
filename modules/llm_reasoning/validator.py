"""Validation orchestration and fallback behavior for LLM reasoning."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import hashlib
import json
import logging
import re
from threading import Lock
import time

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import settings
from modules.alignment.base import CandidateHit
from modules.llm_reasoning.base import LLMProvider, ValidationResult
from modules.prompt_engineering.templates import FIX_JSON_PROMPT
from modules.retrieval.ontology_parser import GeneContext
from modules.scoring.base import compute_alignment_confidence

logger = logging.getLogger(__name__)


class _LLMValidationPayload(BaseModel):
    """Expected strict schema for model validation outputs."""

    model_config = ConfigDict(extra="forbid")

    is_valid_hit: bool
    arg_class: str
    confidence: float = Field(ge=0, le=100)
    reasoning: str
    resistance_summary: str
    drug_impacts: list[str]
    limitations_and_fixes: str


class _LLMBatchValidationPayload(_LLMValidationPayload):
    """Expected schema for one item in a batch response."""

    gene_id: str
    raw_subject_id: str


class LLMValidator:
    """Validates candidate hits with provider-backed reasoning."""

    def __init__(self, provider: LLMProvider | None) -> None:
        self.provider = provider
        self._provider_disabled = False
        self.max_retries = max(0, settings.LLM_MAX_RETRIES)
        self.request_timeout_seconds = max(1, settings.LLM_TIMEOUT_SECONDS)
        self.rate_limit_per_minute = max(1, settings.LLM_RATE_LIMIT_PER_MINUTE)
        self._cache: dict[str, ValidationResult] = {}
        self._batch_cache: dict[str, list[ValidationResult]] = {}
        self._rate_limit_lock = Lock()
        self._request_timestamps: list[float] = []

    def validate(self, hit: CandidateHit, context: GeneContext, system_prompt: str, user_prompt: str) -> ValidationResult:
        """Validate one hit and return a structured result."""

        cache_key = _cache_key(system_prompt=system_prompt, user_prompt=user_prompt)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return _clone_for_hit(hit=hit, cached=cached)

        if self.provider is None or self._provider_disabled:
            result = _heuristic_validation(hit, context)
            self._cache[cache_key] = result
            return result

        previous_raw_response = ""
        try:
            for attempt in range(self.max_retries + 1):
                raw_response = self._complete_with_timeout(system_prompt=system_prompt, user_prompt=user_prompt)
                logger.debug("Raw LLM response for %s (attempt=%d): %s", hit.gene_id, attempt + 1, raw_response)
                previous_raw_response = raw_response

                try:
                    payload = _parse_and_validate_payload(raw_response)
                    result = ValidationResult(
                        gene_id=hit.gene_id,
                        raw_subject_id=hit.raw_subject_id,
                        is_valid_hit=payload.is_valid_hit,
                        arg_class=payload.arg_class,
                        llm_confidence=round(payload.confidence, 2),
                        reasoning=payload.reasoning,
                        resistance_summary=payload.resistance_summary,
                        drug_impacts=payload.drug_impacts,
                        limitations_and_fixes=payload.limitations_and_fixes,
                        raw_response=raw_response,
                    )
                    self._cache[cache_key] = result
                    return result
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "Invalid LLM JSON for %s on attempt %d/%d: %s",
                        hit.gene_id,
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    if attempt >= self.max_retries:
                        break

                    system_prompt = FIX_JSON_PROMPT
                    user_prompt = previous_raw_response
        except Exception as exc:
            logger.warning("LLM validation failed for %s: %s", hit.gene_id, exc)
            if _is_fatal_provider_error(exc):
                self._provider_disabled = True
                logger.warning("Disabling LLM provider for remaining hits; using heuristic fallback.")

        fallback = _heuristic_validation(hit, context)
        fallback.raw_response = previous_raw_response or "heuristic_fallback"
        self._cache[cache_key] = fallback
        return fallback

    def validate_batch(
        self,
        items: list[tuple[CandidateHit, GeneContext]],
        system_prompt: str,
        user_prompt: str,
    ) -> list[ValidationResult]:
        """Validate a group of hits in one model call with per-item fallback."""

        if not items:
            return []

        cache_key = _cache_key(system_prompt=system_prompt, user_prompt=user_prompt)
        if cache_key in self._batch_cache:
            cached_results = self._batch_cache[cache_key]
            by_key = {_validation_key(item.gene_id, item.raw_subject_id): item for item in cached_results}
            cloned: list[ValidationResult] = []
            for hit, _ in items:
                resolved = by_key.get(_validation_key(hit.gene_id, hit.raw_subject_id))
                if resolved is not None:
                    cloned.append(_clone_for_hit(hit=hit, cached=resolved))
            if len(cloned) == len(items):
                return cloned

        if self.provider is None or self._provider_disabled:
            fallback = [_heuristic_validation(hit, context) for hit, context in items]
            self._batch_cache[cache_key] = fallback
            return fallback

        previous_raw_response = ""
        try:
            for attempt in range(self.max_retries + 1):
                raw_response = self._complete_with_timeout(system_prompt=system_prompt, user_prompt=user_prompt)
                logger.debug("Raw batch LLM response (attempt=%d): %s", attempt + 1, raw_response)
                previous_raw_response = raw_response

                try:
                    payload_items = _parse_and_validate_batch_payload(raw_response)
                    payload_index = {
                        _validation_key(item.gene_id, item.raw_subject_id): item for item in payload_items
                    }

                    resolved: list[ValidationResult] = []
                    for hit, context in items:
                        payload = payload_index.get(_validation_key(hit.gene_id, hit.raw_subject_id))
                        if payload is None:
                            resolved.append(_heuristic_validation(hit, context))
                            continue

                        resolved.append(
                            ValidationResult(
                                gene_id=hit.gene_id,
                                raw_subject_id=hit.raw_subject_id,
                                is_valid_hit=payload.is_valid_hit,
                                arg_class=payload.arg_class,
                                llm_confidence=round(payload.confidence, 2),
                                reasoning=payload.reasoning,
                                resistance_summary=payload.resistance_summary,
                                drug_impacts=payload.drug_impacts,
                                limitations_and_fixes=payload.limitations_and_fixes,
                                raw_response=raw_response,
                            )
                        )

                    self._batch_cache[cache_key] = resolved
                    return resolved
                except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "Invalid batch LLM JSON on attempt %d/%d: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        exc,
                    )
                    if attempt >= self.max_retries:
                        break

                    system_prompt = FIX_JSON_PROMPT
                    user_prompt = previous_raw_response
        except Exception as exc:
            logger.warning("Batch LLM validation failed: %s", exc)
            if _is_fatal_provider_error(exc):
                self._provider_disabled = True
                logger.warning("Disabling LLM provider for remaining hits; using heuristic fallback.")

        fallback = [_heuristic_validation(hit, context) for hit, context in items]
        if previous_raw_response:
            for item in fallback:
                item.raw_response = previous_raw_response
        self._batch_cache[cache_key] = fallback
        return fallback

    def _complete_with_timeout(self, system_prompt: str, user_prompt: str) -> str:
        if self.provider is None:
            raise RuntimeError("LLM provider is not configured")

        self._consume_rate_limit_quota()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.provider.complete, system_prompt, user_prompt)
            try:
                return future.result(timeout=self.request_timeout_seconds)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"LLM request exceeded timeout ({self.request_timeout_seconds}s)"
                ) from exc

    def _consume_rate_limit_quota(self) -> None:
        now = time.time()
        with self._rate_limit_lock:
            self._request_timestamps = [stamp for stamp in self._request_timestamps if now - stamp < 60]
            if len(self._request_timestamps) >= self.rate_limit_per_minute:
                raise RuntimeError("LLM rate limit exceeded for the current minute")
            self._request_timestamps.append(now)


def _is_fatal_provider_error(exc: Exception) -> bool:
    message = str(exc).lower()
    fatal_markers = (
        "insufficient_quota",
        "you exceeded your current quota",
        "invalid api key",
        "authentication",
        "429",
    )
    return any(marker in message for marker in fatal_markers)


def _cache_key(system_prompt: str, user_prompt: str) -> str:
    return hashlib.sha256(f"{system_prompt}\n\n{user_prompt}".encode("utf-8")).hexdigest()


def _validation_key(gene_id: str, raw_subject_id: str) -> str:
    return f"{gene_id}::{raw_subject_id}"


def _parse_and_validate_payload(raw_response: str) -> _LLMValidationPayload:
    parsed = _parse_json_object(raw_response)
    return _LLMValidationPayload.model_validate(parsed)


def _parse_and_validate_batch_payload(raw_response: str) -> list[_LLMBatchValidationPayload]:
    parsed = _parse_json_array(raw_response)
    return [_LLMBatchValidationPayload.model_validate(item) for item in parsed]


def _clone_for_hit(hit: CandidateHit, cached: ValidationResult) -> ValidationResult:
    return ValidationResult(
        gene_id=hit.gene_id,
        raw_subject_id=hit.raw_subject_id,
        is_valid_hit=cached.is_valid_hit,
        arg_class=cached.arg_class,
        llm_confidence=cached.llm_confidence,
        reasoning=cached.reasoning,
        resistance_summary=cached.resistance_summary,
        drug_impacts=list(cached.drug_impacts),
        limitations_and_fixes=cached.limitations_and_fixes,
        raw_response=cached.raw_response,
        alignment_confidence=cached.alignment_confidence,
        final_confidence=cached.final_confidence,
    )


def _parse_json_object(raw_response: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_response)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", raw_response)
    if not match:
        raise ValueError("LLM response does not include a JSON object")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON root is not an object")
    return parsed


def _parse_json_array(raw_response: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(raw_response)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            return [item for item in parsed["results"] if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[[\s\S]*\]", raw_response)
    if not match:
        raise ValueError("LLM response does not include a JSON array")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, list):
        raise ValueError("LLM response JSON root is not an array")

    values = [item for item in parsed if isinstance(item, dict)]
    if not values:
        raise ValueError("LLM response array does not contain JSON objects")
    return values


def _heuristic_validation(hit: CandidateHit, context: GeneContext) -> ValidationResult:
    confidence = compute_alignment_confidence(hit)
    is_valid = confidence >= settings.FINAL_CONFIDENCE_THRESHOLD

    drug_impacts = context.antibiotics if context.antibiotics else context.drug_classes
    summary_prefix = "Likely ARG hit" if is_valid else "Possible low-confidence hit"

    return ValidationResult(
        gene_id=hit.gene_id,
        raw_subject_id=hit.raw_subject_id,
        is_valid_hit=is_valid,
        arg_class="heuristic",
        llm_confidence=confidence,
        reasoning=(
            f"Fallback heuristic used. identity_pct={hit.identity_pct:.2f}, "
            f"query_coverage={hit.query_coverage:.2f}, "
            f"subject_coverage={hit.subject_coverage:.2f}, "
            f"e_value={hit.e_value:.2e}, alignment_confidence={confidence:.2f}, "
            f"mechanism={context.resistance_mechanism}."
        ),
        resistance_summary=f"{summary_prefix} based on alignment strength and CARD context.",
        drug_impacts=drug_impacts,
        limitations_and_fixes=(
            "Heuristic fallback may over-weight alignment and under-weight biological plausibility. "
            "Add coverage thresholds, direct-vs-indirect ARG classes, and mechanism-aware scoring "
            "to reduce false positives and false negatives."
        ),
        raw_response="heuristic_fallback",
    )
