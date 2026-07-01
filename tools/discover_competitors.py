"""
Agent 1 — Competitor Auto-Discovery

For a given product (viAct), continuously discovers NEW competitors across the
AI vision safety + construction tech space. Runs weekly and adds anything new
to the "Competitors" tab in the Partnership Leads sheet.

Sources (all free):
  1. Tavily search: 4 curated queries for viAct alternatives
  2. G2 alternatives page: g2.com/products/viact/competitors/alternatives
  3. Capterra alternatives page: capterra.com/p/.../viact-alternatives
  4. Groq LLM classifier — filters noise (review sites, generic terms, non-competitors)

Dedup against:
  - Existing 14 hardcoded competitors in tools/discover_partners.py:COMPETITOR_MAP
  - Existing rows in the "Competitors" tab of the Partnership Leads sheet
  - viact.ai itself (never list your own product)

Output: pushed directly to the "Competitors" tab. User then marks Status =
"Track" or "Skip" — only "Track" rows are picked up by Agent 2.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env, scrape_url

import requests

PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

VIACT_DESCRIPTION = (
    "viAct is an AI computer-vision safety-monitoring platform for construction, "
    "mining, and industrial sites. Detects PPE violations, unsafe behaviour, "
    "hazardous zones from CCTV footage in real time."
)

VALID_CATEGORIES = {
    "ai_vision", "wearables_iot", "site_documentation",
    "compliance_checklist", "project_management",
}

# Tavily queries — deliberately varied to catch different niches
DISCOVERY_QUERIES = [
    "viact.ai competitors alternatives AI construction safety",
    "best AI computer vision safety monitoring construction software",
    "EHS software AI vision worker safety platforms",
    "construction site AI monitoring PPE detection platforms",
    "AI video analytics workplace safety vendors",
]

# Reviewsite / news / non-competitor domains — never treat these as competitors
BLACKLIST_DOMAINS = {
    "g2.com", "capterra.com", "trustradius.com", "getapp.com", "softwareadvice.com",
    "gartner.com", "forrester.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "medium.com", "techcrunch.com", "forbes.com", "bloomberg.com",
    "wikipedia.org", "reddit.com", "quora.com", "google.com", "microsoft.com",
    "salesforce.com", "amazon.com", "aws.amazon.com", "cloudflare.com",
    "viact.ai", "viact.com",
}


# ── Sources ───────────────────────────────────────────────────────────────────

def _tavily_search(query: str, max_results: int = 10) -> list[dict]:
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": get_env("TAVILY_API_KEY"),
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  [tavily] {query[:50]}... failed: {e}")
        return []


def _fetch_alternatives_page(url: str) -> str:
    """Try Firecrawl → Jina fallback via existing scrape_url."""
    return scrape_url(url, max_chars=10000)


def _collect_all_evidence(progress) -> str:
    """Concatenate all discovered snippets into one blob for the LLM."""
    blob = ""

    # ── Tavily searches ─────────────────────────────────────────────────────
    for q in DISCOVERY_QUERIES:
        results = _tavily_search(q, max_results=10)
        progress(f"[tavily] {q[:55]}... → {len(results)} results")
        for r in results:
            blob += (
                f"\n\n--- SOURCE: tavily-search\n"
                f"Title: {r.get('title', '')}\n"
                f"URL: {r.get('url', '')}\n"
                f"Content: {r.get('content', '')[:400]}\n"
            )

    # ── G2 alternatives ─────────────────────────────────────────────────────
    g2_url = "https://www.g2.com/products/viact/competitors/alternatives"
    progress(f"[g2] Scraping {g2_url}")
    md = _fetch_alternatives_page(g2_url)
    if md:
        progress(f"     → {len(md)} chars")
        blob += f"\n\n--- SOURCE: g2-alternatives\nURL: {g2_url}\nContent: {md[:6000]}\n"
    else:
        progress("     → blocked / empty")

    # ── Capterra alternatives (search the site since URL is unknown) ────────
    capterra_results = _tavily_search(
        "viact site:capterra.com alternatives",
        max_results=3,
    )
    for r in capterra_results:
        if "capterra.com" in r.get("url", ""):
            cap_url = r["url"]
            progress(f"[capterra] Scraping {cap_url}")
            md = _fetch_alternatives_page(cap_url)
            if md:
                progress(f"     → {len(md)} chars")
                blob += (
                    f"\n\n--- SOURCE: capterra-alternatives\n"
                    f"URL: {cap_url}\nContent: {md[:6000]}\n"
                )
            break  # one Capterra page is enough

    return blob


# ── LLM classifier ────────────────────────────────────────────────────────────

def _groq_call(prompt: str, max_tokens: int = 3500) -> str:
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    kwargs = dict(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    try:
        resp = client.chat.completions.create(model=PRIMARY_MODEL, **kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e).lower()
        if "429" in err or "413" in err or "rate_limit" in err or "too large" in err:
            resp = client.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            return resp.choices[0].message.content
        raise


CLASSIFIER_PROMPT_TEMPLATE = """You are identifying competitors of viAct from search results.

viAct product context:
{viact_description}

The evidence below is a mix of Tavily search results, G2 alternatives page, and Capterra alternatives page.

TASK: Extract genuine COMPETITOR companies mentioned in the evidence.

STRICT RULES:
- Company must offer one of: AI computer vision for safety, EHS/safety compliance software, wearables/IoT for worker safety, site documentation (drones/360), or construction project management with safety features.
- DO NOT include: news sites, review sites (G2, Capterra themselves), generic terms ("Fortune 500 companies"), consulting firms, or companies clearly outside safety/construction.
- DO NOT invent companies. If a company is not mentioned in the evidence by name, skip it.
- Website must be the company's OWN domain, not a review-site URL like g2.com/products/xxx.
- Assign a category to each: ai_vision | wearables_iot | site_documentation | compliance_checklist | project_management.
- Description: 1 short sentence about what they do (from the evidence, don't invent).

ALREADY-KNOWN competitors to EXCLUDE (do NOT include these in output):
{known_list}

OUTPUT (strict JSON):
{{
  "companies": [
    {{"name": "...", "website": "...", "category": "...", "description": "..."}}
  ]
}}

EVIDENCE:
{evidence}
"""


def _classify_competitors(evidence: str, known: set[str]) -> list[dict]:
    prompt = CLASSIFIER_PROMPT_TEMPLATE.format(
        viact_description=VIACT_DESCRIPTION,
        known_list=", ".join(sorted(known)) if known else "(none)",
        evidence=evidence[:16000],
    )
    try:
        raw = _groq_call(prompt, max_tokens=3500)
        data = json.loads(raw)
        return data.get("companies", [])
    except Exception as e:
        print(f"  [classifier] LLM failed: {e}")
        return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm_domain(website: str) -> str:
    if not website:
        return ""
    w = website.lower().strip()
    w = re.sub(r"^https?://", "", w)
    w = re.sub(r"^www\.", "", w)
    w = w.split("/")[0].strip()
    return w


def _norm_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"[,\.]", "", n)
    n = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|pvt|private)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _load_known_competitors() -> tuple[set[str], set[str]]:
    """
    Return (known_names, known_domains) from:
      1. Hardcoded COMPETITOR_MAP in discover_partners.py
      2. Existing rows in the "Competitors" tab of the Partnership Leads sheet
    """
    known_names: set[str] = set()
    known_domains: set[str] = set()

    # Hardcoded map
    try:
        from discover_partners import COMPETITOR_MAP
        for slug, comp in COMPETITOR_MAP.items():
            known_names.add(_norm_name(comp["name"]))
            known_domains.add(_norm_domain(comp["domain"]))
    except Exception:
        pass

    # Existing "Competitors" tab (may not exist yet — that's fine)
    try:
        from push_to_sheets import get_sheets_service
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")
        if sheet_id:
            service = get_sheets_service()
            try:
                resp = service.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range="'Competitors'!A2:B",
                ).execute()
                for row in resp.get("values", []):
                    if len(row) >= 1:
                        known_names.add(_norm_name(row[0]))
                    if len(row) >= 2:
                        known_domains.add(_norm_domain(row[1]))
            except Exception:
                pass  # tab doesn't exist yet — that's expected on first run
    except Exception:
        pass

    return known_names, known_domains


def _post_filter(candidates: list[dict], known_names: set[str],
                 known_domains: set[str]) -> list[dict]:
    """Final safety net after LLM classification."""
    out = []
    seen_names: set[str] = set()
    seen_domains: set[str] = set()

    for c in candidates:
        name = (c.get("name") or "").strip()
        website = (c.get("website") or "").strip()
        category = (c.get("category") or "").strip()
        description = (c.get("description") or "").strip()

        if not name or not website:
            continue

        n_name = _norm_name(name)
        n_domain = _norm_domain(website)

        # Skip blacklisted / already-known
        if n_domain in BLACKLIST_DOMAINS:
            continue
        if n_name in known_names or n_domain in known_domains:
            continue
        if n_name in seen_names or n_domain in seen_domains:
            continue

        # Category sanity
        if category not in VALID_CATEGORIES:
            category = "ai_vision"  # safe default for uncategorized

        seen_names.add(n_name)
        seen_domains.add(n_domain)

        out.append({
            "name": name,
            "website": website,
            "category": category,
            "description": description[:250],
        })

    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def _seed_existing_competitors(progress) -> int:
    """
    v2 seeding: ensure the 14 hardcoded competitors from discover_partners.COMPETITOR_MAP
    appear in the Competitors tab with Status='Track' pre-set.

    Idempotent — push_competitors dedups by name/domain, so re-runs won't add duplicates.
    Returns the count of rows actually appended.
    """
    try:
        from discover_partners import COMPETITOR_MAP
        from push_to_sheets import push_competitors
    except ImportError as e:
        progress(f"[seed] cannot import COMPETITOR_MAP: {e}")
        return 0

    # Category mapping for the 14 existing competitors (best-effort labels)
    category_hints = {
        "openspace":   "site_documentation",
        "matterport":  "site_documentation",
        "thinxtra":    "wearables_iot",
        "clickup":     "project_management",
        "trimble":     "project_management",
        "skillsignal": "wearables_iot",
        "dronedeploy": "site_documentation",
        "kwant":       "wearables_iot",
        "hammertech":  "compliance_checklist",
        "intenseye":   "ai_vision",
        "protex":      "ai_vision",
        "visionify":   "ai_vision",
        "cority":      "compliance_checklist",
        "fogsphere":   "ai_vision",
    }

    today = date.today().isoformat()
    seed_rows = []
    for slug, comp in COMPETITOR_MAP.items():
        seed_rows.append({
            "name": comp["tab"],                # EXACT match to existing tab (preserves quirks like 'kwant', 'Visionfy')
            "website": f"https://{comp['domain']}",
            "category": category_hints.get(slug, "ai_vision"),
            "description": "Existing competitor (tab already curated).",
            "discovered_at": today,
            "discovered_via": "seeded-from-code",
            "status": "Track",                   # Pre-mark as tracked
        })

    try:
        appended = push_competitors(seed_rows)
        progress(f"[seed] pushed {appended} seed row(s) for existing competitors")
        return appended
    except Exception as e:
        progress(f"[seed] failed: {e}")
        return 0


def discover_competitors(progress=None) -> list[dict]:
    """
    Run one full discovery pass. Returns list of NEW competitors:
        [{name, website, category, description, discovered_at, discovered_via}]

    v2: Also auto-seeds the Competitors tab with the 14 hardcoded existing
    competitors (idempotent) BEFORE running Tavily/G2/Capterra discovery.
    """
    def emit(msg):
        if progress:
            progress(msg)
        else:
            print(f"  {msg}")

    # v2: Seed the 14 existing competitors first (idempotent)
    _seed_existing_competitors(emit)

    known_names, known_domains = _load_known_competitors()
    emit(f"Loaded {len(known_names)} known competitors (deduplication set)")

    evidence = _collect_all_evidence(emit)
    emit(f"Total evidence: {len(evidence)} chars from all sources")

    if len(evidence) < 500:
        emit("Not enough evidence collected — skipping LLM classification")
        return []

    raw_candidates = _classify_competitors(evidence, known_names)
    emit(f"LLM proposed {len(raw_candidates)} candidates")

    filtered = _post_filter(raw_candidates, known_names, known_domains)
    emit(f"After post-filter: {len(filtered)} NEW competitors")

    today = date.today().isoformat()
    for c in filtered:
        c["discovered_at"] = today
        c["discovered_via"] = "tavily+g2+capterra"

    return filtered


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent 1 — Competitor Auto-Discovery")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print discoveries only; do not push to sheet")
    args = parser.parse_args()

    new_competitors = discover_competitors()
    print()
    print(json.dumps(new_competitors, indent=2, ensure_ascii=False))

    if args.dry_run or not new_competitors:
        sys.exit(0)

    # Push to sheet
    try:
        from push_to_sheets import push_competitors
        appended = push_competitors(new_competitors)
        print(f"\nSheet: {appended} row(s) appended to Competitors tab")
    except Exception as e:
        print(f"\nERROR pushing to sheet: {e}", file=sys.stderr)
        sys.exit(1)
