"""JSON report formatter for pipeline output."""

from __future__ import annotations

from datetime import datetime, timezone


def build_json_report(
    *,
    fasta_filename: str,
    hits: list[dict[str, object]],
    filtered_hits: list[object],
    total_raw_hits: int,
    benchmark: dict[str, object] | None = None,
    run_manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a serializable JSON report object."""

    valid_count = sum(1 for item in hits if bool(item.get("is_valid_hit")))
    avg_confidence = (
        round(sum(float(item.get("final_confidence", 0.0)) for item in hits) / len(hits), 2)
        if hits
        else 0.0
    )

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fasta_filename": fasta_filename,
            "total_hits": total_raw_hits,
            "filtered_hits": len(filtered_hits),
            "valid_hits": valid_count,
            "avg_final_confidence": avg_confidence,
            "run_manifest": run_manifest or {},
        },
        "benchmark": benchmark,
        "results": hits,
    }
