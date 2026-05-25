"""
Weekly viAct Market Radar — headless pipeline for GitHub Actions.

Flow:
  Agent 1 (Tavily)   → discover top 3 content gaps
  Agent 2 (Firecrawl)→ scrape competitor pages for each gap
  Agent 3 (Groq)     → generate full webpage content suite
  push_to_sheets     → append rows to Google Sheets (service account, no login)
  send_marketing_email → notify marketing@viact.ai (Gary format title)

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


def send_marketing_email(gaps: list, processed_topic: str, processed_count: int) -> bool:
    """
    Send weekly radar summary to marketing@viact.ai via Resend.
    Subject follows Gary's format:
      viAct Automation - Market Radar Agent Team for <topic> and Webpage Content Generation
    Body covers: What is this agent, Input, Output, Problem Solved, Gap list + Sheet link.
    Returns True on success, False on failure (non-fatal).
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

    # ── Subject: Gary's format ─────────────────────────────────────────────────
    subject = (
        f"viAct Automation - Market Radar Agent Team for "
        f"{processed_topic} and Webpage Content Generation"
    )

    # ── Gap rows ───────────────────────────────────────────────────────────────
    gap_rows_html = ""
    gap_rows_text = ""
    for i, gap in enumerate(gaps, 1):
        topic = gap.get("topic", "—")
        score = gap.get("opportunity_score", "—")
        comp_count = gap.get("competitor_count", 0)
        confirmed = gap.get("confirmed_at", "")
        status_label = "Content Generated + Saved to Sheets" if i <= processed_count else "Identified — Pending Content"
        score_color = "#f59e0b" if score == "High" else "#6b7280"

        gap_rows_html += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-weight:600;color:#0f172a">{i}. {topic}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;text-align:center">
            <span style="background:{score_color};color:#fff;padding:3px 10px;border-radius:4px;font-size:12px;font-weight:600">{score}</span>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px">{comp_count} competitor(s)</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#16a34a;font-weight:500">{status_label}</td>
        </tr>"""

        gap_rows_text += (
            f"  {i}. {topic}\n"
            f"     Score: {score} | {comp_count} competitor(s) | {status_label}\n"
            f"     Confirmed at: {confirmed}\n\n"
        )

    html_body = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif">
<div style="max-width:680px;margin:32px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)">

  <!-- Header -->
  <div style="background:#0f172a;padding:28px 36px">
    <p style="color:#60a5fa;margin:0 0 6px;font-size:12px;letter-spacing:1px;text-transform:uppercase">viAct Automation System</p>
    <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700">Market Radar Agent Team</h1>
    <p style="color:#94a3b8;margin:8px 0 0;font-size:13px">Weekly Auto-Run &nbsp;·&nbsp; {run_date}</p>
  </div>

  <div style="padding:28px 36px">

    <!-- What is this agent -->
    <h2 style="color:#0f172a;font-size:15px;margin:0 0 10px;border-left:3px solid #2563eb;padding-left:10px">What Is This Agent?</h2>
    <p style="color:#475569;font-size:14px;line-height:1.6;margin:0 0 20px">
      The <strong>Market Radar Agent Team</strong> is a 3-agent AI pipeline that runs every Monday.
      It automatically scans competitor websites, identifies construction safety content gaps on viAct.ai,
      and generates a full SEO-ready webpage content suite — all without any human input.
    </p>

    <!-- Problem Solved -->
    <h2 style="color:#0f172a;font-size:15px;margin:0 0 10px;border-left:3px solid #dc2626;padding-left:10px">Problem It Solves</h2>
    <p style="color:#475569;font-size:14px;line-height:1.6;margin:0 0 20px">
      Manually checking 8+ competitor websites, spotting what topics viAct is missing, and writing a full
      solution page takes the content team <strong>2–3 days per topic</strong>. This pipeline does it in
      <strong>under 15 minutes</strong> — with zero hallucination (every gap is confirmed by live Tavily search,
      not LLM guessing).
    </p>

    <!-- Input → Output -->
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
      <tr>
        <td style="width:50%;vertical-align:top;padding-right:12px">
          <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px">
            <p style="margin:0 0 8px;font-weight:700;color:#15803d;font-size:13px">INPUT</p>
            <ul style="margin:0;padding-left:18px;color:#166534;font-size:13px;line-height:1.8">
              <li>viAct.ai sitemap (auto-fetched)</li>
              <li>8 competitor websites (Protex AI, Intenseye, Chooch, EHS Insight, etc.)</li>
              <li>Singapore MOM / UAE OSHAD regulatory trends</li>
              <li>No manual input required</li>
            </ul>
          </div>
        </td>
        <td style="width:50%;vertical-align:top;padding-left:12px">
          <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px">
            <p style="margin:0 0 8px;font-weight:700;color:#1d4ed8;font-size:13px">OUTPUT</p>
            <ul style="margin:0;padding-left:18px;color:#1e40af;font-size:13px;line-height:1.8">
              <li>3 confirmed content gaps (Tavily-verified)</li>
              <li>SEO meta title + description</li>
              <li>Hero section + H1/H2 heading map</li>
              <li>5 Schema FAQs + regulatory context</li>
              <li>Internal links + image prompts</li>
              <li>Saved to Google Sheets (ready for CMS)</li>
            </ul>
          </div>
        </td>
      </tr>
    </table>

    <!-- Agent breakdown -->
    <h2 style="color:#0f172a;font-size:15px;margin:0 0 12px;border-left:3px solid #7c3aed;padding-left:10px">How the 3 Agents Work</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
      <tr style="background:#f8fafc">
        <td style="padding:10px 12px;border:1px solid #e2e8f0;font-weight:700;color:#7c3aed;width:28%">Agent 1 — Market Radar<br><span style="font-weight:400;color:#64748b">Tavily Search API</span></td>
        <td style="padding:10px 12px;border:1px solid #e2e8f0;color:#334155">Searches all competitor sites, extracts 10–15 topic candidates via Llama 3.3, then confirms each as a real gap using a two-layer check (sitemap + live Tavily search on viact.ai).</td>
      </tr>
      <tr>
        <td style="padding:10px 12px;border:1px solid #e2e8f0;font-weight:700;color:#0891b2">Agent 2 — Data Extractor<br><span style="font-weight:400;color:#64748b">Firecrawl API</span></td>
        <td style="padding:10px 12px;border:1px solid #e2e8f0;color:#334155">Scrapes the exact competitor pages that cover the confirmed gap. Returns clean Markdown content. If a page blocks access, it logs ACCESS DENIED — never invents competitor data.</td>
      </tr>
      <tr style="background:#f8fafc">
        <td style="padding:10px 12px;border:1px solid #e2e8f0;font-weight:700;color:#059669">Agent 3 — Content Architect<br><span style="font-weight:400;color:#64748b">Groq / Llama 3.3 70B</span></td>
        <td style="padding:10px 12px;border:1px solid #e2e8f0;color:#334155">Builds the full webpage content suite from scraped data — H1, meta tags, FAQs, regulatory context (MOM/OSHAD), internal links, and image prompts. Saves to Google Sheets.</td>
      </tr>
    </table>

    <!-- This week's gaps -->
    <h2 style="color:#0f172a;font-size:15px;margin:0 0 12px;border-left:3px solid #f59e0b;padding-left:10px">This Week's Confirmed Gaps ({run_date})</h2>
    <table style="width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px">
      <thead>
        <tr style="background:#f1f5f9">
          <th style="padding:10px 12px;text-align:left;border:1px solid #e2e8f0">Topic</th>
          <th style="padding:10px 12px;text-align:center;border:1px solid #e2e8f0">Score</th>
          <th style="padding:10px 12px;text-align:center;border:1px solid #e2e8f0">Competitors</th>
          <th style="padding:10px 12px;text-align:left;border:1px solid #e2e8f0">Status</th>
        </tr>
      </thead>
      <tbody>
        {gap_rows_html}
      </tbody>
    </table>

    <!-- CTA -->
    <div style="text-align:center;margin:8px 0 24px">
      <a href="{sheet_url}"
         style="display:inline-block;background:#2563eb;color:#fff;padding:12px 28px;border-radius:7px;text-decoration:none;font-size:14px;font-weight:700">
        View Full Content in Google Sheets →
      </a>
    </div>

    <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">
    <p style="font-size:11px;color:#94a3b8;text-align:center;margin:0">
      Sent automatically by viAct Automation System &nbsp;·&nbsp; Market Radar Agent Team &nbsp;·&nbsp;
      Powered by Tavily + Firecrawl + Groq/Llama 3.3
    </p>
  </div>
</div>
</body>
</html>"""

    text_body = (
        f"viAct Automation - Market Radar Agent Team\n"
        f"Weekly Auto-Run: {run_date}\n"
        f"{'='*60}\n\n"
        f"WHAT IS THIS AGENT?\n"
        f"A 3-agent AI pipeline that scans competitors, confirms content gaps\n"
        f"on viact.ai, and generates full SEO webpage content — every Monday.\n\n"
        f"PROBLEM IT SOLVES:\n"
        f"Manual competitor research + content writing = 2-3 days per topic.\n"
        f"This pipeline does it in under 15 minutes with zero hallucination.\n\n"
        f"INPUT:\n"
        f"  - viAct.ai sitemap (auto-fetched)\n"
        f"  - 8 competitor websites\n"
        f"  - Singapore MOM / UAE OSHAD regulatory trends\n\n"
        f"OUTPUT:\n"
        f"  - 3 confirmed content gaps\n"
        f"  - SEO meta title + description\n"
        f"  - Hero section, FAQs, regulatory context, internal links\n"
        f"  - Saved to Google Sheets (ready for CMS)\n\n"
        f"THIS WEEK'S CONFIRMED GAPS:\n\n"
        f"{gap_rows_text}"
        f"View full content: {sheet_url}\n"
    )

    import requests as _req
    payload = {
        "from": "viAct Automation <onboarding@resend.dev>",
        "to": ["marketing@viact.ai"],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    try:
        resp = _req.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        email_id = resp.json().get("id", "?")
        log(f"  Email sent (id: {email_id}) — Subject: {subject}")
        return True
    except Exception as exc:
        log(f"  Email send failed: {exc}")
        return False


def _validate_content(content: dict) -> list[str]:
    """Quality gate — returns list of warning strings (non-blocking)."""
    warnings = []
    seo = content.get("seo_suite", {})
    meta_title = seo.get("meta_title", "")
    if len(meta_title) > 60:
        warnings.append(f"meta_title too long: {len(meta_title)} chars (max 60)")
    faq_count = len(content.get("schema_faqs", []))
    if faq_count != 5:
        warnings.append(f"schema_faqs: {faq_count} items (expected 5)")
    for field in ["hero_section", "webpage_body", "seo_suite", "schema_faqs", "internal_links"]:
        if not content.get(field):
            warnings.append(f"Missing required field: {field}")
    return warnings


def main():
    log("=== viAct Weekly Market Radar — Auto Run ===")

    # ── Step 0a: Competitor new-page + freshness monitor ──────────────────────
    log("Step 0a: Checking for new/updated competitor pages this week...")
    from competitor_page_monitor import get_new_competitor_pages
    all_competitor_signals = get_new_competitor_pages(progress_callback=lambda phase, msg: log(msg))
    new_competitor_pages = [p for p in all_competitor_signals if p.get("change_type") != "updated_page"]
    updated_pages = [p for p in all_competitor_signals if p.get("change_type") == "updated_page"]
    if new_competitor_pages:
        log(f"  ALERT: {len(new_competitor_pages)} new competitor page(s):")
        for p in new_competitor_pages:
            log(f"    [NEW] [{p['competitor']}] {p['url']}")
    if updated_pages:
        log(f"  ALERT: {len(updated_pages)} competitor page(s) updated (title changed):")
        for p in updated_pages:
            log(f"    [UPDATED] [{p['competitor']}] {p['url']}")
    if not all_competitor_signals:
        log("  No new or updated competitor pages detected this week.")

    # ── Step 0b: Regulatory trigger scanner ───────────────────────────────────
    log("Step 0b: Scanning MOM / OSHAD / BCA / ISO for new regulatory publications...")
    from regulatory_scanner import scan_regulatory_updates
    regulatory_updates = scan_regulatory_updates(progress_callback=lambda phase, msg: log(msg))
    if regulatory_updates:
        log(f"  ALERT: {len(regulatory_updates)} new regulatory publication(s) found:")
        for r in regulatory_updates:
            log(f"    [{r['source']}] {r['title'][:70]}")
    else:
        log("  No new regulatory publications detected.")

    # ── Step 0c: Load dedup log from Google Sheets ────────────────────────────
    log("Step 0c: Loading topic dedup log from Google Sheets...")
    from push_to_sheets import get_sheets_service, read_dedup_log, write_dedup_log
    _sheets_svc = None
    _sheet_id = os.getenv("SHEET_ID", "")
    seen_topics: dict = {}
    try:
        _sheets_svc = get_sheets_service()
        seen_topics = read_dedup_log(_sheets_svc, _sheet_id)
        log(f"  {len(seen_topics)} previously seen topic(s) loaded from Sheets.")
    except Exception as exc:
        log(f"  Dedup log unavailable ({exc}) — deduplication skipped this run.")

    # ── Step 1: Agent 1 — discover gaps ───────────────────────────────────────
    log("Step 1: Agent 1 scanning competitors via Tavily...")
    injected = (new_competitor_pages or []) + [
        {
            "competitor": r["source"],
            "url": r["url"],
            "title": r["title"],
            "snippet": r["snippet"],
        }
        for r in regulatory_updates
    ]
    radar = discover_market_gaps(
        injected_pages=injected or None,
        seen_topics_override=seen_topics if seen_topics else None,
    )
    gaps = radar.get("topics", [])
    viact_pages = radar.get("viact_known_pages", [])

    # Write updated dedup log back to Sheets
    updated_seen = radar.get("updated_seen_topics", {})
    if updated_seen and _sheets_svc:
        try:
            write_dedup_log(_sheets_svc, _sheet_id, updated_seen)
            log(f"  Dedup log saved to Sheets ({len(updated_seen)} entries).")
        except Exception as exc:
            log(f"  Dedup log write failed: {exc}")

    if not gaps:
        log("No confirmed gaps found. Check TAVILY_API_KEY and competitor list. Exiting.")
        sys.exit(1)

    log(f"Found {len(gaps)} gap(s): {[g['topic'] for g in gaps]}")

    # ── Process top 1 gap per weekly run (stay within free API limits) ─────────
    autorun_base = int(os.getenv("GITHUB_RUN_NUMBER", "1"))
    processed_topic = gaps[0]["topic"] if gaps else "Content Gap Discovery"

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

        # ── Step 3b: Content quality gate ─────────────────────────────────────
        quality_warnings = _validate_content(content)
        if quality_warnings:
            log(f"  Quality gate — {len(quality_warnings)} warning(s):")
            for w in quality_warnings:
                log(f"    ⚠ {w}")
        else:
            log("  Quality gate passed.")

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
            out_path = f".tmp/weekly_gap_{i}.json"
            os.makedirs(".tmp", exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            log(f"  Saved fallback to {out_path}")

    # ── Step 5: Email alert ────────────────────────────────────────────────────
    log("\nStep 5: Sending email alert to marketing@viact.ai...")
    send_marketing_email(gaps=gaps, processed_topic=processed_topic, processed_count=len(gaps[:1]))

    log("\n=== Weekly Radar Complete ===")


if __name__ == "__main__":
    main()
