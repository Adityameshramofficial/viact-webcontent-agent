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
from utils import get_env

COMPETITORS = [
    {"name": "Protex AI",    "domain": "protex.ai"},
    {"name": "Intenseye",    "domain": "intenseye.com"},
    {"name": "Visionify",    "domain": "visionify.ai"},
    {"name": "Wakecap",      "domain": "wakecap.com"},
    {"name": "OpenSpace",    "domain": "openspace.ai"},
    {"name": "Safesite",     "domain": "safesitehq.com"},
    {"name": "Assignar",     "domain": "assignar.com"},
    {"name": "Voxel AI",     "domain": "voxelai.com"},
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


def _tavily_search(query: str, max_results: int = 5, search_depth: str = "basic") -> list[dict]:
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": get_env("TAVILY_API_KEY"),
                "query": query,
                "search_depth": search_depth,
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=20,
        )
        return resp.json().get("results", [])
    except Exception:
        return []


def _scan_competitor_news(emit=print) -> list[dict]:
    """Search for recent news/announcements from each competitor."""
    results = []
    for comp in COMPETITORS:
        emit(f"  Scanning {comp['name']}...")
        query = f"{comp['name']} {comp['domain']} new feature product launch announcement 2025"
        hits = _tavily_search(query, max_results=3)
        for h in hits:
            url = h.get("url", "")
            # Only include results actually from this competitor's domain
            if comp["domain"] in url or comp["name"].lower().replace(" ", "") in url.lower():
                results.append({
                    "competitor": comp["name"],
                    "title":      h.get("title", ""),
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

    prompt = f"""You are a content strategist for viAct, an AI construction safety platform.

TODAY'S COMPETITOR INTEL:
{news_text}

TODAY'S INDUSTRY TRENDS:
{trends_text}

TODAY'S MARKETING OPPORTUNITIES:
{opps_text}

Based on this intel, suggest the SINGLE BEST content topic for each of these 3 page types.
Pick topics that are timely, have search demand, and fill competitive gaps.

Available industries (pick one): {industries_str}
Available VA detections (pick one OR suggest a new one): {va_options_str}

Return JSON:
{{
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
  }}
}}"""

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {
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
        }


def run_daily_monitor(progress_callback=None) -> dict:
    """
    Run full competitor + trend + opportunity scan.
    Returns structured dict with all findings + AI summary.
    """
    emit = progress_callback or print

    emit("Step 1/4 — Scanning competitor news...")
    competitor_news = _scan_competitor_news(emit)

    emit("Step 2/4 — Scanning industry trends...")
    trends = _scan_industry_trends(emit)

    emit("Step 3/4 — Scanning marketing opportunities...")
    opportunities = _scan_marketing_opportunities(emit)

    emit("Step 4/5 — Generating AI executive summary...")
    summary = _llm_summarize(competitor_news, trends, opportunities)

    emit("Step 5/5 — Generating today's 3 content topics...")
    daily_topics = _generate_daily_topics(competitor_news, trends, opportunities, emit)

    emit("Step 5b — Detecting competitor product launches...")
    product_launches = _detect_product_launches(competitor_news, emit)

    return {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "date":             datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "executive_summary":    summary.get("executive_summary", ""),
        "top_competitor_move":  summary.get("top_competitor_move", ""),
        "trending_topic":       summary.get("trending_topic", ""),
        "viact_opportunity":    summary.get("viact_opportunity", ""),
        "urgency":              summary.get("urgency", "medium"),
        "competitor_news":  competitor_news,
        "industry_trends":  trends,
        "marketing_opportunities": opportunities,
        "daily_topics":     daily_topics,
        "product_launches": product_launches,
        "counts": {
            "competitor_news":  len(competitor_news),
            "trends":           len(trends),
            "opportunities":    len(opportunities),
            "product_launches": len(product_launches),
        },
    }
