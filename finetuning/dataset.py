"""
SOP fine-tuning dataset construction.

Builds instruction->response pairs:
  instruction = student profile JSON + target program + "Write a Statement of Purpose"
  response    = the accepted SOP

Sources (see README): public GitHub repos, r/gradadmissions accepted SOPs, and
synthetic examples verified by German academics. This module formats raw JSONL
into the Mistral instruction template and returns a HuggingFace Dataset.
"""
from __future__ import annotations

import json
from pathlib import Path

from config.settings import SOP_DATASET_DIR

# Mistral instruct chat template
_TEMPLATE = "<s>[INST] {instruction} [/INST] {response}</s>"

# a few seed pairs so the pipeline is testable before a real dataset is added
_SEED = [
    {
        "profile": {"degree": "B.Tech CSE", "cgpa": 8.2, "interests": "machine learning"},
        "program": "TU Munich MSc Informatics",
        "response": (
            "My decision to pursue an MSc in Informatics at the Technical University "
            "of Munich is the culmination of a sustained engagement with machine "
            "learning throughout my undergraduate studies. During my B.Tech in "
            "Computer Science, I developed a rigorous foundation in algorithms and "
            "statistics, which I applied to a research project on neural retrieval. "
            "TU Munich's emphasis on systems-oriented ML research aligns precisely "
            "with my goal of building reliable learning systems..."
        ),
    },
]


def _format_pair(profile: dict, program: str, response: str) -> dict:
    instruction = (
        f"Student profile: {json.dumps(profile)}\n"
        f"Target program: {program}\n"
        "Write a Statement of Purpose in German academic English."
    )
    return {"text": _TEMPLATE.format(instruction=instruction, response=response)}


def load_sop_dataset(jsonl_path: Path | None = None):
    """Return a HuggingFace Dataset of formatted SOP training examples."""
    records: list[dict] = []
    jsonl_path = jsonl_path or (SOP_DATASET_DIR / "sops.jsonl")

    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            records.append(_format_pair(row["profile"], row["program"], row["response"]))
    else:
        print(f"[dataset] {jsonl_path} not found - using {len(_SEED)} seed examples")
        records = [_format_pair(r["profile"], r["program"], r["response"]) for r in _SEED]

    try:
        from datasets import Dataset

        return Dataset.from_list(records)
    except Exception:
        return records  # plain list fallback


if __name__ == "__main__":
    ds = load_sop_dataset()
    print(f"Loaded {len(ds)} SOP training examples")
    print(ds[0]["text"][:300])
