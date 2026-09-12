"""Base interfaces for LLM reasoning providers and result models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Structured validation output for a single candidate hit."""

    gene_id: str
    raw_subject_id: str
    is_valid_hit: bool
    arg_class: str
    llm_confidence: float
    reasoning: str
    resistance_summary: str
    drug_impacts: list[str]
    limitations_and_fixes: str
    raw_response: str
    alignment_confidence: float = 0.0
    final_confidence: float = 0.0


class LLMProvider(ABC):
    """Contract for providers that can complete prompts."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return a text completion for the given prompts."""
