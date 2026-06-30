"""
Eligibility Agent.

For every program the Research Agent found, this node runs the hybrid RAG
pipeline over the ingested university PDFs, retrieves the relevant requirement
chunks, and asks the LLM (with structured output) to produce a fit score plus
met / unmet / borderline requirement lists and a recommendation.
"""
from __future__ import annotations

import re

from graph.state import EligibilityResult, IntelliAdmitState

_PROMPT = """You are a German university admissions eligibility checker.

STUDENT PROFILE:
{profile}

TARGET PROGRAM: {university} - {program}
INSTITUTION TYPE: {institution_type}  (university = research-oriented Universität;
applied_sciences = practice-oriented Fachhochschule/HAW that values internships and
work experience)
FUNDING: {funding_type}  (private institutions charge tuition; flag cost + state recognition)
APPLYING FOR INTAKE: {intake}

RETRIEVED ADMISSION REQUIREMENTS (grounded context):
{context}

Compare the student against the requirements. For an applied-sciences program,
weight practical/work experience; for a university, weight academic match. Return a
fit_score (0-100), met_requirements, unmet_requirements, borderline_requirements, a
cost_note (tuition/recognition), and a one-line recommendation. Stay strictly grounded
in the retrieved context.
"""


def _cost_note(program: dict) -> str:
    """Human-readable cost + recognition flag for the student."""
    funding = program.get("funding_type", "public")
    if funding == "private":
        note = f"Private institution - tuition {program.get('tuition_eur', 'applies')}."
        if not program.get("state_recognized", True):
            note += " WARNING: not confirmed state-recognised - verify before applying."
        else:
            note += " State-recognised."
        return note
    return "Public institution - no tuition, only a semester fee."


# CGPA minimums for known universities (used when requirements text has no figure)
_KNOWN_MIN_CGPA: dict[str, float] = {
    "heidelberg": 8.0, "lmu munich": 7.8, "tu munich": 7.5,
    "rwth aachen": 7.0, "kit karlsruhe": 7.0, "tu berlin": 7.0,
    "tu darmstadt": 7.0, "university of mannheim": 7.5,
    "frankfurt school": 7.0, "whu": 7.5, "hhl": 7.0,
    "saarland": 7.0, "free university berlin": 7.5,
    "university of bonn": 7.0, "university of hamburg": 7.0,
    "university of freiburg": 7.5, "tu dresden": 7.0,
    "munich university of applied sciences": 6.5,
    "hamburg university of applied sciences": 6.5,
    "htw berlin": 6.5, "fh dortmund": 6.5,
    "karlsruhe university of applied sciences": 6.5,
    "iu international": 6.0, "constructor": 6.5,
    "srh university": 6.5, "code university": 6.0,
}


def _get_req_cgpa(university: str, context: str) -> float:
    m = re.search(r"cgpa\s*(?:>=|of|:)?\s*([0-9.]+)", context.lower())
    if m:
        return float(m.group(1))
    uni_lower = university.lower()
    for key, val in _KNOWN_MIN_CGPA.items():
        if key in uni_lower:
            return val
    return 7.0


def _score_heuristic(profile: dict, context: str, program: dict) -> EligibilityResult:
    """Fast deterministic scoring — no LLM, no network calls."""
    cgpa = float(profile.get("cgpa", 0) or 0)
    # Handle both field names: legacy chat uses work_experience_years,
    # Supabase profile stores work_experience_months.
    work_months = float(profile.get("work_experience_months", 0) or 0)
    work_years = float(profile.get("work_experience_years", 0) or 0) or work_months / 12
    inst_type = program.get("institution_type", "university")
    met, unmet, borderline = [], [], []

    req_cgpa = _get_req_cgpa(program.get("university", ""), context)

    if cgpa >= req_cgpa + 0.5:
        met.append(f"CGPA {cgpa} — well above the {req_cgpa} minimum")
    elif cgpa >= req_cgpa:
        met.append(f"CGPA {cgpa} meets the {req_cgpa} requirement")
    elif cgpa >= req_cgpa - 0.5:
        borderline.append(f"CGPA {cgpa} is slightly below {req_cgpa} — borderline")
    else:
        unmet.append(f"CGPA {cgpa} is below the {req_cgpa} minimum")

    if "aps" in context.lower():
        borderline.append("APS certificate required for Indian applicants")

    # language test: borderline not unmet — student likely hasn't taken it yet
    if profile.get("language_tests"):
        met.append(f"Language test: {', '.join(profile['language_tests'])}")
    else:
        borderline.append("Language test (IELTS/TestDaF) needed — register early")

    # score: 0-100 driven by CGPA margin
    margin = cgpa - req_cgpa
    base = int(50 + min(50, max(-50, margin * 25)))

    if inst_type == "applied_sciences":
        if work_years >= 1:
            met.append(f"{work_years:.0f} yr work experience — valued by FH programmes")
            base = min(100, base + 5)
    else:
        if cgpa >= req_cgpa + 1.0:
            met.append("Strong academic record for a research-oriented Universität")

    score = max(5, min(100, base - 10 * len(unmet)))
    rec = ("Strong match" if score >= 80 else
           "Good fit" if score >= 65 else
           "Possible" if score >= 45 else "Reach")
    return EligibilityResult(
        fit_score=score,
        met_requirements=met,
        unmet_requirements=unmet,
        borderline_requirements=borderline,
        cost_note=_cost_note(program),
        recommendation=rec,
    )


def score_universities_for_user(profile: dict, resume: dict) -> list[dict]:
    """
    Standalone scorer — used by /api/match route.
    Loads all universities from Supabase and scores each program.
    """
    from api.database import get_universities

    unis = get_universities()
    if not unis:
        return []

    intake = _normalize_intake(profile.get("target_intake", "winter"))
    level = profile.get("application_level", "masters")
    results = []

    for uni in unis:
        programs = uni.get("programs") or []
        if not programs:
            # Create a single generic program entry from the university data
            programs = [{"name": f"MSc {profile.get('target_field', 'Computer Science')}"}]

        for prog_entry in programs[:3]:  # max 3 programs per university
            prog = {
                "university": uni["name"],
                "program": prog_entry.get("name", "MSc"),
                "institution_type": uni.get("type", "public_research").replace("public_", "").replace("_", ""),
                "funding_type": "private" if uni.get("type") == "private" else "public",
                "intakes_offered": ["winter", "summer"],
                "requirements": list((uni.get("admission_requirements") or {}).values()),
                "tuition_eur": uni.get("tuition_eur_semester", 0),
                "state_recognized": True,
            }
            context = " ".join(prog["requirements"])
            result = _score_heuristic(profile, context, prog)
            result.university = uni["name"]
            result.program = prog["program"]
            result.institution_type = prog["institution_type"]
            result.funding_type = prog["funding_type"]
            result.intake = intake
            result.intake_available = True
            results.append(result.model_dump())

    results.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
    return results


def _normalize_intake(raw: str) -> str:
    """Normalize 'winter_2025' / 'summer_2026' → 'winter' / 'summer'."""
    r = (raw or "winter").lower()
    if "summer" in r:
        return "summer"
    return "winter"


def eligibility_node(state: IntelliAdmitState) -> dict:
    profile = state.get("student_profile", {})
    programs = state.get("target_programs", [])

    intake = _normalize_intake(profile.get("target_intake", "winter"))
    level = profile.get("application_level", "masters")
    pref_type = profile.get("preferred_institution_type")   # None = no filter
    pref_funding = profile.get("preferred_funding")         # None = no filter

    results: list[dict] = []

    for prog in programs:
        # --- level filter ---
        if prog.get("program_level", "masters") != level:
            continue
        # --- preference filters ---
        if pref_type and prog.get("institution_type") != pref_type:
            continue
        if pref_funding and prog.get("funding_type") != pref_funding:
            continue

        # --- intake filter ---
        intakes_offered = prog.get("intakes_offered", ["winter"])
        if intake not in intakes_offered:
            results.append(
                EligibilityResult(
                    university=prog["university"],
                    program=prog["program"],
                    institution_type=prog.get("institution_type", ""),
                    funding_type=prog.get("funding_type", ""),
                    intake=intake,
                    intake_available=False,
                    fit_score=0,
                    unmet_requirements=[
                        f"Not offered for {intake} intake (only: {', '.join(intakes_offered)})"
                    ],
                    cost_note=_cost_note(prog),
                    recommendation=f"Apply for {intakes_offered[0]} intake instead",
                ).model_dump()
            )
            continue

        # Build context from the program's known requirements — no RAG call needed.
        # The heuristic only uses context to extract the CGPA threshold.
        context = "\n".join(prog.get("requirements", []))

        result = _score_heuristic(profile, context, prog)

        result.university = prog["university"]
        result.program = prog["program"]
        result.institution_type = prog.get("institution_type", "")
        result.funding_type = prog.get("funding_type", "")
        result.intake = intake
        result.intake_available = True
        if not result.cost_note:
            result.cost_note = _cost_note(prog)
        results.append(result.model_dump())

    return {
        "eligibility_scores": results,
        "current_agent": "eligibility",
        "conversation_history": [
            {"role": "assistant", "content": f"Scored {len(results)} programs for {intake} intake."}
        ],
    }
