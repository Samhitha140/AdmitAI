"""
Custom PDF MCP tool - a locally deployed MCP server (PyMuPDF) that reads the
student's own documents (transcripts, certificates, CV, recommendation letters).
The extracted text is injected into the Eligibility and SOP agents so outputs are
personalised to the real profile, not generic.
"""
from __future__ import annotations

from pathlib import Path

from mcp_tools.compat import tool

from config.settings import settings
from mcp_tools.base import MCPClient

_client = MCPClient("pdf", settings.PDF_MCP_URL)


@tool("pdf_read_student_doc")
def read_student_doc(file_path: str) -> dict:
    """Extract text from one of the student's uploaded documents (transcript, CV,
    certificate). Returns the raw text and a short summary."""
    if _client.live:
        return _client.call_tool("read_pdf", {"path": file_path})

    path = Path(file_path)
    if not path.exists():
        return {"file": file_path, "error": f"File not found: {file_path}", "text": ""}
    if path.suffix.lower() != ".pdf":
        return {"file": path.name, "error": "Not a PDF file", "text": ""}
    try:
        import fitz
        doc = fitz.open(str(path))
        pages_text = [page.get_text() for page in doc]
        text = "\n".join(pages_text).strip()
        doc.close()
        if not text:
            return {
                "file": path.name,
                "text": "",
                "chars": 0,
                "error": "PDF appears to be image-based (scanned). Please use a text-based PDF.",
            }
        print(f"[pdf_tool] extracted {len(text)} chars from {path.name} ({len(pages_text)} pages)")
        return {"file": path.name, "text": text, "chars": len(text)}
    except Exception as exc:
        return {"file": path.name, "error": f"PDF read error: {exc}", "text": ""}
