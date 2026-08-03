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
FALLBACK_MODEL = "llama-3.1-8b-instant"  # v4.15.3: llama-4-scout removed from Groq

VIACT_DESCRIPTION = (
    "viAct is an AI computer-vision safety-monitoring platform for construction, "
    "mining, and industrial sites. Detects PPE violations, unsafe behaviour, "
    "hazardous zones from CCTV footage in real time."
)

VALID_CATEGORIES = {
    "ai_vision", "wearables_iot", "site_documentation",
    "compliance_checklist", "project_management",
}

# Tavily queries — deliberately varied to catch different niches.
# v4.15.1: added 6 vertical-specific queries because the original 5 all
# targeted construction/PPE and the discovery pool saturated at ~78 known
# competitors. Mining / Oil & Gas / Logistics / Manufacturing / APAC
# vendors are equally in-scope for viAct's 5-industry buyer base.
DISCOVERY_QUERIES = [
    "viact.ai competitors alternatives AI construction safety",
    "best AI computer vision safety monitoring construction software",
    "EHS software AI vision worker safety platforms",
    "construction site AI monitoring PPE detection platforms",
    "AI video analytics workplace safety vendors",
    # v4.15.1 — vertical expansion beyond construction
    "AI computer vision safety monitoring mining hazard detection",
    "oil gas refinery worker safety AI video monitoring",
    "warehouse worker safety AI camera PPE detection",
    "manufacturing plant safety computer vision monitoring platform",
    "port terminal shipyard AI safety monitoring vendors",
    "APAC industrial worker safety AI startup platform",
    # v4.15.1 — regional + product-category deep cuts
    "European construction safety AI monitoring startup vendors",
    "Middle East industrial HSE AI video analytics vendors",
    "India Southeast Asia AI construction safety platforms",
    "AI fall detection scaffolding safety monitoring software",
    "AI forklift pedestrian collision warning warehouse safety",
    "AI drowsiness fatigue detection industrial workers platform",
    # v4.15.8 — untapped verticals + adjacent safety niches
    "AI utility power grid worker safety monitoring vendors",
    "AI rail transit safety monitoring computer vision platform",
    "AI marine port shipyard worker safety camera vendors",
    "AI pharma food manufacturing safety monitoring platform",
    "AI steel foundry metal plant worker safety vendors",
    "AI drone inspection industrial site safety platform",
    "OSHA compliance automation AI safety software vendors",
    "smart helmet wearable industrial worker safety startup",
    "AI robotic collision safety monitoring warehouse startup",
    "AI heat stress ergonomic industrial worker monitoring",
]

# Reviewsite / news / non-competitor domains — never treat these as competitors
BLACKLIST_DOMAINS = {
    "g2.com", "capterra.com", "trustradius.com", "getapp.com", "softwareadvice.com",
    "gartner.com", "forrester.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "medium.com", "techcrunch.com", "forbes.com", "bloomberg.com",
    "wikipedia.org", "reddit.com", "quora.com", "google.com", "microsoft.com",
    "salesforce.com", "amazon.com", "aws.amazon.com", "cloudflare.com",
    "viact.ai", "viact.com",
    # v4.15.8 — SEO / AI-tool directories that the classifier keeps mistaking
    # for the vendor's real site (produces `Observia.ai → seektool.ai/ai/observia-ai`
    # and `AI Cover → saashub.com/ai-cover` — the tool name is real, the
    # website is a third-party listing).
    "seektool.ai", "saashub.com", "producthunt.com", "aitools.fyi",
    "futuretools.io", "theresanaiforthat.com", "toolify.ai", "aitoolhunt.com",
    "aitools.inc", "aitoolsdirectory.com", "aigear.io", "insidr.ai",
    "startupstash.com", "sourceforge.net", "alternativeto.net",
    "crozdesk.com", "goodfirms.co", "clutch.co", "designrush.com",
    "owler.com", "zoominfo.com", "growjo.com", "6sense.com",
}


# ── Sources ───────────────────────────────────────────────────────────────────

def _tavily_search(query: str, max_results: int = 10) -> list[dict]:
    """
    v3.5: swapped from Tavily to DuckDuckGo (free unlimited).
    Function name kept for backward compat with existing caller sites.
    """
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "content": r.get("body", ""),
            }
            for r in results
        ]
    except Exception as e:
        print(f"  [ddg] {query[:50]}... failed: {e}")
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

v4.15.8 HARD-REJECT (learned from 2026-07-23 hallucination incident):
- REJECT AI chatbots / companion apps / conversational AI (Replika, Character.ai, Pi, Poe) — NOT industrial safety even though they use "AI".
- REJECT custom software / IT consultancies who happen to build safety projects (RaftLabs, ThinkPalm-style shops) — one-off project work, not a product.
- REJECT AI-tool directories / catalog sites (seektool.ai, saashub.com, aitools.fyi, futuretools.io, toolify.ai, sourceforge, alternativeto).
- REJECT curated lists ("A curated list of HSE software...") — those are the directory ENTRIES, not vendors.
- REJECT if you are not 100% sure the URL exists — do NOT invent plausible-sounding domains. If the evidence doesn't spell out the exact URL, leave website blank and the row will be dropped by post-filter.
- REJECT AI content generators / marketing writers / SEO tools that mention "safety" only tangentially.
- If uncertain whether the company matches viAct's scope, REJECT. Better to output ZERO than to include a chatbot.

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
    # v4.15.8: evidence truncated to 9000 chars (was 16000). With 27 discovery
    # queries × 10 results each + G2/Capterra scrapes, total evidence blows
    # past 100 KB and the classifier request exceeds Groq's TPM ceiling —
    # llama-3.3-70b RPM cap gets hit → fallback llama-3.1-8b-instant fails
    # on 6000 TPM cap. 9 KB fits both model tiers with headroom for the
    # known-competitor list.
    prompt = CLASSIFIER_PROMPT_TEMPLATE.format(
        viact_description=VIACT_DESCRIPTION,
        known_list=", ".join(sorted(known)) if known else "(none)",
        evidence=evidence[:5500],
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
    """v4.15.8: aggressive normalization so 'Observia.ai' == 'Observia AI'.
    Also drops the .ai/.io/.com trailing pseudo-suffix that AI-tool startups
    tack onto their brand ("Observia.ai" and "Observia" collide)."""
    n = name.lower().strip()
    n = re.sub(r"[,\.]", " ", n)
    n = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|pvt|private)\b", "", n)
    n = re.sub(r"\b(ai|io|app|tech|technologies|systems|group|labs|solutions)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    # Also collapse all non-alphanumeric so "Observia AI" and "ObservIA-ai" match
    n_collapsed = re.sub(r"[^a-z0-9]+", "", n)
    return n_collapsed if n_collapsed else n


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


def _domain_resolves(domain: str, timeout: float = 3.0) -> bool:
    """v4.15.8: quick DNS check — does this domain actually resolve?
    Rejects LLM-hallucinated URLs like safeguardvision.ai / gemini3.io /
    aicover.com that look plausible but don't exist. Under Groq TPM
    pressure the fallback model llama-3.1-8b-instant hallucinates
    company URLs; without a resolution check they land in the sheet
    and pollute the tracked list."""
    import socket
    if not domain:
        return False
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False


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

        # v4.15.8: DNS resolution check — rejects LLM-hallucinated domains.
        # Was learned the hard way on 2026-07-23: classifier ran under
        # TPM-pressure fallback (llama-3.1-8b-instant), returned 6 candidates
        # (NWarch AI, AI Cover, Brandwise, Replika, SafeGuard Vision AI,
        # Gemini 3), 5 of them with URLs that don't even DNS-resolve, and
        # the 6th (Replika) was a romantic AI chatbot — none industrial safety.
        if not _domain_resolves(n_domain):
            print(f"    [post-filter] REJECT {name!r} — {n_domain!r} does not resolve (LLM hallucination)")
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
