"""Upload endpoint for FASTA files."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from api.job_store import JobRecord, job_store
from api.models import UploadResponse
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["upload"])

ALLOWED_EXTENSIONS = {".fasta", ".fa", ".fna", ".txt"}
ALLOWED_MIME_TYPES = {
    "text/plain",
    "application/octet-stream",
    "chemical/seq-na-fasta",
    "application/x-fasta",
}


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_fasta(file: UploadFile = File(...)) -> UploadResponse:
    """Accept and store a FASTA file; return job id."""

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file extension. Use .fasta, .fa, .fna, or .txt")

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid MIME type: {file.content_type}")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())
    fasta_path = upload_dir / f"{job_id}{suffix}"

    content = await file.read()
    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    fasta_path.write_bytes(content)
    record = JobRecord(job_id=job_id, filename=file.filename or fasta_path.name, fasta_path=str(fasta_path))
    job_store.save(record)

    logger.info("File uploaded for job %s", job_id)
    return UploadResponse(job_id=job_id, filename=record.filename, message="Upload successful")
