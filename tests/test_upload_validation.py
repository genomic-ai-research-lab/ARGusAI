from __future__ import annotations

from api.routes.upload import _is_valid_fasta


def test_valid_fasta_is_accepted() -> None:
    payload = b">seq1\nATGCGTAA\n>seq2\nTTTTGGCA\n"
    assert _is_valid_fasta(payload) is True


def test_invalid_fasta_without_header_is_rejected() -> None:
    payload = b"ATGCGTAA\nTTTTGGCA\n"
    assert _is_valid_fasta(payload) is False


def test_invalid_fasta_with_invalid_characters_is_rejected() -> None:
    payload = b">seq1\nATGC1234\n"
    assert _is_valid_fasta(payload) is False
