"""
Partner Contact Scraper — 100% free, no paid APIs.

For a given partner website, fetches homepage + /contact + /about pages via
plain `requests` (no Firecrawl burn), extracts:
  - best available email (prioritized by outreach value)
  - office address
  - country

Techniques:
  - Regex email extraction from raw HTML
  - `mailto:` link extraction (most reliable)
  - Cloudflare data-cfemail decoder (bypasses Cloudflare's email obfuscation)
  - Groq LLM extraction for address / country from scraped page text

Fallbacks:
  - If plain requests is blocked (403), Jina Reader (r.jina.ai) — also free
  - If website returns nothing extractable → all fields blank, scrape_status="no_email_found"

No API keys required. Just needs GROQ_API_KEY (already configured) for address extraction.
"""
import os
import re
import sys
from urllib.parse import urlparse, urljoin

import requests

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

PRIMARY_MODEL = "llama-3.3-70b-versatile"

# Pages to try, in priority order
CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/",  # homepage as last fallback
]

# Standard browser UA — most sites accept this
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# v3.5: Placeholder / sample / template email local-parts that leak from
# email-finder services (Hunter, Snov, RocketReach) showing pattern examples
# on their sales pages. These are NEVER real business emails.
PLACEHOLDER_LOCAL_PARTS = {
    "john.doe", "jane.doe", "jane", "john", "johndoe", "janedoe",
    "first.last", "firstname.lastname", "first", "last",
    "firstname", "lastname", "fname", "lname",
    "example", "test", "demo", "sample", "user", "email", "name",
    "yourname", "yourfirstname", "yourlastname", "your.email",
    "email.address", "your-email", "youremail", "your_email",
    "yourfullname", "fullname", "full.name",
    "jdoe", "jsmith", "j.smith", "jane.smith", "john.smith",
    "person", "someone", "yourboss",
    "hello world", "helloworld",
    # v3.7.1: expanded from live-run leaks
    "your", "you", "recipient", "contactname", "clientname",
    "fake", "abc", "xyz", "somebody",
}

# International phone number regex — allows +country code, spaces, dashes, parentheses.
# Requires at least 7 digits total (excludes short codes/years).
PHONE_REGEX = re.compile(
    r"(?:\+?\d{1,3}[\s\-\.]?)?"       # optional country code
    r"(?:\(\d{1,4}\)[\s\-\.]?)?"       # optional area code in parens
    r"(?:\d[\s\-\.]?){6,14}\d"          # main digits with separators
)

# Email prefixes ranked by outreach value. Lower rank = higher priority.
EMAIL_PRIORITY = [
    ("partnership", 1), ("partner", 1), ("bd", 1), ("business", 1), ("biz", 1),
    ("sales", 2), ("marketing", 2),
    ("hello", 3), ("contact", 3), ("info", 3), ("enquir", 3), ("inquir", 3),
    ("team", 4), ("office", 4), ("admin", 4),
    ("support", 5), ("help", 5), ("service", 5),
]

# Prefixes to always skip — useless for outreach
EMAIL_SKIP = {
    "noreply", "no-reply", "donotreply", "do-not-reply", "notification", "notifications",
    "careers", "career", "jobs", "hr", "recruiting", "recruit",
    "legal", "privacy", "abuse", "dmca", "compliance",
    "billing", "invoice", "accounts", "accounting",
    "webmaster", "postmaster", "hostmaster", "root",
    "unsubscribe", "bounce", "mailer-daemon", "example",
}


def _fetch(url: str, timeout: int = 8) -> str:
    """Plain requests fetch. Returns HTML text or '' on failure."""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return ""


def _fetch_jina(url: str, timeout: int = 12) -> str:
    """Free Jina Reader fallback — handles JS-rendered pages."""
    try:
        jina_key = os.getenv("JINA_API_KEY", "")
        headers = {"Accept": "text/plain"}
        if jina_key:
            headers["Authorization"] = f"Bearer {jina_key}"
        r = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=timeout)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


def _decode_cf_email(hex_str: str) -> str:
    """Decode Cloudflare's data-cfemail obfuscation."""
    try:
        r = int(hex_str[:2], 16)
        return "".join(
            chr(int(hex_str[i:i + 2], 16) ^ r) for i in range(2, len(hex_str), 2)
        )
    except Exception:
        return ""


def _clean_email(raw: str) -> str:
    """
    Aggressively strip junk from a scraped email string.
    Returns cleaned email or '' if it's still malformed after cleanup.
    """
    if not raw or "@" not in raw:
        return ""
    e = raw.strip()

    # Decode common HTML entities
    e = e.replace("&#34;", "").replace("&#39;", "").replace("&quot;", "")
    e = e.replace("&amp;", "&").replace("&lt;", "").replace("&gt;", "")

    # Strip leading junk (like //, mailto:, quotes)
    e = re.sub(r"^(?:mailto:|//|/|['\"<>({])+", "", e)

    # Strip trailing junk (parens, semicolons, colons, quotes, HTML tags, JSON, commas, dots)
    e = re.sub(r"[)}>'\";,:]+$", "", e)
    e = re.sub(r"[.]+$", "", e)  # trailing periods separately (email regex allows dots)

    # Any remaining suspicious chars (not part of a valid email) invalidate the email
    if re.search(r'[<>"\'\s(){}\[\]|\\&#;]', e):
        return ""

    # Final format check: must be exactly one @, valid TLD
    if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", e):
        return ""

    e = e.lower()

    # v3.5: Reject placeholder / sample / template emails
    local = e.split("@", 1)[0]
    if local in PLACEHOLDER_LOCAL_PARTS:
        return ""
    # Numeric variants like jsmith123, jsmith1, john.doe2
    local_no_trailing_num = re.sub(r"\d+$", "", local)
    if local_no_trailing_num in PLACEHOLDER_LOCAL_PARTS:
        return ""

    return e


def _extract_emails(html: str) -> list[str]:
    """
    Pull all emails from raw HTML. Combines:
      1. mailto: link extraction (most reliable)
      2. Cloudflare data-cfemail decoding
      3. Plain regex over full text (catches unlinked emails)

    Every candidate goes through _clean_email() so no junk chars can leak
    into the final list (fixes bug where emails like
    `support@x.com)`, `//customercare@y.com`, or `sales@z.com&#34;}}` were
    written to the sheet).
    """
    if not html:
        return []
    found: list[str] = []

    # mailto: links — use a tight character class that excludes MORE junk
    # (previously `[^"\'\s?]+` allowed `)`, `>`, `,`, etc. — root cause of bad emails)
    for m in re.finditer(r'mailto:([^\s"\'<>?)(,;#&{}]+)', html):
        found.append(m.group(1))

    # Cloudflare data-cfemail="hex_encoded"
    for m in re.finditer(r'data-cfemail="([a-f0-9]+)"', html, flags=re.IGNORECASE):
        decoded = _decode_cf_email(m.group(1))
        if decoded and "@" in decoded:
            found.append(decoded)

    # Fallback: plain regex over the whole HTML
    for m in EMAIL_REGEX.findall(html):
        found.append(m)

    # De-obfuscate " [at] " / " (at) " style
    text = re.sub(r"\s*\[\s*at\s*\]\s*", "@", html, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(\s*at\s*\)\s*", "@", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\[\s*dot\s*\]\s*", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(\s*dot\s*\)\s*", ".", text, flags=re.IGNORECASE)
    for m in EMAIL_REGEX.findall(text):
        found.append(m)

    # ── Post-process EVERY candidate through _clean_email ─────────────────
    cleaned = []
    for raw in found:
        e = _clean_email(raw)
        if e:
            cleaned.append(e)
    found = cleaned

    # Normalize + dedup (case-insensitive)
    seen = set()
    unique = []
    for e in found:
        e_clean = e.strip().lower().rstrip(".").rstrip(",")
        # Sanity: must have @ and a real TLD, no whitespace, no HTML tags
        if "@" not in e_clean or "<" in e_clean or " " in e_clean:
            continue

        local, _, domain = e_clean.partition("@")
        if not local or not domain or "." not in domain:
            continue

        # Reject junk domains — analytics, error tracking, CMS platforms, placeholders
        junk_domain_substrings = [
            "example.com", "example.org", "yourdomain",
            "email.com", "domain.com", "domain.tld", "yourcompany",  # v3.7.1
            "yourdomain.com", "site.com", "email-address",             # v3.7.1
            "sentry.io", "sentry-next", "wixpress.com", "wixstudio.com",
            "wordpress.com", "squarespace.com", "webflow.com", "shopifycdn",
            "cloudfront.net", "cloudflare.com", "amazonaws.com",
            "googleusercontent", "google-analytics", "googletagmanager",
            "gstatic.com", "twimg.com", "fbcdn.net", "cdninstagram",
            "sentry-cdn", "bugsnag", "rollbar", "newrelic",
            "domain.com", "domain.tld", "yoursite", "yourcompany",
        ]
        if any(bad in domain for bad in junk_domain_substrings):
            continue

        # Reject if local-part looks like a filename or asset hash
        if local.endswith(("png", "jpg", "jpeg", "svg", "gif", "webp", "ico")):
            continue

        # Reject auto-generated project IDs — local-part that's a long hex string
        # (Sentry/analytics inject these: "605a7baede844d278b89dc95ae0a9123@...")
        if len(local) >= 24 and re.fullmatch(r"[a-f0-9]+", local):
            continue

        # Reject UUID-style local parts (u-1234-abcd-...)
        if re.match(r"^u[-_][a-f0-9\-]{8,}$", local):
            continue

        if e_clean not in seen:
            seen.add(e_clean)
            unique.append(e_clean)
    return unique


def _score_email(email: str, partner_domain: str = "") -> tuple[int, str]:
    """
    Return (priority_score, email). Lower score = higher priority.
    Emails on the partner's own domain get a bonus (subtract 10).
    """
    local = email.split("@")[0].lower()
    email_domain = email.split("@")[1].lower() if "@" in email else ""

    # Absolute skip
    for bad in EMAIL_SKIP:
        if local == bad or local.startswith(bad + ".") or local.startswith(bad + "-"):
            return (999, email)

    # Score by prefix
    score = 6  # default (unknown prefix, e.g., firstname@domain)
    for prefix, rank in EMAIL_PRIORITY:
        if prefix in local:
            score = rank
            break

    # Bonus if email is on partner's own domain
    if partner_domain and partner_domain in email_domain:
        score -= 10

    return (score, email)


def _pick_best_email(emails: list[str], partner_domain: str = "",
                     allow_last_resort: bool = True) -> str:
    """
    Return the highest-priority usable email, or '' if none pass the filter.

    v3.7: `allow_last_resort=True` (default) — if no email passes the strict
    skip-list, still return the "least bad" one that at least has a valid
    format AND is on the partner's own domain. This picks up cases like
    Native Instruments where the only visible email is `privacy-berlin@` —
    still better than blank for BD purposes.
    """
    if not emails:
        return ""
    scored = [_score_email(e, partner_domain) for e in emails]
    strict = [s for s in scored if s[0] < 999]
    if strict:
        strict.sort(key=lambda x: x[0])
        return strict[0][1]

    if not allow_last_resort:
        return ""

    # Last resort: skip-listed emails, but ONLY if on partner's own domain
    # (avoids leaking `careers@othercompany.com` from search results).
    if not partner_domain:
        return ""
    fallback = []
    for score, email in scored:
        if "@" not in email:
            continue
        email_domain = email.split("@", 1)[1].lower()
        if email_domain == partner_domain or email_domain.endswith("." + partner_domain):
            # Reject only truly useless (bounce / auto): noreply, mailer-daemon, unsubscribe
            local = email.split("@")[0]
            if any(local.startswith(bad) for bad in
                   ("noreply", "no-reply", "donotreply", "do-not-reply",
                    "unsubscribe", "bounce", "mailer-daemon")):
                continue
            fallback.append(email)
    return fallback[0] if fallback else ""


def _normalize_website(website: str) -> str:
    """Ensure the URL has a scheme. Return '' if unparseable."""
    if not website:
        return ""
    w = website.strip()
    if not w.startswith(("http://", "https://")):
        w = "https://" + w
    parsed = urlparse(w)
    if not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _domain_of(website: str) -> str:
    """Extract bare domain from URL. e.g., 'https://www.procore.com/a' → 'procore.com'."""
    try:
        netloc = urlparse(website).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return ""


def _extract_phones(html: str) -> list[str]:
    """
    Extract all valid phone numbers from raw HTML.
    Combines: tel: links (most reliable) + regex over full text.
    Filters obviously wrong matches (years, dates, product codes).
    """
    if not html:
        return []
    found: list[str] = []

    # tel: links — most reliable signal
    for m in re.finditer(r'tel:([\+\d\s\-\(\)\.]+)', html):
        found.append(m.group(1).strip())

    # Prioritize text near "phone", "tel", "call us", "contact"
    # by searching only in windows around those keywords
    lower_html = html.lower()
    for kw in ("phone", "tel:", "call us", "call:", "contact"):
        idx = 0
        while True:
            pos = lower_html.find(kw, idx)
            if pos < 0:
                break
            window = html[max(0, pos - 20):pos + 200]
            for m in PHONE_REGEX.findall(window):
                found.append(m)
            idx = pos + len(kw)

    # Normalize and filter
    seen = set()
    unique = []
    for raw in found:
        p = _normalize_phone(raw)
        if not p or p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return unique


def _normalize_phone(raw: str) -> str:
    """Clean phone number. Return '' if invalid."""
    if not raw:
        return ""

    # v3.7.1: Reject ISO date patterns BEFORE cleaning
    # (2024-02-16, 2025/12/12, etc.)
    if re.match(r"^\s*(19|20)\d{2}[-/\.]\d{1,2}[-/\.]\d{1,2}\s*$", raw):
        return ""

    # Strip anything but digits, +, -, space, parens, dot
    cleaned = re.sub(r"[^\d\+\-\s\(\)\.]", "", raw).strip()

    # v3.7.1: Strip trailing junk chars (), commas, semicolons, quotes
    cleaned = re.sub(r"[\)\.,;'\"]+$", "", cleaned).strip()

    # Count digits
    digits_only = re.sub(r"\D", "", cleaned)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return ""
    # Reject if it looks like a year, date, or product code
    if re.fullmatch(r"20\d{2}", digits_only):  # year
        return ""
    if re.fullmatch(r"19\d{2}", digits_only):  # year
        return ""
    # v3.7.1: Reject if digits look like YYYYMMDD or DDMMYYYY
    if re.fullmatch(r"(19|20)\d{6}", digits_only):
        return ""
    if re.fullmatch(r"\d{2}\d{2}(19|20)\d{2}", digits_only):
        return ""

    # Prefer format with country code
    if digits_only.startswith("00"):
        digits_only = "+" + digits_only[2:]
    elif not cleaned.startswith("+") and len(digits_only) >= 10:
        # Keep as-is; caller may add default country prefix if desired
        pass
    # Reformat: keep original separators for readability, but ensure no double-spaces
    result = re.sub(r"\s+", " ", cleaned).strip()
    return result


def _pick_best_phone(phones: list[str]) -> str:
    """Return the most-preferred phone. Ranking:
    1. International format (+CC) wins hardest
    2. Formatted (contains dash, dot, space, or parens) beats raw digits
    3. Longer number wins tiebreaker
    """
    if not phones:
        return ""
    scored = []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        score = len(digits)
        if p.strip().startswith("+"):
            score += 100
        if re.search(r"[\-\.\s\(\)]", p):
            score += 10
        scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return scored[0][1].strip()


def _extract_address_via_llm(text: str) -> dict:
    """
    Use Groq to extract address + country from scraped page text.
    Returns {"address": "...", "country": "..."} — blank strings if not found.
    """
    if not text or len(text) < 100:
        return {"address": "", "country": ""}

    try:
        from groq import Groq
        import json as _json
    except ImportError:
        return {"address": "", "country": ""}

    prompt = f"""Extract the company's office address, country, and phone number from the text below.

RULES:
- If multiple offices/phones are listed, pick the one labeled HQ / Headquarters / main office. Otherwise the first one.
- If no clear address is present, leave "address" as empty string.
- "country" should be the country name in English (e.g., "United States", "United Kingdom", "India").
- "phone" should be a single primary business phone number with country code if visible (e.g., "+1 800 555 1212", "+91 22 1234 5678").
- Do NOT include fax numbers.
- Do NOT invent anything not clearly stated in the text.

OUTPUT (strict JSON):
{{"address": "...", "country": "...", "phone": "..."}}

TEXT:
{text[:6000]}
"""
    try:
        client = Groq(api_key=get_env("GROQ_API_KEY"))
        resp = client.chat.completions.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        data = _json.loads(resp.choices[0].message.content)
        return {
            "address": (data.get("address") or "").strip(),
            "country": (data.get("country") or "").strip(),
            "phone": (data.get("phone") or "").strip(),
        }
    except Exception:
        return {"address": "", "country": "", "phone": ""}


def _html_to_text(html: str, max_chars: int = 8000) -> str:
    """Strip HTML tags for LLM consumption. Simple approach — no BS4 dep."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_chars]


# ── DuckDuckGo helper (v3.5) — free unlimited search, replaces Tavily ────────

def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Free DuckDuckGo search. Returns [{title, url, body}] on success, [] on failure.
    No API key needed. Uses the `ddgs` Python package.
    """
    try:
        from ddgs import DDGS
        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "body": r.get("body", ""),
            }
            for r in results
        ]
    except Exception:
        return []


# ── Tier 2: Email search (DuckDuckGo, v3.5) ──────────────────────────────────

def _tavily_email_search(company_name: str, domain: str) -> list[str]:
    """
    v3.5: name kept for backward compatibility, but now uses DuckDuckGo (free
    unlimited) instead of Tavily.

    Searches Google-index of articles / press releases mentioning the company,
    extracts emails that pass strict _clean_email() validation (which also
    filters placeholder emails like john.doe@ / first.last@).

    Returns list of emails STRICTLY on the partner's own domain.
    """
    queries = [
        f'"@{domain}" contact email',
        f'"{company_name}" contact email address',
    ]

    found: list[str] = []
    for q in queries:
        for item in _ddg_search(q, max_results=5):
            blob = item.get("body", "") + " " + item.get("title", "")
            for m in EMAIL_REGEX.findall(blob):
                cleaned = _clean_email(m)
                if cleaned:
                    found.append(cleaned)

    # STRICT domain match: email's domain must equal partner's domain
    # (or be a subdomain of it).
    strict = []
    for e in found:
        if "@" not in e:
            continue
        email_domain = e.split("@", 1)[1].lower()
        if email_domain == domain or email_domain.endswith("." + domain):
            strict.append(e)
    return strict


# ── Tier 3: Pattern guess + MailboxValidator verify ──────────────────────────

PATTERN_LOCALS = ["partnerships", "partner", "sales", "hello",
                  "contact", "info", "bd", "business"]


def _mailboxvalidator_verify(email: str) -> bool:
    """
    Returns True if MailboxValidator says the email is real+deliverable.
    Requires MAILBOXVALIDATOR_API_KEY env var. If not set, returns False
    (caller should skip guessed emails).

    Free tier: 100 verifications/day. Get key at mailboxvalidator.com (free signup).
    """
    key = os.getenv("MAILBOXVALIDATOR_API_KEY", "").strip()
    if not key:
        return False
    try:
        r = requests.get(
            "https://api.mailboxvalidator.com/v2/validation/single",
            params={"key": key, "email": email, "format": "json"},
            timeout=12,
        )
        if r.status_code != 200:
            return False
        data = r.json()
        # Fields: status ("True"/"False"), is_syntax, is_domain, is_smtp, is_deliverable
        return (
            str(data.get("status", "")).lower() == "true"
            and str(data.get("is_deliverable", "")).lower() == "true"
        )
    except Exception:
        return False


def _pattern_guess_and_verify(domain: str) -> str:
    """
    Try common email patterns on the partner's domain, verify each with
    MailboxValidator. Returns first one that verifies, or "" if none work
    (or if MAILBOXVALIDATOR_API_KEY is missing).
    """
    if not os.getenv("MAILBOXVALIDATOR_API_KEY", "").strip():
        return ""
    for local in PATTERN_LOCALS:
        candidate = f"{local}@{domain}"
        if _mailboxvalidator_verify(candidate):
            return candidate
    return ""


# ── Tier 4: WHOIS registrant email fallback ──────────────────────────────────

def _whois_email(domain: str) -> str:
    """
    Extract registrant email from WHOIS records. Free, no API key.
    Coverage is low (privacy protection is common), but zero cost.
    """
    try:
        import whois  # python-whois — pip install python-whois
    except ImportError:
        return ""
    try:
        w = whois.whois(domain)
        emails = getattr(w, "emails", None)
        if not emails:
            return ""
        if isinstance(emails, str):
            emails = [emails]
        # Skip privacy-guard emails
        for e in emails:
            e_lower = e.lower()
            if any(bad in e_lower for bad in [
                "whoisguard", "privacy", "domainsbyproxy", "protected",
                "registrar", "abuse@",
            ]):
                continue
            if "@" in e_lower and "." in e_lower.split("@")[1]:
                return e_lower
    except Exception:
        pass
    return ""


# ── Tier 5: Social media email search (NEW in v3.4) ─────────────────────────
#
# For partners whose website has no email but who maintain public Facebook /
# LinkedIn / Twitter / Instagram business pages with contact info in the About
# section, use Tavily to search Google's index of those pages. Direct social
# scraping is anti-bot-blocked; Google indexes public pages and Tavily surfaces
# them reliably.

SOCIAL_DOMAINS = {
    "facebook.com": "facebook",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "instagram.com": "instagram",
}


def _social_email_search(company_name: str, partner_domain: str) -> list[tuple[str, str]]:
    """
    v3.5: swapped from Tavily to DuckDuckGo (free unlimited).

    Searches public social profiles (via DDG → Google index) for emails.
    Returns list of (email, source) tuples. source ∈ {facebook, linkedin, twitter, instagram}.
    Only returns emails that pass _clean_email() strict validation (which also
    rejects placeholder emails like john.doe@ / first.last@).
    """
    if not company_name:
        return []

    queries = [
        f'"{company_name}" facebook email contact',
        f'"{company_name}" linkedin email',
        f'"{company_name}" twitter email',
    ]

    hits: list[tuple[str, str]] = []
    for q in queries:
        for item in _ddg_search(q, max_results=5):
            url = item.get("url", "").lower()
            # Detect which social source this result came from
            source = None
            for social_dom, tag in SOCIAL_DOMAINS.items():
                if social_dom in url:
                    source = tag
                    break
            if not source:
                continue

            # Extract emails from title + body snippet
            blob = item.get("body", "") + " " + item.get("title", "")
            for m in EMAIL_REGEX.findall(blob):
                cleaned = _clean_email(m)
                if cleaned:
                    hits.append((cleaned, source))

    # Dedup while preserving first occurrence
    seen: set[str] = set()
    unique = []
    for email, source in hits:
        if email in seen:
            continue
        seen.add(email)
        unique.append((email, source))
    return unique


# ── Main entrypoint ──────────────────────────────────────────────────────────

def scrape_contact(website: str, company_name: str = "",
                   competitor_domain: str = "") -> dict:
    """
    Cascade contact enrichment. Runs Tier 1 → 2 → 3 → 4 → 5 until email is found.

    Args:
        website: Partner's website URL (with or without scheme).
        company_name: Optional company name for Tier 2 + Tier 5 searches. If blank,
            those tiers use domain only.
        competitor_domain: The competitor's own domain (e.g., "autodesk.com").
            If provided AND the partner's website is hosted on this domain
            (e.g., `www.autodesk.com/integrations/partner/360sync`), then all
            enrichment is skipped — because scraping autodesk.com will only
            return AUTODESK's email, not the partner's real email.

    Returns:
        {
          "email":         str,     # best email found, or ""
          "email_source":  str,     # "scraped" | "tavily" | "pattern_verified" | "whois" | "facebook" | "linkedin" | "twitter" | "instagram" | ""
          "address":       str,
          "country":       str,
          "scrape_status": str,     # "ok" | "blocked" | "no_website" | "no_email_found" | "on_competitor_domain"
          "all_emails":    list[str],
        }
    """
    result = {
        "email": "", "email_source": "", "phone": "", "address": "", "country": "",
        "scrape_status": "", "all_emails": [],
    }

    base = _normalize_website(website)
    if not base:
        result["scrape_status"] = "no_website"
        return result

    partner_domain = _domain_of(base)

    # ── Guard: partner listed on competitor's own domain ─────────────────────
    # (e.g., partner listed at autodesk.com/integrations/partner/xxx)
    # Scraping autodesk.com returns Autodesk's email — WRONG for a partner.
    if competitor_domain:
        cd = competitor_domain.lower().strip()
        cd = re.sub(r"^https?://", "", cd)
        cd = re.sub(r"^www\.", "", cd)
        cd = cd.split("/")[0]
        # Match if partner_domain equals or is a subdomain of competitor domain
        if partner_domain == cd or partner_domain.endswith("." + cd):
            result["scrape_status"] = "on_competitor_domain"
            return result

    # ── Tier 1: Website scrape ────────────────────────────────────────────────
    combined_text = ""
    combined_html = ""
    all_emails: list[str] = []
    all_phones: list[str] = []
    got_any_page = False

    for path in CONTACT_PATHS:
        url = urljoin(base + "/", path.lstrip("/"))
        html = _fetch(url)
        if not html:
            html = _fetch_jina(url)
        if not html:
            continue
        got_any_page = True
        all_emails.extend(_extract_emails(html))
        all_phones.extend(_extract_phones(html))
        combined_html += "\n" + html
        combined_text += "\n\n" + _html_to_text(html)
        best_so_far = _pick_best_email(all_emails, partner_domain)
        if best_so_far and len(combined_text) > 3000:
            break

    # Pick best phone from HTML regex extraction
    tier1_phone = _pick_best_phone(all_phones)
    if tier1_phone:
        result["phone"] = tier1_phone

    # Dedup Tier-1 emails
    seen = set()
    unique_emails = []
    for e in all_emails:
        if e not in seen:
            seen.add(e)
            unique_emails.append(e)
    result["all_emails"] = unique_emails

    tier1_email = _pick_best_email(unique_emails, partner_domain)
    if tier1_email:
        result["email"] = tier1_email
        result["email_source"] = "scraped"

    # Extract address + country + phone (LLM fallback for phone) from scraped text
    if combined_text.strip():
        addr = _extract_address_via_llm(combined_text)
        result["address"] = addr["address"]
        result["country"] = addr["country"]
        # LLM phone as fallback if regex didn't catch a good one
        if not result["phone"] and addr.get("phone"):
            result["phone"] = addr["phone"]

    # ── Tier 2: Tavily email search (only if Tier 1 missed) ──────────────────
    if not result["email"] and partner_domain:
        tavily_hits = _tavily_email_search(company_name, partner_domain)
        best_t2 = _pick_best_email(tavily_hits, partner_domain)
        if best_t2:
            result["email"] = best_t2
            result["email_source"] = "tavily"

    # ── Tier 3: Pattern guess + MailboxValidator verify ─────────────────────
    if not result["email"] and partner_domain:
        verified = _pattern_guess_and_verify(partner_domain)
        if verified:
            result["email"] = verified
            result["email_source"] = "pattern_verified"

    # ── Tier 4: WHOIS fallback ───────────────────────────────────────────────
    if not result["email"] and partner_domain:
        whois_email = _whois_email(partner_domain)
        if whois_email:
            result["email"] = whois_email
            result["email_source"] = "whois"

    # ── Tier 5: Social media email search (Facebook / LinkedIn / X / Instagram)
    # Runs last — for partners with no discoverable email on their website but
    # active social business pages. Uses Tavily to search Google's index.
    if not result["email"] and company_name:
        social_hits = _social_email_search(company_name, partner_domain)
        if social_hits:
            # Prefer emails on partner's own domain; otherwise take the first cleanly
            # extracted email (already _clean_email-validated).
            emails_only = [e for e, _ in social_hits]
            best_social = _pick_best_email(emails_only, partner_domain)
            if best_social:
                result["email"] = best_social
                # Look up which social source produced this email
                for email, source in social_hits:
                    if email == best_social:
                        result["email_source"] = source
                        break

    # Set final status
    if not got_any_page and not result["email"]:
        result["scrape_status"] = "blocked"
    elif result["email"] or result["address"]:
        result["scrape_status"] = "ok"
    else:
        result["scrape_status"] = "no_email_found"

    return result


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Scrape contact info from a partner website")
    parser.add_argument("--website", required=True, help="Partner website URL")
    args = parser.parse_args()

    out = scrape_contact(args.website)
    print(json.dumps(out, indent=2, ensure_ascii=False))
