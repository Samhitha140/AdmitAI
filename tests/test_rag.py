"""Tests for the hybrid RAG pipeline."""
from __future__ import annotations

from rag.chunker import chunk_documents
from rag.loader import load_documents
from rag.retriever import HybridRetriever


def test_loader_returns_records():
    records = load_documents()
    assert records
    assert "text" in records[0] and "metadata" in records[0]


def test_chunker_attaches_ids():
    records = load_documents()
    chunks = chunk_documents(records)
    assert chunks
    assert all("chunk_id" in c["metadata"] for c in chunks)


def test_hybrid_retrieval_relevance():
    retriever = HybridRetriever().build()
    docs = retriever.retrieve("TU Munich CGPA requirement APS")
    assert docs
    joined = " ".join(d["text"] for d in docs).lower()
    # the retriever should surface Munich / requirement content
    assert "munich" in joined or "cgpa" in joined or "aps" in joined


def test_rrf_merges_both_sources():
    retriever = HybridRetriever().build()
    docs = retriever.retrieve("data science statistics programming")
    assert 1 <= len(docs) <= 8
