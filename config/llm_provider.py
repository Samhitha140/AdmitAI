"""
LLM provider factory.

Returns a real Gemini chat model when GOOGLE_API_KEY is present, otherwise a
deterministic MockLLM that mimics the LangChain Runnable interface (invoke /
with_structured_output). The rest of the codebase only ever talks to this
factory, so swapping providers never touches agent logic.
"""
from __future__ import annotations

import json
import re
from typing import Any

from config.settings import settings


# --------------------------------------------------------------------------- #
# Mock LLM - keeps the whole graph runnable with no credentials
# --------------------------------------------------------------------------- #
class _MockStructured:
    """Mimics `llm.with_structured_output(Schema)`."""

    def __init__(self, schema: Any):
        self._schema = schema

    def invoke(self, prompt: Any) -> Any:
        text = prompt if isinstance(prompt, str) else str(prompt)
        return self._schema(**_mock_fields_for(self._schema, text))


class MockLLM:
    """A deterministic stand-in for a chat model."""

    model_name = "mock-llm"

    def invoke(self, prompt: Any, **_: Any) -> Any:
        text = prompt if isinstance(prompt, str) else getattr(prompt, "content", str(prompt))
        try:
            from langchain_core.messages import AIMessage

            return AIMessage(content=_mock_text(text))
        except Exception:
            return _Msg(_mock_text(text))


class _Msg:
    """Minimal message object exposing `.content` (langchain-free fallback)."""

    def __init__(self, content: str) -> None:
        self.content = content

    def with_structured_output(self, schema: Any) -> _MockStructured:
        return _MockStructured(schema)

    def bind_tools(self, tools: Any) -> "MockLLM":  # no-op, tools handled in nodes
        return self


def _mock_text(prompt: str) -> str:
    p = prompt.lower()
    if "statement of purpose" in p or "sop" in p:
        return (
            "Statement of Purpose\n\n"
            "My fascination with computational systems began during my undergraduate "
            "studies, where I discovered the elegance of turning theory into working "
            "software. I am applying to this program because its research focus aligns "
            "precisely with my goal of specialising in machine learning systems. "
            "[MOCK SOP - set GOOGLE_API_KEY or load the fine-tuned adapter for real output]"
        )
    if "route" in p or "supervisor" in p:
        return "research_eligibility"
    return "[MOCK LLM RESPONSE - configure a real provider in .env]"


def _mock_fields_for(schema: Any, text: str) -> dict:
    """Best-effort field population for any pydantic model the agents use."""
    fields = getattr(schema, "model_fields", {})
    out: dict[str, Any] = {}
    for name, field in fields.items():
        ann = str(field.annotation)
        if "int" in ann and "List" not in ann:
            out[name] = 72 if "score" in name else 1
        elif "float" in ann:
            out[name] = 0.72
        elif "List" in ann or "list" in ann:
            out[name] = []
        elif "bool" in ann:
            out[name] = True
        elif "dict" in ann.lower():
            out[name] = {}
        else:
            out[name] = f"[mock {name}]"
    # sensible defaults for the eligibility schema
    if "recommendation" in out:
        out["recommendation"] = "Strong fit on academics; verify language test timeline."
    return out


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class _GeminiMsg:
    """Minimal message object exposing `.content` (matches LangChain's AIMessage shape)."""

    def __init__(self, content: str) -> None:
        self.content = content


class _GeminiRestStructured:
    """Mimics `llm.with_structured_output(Schema)` using Gemini's JSON response mode."""

    def __init__(self, client: "_GeminiRestLLM", schema: Any):
        self._client = client
        self._schema = schema

    def invoke(self, prompt: Any) -> Any:
        text = prompt if isinstance(prompt, str) else str(prompt)
        schema_hint = self._schema.model_json_schema()
        full_prompt = (
            f"{text}\n\nRespond with ONLY a JSON object (no markdown fences, no "
            f"commentary) matching this JSON schema:\n{json.dumps(schema_hint)}"
        )
        raw = self._client._call(full_prompt, json_mode=True)
        data = extract_json(raw)
        return self._schema.model_validate(data)


class _GeminiRestLLM:
    """Direct REST client for Gemini, bypassing google-generativeai/langchain SDKs.

    Used because the official SDKs hang indefinitely on some Windows networks
    (likely security-software interference) even though plain HTTPS requests to
    the same endpoint succeed in ~2s. This mimics the small subset of the
    LangChain Runnable interface the rest of the codebase relies on.
    """

    def __init__(self, model: str, temperature: float, api_key: str):
        self.model_name = model
        self.temperature = temperature
        self.api_key = api_key

    def _call(self, prompt: str, json_mode: bool = False) -> str:
        import time

        import requests

        url = f"{_GEMINI_BASE}/{self.model_name}:generateContent?key={self.api_key}"
        generation_config: dict[str, Any] = {"temperature": self.temperature}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        # IMPORTANT: DO NOT use time.sleep() here — this method runs on the
        # async event loop thread and blocking it prevents uvicorn from handling
        # any other requests (health checks, etc.) and can crash the worker.
        # On 429, raise immediately so callers can return a user-friendly message.
        for attempt in range(2):
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 429:
                raise RuntimeError(
                    f"Gemini rate limit hit (429). Wait ~60s and try again. "
                    f"Detail: {resp.text[:200]}"
                )
            elif resp.status_code == 503:
                if attempt == 0:
                    continue  # single immediate retry on server overload
            else:
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
        resp.raise_for_status()
        return ""

    def invoke(self, prompt: Any, **_: Any) -> _GeminiMsg:
        text = prompt if isinstance(prompt, str) else getattr(prompt, "content", str(prompt))
        return _GeminiMsg(self._call(text))

    def with_structured_output(self, schema: Any) -> _GeminiRestStructured:
        return _GeminiRestStructured(self, schema)

    def bind_tools(self, tools: Any) -> "_GeminiRestLLM":  # no-op, tools handled in nodes
        return self


def get_chat_model(model: str | None = None, temperature: float = 0.2):
    """Return a chat model: real Gemini (via direct REST) if configured, else MockLLM.

    Use for quality-sensitive tasks: SOP generation only.
    Resume parsing and routing use get_routing_model() (Groq) to save Gemini quota.
    """
    if not settings.has_gemini:
        return MockLLM()
    return _GeminiRestLLM(
        model=model or settings.AGENT_MODEL,
        temperature=temperature,
        api_key=settings.GOOGLE_API_KEY,
    )


# --------------------------------------------------------------------------- #
# Groq — fast cheap model for routing / eligibility (OpenAI-compatible REST)
# --------------------------------------------------------------------------- #
_GROQ_BASE = "https://api.groq.com/openai/v1/chat/completions"


class _GroqMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _GroqRestStructured:
    """Mimics `llm.with_structured_output(Schema)` using Groq JSON mode."""

    def __init__(self, client: "_GroqRestLLM", schema: Any):
        self._client = client
        self._schema = schema

    def invoke(self, prompt: Any) -> Any:
        text = prompt if isinstance(prompt, str) else str(prompt)
        schema_hint = self._schema.model_json_schema()
        full_prompt = (
            f"{text}\n\nRespond with ONLY a JSON object (no markdown fences, no "
            f"commentary) matching this JSON schema:\n{json.dumps(schema_hint)}"
        )
        raw = self._client._call(full_prompt, json_mode=True)
        data = extract_json(raw)
        return self._schema.model_validate(data)


class _GroqRestLLM:
    """Direct REST client for Groq (OpenAI-compatible API).

    Free tier: 14,400 req/day — used for routing, eligibility scoring,
    and resume extraction so Gemini quota is reserved for SOP generation only.
    """

    def __init__(self, model: str, temperature: float, api_key: str):
        self.model_name = model
        self.temperature = temperature
        self.api_key = api_key

    def _call(self, prompt: str, json_mode: bool = False) -> str:
        import time

        import requests

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # No time.sleep — see comment in _GeminiRestLLM._call for why.
        for attempt in range(2):
            resp = requests.post(_GROQ_BASE, json=payload, headers=headers, timeout=30)
            if resp.status_code == 429:
                raise RuntimeError(f"Groq rate limit hit (429). Detail: {resp.text[:200]}")
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        resp.raise_for_status()
        return ""

    def invoke(self, prompt: Any, **_: Any) -> _GroqMsg:
        text = prompt if isinstance(prompt, str) else getattr(prompt, "content", str(prompt))
        return _GroqMsg(self._call(text))

    def with_structured_output(self, schema: Any) -> _GroqRestStructured:
        return _GroqRestStructured(self, schema)

    def bind_tools(self, tools: Any) -> "_GroqRestLLM":
        return self


def get_routing_model(temperature: float = 0.0):
    """Return the fast routing/scoring model.

    Priority: Groq (14 400 req/day free) → Gemini → MockLLM.
    Used by supervisor routing, eligibility scoring, and resume extraction
    so Gemini quota is reserved for SOP generation only.
    """
    if settings.has_groq:
        return _GroqRestLLM(
            model=settings.GROQ_MODEL,
            temperature=temperature,
            api_key=settings.GROQ_API_KEY,
        )
    return get_chat_model(temperature=temperature)


# --------------------------------------------------------------------------- #
# Cerebras — SOP fallback (OpenAI-compatible, ~1000 req/day free)
# --------------------------------------------------------------------------- #
_CEREBRAS_BASE = "https://api.cerebras.ai/v1/chat/completions"


class _CerebrasMsg:
    def __init__(self, content: str) -> None:
        self.content = content


class _CerebrasRestLLM:
    """Direct REST client for Cerebras (OpenAI-compatible API).

    Used as SOP fallback when Gemini's daily quota is exhausted.
    Cerebras runs llama-3.3-70b on custom silicon — very fast inference.
    """

    def __init__(self, model: str, temperature: float, api_key: str):
        self.model_name = model
        self.temperature = temperature
        self.api_key = api_key

    def _call(self, prompt: str) -> str:
        import requests

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(_CEREBRAS_BASE, json=payload, headers=headers, timeout=60)
        if resp.status_code == 429:
            raise RuntimeError(f"Cerebras rate limit hit (429). Detail: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def invoke(self, prompt: Any, **_: Any) -> _CerebrasMsg:
        text = prompt if isinstance(prompt, str) else getattr(prompt, "content", str(prompt))
        return _CerebrasMsg(self._call(text))

    def with_structured_output(self, schema: Any) -> "_GroqRestStructured":
        return _GroqRestStructured(self, schema)  # type: ignore[arg-type]

    def bind_tools(self, tools: Any) -> "_CerebrasRestLLM":
        return self


def get_sop_fallback_model(temperature: float = 0.7):
    """SOP fallback: Cerebras when Gemini quota is exhausted, then Groq.

    Priority: Cerebras (fastest, dedicated free tier) → Groq → MockLLM.
    """
    if settings.has_cerebras:
        return _CerebrasRestLLM(
            model=settings.CEREBRAS_MODEL,
            temperature=temperature,
            api_key=settings.CEREBRAS_API_KEY,
        )
    if settings.has_groq:
        return _GroqRestLLM(
            model=settings.GROQ_MODEL,
            temperature=temperature,
            api_key=settings.GROQ_API_KEY,
        )
    return MockLLM()


def extract_json(text: str) -> dict:
    """Robustly pull a JSON object out of an LLM response (handles ```json fences)."""
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
