"""
Database layer — all persistence via Supabase.
Uses admin client (service_role) for server-side writes so RLS is bypassed
safely on the backend. Frontend reads use the anon client respecting RLS.
"""
from __future__ import annotations

from config.supabase_client import get_admin_client


# ── Profile ───────────────────────────────────────────────────────────────────

def load_profile(user_id: str) -> dict:
    client = get_admin_client()
    try:
        res = client.table("profiles").select("*").eq("id", user_id).single().execute()
        return res.data or {}
    except Exception:
        return {}


def save_profile(user_id: str, data: dict) -> None:
    client = get_admin_client()
    client.table("profiles").upsert({"id": user_id, **data}).execute()


# ── Resume ────────────────────────────────────────────────────────────────────

def save_resume(user_id: str, filename: str, enriched: dict) -> None:
    client = get_admin_client()
    client.table("profiles").upsert({
        "id": user_id,
        "enriched_resume": enriched,
        "onboarding_step": "ai_questions",
    }).execute()


def load_resume(user_id: str) -> dict:
    client = get_admin_client()
    try:
        res = (
            client.table("profiles")
            .select("enriched_resume")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return (res.data or {}).get("enriched_resume") or {}
    except Exception:
        return {}


# ── Universities ──────────────────────────────────────────────────────────────

def get_universities(type_filter: str | None = None, limit: int = 200) -> list[dict]:
    client = get_admin_client()
    q = client.table("universities").select("*").limit(limit)
    if type_filter:
        q = q.eq("type", type_filter)
    res = q.execute()
    return res.data or []


def get_university(university_id: str) -> dict | None:
    client = get_admin_client()
    try:
        res = client.table("universities").select("*").eq("id", university_id).single().execute()
        return res.data
    except Exception:
        return None


def upsert_university(data: dict) -> dict:
    client = get_admin_client()
    res = client.table("universities").upsert(data, on_conflict="name").execute()
    return res.data[0] if res.data else {}


# ── University scores ─────────────────────────────────────────────────────────

def save_score(user_id: str, university_id: str, program: str, score_data: dict) -> None:
    client = get_admin_client()
    client.table("university_scores").upsert({
        "user_id": user_id,
        "university_id": university_id,
        "program": program,
        **score_data,
    }, on_conflict="user_id,university_id,program").execute()


def get_scores(user_id: str) -> list[dict]:
    client = get_admin_client()
    try:
        res = (
            client.table("university_scores")
            .select("*, universities(name, city, type, ranking_qs, image_url)")
            .eq("user_id", user_id)
            .order("fit_score", desc=True)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


# ── Applications ──────────────────────────────────────────────────────────────

def create_application(user_id: str, data: dict) -> dict:
    client = get_admin_client()
    res = client.table("applications").upsert(
        {"user_id": user_id, **data},
        on_conflict="user_id,university_id,program",
    ).execute()
    return res.data[0] if res.data else {}


def get_applications(user_id: str) -> list[dict]:
    client = get_admin_client()
    try:
        res = (
            client.table("applications")
            .select("*, universities(name, city, type, image_url)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def update_application(application_id: str, user_id: str, data: dict) -> dict:
    client = get_admin_client()
    res = (
        client.table("applications")
        .update(data)
        .eq("id", application_id)
        .eq("user_id", user_id)
        .execute()
    )
    return res.data[0] if res.data else {}


# ── LOR templates ─────────────────────────────────────────────────────────────

def get_lor_templates() -> list[dict]:
    client = get_admin_client()
    res = client.table("lor_templates").select("*").execute()
    return res.data or []


# ── Legacy stubs — kept so old imports don't break ────────────────────────────

def register(email: str, password: str, name: str) -> dict:
    return {"ok": False, "error": "Use Google OAuth via Supabase"}


def login(email: str, password: str) -> dict:
    return {"ok": False, "error": "Use Google OAuth via Supabase"}


def logout(token: str) -> None:
    pass


def get_user_by_token(token: str) -> dict | None:
    return None
