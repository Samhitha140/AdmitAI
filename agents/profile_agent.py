"""
Profile Agent — analyses extracted resume + profile, identifies missing info,
returns a list of targeted questions to ask the student during onboarding.
"""
from __future__ import annotations


_REQUIRED_FIELDS = [
    ("cgpa", "What is your CGPA / GPA? (on a 10-point or 4-point scale)"),
    ("degree_field", "What is your undergraduate degree subject? (e.g. Computer Science, Electronics)"),
    ("graduation_year", "What year did you / will you graduate?"),
    ("target_intake", "Which intake are you targeting? (Winter 2025 / Summer 2026)"),
    ("target_field", "What field do you want to study in Germany? (e.g. AI, Data Science, Mechanical Engineering)"),
]

_OPTIONAL_FIELDS = [
    ("ielts_score", "Do you have an IELTS score? If yes, what is it?"),
    ("toefl_score", "Do you have a TOEFL score? If yes, what is it?"),
    ("work_experience_months", "How many months of work / internship experience do you have?"),
    ("motivation", "In 1-2 sentences, what is your main motivation for studying in Germany?"),
]


def get_gap_questions(profile: dict, resume: dict) -> list[dict]:
    """
    Returns a list of questions for fields still missing after resume extraction.
    Each item: {key, question, type, required, pre_filled}
    """
    questions = []

    # Check required fields
    for key, question in _REQUIRED_FIELDS:
        value = profile.get(key) or _from_resume(key, resume)
        questions.append({
            "key": key,
            "question": question,
            "required": True,
            "pre_filled": value,
            "answered": bool(value),
        })

    # Check optional but high-value fields
    for key, question in _OPTIONAL_FIELDS:
        value = profile.get(key) or _from_resume(key, resume)
        if not value:
            questions.append({
                "key": key,
                "question": question,
                "required": False,
                "pre_filled": None,
                "answered": False,
            })

    # Resume-specific gaps
    if not resume.get("top_projects") and not resume.get("internships"):
        questions.append({
            "key": "experience_summary",
            "question": "Briefly describe your most relevant project or experience (2-3 sentences).",
            "required": False,
            "pre_filled": None,
            "answered": False,
        })

    return questions


def _from_resume(key: str, resume: dict) -> str | None:
    """Try to pull profile fields from resume data."""
    mapping = {
        "cgpa": resume.get("cgpa"),
        "degree_field": resume.get("degree"),
        "work_experience_months": _calc_experience_months(resume),
    }
    return mapping.get(key)


def _calc_experience_months(resume: dict) -> int | None:
    internships = resume.get("internships") or []
    if not internships:
        return None
    # Rough estimate: 3 months per internship if no duration parsed
    return len(internships) * 3
