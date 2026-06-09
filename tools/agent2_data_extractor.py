"""
Agent 2 — Data Extractor (Firecrawl)

Scrapes competitor URLs using Firecrawl's anti-bot-bypass API and returns
clean Markdown content. Any failure (403, timeout, non-200, empty) returns
the ACCESS_DENIED sentinel so Agent 3 knows not to invent that content.

ANTI-HALLUCINATION CONTRACT:
  If markdown == ACCESS_DENIED, Agent 3 must write
  "[Data unavailable for {competitor}]" — never invent their content.
"""
import argparse
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env, scrape_url

import requests

ACCESS_DENIED = "[ACCESS DENIED]"


def _scrape_one(url: str) -> dict:
    """
    Scrape a single URL via scrape_url() — Firecrawl first, Jina fallback.
    DEV_MODE=true skips Firecrawl and uses Jina directly.
    Returns {"success": True/False, "markdown": "...", "word_count": N}.
    """
    markdown = scrape_url(url, max_chars=6000)
    if not markdown or markdown.strip() == "":
        return {"success": False, "markdown": ACCESS_DENIED, "word_count": 0,
                "error": "No content returned"}
    word_count = len(markdown.split())
    return {"success": True, "markdown": markdown, "word_count": word_count}


def extract_competitor_content(urls: list[str], progress_callback=None) -> dict:
    """
    Scrape a list of URLs sequentially via Firecrawl.

    Args:
        urls: List of competitor page URLs to scrape.
        progress_callback: Optional callable(phase, message).

    Returns:
        Dict keyed by URL:
        {
          "https://example.com/page": {
            "success": True,
            "markdown": "# Heading...",
            "word_count": 1240
          },
          "https://blocked.com/page": {
            "success": False,
            "markdown": "[ACCESS DENIED]",
            "word_count": 0,
            "error": "HTTP 403"
          }
        }
    """
    def emit(message: str):
        if progress_callback:
            progress_callback("agent2", message)

    results: dict = {}

    for i, url in enumerate(urls):
        emit(f"[{i + 1}/{len(urls)}] Firecrawl: {url[:60]}...")
        result = _scrape_one(url)
        results[url] = result

        if result["success"]:
            emit(f"  ✅ {result['word_count']} words")
        else:
            emit(f"  🚫 ACCESS DENIED — {result.get('error', 'unknown')}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent 2 — Data Extractor (Firecrawl)")
    parser.add_argument(
        "--urls", required=True,
        help="Comma-separated URLs to scrape"
    )
    args = parser.parse_args()

    urls = [u.strip() for u in args.urls.split(",") if u.strip()]

    def _cli_cb(phase, message):
        print(f"  [{phase.upper()}] {message}")

    try:
        result = extract_competitor_content(urls, progress_callback=_cli_cb)
        print()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
