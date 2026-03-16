"""In-memory job store for upload and alignment process state."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class JobRecord:
    job_id: str
    filename: str
    fasta_path: str
    status: str = "pending"
    stage: str = "uploaded"
    error: str | None = None
    hits: list[dict] = field(default_factory=list)


class JobStore:
    """Thread-safe in-memory storage for API jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()

    def save(self, record: JobRecord) -> None:
        with self._lock:
            self._jobs[record.job_id] = record

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
            return record


job_store = JobStore()
