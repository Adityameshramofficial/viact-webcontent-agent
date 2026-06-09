"""
Agent 5 — Daily Opportunity Scanner
Monitors competitor websites + industry trends to find content gaps viAct should fill.
Runs daily via GitHub Actions, pushes ranked opportunities to "Opportunities" tab.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import requests

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

# ── Patterns copied from agent1 ──────────────────────────────────────────────
BLOG_SKIP_PATTERNS = [
    "/post/", "/blog", "/glossary", "/news/", "/case-stud",
    "/tags/", "/ehs/ehs-management-software-", "/ehs/", "/pages-sitemap",
    "/about", "/contact", "/pricing", "/careers", "/partner",
    "/resources", "/webinar", "/event", "/press", "/media",
    "/legal", "/privacy", "/terms",
]
GENERIC_URL_SUFFIXES = ("viact.ai/", "viact.ai/#", "viact.ai/?", "viact.ai")
GENERIC_KEYWORDS = {
    "safety", "system", "systems", "software", "management",
    "construction", "monitoring", "solution", "solutions",
    "worker", "workers", "digital", "smart", "tools",
    "platform", "artificial", "intelligence", "based",
    "detection", "assessment", "assessments", "automation",
    "reporting", "work", "risk",
}

# ── Constants ────────────────────────────────────────────────────────────────
PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
DEDUP_WINDOW_DAYS = 28
MAX_OPPORTUNITIES_PER_RUN = 10
OPPORTUNITY_SHEET_TAB = "Opportunities"
DEFAULT_PAGE_TYPES = ["Use Case Page"]

REGULATORY_SIGNALS = [
    "MOM", "BCA", "OSHAD", "OSHA", "ISO", "regulation", "compliance",
    "permit", "certification", "mandate", "statutory",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _topic_slug(topic: str) -> str:
    return " ".join(sorted(topic.lower().split()))


def _google_news_rss(query: str, max_results: int = 5) -> list[dict]:
    """Google News RSS fallback. Returns [{title, url, content}]."""
    import xml.etree.ElementTree as ET
    import re
    from urllib.parse import quote
    try:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        results = []
        for item in root.findall(".//item")[:max_results]:
            results.append({
                "url": item.findtext("link", ""),
                "title": item.findtext("title", ""),
                "content": re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300],
            })
        return results
    except Exception:
        return []


def _tavily_search(query: str, max_results: int = 5, include_domains: list | None = None) -> list[dict]:
    """Run a Tavily search. Falls back to Google News RSS on 429/432 or any error."""
    payload: dict = {
        "api_key": get_env("TAVILY_API_KEY"),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        resp = requests.post("https://api.tavily.com/search", json=payload, timeout=20)
        if resp.status_code in (429, 432):
            return _google_news_rss(query, max_results)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return _google_news_rss(query, max_results)


def _groq_call(messages: list[dict], max_tokens: int = 1500, temperature: float = 0.4) -> str:
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    kwargs = dict(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    try:
        resp = client.chat.completions.create(model=PRIMARY_MODEL, **kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "413" in err or "rate_limit" in err.lower() or "too large" in err.lower():
            resp = client.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            return resp.choices[0].message.content
        raise


def _get_skill_pages() -> list[str]:
    """Load automated page types from skill.md files. Falls back to DEFAULT_PAGE_TYPES."""
    try:
        from agent4_dynamic_page_builder import list_skill_pages
        pages = list_skill_pages()
        return pages if pages else list(DEFAULT_PAGE_TYPES)
    except Exception:
        return list(DEFAULT_PAGE_TYPES)


def _load_existing_opportunities() -> list[dict]:
    """
    Load existing Opportunities tab rows from INDUSTRY_SHEET_ID for dedup.
    Returns list of {"date": str, "topic_slug": str}.
    Returns [] if tab missing or Sheet unreachable.
    """
    try:
        from push_to_sheets import get_sheets_service
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{OPPORTUNITY_SHEET_TAB}'!A:C",
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            return []
        existing = []
        for row in rows[1:]:  # skip header row
            if len(row) >= 3:
                existing.append({
                    "date": str(row[0]),
                    "topic_slug": _topic_slug(str(row[2])),
                })
        return existing
    except Exception:
        return []


def _is_duplicate(topic: str, existing: list[dict]) -> bool:
    slug = _topic_slug(topic)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DEDUP_WINDOW_DAYS)).strftime("%Y-%m-%d")
    return any(ex["topic_slug"] == slug and ex["date"] >= cutoff for ex in existing)


# ── Core pipeline functions ──────────────────────────────────────────────────

def scan_competitor_landscape(page_type: str, competitors: list[dict], emit=print) -> list[dict]:
    """
    For a given page type, collect competitor page evidence via Tavily include_domains.
    Fully dynamic — uses page_type name directly in query, no hardcoded maps.
    Returns raw candidates [{"topic_raw", "source_competitor", "evidence_url", "snippet"}].
    """
    candidates = []
    for comp in competitors:
        query = f"construction safety {page_type} {comp['name']}"
        emit(f"  Scanning {comp['name']}...")
        results = _tavily_search(query, max_results=5, include_domains=[comp["url"]])
        for r in results:
            url = r.get("url", "")
            if any(p in url.lower() for p in BLOG_SKIP_PATTERNS):
                continue
            candidates.append({
                "topic_raw": r.get("title", ""),
                "source_competitor": comp["name"],
                "evidence_url": url,
                "snippet": r.get("content", "")[:200],
            })
    return candidates


def detect_trending_topics(page_type: str, emit=print) -> list[dict]:
    """
    Industry-wide trend detection via Tavily without domain filter.
    Fully dynamic — queries built from page_type name, no hardcoded maps.
    Returns candidates [{"topic_raw", "why_trending", "evidence_url", "source_competitor": None}].
    """
    queries = [
        f"construction safety {page_type} trends new topics 2025 APAC Singapore UAE",
        f"workplace safety compliance {page_type} gaps technology 2025",
    ]

    candidates = []
    for q in queries:
        emit(f"  Trend: {q[:60]}...")
        results = _tavily_search(q, max_results=5)
        for r in results:
            url = r.get("url", "")
            if any(p in url.lower() for p in BLOG_SKIP_PATTERNS):
                continue
            candidates.append({
                "topic_raw": r.get("title", ""),
                "why_trending": r.get("content", "")[:200],
                "evidence_url": url,
                "source_competitor": None,
                "snippet": r.get("content", "")[:200],
            })
    return candidates


def _extract_topics_via_llm(candidates: list[dict], page_type: str, viact_pages: list[str]) -> list[dict]:
    """
    Single Groq call — synthesize clean topic names from raw competitor/trend evidence.
    Returns [{"topic", "why_build", "competitor_names": [...], "trending_signals": [...]}].
    """
    evidence_lines = []
    for c in candidates[:30]:
        label = f"[{c['source_competitor']}]" if c.get("source_competitor") else "[Trend]"
        evidence_lines.append(
            f"{label} {c.get('topic_raw', '')} | URL: {c.get('evidence_url', '')} | {c.get('snippet', '')[:100]}"
        )
    evidence_block = "\n".join(evidence_lines)
    viact_sample = "\n".join(viact_pages[:20])

    system = (
        f"You are a content gap analyst for viAct, an AI-powered construction safety platform for APAC and Middle East.\n"
        f"Page type: {page_type}\n"
        f"Find topics viAct should build as {page_type}s based on competitor evidence.\n"
        f"Target buyers: Singapore MOM/BCA, UAE OSHAD, construction safety managers.\n"
        f"Focus on: regulatory compliance, permit-to-work, safety training, incident reporting, "
        f"contractor management, toolbox talk, industry verticals (oil & gas, marine, civil).\n"
        f"Skip: PPE detection, fall protection, crane safety, area control, behavior-based safety, "
        f"fatigue detection (viAct already has dedicated pages for these).\n"
        f"Each topic: 3-7 words, specific, searchable, actionable."
    )

    prompt = (
        f"COMPETITOR/TREND EVIDENCE:\n{evidence_block}\n\n"
        f"viAct EXISTING PAGES (exclude these):\n{viact_sample}\n\n"
        f"Extract 5-8 topics viAct should build as {page_type}s.\n"
        f"Return JSON: {{\"topics\": [{{\"topic\": str, \"why_build\": str, "
        f"\"competitor_names\": [str], \"trending_signals\": [str]}}]}}"
    )

    try:
        raw = _groq_call([
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ])
        data = json.loads(raw)
        return data.get("topics", [])
    except Exception:
        return []


def confirm_viact_gap(topic: str, viact_sitemap: list[str]) -> tuple[bool, str]:
    """
    Two-layer gap check (copied from agent1 pattern).
    Layer 1: keyword match in sitemap — fast, no API call.
    Layer 2: Tavily include_domains=viact.ai — catches pages not in sitemap.
    Returns (is_gap, confirmation_layer).
    """
    solution_pages = [
        p.lower().rstrip("/") for p in viact_sitemap
        if not any(pat in p.lower() for pat in BLOG_SKIP_PATTERNS)
        and not any(p.lower().rstrip("/").endswith(s.rstrip("/")) for s in GENERIC_URL_SUFFIXES)
    ]

    keywords = [
        w.lower() for w in topic.split()
        if len(w) >= 4 and w.lower() not in GENERIC_KEYWORDS
    ]

    if keywords:
        for page_url in solution_pages:
            url_nohyphen = page_url.replace("-", "").replace("_", "")
            if any(kw in page_url or kw in url_nohyphen for kw in keywords):
                return False, "layer1_sitemap"

    results = _tavily_search(
        f"{topic} site:viact.ai",
        max_results=3,
        include_domains=["https://viact.ai"],
    )
    for r in results:
        url = r.get("url", "").lower().rstrip("/")
        title = r.get("title", "").lower()
        if any(url.endswith(s.rstrip("/")) for s in GENERIC_URL_SUFFIXES):
            continue
        if any(p in url for p in BLOG_SKIP_PATTERNS):
            continue
        topic_kw = [w.lower() for w in topic.split() if len(w) > 4]
        if topic_kw and any(kw in url or kw in title for kw in topic_kw):
            return False, "layer2_tavily"

    return True, "confirmed"


def classify_gap_type(topic: str, evidence: list[dict]) -> str:
    combined = " ".join(
        [topic] + [e.get("snippet", "") + " " + e.get("evidence_url", "") for e in evidence]
    ).lower()
    for sig in REGULATORY_SIGNALS:
        if sig.lower() in combined:
            return "REGULATORY_GAP"
    return "MISSING"


def score_opportunity(competitor_names: list[str], gap_type: str, trend_count: int) -> int:
    """
    Score = unique_competitor_count * 2 + trend_score + gap_severity.
    Max = 7*2 + 3 + 4 = 21.
    """
    severity = {"MISSING": 3, "REGULATORY_GAP": 4, "PARTIAL": 1}.get(gap_type, 2)
    return len(set(competitor_names)) * 2 + min(trend_count, 3) + severity


def detect_page_type_for_topic(topic: str, skill_pages: list[str]) -> str:
    """
    Keyword-overlap match to best-fit automated page type from skill.md files.
    Fully dynamic — works for any page type without hardcoded signals.
    Falls back to first skill page, or 'Use Case Page' if none exist.
    """
    if not skill_pages:
        return "Use Case Page"

    topic_words = set(topic.lower().split())
    best_type = skill_pages[0]
    best_score = 0
    for pt in skill_pages:
        pt_words = set(pt.lower().split())
        score = len(topic_words & pt_words)
        if score > best_score:
            best_score = score
            best_type = pt

    return best_type


# ── Entry point ───────────────────────────────────────────────────────────────

def run_daily_scan(progress_callback=None) -> dict:
    """
    Orchestrates the full daily opportunity scan pipeline.
    Returns {"opportunities": [...], "scan_metadata": {...}}.
    """
    emit = progress_callback or print
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_time = datetime.now(timezone.utc)

    emit("=== Agent 5: Opportunity Scanner ===")

    # 1. Load automated page types
    skill_pages = _get_skill_pages()
    emit(f"Page types: {skill_pages}")

    # 2. Load competitors + viAct sitemap
    competitors: list[dict] = []
    viact_sitemap: list[str] = []
    try:
        from research_competitors import get_all_competitors, scrape_viact_sitemap
        competitors = get_all_competitors()
        emit(f"Competitors: {len(competitors)}")
        viact_sitemap = scrape_viact_sitemap()
        emit(f"viAct pages: {len(viact_sitemap)}")
    except Exception as e:
        emit(f"Warning — competitor/sitemap load failed: {e}")

    # 3. Load existing opportunities for dedup
    existing_opps = _load_existing_opportunities()
    emit(f"Existing opportunities (dedup window): {len(existing_opps)}")

    # 4. Scan per page type
    all_raw_candidates: list[dict] = []
    page_types_scanned: list[str] = []

    for page_type in skill_pages:
        emit(f"\n--- {page_type} ---")
        page_types_scanned.append(page_type)

        if competitors:
            comp_cands = scan_competitor_landscape(page_type, competitors, emit)
            all_raw_candidates.extend(comp_cands)
            emit(f"  Competitor pages found: {len(comp_cands)}")

        trend_cands = detect_trending_topics(page_type, emit)
        all_raw_candidates.extend(trend_cands)
        emit(f"  Trend signals found: {len(trend_cands)}")

    emit(f"\nTotal raw signals: {len(all_raw_candidates)}")

    # 5. LLM synthesis — one call per page type
    all_synthesized: list[dict] = []
    for page_type in page_types_scanned:
        if not all_raw_candidates:
            continue
        emit(f"Synthesizing topics for: {page_type}...")
        synthesized = _extract_topics_via_llm(all_raw_candidates, page_type, viact_sitemap)
        for t in synthesized:
            t["_page_type_hint"] = page_type
        all_synthesized.extend(synthesized)
        emit(f"  Synthesized: {len(synthesized)} candidate topics")

    emit(f"After synthesis: {len(all_synthesized)} candidates")

    # 6. Dedup + gap confirmation + scoring
    opportunities: list[dict] = []
    seen_this_run: set[str] = set()

    for t in all_synthesized:
        topic = t.get("topic", "").strip()
        if not topic:
            continue

        slug = _topic_slug(topic)
        if slug in seen_this_run:
            continue
        seen_this_run.add(slug)

        if _is_duplicate(topic, existing_opps):
            emit(f"  Skip (recent): {topic}")
            continue

        emit(f"  Gap check: {topic}")
        is_gap, _ = confirm_viact_gap(topic, viact_sitemap)
        if not is_gap:
            emit(f"  → covered by viAct")
            continue

        comp_names = t.get("competitor_names", [])
        trend_sigs = t.get("trending_signals", [])

        # Match raw evidence back to confirmed competitors
        evidence: list[dict] = []
        seen_comp: set[str] = set()
        for c in all_raw_candidates:
            cname = c.get("source_competitor")
            if cname and cname in comp_names and cname not in seen_comp:
                seen_comp.add(cname)
                evidence.append({
                    "name": cname,
                    "url": c["evidence_url"],
                    "snippet": c.get("snippet", "")[:100],
                })

        gap_type = classify_gap_type(topic, evidence)
        score = score_opportunity(comp_names, gap_type, len(trend_sigs))
        page_type = detect_page_type_for_topic(topic, skill_pages)

        opportunities.append({
            "topic": topic,
            "page_type": page_type,
            "gap_type": gap_type,
            "score": score,
            "why_build": t.get("why_build", ""),
            "competitor_evidence": evidence[:4],
            "trending_signals": trend_sigs,
            "confirmed_gap": True,
            "scan_date": today,
        })
        emit(f"  ✓ {topic} (score={score}, {gap_type})")

    opportunities.sort(key=lambda x: x["score"], reverse=True)
    opportunities = opportunities[:MAX_OPPORTUNITIES_PER_RUN]

    duration = int((datetime.now(timezone.utc) - start_time).total_seconds())

    emit(f"\n=== Done: {len(opportunities)} opportunities in {duration}s ===")

    return {
        "opportunities": opportunities,
        "scan_metadata": {
            "scan_date": today,
            "page_types_scanned": page_types_scanned,
            "competitors_scanned": len(competitors),
            "total_candidates_found": len(all_raw_candidates),
            "after_synthesis": len(all_synthesized),
            "after_dedup_and_confirm": len(opportunities),
            "model_used": PRIMARY_MODEL,
            "duration_seconds": duration,
        },
    }
