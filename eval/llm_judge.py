"""
LLM-as-judge SOP scorer.

Gemini Pro scores each generated SOP on a 4-criterion rubric (1-5):
motivation clarity, German academic tone, program fit, structural correctness.
Falls back to heuristic scoring (length, section keywords, program mentions)
when no LLM is configured.

Known biases to control for (documented for interview answers): position bias,
verbosity bias, self-enhancement bias - mitigated by a fixed rubric, randomised
order in benchmarks, and using a different judge model than the generator.
"""
from __future__ import annotations

from config.llm_provider import extract_json, get_chat_model

_JUDGE_PROMPT = """Score this Statement of Purpose for a German university on each
criterion from 1 to 5. Return ONLY JSON:
{{"motivation": <1-5>, "tone": <1-5>, "fit": <1-5>, "structure": <1-5>}}

Criteria:
- motivation: clarity and authenticity of the applicant's motivation
- tone: formal German academic English tone
- fit: references specific program / university details
- structure: correct section ordering and length

Target program: {program}
SOP:
{sop}"""

_SECTIONS = ["motivation", "background", "program", "germany", "career", "goal"]


def _heuristic(sop: str, program: str) -> dict:
    text = sop.lower()
    word_count = len(sop.split())
    structure = 5 if 400 <= word_count <= 900 else 3
    fit = 5 if any(w in text for w in program.lower().split()) else 3
    motivation = 4 if "motivat" in text or "fascinat" in text or "passion" in text else 3
    tone = 4 if word_count > 200 else 3
    return {
        "motivation": float(motivation),
        "tone": float(tone),
        "fit": float(fit),
        "structure": float(structure),
    }


def judge_sop(sop: str, program: str) -> dict:
    llm = get_chat_model(temperature=0.0)
    try:
        resp = llm.invoke(_JUDGE_PROMPT.format(program=program, sop=sop[:4000])).content
        parsed = extract_json(resp)
        if all(k in parsed for k in ["motivation", "tone", "fit", "structure"]):
            return {k: float(parsed[k]) for k in ["motivation", "tone", "fit", "structure"]}
    except Exception:
        pass
    return _heuristic(sop, program)


if __name__ == "__main__":
    sample = (
        "My motivation to study at TU Munich stems from a deep fascination with "
        "machine learning systems developed during my Computer Science degree..."
    )
    print(judge_sop(sample, "TU Munich MSc Informatics"))
