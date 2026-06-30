# AdmitAI — AI Admissions Counsellor for Indian Students → German Universities

> An end-to-end agentic AI system that guides Indian students through every step of applying to German universities — from eligibility matching to SOP generation, scholarship discovery, and deadline tracking.

**Live Demo:** [admit-ai-delta.vercel.app](https://admit-ai-delta.vercel.app) · **API:** [admitai-5965.onrender.com](https://admitai-5965.onrender.com/docs)

**Stack:** LangGraph · Gemini 2.5 Flash · Groq · Cerebras · phi-2 LoRA · FastAPI · React/Vite · Supabase

---

## What it does

| Feature | Description |
|---------|-------------|
| **University Matching** | Scores 58+ German public universities against your CGPA, degree, and target field. Live sync from DAAD API. |
| **Eligibility Scoring** | 0–100 fit score per program — accounts for institution type (Universität vs FH), intake, language requirements, APS |
| **SOP Generation** | Gemini 2.5 Flash guided by 149 fine-tuned SOP style examples + your resume + live web context for each university |
| **phi-2 LoRA** | Fine-tuned on accepted German SOPs (QLoRA, r=16) — used as primary generator when available, Gemini as fallback |
| **AI University Chat** | Ask anything about a university — deadlines, requirements, programs — answered directly from live university data |
| **Scholarship Matching** | Filters DAAD, Deutschlandstipendium, Erasmus+ against your profile and application level |
| **Document Checklist** | Per-university checklist: APS, blocked account, IELTS, Uni-Assist, transcripts, visa |
| **LOR Templates** | Four letter-of-recommendation templates with fill-in-the-blank placeholders |
| **Deadline Tracking** | Projects annual deadlines to any future year (winter: 15 July · summer: 15 January) |

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│               Supervisor (Groq llama-3.3-70b)        │
│   Routes: full_sop · research_eligibility ·          │
│           tracker_only · scholarship · respond        │
└──────┬──────────────┬──────────────────┬────────────┘
       │              │                  │
       ▼              ▼                  ▼
  Research       Scholarship         Finalize
  Agent          Agent               Node
  (DAAD API      (DAAD DB +
  + DDG web)     Erasmus+)
       │
       ▼
  Eligibility
  Agent
  (Groq + scoring)
       │
       ├──────────────────────┐
       ▼                      ▼
   SOP Agent             Tracker Agent
   (phi-2 LoRA →         (deadlines +
    Gemini 2.5 Flash →   checklist +
    Cerebras fallback)   Gmail MCP)
       │
       ▼
  Finalize → Response

State persisted per thread_id via LangGraph MemorySaver
```

---

## LLM Provider Chain

| Task | Primary | Fallback 1 | Fallback 2 |
|------|---------|------------|------------|
| Routing / Eligibility | Groq llama-3.3-70b | Gemini 2.5 Flash | MockLLM |
| SOP Generation | phi-2 LoRA (HF) | Gemini 2.5 Flash | Cerebras gpt-oss-120b |
| University Chat | Groq llama-3.3-70b | — | — |
| Resume Parsing | Groq llama-3.3-70b | — | — |

---

## Project Layout

```
AdmitAI/
├── agents/
│   ├── eligibility_agent.py   # 0-100 fit scoring per program
│   ├── research_agent.py      # DAAD API + DDG university discovery
│   ├── resume_parser.py       # PDF → structured EnrichedProfile
│   ├── scholarship_agent.py   # DAAD / Erasmus+ / Deutschlandstipendium
│   ├── sop_agent.py           # phi-2 → Gemini → Cerebras SOP pipeline
│   └── tracker_agent.py       # checklist + deadline reminders
│
├── graph/
│   ├── builder.py             # LangGraph StateGraph + MemorySaver
│   ├── supervisor.py          # routing node + finalize node
│   ├── edges.py               # conditional edge functions
│   └── state.py               # IntelliAdmitState TypedDict
│
├── api/
│   ├── main.py                # FastAPI app + CORS
│   ├── routes.py              # all REST endpoints
│   ├── auth.py                # Supabase JWT verification
│   └── schemas.py             # Pydantic request/response models
│
├── config/
│   ├── settings.py            # env-driven config (MOCK / PARTIAL / FULL)
│   └── llm_provider.py        # Gemini / Groq / Cerebras REST clients
│
├── finetuning/
│   ├── colab_finetune.ipynb   # QLoRA training notebook (Colab T4)
│   ├── train.py               # TRL SFTTrainer, r=16, 3 epochs
│   ├── inference.py           # HF Serverless API + local GPU paths
│   └── humanizer.py           # boilerplate stripper
│
├── data/
│   ├── sop_dataset/sops.jsonl # 149 fine-tuned SOP style examples
│   ├── universities_seed.json  # 28 seed universities
│   ├── universities_expansion.json  # +30 universities
│   └── fetch_daad_universities.py   # live DAAD sync script
│
├── frontend/                  # React 18 + Vite + Supabase Auth
│   └── src/
│       ├── pages/             # Login · Onboarding · Dashboard · Apply · Tracker · UniversityPage
│       ├── components/        # Layout · Sidebar
│       └── styles/app.css
│
├── mcp_tools/                 # Browser · Gmail · Drive · PDF (mock-safe)
├── rag/                       # BM25 + Chroma + RRF hybrid retriever
├── eval/                      # RAGAS + LLM-as-judge evaluation
├── Procfile                   # Render deployment
├── requirements-prod.txt      # Production deps (no GPU packages)
└── requirements.txt           # Full dev deps including training
```

---

## Quickstart (Local Dev)

### Prerequisites
- Python 3.12
- Node.js 18+
- Supabase project (free tier works)

### 1. Clone & install backend
```bash
git clone https://github.com/Samhitha140/AdmitAI.git
cd AdmitAI
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your keys (see Environment Variables section below)
```

### 3. Seed the university database
```bash
python data/seed_universities.py
```

### 4. Start the backend
```bash
uvicorn api.main:app --reload
# API docs: http://localhost:8000/docs
```

### 5. Start the frontend
```bash
cd frontend
cp .env.example .env
# Set VITE_API_URL=http://localhost:8000/api
npm install && npm run dev
# App: http://localhost:5173
```

---

## Environment Variables

### Backend (`.env`)
```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

# LLMs
GOOGLE_API_KEY=          # Gemini 2.5 Flash — get at aistudio.google.com
GROQ_API_KEY=            # Free at console.groq.com (14,400 req/day)
CEREBRAS_API_KEY=        # Free at console.cerebras.ai (~1,000 req/day)

# HuggingFace (for phi-2 LoRA)
HUGGINGFACE_TOKEN=       # hf_...
SOP_ADAPTER=allisamhitha/intelliadmit-sop-lora
SOP_MODEL_MERGED=allisamhitha/intelliadmit-sop-phi2-merged

# Model names
AGENT_MODEL=gemini-2.5-flash
SUPERVISOR_MODEL=gemini-2.5-flash
GROQ_MODEL=llama-3.3-70b-versatile
CEREBRAS_MODEL=gpt-oss-120b
```

### Frontend (`frontend/.env`)
```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
VITE_API_URL=http://localhost:8000/api
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

---

## Deployment

### Backend → Render
1. Connect this repo to [render.com](https://render.com)
2. **Build command:** `pip install -r requirements-prod.txt`
3. **Start command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
4. Add all backend env vars in the Render dashboard

### Frontend → Vercel
1. Import `frontend/` directory at [vercel.com](https://vercel.com)
2. Set env vars (update `VITE_API_URL` to your Render URL)
3. Add Vercel domain to:
   - Supabase → Auth → Redirect URLs
   - Google Cloud Console → Authorized redirect URIs

---

## Fine-tuning the SOP Model

The phi-2 LoRA adapter was trained on 149 accepted German university SOPs using QLoRA (4-bit NF4 base, r=16 on `q_proj`/`v_proj`, 3 epochs, lr=2e-4).

**To retrain or merge:**
```python
# Run in Google Colab (T4 GPU)
# See finetuning/colab_finetune.ipynb

from google.colab import userdata
HF_TOKEN = userdata.get('your-token-secret')
# ... follow the notebook
```

**Merge adapter for HF Inference API:**
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

base = AutoModelForCausalLM.from_pretrained("microsoft/phi-2", torch_dtype=torch.float16, device_map="auto", trust_remote_code=True, token=HF_TOKEN)
model = PeftModel.from_pretrained(base, "allisamhitha/intelliadmit-sop-lora", token=HF_TOKEN)
model = model.merge_and_unload()
model.push_to_hub("allisamhitha/intelliadmit-sop-phi2-merged", token=HF_TOKEN)
```

Adapter: [huggingface.co/allisamhitha/intelliadmit-sop-lora](https://huggingface.co/allisamhitha/intelliadmit-sop-lora)

---

## Run Modes

| Mode | Env | Behaviour |
|------|-----|-----------|
| **MOCK** | No keys | Deterministic stubs, full graph still runs |
| **PARTIAL** | `GOOGLE_API_KEY` set | Real Gemini agents, mock MCP tools |
| **FULL** | All keys + MCP URLs | Live scraping, real SOP, real reminders |

---

## Key Design Decisions

**Why direct REST clients instead of LangChain SDKs?**
The official `langchain-google-genai` SDK hangs indefinitely on some Windows networks due to gRPC SSL interference. `_GeminiRestLLM` in `config/llm_provider.py` makes plain HTTPS requests that complete in ~2s on the same machine.

**Why Groq for routing instead of Gemini?**
Groq's free tier gives 14,400 requests/day at near-zero latency. Routing and eligibility scoring run on every query — saving Gemini quota exclusively for SOP generation (the quality-sensitive task).

**Why three fallback LLMs for SOP?**
Gemini free tier returns 503 under load. Rather than failing, the pipeline falls through: phi-2 LoRA (fine-tuned, fastest) → Gemini 2.5 Flash (highest quality) → Cerebras gpt-oss-120b (reliable free fallback).

**Why `asyncio.to_thread` everywhere in routes?**
LangGraph's `graph.invoke()` is synchronous. Calling it directly inside an `async def` FastAPI handler blocks the entire event loop. Wrapping in `to_thread` lets uvicorn handle other requests while the 30-second pipeline runs.

---

## Interview Map

| Topic | Where in the code |
|-------|-------------------|
| Multi-agent / LangGraph | `graph/builder.py` — StateGraph, conditional edges, MemorySaver |
| Supervisor routing | `graph/supervisor.py` — keyword + LLM classification |
| RAG + hybrid retrieval | `rag/retriever.py` — BM25 + Chroma + RRF fusion |
| LoRA fine-tuning | `finetuning/lora_config.py`, `train.py`, `colab_finetune.ipynb` |
| LLM evaluation | `eval/ragas_eval.py`, `eval/llm_judge.py` |
| Human-in-the-loop | `interrupt_before=["sop"]` in `graph/builder.py` |
| MCP tool use | `mcp_tools/` — Browser, Gmail, Drive, PDF |
| Async FastAPI | `api/routes.py` — `asyncio.to_thread` pattern throughout |
| Auth (OAuth + email) | `frontend/src/pages/LoginPage.jsx`, `api/auth.py` |
| Live data sync | `data/fetch_daad_universities.py` — DAAD API pagination |

---

## Built by

**Alli Samhitha** · [github.com/Samhitha140](https://github.com/Samhitha140) · 2026
