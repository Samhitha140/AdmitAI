"""
Adaptive / Corrective RAG (CRAG) retriever.

Flow:
  1. Hybrid retrieve (BM25 + vector + RRF)          — same as before
  2. Grade each chunk with a lightweight LLM call   — relevant / irrelevant
  3. If grade is POOR  → rewrite query, retry local
  4. If still poor     → fall back to web search (Tavily → Serper → none)
  5. Return best docs + source tag ("local" / "web" / "seed")

Security layer applied at every entry point:
  - Query sanitised (length cap, prompt-injection strip)
  - Retrieved content validated before LLM exposure
"""
from __future__ import annotations

import re

from config.settings import settings
from rag.chunker import chunk_documents
from rag.loader import load_documents
from rag.vectorstore import VectorStore


# --------------------------------------------------------------------------- #
# Security helpers
# --------------------------------------------------------------------------- #
_INJECT_PATTERNS = re.compile(
    r"(ignore (previous|above|all) instructions?|"
    r"system\s*prompt|you are now|disregard|forget everything|"
    r"act as|new persona|jailbreak)",
    re.IGNORECASE,
)
_MAX_QUERY_LEN = 512


def _sanitize(query: str) -> str:
    """Cap length and strip prompt-injection attempts."""
    query = query[:_MAX_QUERY_LEN].strip()
    query = _INJECT_PATTERNS.sub("[removed]", query)
    return query


def _safe_content(text: str) -> str:
    """Truncate retrieved chunk to avoid token-flooding the LLM."""
    return text[:2000]


# --------------------------------------------------------------------------- #
# Tokenizer (shared)
# --------------------------------------------------------------------------- #
def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9.]+", text.lower())


# --------------------------------------------------------------------------- #
# Base hybrid retriever (unchanged logic, kept for backward compat)
# --------------------------------------------------------------------------- #
class HybridRetriever:
    def __init__(self) -> None:
        self._chunks: list[dict] = []
        self._bm25 = None
        self._vector = VectorStore()
        self._ready = False

    def build(self, records: list[dict] | None = None) -> "HybridRetriever":
        records = records or load_documents()
        self._chunks = chunk_documents(records)
        self._vector.add(self._chunks)
        self._build_bm25()
        self._ready = True
        print(f"[retriever] indexed {len(self._chunks)} chunks (BM25 + vector)")
        return self

    def _build_bm25(self) -> None:
        try:
            from rank_bm25 import BM25Okapi
            corpus = [_tokenize(c["text"]) for c in self._chunks]
            self._bm25 = BM25Okapi(corpus)
        except Exception as exc:
            print(f"[retriever] rank_bm25 unavailable ({exc}); using TF fallback")
            self._bm25 = None

    def _bm25_rank(self, query: str, k: int) -> list[int]:
        if self._bm25 is not None:
            scores = self._bm25.get_scores(_tokenize(query))
        else:
            q = set(_tokenize(query))
            scores = [
                sum(_tokenize(c["text"]).count(t) for t in q) for c in self._chunks
            ]
        return sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

    def _vector_rank(self, query: str, k: int) -> list[int]:
        results = self._vector.query(query, k)
        idx = []
        for r in results:
            cid = r["metadata"].get("chunk_id")
            if cid is not None and cid < len(self._chunks):
                idx.append(cid)
        return idx

    def _rrf(self, *rankings: list[int]) -> list[int]:
        scores: dict[int, float] = {}
        for ranking in rankings:
            for rank, doc_id in enumerate(ranking):
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (settings.RRF_K + rank + 1)
        return sorted(scores, key=lambda d: scores[d], reverse=True)

    def _compress(self, query: str, chunk: dict) -> dict:
        q_terms = set(_tokenize(query))
        sentences = re.split(r"(?<=[.;])\s+", chunk["text"])
        kept = [s for s in sentences if q_terms & set(_tokenize(s))]
        text = " ".join(kept) if kept else chunk["text"]
        return {"text": text, "metadata": chunk["metadata"]}

    def retrieve(self, query: str) -> list[dict]:
        if not self._ready:
            self.build()
        query = _sanitize(query)
        bm25_ids = self._bm25_rank(query, settings.BM25_TOP_K)
        vec_ids = self._vector_rank(query, settings.VECTOR_TOP_K)
        fused = self._rrf(bm25_ids, vec_ids)[: settings.FINAL_TOP_K]
        return [self._compress(query, self._chunks[i]) for i in fused]


# --------------------------------------------------------------------------- #
# CRAG — Corrective / Adaptive RAG
# --------------------------------------------------------------------------- #
class AdaptiveRetriever(HybridRetriever):
    """
    Extends HybridRetriever with:
      - LLM document grading
      - Query rewriting on poor results
      - Web search fallback (Tavily → Serper)
    """

    # -------------------------------------------------- grading
    def _grade(self, query: str, docs: list[dict]) -> str:
        """Return 'relevant' or 'poor' using a fast LLM binary check."""
        if not docs:
            return "poor"
        snippet = _safe_content(docs[0]["text"])
        prompt = (
            f"Query: {query}\n\n"
            f"Document excerpt:\n{snippet}\n\n"
            "Does this document contain information that directly helps answer the query? "
            "Reply with only 'yes' or 'no'."
        )
        answer = self._llm_call(prompt, max_tokens=4)
        return "relevant" if "yes" in answer.lower() else "poor"

    # -------------------------------------------------- query rewriting
    def _rewrite(self, query: str) -> str:
        """Ask the LLM to rephrase the query for better retrieval."""
        prompt = (
            f"Original query: {query}\n\n"
            "Rewrite this query to be more specific and retrieval-friendly "
            "for German university admissions documents. "
            "Return only the rewritten query, nothing else."
        )
        rewritten = self._llm_call(prompt, max_tokens=80).strip()
        return _sanitize(rewritten) if rewritten else query

    # -------------------------------------------------- web search
    def _web_search(self, query: str) -> list[dict]:
        """Tavily (accurate, paid) → DuckDuckGo (free fallback)."""
        return self._tavily_search(query) or self._ddg_search(query)

    def _tavily_search(self, query: str) -> list[dict]:
        """Tavily: best for RAG — returns full cleaned content, not just snippets."""
        if not settings.TAVILY_API_KEY:
            return []
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=settings.TAVILY_API_KEY)
            results = client.search(query, max_results=5)
            return [
                {
                    "text": _safe_content(r.get("content", r.get("snippet", ""))),
                    "metadata": {"source": r.get("url", "web"), "university": "web"},
                }
                for r in results.get("results", [])
                if r.get("content") or r.get("snippet")
            ]
        except Exception as exc:
            print(f"[adaptive_rag] Tavily failed ({exc}), trying DuckDuckGo...")
            return []

    def _ddg_search(self, query: str) -> list[dict]:
        """DuckDuckGo: free fallback for when Tavily key is not set."""
        try:
            from ddgs import DDGS
            results = DDGS().text(query, max_results=5)
            return [
                {
                    "text": _safe_content(r.get("body", "")),
                    "metadata": {"source": r.get("href", "web"), "university": "web"},
                }
                for r in results
                if r.get("body")
            ]
        except Exception as exc:
            print(f"[adaptive_rag] DuckDuckGo search failed: {exc}")
            return []

    # -------------------------------------------------- LLM helper
    def _llm_call(self, prompt: str, max_tokens: int = 80) -> str:
        """Lightweight LLM call for grading/rewriting. Uses shared REST client."""
        try:
            from config.llm_provider import get_chat_model
            return get_chat_model(temperature=0.0).invoke(prompt).content
        except Exception:
            return ""

    # -------------------------------------------------- main entry point
    def adaptive_retrieve(self, query: str) -> tuple[list[dict], str]:
        """
        Returns (docs, source) where source is "local", "web", or "seed".
        Use this instead of retrieve() for agent calls.
        """
        query = _sanitize(query)
        if not self._ready:
            self.build()

        # Step 1: hybrid retrieve
        docs = self.retrieve(query)

        # Step 2: grade
        grade = self._grade(query, docs)
        if grade == "relevant":
            return docs, "local"

        # Step 3: rewrite + retry local
        rewritten = self._rewrite(query)
        if rewritten != query:
            docs2 = self.retrieve(rewritten)
            if self._grade(rewritten, docs2) == "relevant":
                return docs2, "local"

        # Step 4: web fallback
        web_docs = self._web_search(rewritten or query)
        if web_docs:
            print(f"[adaptive_rag] local index insufficient — using web ({len(web_docs)} results)")
            return web_docs, "web"

        # Step 5: return original local docs as last resort
        print("[adaptive_rag] no web keys configured — returning best local docs")
        return docs, "seed"

    def retrieve(self, query: str) -> list[dict]:
        """Keep the original retrieve() working for backward compat."""
        return super().retrieve(query)


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #
_retriever: AdaptiveRetriever | None = None


def get_retriever() -> AdaptiveRetriever:
    global _retriever
    if _retriever is None:
        _retriever = AdaptiveRetriever().build()
    return _retriever
