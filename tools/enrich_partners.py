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

    in_domain = any(w in domain_part for w in keys)
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
}

# v3.7.1: expanded — many company-lookup / registry sites gave false positives
_DIRECTORY_HINTS = (
    "companiesin", "opencorporates", "bizapedia", "manta.com",
    "yellowpages", "yell.com", "hoovers.com", "d-b.net", "dnb.com",
    "companycheck", "companieshouse", "endole.co.uk", "corporationwiki",
    "buzzfile", "ownership.com", "leadar.io", "sagentia.com",
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


def _find_website_via_search(company_name: str, competitor_domain: str = "",
                              context_hint: str = "") -> str:
    """
    v3.6/v3.7.2: Discover a company's own website via DDG search.

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

        candidate_url = f"https://{domain}"

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

    # Column letters for PARTNER_COLUMNS
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
