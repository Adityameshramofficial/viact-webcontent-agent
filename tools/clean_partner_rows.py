"""
Cleanup utility — remove partner rows written during a specific date.

Use case: v3 data-quality fix ran a pipeline that wrote bad rows (wrong emails
attributed to partners). Rather than manually deleting, delete all rows in
target tabs where "Discovered At" equals a given date.

Preserves any manually-curated rows (those without the "Discovered At" tag)
and rows discovered on other days.

CLI:
    python tools/clean_partner_rows.py --date 2026-07-01 --tabs Autodesk,Procore,Cryotos
    python tools/clean_partner_rows.py --date 2026-07-01 --all-buggy
    python tools/clean_partner_rows.py --date 2026-07-01 --tabs "Spot AI" --dry-run
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import get_sheets_service, PARTNER_COLUMNS

# The 6 tabs that got processed by the buggy pipeline
BUGGY_TABS = ["Autodesk", "Procore", "Cryotos", "Invigilo", "Spot AI", "Voxel"]


def _get_col_index(name: str) -> int:
    """Return zero-based column index for a header name."""
    return PARTNER_COLUMNS.index(name)


def clean_tab(service, sheet_id: str, tab_name: str,
              target_date: str, dry_run: bool = False) -> tuple[int, int]:
    """
    Delete rows from `tab_name` where `Discovered At` column == `target_date`.

    Returns (rows_deleted, rows_kept).
    """
    # Read all rows including header
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1:Z",
    ).execute()
    rows = resp.get("values", [])
    if len(rows) <= 1:
        return (0, 0)

    header = rows[0]
    if "Discovered At" not in header:
        print(f"  [{tab_name}] no 'Discovered At' column — skipping")
        return (0, len(rows) - 1)

    date_col = header.index("Discovered At")

    # Build rows to keep (row 0 = header, always keep)
    kept = [rows[0]]
    deleted_count = 0
    for row in rows[1:]:
        # Row might be shorter than header if trailing cells are blank
        row_date = row[date_col] if date_col < len(row) else ""
        if row_date == target_date:
            deleted_count += 1
        else:
            kept.append(row)

    kept_count = len(kept) - 1  # exclude header
    print(f"  [{tab_name}] delete {deleted_count}, keep {kept_count}"
          + (" (DRY RUN)" if dry_run else ""))

    if dry_run or deleted_count == 0:
        return (deleted_count, kept_count)

    # Overwrite the tab with kept rows only.
    # Strategy: clear range A2:Z (data area), then write kept[1:] back.
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A2:Z",
    ).execute()

    if len(kept) > 1:
        # Normalize row lengths to header length so gaps don't corrupt columns
        header_len = len(header)
        normalized = [
            row + [""] * (header_len - len(row)) if len(row) < header_len else row[:header_len]
            for row in kept[1:]
        ]
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A2",
            valueInputOption="RAW",
            body={"values": normalized},
        ).execute()

    return (deleted_count, kept_count)


def main():
    parser = argparse.ArgumentParser(description="Clean partner rows by discovered-at date")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tabs", help="Comma-separated tab names")
    group.add_argument("--all-buggy", action="store_true",
                       help=f"Clean all v3-buggy tabs: {', '.join(BUGGY_TABS)}")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be deleted, don't actually delete")
    args = parser.parse_args()

    tabs = BUGGY_TABS if args.all_buggy else [t.strip() for t in args.tabs.split(",") if t.strip()]

    sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        print("ERROR: PARTNER_SHEET_ID not set", file=sys.stderr)
        sys.exit(1)

    service = get_sheets_service()

    # Verify tabs exist
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]

    print(f"Cleanup: date={args.date}, dry_run={args.dry_run}")
    print()

    total_deleted = 0
    total_kept = 0
    for tab in tabs:
        if tab not in existing:
            print(f"  [{tab}] NOT FOUND — skipping")
            continue
        deleted, kept = clean_tab(service, sheet_id, tab, args.date, args.dry_run)
        total_deleted += deleted
        total_kept += kept

    print()
    print(f"Total: deleted {total_deleted} row(s), kept {total_kept} row(s)")


if __name__ == "__main__":
    main()
