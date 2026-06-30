"""
Compatibility shim for langchain_core.tools.tool.

Real installs use the genuine LangChain @tool decorator (so tools can be bound to
agents and discovered via MCP). When langchain_core is not installed, we provide
a minimal decorator that still exposes a `.invoke(dict)` method, keeping the whole
project runnable with only pydantic (MOCK mode).
"""
from __future__ import annotations

try:
    from langchain_core.tools import tool  # type: ignore

    HAS_LANGCHAIN = True
except Exception:  # pragma: no cover - fallback path
    HAS_LANGCHAIN = False

    def tool(name=None):
        def decorator(fn):
            class _Tool:
                __name__ = getattr(fn, "__name__", "tool")
                __doc__ = fn.__doc__

                def invoke(self, arguments: dict):
                    return fn(**arguments)

                def __call__(self, *a, **kw):
                    return fn(*a, **kw)

            return _Tool()

        # support both @tool and @tool("name")
        if callable(name):
            return decorator(name)
        return decorator
