# LLM-Driven ARG Detection Framework — VS Code Agent Instructions

## Project Overview

Build a modular, web-based framework that detects **Antibiotic Resistance Genes (ARGs)**
from genomic FASTA files. The pipeline combines sequence alignment (BLAST/DIAMOND)
with a RAG (Retrieval-Augmented Generation) system backed by the CARD database and
an LLM reasoning engine. Output is delivered as both structured JSON and natural
language summaries via a web dashboard.

---

## Architecture Principles

- **Modularity is mandatory.** Every component is a self-contained module with a clear
  interface. Swapping the alignment tool, LLM provider, or database must require
  changes only in the relevant module — not across the codebase.
- **Separation of concerns.** Backend logic, AI reasoning, data retrieval, and frontend
  are strictly separated.
- **Config-driven.** All external service endpoints, model names, thresholds, and
  credentials are read from environment variables or a config file — never hardcoded.

---

## Repository Structure

```
arg-detection-framework/
│
├── INSTRUCTIONS.md             # This file
├── README.md
├── .env.example                # Template for environment variables
├── docker-compose.yml          # Optional: orchestrate services locally
│
├── config/
│   └── settings.py             # Central config loader (reads .env)
│
├── modules/
│   ├── __init__.py
│   │
│   ├── alignment/              # Module 1 — Sequence Alignment
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract base class AlignmentTool
│   │   ├── blast_runner.py     # BLAST implementation
│   │   ├── diamond_runner.py   # DIAMOND implementation
│   │   └── parser.py           # Parse raw alignment output → CandidateHit objects
│   │
│   ├── retrieval/              # Module 2 — CARD RAG / Knowledge Retrieval
│   │   ├── __init__.py
│   │   ├── card_client.py      # Query CARD database by ARO ID / gene name
│   │   ├── ontology_parser.py  # Parse ARO entries → structured context dicts
│   │   └── retriever.py        # Orchestrate retrieval for a list of CandidateHits
│   │
│   ├── prompt_engineering/     # Module 3 — Prompt Builder
│   │   ├── __init__.py
│   │   ├── templates.py        # Jinja2 or f-string prompt templates
│   │   └── builder.py          # Combine alignment scores + CARD context → prompt
│   │
│   ├── llm_reasoning/          # Module 4 — LLM Validation Engine
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract base class LLMProvider
│   │   ├── openai_provider.py  # GPT-4o-mini (or any OpenAI-compatible) implementation
│   │   ├── local_provider.py   # Local LLaMA / Ollama implementation (optional)
│   │   └── validator.py        # Send prompt → parse LLM response → ValidationResult
│   │
│   ├── report_generation/      # Module 5 — Output Formatter
│   │   ├── __init__.py
│   │   ├── json_formatter.py   # Produce structured JSON report
│   │   └── text_formatter.py   # Produce human-readable markdown/plain-text summary
│   │
│   └── pipeline/               # Orchestration Layer
│       ├── __init__.py
│       └── runner.py           # Chains modules 1–5 end-to-end
│
├── api/                        # Backend REST API (FastAPI)
│   ├── __init__.py
│   ├── main.py                 # App entry point, route registration
│   ├── routes/
│   │   ├── upload.py           # POST /upload  — accept FASTA file
│   │   ├── process.py          # POST /process — trigger pipeline
│   │   └── results.py          # GET  /results/{job_id} — fetch output
│   └── models.py               # Pydantic request/response schemas
│
├── frontend/                   # Web Dashboard (plain HTML/JS or React)
│   ├── index.html
│   ├── app.js                  # Upload, status polling, results rendering
│   └── styles.css
│
├── data/
│   ├── sample_input/           # Example FASTA files for testing
│   └── card_db/                # Local CARD database snapshots (if used offline)
│
├── tests/
│   ├── unit/
│   │   ├── test_alignment.py
│   │   ├── test_retrieval.py
│   │   ├── test_prompt_builder.py
│   │   ├── test_llm_validator.py
│   │   └── test_report_generation.py
│   └── integration/
│       └── test_pipeline.py    # End-to-end test with a known FASTA file
│
└── requirements.txt
```

---

## Module Specifications

### Module 1 — Alignment (`modules/alignment/`)

**Purpose:** Accept a FASTA file path, run an alignment tool, return a list of
`CandidateHit` objects.

**Key class — `CandidateHit` (dataclass):**
```python
@dataclass
class CandidateHit:
    gene_id: str          # e.g. "tet(A)"
    identity_pct: float   # e.g. 94.5
    e_value: float        # e.g. 1e-120
    alignment_score: float
    raw_subject_id: str   # CARD database subject identifier
```

**Interface — `AlignmentTool` (abstract base):**
```python
class AlignmentTool(ABC):
    @abstractmethod
    def run(self, fasta_path: str) -> list[CandidateHit]: ...
```

**Rules:**
- `blast_runner.py` and `diamond_runner.py` each implement `AlignmentTool`.
- The active tool is selected via `config/settings.py` (`ALIGNMENT_TOOL=blast|diamond`).
- Raw tool output (TSV/XML) is parsed in `parser.py` — alignment runners must not
  contain parsing logic.
- Use `subprocess` to invoke CLI tools; capture stdout/stderr; raise a clear exception
  on non-zero exit.

---

### Module 2 — Retrieval (`modules/retrieval/`)

**Purpose:** Given a list of `CandidateHit` objects, fetch CARD ontology data for each
gene and return enriched context dictionaries.

**Key output structure — `GeneContext` (dataclass):**
```python
@dataclass
class GeneContext:
    gene_id: str
    aro_accession: str
    description: str
    resistance_mechanism: str
    drug_classes: list[str]
    antibiotics: list[str]
```

**Rules:**
- `card_client.py` handles all HTTP requests to the CARD REST API (or local DB
  lookups). It must be the only file that makes network/database calls in this module.
- `ontology_parser.py` converts raw CARD API responses into `GeneContext` objects.
- `retriever.py` orchestrates: for each `CandidateHit`, call `card_client`, parse with
  `ontology_parser`, return a `dict[gene_id → GeneContext]`.
- Implement simple caching (e.g., `functools.lru_cache` or a local JSON cache file)
  to avoid redundant API calls during testing.

---

### Module 3 — Prompt Engineering (`modules/prompt_engineering/`)

**Purpose:** Combine a `CandidateHit` and its `GeneContext` into a structured LLM
prompt.

**Rules:**
- All prompt text lives in `templates.py` as named template strings — never inline
  strings scattered across code.
- `builder.py` imports templates and fills them; it must not contain raw prompt text.
- The prompt must instruct the LLM to return a **structured JSON response** with keys:
  `is_valid_hit` (bool), `confidence` (0–100), `reasoning` (str),
  `resistance_summary` (str), `drug_impacts` (list[str]).
- Include chain-of-thought instructions in the system prompt.

**Example template structure (in `templates.py`):**
```python
SYSTEM_PROMPT = """
You are an expert bioinformatician specialising in antimicrobial resistance.
You will receive a sequence alignment result and a biological description from
the CARD database. Your task is to validate whether the alignment represents a
true resistance gene or a false positive.
Respond ONLY with a JSON object — no markdown, no preamble.
"""

VALIDATION_PROMPT = """
Gene ID: {gene_id}
Alignment Identity: {identity_pct}%
E-Value: {e_value}
Alignment Score: {alignment_score}

CARD Description: {description}
Resistance Mechanism: {resistance_mechanism}
Drug Classes: {drug_classes}
Antibiotics: {antibiotics}

Validate this hit and respond with JSON matching this schema:
{{
  "is_valid_hit": <bool>,
  "confidence": <int 0-100>,
  "reasoning": "<string>",
  "resistance_summary": "<string>",
  "drug_impacts": ["<drug>", ...]
}}
"""
```

---

### Module 4 — LLM Reasoning (`modules/llm_reasoning/`)

**Purpose:** Send a prompt to an LLM provider and return a `ValidationResult`.

**Key class — `ValidationResult` (dataclass):**
```python
@dataclass
class ValidationResult:
    gene_id: str
    is_valid_hit: bool
    confidence: int        # 0–100
    reasoning: str
    resistance_summary: str
    drug_impacts: list[str]
    raw_response: str      # store for debugging
```

**Interface — `LLMProvider` (abstract base):**
```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...
```

**Rules:**
- `openai_provider.py` implements `LLMProvider` using the OpenAI Python SDK.
  Provider is selected via `LLM_PROVIDER=openai|local` in config.
- `validator.py` calls `provider.complete(...)`, then parses the JSON string into a
  `ValidationResult`. If JSON parsing fails, log the raw response and raise a
  descriptive exception — do not silently return bad data.
- Never hardcode model names; read from `LLM_MODEL` in config
  (default: `gpt-4o-mini`).

---

### Module 5 — Report Generation (`modules/report_generation/`)

**Purpose:** Convert a list of `ValidationResult` objects into final output files.

**Rules:**
- `json_formatter.py` serialises results to a structured JSON report file. Include
  a top-level `metadata` block (timestamp, tool versions, FASTA filename).
- `text_formatter.py` produces a human-readable plain-text (or Markdown) summary.
  Each gene gets a section: prediction verdict, confidence, resistance summary, and
  drug impacts.
- Neither formatter should contain any business logic — only formatting.

---

### Pipeline Orchestration (`modules/pipeline/runner.py`)

**Purpose:** Chain all five modules for a single FASTA file input.

```python
class PipelineRunner:
    def run(self, fasta_path: str, output_dir: str) -> PipelineResult:
        # 1. alignment  → list[CandidateHit]
        # 2. retrieval  → dict[gene_id, GeneContext]
        # 3. for each hit: build prompt → call LLM → ValidationResult
        # 4. report generation → write JSON + text files to output_dir
        # return PipelineResult(job_id, output_paths, summary_stats)
```

**Rules:**
- `runner.py` only instantiates modules and calls their public interfaces.
- All module-specific logic stays inside the modules — never leak logic into the runner.
- Log each stage start/end with timestamps using Python's `logging` module.

---

### Backend API (`api/`)

**Framework:** FastAPI

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Accept a `.fasta` or `.fa` file, save to temp dir, return `job_id` |
| `POST` | `/process/{job_id}` | Trigger `PipelineRunner.run()` asynchronously; return `job_id` |
| `GET` | `/status/{job_id}` | Return `{status: pending\|running\|complete\|error}` |
| `GET` | `/results/{job_id}` | Return the full JSON report once complete |

**Rules:**
- Use FastAPI's `BackgroundTasks` or an async task queue for pipeline execution.
- Validate uploaded file extension and MIME type before accepting.
- All request/response bodies are defined as Pydantic models in `api/models.py`.
- Return meaningful HTTP status codes and error messages — never expose raw
  exception tracebacks.

---

### Frontend (`frontend/`)

**Three UI panels (matching the paper's UI design):**

1. **Upload Panel** — drag-and-drop or file-browser upload of a FASTA file; triggers
   `POST /upload` then `POST /process/{job_id}`.
2. **Status Panel** — progress display showing the three pipeline stages
   (Alignment → Retrieval → Reasoning) polled via `GET /status/{job_id}`.
3. **Results Panel** — a table of detected genes (Gene Name, Identity %, E-Value,
   Prediction). Clicking a row expands to show the LLM's natural language explanation
   and confidence score.

**Rules:**
- Keep the frontend minimal and framework-free unless the team prefers React.
- All API calls go through a single `api.js` helper module — no `fetch()` calls
  scattered across components.
- Display confidence as a coloured badge: green (≥80), amber (50–79), red (<50).

---

## Configuration (`config/settings.py`)

Read all settings from environment variables with sensible defaults:

```python
ALIGNMENT_TOOL     = os.getenv("ALIGNMENT_TOOL", "diamond")   # "blast" | "diamond"
BLAST_DB_PATH      = os.getenv("BLAST_DB_PATH", "data/card_db/card.fasta")
DIAMOND_DB_PATH    = os.getenv("DIAMOND_DB_PATH", "data/card_db/card.dmnd")
CARD_API_BASE_URL  = os.getenv("CARD_API_BASE_URL", "https://card.mcmaster.ca/download")
LLM_PROVIDER       = os.getenv("LLM_PROVIDER", "openai")      # "openai" | "local"
LLM_MODEL          = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
LOCAL_LLM_URL      = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
IDENTITY_THRESHOLD = float(os.getenv("IDENTITY_THRESHOLD", "40.0"))  # skip LLM below this %
OUTPUT_DIR         = os.getenv("OUTPUT_DIR", "outputs/")
LOG_LEVEL          = os.getenv("LOG_LEVEL", "INFO")
```

---

## Data Flow Summary

```
User uploads FASTA
        │
        ▼
[1] Alignment Module (BLAST or DIAMOND)
        │  list[CandidateHit]
        ▼
[2] Retrieval Module (CARD API lookup)
        │  dict[gene_id → GeneContext]
        ▼
[3] Prompt Engineering Module
        │  structured prompt string per hit
        ▼
[4] LLM Reasoning Module (OpenAI / Local)
        │  list[ValidationResult]
        ▼
[5] Report Generation Module
        │
        ├── output.json   (structured, for developers)
        └── output.txt    (natural language, for researchers)
```

---

## Testing Requirements

- Every module must have a corresponding unit test file in `tests/unit/`.
- Unit tests must mock external calls (BLAST/DIAMOND subprocess, CARD API, LLM API).
- `tests/integration/test_pipeline.py` runs the full pipeline against a small known
  FASTA file (include one in `data/sample_input/`) and asserts expected genes appear
  in the JSON output.
- Use `pytest`; target ≥80% coverage on the `modules/` directory.
- Provide a `Makefile` target: `make test` to run all tests.

---

## Dependencies (`requirements.txt`)

```
fastapi
uvicorn[standard]
pydantic
python-multipart       # file uploads
openai                 # LLM provider SDK
httpx                  # async HTTP for CARD API calls
biopython              # FASTA parsing and validation
jinja2                 # prompt templates (optional)
python-dotenv          # load .env file
pytest
pytest-asyncio
pytest-cov
```

---

## Development Workflow

1. Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` and DB paths.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the API server: `uvicorn api.main:app --reload`
4. Serve the frontend: open `frontend/index.html` or mount via FastAPI `StaticFiles`.
5. Run tests: `pytest tests/ --cov=modules`

---

## Coding Standards

- Follow **PEP-8**. Use `black` for formatting and `flake8` for linting.
- All public functions and classes must have **docstrings**.
- Use Python **type hints** on all function signatures.
- Use `logging` (not `print`) for all diagnostic output.
- Never commit secrets or API keys — `.env` is gitignored.
- Keep each file under ~200 lines. Split if it grows larger.

---

## Extensibility Guidelines

**Adding a new alignment tool (e.g., MMseqs2):**
1. Create `modules/alignment/mmseqs_runner.py` implementing `AlignmentTool`.
2. Add the new option to `ALIGNMENT_TOOL` in `config/settings.py`.
3. No other files need to change.

**Adding a new LLM provider (e.g., Anthropic Claude, local Gemma):**
1. Create `modules/llm_reasoning/<provider>_provider.py` implementing `LLMProvider`.
2. Register the new value in `config/settings.py` under `LLM_PROVIDER`.
3. No other files need to change.

**Adding a new output format (e.g., CSV, HTML report):**
1. Create `modules/report_generation/<format>_formatter.py`.
2. Call it from `pipeline/runner.py` alongside existing formatters.

---

## References

- **CARD Database:** https://card.mcmaster.ca
- **DIAMOND:** Buchfink et al., *Nature Methods* 12, 59–60 (2015)
- **BLAST:** Altschul et al., *J. Mol. Biol.* 215, 403–410 (1990)
- **RAG:** Lewis et al., NeurIPS 2020 (arXiv:2005.11401)
- **DNABERT-2:** Zhou et al., arXiv:2306.15006
- **BioGPT:** Luo et al., 2022
- **AuraGenome:** Zhang et al., *IEEE CG&A* 45(5), 2025
