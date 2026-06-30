"""
Source 4 — Synthetic SOP generator.

This is the main volume source.  Real public SOPs give you 30–80 seed examples;
synthetic generation fills the rest to ~400 total.  The key rule is to generate
with per-university constraints so the model learns German-specific conventions,
not generic academic writing.

Diversity grid used (4 × 2 × 2 × 3 = 48 base combinations × ~6 each ≈ 288):
  Fields:          CS, Data Science, Mechanical Engineering, Business
  Institution:     university (Universität), applied_sciences (FH)
  Level:           masters (main), bachelors (smaller share)
  Profile strength: strong (CGPA 8.5+), average (7.0–8.0), practical (work exp)

For each combination the prompt injects:
  - University-specific requirements (word limit, structure, required questions)
  - A realistic student profile matching the profile_strength
  - Realistic project/internship details so the SOP references real things

A single Gemini/GPT call costs ~$0.001; 300 examples ≈ $0.30 total.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

# ── University-specific prompt constraints ────────────────────────────────────
_UNI_CONSTRAINTS = {
    "TU Munich": {
        "word_limit": "~800 words (2 pages max)",
        "required": [
            "Explain why you are suitable for this specific TUM program (not just any program)",
            "Reference at least one TUM research group, lab, or faculty member by name",
            "Include an affirmation that you wrote this yourself",
            "Add a footnote or citation if you reference any external source",
        ],
        "institution_type": "university",
        "style": "formal academic, research-focused, no personal life stories",
    },
    "RWTH Aachen": {
        "word_limit": "500–1000 words",
        "required": [
            "Focus on academic and research experience, not personal anecdotes",
            "Explain how your background matches the program's technical requirements",
        ],
        "institution_type": "university",
        "style": "concise, technical, project-focused",
    },
    "TU Berlin": {
        "word_limit": "1 page (≈500 words)",
        "required": [
            "State motivation for the specific program",
            "What you hope to achieve during studies",
        ],
        "institution_type": "university",
        "style": "brief, direct, honest — avoid overselling",
    },
    "LMU Munich": {
        "word_limit": "2000–3000 characters (~350–500 words)",
        "required": [
            "Very concise — character limit is strict",
            "Focus on program fit and career goal",
        ],
        "institution_type": "university",
        "style": "extremely concise, high signal-to-noise ratio",
    },
    "Munich University of Applied Sciences (HM)": {
        "word_limit": "500–700 words",
        "required": [
            "Emphasise practical experience: internships, industry projects",
            "Mention Vorpraktikum (pre-study internship) if completed",
            "Connect career goal to applied industry outcomes",
        ],
        "institution_type": "applied_sciences",
        "style": "practice-oriented, industry-focused, concrete outcomes",
    },
    "Hamburg University of Applied Sciences (HAW)": {
        "word_limit": "500–700 words",
        "required": [
            "Highlight applied skills and hands-on project work",
            "Explain why an applied sciences degree fits your career plan",
        ],
        "institution_type": "applied_sciences",
        "style": "applied, career-driven, specific technical skills",
    },
    "University of Freiburg": {
        "word_limit": "500–650 words",
        "required": [
            "Answer: motivation for applying to Freiburg specifically",
            "What you like about the curriculum",
            "How your interests relate to program research areas",
        ],
        "institution_type": "university",
        "style": "structured Q&A format following the four required questions",
    },
    "KIT Karlsruhe": {
        "word_limit": "1000–3000 characters (~200–500 words)",
        "required": [
            "Character limit (not word) — extremely concise",
            "Technical background and research interest",
        ],
        "institution_type": "university",
        "style": "very concise, technical precision over personal narrative",
    },
}

# ── Student profile templates ─────────────────────────────────────────────────
_PROFILES = {
    "strong_academic": {
        "cgpa": round(random.uniform(8.5, 9.5), 1),
        "work_experience_years": 0,
        "thesis": True,
        "publications": True,
        "description": "top academic record, thesis, one publication, no industry exp",
    },
    "solid_with_internship": {
        "cgpa": round(random.uniform(7.5, 8.4), 1),
        "work_experience_years": 1,
        "thesis": True,
        "publications": False,
        "description": "solid CGPA, strong internship, final-year thesis",
    },
    "practical_experienced": {
        "cgpa": round(random.uniform(7.0, 7.9), 1),
        "work_experience_years": 2,
        "thesis": False,
        "publications": False,
        "description": "average CGPA but 2+ years industry experience, multiple projects",
    },
}

# ── Field-specific project banks ──────────────────────────────────────────────
_PROJECTS = {
    "Computer Science": [
        ("Hybrid RAG pipeline for document retrieval", "BM25 + ChromaDB + LangChain",
         "14% MRR improvement on MS-MARCO benchmark"),
        ("Real-time fake news detector browser extension", "BERT, PyTorch, Flask",
         "91% F1 on LIAR dataset, 500+ active users"),
        ("Multi-agent LLM admission counsellor", "LangGraph, Mistral-7B, FastAPI",
         "reduced application time by 60% in user study"),
        ("Distributed key-value store", "Go, Raft consensus",
         "achieved 99.9% consistency under 3-node partition tests"),
        ("Compiler for a subset of C", "Python, LLVM IR",
         "passes 94% of standard test suite including edge cases"),
    ],
    "Data Science": [
        ("Customer churn prediction system", "XGBoost, SHAP, Streamlit",
         "reduced churn by 18% for 50k-user e-commerce platform"),
        ("Time-series anomaly detection for IoT sensors", "LSTM, Prophet, Kafka",
         "detected 97% of faults 2–4 hours before failure"),
        ("NLP pipeline for clinical note classification", "BioBERT, scikit-learn",
         "F1 0.89 on 20k medical records, deployed at district hospital"),
    ],
    "Mechanical Engineering": [
        ("CFD simulation of turbine blade cooling", "ANSYS Fluent, Python post-processing",
         "15% thermal efficiency improvement over baseline geometry"),
        ("Lightweight electric vehicle chassis design", "SolidWorks, FEA",
         "35% weight reduction while maintaining crash safety rating"),
        ("Autonomous warehouse robot path planning", "ROS, A* + D* Lite",
         "99.2% obstacle avoidance in simulation, deployed in pilot facility"),
    ],
    "Business/MBA": [
        ("Market entry strategy for SaaS product in DACH region", "Porter's 5 forces, financial modelling",
         "presented to CFO, led to €200k pilot budget approval"),
        ("Supply chain resilience analysis post-COVID", "Excel, R, scenario planning",
         "identified 3 critical bottlenecks, recommendations adopted by board"),
    ],
}

_INTERNSHIPS = {
    "Computer Science": [
        ("Infosys Ltd.", "Software Engineering Intern",
         "built CI/CD dashboard in React + FastAPI reducing deployment time by 40%"),
        ("Tata Consultancy Services", "ML Engineer Intern",
         "deployed BERT sentiment model serving 10k requests/day in production"),
        ("Wipro", "Data Engineer Intern",
         "migrated legacy ETL pipeline to Apache Spark, 3× throughput improvement"),
    ],
    "Data Science": [
        ("Mu Sigma", "Data Science Intern",
         "built customer segmentation model (k-means + RFM) for FMCG client"),
        ("KPMG India", "Analytics Intern",
         "automated monthly reporting saving 20 analyst-hours per month"),
    ],
    "Mechanical Engineering": [
        ("DRDO", "Research Intern",
         "conducted fatigue analysis on composite materials for aerospace application"),
        ("Tata Motors", "Manufacturing Engineering Intern",
         "implemented 5S methodology in assembly line, 12% efficiency gain"),
    ],
    "Business/MBA": [
        ("Deloitte India", "Strategy Consulting Intern",
         "supported due diligence for ₹500Cr acquisition, built financial models"),
        ("HDFC Bank", "Corporate Finance Intern",
         "analysed loan portfolio risk for 200+ SME clients"),
    ],
}


def _make_profile(field: str, profile_type: str, seed: int) -> dict:
    random.seed(seed)
    base = _PROFILES[profile_type].copy()
    projects = random.sample(_PROJECTS.get(field, _PROJECTS["Computer Science"]), k=min(2, len(_PROJECTS.get(field, []))))
    internships = random.sample(_INTERNSHIPS.get(field, _INTERNSHIPS["Computer Science"]), k=1)
    degrees = {
        "Computer Science": ["B.Tech Computer Science", "B.E. Information Technology", "B.Tech CSE"],
        "Data Science": ["B.Tech Computer Science", "B.Sc Statistics", "B.Tech ECE"],
        "Mechanical Engineering": ["B.Tech Mechanical Engineering", "B.E. Mechanical", "B.Tech Production Engineering"],
        "Business/MBA": ["BBA", "B.Com", "B.Tech + MBA (integrated)"],
    }
    colleges = ["NIT Trichy", "VIT Vellore", "BITS Pilani", "IIIT Hyderabad", "Delhi Technological University",
                "PSG College of Technology", "Jadavpur University", "Thapar University"]
    base["degree"] = random.choice(degrees.get(field, ["B.Tech"]))
    base["college"] = random.choice(colleges)
    base["projects"] = projects
    base["internship"] = internships[0]
    return base


_GENERATION_PROMPT = """You are an expert German university admissions consultant.
Write an accepted-quality Statement of Purpose (Motivationsschreiben) for the following student.

UNIVERSITY: {university}
PROGRAM: MSc {field} ({institution_type})
INTAKE: {intake}

WORD LIMIT AND FORMAT RULES FOR THIS UNIVERSITY:
{word_limit}

REQUIRED CONTENT (must cover all of these):
{required}

WRITING STYLE: {style}

STUDENT PROFILE:
- Degree: {degree} from {college}, CGPA: {cgpa}/10
- Work experience: {work_exp} years
- Projects:
{projects}
- Internship: {internship_role} at {internship_company} — {internship_achievement}

RULES:
1. Reference the student's real projects and internship by name — no invented details
2. Name at least one specific course, research group, or professor at {university}
3. Open with a specific, non-generic sentence — NOT "I have always been passionate about..."
4. Formal academic English only — no personal life stories
5. End with a concrete career goal tied to Germany / Europe
6. Stay strictly within the word limit
7. Do NOT include any preamble or postamble — output the SOP text only

Write the SOP now:"""


def _worker(jobs: "queue.Queue", model_name: str, api_key: str,
             results: list, lock: "threading.Lock", counter: list,
             total: int, output_path: "Path | None") -> None:
    """Thread worker: drain jobs queue using one Groq model endpoint."""
    import threading
    from config.llm_provider import _GroqRestLLM
    llm = _GroqRestLLM(model=model_name, temperature=0.85, api_key=api_key)

    while True:
        try:
            item = jobs.get(timeout=3)
        except Exception:
            break

        uni_name, uni_config, field, profile_type, intake, profile, seed = item
        prompt = _GENERATION_PROMPT.format(
            university=uni_name,
            field=field,
            institution_type=uni_config["institution_type"],
            intake=intake,
            word_limit=uni_config["word_limit"],
            required="\n".join(f"  - {r}" for r in uni_config["required"]),
            style=uni_config["style"],
            degree=profile["degree"],
            college=profile["college"],
            cgpa=profile["cgpa"],
            work_exp=profile["work_experience_years"],
            projects="\n".join(f"  · {p[0]} ({p[1]}): {p[2]}" for p in profile["projects"]),
            internship_role=profile["internship"][1],
            internship_company=profile["internship"][0],
            internship_achievement=profile["internship"][2],
        )

        try:
            response = llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            word_count = len(text.split())

            if word_count < 150:
                with lock:
                    counter[0] += 1
                    print(f"    [{counter[0]}/{total}] SKIP too short ({word_count}w) — {uni_name}/{field}")
            else:
                entry = {
                    "source": "synthetic_llm",
                    "url": "",
                    "university": uni_name,
                    "program": f"MSc {field}",
                    "level": "masters",
                    "field": field,
                    "institution_type": uni_config["institution_type"],
                    "confirmed_accepted": False,
                    "profile_type": profile_type,
                    "intake": intake,
                    "text": text,
                    "word_count": word_count,
                    "profile_snapshot": {
                        "cgpa": profile["cgpa"],
                        "degree": profile["degree"],
                        "work_experience_years": profile["work_experience_years"],
                    },
                }
                with lock:
                    results.append(entry)
                    counter[0] += 1
                    done = len(results)
                    print(f"    [{counter[0]}/{total}] {uni_name} | {field} | {profile_type} | {word_count}w")
                    if output_path and done % 10 == 0:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "w", encoding="utf-8") as f:
                            for r in results:
                                f.write(json.dumps(r) + "\n")

        except Exception as exc:
            with lock:
                counter[0] += 1
                print(f"    [{counter[0]}/{total}] ERROR {uni_name}/{field}: {exc}")

        jobs.task_done()
        time.sleep(2.1)  # 30 req/min per model endpoint


def generate_synthetic_sops(
    n_per_combination: int = 3,
    output_path: "Path | None" = None,
) -> list[dict]:
    """Generate synthetic SOPs using two Groq model threads in parallel.

    Two worker threads each hitting a different Groq model endpoint (separate
    30 req/min pools) → effective 60 req/min → 2× faster than single-thread.
    Grid: 4 fields × 8 universities × 3 profiles × n_per_combination.
    n=1 → 96 jobs → ~1.7 min.  n=3 → 288 jobs → ~5 min.
    """
    import queue
    import threading

    from config.settings import settings

    if not settings.GROQ_API_KEY:
        print("  [skip] GROQ_API_KEY not set — cannot generate synthetic SOPs")
        return []

    # Two separate Groq model endpoints, each with their own 30 req/min pool
    models = [
        settings.GROQ_MODEL or "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
    ]

    fields = list(_PROJECTS.keys())
    universities = list(_UNI_CONSTRAINTS.keys())
    profile_types = list(_PROFILES.keys())
    intakes = ["winter", "summer"]

    # Build all jobs upfront
    job_queue: queue.Queue = queue.Queue()
    seed = 42
    for field in fields:
        for uni_name, uni_config in _UNI_CONSTRAINTS.items():
            for profile_type in profile_types:
                for _ in range(n_per_combination):
                    seed += 1
                    intake = intakes[seed % 2]
                    profile = _make_profile(field, profile_type, seed)
                    job_queue.put((uni_name, uni_config, field, profile_type, intake, profile, seed))

    total = job_queue.qsize()
    eta_min = round(total * 2.1 / 60 / 2)  # 2 threads halves the time
    print(f"  Generating {total} synthetic SOPs with 2 parallel Groq threads")
    print(f"  Models: {models[0]}  +  {models[1]}")
    print(f"  Estimated time: ~{eta_min} minutes\n")

    results: list[dict] = []
    lock = threading.Lock()
    counter = [0]

    threads = [
        threading.Thread(
            target=_worker,
            args=(job_queue, model, settings.GROQ_API_KEY, results, lock, counter, total, output_path),
            daemon=True,
        )
        for model in models
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"\n  Synthetic: generated {len(results)} SOPs")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        print(f"  Saved to {output_path}")

    return results


if __name__ == "__main__":
    items = generate_synthetic_sops(n_per_combination=1)
    print(f"Generated {len(items)} synthetic SOPs")
