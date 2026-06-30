"""
Source 2 — Reddit PRAW scraper.

Searches r/gradadmissions, r/Germany, r/Indian_Academia, and r/mspaint (Indian
students) for posts where people share their accepted motivation letters / SOPs
for German universities.  Pushshift was killed in 2024, so we use the official
Reddit API via PRAW (free, 60 req/min limit, non-commercial use is fine).

Setup required:
  1. Create a Reddit account
  2. Go to https://www.reddit.com/prefs/apps → "create another app" → "script"
  3. Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT in your .env

Without credentials this source is skipped gracefully (returns empty list).

Search queries used:
  - "motivation letter" Germany accepted master
  - "SOP" Germany TUM RWTH "got in" OR "accepted"
  - "statement of purpose" Germany 2023 OR 2024 accepted
"""
from __future__ import annotations

import os
import re
import time

# Subreddits most likely to have German SOP content from Indian applicants
_SUBREDDITS = [
    "gradadmissions",
    "germany",
    "Indian_Academia",
    "ApplyingToCollege",
    "GermanUniversities",
]

_QUERIES = [
    'motivation letter Germany accepted master',
    'SOP Germany TUM RWTH accepted',
    'statement of purpose Germany masters 2024',
    'letter of motivation Germany "got in"',
    'Motivationsschreiben Germany accepted',
]

# Keywords that strongly suggest a real SOP is pasted in the post/comment
_SOP_SIGNALS = [
    "dear admissions",
    "dear committee",
    "i am writing to express",
    "i am pleased to apply",
    "my decision to pursue",
    "statement of purpose",
    "letter of motivation",
    "my academic journey",
    "i graduated from",
    "my name is",
    "i would like to apply",
]


def _looks_like_sop(text: str) -> bool:
    t = text.lower()
    return sum(1 for s in _SOP_SIGNALS if s in t) >= 2 and len(text.split()) >= 250


def _extract_sop_from_post(text: str) -> str | None:
    """Try to extract just the SOP portion from a Reddit post."""
    # SOPs are often fenced with --- or quoted in the post
    blocks = re.split(r"\n[-=]{3,}\n", text)
    for block in blocks:
        if _looks_like_sop(block):
            return block.strip()
    if _looks_like_sop(text):
        return text.strip()
    return None


def _guess_university(text: str) -> str:
    t = text.lower()
    for name, keyword in [
        ("TU Munich", "tum"), ("TU Munich", "tu munich"), ("TU Munich", "technical university of munich"),
        ("RWTH Aachen", "rwth"), ("TU Berlin", "tu berlin"),
        ("LMU Munich", "lmu"), ("Heidelberg", "heidelberg"),
        ("KIT", " kit "), ("TU Dresden", "tu dresden"),
        ("University of Stuttgart", "stuttgart"),
    ]:
        if keyword in t:
            return name
    return "German university"


def _guess_field(text: str) -> str:
    t = text.lower()
    for field, keywords in [
        ("Computer Science", ["computer science", "informatics", "cs ", "software"]),
        ("Data Science", ["data science", "data analytics", "machine learning"]),
        ("Electrical Engineering", ["electrical", "electronics"]),
        ("Mechanical Engineering", ["mechanical", "mechatronics"]),
        ("Business/MBA", ["mba", "management", "business"]),
        ("Physics", ["physics"]),
        ("Mathematics", ["mathematics", "math"]),
    ]:
        if any(k in t for k in keywords):
            return field
    return "Engineering"


def scrape_reddit_sops(max_per_query: int = 50) -> list[dict]:
    """Scrape Reddit for shared German university SOPs via PRAW."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "IntelliAdmit SOP collector v1.0")

    if not client_id or not client_secret:
        print("  [skip] REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set — skipping Reddit source")
        print("         Get free credentials at https://www.reddit.com/prefs/apps")
        return []

    try:
        import praw
    except ImportError:
        print("  [skip] praw not installed — run: pip install praw")
        return []

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    results: list[dict] = []
    seen_ids: set[str] = set()

    for query in _QUERIES:
        for subreddit_name in _SUBREDDITS:
            try:
                subreddit = reddit.subreddit(subreddit_name)
                for post in subreddit.search(query, limit=max_per_query, sort="relevance"):
                    if post.id in seen_ids:
                        continue
                    seen_ids.add(post.id)

                    # check post body
                    full_text = f"{post.title}\n\n{post.selftext}"
                    sop = _extract_sop_from_post(full_text)
                    if sop:
                        results.append({
                            "source": f"reddit_{subreddit_name}",
                            "url": f"https://reddit.com{post.permalink}",
                            "university": _guess_university(sop),
                            "program": "MSc",
                            "level": "masters",
                            "field": _guess_field(sop),
                            "institution_type": "university",
                            "confirmed_accepted": "accepted" in full_text.lower() or "got in" in full_text.lower(),
                            "text": sop[:3000],
                            "word_count": len(sop.split()),
                        })
                        print(f"    [post] {post.title[:60]} | {len(sop.split())} words")

                    # check top comments (people often paste SOPs in comments)
                    post.comments.replace_more(limit=0)
                    for comment in post.comments.list()[:20]:
                        if comment.id in seen_ids:
                            continue
                        seen_ids.add(comment.id)
                        sop = _extract_sop_from_post(comment.body)
                        if sop:
                            results.append({
                                "source": f"reddit_{subreddit_name}_comment",
                                "url": f"https://reddit.com{post.permalink}",
                                "university": _guess_university(sop),
                                "program": "MSc",
                                "level": "masters",
                                "field": _guess_field(sop),
                                "institution_type": "university",
                                "confirmed_accepted": "accepted" in comment.body.lower(),
                                "text": sop[:3000],
                                "word_count": len(sop.split()),
                            })
                            print(f"    [comment] {len(sop.split())} words")

                time.sleep(0.5)  # respect rate limits
            except Exception as exc:
                print(f"  [warn] {subreddit_name}/{query}: {exc}")

    print(f"\n  Reddit: collected {len(results)} SOP candidates")
    return results


if __name__ == "__main__":
    items = scrape_reddit_sops()
    print(f"Total Reddit SOPs: {len(items)}")
