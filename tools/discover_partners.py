"""
Agent 11 — Partner Discovery

For a given competitor, finds companies listed as partners / integrations / customers
across 3 sources, returns a deduped list ready to push to the Partnership Leads sheet.

Sources:
  A. Firecrawl on /partners, /integrations, /partner-program, /marketplace
  B. Firecrawl on /customers, /case-studies, /clients
  C. Tavily search: "<competitor> partners with" + "<competitor> partnership"

LLM extraction (Groq llama-3.3-70b) pulls structured rows out of scraped markdown
and news snippets. No invention — if a field isn't visible in the source it's left blank.

Tab names in the Partnership Leads sheet match the slug (case-insensitive). See
COMPETITOR_MAP for the canonical list.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env, scrape_url
from scrape_partner_contact import scrape_contact

import requests

PRIMARY_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Slug → {name, domain, tab_name}. Tab name must match the sheet exactly.
COMPETITOR_MAP: dict[str, dict] = {
    "openspace":   {"name": "OpenSpace",   "domain": "openspace.ai",     "tab": "Openspace"},
    "matterport":  {"name": "Matterport",  "domain": "matterport.com",   "tab": "Matterport"},
    "thinxtra":    {"name": "Thinxtra",    "domain": "thinxtra.com",     "tab": "Thinxtra"},
    "clickup":     {"name": "ClickUp",     "domain": "clickup.com",      "tab": "Clickup"},
    "trimble":     {"name": "Trimble",     "domain": "trimble.com",      "tab": "Trimble"},
    "skillsignal": {"name": "SkillSignal", "domain": "skillsignal.com",  "tab": "Skillsignal"},
    "dronedeploy": {"name": "DroneDeploy", "domain": "dronedeploy.com",  "tab": "Drone Deploy"},
    "kwant":       {"name": "Kwant.io",    "domain": "kwant.io",         "tab": "kwant"},
    "hammertech":  {"name": "HammerTech",  "domain": "hammertech.com",   "tab": "Hammertech"},
    "intenseye":   {"name": "Intenseye",   "domain": "intenseye.com",    "tab": "Intenseye"},
    "protex":      {"name": "Protex AI",   "domain": "protexai.com",     "tab": "Protex"},
    "visionify":   {"name": "Visionify",   "domain": "visionify.ai",     "tab": "Visionfy"},
    "cority":      {"name": "Cority",      "domain": "cority.com",       "tab": "Cority"},
    "fogsphere":   {"name": "Fogsphere",   "domain": "fogsphere.com",    "tab": "Fogsphere"},
}

PARTNER_PATH_PATTERNS = ["/partners", "/integrations", "/partner-program", "/marketplace"]
CUSTOMER_PATH_PATTERNS = ["/customers", "/case-studies", "/clients", "/customer-stories"]

# v3: Noise partners — huge platforms/generic brands that appear on review sites
# or as passing mentions. Never legitimate B2B partners for our use case.
NOISE_NAMES = {
    "trustpilot", "g2", "capterra", "getapp", "software advice", "softwareadvice",
    "godaddy", "afternic", "namecheap", "domains", "domain",
    "linkedin", "twitter", "x", "facebook", "meta", "instagram", "youtube",
    "google", "microsoft", "amazon", "aws", "amazon web services",
    "sap", "oracle", "salesforce", "gartner", "forrester",
    "wikipedia", "reddit", "medium", "techcrunch", "forbes",
}

# Source URLs from these domains produce garbage partner extractions
NOISE_SOURCE_DOMAINS = {
    "trustpilot.com", "g2.com", "capterra.com", "getapp.com",
    "softwareadvice.com", "gartner.com", "linkedin.com",
    "wikipedia.org", "reddit.com", "medium.com",
}

# Anchor keywords that identify partner/customer pages in URLs and link text
PARTNER_LINK_KEYWORDS = [
    "partner", "integration", "customer", "client", "alliance",
    "ecosystem", "reseller", "marketplace",
]

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ── Source A1: Sitemap.xml smart parsing (NEW) ────────────────────────────────

def _fetch_sitemap(domain: str) -> str:
    """Fetch <domain>/sitemap.xml. Try common locations."""
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
        url = f"https://{domain}{path}"
        try:
            r = requests.get(url, headers={"User-Agent": BROWSER_UA}, timeout=10)
            if r.status_code == 200 and "<urlset" in r.text or "<sitemapindex" in r.text:
                return r.text
        except Exception:
            continue
    return ""


def _parse_sitemap_urls(sitemap_xml: str) -> list[str]:
    """Extract <loc> URLs from a sitemap. Handles both urlset and sitemapindex."""
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap_xml)
    return [u.strip() for u in urls if u.strip()]


def _rank_partner_urls(urls: list[str], top_k: int = 3) -> list[str]:
    """Filter to URLs likely to be partner/customer pages, ranked by keyword hit."""
    scored = []
    for u in urls:
        u_lower = u.lower()
        score = 0
        for kw in PARTNER_LINK_KEYWORDS:
            if kw in u_lower:
                # /partners is a stronger signal than /blog/partners-post
                if f"/{kw}" in u_lower or f"-{kw}" in u_lower or u_lower.endswith(kw):
                    score += 3
                else:
                    score += 1
        # Penalize blog posts, articles, careers
        if "/blog/" in u_lower or "/news/" in u_lower or "/careers/" in u_lower:
            score -= 5
        if score > 0:
            scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored[:top_k]]


def _discover_via_sitemap(domain: str) -> list[str]:
    """Return ranked candidate URLs from sitemap. Empty if no sitemap."""
    xml = _fetch_sitemap(domain)
    if not xml:
        return []
    urls = _parse_sitemap_urls(xml)
    return _rank_partner_urls(urls, top_k=3)


# ── Source A2: Homepage smart crawl (NEW) ─────────────────────────────────────

LINK_REGEX = re.compile(
    r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _discover_via_homepage(domain: str) -> list[str]:
    """
    Fetch homepage, extract all <a> links, keep those whose URL OR anchor text
    contains a partner-related keyword. Returns absolute URLs.
    """
    try:
        r = requests.get(
            f"https://{domain}/",
            headers={"User-Agent": BROWSER_UA},
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return []
        html = r.text
    except Exception:
        return []

    candidates: list[tuple[int, str]] = []
    for match in LINK_REGEX.finditer(html):
        href = match.group(1).strip()
        anchor = re.sub(r"<[^>]+>", "", match.group(2)).strip().lower()
        combined = (href + " " + anchor).lower()

        score = 0
        for kw in PARTNER_LINK_KEYWORDS:
            if kw in combined:
                score += 2 if kw in href.lower() else 1

        if score < 1:
            continue

        # Resolve to absolute URL
        if href.startswith("http"):
            abs_url = href
        elif href.startswith("/"):
            abs_url = f"https://{domain}{href}"
        else:
            continue  # skip anchors, javascript, mailto

        # Only keep same-domain links
        parsed_domain = re.sub(r"^https?://(www\.)?", "", abs_url).split("/")[0]
        if not parsed_domain.endswith(domain.replace("www.", "")):
            continue

        candidates.append((score, abs_url))

    candidates.sort(key=lambda x: -x[0])
    seen: set[str] = set()
    out = []
    for _, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= 3:
            break
    return out


# ── Source A & B: Firecrawl page scrape ───────────────────────────────────────

def _scrape_urls(urls: list[str]) -> list[dict]:
    """Scrape each URL via existing scrape_url. Return list of {url, markdown}."""
    results = []
    for u in urls:
        md = scrape_url(u, max_chars=8000)
        if md and len(md) > 200:
            results.append({"url": u, "markdown": md})
    return results


def _scrape_paths(domain: str, paths: list[str]) -> list[dict]:
    """Try each path; return list of {url, markdown} for the ones that worked."""
    urls = [f"https://{domain}{p}" for p in paths]
    return _scrape_urls(urls)


# ── Source C: Tavily news + site-search ───────────────────────────────────────

def _tavily_search(query: str, max_results: int = 8, include_domains: list[str] | None = None) -> list[dict]:
    """
    v3.5: name kept for backward compatibility; internally now uses DuckDuckGo
    (free unlimited) instead of Tavily.

    Returns list of {title, url, content} where 'content' maps to DDG's 'body'.
    If include_domains provided, appends a 'site:' operator to the query for
    each domain (only the first is used — DDG only supports one at a time).
    """
    q = query
    if include_domains:
        # DDG doesn't natively support include_domains; use site: operator
        # for the first domain (usually enough for our use case).
        q = f"{query} site:{include_domains[0]}"
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(q, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "content": r.get("body", ""),
            }
            for r in results
        ]
    except Exception as e:
        print(f"  [ddg] {query[:60]}... failed: {e}")
        return []


def _discover_via_google_site_search(competitor_name: str, domain: str) -> list[str]:
    """
    Use Tavily's include_domains as a Google 'site:' filter. Catches partner
    pages at non-standard paths (e.g., Trimble's /en/products/partners-and-alliances).
    """
    results = _tavily_search(
        f"{competitor_name} partners",
        max_results=5,
        include_domains=[domain],
    )
    urls = [r.get("url", "") for r in results if r.get("url")]
    return [u for u in urls if u.startswith("http")][:3]


# ── LLM extraction ────────────────────────────────────────────────────────────

def _groq_call(messages: list[dict], max_tokens: int = 3000) -> str:
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    kwargs = dict(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,   # Low for data extraction to reduce hallucination
        response_format={"type": "json_object"},
    )
    try:
        resp = client.chat.completions.create(model=PRIMARY_MODEL, **kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e).lower()
        if "429" in err or "413" in err or "rate_limit" in err or "too large" in err:
            resp = client.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            return resp.choices[0].message.content
        raise


EXTRACT_PROMPT = """You are extracting a list of company names from scraped web content.

CONTEXT:
The content below was scraped from {competitor_name}'s website or news about them.
Source type: {source_type}
You are looking for companies that {competitor_name} works with as PARTNERS, INTEGRATIONS, or CUSTOMERS.

STRICT ANTI-HALLUCINATION RULES:
- Return ONLY companies that are clearly listed as a partner, integration, or customer of {competitor_name}.
- Do NOT include {competitor_name} itself.
- Do NOT invent companies. If you are not 100% sure a name is a real company mentioned in the source, skip it.
- Generic terms like "construction firms" or "Fortune 500 companies" — skip.
- For each company, extract ONLY what is visible in the source — leave blank if not stated.

CONFIDENCE TAGGING (very important for data quality):
- confidence = "high"   → both the company name AND its logo/website are visible in the source (e.g., a partner-tile with logo+link)
- confidence = "medium" → the company name is clearly mentioned (e.g., in a customer quote or press release) but no website link is visible
- confidence = "low"    → the name is inferred from context or only appears in surrounding prose — skip these in your output entirely

Only output "high" and "medium". Never output "low".

OUTPUT FORMAT (strict JSON):
{{
  "companies": [
    {{
      "name": "...",
      "description": "...",
      "website": "...",
      "country": "...",
      "confidence": "high" | "medium"
    }}
  ]
}}

CONTENT TO EXTRACT FROM:
{content}
"""


def _extract_companies(content: str, competitor_name: str, source_type: str) -> list[dict]:
    """LLM extraction → list of {name, description, website, country, confidence}."""
    if not content or len(content) < 100:
        return []
    prompt = EXTRACT_PROMPT.format(
        competitor_name=competitor_name,
        source_type=source_type,
        content=content[:12000],
    )
    try:
        raw = _groq_call(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
        )
        data = json.loads(raw)
        companies = data.get("companies", [])
        cleaned = []
        for c in companies:
            if not isinstance(c, dict) or not c.get("name", "").strip():
                continue
            conf = (c.get("confidence") or "medium").lower().strip()
            if conf not in ("high", "medium"):
                continue  # drop "low" or unknown
            c["confidence"] = conf
            cleaned.append(c)
        return cleaned
    except Exception as e:
        print(f"  [extract] LLM failed: {e}")
        return []


# ── Dedup ─────────────────────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    """Lowercase, strip Inc/Ltd/LLC/Co/Corporation, collapse whitespace."""
    n = name.lower().strip()
    n = re.sub(r"[,\.]", "", n)
    n = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|pvt|private)\b", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _norm_domain(website: str) -> str:
    """Strip protocol, www, trailing slash; lowercase. '' if not parseable."""
    if not website:
        return ""
    w = website.lower().strip()
    w = re.sub(r"^https?://", "", w)
    w = re.sub(r"^www\.", "", w)
    w = w.split("/")[0].strip()
    return w


def _dedup(rows: list[dict], competitor_name: str) -> list[dict]:
    """Dedup by normalized name. Drop the competitor itself. Drop noise names."""
    comp_norm = _norm_name(competitor_name)
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        n = _norm_name(r.get("name", ""))
        if not n or n == comp_norm or n in seen:
            continue
        # v3: reject noise (big platforms, review sites, generic brands)
        if n in NOISE_NAMES:
            continue
        # v3: reject if source is a review site
        source_url = (r.get("source_url") or "").lower()
        if any(bad_src in source_url for bad_src in NOISE_SOURCE_DOMAINS):
            continue
        seen.add(n)
        out.append(r)
    return out


# ── Main discovery flow ───────────────────────────────────────────────────────

def discover_partners(competitor_slug: str, progress=None,
                      name_override: str = "", domain_override: str = "") -> list[dict]:
    """
    Run 6-source partner discovery for one competitor.

    Priority order (each new URL run through LLM extractor):
      A1. Sitemap.xml smart parsing
      A2. Homepage smart crawl (partner-link keywords)
      A3. Static URL pattern fanout (/partners, /integrations, ...)
      A4. Google site-search via Tavily
      A5. Tavily news search
      A6. Customer/case-study pages

    Args:
        competitor_slug: Key in COMPETITOR_MAP. If not present but
            name_override/domain_override are given, uses those instead
            (for Agent-1-discovered competitors not yet in the map).

    Returns:
        Deduped list of partner dicts.
    """
    def emit(msg):
        if progress:
            progress(msg)
        else:
            print(f"  {msg}")

    if competitor_slug in COMPETITOR_MAP:
        comp = COMPETITOR_MAP[competitor_slug]
        name, domain = comp["name"], comp["domain"]
    elif name_override and domain_override:
        name, domain = name_override, domain_override
    else:
        raise ValueError(
            f"Unknown competitor: {competitor_slug}. Valid: {list(COMPETITOR_MAP.keys())} "
            "(or pass name_override + domain_override for ad-hoc competitors)"
        )

    all_rows: list[dict] = []
    scraped_urls: set[str] = set()  # dedup across sources

    def _process(scraped: list[dict], source_tag: str, source_type: str):
        """Run LLM extraction on scraped pages and append tagged results."""
        for s in scraped:
            if s["url"] in scraped_urls:
                continue
            scraped_urls.add(s["url"])
            companies = _extract_companies(s["markdown"], name, source_type)
            emit(f"    [{s['url'][:70]}] extracted {len(companies)}")
            for c in companies:
                c["discovered_via"] = source_tag
                c["source_url"] = s["url"]
                all_rows.append(c)

    # ── A1: Sitemap.xml smart parsing ─────────────────────────────────────────
    emit(f"[A1] Fetching sitemap.xml for {domain}...")
    sitemap_urls = _discover_via_sitemap(domain)
    emit(f"     {len(sitemap_urls)} candidate URL(s) ranked from sitemap")
    if sitemap_urls:
        _process(_scrape_urls(sitemap_urls), "A1:sitemap", "sitemap-partner-page")

    # ── A2: Homepage smart crawl ──────────────────────────────────────────────
    emit(f"[A2] Homepage crawl for partner links on {domain}...")
    homepage_urls = _discover_via_homepage(domain)
    emit(f"     {len(homepage_urls)} candidate URL(s) from homepage")
    if homepage_urls:
        _process(_scrape_urls(homepage_urls), "A2:homepage", "homepage-crawl")

    # ── A3: Static URL patterns ───────────────────────────────────────────────
    emit(f"[A3] Trying static partner URL patterns on {domain}...")
    _process(_scrape_paths(domain, PARTNER_PATH_PATTERNS), "A3:patterns", "partners page")

    # ── A4: Google site-search via Tavily ─────────────────────────────────────
    emit(f"[A4] Google site-search on {domain}...")
    site_search_urls = _discover_via_google_site_search(name, domain)
    emit(f"     {len(site_search_urls)} candidate URL(s) from site-search")
    if site_search_urls:
        _process(_scrape_urls(site_search_urls), "A4:site-search", "google-site-search")

    # ── A5: Tavily news search ────────────────────────────────────────────────
    emit(f"[A5] Tavily news search for {name} partnerships...")
    queries = [
        f'"{name}" partners with',
        f'"{name}" partnership announcement',
        f'"{name}" integration with',
    ]
    news_blob = ""
    for q in queries:
        results = _tavily_search(q, max_results=6)
        emit(f"     {q[:50]}... → {len(results)} results")
        for r in results:
            news_blob += (
                f"\n\n--- {r.get('title', '')}\n{r.get('content', '')}\n"
                f"Source: {r.get('url', '')}\n"
            )
    if news_blob:
        companies = _extract_companies(news_blob, name, "news / press releases")
        emit(f"     extracted {len(companies)} from news")
        for c in companies:
            c["discovered_via"] = "A5:news"
            c["source_url"] = "tavily-news"
            all_rows.append(c)

    # ── A6: Customer / case-study pages ───────────────────────────────────────
    emit(f"[A6] Trying customer/case-study pages on {domain}...")
    _process(_scrape_paths(domain, CUSTOMER_PATH_PATTERNS), "A6:customers", "customer page")

    # ── Dedup ─────────────────────────────────────────────────────────────────
    deduped = _dedup(all_rows, name)
    emit(f"=== Total: {len(all_rows)} raw → {len(deduped)} after dedup ===")

    # v3.2: Agent 2 is DISCOVERY ONLY. Enrichment (email/phone/address) is now
    # handled by Agent 3 (tools/enrich_partners.py), invoked separately after
    # Agent 2 pushes partner rows to the sheet. This keeps agents modular and
    # makes it possible to re-run enrichment without re-running discovery.
    return deduped


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Discover partners of a competitor")
    parser.add_argument("--competitor", required=True, help=f"Slug. Options: {', '.join(COMPETITOR_MAP.keys())}")
    args = parser.parse_args()

    rows = discover_partners(args.competitor)
    print()
    print(json.dumps(rows, ensure_ascii=False, indent=2))
