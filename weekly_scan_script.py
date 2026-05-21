"""
Weekly viAct Market Radar — headless pipeline for GitHub Actions.

Flow:
  Agent 1 (Tavily)   → discover top 3 content gaps
  Agent 2 (Firecrawl)→ scrape competitor pages for each gap
  Agent 3 (Groq)     → generate full webpage content suite
  push_to_sheets     → append rows to Google Sheets (service account, no login)
  send_marketing_email → notify marketing@viact.ai with gap list + Sheet link

Required env vars (set as GitHub Secrets):
  TAVILY_API_KEY, GROQ_API_KEY, FIRECRAWL_API_KEY, GCP_SERVICE_ACCOUNT, SHEET_ID,
  RESEND_API_KEY
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from agent1_market_explorer import discover_market_gaps
from agent2_data_extractor import extract_competitor_content
from agent3_content_architect import generate_structured_content
from push_to_sheets import push_webpage
from research_competitors import scrape_viact_sitemap


def log(msg: str):
    print(f"[radar] {msg}", flush=True)


def send_marketing_email(topics: list, processed_count: int) -> bool:
    """
    Send a summary email to marketing@viact.ai via Resend.
    Returns True on success, False on failure (non-fatal — pipeline continues).
    """
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        log("  RESEND_API_KEY not set — skipping email.")
        return False

    sheet_id = os.getenv("SHEET_ID", "")
    sheet_url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        if sheet_id else "https://docs.google.com/spreadsheets"
    )

    import datetime
    run_date = datetime.datetime.utcnow().strftime("%d %b %Y")

    # Build topic rows for plain-text and HTML
    topic_rows_html = ""
    topic_rows_text = ""
    for i, gap in enumerate(topics, 1):
        topic = gap.get("topic", "—")
        score = gap.get("opportunity_score", "—")
        comp_count = gap.get("competitor_count", 0)
        confirmed = gap.get("confirmed_at", "")
        processed_marker = " ✅ Content Generated" if i <= processed_count else ""

        topic_rows_html += (
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;font-weight:600'>{i}. {topic}{processed_marker}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;text-align:center'>"
            f"<span style='background:{'#f59e0b' if score=='High' else '#6b7280'};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px'>{score}</span>"
            f"</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:#6b7280;font-size:13px'>"
            f"{comp_count} competitor(s) | Confirmed {confirmed}"
            f"</td>"
            f"</tr>"
        )
        topic_rows_text += (
            f"  {i}. {topic}{processed_marker}\n"
            f"     Score: {score} | {comp_count} competitor(s) | Confirmed {confirmed}\n\n"
        )

    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#111">
  <div style="background:#0f172a;padding:24px 32px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">📡 viAct Weekly Market Radar</h1>
    <p style="color:#94a3b8;margin:8px 0 0;font-size:14px">Auto-run: {run_date}</p>
  </div>
  <div style="background:#f8fafc;padding:24px 32px;border-radius:0 0 8px 8px;border:1px solid #e2e8f0">
    <p style="font-size:15px">Agent 1 confirmed <strong>{len(topics)} content gap(s)</strong> this week where competitors have dedicated pages but viAct does not.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0">
      <thead>
        <tr style="background:#e2e8f0">
          <th style="padding:8px 12px;text-align:left;font-size:13px">Topic</th>
          <th style="padding:8px 12px;text-align:center;font-size:13px">Score</th>
          <th style="padding:8px 12px;text-align:left;font-size:13px">Evidence</th>
        </tr>
      </thead>
      <tbody>
        {topic_rows_html}
      </tbody>
    </table>
    <p style="font-size:14px;color:#475569">
      Content for the top gap has been generated and saved to Google Sheets.
    </p>
    <a href="{sheet_url}"
       style="display:inline-block;background:#2563eb;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:14px;font-weight:600;margin-top:8px">
      📊 View in Google Sheets →
    </a>
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
    <p style="font-size:12px;color:#94a3b8">
      Sent automatically by viAct Market Radar · Powered by Tavily + Firecrawl + Groq
    </p>
  </div>
</div>
"""

    text_body = (
        f"viAct Weekly Market Radar — {run_date}\n"
        f"{'='*50}\n\n"
        f"Agent 1 confirmed {len(topics)} content gap(s) this week:\n\n"
        f"{topic_rows_text}"
        f"Content for the top gap has been generated and saved to Google Sheets.\n\n"
        f"View sheet: {sheet_url}\n"
    )

    import requests as _req
    payload = {
        "from": "viAct Radar <onboarding@resend.dev>",
        "to": ["marketing@viact.ai"],
        "subject": f"[Market Radar] {len(topics)} New Content Gap(s) Found — {run_date}",
        "html": html_body,
        "text": text_body,
    }
    try:
        resp = _req.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        email_id = resp.json().get("id", "?")
        log(f"  Email sent successfully (id: {email_id})")
        return True
    except Exception as exc:
        log(f"  Email failed: {exc}")
        return False


def main():
    log("=== viAct Weekly Market Radar — Auto Run ===")

    # ── Step 1: Agent 1 — discover gaps ───────────────────────────────────────
    log("Step 1: Agent 1 scanning competitors via Tavily...")
    radar = discover_market_gaps()
    gaps = radar.get("topics", [])
    viact_pages = radar.get("viact_known_pages", [])

    if not gaps:
        log("No confirmed gaps found. Check TAVILY_API_KEY and competitor list. Exiting.")
        sys.exit(1)

    log(f"Found {len(gaps)} gap(s): {[g['topic'] for g in gaps]}")

    # ── Process top 1 gap per weekly run (stay within free API limits) ─────────
    # Change gaps[:1] to gaps[:3] to process all 3 if API quotas allow
    autorun_base = int(os.getenv("GITHUB_RUN_NUMBER", "1"))

    for i, gap in enumerate(gaps[:1], 1):
        topic = gap["topic"]
        log(f"\n--- Gap {i}: '{topic}' ---")

        # ── Step 2: Agent 2 — scrape competitor evidence pages ────────────────
        evidence_urls = [
            e["url"] for e in gap.get("competitor_evidence", []) if e.get("url")
        ]
        log(f"Step 2: Agent 2 scraping {len(evidence_urls)} competitor URL(s) via Firecrawl...")
        competitor_data = extract_competitor_content(evidence_urls) if evidence_urls else {}
        accessible = sum(1 for r in competitor_data.values() if r.get("success"))
        log(f"  {accessible}/{len(evidence_urls)} pages accessible.")

        # ── Step 3: Agent 3 — generate content ────────────────────────────────
        log("Step 3: Agent 3 generating content suite via Groq/Llama...")
        try:
            content = generate_structured_content(
                topic=topic,
                competitor_data=competitor_data,
                viact_pages=viact_pages,
                references="",
                radar_topic_entry=gap,
            )
        except Exception as exc:
            log(f"  Agent 3 failed: {exc}")
            continue

        # ── Step 4: Push to Google Sheets ──────────────────────────────────────
        log("Step 4: Pushing to Google Sheets...")
        try:
            count = push_webpage(
                content=content,
                decision_logic=content.get("decision_logic", ""),
                input_source=f"Weekly Auto-Run #{autorun_base + i - 1}",
                competitor_urls=list(competitor_data.keys()),
                autorun_num=autorun_base + i - 1,
                unverified=True,
            )
            log(f"  Pushed {count} row(s) to Google Sheets. Topic: '{topic}'")
        except Exception as exc:
            log(f"  Sheets push failed: {exc}")
            # Dump content locally as fallback
            out_path = f".tmp/weekly_gap_{i}.json"
            os.makedirs(".tmp", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            log(f"  Saved fallback to {out_path}")

    # ── Step 5: Email alert ────────────────────────────────────────────────────
    log("\nStep 5: Sending email alert...")
    send_marketing_email(topics=gaps, processed_count=len(gaps[:1]))

    log("\n=== Weekly Radar Complete ===")


if __name__ == "__main__":
    main()
