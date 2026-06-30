"""
Clause-boundary chunking.

University admission docs are requirement-dense ("CGPA 7.0", "TestDaF B2",
"deadline 31 May"). Splitting mid-requirement destroys meaning, so we chunk on
sentence/clause boundaries with overlap to preserve the requirement context,
targeting ~500 tokens with 50-token overlap (per the design doc).
"""
from __future__ import annotations

import re

from config.settings import settings


def _approx_tokens(text: str) -> int:
    # cheap heuristic: ~0.75 words per token
    return int(len(text.split()) / 0.75)


def chunk_text(text: str, metadata: dict | None = None) -> list[dict]:
    metadata = metadata or {}
    # split on sentence / clause boundaries, keep delimiters out
    sentences = re.split(r"(?<=[.;:])\s+", text.replace("\n", " "))
    chunks: list[dict] = []
    current: list[str] = []
    current_tokens = 0

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        stoks = _approx_tokens(sent)
        if current_tokens + stoks > settings.CHUNK_SIZE and current:
            chunk_str = " ".join(current)
            chunks.append({"text": chunk_str, "metadata": dict(metadata)})
            # build overlap tail
            overlap, otoks = [], 0
            for s in reversed(current):
                otoks += _approx_tokens(s)
                overlap.insert(0, s)
                if otoks >= settings.CHUNK_OVERLAP:
                    break
            current, current_tokens = overlap, otoks
        current.append(sent)
        current_tokens += stoks

    if current:
        chunks.append({"text": " ".join(current), "metadata": dict(metadata)})
    return chunks


def chunk_documents(records: list[dict]) -> list[dict]:
    out: list[dict] = []
    for rec in records:
        out.extend(chunk_text(rec["text"], rec.get("metadata")))
    for i, c in enumerate(out):
        c["metadata"]["chunk_id"] = i
    return out
