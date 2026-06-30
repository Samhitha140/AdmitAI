"""
Source 3 — Public SOP sample websites.

Several websites publish sample motivation letters / SOPs for German universities.
Most are consultancy marketing pages (use with caution — quality is mixed) but a
few publish genuinely good structural examples that are usable after filtering.

Sites targeted:
  - mygermanuniversity.com  (research-backed samples, best quality)
  - studying-in-germany.org (structured samples)
  - collegedunia.com        (CS / engineering samples per university)
  - kanan.co                (India-specific German SOP samples)
  - yocket.com              (India → Germany samples)
  - expatrio.com            (structured guide with embedded sample)

All are publicly accessible.  We extract only the letter body (not the
surrounding advice text) using heuristics, then tag each with its field
and institution.  The confirmed_accepted flag is False for these since they
are illustrative rather than confirmed-admitted letters.
"""
from __future__ import annotations

import re
import time
import urllib.request

# Each target: url, field, university, institution_type, notes
_TARGETS = [
    {
        "url": "https://www.mygermanuniversity.com/articles/Sample-SOP-for-Masters-in-Germany",
        "field": "Computer Science",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://www.kanan.co/blog/sop-for-germany/",
        "field": "Computer Science",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://yocket.com/blog/sop-for-germany",
        "field": "Engineering",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://www.studying-in-germany.org/motivational-letter-university-admission-germany/",
        "field": "General",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://s4.collegedunia.com/germany/article/sop-for-computer-science-in-germany-guidelines-and-structure-for-top-universities",
        "field": "Computer Science",
        "university": "TU Munich",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://s3.collegedunia.com/germany/article/sop-for-ms-in-germany-guidelines-for-admission",
        "field": "Engineering",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://s3.collegedunia.com/germany/article/sop-for-mba-in-germany-guidelines-and-requirements-for-top-german-institutions",
        "field": "Business/MBA",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
    {
        "url": "https://leverageedu.com/learn/letter-of-motivation-for-german-universities/",
        "field": "General",
        "university": "German university (general)",
        "institution_type": "university",
        "level": "masters",
    },
]

# Phrases that start a real SOP block (case-insensitive)
_SOP_STARTERS = [
    r"dear admissions committee",
    r"dear sir[/\\]?or madam",
    r"i am writing to",
    r"i am pleased to submit",
    r"i am\b.{0,30}\bapply",
    r"my decision to pursue",
    r"my passion for",
    r"it is with great",
    r"i graduated from",
    r"my name is .{2,40} and i",
    r"as a student of",
    r"having completed my",
]


def _fetch(url: str, timeout: int = 12) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"    [fetch fail] {url}: {exc}")
        return None


def _html_to_text(html: str) -> str:
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<p[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"</p>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&#\d+;", "", html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _extract_sop_blocks(text: str) -> list[str]:
    """Find all blocks in the page that look like SOPs."""
    blocks = []
    for pattern in _SOP_STARTERS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start = m.start()
            # take up to 2000 words from that point
            snippet = text[start:start + 8000]
            words = snippet.split()
            if len(words) > 200:
                blocks.append(" ".join(words[:700]))  # cap at ~700 words
    return blocks


def scrape_web_sops() -> list[dict]:
    results: list[dict] = []

    for target in _TARGETS:
        url = target["url"]
        print(f"  Fetching {url[:70]}…")
        html = _fetch(url)
        if not html:
            continue

        text = _html_to_text(html)
        blocks = _extract_sop_blocks(text)

        if not blocks:
            print(f"    [no SOP found]")
            time.sleep(1)
            continue

        for i, block in enumerate(blocks[:3]):  # max 3 per page
            word_count = len(block.split())
            if word_count < 200:
                continue
            results.append({
                "source": "web_sample",
                "url": url,
                "university": target["university"],
                "program": f"MSc {target['field']}",
                "level": target["level"],
                "field": target["field"],
                "institution_type": target["institution_type"],
                "confirmed_accepted": False,  # sample pages, not confirmed
                "text": block,
                "word_count": word_count,
            })
            print(f"    [ok] block {i+1}: {word_count} words")

        time.sleep(1.5)  # polite crawl delay

    print(f"\n  Web samples: collected {len(results)} SOP candidates")
    return results


if __name__ == "__main__":
    items = scrape_web_sops()
    print(f"Total web SOPs: {len(items)}")
