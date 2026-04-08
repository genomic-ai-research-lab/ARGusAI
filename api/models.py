"""Pydantic API request/response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    message: str


class ProcessRequest(BaseModel):
    evalue: float = Field(default=1e-5, gt=0)
    program: str = Field(default="blastx")


class ProcessResponse(BaseModel):
    job_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    job_id: str
    status: str
    stage: str
    error: str | None = None


class HitResponse(BaseModel):
    gene_id: str
    identity_pct: float
    coverage_pct: float = 0.0
    e_value: float
    alignment_score: float
    alignment_length: int = 0
    subject_length: int = 0
    raw_subject_id: str
    alignment_confidence: float = 0.0
    llm_confidence: float = 0.0
    final_confidence: float = 0.0
    is_valid_hit: bool = False
    validation_class: str = "Review Required"
    reasoning: str = ""
    resistance_summary: str = ""
    drug_impacts: list[str] = Field(default_factory=list)
    limitations_and_fixes: str = ""
    context: dict[str, object] = Field(default_factory=dict)


class ResultsResponse(BaseModel):
    job_id: str
    status: str
    total_hits: int
    hits: list[HitResponse]
    report: dict[str, object] | None = None
    text_summary: str | None = None
