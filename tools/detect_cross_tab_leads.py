"""
Cross-tab lead detector — flags partners that appear in 2+ competitor tabs.

A partner listed as a customer/partner of multiple viAct competitors is a
STRONG buying signal — they're actively shopping the space. These are the
hottest BD leads.

Output: writes a new tab "Cross-Vendor Leads" in the same sheet with columns
  Company Name | Website | Email | Also In (competitor tabs) | Signal Strength
Signal Strength = "MEDIUM" for 2 tabs, "HIGH" for 3 tabs, "VERY HIGH" for 4+.

Idempotent — clears + rewrites the tab on each run.

Usage:
    python tools/detect_cross_tab_leads.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import (
    get_sheets_service,
    read_tracked_competitors,
    _norm_name_for_dedup,
    _norm_name_collapsed,
)
from utils import get_env

CROSS_TAB = "Cross-Vendor Leads"
HEADER = [
    "Company Name",
    "Website",
    "Email",
    "Also In (competitor tabs)",
    "Signal Strength",
    "Detected At",
]


def _ensure_cross_tab(service, sheet_id: str) -> int:
    """Create the Cross-Vendor Leads tab if missing. Return sheetId."""
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == CROSS_TAB:
            return s["properties"]["sheetId"]

    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "addSheet": {"properties": {"title": CROSS_TAB}}
        }]},
    ).execute()
    sheet_id_new = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    # write header
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{CROSS_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [HEADER]},
    ).execute()
    return sheet_id_new


def _clear_data_rows(service, sheet_id, tab_sheet_id):
    """Clear rows 2+ in the cross-tab (keep header)."""
    service.spreadsheets().values().clear(
        spreadsheetId=sheet_id,
        range=f"{CROSS_TAB}!A2:Z",
    ).execute()


def main():
    sheet_id = get_env("PARTNER_SHEET_ID")
    service = get_sheets_service()

    tracked = read_tracked_competitors()
    if not tracked:
        print("No Track-status competitors — nothing to scan.")
        return

    # partner_key -> {"name": original_display_name, "website": w, "email": e, "tabs": {t1, t2, ...}}
    partners = defaultdict(lambda: {"name": "", "website": "", "email": "", "tabs": set()})

    for t in tracked:
        tab = t.get("name", "").strip()
        if not tab:
            continue
        try:
            resp = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"{tab}!A:E",  # Name, Description, Website, Phone, Email
            ).execute()
        except Exception as e:
            print(f"  [warn] {tab} unreadable: {e}")
            continue
        rows = resp.get("values", [])
        if len(rows) < 2:
            continue
        for row in rows[1:]:
            name = row[0].strip() if len(row) > 0 else ""
            website = row[2].strip() if len(row) > 2 else ""
            email = row[4].strip() if len(row) > 4 else ""
            if not name:
                continue
            # v4.9: use collapsed-name key so "Rite Hite" and "RiteHite" merge
            key = _norm_name_collapsed(name)
            if not key:
                continue
            p = partners[key]
            if not p["name"]:
                p["name"] = name
            if not p["website"] and website:
                p["website"] = website
            if not p["email"] and email:
                p["email"] = email
            p["tabs"].add(tab)
        print(f"  scanned [{tab}] — {len(rows) - 1} rows")

    # Filter to partners appearing in 2+ tabs
    cross = [p for p in partners.values() if len(p["tabs"]) >= 2]
    cross.sort(key=lambda p: (-len(p["tabs"]), p["name"].lower()))

    if not cross:
        print("\nNo cross-tab partners found.")
        return

    print(f"\n=== {len(cross)} cross-vendor leads found ===")
    from datetime import date
    today = date.today().isoformat()
    out_rows = []
    for p in cross:
        n_tabs = len(p["tabs"])
        if n_tabs >= 4:
            strength = "VERY HIGH"
        elif n_tabs == 3:
            strength = "HIGH"
        else:
            strength = "MEDIUM"
        tabs_str = ", ".join(sorted(p["tabs"]))
        out_rows.append([
            p["name"],
            p["website"],
            p["email"],
            tabs_str,
            strength,
            today,
        ])
        print(f"  [{strength}] {p['name']:30}  in: {tabs_str}")

    # Ensure tab exists, clear old data, write fresh
    tab_sheet_id = _ensure_cross_tab(service, sheet_id)
    _clear_data_rows(service, sheet_id, tab_sheet_id)
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{CROSS_TAB}!A2",
        valueInputOption="RAW",
        body={"values": out_rows},
    ).execute()
    print(f"\nOK: wrote {len(out_rows)} rows to '{CROSS_TAB}' tab.")


if __name__ == "__main__":
    main()
