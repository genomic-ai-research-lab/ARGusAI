"""Centralized configuration for the ARG detection framework."""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str, default: bool = False) -> bool:
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}

ALIGNMENT_TOOL = os.getenv("ALIGNMENT_TOOL", "diamond")
BLAST_DB_PATH = os.getenv("BLAST_DB_PATH", "data/card_db/card.fasta")
DIAMOND_DB_PATH = os.getenv("DIAMOND_DB_PATH", "card_db.dmnd")
CARD_API_BASE_URL = os.getenv("CARD_API_BASE_URL", "https://card.mcmaster.ca/download")
CARD_ONTOLOGY_TSV_PATH = os.getenv("CARD_ONTOLOGY_TSV_PATH", "card-ontology/aro.tsv")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
IDENTITY_THRESHOLD = float(os.getenv("IDENTITY_THRESHOLD", "40.0"))
QUERY_COVERAGE_THRESHOLD = float(os.getenv("QUERY_COVERAGE_THRESHOLD", "70.0"))
SUBJECT_COVERAGE_THRESHOLD = float(os.getenv("SUBJECT_COVERAGE_THRESHOLD", "70.0"))
FILTER_EVALUE_THRESHOLD = float(os.getenv("FILTER_EVALUE_THRESHOLD", "1e-5"))
MIN_ALIGNMENT_AA = int(os.getenv("MIN_ALIGNMENT_AA", "80"))
FINAL_CONFIDENCE_THRESHOLD = float(os.getenv("FINAL_CONFIDENCE_THRESHOLD", "70.0"))
ALIGN_SCORE_IDENTITY_EXPONENT = float(os.getenv("ALIGN_SCORE_IDENTITY_EXPONENT", "1.0"))
ALIGN_SCORE_COVERAGE_EXPONENT = float(os.getenv("ALIGN_SCORE_COVERAGE_EXPONENT", "1.0"))
ALIGN_SCORE_EVALUE_EXPONENT = float(os.getenv("ALIGN_SCORE_EVALUE_EXPONENT", "1.0"))
ALIGN_SCORE_EVALUE_LOG_SCALE = float(os.getenv("ALIGN_SCORE_EVALUE_LOG_SCALE", "5.0"))
ALIGN_SCORE_IDENTITY_WEIGHT = float(os.getenv("ALIGN_SCORE_IDENTITY_WEIGHT", "0.60"))
ALIGN_SCORE_SCOV_WEIGHT = float(os.getenv("ALIGN_SCORE_SCOV_WEIGHT", "0.10"))
ALIGN_SCORE_EVALUE_WEIGHT = float(os.getenv("ALIGN_SCORE_EVALUE_WEIGHT", "0.30"))
ALIGNMENT_CONFIDENCE_WEIGHT = float(os.getenv("ALIGNMENT_CONFIDENCE_WEIGHT", "0.7"))
LLM_CONFIDENCE_WEIGHT = float(os.getenv("LLM_CONFIDENCE_WEIGHT", "0.3"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_RATE_LIMIT_PER_MINUTE = int(os.getenv("LLM_RATE_LIMIT_PER_MINUTE", "120"))
LLM_PARALLELISM = int(os.getenv("LLM_PARALLELISM", "4"))
LLM_BATCH_SIZE = int(os.getenv("LLM_BATCH_SIZE", "5"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION", "2.1.0")
CALIBRATION_MODEL_PATH = os.getenv("CALIBRATION_MODEL_PATH", "")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
JOB_STORE_PATH = os.getenv("JOB_STORE_PATH", "outputs/job_store.json")
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))
API_RATE_LIMIT_PER_MINUTE = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120"))
RETRIEVAL_PARALLELISM = int(os.getenv("RETRIEVAL_PARALLELISM", "8"))
CHROMA_INDEX_BATCH_SIZE = int(os.getenv("CHROMA_INDEX_BATCH_SIZE", "256"))
MAX_HITS = int(os.getenv("MAX_HITS", "5000"))
DIAMOND_THREADS = int(os.getenv("DIAMOND_THREADS", "4"))
DEFAULT_EVALUE = float(os.getenv("DEFAULT_EVALUE", "1e-5"))

BENCHMARK_ENABLED = _as_bool(os.getenv("BENCHMARK_ENABLED", "false"), default=False)
BENCHMARK_TRUTH_PATH = os.getenv("BENCHMARK_TRUTH_PATH", "")
BENCHMARK_OUTPUT_PATH = os.getenv("BENCHMARK_OUTPUT_PATH", "outputs/benchmark_metrics.json")
BENCHMARK_DATASET_NAME = os.getenv("BENCHMARK_DATASET_NAME", "unspecified")
BENCHMARK_BASELINE_NAME = os.getenv("BENCHMARK_BASELINE_NAME", "card-baseline")
