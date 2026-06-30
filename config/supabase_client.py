"""
Supabase client factory.

Two clients:
  - anon_client  : uses the anon key — for frontend-equivalent ops, respects RLS
  - admin_client : uses service_role key — bypasses RLS, for server-side writes
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from config.settings import settings


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)


@lru_cache(maxsize=1)
def get_admin_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
