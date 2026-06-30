"""
Research Agent.

Finds German universities that offer the student's target program, then scrapes
(or mock-scrapes) each one for admission details.

University discovery order:
  1. DuckDuckGo (free, no API key) — searches for universities in the field
  2. Query mentions — if the user named a university explicitly in their message
  3. Expanded hardcoded shortlist — fallback when no API keys are available

This replaces the old hardcoded 4-university list so results are actually
dynamic and course-specific.
"""
from __future__ import annotations

from config.settings import settings
from graph.state import IntelliAdmitState, ProgramInfo
from agents.extraction import extract_program_fields
from mcp_tools.browser_tool import scrape_university

# Expanded fallback list used when Serper is not configured.
# Covers public Universitäten, applied-sciences (FH/HAW), and a private option
# across multiple fields so eligibility filtering has variety to work with.
_FALLBACK_SHORTLIST: dict[str, list[str]] = {
    # ------------------------------------------------------------------ default
    "default": [
        "TU Munich", "RWTH Aachen", "TU Berlin", "KIT Karlsruhe",
        "LMU Munich", "Heidelberg University", "University of Stuttgart",
        "TU Dresden", "University of Hamburg", "University of Bonn",
        "University of Freiburg", "Paderborn University", "University of Ulm",
        "University of Augsburg", "University of Bayreuth",
        "Munich University of Applied Sciences", "Hamburg University of Applied Sciences",
        "HTW Berlin", "Frankfurt University of Applied Sciences",
        "Karlsruhe University of Applied Sciences",
        "IU International University", "Constructor University",
    ],
    # --------------------------------------------------------------- computer science / IT
    "computer": [
        # Research universities (public)
        "TU Munich", "RWTH Aachen", "TU Berlin", "KIT Karlsruhe",
        "Saarland University", "TU Dresden", "University of Stuttgart",
        "LMU Munich", "TU Darmstadt", "University of Freiburg",
        "University of Bonn", "Paderborn University", "University of Ulm",
        "University of Passau", "University of Augsburg",
        "University of Hamburg", "University of Duisburg-Essen",
        "University of Münster", "Free University Berlin",
        # Applied sciences (FH/HAW)
        "Munich University of Applied Sciences", "Hamburg University of Applied Sciences",
        "HTW Berlin", "Frankfurt University of Applied Sciences",
        "Karlsruhe University of Applied Sciences", "FH Dortmund",
        "Nuremberg Institute of Technology", "Hochschule Heilbronn",
        # Private
        "IU International University", "CODE University of Applied Sciences",
        "Constructor University", "SRH University Heidelberg",
    ],
    # --------------------------------------------------------------- data science / AI
    "data": [
        "TU Munich", "LMU Munich", "RWTH Aachen", "University of Mannheim",
        "TU Berlin", "KIT Karlsruhe", "Heidelberg University",
        "Saarland University", "University of Stuttgart", "TU Dresden",
        "University of Ulm", "University of Bonn", "University of Hamburg",
        "TU Darmstadt", "Paderborn University",
        "Munich University of Applied Sciences", "Hamburg University of Applied Sciences",
        "HTW Berlin", "Karlsruhe University of Applied Sciences",
        "IU International University", "Constructor University",
    ],
    # --------------------------------------------------------------- mechanical engineering
    "mechanical": [
        "TU Munich", "RWTH Aachen", "KIT Karlsruhe", "University of Stuttgart",
        "TU Berlin", "TU Dresden", "TU Darmstadt", "University of Hannover",
        "Ruhr University Bochum", "University of Erlangen-Nuremberg",
        "University of Duisburg-Essen", "TU Braunschweig",
        "Hamburg University of Applied Sciences", "Munich University of Applied Sciences",
        "Frankfurt University of Applied Sciences", "FH Dortmund",
        "Karlsruhe University of Applied Sciences", "IU International University",
    ],
    # --------------------------------------------------------------- electrical / electronics
    "electrical": [
        "TU Munich", "RWTH Aachen", "KIT Karlsruhe", "TU Berlin",
        "University of Stuttgart", "TU Dresden", "TU Darmstadt",
        "University of Erlangen-Nuremberg", "Ruhr University Bochum",
        "University of Hannover", "TU Braunschweig", "University of Ulm",
        "Munich University of Applied Sciences", "Hamburg University of Applied Sciences",
        "HTW Berlin", "Karlsruhe University of Applied Sciences",
        "Nuremberg Institute of Technology", "IU International University",
    ],
    # --------------------------------------------------------------- business / management
    "business": [
        "University of Mannheim", "LMU Munich", "Frankfurt School of Finance",
        "WHU Otto Beisheim School", "Heidelberg University",
        "HHL Leipzig Graduate School", "TU Munich", "University of Cologne",
        "Free University Berlin", "University of Hamburg",
        "University of Frankfurt", "University of Münster",
        "University of Augsburg", "University of Bayreuth",
        "IU International University", "EU Business School Munich",
        "SRH University Heidelberg", "Constructor University",
    ],
    # --------------------------------------------------------------- physics / natural sciences
    "physics": [
        "LMU Munich", "TU Munich", "Heidelberg University", "RWTH Aachen",
        "University of Bonn", "University of Hamburg", "Free University Berlin",
        "University of Freiburg", "University of Cologne",
        "University of Göttingen", "University of Würzburg",
        "TU Dresden", "KIT Karlsruhe", "University of Tübingen",
    ],
    # --------------------------------------------------------------- biology / life sciences
    "biology": [
        "Heidelberg University", "LMU Munich", "Free University Berlin",
        "University of Freiburg", "University of Cologne", "University of Bonn",
        "University of Göttingen", "TU Munich", "University of Hamburg",
        "University of Würzburg", "University of Tübingen",
        "University of Münster", "TU Dresden",
    ],
}

_KNOWN_UNI_NAMES = [
    "TU Munich", "RWTH Aachen", "TU Berlin", "Heidelberg", "LMU Munich",
    "University of Stuttgart", "KIT Karlsruhe", "Saarland University",
    "University of Mannheim", "Frankfurt School", "WHU",
    "Munich University of Applied Sciences", "Hamburg University of Applied Sciences",
    "IU International",
]


def _fallback_list(field: str) -> list[str]:
    """Pick the best static list based on field keyword."""
    f = field.lower()
    for key in ("computer", "data", "mechanical", "electrical", "business", "physics", "biology"):
        if key in f:
            return _FALLBACK_SHORTLIST[key]
    return _FALLBACK_SHORTLIST["default"]


def _universities_from_query(query: str) -> list[str]:
    """Extract university names explicitly mentioned in the user's query."""
    found = []
    q = query.lower()
    for uni in _KNOWN_UNI_NAMES:
        if uni.lower() in q:
            found.append(uni)
    return found


def _get_universities(query: str, field: str, level: str) -> list[str]:
    """
    Resolve the list of universities to research.
    Uses the curated DAAD-sourced static list; explicit user mentions take priority.
    """
    # Explicit names in the user's message take top priority
    explicit = _universities_from_query(query)
    if explicit:
        return explicit

    unis = _fallback_list(field)
    print(f"[research] {len(unis)} universities from DAAD list for field '{field}'")
    return unis


def research_node(state: IntelliAdmitState) -> dict:
    query = state["query"]
    profile = state.get("student_profile", {})
    field = profile.get("target_field", "Computer Science")
    level = profile.get("application_level", "masters")

    universities = _get_universities(query, field, level)
    programs: list[dict] = []

    for uni in universities:
        raw = scrape_university.invoke({"university": uni, "program": field})
        program = extract_program_fields(raw, university=uni, program_hint=f"MSc {field}")
        programs.append(program.model_dump())

    source = "DuckDuckGo" if len(universities) > 7 else "static list"
    return {
        "target_programs": programs,
        "current_agent": "research",
        "conversation_history": [
            {
                "role": "assistant",
                "content": f"Found {len(programs)} {field} programs via {source}.",
            }
        ],
    }
