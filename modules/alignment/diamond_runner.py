"""DIAMOND alignment tool implementation."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from modules.alignment.base import AlignmentTool, CandidateHit
from modules.alignment.parser import parse_diamond_tsv

logger = logging.getLogger(__name__)


class DiamondRunner(AlignmentTool):
    """Run DIAMOND and parse candidate hits."""

    def __init__(
        self,
        database_path: str,
        threads: int = 4,
        evalue: float = 1e-5,
        program: str = "blastx",
        max_hits: int | None = None,
    ) -> None:
        self.database_path = database_path
        self.threads = threads
        self.evalue = evalue
        self.program = program
        self.max_hits = max_hits
        self.diamond_cmd = self._resolve_diamond_binary()

    def run(self, fasta_path: str) -> list[CandidateHit]:
        """Execute DIAMOND and return parsed hits."""

        fasta = Path(fasta_path)
        if not fasta.exists():
            raise FileNotFoundError(f"Input FASTA not found: {fasta_path}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".tsv") as tmp:
            out_path = tmp.name

        cmd = [
            self.diamond_cmd,
            self.program,
            "-d",
            self.database_path,
            "-q",
            str(fasta),
            "-o",
            out_path,
            "-e",
            str(self.evalue),
            "--threads",
            str(self.threads),
            "--outfmt",
            "6",
            "qseqid",
            "sseqid",
            "pident",
            "length",
            "mismatch",
            "gapopen",
            "qstart",
            "qend",
            "sstart",
            "send",
            "evalue",
            "bitscore",
        ]

        logger.info("Starting DIAMOND alignment")
        completed = subprocess.run(cmd, capture_output=True, text=True)
        if completed.returncode != 0:
            logger.error("DIAMOND failed: %s", completed.stderr.strip())
            raise RuntimeError("DIAMOND alignment failed")

        hits = parse_diamond_tsv(out_path, max_hits=self.max_hits)
        logger.info("DIAMOND completed with %d hits", len(hits))

        try:
            Path(out_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Temporary alignment output cleanup failed: %s", out_path)

        return hits

    @staticmethod
    def _resolve_diamond_binary() -> str:
        """Resolve DIAMOND command from local executable or PATH."""

        local_binary = Path("diamond.exe")
        if local_binary.exists():
            return str(local_binary)

        diamond_on_path = shutil.which("diamond")
        if diamond_on_path:
            return diamond_on_path

        raise FileNotFoundError("DIAMOND binary not found. Place diamond.exe in project root or add diamond to PATH.")
