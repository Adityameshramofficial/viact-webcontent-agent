"""
tools/regulatory_scanner.py — Regulatory Trigger Scanner.

Detects new MOM / OSHAD / BCA / ISO safety guideline publications weekly.
Injects discovered topics into Agent 1's pipeline as high-priority gaps.

Flow:
  1. Tavily-search each regulatory source for recent publications
  2. Compare URLs/titles against last week's snapshot (content-hash based)
  3. First run: saves baseline, returns [] — no false alerts
  4. Subsequent runs: returns [{source, title, url, snippet, suggested_topic}]
     for every new publication detected
"""
import datetime
import hashlib
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

SNAPSHOT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".tmp", "regulatory_snapshot.json"
)

# Each entry: one Tavily query targeting a regulatory body's recent publications
REGULATORY_SOURCES = [
    {
        "source": "MOM Singapore",
        "query": "Singapore Ministry of Manpower workplace safety new guidelines advisory circular 2025 2026",
    },
    {
        "source": "WSH Council Singapore",
        "query": "WSH Council Singapore new advisory circular construction safety 2025 2026",
    },
    {
        "source": "BCA Singapore",
        "query": "BCA Building Construction Authority Singapore safety circular directive 2025 2026",
    },
    {
        "source": "UAE OSHAD",
        "query": "OSHAD Abu Dhabi new safety framework standard requirement 2025 2026",
    },
    {
        "source": "ISO 45001",
        "query": "ISO 45001 2025 2026 new amendment update occupational health safety management",
    },
]


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


def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Run a Tavily search. Falls back to Google News RSS on 429/432 or any error."""
    payload = {
        "api_key": get_env("TAVILY_API_KEY"),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }
    try:
        resp = requests.post("https://api.tavily.com/search", json=payload, timeout=20)
        if resp.status_code in (429, 432):
            return _google_news_rss(query, max_results)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return _google_news_rss(query, max_results)


def _page_hash(url: str, title: str) -> str:
    """Stable 12-char hash of (url, title) — used as snapshot key."""
    return hashlib.md5(f"{url}|{title}".encode()).hexdigest()[:12]


def _load_snapshot() -> dict:
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_snapshot(data: dict) -> None:
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def scan_regulatory_updates(progress_callback=None) -> list[dict]:
    """
    Scan regulatory sources for new publications since last run.

    Returns:
        [{source, title, url, snippet, suggested_topic}] for each new item.
        Returns [] on first run (baseline only — no false alerts).
    """
    def emit(msg: str):
        if progress_callback:
            progress_callback("regulatory", msg)

    emit(f"Scanning {len(REGULATORY_SOURCES)} regulatory sources (MOM, WSH, BCA, OSHAD, ISO)...")

    prev_snapshot = _load_snapshot()
    is_first_run = not prev_snapshot
    current_snapshot: dict = {}
    new_updates: list[dict] = []

    for item in REGULATORY_SOURCES:
        source = item["source"]
        emit(f"  Checking {source}...")

        try:
            results = _tavily_search(item["query"], max_results=5)
        except Exception as exc:
            emit(f"  ⚠ {source} search failed: {exc}")
            continue

        current_pages: dict = {}
        for r in results:
            url = r.get("url", "")
            title = r.get("title", "")
            snippet = r.get("content", "")[:300]
            if not url:
                continue
            key = _page_hash(url, title)
            current_pages[key] = {"url": url, "title": title, "snippet": snippet}

        current_snapshot[source] = {
            "pages": current_pages,
            "scanned_at": datetime.datetime.now().isoformat(),
        }

        if not is_first_run:
            prev_keys = set(prev_snapshot.get(source, {}).get("pages", {}).keys())
            for key, page in current_pages.items():
                if key not in prev_keys:
                    emit(f"  🔴 NEW [{source}]: {page['title'][:70]}")
                    new_updates.append({
                        "source": source,
                        "title": page["title"],
                        "url": page["url"],
                        "snippet": page["snippet"],
                        "suggested_topic": f"{source}: {page['title'][:60]}",
                    })

    _save_snapshot(current_snapshot)

    if is_first_run:
        emit(f"First run — baseline saved for {len(REGULATORY_SOURCES)} sources. Monitoring starts next run.")
    else:
        emit(f"Regulatory scan complete. {len(new_updates)} new publication(s) found.")

    return new_updates


if __name__ == "__main__":
    updates = scan_regulatory_updates(
        progress_callback=lambda phase, msg: print(f"[{phase}] {msg}", flush=True)
    )
    print(json.dumps(updates, indent=2, ensure_ascii=False))
