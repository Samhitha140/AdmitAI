"""
Central configuration for IntelliAdmit.

Everything is environment-driven so the project runs in three modes:

  1. FULL    - real Gemini + real MCP servers + a fine-tuned Mistral adapter
  2. PARTIAL - real Gemini, mock MCP/SOP (no servers / no GPU needed)
  3. MOCK    - no API keys at all; deterministic stubs so the graph still runs

This lets the whole LangGraph pipeline be demo'd end-to-end on a laptop with
zero credentials, then upgraded to production by setting env vars.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path

    # override=True ensures .env values always win over stale system env vars
    _env_file = _Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_file, override=True)
except Exception:
    pass


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
UNI_DOCS_DIR = DATA_DIR / "uni_docs"
SOP_DATASET_DIR = DATA_DIR / "sop_dataset"
CHROMA_DIR = ROOT_DIR / ".chroma"
BM25_CACHE = ROOT_DIR / ".bm25_index.pkl"


class Settings:
    """Resolved runtime settings."""

    # --- Supabase -----------------------------------------------------------
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # --- LLM provider keys --------------------------------------------------
    GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")
    GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
    CEREBRAS_API_KEY: str | None = os.getenv("CEREBRAS_API_KEY")
    SERPER_API_KEY: str | None = os.getenv("SERPER_API_KEY")
    TAVILY_API_KEY: str | None = os.getenv("TAVILY_API_KEY")
    HF_TOKEN: str | None = os.getenv("HUGGINGFACE_TOKEN")
    LANGSMITH_API_KEY: str | None = os.getenv("LANGCHAIN_API_KEY")
    GPTZERO_API_KEY: str | None = os.getenv("GPTZERO_API_KEY")

    # --- Model names --------------------------------------------------------
    SUPERVISOR_MODEL: str = os.getenv("SUPERVISOR_MODEL", "gemini-2.0-flash")
    AGENT_MODEL: str = os.getenv("AGENT_MODEL", "gemini-2.0-flash")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    CEREBRAS_MODEL: str = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
    BASE_SOP_MODEL: str = os.getenv("BASE_SOP_MODEL", "microsoft/phi-2")
    SOP_ADAPTER: str = os.getenv("SOP_ADAPTER", "allisamhitha/intelliadmit-sop-lora")
    # Merged full model (LoRA weights baked in) — required for HF Inference API
    SOP_MODEL_MERGED: str = os.getenv("SOP_MODEL_MERGED", "")

    # --- RAG -----------------------------------------------------------------
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    BM25_TOP_K: int = int(os.getenv("BM25_TOP_K", "5"))
    VECTOR_TOP_K: int = int(os.getenv("VECTOR_TOP_K", "5"))
    FINAL_TOP_K: int = int(os.getenv("FINAL_TOP_K", "8"))
    RRF_K: int = int(os.getenv("RRF_K", "60"))  # reciprocal-rank-fusion constant

    # --- MCP server endpoints ----------------------------------------------
    BROWSER_MCP_URL: str | None = os.getenv("BROWSER_MCP_URL")
    GMAIL_MCP_URL: str | None = os.getenv("GMAIL_MCP_URL")
    DRIVE_MCP_URL: str | None = os.getenv("DRIVE_MCP_URL")
    PDF_MCP_URL: str | None = os.getenv("PDF_MCP_URL")
    # scholarship source (DAAD scholarship database scraped via Browser MCP, or a
    # dedicated scholarship MCP server); falls back to the bundled DAAD snapshot.
    SCHOLARSHIP_MCP_URL: str | None = os.getenv("SCHOLARSHIP_MCP_URL")

    # --- LangSmith tracing ---------------------------------------------------
    LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
    LANGCHAIN_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "intelliadmit")

    @property
    def has_supabase(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_ANON_KEY)

    @property
    def has_gemini(self) -> bool:
        return bool(self.GOOGLE_API_KEY)

    @property
    def has_groq(self) -> bool:
        return bool(self.GROQ_API_KEY)

    @property
    def has_cerebras(self) -> bool:
        return bool(self.CEREBRAS_API_KEY)

    @property
    def has_serper(self) -> bool:
        return bool(self.SERPER_API_KEY)

    @property
    def mode(self) -> str:
        if self.has_gemini and self.BROWSER_MCP_URL:
            return "FULL"
        if self.has_gemini:
            return "PARTIAL"
        return "MOCK"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
