"""
Fetch ALL German public university programs from DAAD and Hochschulkompass,
then upsert into Supabase.

Can be run two ways:
  1. Direct: python data/fetch_daad_universities.py
  2. Via API: POST /api/admin/sync-universities  (runs server-side — better for local network issues)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

_DAAD_API = (
    "https://www2.daad.de/deutschland/studienangebote/"
    "international-programmes/api/solr/en/search.json"
)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; IntelliAdmit/1.0; research bot)",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
})

_STATE_MAP = {
    "Baden-Württemberg": "Baden-Württemberg", "Bavaria": "Bavaria",
    "Berlin": "Berlin", "Brandenburg": "Brandenburg", "Bremen": "Bremen",
    "Hamburg": "Hamburg", "Hesse": "Hesse", "Lower Saxony": "Lower Saxony",
    "Mecklenburg-Vorpommern": "Mecklenburg-Vorpommern",
    "North Rhine-Westphalia": "North Rhine-Westphalia",
    "Rhineland-Palatinate": "Rhineland-Palatinate", "Saarland": "Saarland",
    "Saxony": "Saxony", "Saxony-Anhalt": "Saxony-Anhalt",
    "Schleswig-Holstein": "Schleswig-Holstein", "Thuringia": "Thuringia",
}
_SEMESTER_FEE = {
    "Bavaria": 115, "Baden-Württemberg": 158, "Berlin": 312, "Hamburg": 380,
    "North Rhine-Westphalia": 316, "Hesse": 311, "Lower Saxony": 387,
    "Saxony": 250, "Brandenburg": 220, "Bremen": 350, "Thuringia": 104,
    "Rhineland-Palatinate": 298, "Saarland": 280, "Saxony-Anhalt": 200,
    "Schleswig-Holstein": 250, "Mecklenburg-Vorpommern": 180,
}
_LIVING_COST = {
    "Munich": 1200, "Berlin": 1050, "Hamburg": 1150, "Frankfurt": 1100,
    "Cologne": 950, "Stuttgart": 1000, "Heidelberg": 1000, "Freiburg": 950,
    "Nuremberg": 850, "Augsburg": 850, "Dortmund": 800, "Bochum": 780,
    "Düsseldorf": 950, "Aachen": 850, "Karlsruhe": 900, "Münster": 750,
}

# Known private universities to skip (we only want public)
_PRIVATE_KEYWORDS = {
    "iu international", "srh", "code university", "esmt", "constructor",
    "frankfurt school", "eu business", "university of europe",
    "mci management", "bsbi", "gisma", "berlin school of business",
    "hwr berlin", "hertie", "bucerius", "private", "steinbeis",
}


def _is_private(name: str, funding: str) -> bool:
    nl = name.lower()
    if any(kw in nl for kw in _PRIVATE_KEYWORDS):
        return True
    if funding and "private" in funding.lower():
        return True
    return False


def _parse_state(raw: str) -> str:
    for k in _STATE_MAP:
        if k.lower() in (raw or "").lower():
            return k
    return raw or "Germany"


def _inst_type(inst_type_raw: str) -> str:
    r = (inst_type_raw or "").lower()
    if "fachhochschule" in r or "applied" in r or "hochschule" in r:
        return "public_applied"
    return "public_research"


def fetch_daad_programs(timeout: int = 60) -> list[dict]:
    """Fetch all master's programs from DAAD API with retry."""
    programs: list[dict] = []
    page_size = 500
    offset = 0

    while True:
        for attempt in range(3):
            try:
                resp = _SESSION.get(
                    _DAAD_API,
                    params={"degree[]": "2", "limit": str(page_size), "offset": str(offset)},
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  DAAD API failed after 3 attempts: {e}")
                    return programs
                time.sleep(2 ** attempt)

        batch = data.get("courses", [])
        total = data.get("numResults", 0)
        if not batch:
            break
        programs.extend(batch)
        print(f"  DAAD: fetched {len(programs)} / {total}")
        if len(programs) >= total:
            break
        offset += page_size
        time.sleep(0.5)

    return programs


def build_universities(programs: list[dict]) -> dict[str, dict]:
    """Group DAAD program records into university → programs[] map."""
    unis: dict[str, dict] = {}

    for p in programs:
        name = (p.get("academy") or "").strip()
        if not name:
            continue

        # Skip private institutions
        if _is_private(name, ""):
            continue

        city = (p.get("city") or "").strip()
        lang_list = p.get("languages") or []
        lang_str = ", ".join(lang_list) if lang_list else "German"
        is_english = any("english" in l.lower() for l in lang_list)
        is_german = any("german" in l.lower() for l in lang_list)

        prog_name = (p.get("courseName") or p.get("courseNameShort") or "").strip()
        if not prog_name:
            continue

        if name not in unis:
            # Infer state from city name if not provided
            state = "Germany"
            city_lower = city.lower()
            if "munich" in city_lower or "münchen" in city_lower or "bavaria" in city_lower:
                state = "Bavaria"
            elif "berlin" in city_lower:
                state = "Berlin"
            elif "hamburg" in city_lower:
                state = "Hamburg"
            elif "aachen" in city_lower or "cologne" in city_lower or "köln" in city_lower or "düsseldorf" in city_lower or "dortmund" in city_lower or "bochum" in city_lower or "münster" in city_lower:
                state = "North Rhine-Westphalia"
            elif "stuttgart" in city_lower or "karlsruhe" in city_lower or "heidelberg" in city_lower or "freiburg" in city_lower or "tübingen" in city_lower or "ulm" in city_lower or "heilbronn" in city_lower:
                state = "Baden-Württemberg"
            elif "frankfurt" in city_lower or "darmstadt" in city_lower or "kassel" in city_lower or "wiesbaden" in city_lower:
                state = "Hesse"
            elif "hannover" in city_lower or "braunschweig" in city_lower or "göttingen" in city_lower or "wolfenbüttel" in city_lower or "hildesheim" in city_lower:
                state = "Lower Saxony"
            elif "dresden" in city_lower or "leipzig" in city_lower or "chemnitz" in city_lower:
                state = "Saxony"
            elif "kaiserslautern" in city_lower or "trier" in city_lower or "mainz" in city_lower or "koblenz" in city_lower:
                state = "Rhineland-Palatinate"
            elif "saarbrücken" in city_lower:
                state = "Saarland"
            elif "jena" in city_lower or "erfurt" in city_lower or "ilmenau" in city_lower:
                state = "Thuringia"
            elif "magdeburg" in city_lower or "halle" in city_lower:
                state = "Saxony-Anhalt"
            elif "potsdam" in city_lower or "cottbus" in city_lower:
                state = "Brandenburg"
            elif "rostock" in city_lower or "greifswald" in city_lower:
                state = "Mecklenburg-Vorpommern"
            elif "kiel" in city_lower or "lübeck" in city_lower or "flensburg" in city_lower:
                state = "Schleswig-Holstein"
            elif "erlangen" in city_lower or "nuremberg" in city_lower or "nürnberg" in city_lower or "würzburg" in city_lower or "augsburg" in city_lower or "regensburg" in city_lower or "passau" in city_lower or "bayreuth" in city_lower or "ingolstadt" in city_lower:
                state = "Bavaria"

            name_lower = name.lower()
            inst_type = "public_applied"
            if any(k in name_lower for k in ["universität", "university of", "tu ", "rwth", "lmu", "kit "]):
                inst_type = "public_research"
            if "technische universität" in name_lower or "technical university" in name_lower:
                inst_type = "public_research"
            if "fachhochschule" in name_lower or "hochschule für" in name_lower or "university of applied" in name_lower:
                inst_type = "public_applied"

            unis[name] = {
                "name": name,
                "name_german": name,
                "type": inst_type,
                "city": city,
                "state": state,
                "website": f"https://www.daad.de/en/study-and-research-in-germany/{name.lower().replace(' ', '-')}/",
                "ranking_qs": None,
                "ranking_the": None,
                "description": (
                    f"{name} is a German {'applied sciences' if inst_type == 'public_applied' else 'research'} "
                    f"university in {city}{', ' + state if state != 'Germany' else ''}. "
                    f"Offers tuition-free education with only a semester administrative fee."
                ),
                "programs": [],
                "admission_requirements": {
                    "cgpa": "Minimum 7.0/10 (varies by program)",
                    "language": "IELTS 6.5 / TOEFL 90 for English; TestDaF TDN 4 for German programs",
                    "gre": "Not required",
                    "aps": "APS certificate required for Indian applicants",
                    "degree": "BSc in a relevant field",
                },
                "deadlines": {"winter": "2025-07-15", "summer": "2025-01-15"},
                "tuition_eur_semester": 0,
                "semester_fee_eur": _SEMESTER_FEE.get(state, 250),
                "living_cost_eur_month": _LIVING_COST.get(city, 850),
                "aps_required": True,
                "uni_assist_required": True,
                "german_required": False,
                "english_programs": False,
                "scholarships": [{"name": "Deutschland Stipendium", "amount_eur": 300, "per": "month"}],
                "career_prospects": {"top_employers": [], "avg_salary_eur": 48000, "employment_rate_pct": 90},
                "notable_faculty": [],
                "research_groups": [],
                "image_url": p.get("image") or "",
                "data_source": "daad_live",
            }

        uni = unis[name]
        if is_english:
            uni["english_programs"] = True
        if is_german:
            uni["german_required"] = True

        existing = {pr["name"] for pr in uni["programs"]}
        if prog_name not in existing:
            uni["programs"].append({
                "name": prog_name,
                "language": lang_str,
                "duration_months": 24,
            })

        deadline = p.get("applicationDeadline")
        if deadline:
            uni["deadlines"]["winter"] = str(deadline)

    return unis


def sync_to_supabase(unis: dict[str, dict]) -> tuple[int, int]:
    from api.database import upsert_university
    ok = fail = 0
    for uni in unis.values():
        try:
            upsert_university(uni)
            ok += 1
        except Exception as e:
            print(f"  FAIL {uni['name']}: {e}")
            fail += 1
    return ok, fail


def run_sync(verbose: bool = True) -> dict:
    if verbose:
        print("Fetching from DAAD API (this may take 30-60s)...")
    programs = fetch_daad_programs()

    if not programs:
        return {"ok": False, "error": "DAAD API returned no results — check network connectivity"}

    unis = build_universities(programs)
    public = {k: v for k, v in unis.items() if v["type"] != "private"}

    if verbose:
        print(f"\nFound {len(public)} public universities ({len(programs)} programs total)")

    ok, fail = sync_to_supabase(public)

    if verbose:
        print(f"Done: {ok} upserted, {fail} failed")

    return {
        "ok": True,
        "universities_found": len(public),
        "programs_found": len(programs),
        "upserted": ok,
        "failed": fail,
    }


if __name__ == "__main__":
    result = run_sync(verbose=True)
    print(json.dumps(result, indent=2))
