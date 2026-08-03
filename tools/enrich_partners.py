"""
Agent 3 — Partner Contact Enrichment (standalone).

Reads rows from a competitor's tab in the Partnership Leads sheet, finds
rows where Email is blank (or Phone/Address/Country), and enriches them by
scraping the partner's own website.

Design principle: SEPARATED from Agent 2 (discovery). Runs on a per-tab basis,
independently, so you can re-run enrichment without re-running discovery — no
extra Firecrawl/Tavily burn for stuff you already have.

Rules (data quality):
- Strict email format check (no junk chars like `)` `&#` `//`)
- Email MUST be on the partner's own domain (strict match)
- Business prefixes preferred: partnerships/sales/contact/info/hello/bd
- Reject: noreply, no-reply, careers, jobs, hr, legal, privacy, abuse
- Reject: auto-generated (32+ hex chars = Sentry / Wix junk)
- If partner is hosted on competitor's own domain → email left blank (no enrichment)

Usage:
    python tools/enrich_partners.py --tab Autodesk --competitor-domain autodesk.com
    python tools/enrich_partners.py --all-tabs
    python tools/enrich_partners.py --tab "Spot AI" --competitor-domain spot.ai --overwrite
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import get_sheets_service, PARTNER_COLUMNS
from scrape_partner_contact import scrape_contact, _ddg_search
from discover_partners import COMPETITOR_MAP
from utils import get_env

import re as _re
import requests as _requests

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _fetch_page_metadata(url: str, timeout: int = 8) -> dict:
    """
    v3.8: Fetch first ~10KB of a page, extract <title>, meta description,
    og:description, and first <h1>. Used for website verification.
    """
    try:
        r = _requests.get(
            url,
            headers={"User-Agent": _BROWSER_UA, "Accept": "text/html"},
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        content = ""
        for chunk in r.iter_content(chunk_size=4096, decode_unicode=False):
            if chunk:
                try:
                    content += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    pass
            if len(content) > 12000:
                break
    except Exception:
        return {"title": "", "description": "", "h1": ""}

    title = ""
    m = _re.search(r"<title[^>]*>(.*?)</title>", content, _re.I | _re.S)
    if m:
        title = _re.sub(r"\s+", " ", m.group(1)).strip()[:200]

    desc = ""
    m = _re.search(
        r'<meta\s+[^>]*(?:name|property)\s*=\s*["\'](?:description|og:description)["\'][^>]*'
        r'content\s*=\s*["\']([^"\']+)["\']',
        content, _re.I,
    )
    if m:
        desc = _re.sub(r"\s+", " ", m.group(1)).strip()[:400]

    h1 = ""
    m = _re.search(r"<h1[^>]*>(.*?)</h1>", content, _re.I | _re.S)
    if m:
        h1 = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", m.group(1))).strip()[:200]

    return {"title": title, "description": desc, "h1": h1}


_CORP_SUFFIX = {"inc", "ltd", "llc", "corp", "gmbh", "pvt", "co",
                "corporation", "limited", "group", "the"}


def _key_words(name: str) -> list[str]:
    """Extract distinguishing name words (drop tiny words + corp suffixes)."""
    words = _re.split(r"[\s\.,]+", name.lower())
    return [w for w in words if len(w) >= 4 and w not in _CORP_SUFFIX]


# v4.15.7: subdomains that indicate the URL is NOT a company's main marketing
# site. When these appear, strip them and prefer the root domain instead.
_JUNK_SUBDOMAINS = {
    "shop", "store", "mystore", "market", "buy",
    "download", "downloads", "download-center",
    "app", "apps", "webapp", "mobile", "m",
    "docs", "documentation", "help", "support", "kb", "faq",
    "blog", "news", "press", "media",
    "careers", "jobs", "work",
    "investors", "ir", "investor",
    "developer", "developers", "dev", "developer-portal",
    "partners", "partner", "reseller", "resellers",
    "community", "forum", "forums",
    "cdn", "assets", "static", "images",
}


def _keyword_matches_domain_token(keyword: str, domain_part: str) -> bool:
    """v4.15.7: match keyword at word boundaries in the domain.

    Splits on `.` and `-`, then checks if `keyword` appears as a prefix
    or suffix of any resulting token (not just as a random substring).

    - keyword="milestone", domain="milestonesys.com"     → True  (prefix of "milestonesys")
    - keyword="milestone", domain="mymilestonecard.net"  → False (substring, but neither prefix nor suffix)
    - keyword="promise",   domain="promise.com"          → True  (exact token)
    - keyword="promise",   domain="promiseshop.promise.com" → True (exact "promise" token)
    """
    tokens = [t for t in _re.split(r"[.-]", domain_part.lower()) if t]
    for t in tokens:
        if t == keyword or t.startswith(keyword) or t.endswith(keyword):
            return True
    return False


# Common two-part TLDs where the eTLD+1 is 3 labels (.co.uk, .com.au, etc.)
_TWO_PART_TLDS = {
    "co.uk", "co.in", "co.jp", "co.kr", "co.nz", "co.za", "co.il", "co.id",
    "com.au", "com.br", "com.mx", "com.sg", "com.hk", "com.tr", "com.tw",
    "com.ar", "com.co", "com.pe", "com.ve", "com.my", "com.ph", "com.pk",
    "org.uk", "gov.uk", "ac.uk", "net.au", "ne.jp", "or.jp",
}


def _strip_junk_subdomain(url: str) -> str:
    """v4.15.7 / v4.15.7-b: reduce URL to its most likely root marketing domain.

    Two-phase logic:
      1. If host has 3+ labels AND the first label is a known junk
         subdomain (shop/docs/careers/…), strip it. Handles the
         infrastructure-subdomain case.
      2. Regardless of that, if the host still has 3+ labels AND the
         first label REPEATS or CONTAINS the second label (indicating
         a brand-specific subdomain like promiseshop.promise.com or
         milestone-events.milestone.com), strip the first label too.
      3. Never touch www — that's the canonical redirect target.

    - https://shop.example.com                → https://example.com
    - https://promiseshop.promise.com         → https://promise.com
    - https://milestone-events.milestone.com  → https://milestone.com
    - https://www.example.com                 → unchanged
    - https://example.com                     → unchanged
    - https://mymilestonecard.net             → unchanged (no shared label)
    """
    m = _re.match(r"^(https?://)([^/]+)(.*)$", url)
    if not m:
        return url
    scheme, host, rest = m.groups()
    parts = host.lower().split(".")

    def _rebuild(new_parts):
        return f"{scheme}{'.'.join(new_parts)}{rest}"

    if len(parts) < 3 or parts[0] == "www":
        return url

    # Phase 1: junk-subdomain list
    if parts[0] in _JUNK_SUBDOMAINS:
        return _strip_junk_subdomain(_rebuild(parts[1:]))  # recurse for chains

    # Phase 2: brand-repeats itself in the subdomain
    # (skip if we'd end up with a two-part public suffix — e.g. .co.uk)
    tail_2 = ".".join(parts[-2:])
    if tail_2 in _TWO_PART_TLDS and len(parts) < 4:
        return url  # host is already brand.co.uk — leave alone
    second_label = parts[1]
    first_label = parts[0]
    if len(second_label) >= 4 and (
        first_label == second_label
        or first_label.startswith(second_label)
        or first_label.endswith(second_label)
    ):
        return _strip_junk_subdomain(_rebuild(parts[1:]))

    return url


def _verify_website_belongs_to_company(url: str, company_name: str,
                                        context_hint: str = "") -> bool:
    """
    v3.8: Return True if `url` looks like the official site of `company_name`.

    Cascading checks (strongest first):
      1. STRONG: name-word in domain AND (name-word in title OR h1) → accept
      2. STRONG: name-word in domain (no hint given) → accept
      3. WEAK/AMBIGUOUS: name-word in title only, hint given → LLM check
      4. NO SIGNALS → reject (or LLM check if hint present)
    """
    if not url or not company_name:
        return False

    meta = _fetch_page_metadata(url)
    keys = _key_words(company_name)
    if not keys:
        # No distinguishing words — always LLM-check (or reject)
        return False

    domain_part = _re.sub(r'^https?://(www\.)?', '', url).split('/')[0].lower()
    title = meta["title"].lower()
    h1 = meta["h1"].lower()
    desc = meta["description"].lower()

    # v4.15.7: word-boundary domain match — "milestone" matches
    # "milestonesys.com" (prefix of token) but NOT "mymilestonecard.net"
    # (substring buried inside a single token).
    in_domain = any(_keyword_matches_domain_token(w, domain_part) for w in keys)
    in_title = any(w in title for w in keys)
    in_h1 = any(w in h1 for w in keys)
    in_desc = any(w in desc for w in keys)

    # STRONG: domain matches + page-content signal AND no hint → accept fast
    # (no namesake risk to worry about)
    if in_domain and (in_title or in_h1 or in_desc) and not context_hint:
        return True

    # STRONG: domain matches + no context hint → accept
    if in_domain and not context_hint:
        return True

    # No signals at all → reject
    if not (in_domain or in_title or in_h1):
        return False

    # v3.9: Narrow anti-namesake filter — only reject if page has RICH content
    # AND page mentions CLEARLY UNRELATED industry keywords AND hint has a
    # specific industry signal. Otherwise trust the LLM check that follows.
    if context_hint and (len(meta["description"]) > 60 or len(meta["title"]) > 80):
        page_blob = (meta["title"] + " " + meta["description"] + " " + meta["h1"]).lower()
        hint_lower = context_hint.lower()
        # Well-defined anti-pairs — if hint contains left, and page has right
        # (but not any of left), this is a clear namesake mismatch.
        anti_pairs = [
            (["carbon capture", "climate tech", "co2"], ["rose", "flower", "garden", "bulb", "perennial"]),
            (["ai vision", "computer vision", "safety"], ["restaurant", "food", "cafe", "menu"]),
            (["construction", "building"], ["jewelry", "necklace", "ring", "bracelet"]),
            (["software", "saas", "app"], ["farm", "livestock", "cattle", "poultry"]),
        ]
        for hint_kws, bad_kws in anti_pairs:
            hint_has = any(kw in hint_lower for kw in hint_kws)
            page_has_bad = any(kw in page_blob for kw in bad_kws)
            page_has_good = any(kw in page_blob for kw in hint_kws)
            if hint_has and page_has_bad and not page_has_good:
                return False

        # v4.10: reject if page appears to be about an INDIVIDUAL PERSON
        # (politician, artist, blogger) rather than a company.
        # Root cause: "Lodha" (real estate company) matched "mangalprabhatlodha.com"
        # which is the chairman's personal politician site. Same for other founder-
        # named sites that get mistaken for the company.
        personal_signals = [
            "personal blog", "my website", "about me", "member of parliament",
            "mla of", "mp of", "senator", "author of", "artist", "musician",
            "portfolio site", "instagram influencer", "youtube channel",
            "born in", "born on", "date of birth", "biography of", "biografia",
        ]
        page_lower_full = page_blob
        if any(sig in page_lower_full for sig in personal_signals):
            return False

    # Any other case (including domain-match + hint present) → LLM check.
    # The hint's purpose is to catch namesakes, so always let LLM look.

    # AMBIGUOUS: partial match — use LLM to break the tie
    try:
        from groq import Groq
        client = Groq(api_key=get_env("GROQ_API_KEY"))
        if context_hint:
            # INDUSTRY MISMATCH check — default is ACCEPT unless clear contradiction
            prompt = (
                f'A company named "{company_name}" is described as: {context_hint}\n\n'
                f'Below is a webpage that might belong to this company.\n\n'
                f'Website URL: {url}\n'
                f'Page title: {meta["title"] or "(empty)"}\n'
                f'Meta description: {meta["description"] or "(empty)"}\n'
                f'Main heading (H1): {meta["h1"] or "(empty)"}\n\n'
                f'Question: Does this page CONTRADICT the company description above?\n\n'
                f'Rules:\n'
                f'- Answer YES (i.e., "keep this website") by default. Accept minimal / thin pages.\n'
                f'- Answer NO ONLY if the page content explicitly indicates a DIFFERENT '
                f'industry (e.g., page is clearly about ROSES/GARDENING but hint says AI/tech, '
                f'or page is TINY HOMES but hint says CLIMATE CARBON CAPTURE, or page is '
                f'JEWELRY but hint says CONSTRUCTION).\n'
                f'- If page is empty, minimal, or unclear → YES (accept).\n\n'
                f'Reply with a single word: YES or NO.'
            )
        else:
            # No hint — lenient (name-only)
            prompt = (
                f'Website URL: {url}\n'
                f'Page title: {meta["title"] or "(empty)"}\n'
                f'Meta description: {meta["description"] or "(empty)"}\n'
                f'Main heading (H1): {meta["h1"] or "(empty)"}\n\n'
                f'Is this website plausibly the official site of "{company_name}"? Reply YES or NO.'
            )
        # v3.8: try lightweight model first (higher rate limits), fall back to 70b
        try:
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0.0,
            )
        except Exception:
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0.0,
            )
        answer = (resp.choices[0].message.content or "").strip().upper()
        return answer.startswith("YES")
    except Exception:
        # LLM failed (rate-limited or offline). Use lenient heuristic fallback:
        # if we have strong name signals (domain + at least one page signal),
        # trust that. Namesake mismatches slip through only if LLM is down —
        # acceptable trade-off vs blank data.
        return in_domain and (in_title or in_h1 or in_desc)

# v3.6: Websites we should NEVER accept as a company's "official website"
_NOT_A_WEBSITE_DOMAIN = {
    "facebook.com", "linkedin.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "wikipedia.org", "wikipedia.com",
    "crunchbase.com", "g2.com", "capterra.com", "tracxn.com",
    "bloomberg.com", "forbes.com", "reddit.com", "medium.com",
    "quora.com", "yelp.com", "yellowpages.com",
    "glassdoor.com", "indeed.com", "ziprecruiter.com",
    "pitchbook.com", "owler.com", "clutch.co", "goodfirms.co",
    "github.com", "stackoverflow.com",
    # v3.7.1: lead-gen / data directories that were leaking through
    "zoominfo.com", "rocketreach.co", "hunter.io", "snov.io",
    "apollo.io", "leadiq.com", "signalhire.com", "clearbit.com",
    "kaspr.io", "cognism.com", "seamless.ai",
    # v4.10: app-store / marketplace / reverse-listing URLs
    # These are where a company is LISTED, not their own site.
    "aptoide.com", "aptoide.co", "apps.apple.com", "play.google.com",
    "microsoft.com/store", "chrome.google.com/webstore",
    "marketplace.procore.com", "marketplace.atlassian.com",
    "appsource.microsoft.com", "appexchange.salesforce.com",
    "workspace.google.com/marketplace", "shopify.com/apps",
    "wordpress.org/plugins", "chromewebstore.google.com",
}

# v3.7.1: expanded — many company-lookup / registry sites gave false positives
_DIRECTORY_HINTS = (
    "companiesin", "opencorporates", "bizapedia", "manta.com",
    "yellowpages", "yell.com", "hoovers.com", "d-b.net", "dnb.com",
    "companycheck", "companieshouse", "endole.co.uk", "corporationwiki",
    "buzzfile", "ownership.com", "leadar.io", "sagentia.com",
    # v4.6: industry-directory / trade-portal domains that leaked through
    # (e.g., glassglobal.com was picked as "Carlex Glass" website)
    "glassglobal.com", "glassonline.com", "glassmagazine.com",
    "constructionreview", "constructiondive.com",
    "logisticsmgmt.com", "logisticsviewpoints",
    "industryweek.com", "industrytoday.com",
    "prnewswire", "businesswire", "prweb.com",
    "trade.gov", "trademap.org", "importgenius", "panjiva",
)


def _is_wrong_website(website: str, competitor_domain: str = "") -> bool:
    """
    v3.7: return True if the stored website is clearly NOT the partner's own
    (competitor's domain, directory site, or blank). Used to decide whether
    to trigger auto-discovery.
    """
    if not website:
        return True
    domain = _re.sub(r'^https?://(www\.)?', '', website).split('/')[0].lower().strip()
    if not domain:
        return True
    # On competitor's own domain — auto-discovery needed
    if competitor_domain and (domain == competitor_domain
                               or domain.endswith("." + competitor_domain)):
        return True
    # Known non-website domains (social, directories)
    if any(bad in domain for bad in _NOT_A_WEBSITE_DOMAIN):
        return True
    # Registry / directory hints
    if any(hint in domain for hint in _DIRECTORY_HINTS):
        return True
    return False


# v4.15.6: canonical domains for well-known enterprise brands. DDG search
# for generic single-word names ("Milestone", "Bosch") returns junk like
# mymilestonecard.net or bosch-retail-microsites — this map short-circuits
# that risk. Match is case-insensitive on the normalized company name
# (strips Inc/Ltd/LLC/Co/GmbH suffixes, punctuation). If a partner is on
# this list, the search stage is skipped entirely.
_CANONICAL_DOMAINS = {
    # VMS / video surveillance
    "milestone":                 "https://www.milestonesys.com/",
    "milestone systems":         "https://www.milestonesys.com/",
    "axis":                      "https://www.axis.com/",
    "axis communications":       "https://www.axis.com/",
    "network optix":             "https://www.networkoptix.com/",
    "hanwha":                    "https://www.hanwhavision.com/",
    "hanwha vision":             "https://www.hanwhavision.com/",
    "hikvision":                 "https://www.hikvision.com/",
    "dahua":                     "https://www.dahuasecurity.com/",
    "genetec":                   "https://www.genetec.com/",
    # Hardware / silicon
    "nvidia":                    "https://www.nvidia.com/",
    "intel":                     "https://www.intel.com/",
    "dell":                      "https://www.dell.com/",
    "dell technologies":         "https://www.dell.com/",
    "hp":                        "https://www.hp.com/",
    "hpe":                       "https://www.hpe.com/",
    "hewlett packard enterprise":"https://www.hpe.com/",
    "lenovo":                    "https://www.lenovo.com/",
    "cisco":                     "https://www.cisco.com/",
    "arm":                       "https://www.arm.com/",
    "qualcomm":                  "https://www.qualcomm.com/",
    "amd":                       "https://www.amd.com/",
    "promise":                   "https://www.promise.com/",
    "promise technology":        "https://www.promise.com/",
    # Cloud / infrastructure
    "microsoft":                 "https://www.microsoft.com/",
    "google":                    "https://about.google/",
    "google cloud":              "https://cloud.google.com/",
    "aws":                       "https://aws.amazon.com/",
    "amazon web services":       "https://aws.amazon.com/",
    "oracle":                    "https://www.oracle.com/",
    "ibm":                       "https://www.ibm.com/",
    "vmware":                    "https://www.vmware.com/",
    "ovhcloud":                  "https://www.ovhcloud.com/",
    # Industrial / OT / MES
    "siemens":                   "https://www.siemens.com/",
    "sap":                       "https://www.sap.com/",
    "rockwell":                  "https://www.rockwellautomation.com/",
    "rockwell automation":       "https://www.rockwellautomation.com/",
    "abb":                       "https://global.abb/",
    "honeywell":                 "https://www.honeywell.com/",
    "schneider electric":        "https://www.se.com/",
    "bosch":                     "https://www.bosch.com/",
    "robert bosch":              "https://www.bosch.com/",
    "ge":                        "https://www.ge.com/",
    "general electric":          "https://www.ge.com/",
    "emerson":                   "https://www.emerson.com/",
    # Construction / BIM / SaaS
    "autodesk":                  "https://www.autodesk.com/",
    "trimble":                   "https://www.trimble.com/",
    "procore":                   "https://www.procore.com/",
    "bentley":                   "https://www.bentley.com/",
    "hexagon":                   "https://hexagon.com/",
    "salesforce":                "https://www.salesforce.com/",
    # EHS
    "enablon":                   "https://www.enablon.com/",
    "cority":                    "https://www.cority.com/",
    "intelex":                   "https://www.intelex.com/",
    "velocityehs":               "https://www.ehs.com/",
    # BI / analytics
    "power bi":                  "https://powerbi.microsoft.com/",
    "microsoft power bi":        "https://powerbi.microsoft.com/",
    "tableau":                   "https://www.tableau.com/",
    "looker":                    "https://cloud.google.com/looker",
    "qlik":                      "https://www.qlik.com/",
}


def _canonical_website_for(company_name: str) -> str:
    """v4.15.6: return hardcoded canonical URL for well-known brands, or ''."""
    if not company_name:
        return ""
    import re as _re2
    n = company_name.lower().strip()
    n = _re2.sub(r"[,\.]", "", n)
    n = _re2.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|pvt|private)\b", "", n)
    n = _re2.sub(r"\s+", " ", n).strip()
    return _CANONICAL_DOMAINS.get(n, "")


def _find_website_via_search(company_name: str, competitor_domain: str = "",
                              context_hint: str = "") -> str:
    """
    v3.6/v3.7.2: Discover a company's own website via DDG search.
    v4.15.6: Short-circuit via _CANONICAL_DOMAINS map for well-known brands
    (Milestone, Bosch, NVIDIA, etc.) — DDG search returns junk sites for
    generic single-word brand names.

    Args:
        company_name: The name to search for.
        competitor_domain: Skip URLs on this domain (would re-scrape competitor).
        context_hint: v3.7.2 — 3-6 word disambiguation hint from the partner's
            description column. Helps distinguish namesakes (e.g., "Heirloom"
            can mean climate-tech OR tiny-homes — hint "climate carbon capture"
            steers DDG to the right company).

    Skips social media, directories, review sites, and competitor domain.
    Returns full URL like "https://massdesigngroup.org" or "" if none found.
    """
    if not company_name:
        return ""

    # v4.15.6: canonical map short-circuit — avoids DDG-junk for generic
    # single-word brand names like "Milestone" (was returning
    # mymilestonecard.net), "Bosch" (regional retail microsites),
    # "Promise" (promiseshop.promise.com).
    canonical = _canonical_website_for(company_name)
    if canonical:
        return canonical

    # v3.7.2: extract 3-6 meaningful words from description as disambiguation
    hint = ""
    if context_hint:
        # Strip common filler words to focus on descriptive nouns
        filler = {"a", "an", "the", "of", "and", "or", "in", "on", "at", "for",
                  "with", "to", "from", "is", "are", "was", "were", "by", "it",
                  "as", "their", "which", "that", "this", "based", "focused",
                  "provider", "solutions", "services", "company", "products"}
        words = [w.strip(".,;:") for w in context_hint.split() if w.strip(".,;:")]
        keep = [w for w in words if w.lower() not in filler and len(w) > 2][:6]
        hint = " ".join(keep)

    # v3.8: search without the hint first (usually cleaner ranking);
    # try the hinted query only if no candidates verify.
    all_results = _ddg_search(f'"{company_name}" official website', max_results=8)
    if not all_results and hint:
        all_results = _ddg_search(f'"{company_name}" {hint} official website', max_results=6)

    seen_domains = set()
    for r in all_results:
        url = r.get("url", "")
        if not url.startswith("http"):
            continue
        domain = _re.sub(r'^https?://(www\.)?', '', url).split('/')[0].lower().strip()
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        # Reject known non-website domains
        if any(bad in domain for bad in _NOT_A_WEBSITE_DOMAIN):
            continue
        # Reject registry / directory hints in domain
        if any(dir_hint in domain for dir_hint in _DIRECTORY_HINTS):
            continue
        # Reject competitor's own domain
        if competitor_domain and (domain == competitor_domain
                                   or domain.endswith("." + competitor_domain)):
            continue

        # v4.4: reject staging / dev / test / beta subdomains — these are internal URLs
        if any(domain.startswith(p) for p in (
            "staging.", "stg.", "dev.", "beta.", "test.", "sandbox.",
            "preview.", "qa.", "uat.", "demo."
        )):
            continue

        # v4.4: reject spam / coupon / dropshipping-style domain patterns
        spam_patterns = (
            "-gsale", "-sale-", "-deal", "-deals", "-shop-", "-buy-",
            "-outlet", "-discount", "-cheap", "-clearance",
            "salegoods", "hotdeals", "bigsale", "supersale",
        )
        if any(sp in domain for sp in spam_patterns):
            continue

        # v4.4: reject .gov / .edu unless partner is clearly a govt or educational body
        name_lower = company_name.lower()
        is_gov_or_edu_partner = any(kw in name_lower for kw in (
            "government", "govt", "department of", "ministry of",
            "university", "college", "institute of technology", "school of",
        ))
        if (domain.endswith(".gov") or ".gov." in domain
                or domain.endswith(".edu") or ".edu." in domain
                or domain.endswith(".mil")):
            if not is_gov_or_edu_partner:
                continue

        candidate_url = f"https://{domain}"

        # v4.15.7: if the candidate has a junk subdomain (shop., docs.,
        # careers., ...), try the root domain FIRST. Prefer root over
        # subdomain to avoid promiseshop.promise.com type ranking noise.
        root_candidate = _strip_junk_subdomain(candidate_url)
        if root_candidate != candidate_url:
            if _verify_website_belongs_to_company(root_candidate, company_name, context_hint):
                return root_candidate

        # v3.8: verify the candidate really belongs to this company
        if _verify_website_belongs_to_company(candidate_url, company_name, context_hint):
            return candidate_url
        # else try next candidate

    return ""


def _col_letter(idx: int) -> str:
    """Convert 0-based column index to A1 letter (0=A, 1=B, ..., 25=Z, 26=AA)."""
    result = ""
    n = idx
    while True:
        result = chr(65 + (n % 26)) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def _read_partner_rows(service, sheet_id: str, tab: str) -> list[dict]:
    """
    Read all rows from a competitor's tab as list of dicts keyed by column name.
    Skips header row.
    """
    try:
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1:Z",
        ).execute()
    except Exception as e:
        print(f"  [{tab}] READ FAILED: {e}")
        return []

    rows = resp.get("values", [])
    if len(rows) <= 1:
        return []

    header = rows[0]
    result = []
    for i, row in enumerate(rows[1:], start=2):  # sheet row number (1-based, skipping header)
        entry = {"_row": i}
        for j, col_name in enumerate(header):
            entry[col_name] = row[j] if j < len(row) else ""
        result.append(entry)
    return result


def _write_cell(service, sheet_id: str, tab: str, row: int, col_letter: str, value: str):
    """Write a single cell value."""
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!{col_letter}{row}",
        valueInputOption="RAW",
        body={"values": [[value]]},
    ).execute()


def enrich_tab(tab: str, competitor_domain: str = "",
               overwrite: bool = False, progress=None) -> dict:
    """
    Enrich all rows in a tab where Email is blank (or all rows if overwrite=True).

    Args:
        tab: Sheet tab name (must match Competitors tab Name column exactly).
        competitor_domain: Bare domain of the competitor (e.g., "autodesk.com").
            When a partner's website is on this domain, enrichment is skipped
            (would return competitor's own email — WRONG).
        overwrite: If True, re-enrich rows even if Email already has a value.
        progress: Optional callable(msg).

    Returns:
        {"tab": ..., "processed": N, "email_hits": N, "phone_hits": N, "errors": [...]}
    """
    def emit(msg):
        if progress:
            progress(msg)
        else:
            print(f"  {msg}")

    sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        raise EnvironmentError("PARTNER_SHEET_ID not set in .env")

    service = get_sheets_service()

    # Verify tab exists
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab not in existing_tabs:
        emit(f"[{tab}] tab does not exist — nothing to enrich")
        return {"tab": tab, "processed": 0, "email_hits": 0, "phone_hits": 0, "errors": []}

    rows = _read_partner_rows(service, sheet_id, tab)
    emit(f"[{tab}] {len(rows)} data row(s) found")

    # v4.15.4: build col_letters from the tab's ACTUAL header row, not
    # hardcoded PARTNER_COLUMNS. Legacy tabs (e.g. Observia AI, AvidBeam)
    # were created before v4.11 and have Status at col D + Phone Number
    # at col E + Email at col F — the opposite of the current schema.
    # Writing via PARTNER_COLUMNS positions would land emails in Phone
    # column and phones in Status column on those tabs. `fill_missing`
    # already does this correctly; enrich now matches. Falls back to
    # PARTNER_COLUMNS positions if the header is missing (fresh tab).
    header_resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!1:1",
    ).execute()
    actual_header = header_resp.get("values", [[]])[0]
    if actual_header:
        col_letters = {name: _col_letter(i) for i, name in enumerate(actual_header)}
    else:
        col_letters = {name: _col_letter(i) for i, name in enumerate(PARTNER_COLUMNS)}

    to_process = []
    for row in rows:
        website = (row.get("Website") or "").strip()
        name = (row.get("Company Name") or "").strip()
        current_email = (row.get("Email") or "").strip()
        # v3.6: process rows even if website is blank — we'll try to discover it
        if not website and not name:
            continue
        if current_email and not overwrite:
            continue
        to_process.append(row)

    emit(f"[{tab}] {len(to_process)} row(s) need enrichment")

    email_hits = 0
    phone_hits = 0
    errors = []

    for i, row in enumerate(to_process):
        website = (row.get("Website") or "").strip()
        name = row.get("Company Name", "").strip()
        row_num = row["_row"]

        # v3.6/v3.7/v3.8: If website is blank OR clearly wrong (competitor
        # domain, directory site), discover the partner's real website via DDG
        # AND verify the candidate's page actually matches the company.
        # Description passed as context — used ONLY inside the LLM verification
        # step (not in the DDG search itself, since that hurts ranking).
        if _is_wrong_website(website, competitor_domain) and name:
            reason = "blank" if not website else "wrong-site"
            emit(f"  [{i+1}/{len(to_process)}] r{row_num} {name[:30]} — discovering website ({reason})...")
            desc_hint = (row.get("Description") or "").strip()
            discovered = _find_website_via_search(name, competitor_domain, context_hint=desc_hint)
            if discovered:
                website = discovered
                # Persist to sheet so it's visible + reused next time
                _write_cell(service, sheet_id, tab, row_num, col_letters["Website"], website)
                emit(f"      found website: {website}")
            else:
                emit(f"      no website found — skipping")
                continue

        emit(f"  [{i+1}/{len(to_process)}] r{row_num} {name[:30]} — {website[:50]}")

        try:
            contact = scrape_contact(
                website,
                company_name=name,
                competitor_domain=competitor_domain,
            )
        except Exception as e:
            errors.append(f"r{row_num} {name}: {e}")
            emit(f"      ERROR: {e}")
            continue

        # Only write fields that have real values
        if contact.get("email"):
            _write_cell(service, sheet_id, tab, row_num, col_letters["Email"], contact["email"])
            _write_cell(service, sheet_id, tab, row_num, col_letters["Email Source"], contact.get("email_source", ""))
            email_hits += 1
        if contact.get("phone") and not row.get("Phone Number", "").strip():
            _write_cell(service, sheet_id, tab, row_num, col_letters["Phone Number"], contact["phone"])
            phone_hits += 1
        if contact.get("address") and not row.get("Address", "").strip():
            _write_cell(service, sheet_id, tab, row_num, col_letters["Address"], contact["address"])
        if contact.get("country") and not row.get("Country", "").strip():
            _write_cell(service, sheet_id, tab, row_num, col_letters["Country"], contact["country"])

        emit(f"      status={contact['scrape_status']}"
             + (f" email={contact['email']}" if contact.get("email") else "")
             + (f" phone={contact['phone']}" if contact.get("phone") else ""))

    emit(f"[{tab}] === {email_hits} emails, {phone_hits} phones added ===")
    return {
        "tab": tab,
        "processed": len(to_process),
        "email_hits": email_hits,
        "phone_hits": phone_hits,
        "errors": errors,
    }


def _competitor_domain_for_tab(service, sheet_id: str, tab: str) -> str:
    """
    Look up the competitor's domain from the Competitors tab (Website column).
    Falls back to COMPETITOR_MAP for the 14 hardcoded ones.
    """
    # Try Competitors tab first
    try:
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'Competitors'!A2:B",
        ).execute()
        for row in resp.get("values", []):
            if len(row) >= 2 and row[0].strip().lower() == tab.strip().lower():
                w = row[1].strip().lower()
                import re
                w = re.sub(r"^https?://", "", w)
                w = re.sub(r"^www\.", "", w)
                return w.split("/")[0]
    except Exception:
        pass

    # Fallback: COMPETITOR_MAP
    for slug, comp in COMPETITOR_MAP.items():
        if comp["tab"] == tab:
            return comp["domain"]

    return ""


def main():
    parser = argparse.ArgumentParser(description="Agent 3 — Standalone partner enrichment")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tab", help="Single competitor tab to enrich")
    group.add_argument("--all-tabs", action="store_true",
                       help="Enrich all Track-status competitor tabs")
    parser.add_argument("--competitor-domain",
                       help="Competitor's own domain (auto-detected if not provided)")
    parser.add_argument("--overwrite", action="store_true",
                       help="Re-enrich rows that already have Email filled")
    args = parser.parse_args()

    sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        print("ERROR: PARTNER_SHEET_ID not set", file=sys.stderr)
        sys.exit(1)

    service = get_sheets_service()

    if args.tab:
        domain = args.competitor_domain or _competitor_domain_for_tab(service, sheet_id, args.tab)
        if not domain:
            print(f"WARN: Could not auto-detect competitor domain for '{args.tab}'. "
                  f"Emails on competitor's domain WON'T be filtered.")
        result = enrich_tab(args.tab, competitor_domain=domain, overwrite=args.overwrite)
        print(f"\nResult: {result}")
        return

    # --all-tabs
    from push_to_sheets import read_tracked_competitors
    tracked = read_tracked_competitors()
    print(f"Enriching {len(tracked)} Track-status competitors...\n")

    all_results = []
    for t in tracked:
        tab_name = t["name"]
        domain = _competitor_domain_for_tab(service, sheet_id, tab_name)
        result = enrich_tab(tab_name, competitor_domain=domain, overwrite=args.overwrite)
        all_results.append(result)
        time.sleep(1)

    print("\n=== Summary ===")
    total_emails = sum(r["email_hits"] for r in all_results)
    total_phones = sum(r["phone_hits"] for r in all_results)
    print(f"  Total: {total_emails} emails, {total_phones} phones added across {len(all_results)} tabs")


if __name__ == "__main__":
    main()
