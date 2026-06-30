"""
Document ingestion for the RAG pipeline.

Loads German university program PDFs (prospectuses, admission guidelines, APS /
DAAD criteria) with PyMuPDF and attaches metadata (university, program, year).
Falls back to plain-text files and a tiny built-in seed corpus so the pipeline
works even before any real PDFs are added to data/uni_docs/.
"""
from __future__ import annotations

from pathlib import Path

from config.settings import UNI_DOCS_DIR


# --------------------------------------------------------------------------- #
# Seed corpus - lets the RAG demo run with zero downloaded PDFs
# --------------------------------------------------------------------------- #
_SEED_DOCS = [
    {
        "text": (
            "TU Munich MSc Informatics admission requires a Bachelor's degree in "
            "Computer Science or a closely related field with a final grade "
            "equivalent to German 2.5 or better (roughly CGPA 7.5/10 for Indian "
            "applicants). An APS certificate is mandatory for Indian students. "
            "English proficiency of IELTS 6.5 or TOEFL 88 is required; German is "
            "not required for the English-taught track. Application deadline for "
            "the winter semester is 31 May via Uni-Assist."
        ),
        "metadata": {"university": "TU Munich", "program": "MSc Informatics", "year": 2026},
    },
    {
        "text": (
            "RWTH Aachen MSc Data Science requires a relevant Bachelor's degree, "
            "minimum CGPA 7.0/10, demonstrated coursework in linear algebra, "
            "statistics and programming. APS certificate required for Indian "
            "applicants. Language: IELTS 6.5 overall. Tuition is free; only a "
            "semester contribution of around 300 EUR applies. Winter deadline 1 March."
        ),
        "metadata": {"university": "RWTH Aachen", "program": "MSc Data Science", "year": 2026},
    },
    {
        "text": (
            "TU Berlin MSc Computer Engineering requires CGPA 7.0/10, an APS "
            "certificate, and German language level B2 (TestDaF/DSH) because parts "
            "of the program are taught in German. Work experience is not required "
            "but is viewed favourably. DAAD scholarships are available for "
            "outstanding applicants. Deadline 15 March for winter intake."
        ),
        "metadata": {"university": "TU Berlin", "program": "MSc Computer Engineering", "year": 2026},
    },
    {
        "text": (
            "Heidelberg University MSc Applied Computer Science expects a strong "
            "academic record (CGPA 8.0/10), an APS certificate, and IELTS 7.0. The "
            "program emphasises research; a clear research motivation in the "
            "Statement of Purpose is weighted heavily. Blocked account of roughly "
            "11,904 EUR per year is required for the student visa."
        ),
        "metadata": {"university": "Heidelberg", "program": "MSc Applied Computer Science", "year": 2026},
    },
]


def _load_pymupdf(path: Path) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)


def load_documents(docs_dir: Path | None = None) -> list[dict]:
    """Return a list of {text, metadata} records from data/uni_docs/."""
    docs_dir = docs_dir or UNI_DOCS_DIR
    records: list[dict] = []

    if docs_dir.exists():
        for path in sorted(docs_dir.glob("**/*")):
            if path.suffix.lower() == ".pdf":
                try:
                    text = _load_pymupdf(path)
                except Exception as exc:
                    print(f"[loader] could not read {path.name}: {exc}")
                    continue
            elif path.suffix.lower() in {".txt", ".md"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
            else:
                continue
            records.append(
                {
                    "text": text,
                    "metadata": {"source": path.name, "university": path.stem, "year": 2026},
                }
            )

    if not records:
        print("[loader] no PDFs found in data/uni_docs/ - using built-in seed corpus")
        records = _SEED_DOCS
    return records
