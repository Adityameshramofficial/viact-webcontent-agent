"""
One-off cleanup: LLM-classify each row in a competitor tab for viAct-relevance,
delete the ones tagged "no".

viAct = AI construction site safety + video analytics platform.
Their BD-relevant partners are construction / EHS / heavy-industry safety, NOT
retail / CPG / logistics / cold storage / insurance / generic SaaS.

Usage:
    python tools/filter_viact_relevance.py Voxel
    python tools/filter_viact_relevance.py Autodesk --dry-run

--dry-run: print classifications only, don't delete anything (safety check).
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from push_to_sheets import get_sheets_service
from utils import get_env

MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

CLASSIFY_PROMPT = """You are classifying a company for viAct.ai's BD outreach.

viAct = AI-powered INDUSTRIAL SAFETY + video analytics platform
(CCTV + computer vision + AI bounding boxes) serving 5 verticals:
  Construction, Manufacturing, Mining, Oil & Gas, Logistics.
Target buyers: EHS Directors, HSE Managers, Plant Managers, Safety Officers
at industrial enterprises.

INCLUDE (viact_relevant="yes") if the company owns / operates / serves
physical industrial sites where worker safety, PPE compliance, or equipment
monitoring matters:
  - Construction: GC, developers, EPC, sub-contractors, MEP
  - Manufacturing plants of ANY kind: automotive parts (Piston Automotive),
    glass (NSG Group), CPG bottling/packaging plants (Clorox, Pepsi, Coca-Cola),
    chemicals, textiles, electronics, food processing (Canfisco)
  - Mining, quarrying, aggregate, cement, steel
  - Oil & Gas: upstream, midstream, downstream
  - Logistics: fulfillment warehouses (Amazon DCs), 3PL (Verst, Ceva),
    ports & terminals (DP World, APM Terminals, Port of Virginia),
    cold storage (Americold)
  - Engineering / BIM / digital twin / 3D reality-capture serving industry
  - Real estate / infrastructure developers (highways, tunnels, airports)
  - EHS consulting or software
  - Site documentation, drone / photo progress-tracking
  - Wearable tech / IoT / edge-camera vendors for industrial workers
  - Loading-dock / material-handling / heavy-equipment vendors (Rite Hite)
  - Facility management at large fixed industrial sites

REJECT (viact_relevant="no"):
  - Retail STORES only (Macy's, Dick's, Albertsons, Home Depot, Saks, Michaels,
    Lowe's, CVS retail). NOTE: retail warehouses/DCs are IN-scope,
    but store-only chains are OUT.
  - Banks / investment firms / VC / hedge funds
  - Insurance (unless construction-specific)
  - Hospitality / hotels / restaurants / travel (Hotel SAAS, Amadeus)
  - Generic enterprise SaaS (Salesforce, HubSpot, Sage, Eclipse IDE,
    WordPress plugins: Elementor, Piotnet, FluentAffiliate, Vbout,
    FlowMattic, BitFlows)
  - Consumer product / gadget makers (MTech knives, Whitestone accessories)
  - Telecom carriers
  - Labor unions
  - Healthcare providers / hospitals / retail pharmacies
  - Media / news / marketing agencies

Company to classify:
  Name: {name}
  Description: {description}
  Website: {website}

On truly ambiguous / unclear cases (name too short or generic), output "no".

OUTPUT (strict JSON):
{{"viact_relevant": "yes" | "no", "reason": "one short sentence"}}
"""


def _classify(client, name, description, website):
    prompt = CLASSIFY_PROMPT.format(
        name=name, description=description or "(no description)",
        website=website or "(no website)",
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return (data.get("viact_relevant") or "").lower().strip(), data.get("reason", "")
    except Exception as e:
        # 70B rate-limit? fall back to 8B-scout
        try:
            resp = client.chat.completions.create(
                model=FALLBACK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            return (data.get("viact_relevant") or "").lower().strip(), data.get("reason", "")
        except Exception as e2:
            return "unknown", f"llm error: {e2}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tab", help="Competitor tab name, e.g., Voxel")
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify only, do not delete")
    args = parser.parse_args()

    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    sheet_id = get_env("PARTNER_SHEET_ID")
    service = get_sheets_service()

    # Read cols A (Name), B (Description), C (Website)
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{args.tab}!A:C",
    ).execute()
    values = result.get("values", [])
    if not values:
        print(f"{args.tab} tab empty — nothing to do.")
        return
    print(f"{args.tab}: {len(values)} rows (including header)")

    to_delete = []
    for idx, row in enumerate(values):
        if idx == 0:
            continue  # skip header
        if not row:
            continue
        name = row[0].strip() if len(row) > 0 else ""
        desc = row[1].strip() if len(row) > 1 else ""
        website = row[2].strip() if len(row) > 2 else ""
        if not name:
            continue

        verdict, reason = _classify(client, name, desc, website)
        tag = "KEEP" if verdict == "yes" else ("DROP" if verdict == "no" else "?")
        print(f"  row {idx + 1:3} [{tag}] {name:30} — {reason[:70]}")
        if verdict == "no":
            to_delete.append((idx, name))
        time.sleep(0.15)  # be nice to Groq TPM

    if not to_delete:
        print("\nNothing to drop — all rows viAct-relevant.")
        return

    print(f"\n{len(to_delete)} rows tagged as viAct-irrelevant.")

    if args.dry_run:
        print("--dry-run: skipping delete.")
        return

    # Get sheet id and batch-delete bottom-up
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    tab_sheet_id = None
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == args.tab:
            tab_sheet_id = s["properties"]["sheetId"]
            break
    if tab_sheet_id is None:
        print(f"ERROR: tab {args.tab} not found in metadata")
        return

    to_delete.sort(key=lambda x: -x[0])
    requests = [{
        "deleteDimension": {
            "range": {
                "sheetId": tab_sheet_id,
                "dimension": "ROWS",
                "startIndex": idx,
                "endIndex": idx + 1,
            }
        }
    } for idx, _ in to_delete]

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests},
    ).execute()
    print(f"OK: deleted {len(to_delete)} rows from {args.tab}.")


if __name__ == "__main__":
    main()
