"""Process endpoint to trigger alignment in background."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.job_store import job_store
from api.models import ProcessRequest, ProcessResponse
from config import settings
from modules.alignment.diamond_runner import DiamondRunner

logger = logging.getLogger(__name__)
router = APIRouter(tags=["process"])


def _run_alignment_job(job_id: str, evalue: float, program: str) -> None:
    """Background task: run alignment and store hits."""

    record = job_store.get(job_id)
    if record is None:
        return

    job_store.update(job_id, status="running", stage="alignment")
    try:
        runner = DiamondRunner(
            database_path=settings.DIAMOND_DB_PATH,
            threads=settings.DIAMOND_THREADS,
            evalue=evalue,
            program=program,
            max_hits=settings.MAX_HITS,
        )
        hits = runner.run(record.fasta_path)

        serialized_hits = [
            {
                "gene_id": h.gene_id,
                "identity_pct": h.identity_pct,
                "e_value": h.e_value,
                "alignment_score": h.alignment_score,
                "raw_subject_id": h.raw_subject_id,
            }
            for h in hits
        ]
        job_store.update(job_id, status="complete", stage="alignment_complete", hits=serialized_hits)
        logger.info("Job %s completed with %d hits", job_id, len(serialized_hits))
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        job_store.update(job_id, status="error", stage="alignment", error=str(exc))


@router.post("/process/{job_id}", response_model=ProcessResponse)
async def process_job(job_id: str, request: ProcessRequest, tasks: BackgroundTasks) -> ProcessResponse:
    """Queue background alignment processing for uploaded FASTA."""

    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if request.program not in {"blastx", "blastp"}:
        raise HTTPException(status_code=400, detail="Program must be 'blastx' or 'blastp'")

    if record.status == "running":
        raise HTTPException(status_code=409, detail="Job is already running")

    tasks.add_task(_run_alignment_job, job_id, request.evalue, request.program)
    job_store.update(job_id, status="pending", stage="queued", error=None)
    return ProcessResponse(job_id=job_id, status="pending", message="Alignment job queued")
