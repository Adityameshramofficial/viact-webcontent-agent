"""
generate_dashboard.py — reads Google Sheets and outputs dashboard-data.json
Runs daily via GitHub Actions after the pipeline completes.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))


def log(msg):
    print(f"[dashboard] {msg}", flush=True)


def get_dashboard_data() -> dict:
    try:
        from push_to_sheets import get_sheets_service
    except ImportError as e:
        log(f"Import failed: {e}")
        return {}

    sheet_id = os.environ.get("SHEET_ID", "")
    if not sheet_id:
        log("SHEET_ID not set — skipping Sheets read")
        return {}

    try:
        svc = get_sheets_service()

        # ── Read Webpage Content tab ──────────────────────────────────────────
        result = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id, range="Webpage Content!A:P"
        ).execute()
        rows = result.get("values", [])[1:]  # skip header

        today      = datetime.date.today()
        week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()
        today_str  = today.isoformat()

        total_pages      = len(rows)
        this_week_rows   = [r for r in rows if r and r[0] >= week_start]
        today_rows       = [r for r in rows if r and r[0] == today_str]
        this_week_pages  = len(this_week_rows)
        today_pages      = len(today_rows)
        last_run_date    = rows[-1][0] if rows and rows[-1] else "—"

        # Latest 5 topics
        latest_topics = []
        for r in reversed(rows[-15:]):
            if not r:
                continue
            col_n = r[13] if len(r) > 13 else ""
            is_blog = "blog" in col_n.lower()
            latest_topics.append({
                "date":         r[0] if len(r) > 0 else "",
                "topic":        r[2] if len(r) > 2 else "",
                "content_type": "Blog" if is_blog else "Pillar",
            })
            if len(latest_topics) >= 5:
                break

        # ── Read Dedup_Log tab ────────────────────────────────────────────────
        try:
            dedup_res   = svc.spreadsheets().values().get(
                spreadsheetId=sheet_id, range="Dedup_Log!A:B"
            ).execute()
            total_dedup = max(len(dedup_res.get("values", [])) - 1, 0)
        except Exception:
            total_dedup = 0

        # ── IST timestamp ─────────────────────────────────────────────────────
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        generated_at = datetime.datetime.now(ist).isoformat()

        data = {
            "total_pages":     total_pages,
            "this_week_pages": this_week_pages,
            "today_pages":     today_pages,
            "total_dedup":     total_dedup,
            "last_run_date":   last_run_date,
            "latest_topics":   latest_topics,
            "generated_at":    generated_at,
        }

        log(f"Total pages: {total_pages} | Today: {today_pages} | Dedup: {total_dedup}")
        return data

    except Exception as exc:
        log(f"Sheets read failed: {exc}")
        return {}


def main():
    log("Reading Google Sheets data...")
    data = get_dashboard_data()

    if not data:
        log("No data — dashboard-data.json not written")
        sys.exit(1)

    out_path = os.path.join(os.path.dirname(__file__), "dashboard-data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log(f"Written to {out_path}")


if __name__ == "__main__":
    main()
