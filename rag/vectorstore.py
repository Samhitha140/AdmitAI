"""
Dense vector index (ChromaDB + sentence-transformers all-MiniLM-L6-v2).

If chromadb / sentence-transformers are not installed, this transparently falls
back to an in-memory cosine-similarity index built on a hashing embedding, so
the hybrid retriever still works for tests and demos.
"""
from __future__ import annotations

import hashlib
import math

from config.settings import CHROMA_DIR, settings


class _HashEmbedding:
    """Deterministic, dependency-free fallback embedding (bag-of-hashed-words)."""

    dim = 256

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in text.lower().split():
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class VectorStore:
    """Thin wrapper exposing add() and query() with a Chroma or in-memory backend."""

    def __init__(self) -> None:
        self._chroma = None
        self._embedder = None
        self._mem: list[dict] = []
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            self._st = SentenceTransformer(settings.EMBEDDING_MODEL)
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._chroma = client.get_or_create_collection("uni_programs")
            print("[vectorstore] using ChromaDB + sentence-transformers")
        except Exception as exc:
            print(f"[vectorstore] Chroma unavailable ({exc}); using in-memory fallback")
            self._embedder = _HashEmbedding()

    # ----------------------------------------------------------------- add
    def add(self, chunks: list[dict]) -> None:
        if self._chroma is not None:
            embeddings = self._st.encode([c["text"] for c in chunks]).tolist()
            self._chroma.add(
                ids=[f"c{c['metadata']['chunk_id']}" for c in chunks],
                documents=[c["text"] for c in chunks],
                embeddings=embeddings,
                metadatas=[c["metadata"] for c in chunks],
            )
        else:
            for c in chunks:
                self._mem.append(
                    {
                        "text": c["text"],
                        "metadata": c["metadata"],
                        "embedding": self._embedder.embed(c["text"]),
                    }
                )

    # --------------------------------------------------------------- query
    def query(self, text: str, top_k: int) -> list[dict]:
        if self._chroma is not None:
            q_emb = self._st.encode([text]).tolist()
            res = self._chroma.query(query_embeddings=q_emb, n_results=top_k)
            out = []
            for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
                out.append({"text": doc, "metadata": meta})
            return out

        q_emb = self._embedder.embed(text)
        scored = [
            (_cosine(q_emb, d["embedding"]), d) for d in self._mem
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"text": d["text"], "metadata": d["metadata"]} for _, d in scored[:top_k]]
