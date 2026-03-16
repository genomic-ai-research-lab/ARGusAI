"""Status and results endpoints for alignment jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.job_store import job_store
from api.models import ResultsResponse, StatusResponse

router = APIRouter(tags=["results"])


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str) -> StatusResponse:
    """Return processing status for a given job id."""

    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return StatusResponse(job_id=record.job_id, status=record.status, stage=record.stage, error=record.error)


@router.get("/results/{job_id}", response_model=ResultsResponse)
async def get_results(job_id: str) -> ResultsResponse:
    """Return alignment results if available."""

    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if record.status == "error":
        raise HTTPException(status_code=500, detail=record.error or "Processing failed")

    if record.status != "complete":
        raise HTTPException(status_code=409, detail="Results are not ready yet")

    return ResultsResponse(
        job_id=record.job_id,
        status=record.status,
        total_hits=len(record.hits),
        hits=record.hits,
    )
