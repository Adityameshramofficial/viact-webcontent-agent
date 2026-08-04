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
# v4.15.3: was "meta-llama/llama-4-scout-17b-16e-instruct" — Groq
# deprecated / removed the model. Every rate-limited call was silently
# returning [] (the fallback raised 404, `_extract_companies`
# swallowed it). Switched to llama-3.1-8b-instant: smaller, currently
# available, and cheap-enough to burn through rate-limit backoff windows.
FALLBACK_MODEL = "llama-3.1-8b-instant"

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
    # v4.15.13: video surveillance / camera / VMS giants that treat
    # cold outreach as a SALES enquiry (not partnership). Motorola
    # replied to a partnership email today saying "understanding your
    # requirements … about our Pelco/Avigilon VSA solutions" — i.e.
    # sales-qualified inbound, not partnership. Same risk with every
    # camera/VMS giant below.
    "motorola", "motorola solutions", "pelco", "avigilon", "watchguard",
    "axis", "axis communications",
    "bosch", "bosch security", "bosch security systems", "robert bosch",
    "hikvision", "hikvision digital technology",
    "dahua", "dahua technology",
    "hanwha", "hanwha vision", "hanwha techwin", "samsung security",
    "genetec", "uniview",
    "verkada", "ring", "wyze", "arlo",
    "cisco meraki", "meraki",
    "eagle eye networks", "eagle eye",
    "flir", "flir systems", "teledyne flir",
    "i-pro", "i-pro americas", "panasonic i-pro",
    "rhombus", "rhombus systems", "puretech systems",
    "cognyte", "hivewatch", "amag", "lenel", "lenels2", "onguard",
    "hexagon physical security",
    "idemia", "nec", "panasonic", "samsung", "samsung techwin",
    "arrow electronics", "amdocs", "atos", "verizon business",
    # v4.15.14: viAct direct competitors (AI vision safety) — appear on other
    # competitor sites as partners, but partnering with them makes no sense
    "zeroeyes", "avathon",
    # v4.15.14: too-big-corp outreach targets — contact form only, never respond
    "boeing", "bmw", "pepsi", "coca-cola", "coca cola", "rwe",
    "accenture", "informatica", "lenovo",
    "sgre", "siemens gamesa", "sgre siemens gamesa renewable",
    "utc", "utc climate controls security",
    # v4.15.14: industry associations — not partnership candidates
    "toronto construction association", "associated construction contractors",
    "firestop contractors international", "ottawa construction association",
    "league of champions", "fcia",
    # v4.15.12: generic productivity / CRM / BI / no-code SaaS that
    # competitor sites list under "integrates with" but that are NOT
    # BD-relevant industrial-safety partners for viAct. Leaked into
    # Fluix ("Trello / Google Sheets / Pipedrive / Zapier / Airtable"),
    # Observia AI ("Power BI / Tableau / Looker / Google Data Studio /
    # Qlik") — same pattern in every deletion cycle.
    "trello", "asana", "jira", "monday", "monday.com", "notion",
    "airtable", "smartsheet", "coda", "clickup",
    "zapier", "make", "integromat", "n8n", "pipedream",
    "pipedrive", "hubspot", "zoho", "zoho crm", "freshworks", "freshsales",
    "google sheets", "google docs", "google drive", "google forms",
    "google workspace", "gmail", "google calendar", "google data studio",
    "microsoft 365", "office 365", "onedrive", "sharepoint",
    "microsoft teams", "teams", "outlook", "excel", "word", "powerpoint",
    "power bi", "microsoft power bi", "tableau", "looker", "qlik",
    "slack", "discord", "twist", "chanty",
    "dropbox", "box", "box.com", "wetransfer",
    "mailchimp", "sendgrid", "twilio", "constant contact",
    "docusign", "hellosign", "adobe sign", "pandadoc",
    "stripe", "paypal", "square", "razorpay",
    "shopify", "wix", "squarespace", "wordpress",
    "quickbooks", "xero", "sage", "netsuite",
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

def _extract_partner_logos_from_html(url: str) -> list[tuple[str, str]]:
    """
    v4.14: Extract partner company names from image alt tags near "Our Partners"
    sections. Many partner pages show partners as LOGOS (image alt), not text.

    Example: Softdesigners' /trusted-partners page has JS tabs (Technology
    Partner / Implementation Partner / Channel Partner) each showing partner
    LOGOS. Text extraction misses these; image alt tags capture them.

    Returns list of (company_name_from_alt, section_type) tuples.
    section_type ∈ {Technology Partner, Implementation Partner,
                    Channel Partner, Integration Partner, Partner}.
    Empty list if nothing found or page unreachable.
    """
    import re as _re2
    try:
        r = requests.get(
            url,
            headers={"User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )},
            timeout=10,
            allow_redirects=True,
        )
        if r.status_code != 200 or not r.text:
            return []
        html = r.text
    except Exception:
        return []

    html_lower = html.lower()
    # v4.15: strip HTML tags to same-length whitespace so inline tags (<em>,
    # <span class="...">, <br/>) inside section headings don't break marker
    # regex. Positions are preserved so the img-proximity check below still
    # aligns with the original html string.
    # Example: "<h2>Technology <em>Partnerships</em></h2>" — the raw
    # html_lower has "<em>" between "technology" and "partnerships", so
    # r"technology\s*partner" never matches. After normalization those tag
    # characters become spaces and the regex fires.
    html_norm = _re2.sub(r"<[^>]+>", lambda m: " " * len(m.group(0)), html_lower)
    # v4.15: patterns end with `partner(?:s|ships?)?\b` so we match all
    # variants (partner / partners / partnership / partnerships) but only
    # at word boundaries — prevents the old `our\s+partners` from firing
    # on the prose "Our partnerships aren't marketing badges..." and
    # overriding the real "Technology Partnerships" heading nearby.
    _P = r"partner(?:s|ships?)?\b"
    section_patterns = [
        (rf"\btechnology\s*{_P}",             "Technology Partner"),
        (rf"\bimplementation\s*{_P}",         "Implementation Partner"),
        (rf"\bchannel\s*{_P}",                "Channel Partner"),
        (rf"\bintegration\s*{_P}",            "Integration Partner"),
        (rf"\bresell(?:er|ing)?\s*{_P}",      "Channel Partner"),
        (rf"\bsolution\s*{_P}",               "Integration Partner"),
        (rf"\bour\s+{_P}",                    "Partner"),
        (rf"\btrusted\s+{_P}",                "Partner"),
        (rf"\bstrategic\s*{_P}",              "Channel Partner"),
    ]

    # Junk alt-text patterns (generic, non-company)
    junk_alts = {"logo", "image", "icon", "photo", "picture", "banner",
                 "arrow", "menu", "search", "close", "hamburger", "next",
                 "prev", "star", "check", "tick", "cross", "play"}

    # v4.14: for accurate section labeling, find ALL section markers first,
    # then for each img alt tag map to the CLOSEST PRECEDING section marker.
    section_markers: list[tuple[int, str]] = []  # [(position, type)]
    for pattern, section_type in section_patterns:
        for m in _re2.finditer(pattern, html_norm):  # v4.15: use tag-stripped
            section_markers.append((m.start(), section_type))
    if not section_markers:
        return []
    section_markers.sort()

    # Only consider img tags AFTER the first partner marker (skip page-header logos)
    first_marker = section_markers[0][0]
    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    # v4.15: prefer specific-type markers over generic "Partner" when both
    # precede the same img within range. Fixes Clarion, where the prose
    # "Our partnerships aren't marketing badges..." matches `our\s+partners`
    # right after the real "Technology Partnerships" heading and would
    # otherwise downgrade every logo to generic Channel Partner.
    _SPECIFIC = {"Technology Partner", "Integration Partner",
                 "Implementation Partner", "Channel Partner"}

    # v4.15.2: track all h1/h2/h3 headings so the "partner section" ends at
    # the NEXT major heading, not just after a fixed char distance. Stops
    # case-study / customer-story sections from bleeding into the partner
    # extraction when they happen to sit right below "Our Partners"
    # (WorkVis has ~15 scene-description alts in its Case Studies grid
    # immediately after the partner tiles — those were leaking through the
    # 5000-char proximity gate).
    heading_positions = sorted(
        m.start() for m in _re2.finditer(r"<h[1-3]\b", html_lower)
    )

    # v4.15.2: widened alt max 80 → 250 chars so descriptive/SEO alt tags
    # like "Code Red Safety company logo, a broken red letter C with the
    # words..." are still captured. The company name is then peeled out of
    # the descriptive text below.
    for m in _re2.finditer(r'<img[^>]+alt="([^"]{2,250})"', html, _re2.IGNORECASE):
        img_pos = m.start()
        if img_pos < first_marker:
            continue  # before any partner section — skip

        # Preceding markers within the proximity window
        # (v4.15: bumped 2500 → 5000 — Clarion's Technology Partnerships card
        # grid spreads 4 logos across ~4600 chars from the section heading,
        # and the tighter limit dropped 3 of 4 valid partners.)
        candidates = [(p, s) for p, s in section_markers
                      if p <= img_pos and img_pos - p <= 5000]
        if not candidates:
            continue

        # Prefer specific-type marker; fall back to closest generic
        specific = [(p, s) for p, s in candidates if s in _SPECIFIC]
        if specific:
            chosen_marker_pos, section_type = max(specific, key=lambda x: x[0])
        else:
            chosen_marker_pos, section_type = max(candidates, key=lambda x: x[0])

        # v4.15.2: reject if a new h1/h2/h3 heading opens between the
        # chosen marker and this img (offset +80 chars to skip the closing
        # tag of the heading containing the marker itself). That new
        # heading marks the end of the partner section.
        next_heading = next(
            (h for h in heading_positions
             if h > chosen_marker_pos + 80 and h < img_pos),
            None,
        )
        if next_heading is not None:
            continue

        alt = m.group(1).strip()
        if not alt:
            continue

        # v4.15.2: reject people-photo alts ("Photo of X from Y", "Picture
        # of ...") — these are team headshots inside a partner testimonial,
        # not partner logos.
        if _re2.match(r"^(photo|picture|image|headshot|portrait)\s+of\s+",
                      alt, _re2.IGNORECASE):
            continue

        # v4.15.2: for long descriptive alts, peel out the company name.
        # WorkVis pattern: "Code Red Safety company logo, a broken red
        # letter..." → keep only the text BEFORE " logo" / " company logo".
        if len(alt) > 60 and _re2.search(r"\blogo\b", alt, _re2.IGNORECASE):
            m_name = _re2.match(
                r"^(.+?)\s+(?:company\s+)?logo\b",
                alt, _re2.IGNORECASE,
            )
            if m_name:
                alt = m_name.group(1).strip(" ,.-—:")

        # Strip WordPress image ID suffixes
        alt_clean = _re2.sub(r"-e\d{5,}$", "", alt)
        alt_clean = _re2.sub(
            r"[-_\s]+(logo|png|jpg|svg|removebg[-_a-z0-9]*|preview[-_a-z0-9]*|\d)$",
            "", alt_clean, flags=_re2.IGNORECASE,
        ).strip("-_ ")

        if not alt_clean or alt_clean.lower() in junk_alts:
            continue
        if len(alt_clean) < 2 or len(alt_clean) > 60:
            continue
        if _re2.fullmatch(r"client\s*\d+", alt_clean, _re2.IGNORECASE):
            continue

        key = alt_clean.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append((alt_clean, section_type))

    return results


def _scrape_urls(urls: list[str]) -> list[dict]:
    """Scrape each URL via existing scrape_url. Return list of {url, markdown}.

    v4.14: also extract partner logos (img alt tags) from raw HTML and inject
    them into the markdown as a STRONG PARTNER SIGNALS block. Fixes the case
    where partner sections use image-only layouts (Softdesigners, many
    small-vendor sites) that Firecrawl/Jina flatten and lose.
    """
    results = []
    for u in urls:
        md = scrape_url(u, max_chars=8000)
        if md and len(md) > 200:
            item = {"url": u, "markdown": md}
            # v4.14: image-alt partner extraction
            logo_partners = _extract_partner_logos_from_html(u)
            if logo_partners:
                lines = ["", "--- v4.14 STRONG PARTNER SIGNALS "
                         "(image alt tags in partner sections) ---"]
                for alt, sec in logo_partners:
                    lines.append(f"- {alt} [{sec}]")
                lines.append("--- END STRONG PARTNER SIGNALS ---", )
                item["markdown"] = "\n".join(lines) + "\n\n" + item["markdown"]
            results.append(item)
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

v4.14 STRONG PARTNER SIGNALS BLOCK:
If the CONTENT starts with a section titled
"--- v4.14 STRONG PARTNER SIGNALS (image alt tags in partner sections) ---",
those are HIGH-CONFIDENCE partner names extracted from IMAGE LOGOS on the
page's "Our Partners" section. TREAT AS PARTNERS with maximum confidence.

Each line looks like:  - {{Company Name}} [{{Section Type}}]
Map section type to relationship as follows:
  - "Technology Partner" or "Integration Partner" → relationship = "Integration"
  - "Implementation Partner", "Channel Partner", "Reseller Partner",
    "Strategic Partner", "Partner" → relationship = "Channel Partner"

Include ALL companies listed in the STRONG PARTNER SIGNALS block, even if
they don't appear elsewhere in the content. These are the authoritative
partner list. Set confidence = "high" for all of them.

v4.13 NOTE ON MARKETPLACE / INTEGRATION LISTINGS:
Reversing an earlier v4.10 rule — "OpticVyu is available on Autodesk
Construction Cloud" means Autodesk IS an integration partner of OpticVyu.
DO extract those platforms as Integration partners (marketplaces + app
stores create genuine partnerships).

v4.4 REJECT RULES (very important — most current data-quality issues come from these):
- REJECT PRODUCTS / SOFTWARE / TECHNOLOGIES — these are NOT companies:
  * Examples: "SAP Hana", "SAP Ariba", "Microsoft Office", "Salesforce Marketing Cloud",
    "AWS S3", "Google Cloud Storage", "Windows Server", "Oracle Database"
  * If the name is a product feature, module, or SKU of a parent brand,
    output ONLY the parent brand ONCE (e.g., "SAP Hana" + "SAP Ariba" → output "SAP" once).
- REJECT INVESTORS / VENTURE CAPITAL FIRMS unless the source EXPLICITLY calls them
  a "strategic partner" or a "channel partner" (funding is not partnership).
  * Reject: "HG Ventures", "Sequoia Capital", "Andreessen Horowitz", "GV" (Google Ventures)
- REJECT LAW FIRMS, PR AGENCIES, RECRUITERS — these are vendors, not partners.
- REJECT GOVERNMENT AGENCIES unless the source is a case study / customer story
  (e.g., "Department of Transportation" is a customer if named in a case study,
  but reject if it just appears in a legal footer).
- DEDUP AT PARENT-BRAND LEVEL — if you see "SAP Ariba" AND "SAP Hana" in the same
  source, output just one entry named "SAP".

v4.8 VIACT-RELEVANCE FILTER (CRITICAL — this is the final BD-quality gate):
The output list will be used by viAct.ai's BD team for outreach.
viAct is an AI-powered INDUSTRIAL SAFETY + video analytics platform (CCTV +
computer vision + AI bounding boxes) serving 5 industry verticals:
  Construction, Manufacturing, Mining, Oil & Gas, Logistics.
Target buyers: EHS Directors, HSE Managers, Plant Managers, Safety Officers
at industrial enterprises anywhere in the world (APAC focus).

INCLUDE (set viact_relevant="yes") any company that owns, operates, or serves
physical industrial sites where worker safety, PPE compliance, or equipment
monitoring matters:
  ✓ Construction: general contractors, developers, EPC, sub-contractors, MEP
  ✓ Manufacturing plants of ANY kind — automotive parts (Piston Automotive),
    glass (NSG Group), CPG bottling / packaging (Clorox, Pepsi, Coca-Cola
    plants), chemicals, textiles, electronics, food processing (Canfisco)
  ✓ Mining, quarrying, aggregate, cement, steel, heavy metals
  ✓ Oil & Gas: upstream (offshore, drilling), midstream (pipelines), downstream
    (refineries, petrochem)
  ✓ Logistics: fulfillment warehouses (Amazon, Walmart DCs), 3PL (Verst, Ceva),
    ports & terminals (DP World, APM Terminals, Port of Virginia),
    cold storage (Americold, Lineage Logistics)
  ✓ Engineering / BIM / digital twin / 3D reality-capture serving industry
  ✓ Real estate / infrastructure developers (highways, tunnels, dams, airports)
  ✓ EHS (Environment, Health, Safety) consulting or software
  ✓ Site documentation, drone / photo / video progress-tracking
  ✓ Wearable tech / IoT / edge-camera vendors for industrial workers
  ✓ Loading-dock / material-handling / heavy-equipment vendors (Rite Hite)
  ✓ Facility management at large fixed industrial sites

REJECT (set viact_relevant="no") companies clearly OUTSIDE industrial-safety AI:
  ✗ Retail STORES (physical shops or e-commerce) — Macy's, Dick's, Albertsons,
    Saks, Home Depot, Michaels, Lowe's, CVS retail pharmacies. NOTE: retail
    warehouses/DCs are IN-scope, but store-only chains are OUT.
  ✗ Banks / investment firms / VC / hedge funds (NewRoad Capital)
  ✗ Insurance carriers (Tokio Marine) — unless construction-insurance specific
  ✗ Hospitality / hotels / restaurants / travel (Hotel SAAS, Amadeus)
  ✗ Generic enterprise SaaS with no industrial hook (Salesforce, HubSpot,
    Zendesk, Sage accounting, Eclipse IDE, WordPress plugins like Elementor,
    Piotnet, FluentAffiliate, Vbout, FlowMattic, BitFlows)
  ✗ Consumer product / gadget makers (MTech knives, Whitestone accessories)
  ✗ Telecom carriers (Ericsson-as-carrier — but Ericsson industrial IoT is OK)
  ✗ Labor unions (UAW Union)
  ✗ Healthcare providers / hospitals / clinics (unless facility-safety focused)
  ✗ Media / news / marketing agencies

On borderline / unclear cases (e.g., "MSI" — too ambiguous), set "no"
(better to miss one than pollute the sheet).

CONFIDENCE TAGGING (very important for data quality):
- confidence = "high"   → both the company name AND its logo/website are visible in the source (e.g., a partner-tile with logo+link)
- confidence = "medium" → the company name is clearly mentioned (e.g., in a customer quote or press release) but no website link is visible
- confidence = "low"    → the name is inferred from context or only appears in surrounding prose — skip these in your output entirely

Only output "high" and "medium". Never output "low".

v4.13 PARTNER-ONLY FILTER (CRITICAL — this is a hard requirement):
Extract ONLY companies that have a formal BUSINESS PARTNERSHIP with
{competitor_name}. There are TWO valid partner types:

TYPE A — CHANNEL PARTNER (reseller / distributor / SI):
  ✓ "reseller", "authorized reseller", "VAR"
  ✓ "distributor", "authorized distributor"
  ✓ "channel partner", "sales partner", "referral partner"
  ✓ "systems integrator", "implementation partner", "delivery partner"
  ✓ "certified partner", "gold/silver/platinum partner"
  → set relationship = "Channel Partner"

TYPE B — INTEGRATION PARTNER (technology / marketplace / API):
  ✓ "technology partner", "integration partner", "app partner"
  ✓ "works with X", "integrates with X", "certified for X"
  ✓ "Available on X Marketplace", "X App Store", "X AppExchange"
    (BOTH sides count: if OpticVyu is listed on Autodesk Construction Cloud,
     THEN Autodesk IS a partner. Do NOT reject this as reverse-listing.)
  ✓ Section header "Integrations", "Technology Partners", "Our Ecosystem"
  → set relationship = "Integration"

REJECT (DO NOT extract) any of these:
  ✗ CUSTOMER — case study, customer story, testimonial, logo wall,
    "our customer", "chose us", "trusted by", success story, "used by".
    Customers BUY the product; partners SELL / RESELL / INTEGRATE with it.
  ✗ INVESTOR / VC — funding is not partnership.
  ✗ EMPLOYEES / ADVISORS / BOARD.
  ✗ ECOSYSTEM MENTIONS — "used by Fortune 500", generic mentions.

v4.15.15 BD-OUTREACH GOAL (manager clarification 2026-07-23):
The Partnership Leads sheet feeds viAct's channel-development team, not
sales. Their goal is: FIND COMPETITOR X's RESELLERS/INTEGRATORS/VARs so
viAct can approach them and say "you already sell X, add viAct to your
portfolio". This means the row must be a company whose BUSINESS MODEL
is RESELLING/INTEGRATING/INSTALLING third-party software — NOT a
company that BUILDS its own product.

For BD-outreach ranking:
  ✓✓ HIGHEST VALUE: named channel partner / authorized reseller /
     systems integrator / VAR / value-added distributor (e.g., REVTech,
     SICA, Inforica for AegisVision) — these are small-to-mid regional
     services companies whose whole business is reselling other people's
     software
  ✓  MEDIUM: tech integration partners where the partner's product
     CLEARLY complements (not overlaps with) viAct — e.g., a camera
     hardware certification. Keep in the per-competitor tab but do NOT
     surface in the aggregated outreach list unless explicitly wanted.
  ✗  WORST-CASE: another AI vision / safety / EHS software vendor
     listed as a "technology partner" of the competitor. These are
     viAct's competitors themselves and treat cold outreach as sales
     enquiries (Motorola incident 2026-07-23).

The manager said verbatim: "Hume kharidna thodi hai — partners dhundh
rahe hai" (we're not buying, we're looking for resellers).

v4.15.13 REJECT — VIDEO SURVEILLANCE / CAMERA / VMS GIANTS
(learned from 2026-07-23 Motorola incident: our BD outreach was replied to
as a SALES enquiry, not a partnership one, because Motorola/Pelco/Avigilon
compete with viAct in AI-vision security):
  ✗ Motorola Solutions and its brands (Pelco, Avigilon, WatchGuard)
  ✗ Camera hardware giants: Axis Communications, Bosch Security,
    Hikvision, Dahua, Hanwha Vision (aka Samsung / Hanwha Techwin),
    Uniview, FLIR, i-PRO (Panasonic)
  ✗ VMS platforms with their own AI: Genetec, Milestone (borderline),
    Eagle Eye Networks
  ✗ Cloud video-surveillance competitors: Verkada, Rhombus, Meraki
  ✗ Consumer cameras: Ring, Wyze, Arlo
These are viAct's direct competitors OR too-large-to-partner giants.
Their sales teams treat inbound BD as product-purchase enquiries.

v4.15.5 REJECT — CAPABILITY-CLAIM sections (learned from 2026-07-23 Observia audit):
  ✗ Generic "we connect to your existing stack" grids: sections titled
    "Connection with your entire stack", "Integrations & API access",
    "Compatible with", "Works with your tools", "Effortlessly connect to"
    that list tool logos WITHOUT any formal partnership language.
    Example: Observia listed Enablon/Cority/Power BI/Tableau under
    "Connection with your entire safety & ops stack, out of the box".
    These are ONE-SIDED "our API can talk to X" claims — not partnerships.
    ONLY extract if the SAME logos appear under an explicit "Technology
    Partners", "Our Partners", "Certified Partners" heading, OR the
    prose says "X partnered with", "X is our reseller/distributor",
    "certified by X", "Available on X Marketplace".
  ✗ TECHNICAL PROTOCOL / STANDARDS mentions: "OPC UA integration",
    "MES systems we integrate with", "Plug-and-Play with barcode
    scanners / Smart Torque Wrenches / Light Towers", "Single Sign-On
    via Azure AD / Okta". These describe capabilities, not partners.
    Example: Retrocausal's "MES / OPC UA / Plug-and-Play" section
    showed Siemens (real partner via interview + booth) alongside SAP
    and Rockwell (just MES vendors they can talk to) — only Siemens
    was a real partnership.
  ✗ MEDIA / PR relationships: if the only "partnership" evidence is
    that competitor publishes press releases on X's news site, or X
    covers the competitor in their media property (X is a trade
    publication / news outlet), X is a MEDIA partner not a
    tech/channel partner. Example: OpenEye + Syncomm Management
    Group — Syncomm runs snnonline.com which republishes OpenEye
    press releases; not an integration or reseller relationship.
  ✗ BIG-BRAND CLOUD/HARDWARE PROVIDERS as generic ecosystem:
    Microsoft, Google, AWS, Oracle, IBM listed as "we integrate with"
    are almost NEVER formal partnerships (the big-brand still won't
    know the vendor exists). Only extract if there's a named
    partnership program (e.g., "NVIDIA Inception Program", "Intel
    Partner Alliance", "Google Cloud for Startups", "AWS ISV
    Accelerate Program") — the program NAME must appear verbatim.

If unclear whether it's a partner, REJECT. Better to output ZERO than to
include a Customer by mistake.

For each included company, set:
  - "relationship": "Channel Partner"  OR  "Integration"  (nothing else)

OUTPUT FORMAT (strict JSON):
{{
  "companies": [
    {{
      "name": "...",
      "description": "...",
      "website": "...",
      "country": "...",
      "confidence": "high" | "medium",
      "viact_relevant": "yes" | "no",
      "relationship": "Customer" | "Channel Partner" | "Integration" | "Unknown"
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
        dropped_irrelevant = 0
        for c in companies:
            if not isinstance(c, dict) or not c.get("name", "").strip():
                continue
            conf = (c.get("confidence") or "medium").lower().strip()
            if conf not in ("high", "medium"):
                continue  # drop "low" or unknown
            c["confidence"] = conf

            # v4.7: viAct-relevance filter — drop partners that don't fit
            # construction / EHS / industrial-safety BD profile
            relevance = (c.get("viact_relevant") or "").lower().strip()
            if relevance == "no":
                dropped_irrelevant += 1
                continue
            # If field missing (older prompt / LLM slip), keep the row —
            # relevance filter is best-effort, not a hard requirement.

            # v4.10: Drop low-confidence rows — if BOTH description AND website
            # are missing, the partner name has no context. These pollute the
            # sheet with empty rows (e.g., "Spacematrix", "Lisual", "GMR" with
            # nothing else). Confidence signal was too weak to trust.
            has_desc = bool((c.get("description") or "").strip())
            has_web = bool((c.get("website") or "").strip())
            if not has_desc and not has_web:
                dropped_irrelevant += 1
                continue

            # v4.11: normalize relationship field
            rel = (c.get("relationship") or "").strip()
            if rel not in ("Customer", "Channel Partner", "Integration", "Unknown"):
                rel = "Unknown"
            c["relationship"] = rel

            # v4.13: HARD FILTER — only Partners (Channel + Integration) allowed.
            # User's clarification: Autodesk on OpticVyu IS a partner (integration).
            # Only Customers (who BUY the product) are excluded.
            if rel not in ("Channel Partner", "Integration"):
                dropped_irrelevant += 1
                continue

            cleaned.append(c)
        if dropped_irrelevant:
            print(f"  [extract] dropped {dropped_irrelevant} viAct-irrelevant partners")
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
        _process(_scrape_urls(sitemap_urls), "1-High: Partners page (sitemap)", "sitemap-partner-page")

    # ── A2: Homepage smart crawl ──────────────────────────────────────────────
    emit(f"[A2] Homepage crawl for partner links on {domain}...")
    homepage_urls = _discover_via_homepage(domain)
    emit(f"     {len(homepage_urls)} candidate URL(s) from homepage")
    if homepage_urls:
        _process(_scrape_urls(homepage_urls), "1-High: Homepage link", "homepage-crawl")

    # ── A3: Static URL patterns ───────────────────────────────────────────────
    emit(f"[A3] Trying static partner URL patterns on {domain}...")
    _process(_scrape_paths(domain, PARTNER_PATH_PATTERNS), "1-High: Partners page (URL match)", "partners page")

    # ── A4: Google site-search via Tavily ─────────────────────────────────────
    emit(f"[A4] Google site-search on {domain}...")
    site_search_urls = _discover_via_google_site_search(name, domain)
    emit(f"     {len(site_search_urls)} candidate URL(s) from site-search")
    if site_search_urls:
        _process(_scrape_urls(site_search_urls), "1-High: Website (site search)", "google-site-search")

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
            c["discovered_via"] = "2-Medium: News / Press release"
            c["source_url"] = "tavily-news"
            all_rows.append(c)

    # ── A6: Customer / case-study pages ───────────────────────────────────────
    emit(f"[A6] Trying customer/case-study pages on {domain}...")
    _process(_scrape_paths(domain, CUSTOMER_PATH_PATTERNS), "3-Low: Case study / customer", "customer page")

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
