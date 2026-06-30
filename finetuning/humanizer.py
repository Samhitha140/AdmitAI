"""
SOP Humanization + AI-Detection loop.

Detection: openai-community/roberta-base-openai-detector (local, free, no limits)
  - LABEL_0 = Real (human)   LABEL_1 = Fake (AI)
  - SOPs exceed 512 tokens → split into chunks, average the scores

Flow:
  generate SOP
      ↓
  scan(sop)  →  RoBERTa score 0.0 (human) … 1.0 (AI)
      ↓
  score ≥ 0.45  →  humanize(sop, profile)  →  scan again
      ↓  (max 3 attempts)
  return best version + final score

Humanization strategy:
  1. Strip 20+ AI boilerplate phrases
  2. LLM rewrite with strict sentence-variation + active-voice rules
"""
from __future__ import annotations

import re
import statistics
from functools import lru_cache


# --------------------------------------------------------------------------- #
# AI boilerplate phrases
# --------------------------------------------------------------------------- #
_AI_PHRASES: list[tuple[str, str]] = [
    (r"\bdelve\b", "explore"),
    (r"\bdelving\b", "exploring"),
    (r"\bit is worth noting that\b", ""),
    (r"\bit is important to note that\b", ""),
    (r"\bfurthermore,?\b", ""),
    (r"\bmoreover,?\b", ""),
    (r"\bin conclusion,?\b", "To close,"),
    (r"\bin summary,?\b", ""),
    (r"\bto summarize,?\b", ""),
    (r"\bunderscores?\b", "shows"),
    (r"\bfacilitates?\b", "helps"),
    (r"\butilize[sd]?\b", "use"),
    (r"\bcomprehensive(ly)?\b", "thorough"),
    (r"\bseamlessly\b", "effectively"),
    (r"\btailored to\b", "suited to"),
    (r"\brobust\b", "strong"),
    (r"\bparadigm\b", "approach"),
    (r"\beveryday life\b", "practice"),
    (r"\bi have always been passionate about\b", "My interest in"),
    (r"\bi am deeply passionate about\b", "I am drawn to"),
    (r"\bI am writing to express\b", "I am applying for"),
]

_AI_PHRASES_COMPILED = [
    (re.compile(pat, re.IGNORECASE), repl) for pat, repl in _AI_PHRASES
]


def _strip_boilerplate(text: str) -> str:
    for pattern, replacement in _AI_PHRASES_COMPILED:
        text = pattern.sub(replacement, text)
    text = re.sub(r"  +", " ", text)
    text = re.sub(r" ,", ",", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- #
# Local sentence-uniformity fallback (no model needed)
# --------------------------------------------------------------------------- #
def _local_ai_score(text: str) -> float:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s for s in sentences if len(s.split()) >= 3]
    if len(sentences) < 4:
        return 0.5
    lengths = [len(s.split()) for s in sentences]
    mean = statistics.mean(lengths)
    if mean == 0:
        return 0.5
    cv = statistics.stdev(lengths) / mean
    return round(max(0.0, min(1.0, 1.0 - (cv / 0.6))), 3)


# --------------------------------------------------------------------------- #
# RoBERTa AI detector (local, free, unlimited)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _load_detector():
    """Load once, reuse across all calls."""
    from transformers import pipeline as hf_pipeline
    print("[humanizer] loading roberta-base-openai-detector (first run only)...")
    return hf_pipeline(
        "text-classification",
        model="openai-community/roberta-base-openai-detector",
        device=-1,  # CPU; change to 0 if GPU available
    )


def _split_chunks(text: str, max_words: int = 350) -> list[str]:
    """Split into ~350-word chunks — safely within RoBERTa's 512-token limit."""
    words = text.split()
    if len(words) <= max_words:
        return [text]
    return [
        " ".join(words[i : i + max_words])
        for i in range(0, len(words), max_words)
    ]


def _roberta_score(text: str) -> float:
    """
    Returns AI-likelihood 0.0 (human) … 1.0 (AI).
    Chunks long SOPs and averages scores across chunks.
    """
    try:
        detector = _load_detector()
        chunks = _split_chunks(text)
        ai_scores = []
        for chunk in chunks:
            result = detector(chunk, truncation=True, max_length=512)
            label = result[0]["label"]   # LABEL_0=Real, LABEL_1=Fake
            conf  = result[0]["score"]
            ai_scores.append(conf if label == "LABEL_1" else 1.0 - conf)
        return round(sum(ai_scores) / len(ai_scores), 3)
    except Exception as exc:
        print(f"[humanizer] RoBERTa failed ({exc}), using local heuristic")
        return _local_ai_score(text)


# --------------------------------------------------------------------------- #
# Scanner — tries RoBERTa, falls back to local heuristic
# --------------------------------------------------------------------------- #
def scan(text: str) -> dict:
    """
    Returns {"score": float, "source": str, "flagged": bool}
    score: 0.0 = human, 1.0 = AI
    """
    try:
        score = _roberta_score(text)
        source = "roberta"
    except Exception:
        score = _local_ai_score(text)
        source = "local"
    return {"score": score, "source": source, "flagged": score >= 0.45}


# --------------------------------------------------------------------------- #
# LLM humanizer
# --------------------------------------------------------------------------- #
_HUMANIZE_PROMPT = """You are rewriting a Statement of Purpose so it reads as
genuinely written by the specific student below — not by an AI.

STUDENT DETAILS (use these concrete specifics — do NOT invent new ones):
{profile_context}

ORIGINAL SOP:
{sop}

REWRITING RULES — follow every one:
1. Keep every factual claim and named detail from the original.
2. Vary sentence length heavily: some sentences should be 5–8 words, others 25–35 words.
   Pattern to follow: [long sentence]. [Short punchy sentence.] [Medium.] [Long again.]
3. Remove every instance of: "Furthermore", "Moreover", "In conclusion", "It is worth
   noting", "delve", "comprehensive", "seamlessly", "robust", "underscores", "facilitate".
4. Replace passive voice with active voice wherever possible.
5. The opening sentence must state the specific program and university directly —
   no "I have always been passionate about..." opener.
6. At least one paragraph must contain a sentence of 6 words or fewer.
7. Do NOT add any new claims, achievements, or experiences not in the original.
8. Output only the rewritten SOP text — no preamble, no commentary.
"""


def _llm_humanize(sop: str, profile: dict) -> str:
    profile_context = "\n".join(f"- {k}: {v}" for k, v in profile.items() if v)
    prompt = _HUMANIZE_PROMPT.format(profile_context=profile_context, sop=sop)
    try:
        from config.llm_provider import get_chat_model
        result = get_chat_model(temperature=0.85).invoke(prompt).content
        return result.strip() if result else sop
    except Exception as exc:
        print(f"[humanizer] LLM humanize failed: {exc}")
        return sop


def humanize(sop: str, profile: dict) -> str:
    """Strip boilerplate then LLM rewrite."""
    sop = _strip_boilerplate(sop)
    sop = _llm_humanize(sop, profile)
    return sop


# --------------------------------------------------------------------------- #
# Main loop — scan → humanize → rescan (all local, no quota)
# --------------------------------------------------------------------------- #
def humanize_until_clear(
    sop: str,
    profile: dict,
    max_attempts: int = 3,
    target_score: float = 0.45,
) -> dict:
    """
    Scan → humanize → rescan loop (RoBERTa, free, no word limits).

    Returns:
        {
          "text":     final SOP text,
          "score":    AI-likelihood (0 = human, 1 = AI),
          "source":   "roberta" or "local",
          "flagged":  bool,
          "attempts": int,
          "passed":   bool,
        }
    """
    best_text = sop
    best_score = 1.0

    for attempt in range(1, max_attempts + 1):
        result = scan(sop)
        score = result["score"]
        print(
            f"[humanizer] attempt {attempt}/{max_attempts} "
            f"({result['source']}) — score: {score:.2f} "
            f"({'FLAGGED' if result['flagged'] else 'CLEAR ✓'})"
        )

        if score < best_score:
            best_score = score
            best_text = sop

        if score < target_score:
            return {
                "text": sop,
                "score": score,
                "source": result["source"],
                "flagged": False,
                "attempts": attempt,
                "passed": True,
            }

        if attempt < max_attempts:
            print("[humanizer] rewriting to reduce AI signature...")
            sop = humanize(sop, profile)

    return {
        "text": best_text,
        "score": best_score,
        "source": result["source"],
        "flagged": best_score >= target_score,
        "attempts": max_attempts,
        "passed": best_score < target_score,
    }
