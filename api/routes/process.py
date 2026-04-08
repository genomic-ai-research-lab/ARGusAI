"""Process endpoint to trigger alignment in background."""

from __future__ import annotations

from dataclasses import asdict
import logging
from importlib import import_module
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.job_store import job_store
from api.models import ProcessRequest, ProcessResponse
from api.rate_limit import enforce_rate_limit
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["process"])


def _load_pipeline_runner():
    """Lazily load PipelineRunner so API can start without optional modules."""

    try:
        module = import_module("modules.pipeline.runner")
        return module.PipelineRunner, None
    except ModuleNotFoundError as exc:
        logger.warning("Pipeline module unavailable: %s", exc)
        return None, "Pipeline module is unavailable in this deployment"
    except ImportError as exc:
        logger.warning("Pipeline dependencies unavailable: %s", exc)
        return None, "Pipeline dependencies are unavailable in this deployment"


def _load_alignment_runner():
    """Lazily load DiamondRunner for alignment-only fallback mode."""

    try:
        module = import_module("modules.alignment.diamond_runner")
        return module.DiamondRunner, None
    except ModuleNotFoundError as exc:
        logger.warning("Alignment module unavailable: %s", exc)
        return None, "Alignment module is unavailable in this deployment"
    except ImportError as exc:
        logger.warning("Alignment dependencies unavailable: %s", exc)
        return None, "Alignment dependencies are unavailable in this deployment"


def _run_alignment_only(job_id: str, evalue: float, program: str) -> tuple[list[dict[str, object]], dict[str, object], str]:
    """Run alignment stage only when pipeline module is not available."""

    record = job_store.get(job_id)
    if record is None:
        raise RuntimeError("Job not found")

    alignment_cls, unavailable_reason = _load_alignment_runner()
    if alignment_cls is None:
        raise RuntimeError(unavailable_reason)

    alignment_runner = alignment_cls(
        database_path=settings.DIAMOND_DB_PATH,
        threads=settings.DIAMOND_THREADS,
        evalue=evalue,
        program=program,
        max_hits=settings.MAX_HITS,
    )

    raw_hits = alignment_runner.run(record.fasta_path)
    hits = [asdict(hit) for hit in raw_hits]
    report = {
        "mode": "alignment-only",
        "fasta_filename": record.filename,
        "total_hits": len(hits),
        "skipped_stages": ["scoring", "retrieval", "reasoning", "fusion", "reporting"],
    }
    text_summary = f"Alignment completed. Candidate hits: {len(hits)}."
    return hits, report, text_summary


def _run_pipeline_job(job_id: str, evalue: float, program: str) -> None:
    """Background task: run full pipeline and store results."""

    record = job_store.get(job_id)
    if record is None:
        return

    logger.info("Job %s started (program=%s, evalue=%s)", job_id, program, evalue)
    job_store.update(job_id, status="running", stage="initializing")
    try:
        runner_cls, unavailable_reason = _load_pipeline_runner()
        if runner_cls is not None:
            def _update_stage(stage: str) -> None:
                job_store.update(job_id, stage=stage)
                logger.info("Job %s stage -> %s", job_id, stage)

            init_started = time.perf_counter()
            runner = runner_cls()
            logger.info("Job %s pipeline initialized in %.2fs", job_id, time.perf_counter() - init_started)
            result = runner.run(
                run_id=job_id,
                fasta_path=record.fasta_path,
                fasta_filename=record.filename,
                evalue=evalue,
                program=program,
                stage_callback=_update_stage,
            )

            job_store.update(
                job_id,
                status="complete",
                stage="complete",
                hits=result.hits,
                report=result.report,
                text_summary=result.text_summary,
            )
            logger.info("Job %s completed with %d hits (pipeline mode)", job_id, len(result.hits))
            return

        logger.info("Job %s using fallback mode: %s", job_id, unavailable_reason)
        hits, report, text_summary = _run_alignment_only(job_id, evalue, program)
        job_store.update(
            job_id,
            status="complete",
            stage="complete",
            hits=hits,
            report=report,
            text_summary=text_summary,
        )
        logger.info("Job %s completed with %d hits (alignment-only mode)", job_id, len(hits))
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        failed_stage = (job_store.get(job_id).stage if job_store.get(job_id) else "failed")
        job_store.update(job_id, status="error", stage=failed_stage, error=str(exc))


@router.post("/process/{job_id}", response_model=ProcessResponse)
async def process_job(job_id: str, request: ProcessRequest, tasks: BackgroundTasks) -> ProcessResponse:
    """Queue background RAG pipeline processing for uploaded FASTA."""

    enforce_rate_limit("process")

    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if request.program not in {"blastx", "blastp"}:
        raise HTTPException(status_code=400, detail="Program must be 'blastx' or 'blastp'")

    pipeline_cls, _ = _load_pipeline_runner()
    alignment_cls, alignment_unavailable_reason = _load_alignment_runner()
    if pipeline_cls is None and alignment_cls is None:
        raise HTTPException(status_code=503, detail=alignment_unavailable_reason)

    if record.status == "running":
        raise HTTPException(status_code=409, detail="Job is already running")

    tasks.add_task(_run_pipeline_job, job_id, request.evalue, request.program)
    job_store.update(job_id, status="pending", stage="queued", error=None)
    logger.info("Job %s queued", job_id)
    if pipeline_cls is None:
        return ProcessResponse(job_id=job_id, status="pending", message="Alignment-only job queued")

    return ProcessResponse(job_id=job_id, status="pending", message="Pipeline job queued")
