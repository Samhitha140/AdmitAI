"""
Resume Parser Agent.

Extraction pipeline (zero-API-first):
  1. Regex (instant)        — name, email, CGPA, degree from raw text
  2. Section parser (instant) — scans for "PROJECTS", "SKILLS" etc. headers,
                                parses entries under each section with zero API calls
  3. Groq fallback (rare)   — only fires if step 2 found 0 projects AND 0 internships
                                (handles unusual / non-standard resume layouts)

This design means Gemini quota is never touched during resume parsing.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from config.llm_provider import get_routing_model
from mcp_tools.pdf_tool import read_student_doc


# --------------------------------------------------------------------------- #
# Structured output models
# --------------------------------------------------------------------------- #
class ProjectItem(BaseModel):
    name: str = ""
    tech_stack: str = ""
    outcome: str = ""


class InternshipItem(BaseModel):
    company: str = ""
    role: str = ""
    achievement: str = ""


class EnrichedProfile(BaseModel):
    """Resume-extracted facts used by the SOP agent and shown in the UI."""
    name: str = ""
    email: str = ""
    cgpa: float = 0.0
    degree: str = ""
    thesis_title: str = ""
    thesis_summary: str = ""
    top_projects: list[ProjectItem] = Field(default_factory=list)
    internships: list[InternshipItem] = Field(default_factory=list)
    relevant_courses: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    raw_text_chars: int = 0


# --------------------------------------------------------------------------- #
# Phase 1 — fast regex (no LLM, <5 ms)
# --------------------------------------------------------------------------- #
def _fast_extract(text: str) -> dict:
    """Extract name / email / CGPA / degree instantly with regex."""
    result: dict = {}

    m = re.search(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", text)
    if m:
        result["email"] = m.group(0)

    m = re.search(
        r"(?:cgpa|gpa|cumulative\s+gpa)[:\s]+(\d+\.?\d*)"
        r"|(\d+\.?\d*)\s*/\s*(?:10(?:\.0)?|4(?:\.0)?)",
        text, re.IGNORECASE,
    )
    if m:
        raw_cgpa = m.group(1) or m.group(2)
        try:
            result["cgpa"] = float(raw_cgpa)
        except ValueError:
            pass

    m = re.search(
        r"(B\.?\s*Tech(?:nology)?[\w\s]{0,30}|B\.?\s*E(?:ng(?:ineering)?)?[\w\s]{0,20}"
        r"|B\.?\s*Sc[\w\s]{0,20}|Bachelor\s+of\s+[\w\s]{3,30})",
        text, re.IGNORECASE,
    )
    if m:
        result["degree"] = re.sub(r"\s+", " ", m.group(0)).strip()

    for line in text.split("\n")[:15]:
        line = line.strip()
        if re.fullmatch(r"[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}", line):
            result["name"] = line
            break

    return result


# --------------------------------------------------------------------------- #
# Phase 2 — zero-API section-based parser (<5 ms)
# --------------------------------------------------------------------------- #

# Ordered list: (keyword_lower, category).  Checked against the stripped,
# lower-cased line so "PROJECTS:" → "projects" → "projects" category.
_SECTION_KEYWORDS: list[tuple[str, str]] = [
    # projects
    ("projects", "projects"),
    ("project", "projects"),
    ("personal projects", "projects"),
    ("personal project", "projects"),
    ("academic projects", "projects"),
    ("academic project", "projects"),
    ("key projects", "projects"),
    ("major projects", "projects"),
    ("mini projects", "projects"),
    ("project work", "projects"),
    ("project experience", "projects"),
    # internships / experience
    ("internships", "internships"),
    ("internship", "internships"),
    ("work experience", "internships"),
    ("professional experience", "internships"),
    ("industry experience", "internships"),
    ("work history", "internships"),
    ("experience", "internships"),
    ("employment", "internships"),
    # skills
    ("technical skills", "skills"),
    ("technical skill", "skills"),
    ("skills", "skills"),
    ("skill", "skills"),
    ("core competencies", "skills"),
    ("key skills", "skills"),
    ("programming skills", "skills"),
    ("technologies", "skills"),
    ("technical expertise", "skills"),
    # courses
    ("relevant courses", "courses"),
    ("relevant coursework", "courses"),
    ("related coursework", "courses"),
    ("courses", "courses"),
    ("coursework", "courses"),
    # achievements / awards
    ("achievements", "achievements"),
    ("achievement", "achievements"),
    ("awards", "achievements"),
    ("award", "achievements"),
    ("honors", "achievements"),
    ("accomplishments", "achievements"),
    ("certifications", "achievements"),
    ("certification", "achievements"),
    ("co-curricular activities", "achievements"),
    ("extracurricular activities", "achievements"),
    ("activities", "achievements"),
    # publications
    ("publications", "publications"),
    ("publication", "publications"),
    ("research papers", "publications"),
    ("papers", "publications"),
    # thesis
    ("thesis", "thesis"),
    ("dissertation", "thesis"),
    ("final year project", "thesis"),
    ("capstone project", "thesis"),
    ("b.tech project", "thesis"),
    ("btech project", "thesis"),
    # education (we just skip its content; regex handles CGPA/degree)
    ("education", "education"),
    ("academic background", "education"),
    ("academic details", "education"),
]

# Date patterns to strip from entry title lines.
# Handles both 3-letter abbreviations (Jun) and full names (June, August).
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_RE = re.compile(
    rf"{_MONTH}\.?\s+\d{{4}}"
    rf"(?:\s*[-–]\s*(?:{_MONTH}\.?\s+\d{{4}}|Present|Ongoing))?"
    r"|\d{4}\s*[-–]\s*(?:\d{4}|Present|Ongoing)"
    r"|(?:Present|Ongoing)",
    re.IGNORECASE,
)

# Numbered entry lines ("1. Project" / "2) Company")  — always start a new entry
_NUMBERED_RE = re.compile(r"^\d+[.)]\s+")
# Symbol/dash bullet lines — description bullets under an entry title
_BULLET_RE = re.compile(r"^[-•*◦→►■▪·]\s+")
# Standalone 4-digit year (fitz often puts right-aligned years on their own line)
_STANDALONE_YEAR_RE = re.compile(r"^\d{4}$")
# Action verbs that start description sentences (not tech keywords)
_VERB_START_RE = re.compile(
    r"^(built|designed|developed|implemented|created|led|managed|improved|"
    r"reduced|achieved|contributed|engineered|applied|trained|fine.tuned|"
    r"increased|decreased|wrote|analyzed|conducted|deployed|automated|"
    r"integrated|architected|optimized|researched|collaborated)",
    re.IGNORECASE,
)
# Job role keywords — identifies a "role line" that belongs to the current entry
_ROLE_WORD_RE = re.compile(
    r"\b(intern|engineer|analyst|developer|researcher|consultant|lead|associate|"
    r"trainee|fellow|scientist|specialist|assistant|manager|architect)\b",
    re.IGNORECASE,
)
# Inline role suffix — matches the role phrase at the end of a combined line like
# "DeepThought CultureTech Ventures  AI Engineer Intern".
# Cap at {0,2} pre-role words so the regex doesn't consume company words
# (e.g. {0,4} would greedily grab "CultureTech Ventures AI Engineer Intern").
_INLINE_ROLE_RE = re.compile(
    r"\s+((?:\w[\w\-\.]*\s+){0,2}"
    r"(?:Engineer(?:ing)?|Intern(?:ship)?|Analyst|Developer|Researcher|"
    r"Scientist|Lead|Associate|Consultant|Assistant|Trainee|Fellow))\s*$",
    re.IGNORECASE,
)

# Lines that are tech-stack clarifiers under a title (not new entries)
_TECH_LINE_RE = re.compile(
    r"^(?:tech(?:nologies|nology|nical)?(?:\s+stack)?|tools?|stack|built\s+with)\s*:\s*",
    re.IGNORECASE,
)


def _looks_like_tech_stack(line: str) -> bool:
    """True if the line is a comma/dot-separated list of short tech keywords.

    Handles untagged lines like "Python, FastAPI, React" or
    "RAG, Gemini, ChromaDB, FastAPI" that fitz places on their own line
    below a project title (without a "Tech Stack:" prefix).
    """
    if not re.search(r"[,·]", line):
        return False
    parts = re.split(r"[,·]", line)
    if len(parts) < 2:
        return False
    for p in parts:
        p = p.strip()
        if len(p) > 38 or _VERB_START_RE.match(p):
            return False
    return True


def _looks_like_role(line: str) -> bool:
    """True if a SHORT line looks like a standalone role (not a new company).

    Threshold 35 chars keeps "AI Engineer Intern" (18) and "ML Intern" (9)
    but rejects "SkillCraft Technologies Machine Learning Intern" (47).
    """
    s = line.strip()
    return bool(len(s) <= 35 and "," not in s and _ROLE_WORD_RE.search(s))


def _detect_section(line: str) -> Optional[str]:
    """Return section category if line is a known section header, else None."""
    # Strip leading/trailing decoration (---, ===, spaces, colons)
    stripped = re.sub(r"^[\s\-=*#_|]+|[\s\-=*#_|:]+$", "", line).strip()
    if not stripped or len(stripped) > 60:
        return None

    low = stripped.lower()
    for keyword, category in _SECTION_KEYWORDS:
        # Exact match or keyword surrounded by whitespace within the line
        if low == keyword:
            return category
        # e.g. "PROJECTS AND INTERNSHIPS" → still → "projects"
        if low.startswith(keyword + " ") or low.endswith(" " + keyword):
            return category

    # ALL-CAPS lines that are exactly one or two words often are headers
    # but only if they match the keywords above (already checked), so skip.
    return None


def _parse_entry_title(line: str, is_work: bool) -> dict:
    """Parse 'Name | Tech | Date' or 'Company | Role | Date' into fields."""
    # Remove dates first
    clean = _DATE_RE.sub("", line).strip().strip("|–—-").strip()
    # Split by pipe, slash, or em-dash
    parts = [p.strip() for p in re.split(r"\s*[|/–—]\s*", clean) if p.strip()]

    if is_work:
        if len(parts) > 1:
            return {"company": parts[0], "role": parts[1]}
        # No pipe/dash separator — try to split inline role suffix.
        # e.g. "DeepThought CultureTech Ventures  AI Engineer Intern"
        text = parts[0] if parts else clean
        m = _INLINE_ROLE_RE.search(text)
        if m:
            # Normalize multiple spaces (fitz uses wide gaps as column separators)
            company_part = re.sub(r"\s+", " ", text[:m.start()]).strip()
            role_part = re.sub(r"\s+", " ", m.group(1)).strip()
            return {"company": company_part, "role": role_part}
        return {"company": text, "role": ""}
    else:
        name = parts[0] if parts else line.strip()
        tech = ", ".join(parts[1:]) if len(parts) > 1 else ""
        # Also capture tech in parens: "Project Name (Python, React)"
        if not tech:
            pm = re.search(r"\(([^)]+)\)", name)
            if pm:
                tech = pm.group(1)
                name = name[:pm.start()].strip()
        return {"name": name, "tech_stack": tech}


def _parse_section_entries(lines: list[str], is_work: bool) -> list[dict]:
    """Parse project or internship entries from their section lines.

    Each entry consists of:
      - A title line (no bullet prefix, not a continuation bullet)
      - Optional "Tech Stack: ..." line
      - Zero or more bullet point lines (description / achievements)
    """
    entries: list[dict] = []
    current: Optional[dict] = None
    current_bullets: list[str] = []

    def _flush() -> None:
        if current is None:
            return
        text = " ".join(current_bullets)
        if is_work:
            entries.append({
                "company": current.get("company", ""),
                "role": current.get("role", ""),
                "achievement": text[:350],
            })
        else:
            entries.append({
                "name": current.get("name", ""),
                "tech_stack": current.get("tech_stack", ""),
                "outcome": text[:350],
            })

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if _NUMBERED_RE.match(line):
            # "1. Project Name" or "2) Company" — always a new entry title
            _flush()
            title_text = _NUMBERED_RE.sub("", line).strip()
            current = _parse_entry_title(title_text, is_work=is_work)
            current_bullets = []

        elif _STANDALONE_YEAR_RE.match(line):
            # A bare year like "2026" — fitz splits right-aligned years onto
            # their own line. Skip it; it doesn't start a new entry.
            pass

        elif _BULLET_RE.match(line):
            if current is None:
                # First line in section is bullet-prefixed → treat as entry title
                title_text = _BULLET_RE.sub("", line).strip()
                current = _parse_entry_title(title_text, is_work=is_work)
                current_bullets = []
            else:
                text = _BULLET_RE.sub("", line).strip()
                current_bullets.append(text)

        elif _TECH_LINE_RE.match(line):
            # "Tech Stack: Python, React" — tagged tech line
            if current is not None and not current.get("tech_stack"):
                current["tech_stack"] = _TECH_LINE_RE.sub("", line).strip()

        elif not is_work and _looks_like_tech_stack(line):
            # Untagged tech line below a project title, e.g.:
            # "RAG, Gemini, ChromaDB, FastAPI"
            # "Python, PennyLane, TensorFlow Federated, IBM Quantum · College Research"
            if current is not None and not current.get("tech_stack"):
                current["tech_stack"] = line

        elif is_work and current is not None and not current.get("role"):
            # For internship entries fitz often splits company and role:
            #   "DeepThought CultureTech Ventures"
            #   "AI Engineer Intern  Nov 2025 – Present"   ← role line
            role_clean = _DATE_RE.sub("", line).strip().strip("|–—-").strip()
            if _looks_like_role(role_clean):
                current["role"] = role_clean
            else:
                # Real new entry
                _flush()
                current = _parse_entry_title(line, is_work=is_work)
                current_bullets = []

        else:
            # Plain title line → new entry
            _flush()
            current = _parse_entry_title(line, is_work=is_work)
            current_bullets = []

    _flush()
    return entries[:4 if not is_work else 3]


def _parse_skills(lines: list[str]) -> list[str]:
    """Parse skill lists, handling 'Category: s1, s2, s3' and plain lists."""
    skills: list[str] = []
    for line in lines:
        if ":" in line:
            _, vals = line.split(":", 1)
            items = re.split(r"[,|;]", vals)
        else:
            items = re.split(r"[,|;]", line)
        for item in items:
            s = re.sub(r"^[-•*\s]+|[\s]+$", "", item).strip()
            if s and len(s) < 40 and not re.match(r"^\d+$", s):
                skills.append(s)
    return skills[:15]


_ANY_BULLET_RE = re.compile(r"^[-•*◦→►■▪·]\s+|\d+[.)]\s+")


def _parse_list(lines: list[str]) -> list[str]:
    """Extract a flat list of strings from bullet/plain lines."""
    items: list[str] = []
    for line in lines:
        text = _ANY_BULLET_RE.sub("", line).strip()
        if text and len(text) < 200:
            items.append(text)
    return items


def _section_extract(text: str) -> dict:
    """Zero-API resume parser — detects section headers and parses content.

    Works for virtually all single-column Indian student resume formats.
    Returns the same dict shape as the LLM prompt expects.
    """
    lines = text.split("\n")

    # ── Step 1: split text into named sections ──────────────────────────────
    sections: dict[str, list[str]] = {}
    current_section: Optional[str] = None
    current_lines: list[str] = []

    for line in lines:
        category = _detect_section(line)
        if category:
            if current_section:
                sections.setdefault(current_section, []).extend(current_lines)
            current_section = category
            current_lines = []
        elif current_section:
            current_lines.append(line)

    if current_section and current_lines:
        sections.setdefault(current_section, []).extend(current_lines)

    # ── Step 2: parse each section ──────────────────────────────────────────
    result: dict = {
        "thesis_title": "",
        "thesis_summary": "",
        "projects": [],
        "internships": [],
        "courses": [],
        "skills": [],
        "publications": [],
        "achievements": [],
    }

    if "projects" in sections:
        raw = _parse_section_entries(sections["projects"], is_work=False)
        result["projects"] = raw

    if "internships" in sections:
        raw = _parse_section_entries(sections["internships"], is_work=True)
        result["internships"] = raw

    if "skills" in sections:
        result["skills"] = _parse_skills(sections["skills"])

    if "courses" in sections:
        result["courses"] = _parse_list(sections["courses"])[:8]

    if "achievements" in sections:
        result["achievements"] = _parse_list(sections["achievements"])[:6]

    if "publications" in sections:
        result["publications"] = _parse_list(sections["publications"])[:4]

    if "thesis" in sections:
        t_lines = [l.strip() for l in sections["thesis"] if l.strip()]
        if t_lines:
            result["thesis_title"] = t_lines[0]
            result["thesis_summary"] = " ".join(t_lines[1:])[:300]

    n_projects = len(result["projects"])
    n_internships = len(result["internships"])
    n_skills = len(result["skills"])
    print(f"[resume_parser] section-parser: {n_projects} projects, "
          f"{n_internships} internships, {n_skills} skills  "
          f"(sections found: {list(sections.keys())})")

    return result


# --------------------------------------------------------------------------- #
# Phase 3 — Groq fallback (only when section parser found nothing)
# --------------------------------------------------------------------------- #
_EXTRACT_PROMPT = """You are parsing a student's resume. Extract ALL projects and internships you can find.

RESUME:
{text}

Return ONLY valid JSON, no markdown fences, no commentary. Use this exact structure:
{{
  "thesis_title": "full thesis title or empty string",
  "thesis_summary": "one sentence summary or empty string",
  "projects": [
    {{"name": "project name", "tech_stack": "tools/languages used", "outcome": "result or impact"}}
  ],
  "internships": [
    {{"company": "company name", "role": "job title", "achievement": "what you built or achieved"}}
  ],
  "courses": ["course1", "course2"],
  "skills": ["skill1", "skill2"],
  "publications": [],
  "achievements": ["achievement1"]
}}
Rules: include up to 4 projects, 3 internships, 12 skills, 6 courses. If a field is not in the resume, use an empty list or empty string. Do NOT invent anything not in the resume."""


def _groq_extract(text: str) -> dict:
    """Groq fallback — only called if section parser found 0 projects and 0 internships."""
    from config.llm_provider import extract_json
    llm = get_routing_model(temperature=0.0)
    raw = llm.invoke(_EXTRACT_PROMPT.format(text=text[:6000])).content
    result = extract_json(raw)
    print(f"[resume_parser] groq fallback: {len(result.get('projects', []))} projects, "
          f"{len(result.get('internships', []))} internships")
    return result


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def parse_resume(file_path: str) -> EnrichedProfile:
    """Extract structured profile from a resume PDF.

    1. fitz reads the PDF text (no API call)
    2. Regex extracts name/email/CGPA/degree (no API call)
    3. Section parser extracts projects/internships/skills (no API call)
    4. Groq fallback ONLY if section parser found nothing (rare — unusual layouts)
    """
    raw = read_student_doc.invoke({"file_path": file_path})

    if raw.get("error") and not raw.get("text"):
        raise ValueError(raw["error"])

    text = raw.get("text", "").strip()
    if not text:
        raise ValueError(
            "Could not extract text from this PDF. "
            "Please make sure it is a text-based PDF (not a scanned image). "
            "Try copy-pasting text from the PDF to confirm."
        )
    chars = raw.get("chars", len(text))

    # Phase 1 — regex
    basic = _fast_extract(text)

    # Phase 2 — section parser (zero API calls)
    extracted = _section_extract(text)

    # Phase 3 — Groq fallback when section parser found nothing OR extracted
    # suspicious entries (e.g. project name = "2026" or very short < 4 chars).
    def _suspicious(entries: list[dict], key: str) -> bool:
        if not entries:
            return False
        bad = sum(1 for e in entries
                  if re.match(r"^\d{4}$", e.get(key, "")) or len(e.get(key, "")) < 4)
        return bad > len(entries) // 2

    needs_fallback = (
        (not extracted["projects"] and not extracted["internships"])
        or _suspicious(extracted["projects"], "name")
        or _suspicious(extracted["internships"], "company")
    )
    if needs_fallback:
        print("[resume_parser] section parser result looks wrong — trying Groq fallback")
        try:
            extracted = _groq_extract(text)
        except Exception as exc:
            print(f"[resume_parser] Groq fallback failed: {exc} — using section-parser result")

    projects = [
        ProjectItem(
            name=p.get("name", ""),
            tech_stack=p.get("tech_stack", ""),
            outcome=p.get("outcome", ""),
        )
        for p in extracted.get("projects", [])
        if isinstance(p, dict) and p.get("name")
    ]
    internships = [
        InternshipItem(
            company=i.get("company", ""),
            role=i.get("role", ""),
            achievement=i.get("achievement", ""),
        )
        for i in extracted.get("internships", [])
        if isinstance(i, dict) and i.get("company")
    ]

    return EnrichedProfile(
        name=basic.get("name", ""),
        email=basic.get("email", ""),
        cgpa=basic.get("cgpa", 0.0),
        degree=basic.get("degree", ""),
        thesis_title=extracted.get("thesis_title", ""),
        thesis_summary=extracted.get("thesis_summary", ""),
        top_projects=projects,
        internships=internships,
        relevant_courses=extracted.get("courses", []),
        skills=extracted.get("skills", []),
        publications=extracted.get("publications", []),
        achievements=extracted.get("achievements", []),
        raw_text_chars=chars,
    )


def enriched_to_context(ep: EnrichedProfile) -> str:
    """Convert an EnrichedProfile into the plain-text block injected into the SOP prompt."""
    parts = []
    if ep.thesis_title:
        parts.append(f"Thesis: {ep.thesis_title} — {ep.thesis_summary}")
    for p in ep.top_projects:
        parts.append(f"Project · {p.name} ({p.tech_stack}): {p.outcome}")
    for i in ep.internships:
        parts.append(f"Internship · {i.role} at {i.company}: {i.achievement}")
    if ep.relevant_courses:
        parts.append("Relevant courses: " + ", ".join(ep.relevant_courses))
    if ep.skills:
        parts.append("Skills: " + ", ".join(ep.skills))
    for pub in ep.publications:
        parts.append(f"Publication: {pub}")
    for ach in ep.achievements:
        parts.append(f"Achievement: {ach}")
    return "\n".join(parts)
