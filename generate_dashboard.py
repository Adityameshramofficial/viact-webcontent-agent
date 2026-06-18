"""
generate_dashboard.py — reads Google Sheets (vertical format) and outputs dashboard-data.json
Runs daily via GitHub Actions after the pipeline completes.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

SHEET_ID   = os.environ.get("SHEET_ID", "1vo2UiNHJIFGyLj7wxAweEMyvwnNJoOVUTrJM4M9KOec")
SHEETS_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"


def log(msg):
    print(f"[dashboard] {msg}", flush=True)


def _parse_pages(rows: list) -> list[dict]:
    """Split vertical-format rows into page blocks. Each page starts with 'Input Source' row."""
    pages = []
    current = {}
    in_page = False

    for r in rows:
        if not r:
            continue
        label = str(r[0]).strip() if len(r) > 0 else ""
        value = str(r[1]).strip() if len(r) > 1 else ""

        if label == "Input Source":
            if current:
                pages.append(current)
            current = {"Input Source": value}
            in_page = True
            continue

        if in_page and label and value:
            # Only store first occurrence of each label
            if label not in current:
                current[label] = value

    if current:
        pages.append(current)

    return pages


def get_dashboard_data() -> dict:
    try:
        from push_to_sheets import get_sheets_service
    except ImportError as e:
        log(f"Import failed: {e}")
        return {}

    if not SHEET_ID:
        log("SHEET_ID not set")
        return {}

    try:
        svc = get_sheets_service()

        # ── Webpage Content tab ───────────────────────────────────────────────
        result = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range="Webpage Content!A:B"
        ).execute()
        rows = result.get("values", [])[1:]

        pages = _parse_pages(rows)
        total_pages = len(pages)

        today      = datetime.date.today()
        week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()
        today_str  = today.isoformat()

        this_week_pages = sum(1 for p in pages if p.get("Date", "") >= week_start)
        today_pages     = sum(1 for p in pages if p.get("Date", "") == today_str)
        last_run_date   = pages[-1].get("Date", "—") if pages else "—"

        # Latest 5 for email preview
        latest_topics = []
        for p in reversed(pages[-15:]):
            src     = p.get("Input Source", "")
            is_blog = "blog" in src.lower()
            title   = p.get("H1") or p.get("Meta Title") or p.get("Webpage Body", "")[:60]
            latest_topics.append({
                "date":         p.get("Date", ""),
                "topic":        title[:70],
                "content_type": "Blog" if is_blog else "Pillar",
            })
            if len(latest_topics) >= 5:
                break

        # Last 3 pages as full output previews
        recent_outputs = []
        for p in reversed(pages[-10:]):
            src     = p.get("Input Source", "")
            is_blog = "blog" in src.lower()

            h1          = p.get("H1", "")
            subheadline = p.get("Subheadline", "")
            meta_title  = p.get("Meta Title", "")
            meta_desc   = p.get("Meta Description", "")
            keyword     = p.get("Primary Keyword", "")
            problem     = p.get("Problem Statement", "")[:200]
            faq_q       = p.get("FAQ 1 Question", "")
            faq_a       = p.get("FAQ 1 Answer", "")[:120]
            date        = p.get("Date", "")

            # Skip rows with no real content
            if not h1 and not meta_title:
                continue

            recent_outputs.append({
                "date":         date,
                "topic":        h1[:70] or meta_title[:70],
                "content_type": "Blog" if is_blog else "Pillar",
                "meta_title":   meta_title[:75],
                "meta_desc":    meta_desc[:160],
                "keyword":      keyword[:60],
                "subheadline":  subheadline[:130],
                "problem":      problem,
                "faq_q":        faq_q[:100],
                "faq_a":        faq_a,
                "source":       src[:40],
            })
            if len(recent_outputs) >= 3:
                break

        # ── Dedup_Log tab ─────────────────────────────────────────────────────
        try:
            dedup_res   = svc.spreadsheets().values().get(
                spreadsheetId=SHEET_ID, range="Dedup_Log!A:B"
            ).execute()
            total_dedup = max(len(dedup_res.get("values", [])) - 1, 0)
        except Exception:
            total_dedup = 0

        # ── IST timestamp ─────────────────────────────────────────────────────
        ist          = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        generated_at = datetime.datetime.now(ist).isoformat()

        data = {
            "total_pages":     total_pages,
            "this_week_pages": this_week_pages,
            "today_pages":     today_pages,
            "total_dedup":     total_dedup,
            "last_run_date":   last_run_date,
            "latest_topics":   latest_topics,
            "recent_outputs":  recent_outputs,
            "sheet_url":       SHEETS_URL,
            "generated_at":    generated_at,
        }

        log(f"Total: {total_pages} | Today: {today_pages} | Dedup: {total_dedup} | Output previews: {len(recent_outputs)}")
        return data

    except Exception as exc:
        log(f"Sheets read failed: {exc}")
        return {}


def main():
    log("Reading Google Sheets data...")
    data = get_dashboard_data()

    if not data:
        log("No data written")
        sys.exit(1)

    out_path = os.path.join(os.path.dirname(__file__), "dashboard-data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    log(f"Written: {out_path}")


if __name__ == "__main__":
    main()
