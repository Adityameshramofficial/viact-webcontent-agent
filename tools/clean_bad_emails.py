"""
Cleanup utility — find and clear MALFORMED emails from all partner tabs.

An email is malformed if any of:
  - contains stray junk chars: ) ( ; : > < / { } # & spaces
  - contains HTML entities (&#34;, &amp;, etc.)
  - contains JSON syntax leaks (}}, ]}, etc.)
  - doesn't match strict email regex after cleanup

Preserves ALL other data (name, description, website, phone, address, country).
Only clears the Email + Email Source columns for the affected rows.

Usage:
    python tools/clean_bad_emails.py --dry-run
    python tools/clean_bad_emails.py               # actually clears
    python tools/clean_bad_emails.py --tab Autodesk
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import get_sheets_service, PARTNER_COLUMNS

STRICT_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

MALFORMED_CHAR_SET = set(list("()<>{}[]|\\;/'\"&#\t\n "))


def _is_malformed(email: str) -> tuple[bool, str]:
    """Return (is_bad, reason)."""
    e = email.strip()
    if not e:
        return (False, "empty")
    # 1. Junk chars anywhere
    for c in e:
        if c in MALFORMED_CHAR_SET:
            return (True, f"junk char {c!r}")
    # 2. HTML entities
    if re.search(r"&\w+;|&#\d+;", e):
        return (True, "html entity")
    # 3. Trailing punctuation
    if e[-1] in ".,":
        return (True, "trailing punct")
    # 4. Strict format check
    if not STRICT_EMAIL_RE.match(e):
        return (True, "format")
    # 5. Junk domains (still slipping in from Sentry/Wix/etc.)
    junk_domains = ["sentry", "wixpress", "cloudflare", "sentry-cdn",
                    "example.com", "yourdomain", "example.org"]
    local, _, dom = e.partition("@")
    if any(j in dom for j in junk_domains):
        return (True, "junk domain")
    # 6. Auto-generated hex local part (Sentry-style)
    if len(local) >= 24 and re.fullmatch(r"[a-f0-9]+", local):
        return (True, "auto-generated hex")
    return (False, "ok")


def _get_col_index(header: list, name: str) -> int:
    """Zero-based index. Returns -1 if not found."""
    return header.index(name) if name in header else -1


def _col_letter(idx: int) -> str:
    result = ""
    n = idx
    while True:
        result = chr(65 + (n % 26)) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def clean_tab(service, sheet_id: str, tab: str, dry_run: bool = False,
              force: bool = False) -> dict:
    """Read tab, find malformed emails, clear Email + Email Source cells.

    Only clears if row was ADDED BY AGENT (Discovered Via column set).
    User-curated rows (blank Discovered Via) are left alone — those may have
    multi-email cells that look 'malformed' but are intentional.

    Set force=True to override this protection.
    """
    try:
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1:Z",
        ).execute()
    except Exception as e:
        return {"tab": tab, "error": str(e), "cleared": 0, "kept": 0, "skipped_user": 0}

    rows = resp.get("values", [])
    if len(rows) <= 1:
        return {"tab": tab, "error": None, "cleared": 0, "kept": 0, "skipped_user": 0}

    header = rows[0]
    email_col = _get_col_index(header, "Email")
    source_col = _get_col_index(header, "Email Source")
    discovered_col = _get_col_index(header, "Discovered Via")
    if email_col < 0:
        return {"tab": tab, "error": "No Email column", "cleared": 0, "kept": 0, "skipped_user": 0}

    cleared = 0
    kept = 0
    skipped_user = 0
    to_clear = []  # list of (row_num, reason, bad_email)

    for i, row in enumerate(rows[1:], start=2):  # sheet row = i (1-based, skipping header)
        current_email = row[email_col] if email_col < len(row) else ""
        if not current_email:
            continue
        bad, reason = _is_malformed(current_email)
        if not bad:
            kept += 1
            continue

        # Bad email found. Was this row added by the agent (Discovered Via set) or user-curated?
        added_by_agent = False
        if discovered_col >= 0:
            dv = row[discovered_col] if discovered_col < len(row) else ""
            added_by_agent = bool(dv.strip())

        if not added_by_agent and not force:
            # User-curated row with multi-email cell — leave alone
            skipped_user += 1
            continue

        to_clear.append((i, reason, current_email))

    if not to_clear and skipped_user == 0:
        return {"tab": tab, "error": None, "cleared": 0, "kept": kept, "skipped_user": 0}

    if to_clear or skipped_user:
        print(f"  [{tab}] {len(to_clear)} agent-added malformed / {skipped_user} user-curated skipped / {kept} good")
    for row_num, reason, bad_email in to_clear[:5]:  # print first 5 examples
        print(f"    r{row_num}: {reason:20} — {bad_email!r}")
    if len(to_clear) > 5:
        print(f"    ... and {len(to_clear) - 5} more")

    if dry_run or not to_clear:
        return {"tab": tab, "error": None, "cleared": len(to_clear),
                "kept": kept, "skipped_user": skipped_user}

    # Batch-clear the Email and Email Source cells
    data = []
    for row_num, _, _ in to_clear:
        data.append({
            "range": f"'{tab}'!{_col_letter(email_col)}{row_num}",
            "values": [[""]],
        })
        if source_col >= 0:
            data.append({
                "range": f"'{tab}'!{_col_letter(source_col)}{row_num}",
                "values": [[""]],
            })

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    cleared = len(to_clear)
    return {"tab": tab, "error": None, "cleared": cleared, "kept": kept,
            "skipped_user": skipped_user}


def main():
    parser = argparse.ArgumentParser(description="Clear malformed emails from partner tabs")
    parser.add_argument("--tab", help="One specific tab. If omitted, all tabs.")
    parser.add_argument("--dry-run", action="store_true", help="Just report, don't clear")
    parser.add_argument("--force", action="store_true",
                       help="Also clear USER-curated rows (careful — destroys multi-email cells "
                            "user pasted manually). Default: only clear agent-added rows.")
    args = parser.parse_args()

    sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        print("ERROR: PARTNER_SHEET_ID not set", file=sys.stderr)
        sys.exit(1)

    service = get_sheets_service()
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

    # Skip Competitors, Other, Sheet4 — those aren't partner tabs
    skip_tabs = {"Competitors", "Other", "Sheet4"}
    if args.tab:
        target_tabs = [args.tab]
    else:
        target_tabs = [t for t in all_tabs if t not in skip_tabs]

    print(f"Cleanup: {len(target_tabs)} tab(s), dry_run={args.dry_run}\n")

    total_cleared = 0
    total_kept = 0
    total_skipped = 0
    for tab in target_tabs:
        result = clean_tab(service, sheet_id, tab, args.dry_run, force=args.force)
        if result.get("error"):
            print(f"  [{tab}] ERROR: {result['error']}")
        total_cleared += result.get("cleared", 0)
        total_kept += result.get("kept", 0)
        total_skipped += result.get("skipped_user", 0)

    print()
    print(f"Total: cleared {total_cleared} agent-added malformed | "
          f"skipped {total_skipped} user-curated | kept {total_kept} valid"
          + (" (DRY RUN)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
