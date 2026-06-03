"""
Entry point for GitHub Actions daily opportunity scan.
Runs Agent 5, pushes results to Sheets, saves .tmp fallback.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from agent5_opportunity_scanner import run_daily_scan
from push_to_sheets import push_opportunities


def main() -> None:
    result = run_daily_scan(progress_callback=print)
    opportunities = result.get("opportunities", [])
    meta = result.get("scan_metadata", {})

    if opportunities:
        pushed = push_opportunities(opportunities)
        print(f"Pushed {pushed} opportunities to Sheets tab 'Opportunities'")
    else:
        print("No new opportunities found this run")

    # Save .tmp fallback for Actions artifact
    os.makedirs(".tmp", exist_ok=True)
    out_path = f".tmp/opportunities_{meta.get('scan_date', 'unknown')}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Saved fallback: {out_path}")

    print(
        f"Scan complete — {len(opportunities)} opportunities | "
        f"{meta.get('competitors_scanned', 0)} competitors | "
        f"{meta.get('duration_seconds', 0)}s"
    )


if __name__ == "__main__":
    main()
