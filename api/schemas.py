"""Request / response schemas for the AdmitAI FastAPI backend."""
from __future__ import annotations
from pydantic import BaseModel, Field


# Legacy stubs kept so old imports don't break
class RegisterIn(BaseModel):
    email: str
    password: str
    name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    ok: bool
    token: str = ""
    user_id: str = ""
    name: str = ""
    error: str = ""


class ProfileUpdateIn(BaseModel):
    name: str | None = None
    cgpa: float | None = None
    degree: str | None = None
    degree_field: str | None = None
    graduation_year: int | None = None
    target_intake: str | None = None
    application_level: str | None = None
    target_field: str | None = None
    ielts_score: float | None = None
    toefl_score: int | None = None
    gre_score: int | None = None
    work_experience_months: int | None = None
    has_research: bool | None = None
    has_publications: bool | None = None
    motivation: str | None = None
    profile_complete: bool | None = None
    onboarding_step: str | None = None


class StudentProfileIn(BaseModel):
    name: str = "Anonymous"
    degree: str = ""
    cgpa: float = 0.0
    target_field: str = "Computer Science"
    target_country: str = "Germany"
    work_experience_years: float = 0.0
    language_tests: list[str] = Field(default_factory=list)
    interests: str = ""
    email: str = "student@example.com"
    target_intake: str = "winter"
    application_level: str = "masters"
    preferred_institution_type: str | None = None
    preferred_funding: str | None = None


class ChatRequest(BaseModel):
    query: str
    profile: StudentProfileIn
    thread_id: str = "default"
    selected_university: str = ""
    resume_enriched: dict = Field(default_factory=dict)
    context: str = ""  # extra context for university-specific chat


class ChatResponse(BaseModel):
    response: str
    route: str = ""
    eligibility_scores: list[dict] = Field(default_factory=list)
    sop_drafts: list[dict] = Field(default_factory=list)
    scholarship_matches: list[dict] = Field(default_factory=list)
    checklist: list[dict] = Field(default_factory=list)
    programs: list[dict] = Field(default_factory=list)


class ResumeParseResponse(BaseModel):
    ok: bool
    enriched: dict = Field(default_factory=dict)
    error: str = ""
