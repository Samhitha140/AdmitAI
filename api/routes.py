"""
AdmitAI — API routes.

Flow:
  1. Google OAuth via Supabase (frontend handles, sends access_token)
  2. POST /api/resume/upload  — parse PDF, save enriched profile
  3. GET  /api/profile/gaps   — AI identifies missing info, returns questions
  4. PUT  /api/profile        — save completed profile
  5. POST /api/match          — run eligibility + scoring against all universities
  6. GET  /api/universities   — list universities (with scores if logged in)
  7. GET  /api/universities/:id — full university detail
  8. POST /api/applications   — start application (triggers SOP generation)
  9. PUT  /api/applications/:id — update status / save SOP / save LOR
  10. GET /api/applications   — user's application board
  11. GET /api/lor-templates  — LOR template list
"""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.auth import optional_user, require_user
from api.database import (
    create_application,
    get_applications,
    get_lor_templates,
    get_scores,
    get_universities,
    get_university,
    load_profile,
    load_resume,
    save_profile,
    save_resume,
    save_score,
    update_application,
    upsert_university,
)
from api.schemas import (
    ChatRequest,
    ChatResponse,
    ProfileUpdateIn,
    ResumeParseResponse,
)

router = APIRouter()

# Simple TTL cache for universities — avoids a Supabase round-trip on every page load
_uni_cache: list[dict] = []
_uni_cache_ts: float = 0.0
_UNI_TTL = 300  # 5 minutes


async def _get_universities_cached(type_filter: str | None = None) -> list[dict]:
    global _uni_cache, _uni_cache_ts
    now = time.monotonic()
    if not type_filter and _uni_cache and (now - _uni_cache_ts) < _UNI_TTL:
        return _uni_cache
    unis = await asyncio.to_thread(get_universities, type_filter)
    if not type_filter:
        _uni_cache = unis
        _uni_cache_ts = now
    return unis


# ── Health / Admin ────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict:
    from config.settings import settings
    return {"status": "ok", "mode": settings.mode, "app": "AdmitAI"}


@router.post("/admin/cache/clear")
async def clear_cache() -> dict:
    global _uni_cache, _uni_cache_ts
    _uni_cache = []
    _uni_cache_ts = 0.0
    return {"ok": True, "msg": "University cache cleared"}


@router.post("/admin/sync-universities")
async def sync_universities_from_daad() -> dict:
    """
    Fetch all German public university programs from DAAD and upsert into Supabase.
    Runs server-side so local network/SSL issues on the dev machine don't matter.
    This can take 30–90 seconds depending on DAAD API response time.
    """
    global _uni_cache, _uni_cache_ts
    try:
        from data.fetch_daad_universities import run_sync
        result = await asyncio.to_thread(run_sync, False)
        # Bust cache so the fresh data is served immediately
        _uni_cache = []
        _uni_cache_ts = 0.0
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Auth / Profile ────────────────────────────────────────────────────────────

@router.get("/auth/me")
async def me(user: dict = Depends(require_user)) -> dict:
    profile = load_profile(user["id"])
    return {"ok": True, "user": user, "profile": profile}


@router.put("/profile")
async def update_profile(
    body: ProfileUpdateIn,
    user: dict = Depends(require_user),
) -> dict:
    save_profile(user["id"], body.model_dump(exclude_none=True))
    return {"ok": True}


# ── Resume ────────────────────────────────────────────────────────────────────

@router.post("/resume/upload", response_model=ResumeParseResponse)
async def upload_resume(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
) -> ResumeParseResponse:
    from agents.resume_parser import parse_resume

    if not file.filename.lower().endswith(".pdf"):
        return ResumeParseResponse(ok=False, error="Only PDF files are supported")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        enriched = parse_resume(tmp_path)
        enriched_dict = enriched.model_dump()
        save_resume(user["id"], file.filename, enriched_dict)
        return ResumeParseResponse(ok=True, enriched=enriched_dict)
    except Exception as exc:
        return ResumeParseResponse(ok=False, error=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/resume")
async def get_resume(user: dict = Depends(require_user)) -> dict:
    return {"ok": True, "resume": load_resume(user["id"])}


@router.get("/profile/gaps")
async def get_profile_gaps(user: dict = Depends(require_user)) -> dict:
    """AI analyses the extracted resume and returns questions for missing info."""
    from agents.profile_agent import get_gap_questions
    profile = load_profile(user["id"])
    resume = load_resume(user["id"])
    questions = get_gap_questions(profile, resume)
    return {"ok": True, "questions": questions}


# ── Universities ──────────────────────────────────────────────────────────────

@router.get("/universities")
async def list_universities(
    type: str | None = None,
    user: dict | None = Depends(optional_user),
) -> dict:
    if user:
        unis, scores_list = await asyncio.gather(
            _get_universities_cached(type),
            asyncio.to_thread(get_scores, user["id"]),
        )
        scores = {s["university_id"]: s for s in scores_list}
    else:
        unis = await _get_universities_cached(type)
        scores = {}
    for u in unis:
        if u["id"] in scores:
            u["fit_score"] = scores[u["id"]]["fit_score"]
            u["recommendation"] = scores[u["id"]]["recommendation"]
    return {"ok": True, "universities": unis}


@router.get("/universities/{university_id}")
async def university_detail(
    university_id: str,
    user: dict | None = Depends(optional_user),
) -> dict:
    uni = await asyncio.to_thread(get_university, university_id)
    if not uni:
        raise HTTPException(status_code=404, detail="University not found")
    if user:
        scores = await asyncio.to_thread(get_scores, user["id"])
        for s in scores:
            if s["university_id"] == university_id:
                uni["fit_score"] = s["fit_score"]
                uni["recommendation"] = s["recommendation"]
                uni["strengths"] = s["strengths"]
                uni["gaps"] = s["gaps"]
                break
    return {"ok": True, "university": uni}


# ── Matching ──────────────────────────────────────────────────────────────────

@router.post("/match")
async def run_matching(user: dict = Depends(require_user)) -> dict:
    """Run eligibility scoring for all universities against the user's profile."""
    from agents.eligibility_agent import score_universities_for_user
    profile = load_profile(user["id"])
    resume = load_resume(user["id"])
    if not profile.get("target_field"):
        return {"ok": False, "error": "Complete your profile before matching"}

    scores = await asyncio.to_thread(score_universities_for_user, profile, resume)
    unis = await _get_universities_cached()
    uni_map = {u["name"].lower(): u["id"] for u in unis}

    for s in scores:
        uni_id = uni_map.get(s.get("university", "").lower())
        if uni_id:
            save_score(user["id"], uni_id, s.get("program", ""), {
                "fit_score": s.get("fit_score", 0),
                "reasoning": s.get("recommendation", ""),
                "strengths": s.get("met_requirements", []),
                "gaps": s.get("unmet_requirements", []),
                "recommendation": s.get("recommendation", ""),
            })
    return {"ok": True, "scores": scores}


@router.get("/scores")
async def get_user_scores(user: dict = Depends(require_user)) -> dict:
    return {"ok": True, "scores": await asyncio.to_thread(get_scores, user["id"])}


# ── Applications ──────────────────────────────────────────────────────────────

@router.post("/applications")
async def start_application(
    body: dict,
    user: dict = Depends(require_user),
) -> dict:
    """Create an application record. SOP generation triggered separately."""
    app = create_application(user["id"], {
        "university_id": body["university_id"],
        "university_name": body.get("university_name", ""),
        "program": body["program"],
        "target_intake": body.get("target_intake", ""),
        "status": "planning",
    })
    return {"ok": True, "application": app}


@router.get("/applications")
async def list_applications(user: dict = Depends(require_user)) -> dict:
    return {"ok": True, "applications": get_applications(user["id"])}


@router.put("/applications/{app_id}")
async def patch_application(
    app_id: str,
    body: dict,
    user: dict = Depends(require_user),
) -> dict:
    updated = update_application(app_id, user["id"], body)
    return {"ok": True, "application": updated}


@router.post("/applications/{app_id}/sop")
async def generate_sop_for_application(
    app_id: str,
    user: dict = Depends(require_user),
) -> dict:
    """Generate SOP for a specific application."""
    from graph.builder import run_query
    apps = await asyncio.to_thread(get_applications, user["id"])
    app = next((a for a in apps if str(a["id"]) == str(app_id)), None)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    profile = await asyncio.to_thread(load_profile, user["id"])
    resume = await asyncio.to_thread(load_resume, user["id"])

    # Ensure the profile has the minimum fields the supervisor requires.
    # Fill in any missing fields from the application itself so SOP can always run.
    profile = profile or {}
    if not profile.get("target_field"):
        profile["target_field"] = app.get("program", "Computer Science")
    if not profile.get("degree"):
        profile["degree"] = profile.get("degree_field", "B.Tech")
    if not profile.get("cgpa"):
        profile["cgpa"] = 7.0  # default — supervisor won't block on this

    state = await asyncio.to_thread(
        run_query,
        "generate my sop",
        profile,
        f"sop-{user['id']}-{app_id}",
        app["university_name"],
        resume,
    )
    drafts = state.get("sop_drafts", [])
    if drafts:
        sop_text = drafts[0].get("text", "")
        await asyncio.to_thread(
            update_application, app_id, user["id"], {
                "sop_text": sop_text,
                "sop_version": (app.get("sop_version") or 0) + 1,
                "status": "documents",
            }
        )
        return {"ok": True, "sop": sop_text, "version": (app.get("sop_version") or 0) + 1}

    # Supervisor might have asked for clarification instead of generating SOP
    final_resp = state.get("final_response", "")
    if final_resp and "need a few more details" in final_resp:
        return {"ok": False, "error": f"Profile incomplete — {final_resp}"}
    return {"ok": False, "error": "SOP generation failed — check server logs for details"}


# ── LOR Templates ─────────────────────────────────────────────────────────────

@router.get("/lor-templates")
async def list_lor_templates() -> dict:
    return {"ok": True, "templates": get_lor_templates()}


# ── Legacy chat (kept for backward compat) ────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: dict | None = Depends(optional_user)) -> ChatResponse:
    from graph.builder import run_query

    # Fast path: when a university context is provided, answer directly with an LLM
    # instead of running the full LangGraph pipeline. This powers the per-university
    # chat widget where all facts are already known and no student profile is needed.
    if req.context:
        try:
            from config.llm_provider import get_routing_model
            llm = get_routing_model(temperature=0.3)
            direct_prompt = (
                f"You are an expert on German university admissions. "
                f"Answer the student's question using the provided context.\n\n"
                f"Context: {req.context}\n\n"
                f"Question: {req.query}\n\n"
                f"Rules:\n"
                f"- German university application deadlines repeat on the same month/day every year.\n"
                f"- If the context gives a deadline pattern (MM-DD), apply it to whatever year the student asks about.\n"
                f"- Example: if winter deadline is 15 July and student asks about 2027, answer '15 July 2027'.\n"
                f"- Be specific about dates and numbers. Answer in 2-4 sentences."
            )
            answer = await asyncio.to_thread(lambda: llm.invoke(direct_prompt).content)
            return ChatResponse(response=answer, route="context_qa")
        except Exception as exc:
            print(f"[chat] context_qa path failed ({exc}), falling back to graph")

    profile = req.profile.model_dump()
    resume_enriched = req.resume_enriched

    if user:
        saved = await asyncio.to_thread(load_profile, user["id"])
        if saved:
            profile = {**saved, **{k: v for k, v in profile.items() if v}}
        if not resume_enriched:
            resume_enriched = await asyncio.to_thread(load_resume, user["id"])

    thread_id = f"user-{user['id']}" if user else req.thread_id

    state = await asyncio.to_thread(
        run_query,
        req.query, profile,
        thread_id,
        req.selected_university,
        resume_enriched,
    )

    score_map = {
        s["university"].strip().lower(): s
        for s in state.get("eligibility_scores", [])
    }
    programs = []
    for p in state.get("target_programs", []):
        score_entry = score_map.get(p.get("university", "").strip().lower(), {})
        programs.append({
            **p,
            "fit_score": score_entry.get("fit_score"),
            "recommendation": score_entry.get("recommendation", ""),
            "intake_available": score_entry.get("intake_available", True),
        })

    return ChatResponse(
        response=state.get("final_response", ""),
        route=state.get("route", ""),
        eligibility_scores=state.get("eligibility_scores", []),
        sop_drafts=state.get("sop_drafts", []),
        scholarship_matches=state.get("scholarship_matches", []),
        checklist=state.get("application_checklist", []),
        programs=programs,
    )
