from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.job_store import job_store
from api.main import app


client = TestClient(app)


def _reset_job_store() -> None:
    job_store._jobs.clear()  # noqa: SLF001 - test-only reset


def test_upload_process_status_results_flow(monkeypatch) -> None:
    _reset_job_store()

    # Avoid rate-limit noise in tests.
    monkeypatch.setattr("api.routes.upload.enforce_rate_limit", lambda key: None)
    monkeypatch.setattr("api.routes.process.enforce_rate_limit", lambda key: None)

    def fake_run_pipeline_job(job_id: str, evalue: float, program: str) -> None:
        record = job_store.get(job_id)
        assert record is not None

        hits = [
            {
                "gene_id": "geneA",
                "identity_pct": 92.4,
                "e_value": 1e-20,
                "alignment_score": 140.0,
                "alignment_length": 420,
                "query_length": 500,
                "subject_length": 500,
                "query_coverage": 86.0,
                "subject_coverage": 84.0,
                "raw_subject_id": "subA",
                "aro_accession": "ARO:3000001",
                "alignment_confidence": 83.1,
                "llm_confidence": 89.0,
                "final_confidence": 83.1,
                "is_valid_hit": True,
                "reasoning": "Strong biological plausibility.",
                "resistance_summary": "Likely ARG hit.",
                "drug_impacts": ["beta-lactam"],
                "limitations_and_fixes": "No major issues.",
                "validation_pathway": ["alignment", "scoring", "retrieval_aro_exact", "llm_gemini", "fusion"],
                "contradiction_flag": False,
                "context": {
                    "aro_accession": "ARO:3000001",
                    "description": "Sample context",
                    "resistance_mechanism": "efflux",
                    "drug_classes": ["beta-lactam"],
                    "antibiotics": ["amoxicillin"],
                    "similar_contexts": ["similar-1"],
                    "retrieval_method": "retrieval_aro_exact",
                },
            }
        ]

        job_store.update(
            job_id,
            status="complete",
            stage="complete",
            hits=hits,
            report={"metadata": {"total_hits": 1}, "results": hits},
            text_summary="Pipeline completed",
        )

    monkeypatch.setattr("api.routes.process._run_pipeline_job", fake_run_pipeline_job)

    upload_response = client.post(
        "/upload",
        files={"file": ("sample.fasta", b">seq1\nATGCATGC\n", "text/plain")},
    )
    assert upload_response.status_code == 201
    upload_payload = upload_response.json()
    job_id = upload_payload["job_id"]

    process_response = client.post(
        f"/process/{job_id}",
        json={"evalue": 1e-5, "program": "blastx"},
    )
    assert process_response.status_code == 200

    status_response = client.get(f"/status/{job_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "complete"

    results_response = client.get(f"/results/{job_id}")
    assert results_response.status_code == 200
    payload = results_response.json()
    assert payload["total_hits"] == 1
    assert payload["hits"][0]["gene_id"] == "geneA"

    record = job_store.get(job_id)
    if record is not None:
        upload_path = Path(record.fasta_path)
        if upload_path.exists():
            upload_path.unlink()
