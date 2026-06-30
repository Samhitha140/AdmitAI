"""
SOP Drafting Agent — resume-grounded with few-shot style examples.

Context layers injected into the prompt:
  1. A matching SOP from the fine-tuned dataset (same field + institution type)
     — gives Gemini a style model; prevents placeholder output
  2. Student typed profile (CGPA, degree, intake, level)
  3. Enriched resume facts (thesis, projects, internships) — only if present
  4. Program requirements for the selected university
"""
from __future__ import annotations

import json
from pathlib import Path

from agents.resume_parser import EnrichedProfile, enriched_to_context
from config.llm_provider import get_chat_model, get_sop_fallback_model
from graph.state import IntelliAdmitState, SOPDraft
from mcp_tools.drive_tool import save_sop

# ── Dataset path ──────────────────────────────────────────────────────────────
_DATASET = Path(__file__).parent.parent / "data" / "sop_dataset" / "sops.jsonl"


def _load_example_sop(field: str, inst_type: str) -> str:
    """Return the text of a matching SOP from the fine-tuned dataset."""
    if not _DATASET.exists():
        return ""
    field_lower = field.lower()
    best_field_only = None
    try:
        with _DATASET.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                p = entry.get("profile", {})
                ef = p.get("target_field", "").lower()
                et = p.get("institution_type", "")
                field_match = any(k in ef for k in field_lower.split()) or any(k in field_lower for k in ef.split())
                if field_match and et == inst_type:
                    return entry.get("response", "")
                if field_match and best_field_only is None:
                    best_field_only = entry.get("response", "")
    except Exception:
        pass
    return best_field_only or ""


# ── Prompts ───────────────────────────────────────────────────────────────────
_DRAFT_PROMPT_WITH_RESUME = """Write an accepted-quality Statement of Purpose for a German
university admission application.

EXAMPLE SOP — same field and institution type as this student (use as style reference ONLY,
do not copy content; notice how it names real projects and tools specifically):
---
{example_sop}
---

STUDENT PROFILE:
Name: {name}
Degree: {degree}
CGPA: {cgpa}
Target intake: {intake}
Application level: {level}

STUDENT'S ACTUAL BACKGROUND (from resume — use these EXACT details):
{resume_context}

TARGET PROGRAM: {university} — {program}
INSTITUTION TYPE: {institution_type}

PROGRAM CONTEXT (what this university looks for):
{rag_context}

Writing rules:
- Length: ~700 words
- Tone: formal German academic English — structured, precise
- Opening: state the specific program and why this student's background leads there
- Reference AT LEAST 2 of the student's ACTUAL projects or experiences listed above by name
- Mention specific tech stacks and outcomes (numbers help: "14% improvement", "deployed to 500 users")
- Name at least one specific course, research group, or professor at {university}
- For applied-sciences: emphasise practical impact and industry goals
- For research university: emphasise research depth and academic continuity
- Close with a concrete career goal tied to Germany's industry or research landscape
- No generic openers like "I have always been passionate about..."
- Do NOT write placeholder text like "[Insert Project Name Here]" — write a complete, final SOP
"""

_DRAFT_PROMPT_NO_RESUME = """Write an accepted-quality Statement of Purpose for a German
university admission application.

EXAMPLE SOP — same field and institution type (use as style reference ONLY):
---
{example_sop}
---

STUDENT PROFILE:
Name: {name}
Degree: {degree}
CGPA: {cgpa}
Target intake: {intake}
Application level: {level}

TARGET PROGRAM: {university} — {program}
INSTITUTION TYPE: {institution_type}

PROGRAM CONTEXT (what this university looks for):
{rag_context}

Writing rules:
- Length: ~700 words
- Tone: formal German academic English — structured, precise
- No resume was provided — write based on the student's degree subject and academic profile
- Open with the student's academic background in {degree} and how it leads to this program
- Discuss how {target_field} aligns with the student's degree foundations
- Name at least one specific course, research group, or professor at {university}
- For applied-sciences: emphasise practical orientation and industry goals
- For research university: emphasise academic depth and research interest
- Close with a concrete career goal in Germany's {target_field} industry
- Do NOT write placeholder text like "[Insert Name Here]" — write a complete, final SOP
- Do NOT mention that the student has no resume or projects
"""


def _select_program(state: IntelliAdmitState) -> dict:
    """Return the user-selected university if set, else the highest-scoring one."""
    selected = state.get("selected_university", "")
    programs = state.get("target_programs", [])
    scores = state.get("eligibility_scores", [])

    if selected:
        for p in programs:
            if selected.lower() in p.get("university", "").lower():
                return p

    if scores:
        best = max(scores, key=lambda s: s.get("fit_score", 0))
        for p in programs:
            if p["university"] == best["university"]:
                return p

    return programs[0] if programs else {
        "university": "TU Munich",
        "program": "MSc Informatics",
        "institution_type": "university",
    }


def _web_context(university: str, program_name: str) -> str:
    """Fetch live program details from DuckDuckGo in parallel with a 10s cap.

    IMPORTANT: uses shutdown(wait=False) so stuck DDG threads never block the
    SOP pipeline — the context manager's shutdown(wait=True) would hang forever
    if a DDG request stalls without hitting its own network timeout.
    """
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout
        from ddgs import DDGS

        queries = [
            f"{university} {program_name} curriculum professors research groups",
            f"{university} admission requirements CGPA language",
        ]

        def _one_search(q: str) -> list[str]:
            try:
                return [r.get("body", "") for r in DDGS().text(q, max_results=1) if r.get("body")]
            except Exception:
                return []

        snippets: list[str] = []
        pool = ThreadPoolExecutor(max_workers=2)
        futs = [pool.submit(_one_search, q) for q in queries]
        for fut in futs:
            try:
                snippets.extend(fut.result(timeout=10))
            except (FTimeout, Exception):
                pass
        pool.shutdown(wait=False)  # don't block on stuck threads

        combined = " ".join(snippets)[:2000].strip()
        if combined:
            print(f"[sop_agent] web context: {len(combined)} chars for {university}")
        return combined
    except Exception as exc:
        print(f"[sop_agent] web context skipped: {exc}")
        return ""


def sop_node(state: IntelliAdmitState) -> dict:
    profile = state.get("student_profile", {})
    program = _select_program(state)

    # Start with hardcoded requirements from mock, then enrich with live web context
    base_requirements = "\n".join(program.get("requirements", []))
    live_context = _web_context(program["university"], program.get("program", ""))
    rag_context = "\n".join(filter(None, [base_requirements, live_context]))
    if not rag_context:
        rag_context = f"Admission to {program['university']} {program.get('program', '')}."

    institution_type = program.get("institution_type", "university")
    target_field = profile.get("target_field", "Computer Science")

    example_sop = _load_example_sop(target_field, institution_type)

    # Check if enriched resume has actual content (not just empty defaults)
    enriched_raw = state.get("resume_enriched") or {}
    has_projects = bool(enriched_raw.get("top_projects"))
    has_thesis = bool(enriched_raw.get("thesis_title"))
    has_internships = bool(enriched_raw.get("internships"))
    has_resume_content = has_projects or has_thesis or has_internships

    if has_resume_content:
        try:
            ep = EnrichedProfile(**enriched_raw)
        except Exception:
            has_resume_content = False

    if has_resume_content:
        resume_context = enriched_to_context(ep)
        prompt = _DRAFT_PROMPT_WITH_RESUME.format(
            example_sop=example_sop or "(no example available)",
            name=profile.get("name", "the student"),
            degree=profile.get("degree") or profile.get("degree_field", ""),
            cgpa=profile.get("cgpa", ""),
            intake=profile.get("target_intake", "winter"),
            level=profile.get("application_level", "masters"),
            resume_context=resume_context,
            university=program["university"],
            program=program["program"],
            institution_type=institution_type,
            rag_context=rag_context,
        )
    else:
        prompt = _DRAFT_PROMPT_NO_RESUME.format(
            example_sop=example_sop or "(no example available)",
            name=profile.get("name", "the student"),
            degree=profile.get("degree") or profile.get("degree_field", ""),
            cgpa=profile.get("cgpa", ""),
            intake=profile.get("target_intake", "winter"),
            level=profile.get("application_level", "masters"),
            university=program["university"],
            program=program["program"],
            institution_type=institution_type,
            rag_context=rag_context,
            target_field=target_field,
        )

    # Try phi-2 fine-tuned model first (HF Serverless API or local GPU).
    # Runs in a capped thread so a slow/stuck HF cold-start never blocks the pipeline.
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout
    from finetuning.inference import generate_sop
    from config.settings import settings as _s

    draft_text = None
    _phi2_available = bool(_s.SOP_MODEL_MERGED and _s.HF_TOKEN)
    import shutil as _shutil
    _has_gpu = bool(_shutil.which("nvidia-smi"))

    if _phi2_available or _has_gpu:
        _phi_pool = ThreadPoolExecutor(max_workers=1)
        _phi_fut = _phi_pool.submit(generate_sop, profile, program, rag_context)
        try:
            draft_text = _phi_fut.result(timeout=130)  # 130s: covers HF cold-start (~60s) + generation
            print(f"[sop_agent] phi-2 SOP ready ({len(draft_text)} chars)")
        except FTimeout:
            print("[sop_agent] phi-2 timed out — falling back to Gemini")
        except Exception as exc:
            print(f"[sop_agent] phi-2 unavailable: {exc} — falling back to Gemini")
        _phi_pool.shutdown(wait=False)
    else:
        print("[sop_agent] SOP_MODEL_MERGED not set — using Gemini directly")

    if not draft_text:
        try:
            llm = get_chat_model(temperature=0.7)
            draft_text = llm.invoke(prompt).content
            print("[sop_agent] SOP generated via Gemini")
        except Exception as exc:
            # Catch all Gemini failures: 503 overload, 429 quota, 400 bad request, network errors, etc.
            print(f"[sop_agent] Gemini unavailable ({type(exc).__name__}: {str(exc)[:100]}) — falling back to Cerebras/Groq")
            try:
                llm_fallback = get_sop_fallback_model(temperature=0.7)
                draft_text = llm_fallback.invoke(prompt).content
                print(f"[sop_agent] SOP generated via {llm_fallback.model_name} fallback")
            except Exception as fallback_exc:
                print(f"[sop_agent] all providers failed: {fallback_exc}")
                draft_text = (
                    "⚠️ SOP generation failed — Gemini is currently unavailable and the fallback also failed.\n\n"
                    "Please try again in a few minutes. If the problem persists, check that "
                    "CEREBRAS_API_KEY and GROQ_API_KEY are set correctly in .env."
                )

    # Strip any meta-commentary Gemini sometimes adds before the SOP
    for marker in ["---\n", "Statement of Purpose\n", "SOP:\n"]:
        if marker in draft_text:
            draft_text = draft_text.split(marker, 1)[-1].strip()

    # Strip boilerplate phrases locally (no model — avoids OOM on low-RAM machines)
    from finetuning.humanizer import _strip_boilerplate
    draft_text = _strip_boilerplate(draft_text)
    detection_note = "Boilerplate removed"
    print(f"[sop_agent] SOP ready ({len(draft_text)} chars) | resume_content={has_resume_content}")

    draft = SOPDraft(
        university=program["university"],
        program=program["program"],
        text=draft_text,
        version=len(state.get("sop_drafts", [])) + 1,
        critique=detection_note,
    )

    saved = save_sop.invoke({
        "university": draft.university,
        "program": draft.program,
        "version": draft.version,
        "text": draft.text,
    })
    draft.drive_url = saved.get("drive_url", "")

    return {
        "sop_drafts": [draft.model_dump()],
        "current_agent": "sop",
        "awaiting_sop_approval": True,
        "conversation_history": [
            {"role": "assistant", "content": f"Drafted SOP v{draft.version} for {draft.university}."}
        ],
    }
