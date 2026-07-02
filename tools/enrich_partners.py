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
from scrape_partner_contact import scrape_contact
from discover_partners import COMPETITOR_MAP


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
        current_email = (row.get("Email") or "").strip()
        if not website:
            continue
        if current_email and not overwrite:
            continue
        to_process.append(row)

    emit(f"[{tab}] {len(to_process)} row(s) need enrichment")

    email_hits = 0
    phone_hits = 0
    errors = []

    for i, row in enumerate(to_process):
        website = row["Website"]
        name = row.get("Company Name", "")
        row_num = row["_row"]
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
