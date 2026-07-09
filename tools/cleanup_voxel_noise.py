"""
One-off cleanup: remove 7 noise rows from Voxel tab.

Noise categories:
  - Products mis-extracted as companies (SAP Ariba, SAP Hana)
  - Investors mis-extracted as partners (HG Ventures)
  - Wrong namesake matches (Motus -> motus.dot.gov)
  - Ambiguous acronyms with no verifiable website (AGI)
  - Duplicate variants of same company (Americold vs Americold Logistics,
    Carlex vs Carlex Glass)

Matches on EXACT company name (case-insensitive) to avoid deleting the
correct row of a similar name. Deletes bottom-up so row indices don't shift.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import get_sheets_service
from utils import get_env

VOXEL_TAB = "Voxel"

NOISE_NAMES = {
    "agi",
    "americold",           # duplicate of "Americold Logistics"
    "motus",
    "carlex",              # duplicate of "Carlex Glass"
    "sap ariba",
    "sap hana",
    "hg ventures",
}

# v4.6: also purge rows whose Website column contains obvious junk domains
# (from pre-v4.4 discoveries that didn't have spam/directory filters).
NOISE_WEBSITE_SUBSTRINGS = {
    "sporting-gsale",       # spam-shop clone site
    "glassglobal.com",      # industry directory, not any partner's own site
    "-gsale", "-deal-", "-shop-", "-buy-", "-outlet-",
    "staging.", "dev.", "beta.", "test.",
}


def main():
    sheet_id = get_env("PARTNER_SHEET_ID")
    service = get_sheets_service()

    # 1. Get all rows from Voxel tab — columns A (name) + C (website)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{VOXEL_TAB}!A:C",
    ).execute()
    values = result.get("values", [])
    if not values:
        print(f"Voxel tab empty — nothing to do.")
        return

    print(f"Voxel tab: {len(values)} rows total (including header)")

    # 2. Find row indices to delete (0-based, sheet-API style)
    #    Delete if EITHER: (a) name is in NOISE_NAMES, OR
    #                      (b) website contains a NOISE_WEBSITE_SUBSTRINGS pattern
    to_delete = []
    for idx, row in enumerate(values):
        if not row:
            continue
        name = row[0].strip().lower() if len(row) > 0 else ""
        website = row[2].strip().lower() if len(row) > 2 else ""

        if name in NOISE_NAMES:
            to_delete.append((idx, row[0], "noise name"))
            continue
        if website and any(sub in website for sub in NOISE_WEBSITE_SUBSTRINGS):
            to_delete.append((idx, row[0], f"junk website: {website}"))

    if not to_delete:
        print("No noise rows matched. Nothing to delete.")
        return

    print(f"\nFound {len(to_delete)} noise rows to delete:")
    for idx, name, reason in to_delete:
        print(f"  row {idx + 1}: {name}  ({reason})")

    # 3. Get the sheetId for Voxel tab (needed for deleteDimension)
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    voxel_sheet_id = None
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == VOXEL_TAB:
            voxel_sheet_id = s["properties"]["sheetId"]
            break
    if voxel_sheet_id is None:
        print(f"ERROR: Voxel tab not found in sheet metadata")
        return

    # 4. Delete rows bottom-up so indices don't shift
    to_delete.sort(key=lambda x: -x[0])
    requests = []
    for idx, _name, _reason in to_delete:
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": voxel_sheet_id,
                    "dimension": "ROWS",
                    "startIndex": idx,
                    "endIndex": idx + 1,
                }
            }
        })

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests},
    ).execute()

    print(f"\nOK: deleted {len(to_delete)} rows from Voxel tab.")


if __name__ == "__main__":
    main()
