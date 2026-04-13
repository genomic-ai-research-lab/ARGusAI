"""Vector-assisted retrieval over CARD descriptions with lexical fallback."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import logging
from pathlib import Path
import re
from threading import Lock, Thread

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class _Document:
    doc_id: str
    text: str


class VectorContextStore:
    """Retrieve semantically similar CARD contexts for a query string."""

    def __init__(self, records: list[dict[str, str]]) -> None:
        self._docs = self._build_documents(records)
        self._chroma_collection = None
        self._chroma_lock = Lock()
        self._chroma_init_started = False
        self._chroma_init_error: Exception | None = None
        self._maybe_start_chroma_init()

    def query(self, query_text: str, top_k: int = 3) -> list[str]:
        """Return top-k similar context snippets."""

        top_k = max(1, top_k)
        self._maybe_start_chroma_init()

        if self._chroma_collection is not None:
            try:
                result = self._chroma_collection.query(
                    query_texts=[query_text],
                    n_results=top_k,
                    include=["documents"],
                )
                documents = result.get("documents", [[]])
                if documents and documents[0]:
                    return [str(item) for item in documents[0] if isinstance(item, str)]
            except Exception as exc:
                logger.warning("Vector query failed, falling back to lexical similarity: %s", exc)

        return self._lexical_query(query_text=query_text, top_k=top_k)

    def _maybe_start_chroma_init(self) -> None:
        if not self._docs or self._chroma_collection is not None:
            return

        with self._chroma_lock:
            if self._chroma_init_started or self._chroma_collection is not None:
                return

            self._chroma_init_started = True
            Thread(target=self._init_chroma, daemon=True, name="chroma-init").start()

    def _init_chroma(self) -> None:
        if not self._docs:
            return

        try:
            chromadb = import_module("chromadb")

            persist_dir = Path(settings.OUTPUT_DIR) / "chroma"
            persist_dir.mkdir(parents=True, exist_ok=True)
            if hasattr(chromadb, "PersistentClient"):
                client = chromadb.PersistentClient(path=str(persist_dir))
            else:
                client = chromadb.Client()

            collection = client.get_or_create_collection(name="card_context_store")

            if collection.count() == 0:
                batch_size = max(1, settings.CHROMA_INDEX_BATCH_SIZE)
                for start in range(0, len(self._docs), batch_size):
                    batch = self._docs[start : start + batch_size]
                    collection.add(
                        ids=[item.doc_id for item in batch],
                        documents=[item.text for item in batch],
                    )

            self._chroma_collection = collection
            logger.info("ChromaDB index ready with %d documents", len(self._docs))
        except Exception as exc:
            logger.warning("ChromaDB unavailable; retrieval will use lexical fallback: %s", exc)
            self._chroma_init_error = exc
            self._chroma_collection = None

    def _lexical_query(self, query_text: str, top_k: int) -> list[str]:
        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return [item.text for item in self._docs[:top_k]]

        scored: list[tuple[int, str]] = []
        for item in self._docs:
            tokens = _tokenize(item.text)
            score = len(query_tokens & tokens)
            if score > 0:
                scored.append((score, item.text))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored:
            return [text for _, text in scored[:top_k]]

        return [item.text for item in self._docs[:top_k]]

    @staticmethod
    def _build_documents(records: list[dict[str, str]]) -> list[_Document]:
        documents: list[_Document] = []
        for idx, row in enumerate(records):
            name = (row.get("Name") or "unknown").strip()
            short = (row.get("CARD Short Name") or "").strip()
            accession = (row.get("Accession") or "unknown").strip()
            description = (row.get("Description") or "").strip()

            text = (
                f"Name: {name}. "
                f"Short Name: {short if short else 'n/a'}. "
                f"ARO: {accession}. "
                f"Description: {description if description else 'n/a'}."
            )
            documents.append(_Document(doc_id=f"card-{idx}", text=text))

        return documents


def _tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}
