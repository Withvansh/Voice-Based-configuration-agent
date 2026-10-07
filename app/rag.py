"""ChromaDB indexing and semantic retrieval for network commands."""

import os
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.utils import embedding_functions


DEFAULT_CHROMA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chroma_db")
)


class CommandRAG:
    """Manages command library indexing and semantic search."""

    def __init__(
        self,
        persist_dir: str = DEFAULT_CHROMA_DIR,
        collection_name: str = "commands",
        model_name: str = "all-MiniLM-L6-v2",
        threshold: float = 0.40,
    ) -> None:
        """Initialize ChromaDB client and embedding model."""
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.threshold = threshold
        os.makedirs(self.persist_dir, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.emb_fn,
        )

    def index_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Upsert parsed chunks into ChromaDB collection."""
        if not chunks:
            return 0

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for c in chunks:
            ids.append(c["id"])
            # Document text combines section heading and command
            documents.append(f"{c['section_heading']} | {c['command']}")
            metadatas.append({
                "source_file": c["source_file"],
                "section_heading": c["section_heading"],
                "command": c["command"],
                "note": c.get("note", ""),
            })

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        return len(chunks)

    def search(
        self,
        query: str,
        k: int = 3,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Search command library for matching query above similarity threshold."""
        if threshold is None:
            threshold = self.threshold

        count = self.collection.count()
        if count == 0:
            return []

        actual_k = min(k, count)
        results = self.collection.query(
            query_texts=[query],
            n_results=actual_k,
            include=["metadatas", "distances", "documents"],
        )

        matches: List[Dict[str, Any]] = []
        if not results or not results.get("metadatas") or not results["metadatas"][0]:
            return []

        metas = results["metadatas"][0]
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(metas)

        for meta, dist in zip(metas, distances):
            # Chroma with cosine distance: distance in [0, 2].
            # Cosine similarity = 1 - distance
            similarity = 1.0 - float(dist)
            if similarity >= threshold:
                matches.append({
                    "command": meta["command"],
                    "section_heading": meta["section_heading"],
                    "source_file": meta["source_file"],
                    "score": round(similarity, 4),
                    "note": meta.get("note", ""),
                })

        return matches

    def find_exact(self, command: str) -> Optional[Dict[str, Any]]:
        """Locate exact command match in the library."""
        try:
            results = self.collection.get(
                where={"command": command},
                include=["metadatas"],
            )
            if results and results.get("metadatas") and len(results["metadatas"]) > 0:
                meta = results["metadatas"][0]
                return {
                    "command": meta["command"],
                    "section_heading": meta["section_heading"],
                    "source_file": meta["source_file"],
                    "score": 1.0,
                    "note": meta.get("note", ""),
                }
        except Exception:
            pass
        return None
