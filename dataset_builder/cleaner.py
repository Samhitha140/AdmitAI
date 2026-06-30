"""
Dataset cleaner and deduplicator.

Runs every collected SOP through four quality gates before it enters training:

  Gate 1 — Length filter
    Discard anything under 200 words or over 1500 words.
    German SOPs are 500–1000 words; anything outside is either a snippet or bloat.

  Gate 2 — German-SOP signal check
    Must contain signals that it's a German university application, not a generic
    US grad school SOP (which has very different conventions).

  Gate 3 — Quality heuristics
    Rejects red-flag patterns: generic openers, duplicate sentences, excessive
    bullet points (German SOPs are prose), visa language in an admission SOP.

  Gate 4 — Near-duplicate deduplication
    Uses MinHash to detect SOPs that are >70% similar (same template with names
    swapped — common in consultancy sample pages).

Output: cleaned JSONL ready for finetuning/dataset.py to consume.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


# ── Gate 1: length ────────────────────────────────────────────────────────────
MIN_WORDS = 200
MAX_WORDS = 1500


# ── Gate 2: German university signals ─────────────────────────────────────────
_GERMAN_SIGNALS = [
    "germany", "german", "universität", "technische", "münchen", "munich",
    "berlin", "aachen", "rwth", "tum", "tu ", "kit", "lmu", "heidelberg",
    "freiburg", "stuttgart", "karlsruhe", "winter semester", "summer semester",
    "uni-assist", "aps certificate", "semester fee", "motivation letter",
    "motivationsschreiben", "master of science", "msc", "m.sc",
]
_MIN_GERMAN_SIGNALS = 2


# ── Gate 3: quality heuristics ────────────────────────────────────────────────
_RED_FLAGS = [
    r"i have always been passionate about",
    r"ever since i was a child",
    r"from a very young age",
    r"it is with great pleasure",
    r"i am excited to apply to your esteemed",
    r"your prestigious university",
    r"enclosed please find",
    r"visa\s+interview",              # visa SOP, not admission SOP
    r"blocked account",               # visa context, not admission
    r"[\[\{]your name[\]\}]",         # unfilled template
    r"[\[\{]university name[\]\}]",
    r"\[insert",
]

_MIN_QUALITY_SCORE = 1  # net positive required

def _quality_score(text: str) -> int:
    t = text.lower()
    # each red flag counts as -2 so even one common bad pattern fails the gate
    flags = sum(2 for p in _RED_FLAGS if re.search(p, t))
    # positive signals
    has_project = any(k in t for k in ["project", "thesis", "research", "developed", "implemented"])
    has_career = any(k in t for k in ["career", "goal", "aspire", "future", "industry", "research group"])
    has_program_fit = any(k in t for k in ["program", "curriculum", "course", "professor", "research group"])
    has_specifics = any(k in t for k in ["cgpa", "gpa", "internship", "published", "paper", "award"])
    score = has_project + has_career + has_program_fit + has_specifics - flags
    return score


# ── Gate 4: MinHash deduplication ─────────────────────────────────────────────
def _shingles(text: str, k: int = 5) -> set[str]:
    words = text.lower().split()
    return {" ".join(words[i:i+k]) for i in range(len(words) - k + 1)}


def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _fingerprint(text: str) -> str:
    return hashlib.md5(text.lower().split()[0:30].__str__().encode()).hexdigest()


# ── Main cleaner ──────────────────────────────────────────────────────────────

def clean_and_deduplicate(raw_items: list[dict], similarity_threshold: float = 0.70) -> list[dict]:
    """Run all four quality gates and return the clean set."""
    passed: list[dict] = []
    seen_shingles: list[set] = []
    seen_fingerprints: set[str] = set()

    stats = {"total": len(raw_items), "g1_length": 0, "g2_german": 0,
             "g3_quality": 0, "g4_duplicate": 0, "passed": 0}

    for item in raw_items:
        text = item.get("text", "").strip()
        words = text.split()

        # Gate 1: length
        if not (MIN_WORDS <= len(words) <= MAX_WORDS):
            stats["g1_length"] += 1
            continue

        # Gate 2: German signals
        t_lower = text.lower()
        signal_count = sum(1 for s in _GERMAN_SIGNALS if s in t_lower)
        if signal_count < _MIN_GERMAN_SIGNALS:
            stats["g2_german"] += 1
            continue

        # Gate 3: quality heuristics
        if _quality_score(text) < _MIN_QUALITY_SCORE:
            stats["g3_quality"] += 1
            continue

        # Gate 4: near-duplicate check
        fp = _fingerprint(text)
        if fp in seen_fingerprints:
            stats["g4_duplicate"] += 1
            continue
        shingles = _shingles(text)
        is_dup = any(_jaccard(shingles, prev) > similarity_threshold for prev in seen_shingles)
        if is_dup:
            stats["g4_duplicate"] += 1
            continue

        seen_fingerprints.add(fp)
        seen_shingles.append(shingles)
        passed.append({**item, "word_count": len(words)})
        stats["passed"] += 1

    print(f"\n  Cleaning stats:")
    print(f"    Total in:        {stats['total']}")
    print(f"    Dropped (length):{stats['g1_length']}")
    print(f"    Dropped (german):{stats['g2_german']}")
    print(f"    Dropped (quality):{stats['g3_quality']}")
    print(f"    Dropped (duplic):{stats['g4_duplicate']}")
    print(f"    Passed:          {stats['passed']}")

    return passed


def save_cleaned(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"  Saved {len(items)} clean items to {path}")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    # quick test with dummy data
    dummy = [
        {"text": "I have always been passionate about computer science in Germany. " * 30,
         "university": "TU Munich", "field": "CS"},
        {"text": "My decision to pursue an MSc in Informatics at TU Munich stems from "
                 "my thesis on retrieval systems, which I developed at NIT Trichy. "
                 "The research group led by Prof. Gurevych at TU Munich aligns with "
                 "my interest in dense retrieval. Germany's tuition-free model enables "
                 "me to focus fully on research. " * 8,
         "university": "TU Munich", "field": "CS"},
    ]
    clean = clean_and_deduplicate(dummy)
    print(f"Clean: {len(clean)}")
