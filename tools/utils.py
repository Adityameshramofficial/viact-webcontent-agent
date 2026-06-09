import os
import requests
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Missing required env var: {key}")
    return value


# ── Scraper: Firecrawl (primary) → Jina Reader (fallback / dev mode) ──────────
#
# DEV_MODE=true  → always use Jina (free, saves Firecrawl credits during dev)
# DEV_MODE=false → Firecrawl first; auto-fallback to Jina on error or limit hit
#
# Firecrawl limit codes: 402 (credits exhausted), 429 (rate limit)
# Jina Reader: https://r.jina.ai/{url}  — free, no key needed

def _scrape_firecrawl(url: str, max_chars: int) -> str:
    key = os.getenv("FIRECRAWL_API_KEY", "")
    if not key:
        return ""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=20,
        )
        if resp.status_code in (402, 429):
            return ""  # limit hit — trigger Jina fallback
        if resp.status_code != 200:
            return ""
        md = resp.json().get("data", {}).get("markdown", "")
        return md[:max_chars] if md else ""
    except Exception:
        return ""


def _scrape_jina(url: str, max_chars: int) -> str:
    jina_key = os.getenv("JINA_API_KEY", "")
    headers = {"Accept": "text/plain"}
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            headers=headers,
            timeout=20,
        )
        if resp.status_code != 200:
            return ""
        return resp.text[:max_chars]
    except Exception:
        return ""


def scrape_url(url: str, max_chars: int = 3000) -> str:
    """
    Scrape a URL and return clean markdown content.

    Strategy:
      - DEV_MODE=true  → Jina only (free, no Firecrawl credits used)
      - DEV_MODE=false → Firecrawl first; Jina fallback on failure or limit

    Set DEV_MODE=true in .env while building/testing agents.
    Set DEV_MODE=false (or remove) for production daily runs.
    """
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"

    if not dev_mode:
        result = _scrape_firecrawl(url, max_chars)
        if result:
            return result

    # Dev mode or Firecrawl failed/limit hit → use Jina
    return _scrape_jina(url, max_chars)
