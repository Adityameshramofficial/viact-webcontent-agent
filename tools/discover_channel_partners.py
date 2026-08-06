"""
v4.15.16 — Channel Partner Discovery (BD-outreach optimized)

Replaces the generic partner-discovery approach with a targeted search for
REGIONAL SYSTEMS INTEGRATORS / VARs / AUTHORIZED RESELLERS of specific
viAct competitors. This is what the manager actually wants for the
"Channel Partners (Manual)" outreach tab.

Pattern: for each Track-status competitor, run DDG queries like:
  "<competitor_name> authorized reseller"
  "<competitor_name> certified partner"
  "<competitor_name> silver gold partner"
  "<competitor_name> systems integrator"
  "<competitor_name> platinum dealer"

Then extract company names + domains from search results, filter aggressively
against NOISE_NAMES (from discover_partners) and additional TRADE_PUBS /
BLOG_HOSTS / MARKETPLACE_HOSTS blocklists, verify DNS resolves, and return
a deduped list of {name, website, email_guess, resells_competitor}.

Outputs to a target tab (default "Channel Partners (Manual)") with 9-column
schema matching what BD team uses for outreach.

Usage from partner_pipeline.py:
    python partner_pipeline.py --find-channel-partners
"""
import os
import re
import socket
import time
from datetime import date

# Reuse the extensive NOISE_NAMES filter from partner discovery
from discover_partners import NOISE_NAMES


# Trade publications, review sites, blogs, aggregators — DDG returns these
# when searching "X authorized reseller"; none of them are actual channel
# partners, so filter them all out at extraction time.
TRADE_PUB_BLOG_HOSTS = {
    "channeldrive.in", "channeltimes.com", "asmag.com", "varinsights.com",
    "sourcesecurity.com", "securityinformed.com", "securityupdate.in",
    "learncctv.com", "cctvinstaller.ai", "comptia.org",
    "giosg.com", "osirisai.live",
    # marketplaces / job boards / aggregators
    "indiamart.com", "amazon.com", "aws.amazon.com", "ebay.com",
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "youtube.com",
    "instagram.com", "tiktok.com", "reddit.com", "medium.com", "quora.com",
    "wikipedia.org", "github.com", "gitlab.com", "bitbucket.org",
    "g2.com", "capterra.com", "getapp.com", "softwareadvice.com",
    "trustpilot.com", "trustradius.com", "gartner.com", "forrester.com",
    "bloomberg.com", "forbes.com", "techcrunch.com",
    # search engine / directory pages
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com",
    "cloud.google.com", "login.noon.partners",
    # Apple resellers (wrong category — not viAct-relevant)
    "gadgetandgear.com", "ispace.md", "ivenus.in", "imagineonline.store",
}


# Search query patterns to try per competitor. Focus on formal channel-partner
# terminology because those keywords are what real resellers put on their sites.
QUERY_TEMPLATES = [
    "{name} authorized reseller",
    "{name} certified partner",
    "{name} platinum partner reseller",
    "{name} silver gold partner",
    "{name} systems integrator installer",
    "{name} authorised dealer",
]


# Article-title / blog-post signals — reject if these appear in result title.
BLOG_TITLE_TRIGGERS = [
    "top 10", "best of", "list of", "review", "vs.", " vs ",
    "how to", "why ", "5 reasons", "10 reasons",
    "default password", "cheat sheet", "tutorial",
]


def _dns_ok(domain: str, timeout: float = 3.0) -> bool:
    """Cheap DNS check — rejects hallucinated / dead domains."""
    if not domain:
        return False
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(domain)
        return True
    except Exception:
        return False


def _extract_domain(url: str) -> str:
    m = re.match(r"^(?:https?://)?(?:www\.)?([^/]+)", url)
    return m.group(1).lower() if m else ""


def _clean_title(title: str) -> str:
    """Strip common ' | Site Name' / ' - Site Name' suffixes from result title."""
    for sep in (" | ", " - ", " — ", " · "):
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()[:80]


def _norm_name(name: str) -> str:
    """Normalization for NOISE_NAMES matching (matches _norm_name in
    discover_partners.py — keeps behaviour consistent)."""
    n = re.sub(r"[,\.]", " ", name.lower())
    n = re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|pvt|private)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def _tld_country(domain: str) -> str:
    """Guess country from ccTLD. Empty for generic TLDs (.com/.net/.org/etc.)."""
    m = {
        "co.uk": "United Kingdom", "uk": "United Kingdom",
        "co.in": "India", "in": "India",
        "com.au": "Australia", "au": "Australia",
        "co.nz": "New Zealand",
        "ca": "Canada", "us": "USA",
        "de": "Germany", "fr": "France", "it": "Italy", "es": "Spain",
        "nl": "Netherlands", "be": "Belgium", "ch": "Switzerland",
        "se": "Sweden", "no": "Norway", "dk": "Denmark", "fi": "Finland",
        "ie": "Ireland", "at": "Austria", "pl": "Poland", "cz": "Czechia",
        "ru": "Russia", "tr": "Turkey", "gr": "Greece", "pt": "Portugal",
        "jp": "Japan", "sg": "Singapore", "hk": "Hong Kong", "kr": "South Korea",
        "tw": "Taiwan", "th": "Thailand", "vn": "Vietnam", "my": "Malaysia",
        "ph": "Philippines", "id": "Indonesia",
        "ae": "UAE", "sa": "Saudi Arabia", "il": "Israel", "eg": "Egypt",
        "za": "South Africa", "ng": "Nigeria", "ke": "Kenya",
        "br": "Brazil", "mx": "Mexico", "ar": "Argentina", "cl": "Chile",
        "co": "Colombia", "pe": "Peru",
    }
    parts = domain.split(".")
    if len(parts) >= 2:
        tail2 = ".".join(parts[-2:])
        if tail2 in m:
            return m[tail2]
    if parts[-1] in m:
        return m[parts[-1]]
    return ""


def _ddg_search(query: str, max_results: int = 10) -> list[dict]:
    from ddgs import DDGS
    try:
        return list(DDGS().text(query, max_results=max_results))
    except Exception as e:
        print(f"  [ddg] {query[:60]}... failed: {e}")
        return []


def find_channel_partners_for(competitor_name: str,
                              competitor_domain: str = "",
                              max_queries: int = 4,
                              max_results_per_q: int = 8,
                              progress=None) -> list[dict]:
    """Search DDG for regional resellers of `competitor_name`.

    Returns list of dicts:
      {name, website, email_guess, country, resells_competitor}
    Each entry has already passed NOISE_NAMES + TRADE_PUB + DNS + noise-title
    filters, so it's safe to append straight to the Channel Partners tab.
    """
    def log(m):
        if progress: progress(m)
        else: print(f"  {m}")

    found: dict[str, dict] = {}  # domain -> entry
    for tmpl in QUERY_TEMPLATES[:max_queries]:
        q = tmpl.format(name=competitor_name)
        log(f"[q] {q}")
        results = _ddg_search(q, max_results=max_results_per_q)
        for r in results:
            url = r.get("href", "")
            title = r.get("title", "")
            dom = _extract_domain(url)
            if not dom or dom in found:
                continue
            # Filter: blocked / vendor's own / competitor's own
            if any(bad in dom for bad in TRADE_PUB_BLOG_HOSTS):
                continue
            if competitor_domain and (dom == competitor_domain
                                       or dom.endswith("." + competitor_domain)):
                continue
            # Filter: blog / article titles
            title_low = title.lower()
            if any(t in title_low for t in BLOG_TITLE_TRIGGERS):
                continue
            # Filter: NOISE_NAMES (surveillance giants, big brands, generic SaaS)
            clean_name = _clean_title(title)
            if _norm_name(clean_name) in NOISE_NAMES:
                continue
            # v4.15.17: also check name-substring for compound noise
            # ("Motorola Solutions Partner", "Bosch Security Reseller" etc.)
            name_low = clean_name.lower()
            if any(nn in name_low for nn in NOISE_NAMES if len(nn) >= 6):
                continue
            # Filter: URL too deep (article page, not company home)
            if len(url.split("/")) > 6:
                continue
            # Filter: too-short host (e.g., "co" typo)
            if len(dom) < 5:
                continue
            # v4.15.17: additional URL structural rejects
            # /partners/ / /events/ / /news/ / /blog/ = subpage on vendor site
            url_low = url.lower()
            if any(seg in url_low for seg in (
                "/partners/", "/partner/", "/reseller/", "/dealer/",
                "/events/", "/event/", "/news/", "/blog/", "/press/",
                "/case-studies/", "/case-study/", "/customers/",
                "/support/", "/careers/", "/jobs/", "/about/",
                "/investor/", "/investors/",
            )):
                continue
            found[dom] = {
                "name": clean_name,
                "website": f"https://{dom}",
                "email_guess": f"info@{dom}",
                "country": _tld_country(dom),
                "url": url,
                "resells_competitor": competitor_name,
            }

    # DNS-verify each candidate
    verified = []
    for dom, entry in found.items():
        if _dns_ok(dom):
            verified.append(entry)
    log(f"[found] {len(verified)} live candidates for '{competitor_name}'")
    return verified


def append_to_channel_partners_tab(entries: list[dict],
                                    tab: str = "Channel Partners (Manual)",
                                    sheet_id: str = "") -> int:
    """Append new channel-partner rows to the target tab. Deduplicates
    against existing rows by Email + normalized name. Returns count appended."""
    from push_to_sheets import get_sheets_service

    if not sheet_id:
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")

    svc = get_sheets_service()

    # Ensure tab exists with proper 9-col header
    header = ["Company Name", "Description", "Website", "Phone Number", "Email",
              "Address", "Country", "Status", "Resells (Competitor)"]
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab not in existing_tabs:
        svc.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={
            "requests": [{"addSheet": {"properties": {"title": tab}}}]
        }).execute()
        svc.spreadsheets().values().update(spreadsheetId=sheet_id,
            range=f"'{tab}'!A1", valueInputOption="RAW",
            body={"values": [header]}).execute()

    # Read existing for dedup
    resp = svc.spreadsheets().values().get(spreadsheetId=sheet_id,
        range=f"'{tab}'!A2:E").execute()
    existing_rows = resp.get("values", [])
    existing_emails = {r[4].lower().strip() for r in existing_rows if len(r) > 4}
    existing_names = {_norm_name(r[0]) for r in existing_rows if len(r) > 0}

    new_rows = []
    for e in entries:
        email = e["email_guess"].lower().strip()
        norm = _norm_name(e["name"])
        if email in existing_emails or norm in existing_names:
            continue
        existing_emails.add(email)
        existing_names.add(norm)
        new_rows.append([
            e["name"], "", e["website"], "", email,
            "", e.get("country", ""), "", e["resells_competitor"],
        ])

    if new_rows:
        svc.spreadsheets().values().append(spreadsheetId=sheet_id,
            range=f"'{tab}'!A:I", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": new_rows}).execute()

    return len(new_rows)


def run_channel_partner_discovery(competitor_list: list[dict] | None = None,
                                    max_per_competitor: int = 4) -> int:
    """Full pipeline: iterate over Track-status competitors, search for their
    channel partners, append verified entries to the target tab.

    competitor_list: list of {"name", "website"} dicts. If None, reads from
        Competitors tab via read_tracked_competitors().
    Returns total number of new rows appended.
    """
    if competitor_list is None:
        from partner_pipeline import read_tracked_competitors
        competitor_list = read_tracked_competitors()

    total_new = 0
    for c in competitor_list:
        name = c.get("name", "").strip()
        website = c.get("website", "").strip()
        if not name:
            continue
        # Extract bare domain from website
        dom = _extract_domain(website)
        print(f"\n>>> {name} ({dom})")
        entries = find_channel_partners_for(name, competitor_domain=dom,
                                             max_queries=max_per_competitor)
        added = append_to_channel_partners_tab(entries)
        print(f"    Appended {added} new channel partners")
        total_new += added
        time.sleep(2)  # gentle DDG pacing

    print(f"\n\nTOTAL new channel partners added: {total_new}")
    return total_new


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_channel_partner_discovery()
