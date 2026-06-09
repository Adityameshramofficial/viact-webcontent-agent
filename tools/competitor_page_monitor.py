"""
tools/competitor_page_monitor.py — Week-over-week competitor new page detector.

Detects when competitors publish new pages so viAct can build counter-pages first.

Flow:
  1. For each competitor: fetch sitemap.xml (or Tavily fallback if blocked)
  2. Compare current URL list with last week's snapshot (.tmp/competitor_snapshot.json)
  3. Return [{competitor, url, title, snippet}] for every new URL found
  4. Save updated snapshot for next week's comparison

Edge cases:
  - First run: saves baseline, returns [] — no false "everything is new" alert
  - Sitemap blocked (403/404): Tavily search fallback silently
  - Sitemap index (.xml locs): treated as failure → Tavily fallback
"""
import datetime
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".tmp", "competitor_snapshot.json"
)


def _web_search_pages(query: str, max_results: int = 10) -> list[dict]:
    """
    Search for competitor pages: Tavily first → Google News RSS fallback.
    Used when sitemap.xml is blocked.
    """
    # Try Tavily
    try:
        key = os.getenv("TAVILY_API_KEY", "")
        if key:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": query, "search_depth": "basic",
                      "max_results": max_results},
                timeout=20,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
    except Exception:
        pass
    # Google News RSS fallback
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
                "url":     item.findtext("link", ""),
                "title":   item.findtext("title", ""),
                "content": re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300],
            })
        return results
    except Exception:
        return []


def _fetch_sitemap_urls(domain: str) -> list[str]:
    """
    Try {domain}/sitemap.xml → parse XML locs → return page URL list.
    Returns [] on any failure or if result looks like a sitemap index.
    """
    from bs4 import BeautifulSoup

    sitemap_url = f"https://{domain}/sitemap.xml"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; viact-content-agent/1.0)"}
    try:
        resp = requests.get(sitemap_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "xml")
        locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
        pages = [l for l in locs if not l.endswith(".xml")]
        # If mostly .xml entries it's a sitemap index — skip, use Tavily
        if len(pages) < len(locs) // 2 and len(locs) > 0:
            return []
        return pages[:100]
    except Exception:
        return []


def _get_competitor_urls(competitor: dict) -> list[dict]:
    """
    Return [{url, title, snippet}] for a competitor.
    Tries sitemap first; falls back to Tavily if sitemap is blocked or empty.
    """
    domain = competitor["url"].split("//")[-1].split("/")[0]

    sitemap_urls = _fetch_sitemap_urls(domain)
    if sitemap_urls:
        return [{"url": u, "title": "", "snippet": ""} for u in sitemap_urls]

    # Web search fallback — surfaces recently indexed pages
    query = f"site:{domain} safety AI construction monitoring"
    try:
        results = _web_search_pages(query, max_results=10)
        return [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("content", "")[:300],
            }
            for r in results
            if r.get("url")
        ]
    except Exception:
        return []


def load_previous_snapshot() -> dict:
    """Read .tmp/competitor_snapshot.json. Returns {} on first run (file not found)."""
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_snapshot(data: dict) -> None:
    """Write current competitor URL snapshot to .tmp/competitor_snapshot.json."""
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_new_competitor_pages(progress_callback=None) -> list[dict]:
    """
    Detect new competitor pages published since last week.

    Returns list of {competitor, domain, url, title, snippet} for each new URL.
    First run: saves baseline snapshot, returns [] (no false all-new alert).
    """
    from research_competitors import get_all_competitors

    def emit(msg: str):
        if progress_callback:
            progress_callback("agent0", msg)

    previous = load_previous_snapshot()
    is_first_run = not previous
    current: dict = {}
    new_pages: list[dict] = []
    updated_pages: list[dict] = []

    all_competitors = get_all_competitors()
    emit(f"Checking {len(all_competitors)} competitors for new/updated pages...")

    for comp in all_competitors:
        name = comp["name"]
        emit(f"  Checking {name}...")

        page_entries = _get_competitor_urls(comp)
        current_urls = list(dict.fromkeys(e["url"] for e in page_entries if e["url"]))
        # Store title map for freshness detection
        current_titles = {
            e["url"]: e.get("title", "")
            for e in page_entries if e["url"]
        }

        current[name] = {
            "urls": current_urls,
            "titles": current_titles,
            "saved_at": datetime.datetime.now().isoformat(),
        }

        if not is_first_run:
            comp_prev = previous.get(name)
            # Skip if no baseline for this competitor (0 pages = treat as first run)
            if not comp_prev or not comp_prev.get("urls"):
                continue
            prev_urls = set(comp_prev.get("urls", []))
            prev_titles = comp_prev.get("titles", {})

            for entry in page_entries:
                url = entry["url"]
                title = entry.get("title", "")
                if not url:
                    continue

                if url not in prev_urls:
                    new_pages.append({
                        "competitor": name,
                        "domain": comp["url"],
                        "url": url,
                        "title": title,
                        "snippet": entry.get("snippet", ""),
                        "change_type": "new_page",
                    })
                    emit(f"    NEW PAGE: {url}")
                elif (
                    title
                    and url in prev_titles
                    and prev_titles[url]
                    and title != prev_titles[url]
                ):
                    updated_pages.append({
                        "competitor": name,
                        "domain": comp["url"],
                        "url": url,
                        "title": title,
                        "old_title": prev_titles[url],
                        "snippet": entry.get("snippet", ""),
                        "change_type": "updated_page",
                    })
                    emit(f"    UPDATED: {url} (title changed)")

    save_snapshot(current)

    if is_first_run:
        emit("First run — baseline snapshot saved. No pages reported.")
    else:
        emit(f"Scan complete. {len(new_pages)} new page(s), {len(updated_pages)} updated page(s).")

    # Return new pages first, then updated pages (both are high-priority signals)
    return new_pages + updated_pages


if __name__ == "__main__":
    pages = get_new_competitor_pages(
        progress_callback=lambda phase, msg: print(f"[{phase}] {msg}", flush=True)
    )
    print(json.dumps(pages, indent=2, ensure_ascii=False))
