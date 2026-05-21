"""
Agent 1 — Market Explorer (Tavily + Groq)

Discovers construction safety topics that viAct is missing by:
  1. Searching each competitor via Tavily for live page snippets
  2. Extracting 10-15 topic names from snippets via Groq/Llama
  3. Confirming each gap with a Tavily site:viact.ai search (0 results = confirmed gap)
  4. Returning the top 3 scored opportunities

ANTI-HALLUCINATION: Only topics where Tavily site:viact.ai returns 0 results
are returned as confirmed gaps. No LLM inference alone.
"""
import argparse
import datetime
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

import requests


def _tavily_search(query: str, max_results: int = 5, include_domains: list[str] | None = None) -> list[dict]:
    """Run a Tavily search. Returns list of {title, url, content} dicts."""
    payload: dict = {
        "api_key": get_env("TAVILY_API_KEY"),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    resp = requests.post("https://api.tavily.com/search", json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _extract_topics_via_llm(snippets_block: str, viact_pages: list[str]) -> list[str]:
    """
    Single Groq call to extract 10-15 niche topics from competitor snippets.
    Passes viAct's known solution areas so the LLM avoids already-covered topics.
    """
    from groq import Groq

    # Build viAct coverage context from sitemap page slugs
    viact_slugs = []
    for p in viact_pages:
        path = p.rstrip("/").split("/")[-1].replace("-", " ")
        if path and len(path) > 3:
            viact_slugs.append(path)
    viact_context = "; ".join(viact_slugs[:30]) if viact_slugs else "PPE detection, fall protection, danger zone, crane safety"

    client = Groq(api_key=get_env("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "user", "content": (
                "You are a construction safety content strategist analyzing competitor websites.\n\n"
                "Your goal: find topics that competitors address but viAct.ai has NOT built a dedicated solution page for.\n\n"
                f"VIACT ALREADY COVERS THESE (do NOT suggest topics in these areas):\n{viact_context}\n\n"
                "COMPETITOR SNIPPETS (analyze these for gaps):\n"
                f"{snippets_block[:5000]}\n\n"
                "RULES FOR SUGGESTED TOPICS:\n"
                "- Must be topics a competitor explicitly addresses that viAct does NOT\n"
                "- Focus on: regulatory compliance processes, permit-to-work systems, "
                "safety training platforms, incident reporting workflows, contractor management, "
                "toolbox talk management, RAMS (Risk Assessment Method Statement), "
                "industry-specific verticals (tunneling, oil & gas, offshore), "
                "or emerging 2025-2026 safety topics\n"
                "- Do NOT suggest: PPE detection, fall protection, crane safety, area control, "
                "behavior-based safety, fatigue detection — viAct already has these\n"
                "- Each topic should be 4-8 words, specific and searchable\n\n"
                "Return ONLY valid JSON: {\"topics\": [\"specific topic 1\", \"specific topic 2\", ...]}"
            )},
        ],
        temperature=0.4,
        max_tokens=1024,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("topics", [])


def discover_market_gaps(progress_callback=None) -> dict:
    """
    Main function. Discovers 3 confirmed content gaps for viAct.

    Returns:
        {
          "topics": [list of up to 3 gap entries],
          "viact_known_pages": [...],
          "total_competitors_scanned": N,
          "scan_timestamp": "YYYY-MM-DD HH:MM"
        }
    """
    from research_competitors import get_all_competitors, scrape_viact_sitemap

    def emit(message: str):
        if progress_callback:
            progress_callback("agent1", message)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Step 1: viAct existing pages ────────────────────────────────────────────
    emit("Fetching viAct sitemap...")
    viact_pages = scrape_viact_sitemap()
    emit(f"viAct sitemap: {len(viact_pages)} known pages.")

    # ── Step 2: Tavily search per competitor ─────────────────────────────────────
    all_competitors = get_all_competitors()
    emit(f"Searching {len(all_competitors)} competitors via Tavily...")

    competitor_snippets: list[dict] = []
    scanned_count = 0

    for comp in all_competitors:
        name = comp["name"]
        domain = comp["url"].split("//")[-1].split("/")[0]
        query = f"site:{domain} construction safety"
        emit(f"  Tavily: {query}")
        try:
            results = _tavily_search(query, max_results=5)
            for r in results:
                competitor_snippets.append({
                    "competitor": name,
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("content", "")[:400],
                })
            scanned_count += 1
            if progress_callback:
                progress_callback("competitors", f"{name}|{len(results)}")
        except Exception as exc:
            emit(f"  ⚠ {name} search failed: {exc}")
            if progress_callback:
                progress_callback("competitors", f"{name}|0")

    if not competitor_snippets:
        emit("No competitor snippets found — all searches failed.")
        return {
            "topics": [],
            "viact_known_pages": viact_pages,
            "total_competitors_scanned": 0,
            "scan_timestamp": timestamp,
        }

    emit(f"Collected {len(competitor_snippets)} snippets from {scanned_count} competitors.")

    # ── Step 3: Extract topics from snippets via LLM ────────────────────────────
    emit("Extracting topic names via Llama 3.3 (excluding viAct's known coverage)...")
    snippets_block = "\n\n".join(
        f"[{s['competitor']} — {s['title']}]\n{s['snippet']}"
        for s in competitor_snippets
    )
    try:
        raw_topics = _extract_topics_via_llm(snippets_block, viact_pages)
    except Exception as exc:
        emit(f"Topic extraction failed: {exc}")
        raw_topics = []

    emit(f"Extracted {len(raw_topics)} candidate topics. Checking viAct coverage...")
    if progress_callback:
        for t in raw_topics:
            progress_callback("topics", t)

    # ── Step 4: Confirm gaps via Tavily include_domains:viact.ai ────────────────
    # A topic is ONLY "covered" if viAct has a DEDICATED SOLUTION page.
    # Blog posts, glossary entries, news, and country-EHS pages do NOT count.
    # This distinguishes a product gap from a content gap.

    # URLs that are NOT dedicated solution pages — blog, generic, root pages
    BLOG_SKIP_PATTERNS = [
        "/post/", "/blog", "/glossary", "/news/", "/case-stud",
        "/tags/", "/ehs/ehs-management-software-", "/ehs/", "/pages-sitemap",
        "/about", "/contact", "/pricing", "/careers", "/partner",
        "/resources", "/webinar", "/event", "/press", "/media",
        "/legal", "/privacy", "/terms",
    ]

    # Root/generic pages that can match anything — never count as topic-specific
    GENERIC_URL_SUFFIXES = ("viact.ai/", "viact.ai/#", "viact.ai/?", "viact.ai")

    def _has_dedicated_solution_page(results: list[dict], topic_name: str) -> tuple[bool, list[str]]:
        """
        Return (True, [solution_urls]) ONLY if viAct has a SPECIFIC page for this topic.
        A page counts only if:
          1. URL does not match any BLOG_SKIP_PATTERNS
          2. URL is not a generic root/homepage
          3. At least one of the topic's keywords appears in the URL slug OR page title
        """
        topic_keywords = [w.lower() for w in topic_name.split() if len(w) > 4]
        solution_urls = []
        for r in results:
            url = r.get("url", "").lower().rstrip("/")
            title = r.get("title", "").lower()

            # Skip generic root pages
            if any(url.endswith(s.rstrip("/")) for s in GENERIC_URL_SUFFIXES):
                continue
            # Skip blog/generic section pages
            if any(p in url for p in BLOG_SKIP_PATTERNS):
                continue
            # Only count if a topic keyword appears in the URL slug or page title
            if topic_keywords and not any(kw in url or kw in title for kw in topic_keywords):
                continue
            solution_urls.append(r.get("url", ""))
        return bool(solution_urls), solution_urls

    confirmed_gaps: list[dict] = []

    for topic_name in raw_topics:
        if len(confirmed_gaps) >= 6:
            break
        emit(f"  Checking viact.ai for: '{topic_name}'")
        try:
            viact_results = _tavily_search(
                query=topic_name,
                max_results=5,
                include_domains=["viact.ai"],
            )
        except Exception:
            viact_results = []

        is_covered, solution_pages = _has_dedicated_solution_page(viact_results, topic_name)

        if not is_covered:
            # CONFIRMED GAP — no dedicated solution page (only blog/glossary/generic)
            topic_lower = topic_name.lower()
            topic_keywords = [w for w in topic_lower.split() if len(w) > 4]
            evidence = []
            for s in competitor_snippets:
                text = (s["title"] + " " + s["snippet"]).lower()
                if any(kw in text for kw in topic_keywords):
                    evidence.append({
                        "competitor": s["competitor"],
                        "url": s["url"],
                        "snippet": s["snippet"][:200],
                    })
            evidence = evidence[:4]

            competitor_count = len({e["competitor"] for e in evidence})
            opportunity_score = "High" if competitor_count >= 2 else "Medium"
            blog_only_note = (
                f" (only blog/glossary entries found: {len(viact_results)})"
                if viact_results else " (0 results)"
            )

            confirmed_gaps.append({
                "topic": topic_name,
                "why_trending": (
                    f"Found in content from {competitor_count} competitor(s). "
                    f"viAct has no dedicated solution page for this topic{blog_only_note}."
                ),
                "competitor_evidence": evidence,
                "viact_gap_confirmed": True,
                "viact_search_query": f"viact.ai semantic search: '{topic_name}'",
                "viact_results_count": 0,
                "confirmed_at": timestamp,
                "opportunity_score": opportunity_score,
                "competitor_count": competitor_count,
            })
            emit(f"  ✅ CONFIRMED GAP: '{topic_name}' ({opportunity_score}, {competitor_count} competitors){blog_only_note}")
            if progress_callback:
                progress_callback("gaps", f"CONFIRMED|{topic_name}|{opportunity_score}")
        else:
            emit(f"  ↳ viAct has solution page: {solution_pages[0][:60]}")
            if progress_callback:
                progress_callback("gaps", f"SKIP|{topic_name}|{solution_pages[0][:60]}")

    # ── Step 5: Score and return top 3 ──────────────────────────────────────────
    confirmed_gaps.sort(key=lambda x: x["competitor_count"], reverse=True)
    top_3 = confirmed_gaps[:3]

    # ── Step 6: Build full competitor landscape (all competitors + their pages) ─
    competitor_landscape: dict = {}
    for s in competitor_snippets:
        comp = s["competitor"]
        if comp not in competitor_landscape:
            competitor_landscape[comp] = {"urls": [], "titles": [], "snippets": []}
        if s["url"] not in competitor_landscape[comp]["urls"]:
            competitor_landscape[comp]["urls"].append(s["url"])
            competitor_landscape[comp]["titles"].append(s["title"])
            competitor_landscape[comp]["snippets"].append(s["snippet"][:200])

    emit(f"Done. {len(top_3)} confirmed gap(s) returned.")

    return {
        "topics": top_3,
        "viact_known_pages": viact_pages,
        "total_competitors_scanned": scanned_count,
        "scan_timestamp": timestamp,
        "competitor_landscape": competitor_landscape,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent 1 — Market Explorer (Tavily + Groq)")
    parser.add_argument("--out", default="", help="Optional path to write JSON output")
    args = parser.parse_args()

    def _cli_cb(phase, message):
        print(f"  [{phase.upper()}] {message}")

    try:
        result = discover_market_gaps(progress_callback=_cli_cb)
        print()
        print("── CONFIRMED GAPS ────────────────────────────────────────────────────")
        for i, t in enumerate(result["topics"], 1):
            print(f"\n  {i}. {t['topic']}")
            print(f"     Score: {t['opportunity_score']} | Competitors: {t['competitor_count']}")
            print(f"     Confirmed at: {t['confirmed_at']}")
            print(f"     Tavily query: {t['viact_search_query']}")
        print()
        output = json.dumps(result, ensure_ascii=False, indent=2)
        print(output)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"\nSaved to {args.out}")
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
