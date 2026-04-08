# ARG Detection Framework (RAG Pipeline)

This repository now implements an end-to-end ARG detection pipeline with retrieval and reasoning:

- Modular alignment backend (`modules/alignment/`)
- CARD retrieval module (`modules/retrieval/`)
- Prompt engineering module (`modules/prompt_engineering/`)
- LLM reasoning and validation (`modules/llm_reasoning/`)
- Report generation (`modules/report_generation/`)
- End-to-end orchestration (`modules/pipeline/`)
- FastAPI upload/process/status/results API (`api/`)
- Framework-free frontend dashboard (`frontend/`)

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
   - as `diamond.exe` (Windows) or `diamond` (Linux/macOS) in the project root, or
   - in system `PATH` as `diamond`
3. A built DIAMOND database, for example `card_db.dmnd`

## Setup

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Linux/macOS (bash/zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run API + Frontend

Start backend:

```bash
uvicorn api.main:app --reload
```

Open frontend in browser:

- `http://127.0.0.1:8000/frontend/index.html`

## API Endpoints

- `POST /upload` - upload `.fasta`, `.fa`, `.fna`, `.txt`
- `POST /process/{job_id}` - run full RAG pipeline in background
- `GET /status/{job_id}` - check job state
- `GET /results/{job_id}` - fetch candidate hits, validation output, and report data

## Notes

- DIAMOND is the active alignment runner in this implementation.
- If no configured LLM is available, validation gracefully falls back to a heuristic validator.
- To use Gemini reasoning, set `GEMINI_API_KEY` and keep `LLM_PROVIDER=gemini`.

## Benchmarking

Run the bundled sample benchmark dataset in one command:

```bash
python scripts/run_sample_benchmark.py
```

This writes metrics to:

- `outputs/benchmark/sample_metrics.json`

To enable automatic benchmark output during pipeline runs, configure in `.env`:

- `BENCHMARK_ENABLED=true`
- `BENCHMARK_TRUTH_PATH=data/benchmark/sample_truth.json`
- `BENCHMARK_OUTPUT_PATH=outputs/benchmark/benchmark_metrics.json`

## Testing

Run all tests:

```bash
python -m pytest -q
```

Included tests now cover:

- Validator fallback behavior (invalid JSON and timeout)
- Batch validation JSON parsing
- FASTA validation edge cases
- JSON report snapshot drift detection
- API upload/process/status/results end-to-end flow
- Sample benchmark script output generation
