"""Centralized configuration for the ARG detection framework."""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

ALIGNMENT_TOOL = os.getenv("ALIGNMENT_TOOL", "diamond")
BLAST_DB_PATH = os.getenv("BLAST_DB_PATH", "data/card_db/card.fasta")
DIAMOND_DB_PATH = os.getenv("DIAMOND_DB_PATH", "card_db.dmnd")
CARD_API_BASE_URL = os.getenv("CARD_API_BASE_URL", "https://card.mcmaster.ca/download")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
IDENTITY_THRESHOLD = float(os.getenv("IDENTITY_THRESHOLD", "40.0"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
MAX_HITS = int(os.getenv("MAX_HITS", "5000"))
DIAMOND_THREADS = int(os.getenv("DIAMOND_THREADS", "4"))
DEFAULT_EVALUE = float(os.getenv("DEFAULT_EVALUE", "1e-5"))
