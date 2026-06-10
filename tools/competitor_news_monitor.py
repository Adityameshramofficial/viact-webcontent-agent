"""
tools/competitor_news_monitor.py — Daily competitor news + industry trend monitor.

Runs daily to find:
  1. What competitors published / announced recently
  2. What's trending in construction safety AI globally
  3. Marketing opportunities for viAct

Output: structured dict pushed to "Competitor Intel" tab in Google Sheet.
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env, scrape_url

COMPETITORS = [
    # ── AI Vision / Computer Vision Safety ──────────────────────────────────
    {"name": "Protex AI",            "domain": "protex.ai"},
    {"name": "Intenseye",            "domain": "intenseye.com"},
    {"name": "Visionify",            "domain": "visionify.ai"},
    {"name": "Voxel AI",             "domain": "voxelai.com"},
    {"name": "Smartvid.io",          "domain": "smartvid.io"},
    {"name": "Detect Technologies",  "domain": "detecttechnologies.com"},
    {"name": "Chooch",               "domain": "chooch.com"},
    {"name": "Hakimo AI",            "domain": "hakimo.ai"},
    {"name": "Surveily",             "domain": "surveily.com"},
    {"name": "Arvist AI",            "domain": "arvist.ai"},
    {"name": "Buildots",             "domain": "buildots.com"},
    {"name": "DroneDeploy",          "domain": "dronedeploy.com"},
    {"name": "Fyld",                 "domain": "fyld.ai"},
    {"name": "Attentive AI",         "domain": "attentive.ai"},
    # ── Wearables / IoT ─────────────────────────────────────────────────────
    {"name": "Wakecap",              "domain": "wakecap.com"},
    {"name": "Guardhat",             "domain": "guardhat.com"},
    {"name": "Proxgy",               "domain": "proxgy.com"},
    # ── Site Documentation / Progress ───────────────────────────────────────
    {"name": "OpenSpace",            "domain": "openspace.ai"},
    # ── Compliance / Safety Management ──────────────────────────────────────
    {"name": "Safesite",             "domain": "safesitehq.com"},
    {"name": "Assignar",             "domain": "assignar.com"},
    {"name": "HammerTech",           "domain": "hammertech.com"},
    {"name": "Field1st",             "domain": "field1st.com"},
    {"name": "SafetyCulture",        "domain": "safetyculture.com"},
    {"name": "Sitedocs",             "domain": "sitedocs.com"},
    {"name": "SafetyMint",           "domain": "safetymint.com"},
]

INDUSTRY_TREND_QUERIES = [
    "construction site safety AI technology 2025 news",
    "AI PPE detection fall protection construction latest",
    "construction safety regulation update Asia 2025",
    "computer vision workplace safety new product launch",
    "viAct competitor construction AI news",
]

MARKETING_OPPORTUNITY_QUERIES = [
    "construction safety incident news Asia 2025",
    "AI safety monitoring ROI construction case study",
    "construction fatality accident news latest",
    "workplace safety compliance regulation new 2025",
]

# Batched news queries — 5 searches cover all 25 competitors (5 credits vs 25)
COMPETITOR_NEWS_BATCHES = [
    "Protex AI OR Intenseye OR Visionify OR Voxel AI OR Smartvid construction safety news 2025",
    "Detect Technologies OR Chooch OR Hakimo AI OR Surveily OR Arvist AI safety AI 2025",
    "Buildots OR DroneDeploy OR Fyld OR Attentive AI construction safety news 2025",
    "SafetyCulture OR HammerTech OR Field1st OR Safesite OR Assignar safety software news 2025",
    "Wakecap OR Guardhat OR Proxgy OR OpenSpace OR SafetyMint workplace safety 2025",
]

PRODUCT_LAUNCH_QUERIES = [
    "Protex AI OR Intenseye OR Visionify OR Voxel AI new product launch feature release 2025",
    "construction safety AI software new product announcement release 2025",
]

LAUNCH_KEYWORDS = [
    "launch", "launches", "launched", "release", "released", "releases",
    "new product", "new feature", "new module", "new capability",
    "introduces", "introduce", "announces", "announced", "unveils", "unveiled",
    "new solution", "new platform", "new tool",
]


# Module-level flag — once Tavily limit hit, skip for rest of session
_TAVILY_LIMIT_HIT = False


def _tavily_search_raw(query: str, max_results: int = 5, search_depth: str = "basic"):
    """
    Returns list[dict] on success, None when monthly limit hit (432).
    Caller should set _TAVILY_LIMIT_HIT=True on None and switch to RSS.
    """
    try:
        key = os.getenv("TAVILY_API_KEY", "")
        if not key:
            return None
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=20,
        )
        if resp.status_code == 432:   # monthly limit exhausted
            return None
        if resp.status_code != 200:
            return []
        return resp.json().get("results", [])
    except Exception:
        return []


def _google_news_search(query: str, max_results: int = 5) -> list[dict]:
    """Free Google News RSS search — no API key, no limits."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    try:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items = root.findall(".//item")
        results = []
        for item in items[:max_results]:
            title   = item.findtext("title", "")
            link    = item.findtext("link", "")
            desc    = item.findtext("description", "")
            # Strip HTML tags from description
            import re
            desc = re.sub(r"<[^>]+>", "", desc)
            results.append({"title": title, "url": link, "content": desc[:200]})
        return results
    except Exception:
        return []


def _web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> list[dict]:
    """
    Unified search: Tavily first (credits available) → Google News RSS fallback.
    Once Tavily limit hit, uses RSS for the entire session automatically.
    """
    global _TAVILY_LIMIT_HIT
    if not _TAVILY_LIMIT_HIT:
        result = _tavily_search_raw(query, max_results, search_depth)
        if result is not None:
            return result
        _TAVILY_LIMIT_HIT = True
        print("[search] Tavily limit hit — switching to Google News RSS", flush=True)
    return _google_news_search(query, max_results)


# Keep _tavily_search as alias for backward compatibility (used in competitor_page_monitor)
def _tavily_search(query: str, max_results: int = 5, search_depth: str = "basic") -> list[dict]:
    return _web_search(query, max_results, search_depth)


def _scan_competitor_news(emit=print) -> list[dict]:
    """
    Search for recent competitor news using 5 batched queries (5 credits total).
    Each batch covers 5 competitors. Results tagged by which competitor is mentioned.
    """
    emit("  Scanning competitor news (batched)...")
    results = []
    seen = set()

    # Build name→competitor lookup for tagging results
    name_map = {c["name"].lower(): c["name"] for c in COMPETITORS}
    # Also map short tokens (e.g. "protex" → "Protex AI")
    token_map = {}
    for c in COMPETITORS:
        for token in c["name"].lower().split():
            if len(token) > 4:  # skip short words like "ai"
                token_map.setdefault(token, c["name"])

    for query in COMPETITOR_NEWS_BATCHES:
        hits = _tavily_search(query, max_results=5)
        for h in hits:
            url   = h.get("url", "")
            title = h.get("title", "")
            text  = (title + " " + h.get("content", "")).lower()
            if url in seen:
                continue
            # Tag to the first competitor name found in title/content
            matched = None
            for c in COMPETITORS:
                cname = c["name"].lower()
                if cname in text or c["domain"].split(".")[0] in text:
                    matched = c["name"]
                    break
            if not matched:
                continue
            seen.add(url)
            results.append({
                "competitor": matched,
                "title":      title,
                "url":        url,
                "snippet":    h.get("content", "")[:200],
                "type":       "competitor_news",
            })

    return results


def _scan_industry_trends(emit=print) -> list[dict]:
    """Find what's trending in construction safety AI globally."""
    results = []
    emit("  Scanning industry trends...")
    seen = set()
    for query in INDUSTRY_TREND_QUERIES:
        hits = _tavily_search(query, max_results=3)
        for h in hits:
            url = h.get("url", "")
            if url in seen:
                continue
            # Skip competitor domains (handled separately)
            if any(c["domain"] in url for c in COMPETITORS):
                continue
            seen.add(url)
            results.append({
                "title":   h.get("title", ""),
                "url":     url,
                "snippet": h.get("content", "")[:200],
                "type":    "industry_trend",
            })
    return results[:8]


def _scan_marketing_opportunities(emit=print) -> list[dict]:
    """Find incidents, regulations, or news that viAct can respond to."""
    results = []
    emit("  Scanning marketing opportunities...")
    seen = set()
    for query in MARKETING_OPPORTUNITY_QUERIES:
        hits = _tavily_search(query, max_results=3)
        for h in hits:
            url = h.get("url", "")
            if url in seen:
                continue
            seen.add(url)
            results.append({
                "title":   h.get("title", ""),
                "url":     url,
                "snippet": h.get("content", "")[:200],
                "type":    "marketing_opportunity",
            })
    return results[:6]


def _llm_summarize(competitor_news: list, trends: list, opportunities: list) -> dict:
    """Use Groq to generate a short executive summary + action items."""
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    news_text = "\n".join(
        f"- [{c['competitor']}] {c['title']}: {c['snippet'][:100]}"
        for c in competitor_news[:6]
    ) or "No competitor news found."

    trends_text = "\n".join(
        f"- {t['title']}: {t['snippet'][:100]}"
        for t in trends[:5]
    ) or "No trends found."

    opps_text = "\n".join(
        f"- {o['title']}: {o['snippet'][:100]}"
        for o in opportunities[:4]
    ) or "No opportunities found."

    prompt = f"""You are a marketing analyst for viAct, an AI construction safety platform.

COMPETITOR NEWS TODAY:
{news_text}

INDUSTRY TRENDS:
{trends_text}

MARKETING OPPORTUNITIES (incidents/regulations):
{opps_text}

Return a JSON with:
{{
  "executive_summary": "2-3 sentence summary of today's competitive landscape. What's the most important thing happening?",
  "top_competitor_move": "Most significant competitor action today (1 sentence). If none, write 'No major moves today.'",
  "trending_topic": "The single hottest topic in construction safety AI right now (5-10 words)",
  "viact_opportunity": "One specific marketing action viAct should take based on today's intel (1-2 sentences)",
  "urgency": "high|medium|low"
}}"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {
            "executive_summary": "Intel scan completed.",
            "top_competitor_move": "See competitor news below.",
            "trending_topic": "Construction Safety AI",
            "viact_opportunity": "Review findings and create targeted content.",
            "urgency": "medium",
        }


INDUSTRY_OPTIONS = [
    "Construction Safety",
    "Oil & Gas Safety",
    "Manufacturing Safety",
    "Mining Safety",
    "Facility Management",
    "Food & Beverage Safety",
]

VA_DETECTION_OPTIONS = [
    "Hot Work Perimeter Violation Detection",
    "Crane Swing Radius Violation Detection",
    "Vehicle Blind Spot Intrusion Detection",
    "Unsafe Lifting Posture Detection",
    "Emergency Exit Blockage Detection",
    "Confined Space Entry Violation Detection",
    "Struck-By-Object Hazard Detection",
    "Excavation Collapse Risk Detection",
    "Worker Isolation Detection",
    "Formwork Stability Monitoring",
    "Chemical Hazmat Container Breach Detection",
    "Equipment Thermal Overheating Detection",
    "Hazardous Dust Exposure Detection",
    "Suspended Load Swing Detection",
    "Improper Equipment Operation Detection",
]

PILLAR_PAGE_TOPICS = [
    "AI PPE Compliance Monitoring",
    "Construction Site Safety Automation",
    "Computer Vision Workplace Safety",
    "Real-Time Hazard Detection AI",
    "Safety Compliance Software Construction",
    "AI Video Analytics Construction",
    "Fall Detection Construction Sites",
    "Permit to Work Automation",
]


def _detect_product_launches(competitor_news: list, emit=print) -> list[dict]:
    """
    Detect competitor product launches by:
    1. Filtering existing competitor_news for launch keywords (0 extra credits)
    2. Running 2 dedicated Tavily queries (2 credits)
    Then using Groq to extract a clean product_name from each match.
    """
    from groq import Groq
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seen_urls = set()
    raw_launches = []

    # Pass 1 — filter existing competitor_news
    for item in competitor_news:
        text = (item.get("title", "") + " " + item.get("snippet", "")).lower()
        if any(kw in text for kw in LAUNCH_KEYWORDS):
            url = item.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                raw_launches.append(item)

    # Pass 2 — 2 dedicated Tavily queries
    emit("  Scanning for competitor product launches (2 Tavily credits)...")
    for query in PRODUCT_LAUNCH_QUERIES:
        hits = _tavily_search(query, max_results=4)
        for h in hits:
            url = h.get("url", "")
            if url in seen_urls:
                continue
            # Match to a known competitor
            matched_comp = next(
                (c["name"] for c in COMPETITORS if c["domain"] in url or c["name"].lower().replace(" ", "") in url.lower()),
                None,
            )
            text = (h.get("title", "") + " " + h.get("content", "")).lower()
            if matched_comp and any(kw in text for kw in LAUNCH_KEYWORDS):
                seen_urls.add(url)
                raw_launches.append({
                    "competitor": matched_comp,
                    "title":      h.get("title", ""),
                    "url":        url,
                    "snippet":    h.get("content", "")[:200],
                })

    if not raw_launches:
        return []

    # Groq call to extract clean product_name from each title
    try:
        client = Groq(api_key=get_env("GROQ_API_KEY"))
        items_text = "\n".join(
            f"{i+1}. [{r.get('competitor','Unknown')}] {r.get('title','')}"
            for i, r in enumerate(raw_launches[:8])
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": (
                f"For each competitor news item below, extract a clean product or feature name (3-7 words max).\n\n{items_text}\n\n"
                "Return JSON: {\"names\": [\"Product Name 1\", \"Product Name 2\", ...]}"
            )}],
            max_tokens=300,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        names = json.loads(resp.choices[0].message.content).get("names", [])
    except Exception:
        names = []

    launches = []
    for i, item in enumerate(raw_launches[:8]):
        launches.append({
            "competitor":    item.get("competitor", "Unknown"),
            "product_name":  names[i] if i < len(names) else item.get("title", "")[:60],
            "url":           item.get("url", ""),
            "snippet":       item.get("snippet", "")[:200],
            "date":          today,
        })
    return launches


def _generate_daily_topics(
    competitor_news: list,
    trends: list,
    opportunities: list,
    emit=print,
) -> dict:
    """Use Groq (free) to analyze today's intel and suggest 3 content topics."""
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    news_text = "\n".join(
        f"- [{c.get('competitor','')}] {c.get('title','')}: {c.get('snippet','')[:80]}"
        for c in competitor_news[:5]
    ) or "No competitor news."

    trends_text = "\n".join(
        f"- {t.get('title','')}: {t.get('snippet','')[:80]}"
        for t in trends[:4]
    ) or "No trends."

    opps_text = "\n".join(
        f"- {o.get('title','')}: {o.get('snippet','')[:80]}"
        for o in opportunities[:3]
    ) or "No opportunities."

    industries_str = ", ".join(INDUSTRY_OPTIONS)
    va_options_str = ", ".join(VA_DETECTION_OPTIONS)

    pillar_examples_str = ", ".join(PILLAR_PAGE_TOPICS[:6])

    solutions_options_str = (
        "Job Hazard Analysis Software, Incident Management Software, Lone Worker Monitoring System, "
        "Vehicle Control Management Software, Industrial Space Management Solution, "
        "Behaviour Based Safety Software, Scaffolding Safety Software, "
        "Housekeeping Assessment Software Solution, Crane Safety Software, "
        "Inventory Utilization Monitoring System, Ergonomics Assessment Software, "
        "Forklift Safety System, Area Control Safety System, "
        "Industrial Workforce Productivity Monitoring Solution"
    )

    prompt = f"""You are a content strategist for viAct, an AI construction safety platform.

TODAY'S COMPETITOR INTEL:
{news_text}

TODAY'S INDUSTRY TRENDS:
{trends_text}

TODAY'S MARKETING OPPORTUNITIES:
{opps_text}

Based on this intel, suggest the SINGLE BEST content topic for each of these 6 page types.
Pick topics that are timely, have search demand, and fill competitive gaps.

Available industries (pick one): {industries_str}
Available VA detections (pick one OR suggest a new one): {va_options_str}
Pillar page topic examples (or create a new one): {pillar_examples_str}
Available solutions pages (pick one): {solutions_options_str}

Return JSON:
{{
  "pillar_topic": {{
    "topic": "SEO-focused pillar page title (8-12 words, target a high-volume keyword)",
    "primary_keyword": "main keyword this page targets (4-7 words)",
    "why": "one sentence: why this pillar page is timely based on today's intel"
  }},
  "blog_topic": {{
    "topic": "blog post title (8-14 words, conversational + SEO-friendly)",
    "primary_keyword": "main keyword this blog targets (4-7 words)",
    "why": "one sentence: why this blog post angle is relevant today"
  }},
  "industry_topic": {{
    "industry": "one of the 6 industries above",
    "topic": "specific landing page topic title (8-12 words)",
    "why": "one sentence: why this is timely based on today's intel"
  }},
  "case_study_topic": {{
    "company_type": "e.g. 'Large infrastructure developer' or 'Oil refinery operator'",
    "industry": "e.g. 'Construction' or 'Oil & Gas'",
    "location": "APAC city e.g. 'Singapore' or 'Hong Kong'",
    "detection_focus": "e.g. 'Fall Detection + PPE Compliance'",
    "why": "one sentence: why this case study angle is relevant today"
  }},
  "va_topic": {{
    "detection_name": "exact detection type name (from list or a new relevant one)",
    "why": "one sentence: why this detection type is worth a new page"
  }},
  "solutions_topic": {{
    "solution_name": "exact solution name from the list above",
    "why": "one sentence: why this solution page is worth refreshing/creating today"
  }}
}}"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=850,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {
            "pillar_topic": {
                "topic": "AI-Powered Construction Site Safety Monitoring Platform",
                "primary_keyword": "construction site safety AI monitoring",
                "why": "Fallback — high search volume, core viAct offering.",
            },
            "blog_topic": {
                "topic": "How AI Is Reducing Construction Fatalities in Asia in 2025",
                "primary_keyword": "AI construction safety Asia 2025",
                "why": "Fallback — evergreen topic with strong regional relevance.",
            },
            "industry_topic": {
                "industry": "Construction Safety",
                "topic": "AI Safety Monitoring for High-Rise Construction Sites",
                "why": "Always-relevant fallback topic.",
            },
            "case_study_topic": {
                "company_type": "Large construction developer",
                "industry": "Construction",
                "location": "Singapore",
                "detection_focus": "Fall Detection + PPE",
                "why": "Fallback — review competitor news manually.",
            },
            "va_topic": {
                "detection_name": "Hot Work Perimeter Violation Detection",
                "why": "Fallback — strong competitor gap exists.",
            },
            "solutions_topic": {
                "solution_name": "Job Hazard Analysis Software",
                "why": "Fallback — high search volume, core viAct product.",
            },
        }


def _detect_website_changes(emit=print) -> list[dict]:
    """
    Detect new/updated pages on competitor websites via sitemap comparison.
    Calls competitor_page_monitor.get_new_competitor_pages() (0–4 Tavily credits).
    For NEW pages: optionally fetches content via Firecrawl.
    For each change: Groq generates a 1-sentence marketing response.
    """
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from competitor_page_monitor import get_new_competitor_pages
    except ImportError:
        return []

    emit("  Scanning competitor websites for page changes...")
    try:
        raw_changes = get_new_competitor_pages(progress_callback=lambda phase, msg: None)
    except Exception:
        return []

    if not raw_changes:
        return []

    # Fetch content snippet for NEW pages via scrape_url (Firecrawl → Jina fallback)
    for ch in raw_changes[:8]:
        if ch.get("change_type") == "new_page":
            content = scrape_url(ch["url"], max_chars=400)
            ch["content_snippet"] = content if content else ch.get("snippet", "")
        else:
            ch["content_snippet"] = ch.get("snippet", "")

    # Groq: 1-sentence marketing response for each change
    try:
        from groq import Groq
        client = Groq(api_key=get_env("GROQ_API_KEY"))
        items_text = "\n".join(
            f"{i+1}. [{ch.get('competitor','')}] {ch.get('change_type','').upper()}: {ch.get('title', ch.get('url',''))}"
            for i, ch in enumerate(raw_changes[:8])
        )
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": (
                "You are a marketing strategist for viAct (AI construction safety). "
                "For each competitor website change below, suggest a 1-sentence marketing action viAct should take.\n\n"
                f"{items_text}\n\n"
                'Return JSON: {"responses": ["action 1", "action 2", ...]}'
            )}],
            max_tokens=400,
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        responses = json.loads(resp.choices[0].message.content).get("responses", [])
    except Exception:
        responses = []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = []
    for i, ch in enumerate(raw_changes[:8]):
        result.append({
            "date":               today,
            "competitor":         ch.get("competitor", ""),
            "change_type":        ch.get("change_type", "new_page"),
            "url":                ch.get("url", ""),
            "title":              ch.get("title", ""),
            "content_snippet":    ch.get("content_snippet", "")[:300],
            "marketing_response": responses[i] if i < len(responses) else "Monitor this change and create a counter-page.",
        })
    return result


def run_daily_monitor(progress_callback=None) -> dict:
    """
    Run full competitor + trend + opportunity scan.
    Returns structured dict with all findings + AI summary.
    """
    emit = progress_callback or print

    emit("Step 0/6 — Checking competitor websites for changes...")
    website_changes = _detect_website_changes(emit)

    emit("Step 1/6 — Scanning competitor news...")
    competitor_news = _scan_competitor_news(emit)

    emit("Step 2/6 — Scanning industry trends...")
    trends = _scan_industry_trends(emit)

    emit("Step 3/6 — Scanning marketing opportunities...")
    opportunities = _scan_marketing_opportunities(emit)

    emit("Step 4/6 — Generating AI executive summary...")
    summary = _llm_summarize(competitor_news, trends, opportunities)

    emit("Step 5/6 — Generating today's 3 content topics...")
    daily_topics = _generate_daily_topics(competitor_news, trends, opportunities, emit)

    emit("Step 6/6 — Detecting competitor product launches...")
    product_launches = _detect_product_launches(competitor_news, emit)

    return {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "date":             datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "executive_summary":    summary.get("executive_summary", ""),
        "top_competitor_move":  summary.get("top_competitor_move", ""),
        "trending_topic":       summary.get("trending_topic", ""),
        "viact_opportunity":    summary.get("viact_opportunity", ""),
        "urgency":              summary.get("urgency", "medium"),
        "competitor_news":      competitor_news,
        "industry_trends":      trends,
        "marketing_opportunities": opportunities,
        "daily_topics":         daily_topics,
        "product_launches":     product_launches,
        "website_changes":      website_changes,
        "counts": {
            "competitor_news":  len(competitor_news),
            "trends":           len(trends),
            "opportunities":    len(opportunities),
            "product_launches": len(product_launches),
            "website_changes":  len(website_changes),
        },
    }
