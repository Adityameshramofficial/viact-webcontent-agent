"""
Agent 3.5 — Fill Missing Fields

For rows in a competitor tab where basic contact info (Email, Website, Phone)
is already there but other columns (Description, Address, Country) are blank,
scrape the partner's website once and use Groq LLM to extract the missing
fields.

Used when a run of Agent 3 partially populated a row but couldn't extract the
richer context in the same pass.

100% FREE:
  - Website scrape:  requests -> Jina Reader fallback
  - Phone regex:     built-in (no LLM needed)
  - LLM extraction:  Groq llama-3.1-8b-instant (JSON mode, one call per row)
  - Sheets write:    Google Sheets API service account

Usage:
    python tools/fill_missing_fields.py --tab Autodesk
    python tools/fill_missing_fields.py --tab "Spot AI"
    python tools/fill_missing_fields.py --all-tabs
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import get_sheets_service, PARTNER_COLUMNS
from scrape_partner_contact import (
    _fetch, _fetch_jina, _extract_phones, _pick_best_phone
)
from utils import get_env

_MODEL_FAST = "llama-3.1-8b-instant"
_MODEL_BACKUP = "llama-3.3-70b-versatile"


# ── ccTLD → country map (only unambiguous / consistent-use TLDs) ─────────────
# Deliberately EXCLUDES: .co (Colombia BUT overwhelmingly used generically),
# .io / .ai / .ly / .ml / .tv / .cc / .me / .tk — tech domains, no country signal
_TLD_TO_COUNTRY = {
    # North America
    "us": "United States", "ca": "Canada", "mx": "Mexico",

    # Latin America
    "br": "Brazil", "ar": "Argentina", "cl": "Chile", "pe": "Peru",
    "ec": "Ecuador", "uy": "Uruguay", "py": "Paraguay", "ve": "Venezuela",

    # Western Europe
    "uk": "United Kingdom", "gb": "United Kingdom",
    "de": "Germany", "fr": "France", "it": "Italy", "es": "Spain",
    "nl": "Netherlands", "be": "Belgium", "pt": "Portugal", "ie": "Ireland",
    "at": "Austria", "ch": "Switzerland", "li": "Liechtenstein",
    "lu": "Luxembourg", "mt": "Malta",

    # Nordics
    "se": "Sweden", "no": "Norway", "dk": "Denmark", "fi": "Finland",
    "is": "Iceland",

    # Central/Eastern Europe
    "pl": "Poland", "cz": "Czech Republic", "sk": "Slovakia", "hu": "Hungary",
    "ro": "Romania", "bg": "Bulgaria", "hr": "Croatia", "si": "Slovenia",
    "rs": "Serbia", "gr": "Greece", "ee": "Estonia", "lv": "Latvia",
    "lt": "Lithuania",

    # East / South-East Asia
    "jp": "Japan", "kr": "South Korea", "cn": "China", "hk": "Hong Kong",
    "tw": "Taiwan", "sg": "Singapore", "my": "Malaysia", "th": "Thailand",
    "id": "Indonesia", "ph": "Philippines", "vn": "Vietnam", "kh": "Cambodia",

    # South Asia
    "in": "India", "pk": "Pakistan", "bd": "Bangladesh", "lk": "Sri Lanka",
    "np": "Nepal",

    # Middle East / North Africa
    "ae": "United Arab Emirates", "sa": "Saudi Arabia", "qa": "Qatar",
    "kw": "Kuwait", "bh": "Bahrain", "om": "Oman", "eg": "Egypt",
    "ma": "Morocco", "tn": "Tunisia", "dz": "Algeria", "il": "Israel",
    "tr": "Turkey", "ir": "Iran", "jo": "Jordan", "lb": "Lebanon",

    # Sub-Saharan Africa
    "za": "South Africa", "ng": "Nigeria", "ke": "Kenya", "ug": "Uganda",
    "tz": "Tanzania", "gh": "Ghana", "et": "Ethiopia", "rw": "Rwanda",

    # Oceania
    "au": "Australia", "nz": "New Zealand",

    # Eastern Europe / former USSR
    "ru": "Russia", "ua": "Ukraine", "by": "Belarus", "kz": "Kazakhstan",
    "uz": "Uzbekistan", "ge": "Georgia", "am": "Armenia", "az": "Azerbaijan",
}

# Compound TLDs — checked BEFORE single-TLD lookup because these override
_COMPOUND_TLDS = {
    "co.uk": "United Kingdom", "org.uk": "United Kingdom", "ac.uk": "United Kingdom",
    "co.in": "India", "com.in": "India", "net.in": "India",
    "com.au": "Australia", "org.au": "Australia", "net.au": "Australia",
    "co.jp": "Japan", "or.jp": "Japan", "ne.jp": "Japan",
    "co.kr": "South Korea", "or.kr": "South Korea", "ne.kr": "South Korea",
    "com.br": "Brazil", "org.br": "Brazil",
    "com.mx": "Mexico", "org.mx": "Mexico",
    "com.sg": "Singapore", "org.sg": "Singapore",
    "com.hk": "Hong Kong", "org.hk": "Hong Kong",
    "com.tw": "Taiwan", "org.tw": "Taiwan",
    "co.nz": "New Zealand", "org.nz": "New Zealand",
    "co.za": "South Africa", "org.za": "South Africa",
    "com.tr": "Turkey", "org.tr": "Turkey",
    "co.il": "Israel", "org.il": "Israel",
    "co.ke": "Kenya",
    "com.ar": "Argentina",
    "com.co": "Colombia",
    "com.pe": "Peru",
    "com.ph": "Philippines",
    "com.my": "Malaysia",
    "co.th": "Thailand",
    "com.vn": "Vietnam",
    "com.pk": "Pakistan",
    "com.bd": "Bangladesh",
    "com.eg": "Egypt",
    "com.sa": "Saudi Arabia",
    "com.qa": "Qatar",
    "com.kw": "Kuwait",
}


def _country_from_tld(website: str) -> str:
    """
    Infer country from a website URL's TLD. Returns '' for gTLDs
    (.com, .net, .org, .io, .ai, etc.) and ambiguous ccTLDs.

    Examples:
        https://archilizer.com    -> ''             (gTLD)
        https://example.co.uk     -> 'United Kingdom'
        https://tata.co.in        -> 'India'
        https://acme.de           -> 'Germany'
    """
    if not website:
        return ""
    # Strip protocol + www
    dom = re.sub(r"^https?://(www\.)?", "", website.lower()).split("/")[0].strip()
    if not dom or "." not in dom:
        return ""
    # Check compound TLDs first (e.g., 'co.uk' before 'uk')
    for compound, country in _COMPOUND_TLDS.items():
        if dom.endswith("." + compound):
            return country
    # Single ccTLD
    parts = dom.rsplit(".", 1)
    if len(parts) == 2:
        tld = parts[1]
        return _TLD_TO_COUNTRY.get(tld, "")
    return ""


def _col_letter(idx: int) -> str:
    """Zero-based index -> A1 letter."""
    result = ""
    n = idx
    while True:
        result = chr(65 + (n % 26)) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def _html_to_text(html: str, max_chars: int = 6000) -> str:
    """Strip tags, collapse whitespace, cap length."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:max_chars]


def _summarize_llm(name: str, website: str, text: str) -> dict:
    """
    Ask Groq to extract description, address, country from scraped text.
    Uses fast 8B model first; falls back to 70B if the fast one is rate-limited.
    Anti-hallucination: instruct model to leave fields empty if not visible.
    """
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    prompt = (
        f'Extract these facts about the company "{name}" (website: {website}) '
        f'from the text below.\n\n'
        f'Reply STRICTLY as JSON with these keys:\n'
        f'  description: one short line (max 15 words) describing what the company does\n'
        f'  address: office/HQ address if visible, else empty\n'
        f'  country: country name in English if identifiable, else empty\n\n'
        f'If a field is not clearly visible in the text, use empty string. '
        f'Do NOT invent.\n\n'
        f'TEXT:\n{text[:6000]}'
    )
    payload = dict(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    try:
        resp = client.chat.completions.create(model=_MODEL_FAST, **payload)
    except Exception as e:
        # Rate limited or model unavailable — try the bigger backup
        err = str(e).lower()
        if "429" in err or "rate" in err or "too many" in err:
            try:
                resp = client.chat.completions.create(model=_MODEL_BACKUP, **payload)
            except Exception:
                return {"description": "", "address": "", "country": ""}
        else:
            return {"description": "", "address": "", "country": ""}

    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        return {"description": "", "address": "", "country": ""}

    return {
        "description": (data.get("description") or "").strip()[:200],
        "address": (data.get("address") or "").strip()[:200],
        "country": (data.get("country") or "").strip()[:60],
    }


def _fetch_html(website: str) -> str:
    """
    Try the website URL, then /contact, /contact-us, /about paths.
    Falls back to Jina Reader if plain requests returns blocked/empty.
    Returns HTML or empty string.
    """
    for path in ("", "/contact", "/contact-us", "/about"):
        url = website.rstrip("/") + path if path else website
        html = _fetch(url) or _fetch_jina(url)
        if html and len(html) > 500:
            return html
    return ""


def fill_tab(tab: str, dry_run: bool = False, progress=None) -> dict:
    """
    For every row in `tab` that has at least a Website but is missing
    Description, Address, Country, or Phone, scrape the site once and
    fill those cells via LLM extraction + phone regex.

    Skips rows that are already fully filled.

    Returns {"processed": N, "descriptions": N, "phones": N,
             "addresses": N, "countries": N, "skipped": N}.
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

    # Read header + rows
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1:Z"
    ).execute()
    all_rows = resp.get("values", [])
    if len(all_rows) < 2:
        emit(f"[{tab}] no data rows")
        return {"processed": 0, "descriptions": 0, "phones": 0,
                "addresses": 0, "countries": 0, "skipped": 0}

    header = all_rows[0]
    col_letters = {name: _col_letter(i) for i, name in enumerate(header)}
    # Only proceed if header has the columns we need
    for req in ("Description", "Phone Number", "Address", "Country"):
        if req not in header:
            emit(f"[{tab}] header missing '{req}' — abort")
            return {"processed": 0, "descriptions": 0, "phones": 0,
                    "addresses": 0, "countries": 0, "skipped": 0}

    processed = 0
    fills = {"descriptions": 0, "phones": 0, "addresses": 0, "countries": 0}
    skipped = 0

    for i, row in enumerate(all_rows[1:], start=2):
        pad = row + [""] * (len(header) - len(row))
        name = pad[header.index("Company Name")].strip()
        if not name:
            continue
        website = pad[header.index("Website")].strip()
        if not website:
            continue

        desc = pad[header.index("Description")].strip()
        phone = pad[header.index("Phone Number")].strip()
        addr = pad[header.index("Address")].strip()
        country = pad[header.index("Country")].strip()

        missing = []
        if not desc: missing.append("description")
        if not phone: missing.append("phone")
        if not addr: missing.append("address")
        if not country: missing.append("country")
        if not missing:
            continue

        emit(f"r{i} {name[:30]:30}  missing={missing}")

        html = _fetch_html(website)
        if not html:
            emit(f"    skip (no HTML)")
            skipped += 1
            continue

        # Phone (no LLM needed — regex from HTML)
        if "phone" in missing:
            phones = _extract_phones(html)
            best = _pick_best_phone(phones) if phones else ""
            if best:
                if not dry_run:
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'{tab}'!{col_letters['Phone Number']}{i}",
                        valueInputOption="RAW",
                        body={"values": [[best]]},
                    ).execute()
                fills["phones"] += 1
                emit(f"    phone: {best}")

        # LLM for description / address / country
        if any(m in missing for m in ("description", "address", "country")):
            text = _html_to_text(html)
            result = _summarize_llm(name, website, text)

            if "description" in missing and result.get("description"):
                if not dry_run:
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'{tab}'!{col_letters['Description']}{i}",
                        valueInputOption="RAW",
                        body={"values": [[result["description"]]]},
                    ).execute()
                fills["descriptions"] += 1
                emit(f"    desc: {result['description'][:60]}")

            if "address" in missing and result.get("address"):
                if not dry_run:
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'{tab}'!{col_letters['Address']}{i}",
                        valueInputOption="RAW",
                        body={"values": [[result["address"]]]},
                    ).execute()
                fills["addresses"] += 1
                emit(f"    addr: {result['address'][:60]}")

            if "country" in missing and result.get("country"):
                if not dry_run:
                    service.spreadsheets().values().update(
                        spreadsheetId=sheet_id,
                        range=f"'{tab}'!{col_letters['Country']}{i}",
                        valueInputOption="RAW",
                        body={"values": [[result["country"]]]},
                    ).execute()
                fills["countries"] += 1
                emit(f"    country: {result['country']}")

        # v4.0 improvement: TLD-based country fallback.
        # If country is STILL blank after all LLM attempts, guess from the
        # website's TLD (deterministic mapping, no API call).
        if "country" in missing:
            llm_got_country = False
            try:
                llm_got_country = bool(result.get("country"))
            except NameError:
                pass  # result didn't exist (row didn't hit LLM branch)
            if not llm_got_country:
                tld_country = _country_from_tld(website)
                if tld_country:
                    if not dry_run:
                        service.spreadsheets().values().update(
                            spreadsheetId=sheet_id,
                            range=f"'{tab}'!{col_letters['Country']}{i}",
                            valueInputOption="RAW",
                            body={"values": [[tld_country]]},
                        ).execute()
                    fills["countries"] += 1
                    emit(f"    country (from TLD): {tld_country}")

        processed += 1
        time.sleep(0.5)  # gentle pacing

    result = {"processed": processed, "skipped": skipped, **fills}
    emit(f"=== [{tab}] processed {processed}, skipped {skipped}, "
         f"desc={fills['descriptions']}, phones={fills['phones']}, "
         f"addrs={fills['addresses']}, countries={fills['countries']} ===")
    return result


def main():
    parser = argparse.ArgumentParser(description="Fill missing Description/Address/Country/Phone")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tab", help="One competitor tab to process")
    group.add_argument("--all-tabs", action="store_true",
                       help="Process every Track-status tab from Competitors")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would fill; do not write to sheet")
    args = parser.parse_args()

    if args.tab:
        r = fill_tab(args.tab, dry_run=args.dry_run)
        print(f"\nResult: {r}")
        return

    # --all-tabs
    from push_to_sheets import read_tracked_competitors
    tracked = read_tracked_competitors()
    print(f"Filling missing fields for {len(tracked)} tracked tabs...\n")
    totals = {"descriptions": 0, "phones": 0, "addresses": 0, "countries": 0}
    for t in tracked:
        print(f"=== {t['name']} ===")
        r = fill_tab(t["name"], dry_run=args.dry_run)
        for k in totals:
            totals[k] += r[k]
        time.sleep(1)
    print(f"\n=== TOTALS ===")
    print(f"  Descriptions: {totals['descriptions']}")
    print(f"  Phones:       {totals['phones']}")
    print(f"  Addresses:    {totals['addresses']}")
    print(f"  Countries:    {totals['countries']}")


if __name__ == "__main__":
    main()
