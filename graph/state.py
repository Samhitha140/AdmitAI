"""
Shared graph state and the structured-output schemas used by the agents.

The `IntelliAdmitState` TypedDict is the single object every LangGraph node
reads from and writes to. The `Annotated[..., add]` reducers let parallel
nodes append to the same list without clobbering each other.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Domain models (also reused as structured-output schemas)
# --------------------------------------------------------------------------- #
class StudentProfile(BaseModel):
    name: str = "Anonymous"
    degree: str = Field("", description="e.g. B.Tech Computer Science")
    cgpa: float = Field(0.0, description="On a 0-10 scale")
    target_country: str = "Germany"
    target_field: str = ""
    work_experience_years: float = 0.0
    language_tests: list[str] = Field(default_factory=list)  # e.g. ["IELTS 7.0"]
    interests: str = ""
    # which semester the student is applying for; drives every deadline
    target_intake: Literal["winter", "summer"] = "winter"
    # are they applying for an undergraduate or postgraduate degree?
    application_level: Literal["bachelors", "masters"] = "masters"
    # optional hard filters (None = no preference, show both)
    preferred_institution_type: Optional[Literal["university", "applied_sciences"]] = None
    preferred_funding: Optional[Literal["public", "private"]] = None


class ProgramInfo(BaseModel):
    university: str
    program: str
    # bachelors (undergraduate) vs masters (postgraduate)
    program_level: Literal["bachelors", "masters"] = "masters"
    # Universität vs Fachhochschule / Hochschule für Angewandte Wissenschaften (HAW)
    institution_type: Literal["university", "applied_sciences"] = "university"
    # public = ~free (semester fee only); private = real tuition
    funding_type: Literal["public", "private"] = "public"
    # only meaningful for private institutions; public ones are recognised by default
    state_recognized: bool = True
    deadline: str = "unknown"                      # kept for back-compat / display
    intakes_offered: list[str] = Field(default_factory=lambda: ["winter"])
    deadlines: dict[str, str] = Field(default_factory=dict)  # {"winter": "...", "summer": "..."}
    tuition_eur: str = "0 (public)"
    language_requirement: str = ""
    aps_required: bool = True
    requirements: list[str] = Field(default_factory=list)
    source_url: str = ""


class EligibilityResult(BaseModel):
    university: str = ""
    program: str = ""
    institution_type: str = ""        # university | applied_sciences
    funding_type: str = ""            # public | private
    intake: str = ""                  # the intake this result was scored for
    intake_available: bool = True     # is the program offered in that intake?
    fit_score: int = Field(0, ge=0, le=100)
    met_requirements: list[str] = Field(default_factory=list)
    unmet_requirements: list[str] = Field(default_factory=list)
    borderline_requirements: list[str] = Field(default_factory=list)
    cost_note: str = ""               # tuition / recognition flag for the student
    recommendation: str = ""


class SOPDraft(BaseModel):
    university: str = ""
    program: str = ""
    text: str = ""
    version: int = 1
    drive_url: str = ""
    critique: str = ""


class ChecklistItem(BaseModel):
    task: str
    due_date: str = ""
    done: bool = False


class ScholarshipMatch(BaseModel):
    name: str = ""
    provider: str = ""                          # DAAD, Deutschlandstipendium, Erasmus+, ...
    levels: list[str] = Field(default_factory=list)  # which levels it funds, e.g. ["masters"]
    fields: str = "all"                         # subject scope, e.g. "STEM" / "all"
    amount_eur_month: str = ""                  # stipend, e.g. "~992 EUR/month"
    covers: list[str] = Field(default_factory=list)  # ["stipend", "health insurance", "travel"]
    deadline: str = ""
    eligible: bool = True                       # eligible for THIS student?
    eligibility_note: str = ""                  # why eligible / not
    source_url: str = ""


# --------------------------------------------------------------------------- #
# Graph state
# --------------------------------------------------------------------------- #
RouteDecision = Literal[
    "research_eligibility",  # program search
    "full_sop",              # research -> eligibility -> sop
    "tracker_only",          # deadline / checklist check
    "scholarship",           # find funding / scholarships
    "respond",               # nothing to do, just answer
]


class IntelliAdmitState(TypedDict, total=False):
    # inputs
    query: str
    student_profile: dict[str, Any]
    thread_id: str

    # routing
    route: RouteDecision
    plan: list[str]

    # agent outputs (parallel-safe with reducers)
    target_programs: Annotated[list[dict], operator.add]
    retrieved_docs: Annotated[list[dict], operator.add]
    eligibility_scores: Annotated[list[dict], operator.add]
    sop_drafts: Annotated[list[dict], operator.add]
    scholarship_matches: Annotated[list[dict], operator.add]
    application_checklist: list[dict]

    # conversation
    conversation_history: Annotated[list[dict], operator.add]
    current_agent: str
    final_response: str

    # human-in-the-loop
    awaiting_sop_approval: bool

    # resume + university selection (set by the frontend/API before graph runs)
    resume_enriched: dict        # EnrichedProfile.model_dump() after parsing
    selected_university: str     # university name the student explicitly chose for SOP


def initial_state(query: str, profile: dict, thread_id: str = "default") -> IntelliAdmitState:
    return IntelliAdmitState(
        query=query,
        student_profile=profile,
        thread_id=thread_id,
        target_programs=[],
        retrieved_docs=[],
        eligibility_scores=[],
        sop_drafts=[],
        scholarship_matches=[],
        application_checklist=[],
        conversation_history=[{"role": "user", "content": query}],
        current_agent="supervisor",
        final_response="",
        awaiting_sop_approval=False,
        resume_enriched={},
        selected_university="",
    )
