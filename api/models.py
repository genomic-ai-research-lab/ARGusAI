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
    e_value: float
    alignment_score: float
    raw_subject_id: str
    is_valid_hit: bool = False
    confidence: int = 0
    resistance_summary: str = ""
    drug_impacts: list[str] = Field(default_factory=list)
    limitations_and_fixes: str = ""


class ResultsResponse(BaseModel):
    job_id: str
    status: str
    total_hits: int
    hits: list[HitResponse]
    report: dict[str, object] | None = None
    text_summary: str | None = None
