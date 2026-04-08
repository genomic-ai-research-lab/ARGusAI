"""In-memory job store for upload and alignment process state."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from threading import Lock

from config import settings


@dataclass
class JobRecord:
    job_id: str
    filename: str
    fasta_path: str
    status: str = "pending"
    stage: str = "uploaded"
    error: str | None = None
    hits: list[dict] = field(default_factory=list)
    report: dict | None = None
    text_summary: str | None = None


class JobStore:
    """Thread-safe in-memory storage for API jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._store_path = Path(settings.JOB_STORE_PATH)
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()
        self._recover_interrupted_jobs()

    def save(self, record: JobRecord) -> None:
        with self._lock:
            self._jobs[record.job_id] = record
            self._persist_to_disk()

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **updates: object) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            for key, value in updates.items():
                setattr(record, key, value)
            self._persist_to_disk()
            return record

    def _load_from_disk(self) -> None:
        if not self._store_path.exists():
            return

        try:
            payload = json.loads(self._store_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return

            for job_id, record_data in payload.items():
                if not isinstance(record_data, dict):
                    continue

                self._jobs[job_id] = JobRecord(
                    job_id=job_id,
                    filename=str(record_data.get("filename", "")),
                    fasta_path=str(record_data.get("fasta_path", "")),
                    status=str(record_data.get("status", "pending")),
                    stage=str(record_data.get("stage", "uploaded")),
                    error=record_data.get("error"),
                    hits=list(record_data.get("hits", [])),
                    report=record_data.get("report"),
                    text_summary=record_data.get("text_summary"),
                )
        except Exception:
            # Corrupt job file should not block API startup.
            self._jobs = {}

    def _persist_to_disk(self) -> None:
        payload: dict[str, dict[str, object]] = {}
        for job_id, record in self._jobs.items():
            payload[job_id] = {
                "filename": record.filename,
                "fasta_path": record.fasta_path,
                "status": record.status,
                "stage": record.stage,
                "error": record.error,
                "hits": record.hits,
                "report": record.report,
                "text_summary": record.text_summary,
            }

        self._store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _recover_interrupted_jobs(self) -> None:
        changed = False
        for record in self._jobs.values():
            if record.status in {"pending", "running"}:
                record.status = "error"
                record.stage = "interrupted"
                record.error = "Server restarted while processing this job. Please run it again."
                changed = True

        if changed:
            self._persist_to_disk()


job_store = JobStore()
