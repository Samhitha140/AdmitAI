"""
Scholarship Agent (the 5th agent).

Funding is a separate concern from admissions: scholarships come from their own
source (the DAAD scholarship database + other providers via `scholarship_tool`),
not from university admission pages. This agent fetches scholarships for the
student's academic LEVEL (bachelors vs masters - which matters a lot, since most
DAAD scholarships fund master's and above, not full bachelor's degrees), then
scores each one against the student's field and CGPA and returns eligible matches
with a clear note. It is routed by the supervisor only when the user asks about
funding, so simpler queries never pay for it.
"""
from __future__ import annotations

from graph.state import IntelliAdmitState, ScholarshipMatch
from mcp_tools.scholarship_tool import search_scholarships

_STEM_FIELDS = (
    "computer", "data", "engineer", "math", "physic", "inform", "electric",
    "mechanic", "chemi", "bio", "science", "technolog", "ai", "machine learning",
)


def _is_stem(field: str) -> bool:
    f = field.lower()
    return any(k in f for k in _STEM_FIELDS)


def _field_matches(scholarship_scope: str, student_field: str) -> bool:
    scope = scholarship_scope.lower()
    if "all" in scope:
        return True
    if "stem" in scope:
        return _is_stem(student_field)
    # otherwise require a loose keyword overlap with the student's field
    return any(tok in scope for tok in student_field.lower().split())


def _evaluate(raw: dict, profile: dict) -> ScholarshipMatch:
    cgpa = float(profile.get("cgpa", 0) or 0)
    work_years = float(profile.get("work_experience_years", 0) or 0)
    field = profile.get("target_field", "")

    eligible = True
    notes: list[str] = []

    # field scope
    if not _field_matches(raw.get("fields", "all"), field):
        eligible = False
        notes.append(f"field scope is '{raw.get('fields')}', not your field")

    # academic performance
    min_cgpa = float(raw.get("min_cgpa", 0) or 0)
    if cgpa and min_cgpa and cgpa < min_cgpa:
        eligible = False
        notes.append(f"needs ~CGPA {min_cgpa}+ (you have {cgpa})")
    elif min_cgpa:
        notes.append(f"meets the ~CGPA {min_cgpa} bar")

    # work-experience-gated programmes (e.g. EPOS)
    if raw.get("requires_work_experience") and work_years < 2:
        notes.append("usually expects ~2 yrs work experience")

    notes.append("verify exact terms with the provider before applying")

    return ScholarshipMatch(
        name=raw.get("name", ""),
        provider=raw.get("provider", ""),
        levels=raw.get("levels", []),
        fields=raw.get("fields", "all"),
        amount_eur_month=raw.get("amount_eur_month", ""),
        covers=raw.get("covers", []),
        deadline=raw.get("deadline", ""),
        eligible=eligible,
        eligibility_note="; ".join(notes),
        source_url=raw.get("source_url", ""),
    )


def scholarship_node(state: IntelliAdmitState) -> dict:
    profile = state.get("student_profile", {})
    level = profile.get("application_level", "masters")
    field = profile.get("target_field", "")

    raw_list = search_scholarships.invoke({"level": level, "field": field})
    matches = [_evaluate(r, profile).model_dump() for r in raw_list]
    # eligible ones first, then by provider
    matches.sort(key=lambda m: (not m["eligible"], m["provider"]))

    eligible_count = sum(1 for m in matches if m["eligible"])
    note = (
        f"Found {len(matches)} scholarships for {level} applicants "
        f"({eligible_count} you likely qualify for) via the DAAD database."
    )
    if level == "bachelors":
        note += " Note: most DAAD scholarships fund master's+, so bachelor options are limited."

    return {
        "scholarship_matches": matches,
        "current_agent": "scholarship",
        "conversation_history": [{"role": "assistant", "content": note}],
    }
