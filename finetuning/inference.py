"""
Inference with the fine-tuned phi-2 SOP model.

Priority chain:
  1. HF Serverless Inference API (router.huggingface.co) — works without GPU,
     requires SOP_MODEL_MERGED to be set (the merged full model, not the LoRA adapter).
  2. Local PEFT inference — only when a CUDA GPU is available.

Set in .env:
  SOP_MODEL_MERGED=Samhitha140/intelliadmit-sop-phi2-merged   ← merged full model
  SOP_ADAPTER=Samhitha140/intelliadmit-sop-lora               ← LoRA adapter (local only)
  HUGGINGFACE_TOKEN=hf_...
"""
from __future__ import annotations

import json

import requests

from config.settings import settings

# Matches the prompt template used in colab_finetune.ipynb
_PROMPT = (
    "Instruct: Student profile: {profile}\n"
    "Target program: {program}\n"
    "Program context: {context}\n"
    "Write a Statement of Purpose in German academic English.\nOutput:"
)

# router.huggingface.co resolves on networks where api-inference.huggingface.co is blocked
_HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/{model}"
_HF_LEGACY_URL = "https://api-inference.huggingface.co/models/{model}"


def _hf_inference_api(prompt: str) -> str:
    """Call HuggingFace Serverless Inference API using the merged full model.

    Uses router.huggingface.co (new endpoint) first, then the legacy URL as fallback.
    Requires SOP_MODEL_MERGED in .env — the LoRA adapter alone is not supported.
    """
    if not settings.HF_TOKEN:
        raise RuntimeError("HUGGINGFACE_TOKEN not set in .env")

    model = settings.SOP_MODEL_MERGED
    if not model:
        raise RuntimeError(
            "SOP_MODEL_MERGED not set — add the merged model repo name to .env. "
            "Run the Colab merge snippet to create it."
        )

    headers = {"Authorization": f"Bearer {settings.HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 900,
            "temperature": 0.7,
            "do_sample": True,
            "return_full_text": False,
        },
    }

    for url_template in [_HF_ROUTER_URL, _HF_LEGACY_URL]:
        url = url_template.format(model=model)
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 503:
                data = resp.json()
                wait = data.get("estimated_time", 30)
                raise RuntimeError(f"HF model is loading (est. {wait:.0f}s) — retry shortly")
            if resp.status_code == 400:
                raise RuntimeError(f"HF model not supported: {resp.text[:200]}")
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, list) and result:
                text = result[0].get("generated_text", "")
                if text.strip():
                    return text
            raise RuntimeError(f"Unexpected HF response: {result}")
        except RuntimeError:
            raise
        except Exception as exc:
            print(f"[inference] {url_template.split('/')[2]} failed: {exc}")
            continue

    raise RuntimeError("Both HF endpoints failed")


def _local_inference(prompt: str) -> str:
    """Load phi-2 + LoRA adapter locally. Requires CUDA GPU."""
    import shutil
    if not shutil.which("nvidia-smi"):
        raise RuntimeError("No CUDA GPU — nvidia-smi not found")

    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("No CUDA GPU — torch.cuda.is_available() is False")

    from functools import lru_cache

    @lru_cache(maxsize=1)
    def _pipeline():
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline as hf_pipeline
        tokenizer = AutoTokenizer.from_pretrained(
            settings.BASE_SOP_MODEL, trust_remote_code=True, token=settings.HF_TOKEN,
        )
        base = AutoModelForCausalLM.from_pretrained(
            settings.BASE_SOP_MODEL,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
            token=settings.HF_TOKEN,
        )
        model = PeftModel.from_pretrained(base, settings.SOP_ADAPTER, token=settings.HF_TOKEN)
        model = model.merge_and_unload()
        return hf_pipeline(
            "text-generation", model=model, tokenizer=tokenizer,
            max_new_tokens=900, temperature=0.7, do_sample=True,
        )

    pipe = _pipeline()
    out = pipe(prompt)[0]["generated_text"]
    return out.split("Output:")[-1].strip()


def generate_sop(profile: dict, program: dict, context: str) -> str:
    """Generate a SOP draft using the fine-tuned phi-2 model.

    Tries HF Serverless API first (no GPU needed), then local GPU.
    Raises RuntimeError if both fail — sop_agent falls back to Gemini.
    """
    prompt = _PROMPT.format(
        profile=json.dumps(profile),
        program=f"{program.get('university', '')} {program.get('program', '')}",
        context=context[:1500],
    )

    try:
        text = _hf_inference_api(prompt)
        print(f"[inference] phi-2 merged via HF API: {len(text)} chars")
        return text
    except Exception as exc:
        print(f"[inference] HF API failed: {exc}")

    try:
        text = _local_inference(prompt)
        print(f"[inference] phi-2 local GPU: {len(text)} chars")
        return text
    except Exception as exc:
        print(f"[inference] local GPU failed: {exc}")
        raise RuntimeError("phi-2 unavailable — set SOP_MODEL_MERGED and HUGGINGFACE_TOKEN") from exc
