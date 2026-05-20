"""
Sequential competitor research — 4-Phase protocol.
Phase 1: Identify competitors by topic category (competitor map).
Phase 2: Analyze each competitor individually (one LLM call per competitor).
Phase 3: Synthesize gaps that ALL competitors missed.
Phase 4: Package and cache results.

CRITICAL: Phases run in strict sequential order. Phase 2 is a loop —
one LLM call per competitor, never batched. Do not parallelize.
"""
import argparse
import hashlib
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

# ---------------------------------------------------------------------------
# Competitor map — filtered by topic domain
# Add new categories here as viAct expands into new markets.
# ---------------------------------------------------------------------------
COMPETITOR_MAP = {
    "ai_vision": {
        "label": "AI Vision / Real-Time Detection",
        "competitors": [
            {"name": "Protex AI",   "url": "https://www.protex.ai/"},
            {"name": "Intenseye",   "url": "https://www.intenseye.com/"},
            {"name": "Visionify",   "url": "https://visionify.ai/"},
        ],
        "keywords": [
            "computer vision", "ai detection", "real-time", "camera", "vision",
            "detect", "ppe", "hazard", "fall", "height", "scaffolding",
            "construction ai", "safety ai", "video analytics",
        ],
    },
    "wearables_iot": {
        "label": "Wearables / IoT Safety",
        "competitors": [
            {"name": "Wakecap", "url": "https://wakecap.com/"},
        ],
        "keywords": [
            "wearable", "helmet", "iot", "sensor", "smart device",
            "biometric", "connected worker", "lone worker",
        ],
    },
    "site_documentation": {
        "label": "Site Documentation / Progress Tracking",
        "competitors": [
            {"name": "OpenSpace", "url": "https://openspace.ai/"},
        ],
        "keywords": [
            "documentation", "360", "photo", "walkaround", "progress",
            "reality capture", "site visibility", "as-built",
        ],
    },
    "compliance_checklist": {
        "label": "Compliance / Checklist Tools",
        "competitors": [
            {"name": "Safesite",  "url": "https://safesitehq.com/"},
            {"name": "Assignar",  "url": "https://www.assignar.com/"},
        ],
        "keywords": [
            "checklist", "compliance", "inspection", "form", "audit", "permit",
            "safety management", "mom", "bca", "regulation", "certification",
        ],
    },
    "project_management": {
        "label": "Project Management / Scheduling",
        "competitors": [
            {"name": "ClickUp",  "url": "https://clickup.com/teams/construction"},
            {"name": "Assignar", "url": "https://www.assignar.com/"},
        ],
        "keywords": [
            "project management", "scheduling", "workflow",
            "task", "planning", "resource",
        ],
    },
}

DEFAULT_CATEGORY = "ai_vision"
VIACT_SITEMAP_URL = "https://viact.ai/sitemap.xml"

# AHREFS INTEGRATION NOTE:
# The Ahrefs MCP server is available in Claude Code conversation context
# but cannot be called from Python scripts directly.
# To use live keyword data: run Ahrefs MCP tools in the conversation,
# copy the volume/trend text into your --topic brief alongside the topic.
# Future: add --ahrefs-json flag to accept pre-fetched keyword JSON.


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _llm_call(prompt: str, system: str = "", temperature: float = 0.4, max_tokens: int = 4096) -> dict:
    from groq import Groq

    client = Groq(api_key=get_env("GROQ_API_KEY"))
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def scrape_viact_sitemap() -> list[str]:
    """
    Fetch viAct sitemap and return actual page URLs for internal linking.
    Handles sitemap indexes by following pages-sitemap.xml and solution sub-sitemaps.
    """
    import requests
    from bs4 import BeautifulSoup

    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; viact-content-agent/1.0)"}

    def _fetch_locs(url: str) -> list[str]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "xml")
            return [loc.get_text(strip=True) for loc in soup.find_all("loc")]
        except Exception:
            return []

    try:
        locs = _fetch_locs(VIACT_SITEMAP_URL)
        if not locs:
            raise ValueError("empty")

        # Detect sitemap index: most locs end in .xml → follow sub-sitemaps
        xml_locs = [l for l in locs if l.endswith(".xml")]
        if len(xml_locs) > len(locs) // 2:
            # It's a sitemap index — collect actual pages from sub-sitemaps
            page_urls: list[str] = []
            priority_patterns = ["pages-sitemap", "solutions", "ehs", "video-analytics"]
            sub_urls = sorted(xml_locs, key=lambda u: (
                0 if any(p in u for p in priority_patterns) else 1
            ))
            for sub_url in sub_urls[:5]:
                sub_locs = [l for l in _fetch_locs(sub_url) if not l.endswith(".xml")]
                page_urls.extend(sub_locs[:30])
                if len(page_urls) >= 40:
                    break
            if page_urls:
                return list(dict.fromkeys(page_urls))[:50]

        # Already page URLs — filter out non-page entries
        pages = [l for l in locs if not l.endswith(".xml")]
        if pages:
            return pages[:50]
    except Exception:
        pass

    # Fallback: known core viAct pages
    return [
        "https://viact.ai/",
        "https://viact.ai/ppe-detection",
        "https://viact.ai/danger-zone",
        "https://viact.ai/fleet-management",
        "https://viact.ai/environmental-monitoring",
        "https://viact.ai/video-analytics-solution",
        "https://viact.ai/case-studies",
        "https://viact.ai/contact",
    ]


def match_category(topic: str) -> str:
    """Return the best-matching competitor category key for a given topic string."""
    topic_lower = topic.lower()
    best_key = DEFAULT_CATEGORY
    best_score = 0
    for key, cat in COMPETITOR_MAP.items():
        score = sum(1 for kw in cat["keywords"] if kw in topic_lower)
        if score > best_score:
            best_score = score
            best_key = key
    return best_key


def research_competitors(
    topic: str,
    competitor_urls: list[str] | None = None,
    progress_callback=None,
) -> dict:
    """
    Run 4-phase sequential competitor research.

    Phases must complete in strict order. Phase 2 loops over competitors
    one at a time — each with its own Gemini call — so the gap synthesis
    in Phase 3 is grounded in individual assessments, not a blended summary.

    Args:
        topic: Safety topic string.
        competitor_urls: Optional override list of URLs. Uses category defaults if None.
        progress_callback: Optional callable(phase: int, message: str) for UI progress.
    """

    def emit(phase: int, message: str):
        if progress_callback:
            progress_callback(phase, message)

    # ── Phase 1: Identify Competitors ─────────────────────────────────────────
    category_key = match_category(topic)
    category = COMPETITOR_MAP[category_key]

    if competitor_urls:
        competitors = [{"name": url, "url": url} for url in competitor_urls[:4]]
    else:
        competitors = category["competitors"]

    emit(1, (
        f"Category: '{category['label']}' — "
        f"{len(competitors)} competitors: {', '.join(c['name'] for c in competitors)}"
    ))

    viact_pages = scrape_viact_sitemap()

    # ── Phase 2: Analyze Each Competitor — Sequential, One at a Time ──────────
    # Do NOT batch these calls. Each competitor gets its own Gemini analysis.
    competitor_analyses: list[dict] = []

    for i, competitor in enumerate(competitors):
        url = competitor["url"]
        name = competitor["name"]

        # Step 2a: Scrape competitor page
        try:
            from scrape_url import scrape as _scrape
            scraped = _scrape(url)
            title = scraped.get("title", name)
            body = scraped.get("body", "")[:3000]
        except Exception as exc:
            title = name
            body = f"[Scrape failed: {exc}]"

        # Step 2b: Single-competitor analysis prompt — never bundled with others
        analysis_prompt = f"""TOPIC BEING RESEARCHED: {topic}

COMPETITOR: {name}
COMPETITOR URL: {url}
COMPETITOR PAGE CONTENT (first 3000 chars):
{body}

Analyze ONLY this one competitor page. Do not reference any other competitor.
Return ONLY valid JSON, no markdown fences.

{{
  "url": "{url}",
  "name": "{name}",
  "title": "{title}",
  "core_message": "1-2 sentence summary of their main pitch on this topic",
  "features_highlighted": ["feature1", "feature2"],
  "tone": "checklist-focused | feature-listing | problem-solving | informational",
  "has_faqs": false,
  "has_regulatory_context": false,
  "regulatory_standards_mentioned": [],
  "word_count_estimate": 0,
  "notable_absence": "The single most critical topic this page does NOT cover, specifically relevant to: {topic}"
}}"""

        try:
            analysis = _llm_call(analysis_prompt)
        except Exception as exc:
            analysis = {
                "url": url,
                "name": name,
                "title": title,
                "core_message": "Analysis unavailable",
                "features_highlighted": [],
                "tone": "unknown",
                "has_faqs": False,
                "has_regulatory_context": False,
                "regulatory_standards_mentioned": [],
                "word_count_estimate": 0,
                "notable_absence": f"Could not analyze: {exc}",
            }

        competitor_analyses.append(analysis)
        emit(2, (
            f"[{i + 1}/{len(competitors)}] {name} — "
            f"tone: {analysis.get('tone', '?')} | "
            f"absence: {analysis.get('notable_absence', '')[:70]}..."
        ))

    # ── Phase 3: Gap Synthesis — runs ONLY after Phase 2 loop is complete ─────
    synthesis_prompt = f"""TOPIC: {topic}

INDIVIDUAL COMPETITOR ANALYSES (one entry per competitor, assessed separately):
{json.dumps(competitor_analyses, indent=2)}

You have now reviewed all individual competitor analyses. Identify 2-3 critical gaps.
A gap is valid ONLY if it is absent from EVERY competitor analyzed above.
Do not invent gaps. Only report absences that are confirmed across all entries.

Return ONLY valid JSON, no markdown fences:
{{
  "identified_gaps": [
    "Gap 1: No competitor addresses [specific absence] relevant to {topic}",
    "Gap 2: All competitors [common pattern] — none cover [specific absence]"
  ],
  "keyword_signal": "1-paragraph reasoning on search trend and business opportunity for this topic in APAC/Singapore/UAE",
  "gap_brief": "400-600 word strategic brief combining the above gaps. Written in plain English for the viAct content generator. Explains the content opportunity, what angle the page should take, and why viAct is positioned to own this space."
}}"""

    synthesis = _llm_call(synthesis_prompt)

    gaps = synthesis.get("identified_gaps", [])
    emit(3, (
        f"{len(gaps)} universal gap(s) confirmed — "
        f"{gaps[0][:80]}..." if gaps else "No universal gaps found."
    ))

    # ── Phase 4: Package and Cache ─────────────────────────────────────────────
    result = {
        "topic": topic,
        "category": category["label"],
        "competitor_analyses": competitor_analyses,
        "identified_gaps": gaps,
        "keyword_signal": synthesis.get("keyword_signal", ""),
        "gap_brief": synthesis.get("gap_brief", ""),
        "viact_known_pages": viact_pages,
    }

    cache_dir = os.path.join(os.path.dirname(__file__), "..", ".tmp")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"research_{_md5(topic)}.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    emit(4, f"Research complete. Cached to {os.path.basename(cache_path)}.")
    return result


def build_gap_table(research: dict) -> list[dict]:
    """Convert competitor_analyses into rows for the 5-column gap table."""
    rows = []
    for a in research.get("competitor_analyses", []):
        wc = a.get("word_count_estimate", 0)
        depth = "High" if wc > 800 else ("Medium" if wc > 400 else "Low")

        regs = a.get("regulatory_standards_mentioned", [])
        has_reg = a.get("has_regulatory_context", False)
        reg_display = ", ".join(regs) if regs else ("General only" if has_reg else "None")

        # Determine gap type
        if not has_reg and not a.get("has_faqs"):
            gap_type = "MISSING"
        elif not has_reg:
            gap_type = "REGULATORY GAP"
        elif depth == "Low":
            gap_type = "DEPTH GAP"
        elif not a.get("has_faqs"):
            gap_type = "FORMAT GAP"
        else:
            gap_type = "PARTIAL"

        rows.append({
            "Competitor": a.get("name", ""),
            "Topic / Core Message": a.get("core_message", "")[:90],
            "URL": a.get("url", ""),
            "Content Depth": depth,
            "Regulatory Context": reg_display,
            "Notable Absence": a.get("notable_absence", "")[:90],
            "Gap Type": gap_type,
        })
    return rows


# =============================================================================
# AUTONOMOUS MARKET RADAR — Concurrent full-market sweep
# =============================================================================

def get_all_competitors() -> list[dict]:
    """Return all unique competitors across all categories (deduplicated by URL)."""
    seen: set[str] = set()
    result: list[dict] = []
    for cat in COMPETITOR_MAP.values():
        for comp in cat["competitors"]:
            if comp["url"] not in seen:
                seen.add(comp["url"])
                result.append(comp)
    return result


def _scrape_all_concurrent(
    competitors: list[dict],
    progress_callback=None,
) -> dict:
    """
    Scrape all competitor URLs simultaneously using a thread pool.
    Returns {name: {url, title, body, success, error?}}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from scrape_url import scrape as _scrape

    results: dict = {}

    def _scrape_one(comp: dict):
        name, url = comp["name"], comp["url"]
        try:
            data = _scrape(url)
            return name, {
                "url": url,
                "title": data.get("title", name),
                "body": data.get("body", "")[:2000],
                "success": True,
            }
        except Exception as exc:
            return name, {"url": url, "title": name, "body": "", "success": False, "error": str(exc)}

    with ThreadPoolExecutor(max_workers=min(len(competitors), 8)) as pool:
        futures = {pool.submit(_scrape_one, c): c for c in competitors}
        done = 0
        for future in as_completed(futures):
            name, data = future.result()
            results[name] = data
            done += 1
            if progress_callback:
                status = "✓" if data["success"] else "✗"
                progress_callback("scrape", f"{status} {name} [{done}/{len(competitors)}]")

    return results


def _build_landscape_for_topic(
    topic_entry: dict,
    all_scrapes: dict,
    viact_pages: list[str],
) -> dict:
    """
    Given one discovered topic and all pre-scraped competitor data,
    build the Market Landscape Matrix in a single Gemini call.
    """
    comp_summaries = "\n\n".join(
        f"### {name}\nURL: {data['url']}\nCONTENT:\n{data['body'][:1500]}"
        for name, data in all_scrapes.items()
        if data.get("success")
    )

    viact_str = "\n".join(viact_pages[:30]) if viact_pages else "https://viact.ai/"

    prompt = f"""TOPIC: {topic_entry['topic']}

VIACT EXISTING PAGES:
{viact_str}

COMPETITOR CONTENT (pre-scraped):
{comp_summaries}

For each competitor, assess whether they have meaningful content specifically on:
"{topic_entry['topic']}"

"Has it" = dedicated page, article, or a significant section addressing this topic directly.
"Does not have it" = topic absent, mentioned only in passing, or clearly a different focus.

Return ONLY valid JSON, no markdown fences:
{{
  "landscape_matrix": {{
    {", ".join(f'"{n}": {{"has_it": false, "evidence": "...", "url": "{d["url"]}"}}' for n, d in all_scrapes.items())}
  }},
  "competitors_with_it": ["name1"],
  "competitors_without_it": ["name2"],
  "opportunity_score": "High | Medium | Low",
  "opportunity_reason": "1-2 sentences: why this gap is a strong content opportunity for viAct specifically"
}}"""

    try:
        result = _llm_call(prompt, temperature=0.3)
    except Exception as exc:
        result = {
            "landscape_matrix": {n: {"has_it": False, "evidence": f"Analysis failed: {exc}", "url": d["url"]} for n, d in all_scrapes.items()},
            "competitors_with_it": [],
            "competitors_without_it": list(all_scrapes.keys()),
            "opportunity_score": "Unknown",
            "opportunity_reason": f"Matrix build failed: {exc}",
        }

    return {**topic_entry, **result}


def autonomous_market_radar(progress_callback=None) -> dict:
    """
    Autonomous market sweep — no topic input required.

    Flow:
      0. Scrape viAct sitemap (what viAct already has)
      1. Concurrently scrape ALL competitors across ALL categories
      2. One Gemini call: identify 3 trending topics viAct is missing
      3. For each topic: build Market Landscape Matrix (using already-scraped data)

    Returns a dict with 'topics' (list of 3), 'viact_existing_pages',
    'total_competitors_scanned', and 'scan_timestamp'.
    """
    import datetime

    def emit(phase: str, message: str):
        if progress_callback:
            progress_callback(phase, message)

    # ── 0. viAct sitemap ──────────────────────────────────────────────────────
    emit("init", "Scanning viAct sitemap to map existing content...")
    viact_pages = scrape_viact_sitemap()
    emit("init", f"viAct sitemap: {len(viact_pages)} known pages found.")

    # ── 1. Concurrent competitor sweep ────────────────────────────────────────
    all_competitors = get_all_competitors()
    emit("sweep", f"Launching concurrent sweep of {len(all_competitors)} competitors...")

    all_scrapes = _scrape_all_concurrent(all_competitors, progress_callback=progress_callback)
    success_count = sum(1 for d in all_scrapes.values() if d.get("success"))
    emit("sweep", f"Sweep complete: {success_count}/{len(all_competitors)} competitors scraped successfully.")

    # ── 2. Discover 3 trending topics viAct is missing ────────────────────────
    emit("discover", "Analyzing market landscape — finding gaps viAct is missing...")

    comp_block = "\n\n".join(
        f"### {name} ({data['url']})\n{data['body'][:1500]}"
        for name, data in all_scrapes.items()
        if data.get("success")
    )
    viact_pages_str = "\n".join(viact_pages[:30])

    discovery_prompt = f"""You are a construction safety AI market analyst reviewing content from 8 competitors.

VIACT EXISTING PAGES (already published — do NOT suggest these):
{viact_pages_str}

ALL COMPETITOR CONTENT (scraped simultaneously):
{comp_block}

TASK: Identify exactly 3 high-value, trending construction safety topics that:
1. Appear in content from at LEAST 2 of the competitors above
2. Are clearly NOT covered by viAct's existing pages (check the sitemap list carefully)
3. Are relevant to AI-powered construction safety in APAC (Singapore, UAE, Malaysia) in 2026
4. Have real search intent — a construction site manager would actively search for this

Return ONLY valid JSON, no markdown fences:
{{
  "topics": [
    {{
      "topic": "Concise topic name (5-8 words)",
      "why_trending": "2-3 sentences: what is driving demand for this topic in 2026 — regulations, incidents, market pressure",
      "competitor_signals": ["Competitor A has a dedicated page on X", "Competitor B's homepage prominently features Y"]
    }},
    {{
      "topic": "...",
      "why_trending": "...",
      "competitor_signals": [...]
    }},
    {{
      "topic": "...",
      "why_trending": "...",
      "competitor_signals": [...]
    }}
  ]
}}"""

    try:
        discovery = _llm_call(discovery_prompt, temperature=0.5)
        raw_topics = discovery.get("topics", [])[:3]
    except Exception as exc:
        raw_topics = [
            {"topic": "AI-Based Fall Detection for High-Rise Construction", "why_trending": f"Discovery failed: {exc}", "competitor_signals": []},
            {"topic": "PPE Compliance Monitoring with Computer Vision", "why_trending": "Default fallback topic.", "competitor_signals": []},
            {"topic": "Real-Time Danger Zone Alerts for Construction Sites", "why_trending": "Default fallback topic.", "competitor_signals": []},
        ]

    emit("discover", f"Discovered {len(raw_topics)} topic opportunities.")

    # ── 3. Build Market Landscape Matrix for each topic ───────────────────────
    # Run sequentially to respect Gemini rate limits on free tier
    enriched_topics = []
    for i, topic_entry in enumerate(raw_topics):
        emit("matrix", f"Building Market Landscape Matrix [{i + 1}/3]: {topic_entry['topic'][:50]}...")
        enriched = _build_landscape_for_topic(topic_entry, all_scrapes, viact_pages)
        enriched_topics.append(enriched)

    emit("done", "Market Radar scan complete. 3 opportunities ready for review.")

    return {
        "topics": enriched_topics,
        "viact_existing_pages": viact_pages,
        "total_competitors_scanned": len(all_competitors),
        "competitors_scanned": [c["name"] for c in all_competitors],
        "scan_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Competitor research — sequential (topic mode) or autonomous radar (market mode)"
    )
    parser.add_argument("--mode", choices=["topic", "radar"], default="topic")
    parser.add_argument("--topic", default="", help="Safety topic (topic mode only)")
    parser.add_argument(
        "--competitors", default="",
        help="Comma-separated competitor URLs (topic mode only)"
    )
    args = parser.parse_args()

    def _cli_progress(phase, message):
        print(f"  [{phase.upper()}] {message}")

    try:
        if args.mode == "radar":
            result = autonomous_market_radar(progress_callback=_cli_progress)
            print()
            print("── 3 TOPIC OPPORTUNITIES FOUND ───────────────────────────────────────")
            for i, t in enumerate(result["topics"], 1):
                print(f"\n  {i}. {t['topic']}")
                print(f"     Why trending: {t['why_trending'][:100]}...")
                print(f"     Has it: {', '.join(t.get('competitors_with_it', []))}")
                print(f"     Missing it: {', '.join(t.get('competitors_without_it', []))}")
                print(f"     Opportunity: {t.get('opportunity_score', '?')}")
            print()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if not args.topic:
                print("Error: --topic is required in topic mode", file=sys.stderr)
                sys.exit(1)
            urls = [u.strip() for u in args.competitors.split(",") if u.strip()] or None
            result = research_competitors(args.topic, urls, progress_callback=_cli_progress)
            print()
            print("── IDENTIFIED GAPS ───────────────────────────────────────────────────")
            for g in result["identified_gaps"]:
                print(f"  • {g}")
            print()
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
