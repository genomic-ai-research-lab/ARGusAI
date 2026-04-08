"""Upload endpoint for FASTA files."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
import re

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from api.job_store import JobRecord, job_store
from api.models import UploadResponse
from api.rate_limit import enforce_rate_limit
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
_FASTA_SEQUENCE_RE = re.compile(r"^[A-Za-z*.-]+$")


def _is_valid_fasta(content: bytes) -> bool:
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    seen_header = False
    seen_sequence = False
    for line in lines:
        if line.startswith(">"):
            seen_header = True
            continue
        if not seen_header:
            return False
        if not _FASTA_SEQUENCE_RE.match(line):
            return False
        seen_sequence = True

    return seen_header and seen_sequence


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_fasta(file: UploadFile = File(...)) -> UploadResponse:
    """Accept and store a FASTA file; return job id."""

    enforce_rate_limit("upload")

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
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        limit_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"Uploaded file exceeds {limit_mb:.1f}MB limit")
    if not _is_valid_fasta(content):
        raise HTTPException(status_code=400, detail="Uploaded content is not valid FASTA format")

    fasta_path.write_bytes(content)
    record = JobRecord(job_id=job_id, filename=file.filename or fasta_path.name, fasta_path=str(fasta_path))
    job_store.save(record)

    logger.info("File uploaded for job %s", job_id)
    return UploadResponse(job_id=job_id, filename=record.filename, message="Upload successful")
