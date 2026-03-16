# ARG Detection Framework (Alignment Milestone)

This repository is now rebuilt to match `INSTRUCTIONS.md` up to the completed milestone:

- Modular alignment backend (`modules/alignment/`)
- FastAPI upload/process/status/results API (`api/`)
- Framework-free frontend dashboard (`frontend/`)

Scope intentionally stops at the DIAMOND alignment tool. Retrieval, prompt-engineering,
LLM reasoning, and report-generation modules are not implemented in this milestone.

## Implemented Structure

```text
config/settings.py
modules/alignment/{base.py, parser.py, diamond_runner.py, blast_runner.py}
api/{main.py, models.py, job_store.py, routes/{upload.py, process.py, results.py}}
frontend/{index.html, app.js, api.js, styles.css}
```

## Prerequisites

1. Python 3.10+
2. DIAMOND executable available either:
   - as `diamond.exe` in the project root, or
   - in system `PATH` as `diamond`
3. A built DIAMOND database, for example `card_db.dmnd`

## Setup

```bash
pip install -r requirements.txt
```

Copy environment template:

```bash
copy .env.example .env
```

## Run API + Frontend

Start backend:

```bash
uvicorn api.main:app --reload
```

Open frontend in browser:

- `http://127.0.0.1:8000/frontend/index.html`

## API Endpoints (Alignment Only)

- `POST /upload` - upload `.fasta`, `.fa`, `.fna`, `.txt`
- `POST /process/{job_id}` - run DIAMOND alignment in background
- `GET /status/{job_id}` - check job state
- `GET /results/{job_id}` - fetch candidate hits after completion

## Notes

- `ALIGNMENT_TOOL` is config-driven, but only DIAMOND execution is implemented in this milestone.
- BLAST runner is a placeholder to preserve module-swappability.
