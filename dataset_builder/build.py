"""
Master dataset builder for IntelliAdmit SOP fine-tuning.

Usage:
    python -m dataset_builder.build                  # full pipeline
    python -m dataset_builder.build --skip-reddit    # skip Reddit (no credentials)
    python -m dataset_builder.build --skip-synthetic # skip LLM generation (no API key)
    python -m dataset_builder.build --synthetic-only # only generate synthetic examples

Output:
    data/sop_dataset/sops.jsonl          ← training file (Mistral instruction format)
    data/sop_dataset/raw_combined.jsonl  ← raw before cleaning (for inspection)
    data/sop_dataset/build_report.json   ← stats per source

The training format matches what finetuning/dataset.py already expects:
    {
      "profile": {...},
      "program": "TU Munich MSc Computer Science",
      "response": "<the SOP text>"
    }
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data" / "sop_dataset"
RAW_PATH = DATA_DIR / "raw_combined.jsonl"
CLEAN_PATH = DATA_DIR / "sops.jsonl"
REPORT_PATH = DATA_DIR / "build_report.json"


# ── convert raw SOP record → training pair ─────────────────────────────────--

def _raw_to_training(item: dict) -> dict:
    """Convert a raw scraped/generated SOP record into the training JSONL format."""
    snap = item.get("profile_snapshot", {})
    profile = {
        "degree": snap.get("degree", "B.Tech Computer Science"),
        "cgpa": snap.get("cgpa", 8.0),
        "work_experience_years": snap.get("work_experience_years", 0),
        "target_field": item.get("field", "Computer Science"),
        "application_level": item.get("level", "masters"),
        "institution_type": item.get("institution_type", "university"),
        "intake": item.get("intake", "winter"),
    }
    program = f"{item.get('university', 'German university')} {item.get('program', 'MSc')}"
    return {
        "profile": profile,
        "program": program,
        "source": item.get("source", "unknown"),
        "confirmed_accepted": item.get("confirmed_accepted", False),
        "word_count": item.get("word_count", len(item.get("text", "").split())),
        "response": item.get("text", ""),
    }


def build(
    skip_reddit: bool = False,
    skip_synthetic: bool = False,
    synthetic_only: bool = False,
    n_synthetic_per_combo: int = 4,
) -> None:
    print(f"\n{'='*60}")
    print(f"IntelliAdmit SOP Dataset Builder")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_raw: list[dict] = []
    source_counts: dict[str, int] = {}

    # ── Source 1: GitHub / blog real examples ─────────────────────────────────
    if not synthetic_only:
        print("── Source 1: GitHub / blog (real accepted examples) ──")
        from dataset_builder.source_github import scrape_github_sops
        github_items = scrape_github_sops()
        all_raw.extend(github_items)
        source_counts["github_blog"] = len(github_items)
        print(f"   → {len(github_items)} items\n")

    # ── Source 2: Reddit ──────────────────────────────────────────────────────
    if not synthetic_only and not skip_reddit:
        print("── Source 2: Reddit (r/gradadmissions, r/Germany, etc.) ──")
        from dataset_builder.source_reddit import scrape_reddit_sops
        reddit_items = scrape_reddit_sops()
        all_raw.extend(reddit_items)
        source_counts["reddit"] = len(reddit_items)
        print(f"   → {len(reddit_items)} items\n")
    else:
        print("── Source 2: Reddit [SKIPPED] ──\n")
        source_counts["reddit"] = 0

    # ── Source 3: Web sample pages ────────────────────────────────────────────
    if not synthetic_only:
        print("── Source 3: Web sample pages ──")
        from dataset_builder.source_web import scrape_web_sops
        web_items = scrape_web_sops()
        all_raw.extend(web_items)
        source_counts["web_samples"] = len(web_items)
        print(f"   → {len(web_items)} items\n")

    # ── Source 4: Synthetic generation ───────────────────────────────────────
    if not skip_synthetic:
        print(f"── Source 4: Synthetic generation ({n_synthetic_per_combo} per combo) ──")
        from dataset_builder.source_synthetic import generate_synthetic_sops
        synth_path = DATA_DIR / "synthetic_raw.jsonl"
        synth_items = generate_synthetic_sops(
            n_per_combination=n_synthetic_per_combo,
            output_path=synth_path,
        )
        all_raw.extend(synth_items)
        source_counts["synthetic"] = len(synth_items)
        print(f"   → {len(synth_items)} items\n")
    else:
        print("── Source 4: Synthetic [SKIPPED] ──\n")
        source_counts["synthetic"] = 0

    # ── Save raw combined ─────────────────────────────────────────────────────
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        for item in all_raw:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Raw combined: {len(all_raw)} items → {RAW_PATH}\n")

    # ── Clean and deduplicate ─────────────────────────────────────────────────
    print("── Cleaning and deduplicating ──")
    from dataset_builder.cleaner import clean_and_deduplicate, save_cleaned
    clean_items = clean_and_deduplicate(all_raw)

    # ── Convert to training format ────────────────────────────────────────────
    print("\n── Converting to training format ──")
    training_items = [_raw_to_training(item) for item in clean_items]

    # Shuffle so training doesn't see all synthetic before real
    random.seed(42)
    random.shuffle(training_items)

    save_cleaned(training_items, CLEAN_PATH)

    # ── Print distribution report ─────────────────────────────────────────────
    by_source = {}
    by_field = {}
    by_uni = {}
    by_accepted = {True: 0, False: 0}
    word_counts = []

    for it in training_items:
        src = it.get("source", "?")
        by_source[src] = by_source.get(src, 0) + 1
        field = it["profile"].get("target_field", "?")
        by_field[field] = by_field.get(field, 0) + 1
        uni = it.get("program", "?").split(" ")[0]
        by_uni[uni] = by_uni.get(uni, 0) + 1
        by_accepted[it.get("confirmed_accepted", False)] += 1
        word_counts.append(it.get("word_count", 0))

    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0

    print(f"\n{'='*60}")
    print(f"FINAL DATASET: {len(training_items)} training examples")
    print(f"  Avg word count : {avg_words:.0f} words")
    print(f"  Confirmed accepted: {by_accepted[True]}")
    print(f"  Sample/synthetic  : {by_accepted[False]}")
    print(f"\n  By source:")
    for k, v in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"    {k:35s} {v}")
    print(f"\n  By field:")
    for k, v in sorted(by_field.items(), key=lambda x: -x[1]):
        print(f"    {k:35s} {v}")
    print(f"{'='*60}\n")

    # ── Save report ───────────────────────────────────────────────────────────
    report = {
        "built_at": datetime.now().isoformat(),
        "total_raw": len(all_raw),
        "total_clean": len(training_items),
        "source_raw_counts": source_counts,
        "by_source": by_source,
        "by_field": by_field,
        "confirmed_accepted": by_accepted[True],
        "avg_word_count": round(avg_words),
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved to {REPORT_PATH}")
    print(f"\nTraining file ready: {CLEAN_PATH}")
    print("Next step: python -m finetuning.train")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build IntelliAdmit SOP dataset")
    parser.add_argument("--skip-reddit", action="store_true",
                        help="Skip Reddit scraping (no credentials needed)")
    parser.add_argument("--skip-synthetic", action="store_true",
                        help="Skip LLM synthetic generation (no API key needed)")
    parser.add_argument("--synthetic-only", action="store_true",
                        help="Only run the synthetic LLM generation source")
    parser.add_argument("--n-synthetic", type=int, default=4,
                        help="Number of synthetic SOPs per field/university/profile combo (default 4)")
    args = parser.parse_args()

    build(
        skip_reddit=args.skip_reddit,
        skip_synthetic=args.skip_synthetic,
        synthetic_only=args.synthetic_only,
        n_synthetic_per_combo=args.n_synthetic,
    )


if __name__ == "__main__":
    main()
