"""Utilities to normalize CARD ontology records into retrieval context objects."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class GeneContext:
    """Structured retrieval context used by prompt building and validation."""

    gene_id: str
    aro_accession: str
    description: str
    resistance_mechanism: str
    drug_classes: list[str]
    antibiotics: list[str]


def parse_gene_context(record: dict[str, str]) -> GeneContext:
    """Build a GeneContext from a CARD TSV row-like dictionary."""

    description = (record.get("Description") or "").strip()
    mechanism = _infer_resistance_mechanism(description)
    drug_classes = _infer_drug_classes(description)
    antibiotics = _extract_antibiotics(description)

    return GeneContext(
        gene_id=(record.get("Name") or "unknown").strip(),
        aro_accession=(record.get("Accession") or "unknown").strip(),
        description=description,
        resistance_mechanism=mechanism,
        drug_classes=drug_classes,
        antibiotics=antibiotics,
    )


def _infer_resistance_mechanism(description: str) -> str:
    lowered = description.lower()
    if "efflux" in lowered:
        return "efflux"
    if "beta-lactamase" in lowered or "hydroly" in lowered:
        return "enzymatic inactivation"
    if "methyltransferase" in lowered or "ribosomal" in lowered:
        return "target modification/protection"
    if "ligase" in lowered:
        return "target replacement"
    if "monooxygenase" in lowered:
        return "enzymatic modification"
    return "unknown"


def _infer_drug_classes(description: str) -> list[str]:
    classes: dict[str, tuple[str, ...]] = {
        "tetracycline": ("tetracycline",),
        "beta-lactam": ("beta-lactam", "penicillin", "cephalosporin", "carbapenem"),
        "glycopeptide": ("glycopeptide", "vancomycin", "teicoplanin"),
        "aminoglycoside": ("aminoglycoside",),
        "macrolide": ("macrolide", "erythromycin"),
        "fluoroquinolone": ("fluoroquinolone",),
        "fosfomycin": ("fosfomycin",),
    }

    lowered = description.lower()
    found: list[str] = []
    for label, keywords in classes.items():
        if any(keyword in lowered for keyword in keywords):
            found.append(label)
    return found


def _extract_antibiotics(description: str) -> list[str]:
    antibiotic_words = {
        "vancomycin",
        "teicoplanin",
        "tetracycline",
        "doxycycline",
        "minocycline",
        "tigecycline",
        "erythromycin",
        "rifampin",
        "fosfomycin",
        "nalidixic acid",
        "streptomycin",
        "chloramphenicol",
    }

    lowered = description.lower()
    found = [item for item in antibiotic_words if item in lowered]

    if not found:
        # Simple fallback for patterns like "confers resistance to X"
        match = re.search(r"resistance to ([^.]+)", lowered)
        if match:
            candidates = [token.strip() for token in re.split(r",| and ", match.group(1))]
            found.extend([token for token in candidates if token])

    return sorted(set(found))
