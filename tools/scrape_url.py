"""Fetch and clean text content from a URL."""
import argparse
import hashlib
import json
import os
import sys

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

import requests
from bs4 import BeautifulSoup

from utils import get_env

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; viact-content-agent/1.0)"}
TMP_DIR = os.path.join(os.path.dirname(__file__), "..", ".tmp")


def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title else ""
    body = " ".join(soup.get_text(separator=" ").split())

    result = {"url": url, "title": title, "body": body[:8000]}

    os.makedirs(TMP_DIR, exist_ok=True)
    slug = hashlib.md5(url.encode()).hexdigest()[:8]
    cache_path = os.path.join(TMP_DIR, f"scrape_{slug}.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape text from a URL")
    parser.add_argument("--url", required=True, help="URL to scrape")
    args = parser.parse_args()

    try:
        data = scrape(args.url)
        print(json.dumps(data, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
