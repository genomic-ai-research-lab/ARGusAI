"""Human-readable report formatter."""

from __future__ import annotations


def _class_label(item: dict[str, object]) -> str:
    provided = item.get("validation_class")
    if provided:
        return str(provided)
    return "Probable ARG" if bool(item.get("is_valid_hit")) else "Unlikely ARG"

def build_text_summary(hits: list[dict[str, object]]) -> str:
    """Render a plain-text report from fused hit outputs."""

    if not hits:
        return "No candidate hits were found for the uploaded sequence."

    lines: list[str] = ["ARG Validation Summary", "======================", ""]
    for item in hits:
        classification = _class_label(item)
        drug_values = item.get("drug_impacts", [])
        drug_impacts = ", ".join(str(entry) for entry in drug_values) if drug_values else "n/a"

        lines.extend(
            [
                f"Gene: {item.get('gene_id', 'unknown')}",
                f"Subject ID: {item.get('raw_subject_id', 'unknown')}",
                f"Class: {classification}",
                f"Query Coverage: {item.get('query_coverage', 0)}",
                f"Subject Coverage: {item.get('subject_coverage', 0)}",
                f"Alignment Confidence: {item.get('alignment_confidence', 0)}",
                f"LLM Confidence: {item.get('llm_confidence', 0)}",
                f"Final Confidence: {item.get('final_confidence', 0)}",
                f"Summary: {item.get('resistance_summary', '')}",
                f"Drug impacts: {drug_impacts}",
                f"Reasoning: {item.get('reasoning', '')}",
                f"Limitations and fixes: {item.get('limitations_and_fixes', '')}",
                "",
            ]
        )

    return "\n".join(lines).strip()
