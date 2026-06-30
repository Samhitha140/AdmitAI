"""
Structured extraction for the Research Agent.

In LIVE mode the Browser MCP returns the raw text/HTML of an admission page. This
module turns that unstructured page into a typed `ProgramInfo` record — the same
structured-output pattern the Eligibility Agent uses for scoring.

Two-stage design for reliability:
  1. A cheap deterministic classifier reads the university *name* for unambiguous
     signals ("Fachhochschule", "University of Applied Sciences", "Technische
     Universität"). This anchors institution_type even if the LLM is unsure.
  2. The LLM reads the full page with `with_structured_output(ProgramInfo)` to pull
     deadlines, intakes, funding, tuition, language and APS requirements.

If the LLM call fails (no key / MOCK mode), we fall back to the name heuristic plus
safe defaults, so the pipeline never breaks.
"""
from __future__ import annotations

import re

from config.llm_provider import get_chat_model
from graph.state import ProgramInfo

# --------------------------------------------------------------------------- #
# Stage 1: deterministic institution-type / funding hints from the name + text
# --------------------------------------------------------------------------- #
_FH_SIGNALS = [
    "fachhochschule",
    "university of applied sciences",
    "hochschule für angewandte",
    "hochschule fuer angewandte",
    " haw",
    "(haw)",
    " fh ",
    "(fh)",
]
_UNI_SIGNALS = [
    "universität",
    "universitaet",
    "university",          # generic; FH signals are checked first and win
    "technische universität",
    "technical university",
]
_PRIVATE_SIGNALS = ["private", "ggmbh", "gmbh", "tuition fee", "study fee", "€/semester tuition"]


def classify_institution_type(name: str, page_text: str = "") -> str:
    """Return 'applied_sciences' or 'university' from name/page signals."""
    blob = f"{name} {page_text}".lower()
    if any(s in blob for s in _FH_SIGNALS):
        return "applied_sciences"
    if any(s in blob for s in _UNI_SIGNALS):
        return "university"
    return "university"  # safe default for German public institutions


def classify_funding(page_text: str) -> str:
    blob = page_text.lower()
    # an explicit non-trivial tuition figure or "private" wording => private
    if any(s in blob for s in _PRIVATE_SIGNALS):
        return "private"
    if re.search(r"tuition[^.\n]{0,40}\b([1-9][0-9]{3,})\b", blob):
        return "private"
    return "public"


def detect_intakes(page_text: str) -> list[str]:
    blob = page_text.lower()
    intakes = []
    if any(k in blob for k in ["winter", "wintersemester", "october", "oct ", "fall"]):
        intakes.append("winter")
    if any(k in blob for k in ["summer", "sommersemester", "april", "spring"]):
        intakes.append("summer")
    return intakes or ["winter"]


def detect_level(name: str, page_text: str = "") -> str:
    """bachelors vs masters from the program name / page wording."""
    blob = f"{name} {page_text}".lower()
    if any(k in blob for k in ["msc", "m.sc", "master", "ma ", "m.a", "postgraduate", "pg "]):
        return "masters"
    if any(k in blob for k in ["bsc", "b.sc", "bachelor", "ba ", "undergraduate", "ug "]):
        return "bachelors"
    return "masters"  # most international applicants to Germany apply for master's


# --------------------------------------------------------------------------- #
# Stage 2: LLM structured extraction over the full page
# --------------------------------------------------------------------------- #
_EXTRACT_PROMPT = """You read a German university admission web page and extract a
structured program record. Be strictly faithful to the page; never invent figures.

UNIVERSITY (from the link): {university}
PROGRAM HINT: {program}

PAGE CONTENT (truncated):
\"\"\"
{page_text}
\"\"\"

Fill these fields:
- institution_type: "university" (research-oriented Universität) OR
  "applied_sciences" (Fachhochschule / Hochschule für Angewandte Wissenschaften / HAW).
  Decide from the institution's name and self-description on the page.
- funding_type: "public" (free, only a semester fee) OR "private" (charges tuition).
- state_recognized: true unless the page gives reason to doubt recognition.
- intakes_offered: list containing "winter" and/or "summer".
- deadlines: a map like {{"winter": "<date>", "summer": "<date>"}} using only intakes offered.
- tuition_eur: short string, e.g. "0 (semester fee ~150 EUR)" or "~13,000 EUR total".
- language_requirement, aps_required, requirements (list), program, deadline (the next one).

Return the structured object only.
"""


def extract_program_fields(raw: dict, university: str, program_hint: str) -> ProgramInfo:
    """Convert a raw scraped page (dict with 'page_text'/'html' or pre-parsed
    fields) into a validated ProgramInfo. Live LLM path with heuristic fallback."""
    page_text = (raw.get("page_text") or raw.get("html") or "")[:6000]

    # ---- Fallback path: the mock tool already returns parsed fields ---------
    if not page_text:
        return ProgramInfo(
            university=raw.get("university", university),
            program=raw.get("program", program_hint or "MSc"),
            program_level=raw.get(
                "program_level", detect_level(raw.get("program", program_hint or ""))
            ),
            institution_type=raw.get(
                "institution_type", classify_institution_type(raw.get("university", university))
            ),
            funding_type=raw.get("funding_type", "public"),
            state_recognized=raw.get("state_recognized", True),
            deadline=raw.get("deadline", "unknown"),
            intakes_offered=raw.get("intakes_offered", ["winter"]),
            deadlines=raw.get("deadlines", {}),
            tuition_eur=str(raw.get("tuition_eur", "0")),
            language_requirement=raw.get("language_requirement", ""),
            aps_required=raw.get("aps_required", True),
            requirements=raw.get("requirements", []),
            source_url=raw.get("source_url", ""),
        )

    # ---- Live path: LLM structured output, anchored by heuristics -----------
    heur_type = classify_institution_type(university, page_text)
    heur_funding = classify_funding(page_text)
    heur_intakes = detect_intakes(page_text)

    try:
        llm = get_chat_model(temperature=0.0).with_structured_output(ProgramInfo)
        info: ProgramInfo = llm.invoke(
            _EXTRACT_PROMPT.format(
                university=university, program=program_hint, page_text=page_text
            )
        )
        # trust the deterministic classifier over a hedging LLM
        if not info.institution_type:
            info.institution_type = heur_type
        if not info.intakes_offered:
            info.intakes_offered = heur_intakes
        if not info.program_level:
            info.program_level = detect_level(info.program or program_hint, page_text)
        info.university = info.university or university
        info.source_url = raw.get("source_url", info.source_url)
        return info
    except Exception:
        return ProgramInfo(
            university=university,
            program=program_hint or "MSc",
            institution_type=heur_type,
            funding_type=heur_funding,
            intakes_offered=heur_intakes,
            deadline=raw.get("deadline", "unknown"),
            source_url=raw.get("source_url", ""),
        )
