"""
viAct Automation — Daily Report Email

Runs every day at 5:55 PM IST via GitHub Actions cron.
Sends report automatically to Gary and Surendra (CC: Aditya).

Required GitHub Secrets:
  GCP_SERVICE_ACCOUNT  — Google Sheets service account JSON
  SHEET_ID             — Google Sheet ID
  RESEND_API_KEY       — re_ds6KxJPG_BWrArVtb5aAh6hcYfcfFZYQu
"""
import datetime
import os
import subprocess
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

# TEST MODE — sending to Shoyab first for review before Gary/Surendra
SHOYAB_EMAIL   = "shoyab.ali@viact.ai"
GARY_EMAIL     = "gary.ng@viact.ai"
SURENDRA_EMAIL = "surendra.singh@viact.ai"
ADITYA_EMAIL   = "aditya.meshram@viact.ai"
RESEND_FROM    = "Aditya Meshram <aditya.meshram@viact.ai>"  # requires viact.ai domain verified in Resend


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def log(msg: str):
    print(f"[daily-report] {msg}", flush=True)


# ── 1. Read Google Sheets data ────────────────────────────────────────────────
def _get_sheets_data() -> dict:
    from push_to_sheets import get_sheets_service

    sheet_id = _env("SHEET_ID")
    if not sheet_id:
        return {}
    try:
        svc = get_sheets_service()
        result = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id, range="Webpage Content!A:P"
        ).execute()
        rows = result.get("values", [])[1:]

        today      = datetime.date.today()
        week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()
        today_str  = today.isoformat()

        total_pages     = len(rows)
        this_week_rows  = [r for r in rows if r and r[0] >= week_start]
        today_rows      = [r for r in rows if r and r[0] == today_str]
        this_week_pages = len(this_week_rows)
        today_pages     = len(today_rows)

        pillar_count = sum(1 for r in this_week_rows if "blog" not in (r[13] if len(r) > 13 else "").lower())
        blog_count   = sum(1 for r in this_week_rows if "blog"     in (r[13] if len(r) > 13 else "").lower())

        latest_topics = []
        for r in reversed(rows[-10:]):
            if not r:
                continue
            is_blog = "blog" in (r[13] if len(r) > 13 else "").lower()
            latest_topics.append({
                "date":         r[0]  if len(r) > 0  else "",
                "topic":        r[2]  if len(r) > 2  else "",
                "content_type": "Blog" if is_blog else "Pillar",
            })
            if len(latest_topics) >= 5:
                break

        try:
            dedup_res   = svc.spreadsheets().values().get(
                spreadsheetId=sheet_id, range="Dedup_Log!A:B"
            ).execute()
            total_dedup = max(len(dedup_res.get("values", [])) - 1, 0)
        except Exception:
            total_dedup = 0

        last_run_date = rows[-1][0] if rows and rows[-1] else "No runs yet"

        return {
            "total_pages":     total_pages,
            "this_week_pages": this_week_pages,
            "today_pages":     today_pages,
            "pillar_count":    pillar_count,
            "blog_count":      blog_count,
            "latest_topics":   latest_topics,
            "total_dedup":     total_dedup,
            "last_run_date":   last_run_date,
        }
    except Exception as exc:
        log(f"Sheets read failed: {exc}")
        return {}


# ── 1b. Read Partner Outreach data (Agent 11) ────────────────────────────────
def _get_partner_outreach_stats() -> dict:
    """Return stats from the Partnership Leads sheet (Agent 11)."""
    from push_to_sheets import get_sheets_service

    sheet_id = _env("PARTNER_SHEET_ID")
    if not sheet_id:
        return {}
    try:
        svc = get_sheets_service()
        # List all tabs
        meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
        all_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]

        # Skip system tabs — everything else is a competitor partner tab
        skip = {"Competitors", "Other", "Sheet4", "External"}
        partner_tabs = [t for t in all_tabs if t not in skip]

        today_str = datetime.date.today().isoformat()
        total_partners = 0
        total_emails = 0
        total_phones = 0
        today_new_partners = 0
        today_new_emails = 0
        today_tab = ""
        per_tab_stats = []

        for tab in partner_tabs:
            try:
                r = svc.spreadsheets().values().get(
                    spreadsheetId=sheet_id, range=f"'{tab}'!A2:K200"
                ).execute()
                rows = r.get("values", [])
                tab_partners = 0
                tab_emails = 0
                tab_phones = 0
                for row in rows:
                    if not row or not row[0].strip():
                        continue
                    tab_partners += 1
                    if len(row) > 4 and row[4].strip():
                        tab_emails += 1
                    if len(row) > 3 and row[3].strip():
                        tab_phones += 1
                    # Discovered At = column K (index 10)
                    if len(row) > 10 and row[10].strip() == today_str:
                        today_new_partners += 1
                        today_tab = tab
                        if len(row) > 4 and row[4].strip():
                            today_new_emails += 1
                total_partners += tab_partners
                total_emails += tab_emails
                total_phones += tab_phones
                if tab_partners > 0:
                    per_tab_stats.append({
                        "tab": tab,
                        "partners": tab_partners,
                        "emails": tab_emails,
                        "coverage": int(tab_emails * 100 / tab_partners) if tab_partners else 0,
                    })
            except Exception:
                continue

        # Top 5 tabs by partner count
        per_tab_stats.sort(key=lambda x: -x["partners"])
        top_tabs = per_tab_stats[:5]

        # Read Competitors tab for Track/Skip breakdown
        try:
            r = svc.spreadsheets().values().get(
                spreadsheetId=sheet_id, range="'Competitors'!A2:G50"
            ).execute()
            comp_rows = r.get("values", [])
            comp_total = len(comp_rows)
            comp_track = sum(1 for row in comp_rows if len(row) >= 7 and row[6].strip().lower() == "track")
        except Exception:
            comp_total = 0
            comp_track = 0

        return {
            "total_tabs": len(partner_tabs),
            "total_partners": total_partners,
            "total_emails": total_emails,
            "total_phones": total_phones,
            "coverage_pct": int(total_emails * 100 / total_partners) if total_partners else 0,
            "today_new_partners": today_new_partners,
            "today_new_emails": today_new_emails,
            "today_tab": today_tab,
            "top_tabs": top_tabs,
            "comp_total": comp_total,
            "comp_track": comp_track,
        }
    except Exception as exc:
        log(f"Partner outreach read failed: {exc}")
        return {}


# ── 2. Get today's git improvements ──────────────────────────────────────────
def _get_todays_commits() -> list[dict]:
    try:
        result = subprocess.run(
            ["git", "log", "--since=24 hours ago", "--pretty=format:%h|%s", "--no-merges"],
            capture_output=True, text=True, timeout=10
        )
        commits = []
        for line in result.stdout.strip().splitlines():
            if "|" in line:
                h, msg = line.split("|", 1)
                display = msg.strip()
                for prefix in ("feat: ", "fix: ", "chore: ", "refactor: ", "docs: "):
                    if display.lower().startswith(prefix):
                        display = display[len(prefix):]
                        break
                commits.append({"hash": h.strip(), "raw": msg.strip(), "display": display})
        return commits
    except Exception:
        return []


# ── 3. Build HTML email ───────────────────────────────────────────────────────
def _build_partner_outreach_section(p: dict) -> str:
    """Return HTML for the Partner Outreach (Agent 11) section."""
    if not p or p.get("total_partners", 0) == 0:
        return ""

    today_line = ""
    if p.get("today_new_partners", 0) > 0:
        today_line = (
            f'<div style="background:#0f172a;border:1px solid #22c55e33;border-radius:8px;'
            f'padding:10px 14px;margin-bottom:10px;">'
            f'<span style="color:#22c55e;font-size:11px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:1px;">Today ({p.get("today_tab", "—")}):</span> '
            f'<span style="color:#e2e8f0;font-size:13px;font-weight:600;">'
            f'{p["today_new_partners"]} new partners, {p["today_new_emails"]} emails</span>'
            f'</div>'
        )

    # Top tabs
    top_rows_html = ""
    for t in p.get("top_tabs", []):
        top_rows_html += (
            f'<tr style="border-bottom:1px solid #1e293b;">'
            f'<td style="padding:6px 12px;color:#e2e8f0;font-size:12px;font-weight:500;">{t["tab"]}</td>'
            f'<td style="padding:6px 12px;text-align:center;color:#3b82f6;font-size:12px;font-weight:700;">{t["partners"]}</td>'
            f'<td style="padding:6px 12px;text-align:center;color:#22c55e;font-size:12px;font-weight:700;">{t["emails"]}</td>'
            f'<td style="padding:6px 12px;text-align:center;color:#94a3b8;font-size:11px;">{t["coverage"]}%</td>'
            f'</tr>'
        )

    return f"""
    <div style="margin-bottom:20px;">
      <p style="color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;
        letter-spacing:1.5px;margin:0 0 10px;">Partner Outreach (Agent 11)</p>
      {today_line}
      <table style="width:100%;border-collapse:collapse;margin-bottom:10px;">
        <tr>
          <td style="width:25%;padding-right:6px;vertical-align:top;">
            <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center;">
              <div style="color:#3b82f6;font-size:24px;font-weight:800;line-height:1;">{p["total_partners"]}</div>
              <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Partners</div>
            </div>
          </td>
          <td style="width:25%;padding:0 6px;vertical-align:top;">
            <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center;">
              <div style="color:#22c55e;font-size:24px;font-weight:800;line-height:1;">{p["total_emails"]}</div>
              <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Emails</div>
            </div>
          </td>
          <td style="width:25%;padding:0 6px;vertical-align:top;">
            <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center;">
              <div style="color:#a855f7;font-size:24px;font-weight:800;line-height:1;">{p["total_phones"]}</div>
              <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Phones</div>
            </div>
          </td>
          <td style="width:25%;padding-left:6px;vertical-align:top;">
            <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:12px;text-align:center;">
              <div style="color:#ff6a3d;font-size:24px;font-weight:800;line-height:1;">{p["coverage_pct"]}%</div>
              <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Coverage</div>
            </div>
          </td>
        </tr>
      </table>
      <table style="width:100%;border-collapse:collapse;background:#0f172a;
        border:1px solid #334155;border-radius:8px;overflow:hidden;">
        <thead><tr style="background:#1e293b;border-bottom:1px solid #334155;">
          <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;">Top Competitor Tabs</th>
          <th style="padding:8px 12px;text-align:center;color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;">Partners</th>
          <th style="padding:8px 12px;text-align:center;color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;">Emails</th>
          <th style="padding:8px 12px;text-align:center;color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;">%</th>
        </tr></thead>
        <tbody>{top_rows_html}</tbody>
      </table>
      <div style="margin-top:8px;background:#0f172a;border:1px solid #334155;border-radius:8px;
        padding:8px 14px;font-size:11px;color:#94a3b8;">
        Competitors tracked: <strong style="color:#e2e8f0;">{p["comp_track"]}</strong> / {p["comp_total"]}
        &nbsp;·&nbsp; Tabs: <strong style="color:#e2e8f0;">{p["total_tabs"]}</strong>
        &nbsp;·&nbsp; Free stack (no Apollo/paid) &nbsp;·&nbsp; Daily 6:30 AM IST auto-refresh
      </div>
    </div>"""


def _build_email(data: dict, commits: list[dict], partner_stats: dict) -> tuple[str, str]:

    run_date      = datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ).strftime("%d %b %Y, %I:%M %p IST")
    today_weekday = datetime.date.today().strftime("%A")

    total      = data.get("total_pages", 0)
    this_week  = data.get("this_week_pages", 0)
    today_new  = data.get("today_pages", 0)
    pillar_cnt = data.get("pillar_count", 0)
    blog_cnt   = data.get("blog_count", 0)
    dedup      = data.get("total_dedup", 0)
    last_run   = data.get("last_run_date", "—")
    topics     = data.get("latest_topics", [])

    sheet_id      = _env("SHEET_ID", "")
    sheet_url     = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=1093335602"
        if sheet_id else "https://docs.google.com/spreadsheets"
    )
    dashboard_url = "https://viact-webcontent-agent-a7yrhfuaifju4prfqntzku.streamlit.app/"

    days_to_monday = (7 - datetime.date.today().weekday()) % 7 or 7
    next_monday    = (datetime.date.today() + datetime.timedelta(days=days_to_monday)).strftime("%d %b %Y")

    is_run_day   = datetime.date.today().weekday() == 0
    status_label = "Content Generated Today" if today_new > 0 else ("Run Day" if is_run_day else "Monitoring Active")
    status_color = "#22c55e" if today_new > 0 else ("#f59e0b" if is_run_day else "#3b82f6")

    # Topic rows
    topic_rows_html = ""
    topic_rows_text = ""
    for t in topics:
        badge_color = "#7c3aed" if t["content_type"] == "Blog" else "#0891b2"
        topic_rows_html += (
            f"<tr style='border-bottom:1px solid #1e293b;'>"
            f"<td style='padding:8px 12px;color:#64748b;font-size:12px;white-space:nowrap;'>{t['date']}</td>"
            f"<td style='padding:8px 12px;color:#e2e8f0;font-size:13px;font-weight:500;'>{t['topic'][:65]}</td>"
            f"<td style='padding:8px 12px;text-align:center;'>"
            f"<span style='background:{badge_color}22;color:{badge_color};border:1px solid {badge_color}55;"
            f"border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;'>{t['content_type']}</span>"
            f"</td></tr>"
        )
        topic_rows_text += f"  {t['date']}  {t['topic'][:55]}  [{t['content_type']}]\n"

    # Improvements
    if commits:
        commit_rows_html = "".join(
            f"<tr style='border-bottom:1px solid #1e293b;'>"
            f"<td style='padding:7px 12px;width:60px;font-family:monospace;color:#475569;font-size:11px;'>{c['hash']}</td>"
            f"<td style='padding:7px 12px;color:#e2e8f0;font-size:13px;'>{c['display'][:90]}</td>"
            f"</tr>"
            for c in commits
        )
        improvements_section = f"""
    <div style="margin-bottom:20px;">
      <p style="color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;
        letter-spacing:1.5px;margin:0 0 10px;">Today's System Improvements</p>
      <table style="width:100%;border-collapse:collapse;background:#0f172a;
        border:1px solid #22c55e33;border-radius:8px;overflow:hidden;">
        <thead><tr style="background:#0f172a;border-bottom:1px solid #334155;">
          <th style="padding:8px 12px;text-align:left;color:#22c55e;font-size:11px;
            font-weight:700;text-transform:uppercase;width:60px;">Commit</th>
          <th style="padding:8px 12px;text-align:left;color:#22c55e;font-size:11px;
            font-weight:700;text-transform:uppercase;">Update</th>
        </tr></thead>
        <tbody>{commit_rows_html}</tbody>
      </table>
    </div>"""
        improvements_text = "TODAY'S IMPROVEMENTS:\n" + "\n".join(
            f"  [{c['hash']}] {c['display']}" for c in commits
        ) + "\n\n"
    else:
        improvements_section = ""
        improvements_text    = ""

    # Input / Output
    input_output_section = f"""
    <div style="margin-bottom:20px;">
      <p style="color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;
        letter-spacing:1.5px;margin:0 0 10px;">Input → Output Breakdown</p>
      <table style="width:100%;border-collapse:collapse;">
        <tr>
          <td style="width:50%;padding-right:8px;vertical-align:top;">
            <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;">
              <p style="margin:0 0 10px;font-weight:700;color:#3b82f6;font-size:12px;
                text-transform:uppercase;letter-spacing:1px;">INPUT</p>
              <ul style="margin:0;padding-left:16px;color:#94a3b8;font-size:12px;line-height:1.9;">
                <li>8 competitor websites (Protex AI, Intenseye, Visionify, Wakecap, OpenSpace, Safesite, Assignar, ClickUp)</li>
                <li>viAct.ai sitemap (auto-fetched, live)</li>
                <li>5 regulatory sources (MOM, WSH, BCA, OSHAD, ISO 45001)</li>
                <li>Reference Library (viAct project stats &amp; case studies)</li>
                <li>12-week dedup log — {dedup} topics tracked</li>
              </ul>
            </div>
          </td>
          <td style="width:50%;padding-left:8px;vertical-align:top;">
            <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;">
              <p style="margin:0 0 10px;font-weight:700;color:#ff6a3d;font-size:12px;
                text-transform:uppercase;letter-spacing:1px;">OUTPUT (per Monday run)</p>
              <ul style="margin:0;padding-left:16px;color:#94a3b8;font-size:12px;line-height:1.9;">
                <li><strong style="color:#e2e8f0;">1 Pillar Page</strong> — hero, 5 FAQs, regulatory context, schema JSON-LD</li>
                <li><strong style="color:#e2e8f0;">3 Supporting Blogs</strong> — regulatory / ROI / how-to, 3 FAQs each</li>
                <li>SEO meta title + description + primary keyword</li>
                <li>Internal links (34+ viAct product pages)</li>
                <li>2 AI image prompts (Nano Banana ready)</li>
                <li>Auto-pushed to Google Sheets → ready to publish</li>
              </ul>
            </div>
          </td>
        </tr>
      </table>
      <div style="margin-top:8px;background:#0f172a;border:1px solid #334155;border-radius:8px;
        padding:10px 14px;">
        <span style="color:#94a3b8;font-size:12px;">This week: </span>
        <span style="color:#22c55e;font-size:13px;font-weight:700;">{this_week} pages
          ({pillar_cnt} pillar + {blog_cnt} blog) &nbsp;·&nbsp; </span>
        <span style="color:#94a3b8;font-size:12px;">All time: </span>
        <span style="color:#ff6a3d;font-size:13px;font-weight:700;">{total} pages total</span>
      </div>
    </div>"""

    topics_section = ""
    if topics:
        topics_section = (
            '<div style="margin-bottom:20px;">'
            '<p style="color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:1.5px;margin:0 0 10px;">Latest Generated Topics</p>'
            '<table style="width:100%;border-collapse:collapse;background:#0f172a;'
            'border:1px solid #334155;border-radius:8px;overflow:hidden;">'
            '<thead><tr style="background:#1e293b;border-bottom:1px solid #334155;">'
            '<th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;'
            'font-weight:700;text-transform:uppercase;">Date</th>'
            '<th style="padding:8px 12px;text-align:left;color:#64748b;font-size:11px;'
            'font-weight:700;text-transform:uppercase;">Topic</th>'
            '<th style="padding:8px 12px;text-align:center;color:#64748b;font-size:11px;'
            'font-weight:700;text-transform:uppercase;">Type</th>'
            '</tr></thead>'
            f'<tbody>{topic_rows_html}</tbody></table></div>'
        )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0f1a;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:680px;margin:28px auto;background:#1e293b;border-radius:12px;
  overflow:hidden;border:1px solid #334155;box-shadow:0 8px 40px rgba(0,0,0,0.4);">

  <div style="background:linear-gradient(135deg,#0f172a 0%,#1a2744 100%);
    padding:26px 32px;border-bottom:1px solid #334155;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;">
      <div>
        <p style="color:#475569;margin:0 0 4px;font-size:11px;letter-spacing:2px;
          text-transform:uppercase;font-weight:700;">viAct Automation System</p>
        <h1 style="color:#f1f5f9;margin:0;font-size:20px;font-weight:800;">Daily Automation Report</h1>
        <p style="color:#475569;margin:5px 0 0;font-size:12px;">{run_date} &nbsp;·&nbsp; {today_weekday}</p>
      </div>
      <span style="background:{status_color}18;color:{status_color};border:1px solid {status_color}44;
        border-radius:20px;padding:5px 14px;font-size:12px;font-weight:700;
        white-space:nowrap;">{status_label}</span>
    </div>
  </div>

  <div style="padding:24px 32px;">

    <table style="width:100%;border-collapse:collapse;margin-bottom:22px;">
      <tr>
        <td style="width:25%;padding-right:6px;vertical-align:top;">
          <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;text-align:center;">
            <div style="color:#ff6a3d;font-size:30px;font-weight:800;line-height:1;">{total}</div>
            <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Total Pages</div>
          </div>
        </td>
        <td style="width:25%;padding:0 6px;vertical-align:top;">
          <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;text-align:center;">
            <div style="color:#3b82f6;font-size:30px;font-weight:800;line-height:1;">{this_week}</div>
            <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">This Week</div>
          </div>
        </td>
        <td style="width:25%;padding:0 6px;vertical-align:top;">
          <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;text-align:center;">
            <div style="color:#22c55e;font-size:30px;font-weight:800;line-height:1;">{today_new}</div>
            <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Today</div>
          </div>
        </td>
        <td style="width:25%;padding-left:6px;vertical-align:top;">
          <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:14px;text-align:center;">
            <div style="color:#a855f7;font-size:30px;font-weight:800;line-height:1;">{dedup}</div>
            <div style="color:#475569;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-top:5px;">Topics Tracked</div>
          </div>
        </td>
      </tr>
    </table>

    {improvements_section}

    {_build_partner_outreach_section(partner_stats)}

    {input_output_section}

    {topics_section}

    <div style="background:#0f172a;border:1px solid #334155;border-radius:8px;
      padding:14px 16px;margin-bottom:20px;">
      <p style="color:#64748b;font-size:11px;font-weight:700;text-transform:uppercase;
        letter-spacing:1.5px;margin:0 0 10px;">System Status</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <tr>
          <td style="padding:4px 0;color:#64748b;">Last Content Run</td>
          <td style="padding:4px 0;color:#e2e8f0;text-align:right;font-weight:600;">{last_run}</td>
        </tr>
        <tr>
          <td style="padding:4px 0;color:#64748b;">Next Scheduled Run</td>
          <td style="padding:4px 0;color:#e2e8f0;text-align:right;font-weight:600;">Monday, {next_monday} &nbsp;·&nbsp; 9:30 AM IST</td>
        </tr>
        <tr>
          <td style="padding:4px 0;color:#64748b;">Automation</td>
          <td style="padding:4px 0;color:#22c55e;text-align:right;font-weight:700;">LIVE &nbsp;·&nbsp; GitHub Actions (zero manual input)</td>
        </tr>
        <tr>
          <td style="padding:4px 0;color:#64748b;">Anti-hallucination</td>
          <td style="padding:4px 0;color:#e2e8f0;text-align:right;font-weight:600;">Tavily live-search + Firecrawl verified</td>
        </tr>
      </table>
    </div>

    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <td style="padding-right:6px;">
          <a href="{sheet_url}" style="display:block;background:#ff6a3d;color:#fff;
            padding:12px 0;border-radius:7px;text-decoration:none;font-size:13px;
            font-weight:700;text-align:center;">View Output in Google Sheets &rarr;</a>
        </td>
        <td style="padding-left:6px;">
          <a href="{dashboard_url}" style="display:block;background:#1e293b;color:#94a3b8;
            padding:12px 0;border-radius:7px;text-decoration:none;font-size:13px;
            font-weight:600;text-align:center;border:1px solid #334155;">Open Live Dashboard &rarr;</a>
        </td>
      </tr>
    </table>

  </div>

  <div style="padding:14px 32px;border-top:1px solid #334155;background:#0a0f1a;">
    <p style="font-size:11px;color:#334155;margin:0;text-align:center;">
      Sent by Aditya Meshram &nbsp;·&nbsp; viAct Automation System &nbsp;·&nbsp;
      Tavily + Firecrawl + Groq / Llama 3.3
    </p>
  </div>
</div>
</body>
</html>"""

    # Partner Outreach text section
    p = partner_stats or {}
    partner_text = ""
    if p.get("total_partners", 0) > 0:
        top_lines = "\n".join(
            f"    {t['tab']:20} {t['partners']:3} partners  {t['emails']:3} emails ({t['coverage']}%)"
            for t in p.get("top_tabs", [])
        )
        today_partner_line = ""
        if p.get("today_new_partners", 0) > 0:
            today_partner_line = (
                f"  Today ({p.get('today_tab','—')}): "
                f"{p['today_new_partners']} partners, {p['today_new_emails']} emails\n"
            )
        partner_text = (
            f"\nPARTNER OUTREACH (Agent 11):\n"
            f"  Partners: {p['total_partners']} | Emails: {p['total_emails']} "
            f"| Phones: {p['total_phones']} | Coverage: {p['coverage_pct']}%\n"
            f"  Tracked competitors: {p['comp_track']}/{p['comp_total']} | Tabs: {p['total_tabs']}\n"
            f"{today_partner_line}"
            f"  Top tabs:\n{top_lines}\n"
        )

    text_body = (
        f"viAct Automation — Daily Report\n{run_date}\n{'='*60}\n\n"
        f"METRICS:\n"
        f"  Total Pages    : {total}\n"
        f"  This Week      : {this_week} ({pillar_cnt} pillar + {blog_cnt} blog)\n"
        f"  Today          : {today_new}\n"
        f"  Topics Tracked : {dedup}\n"
        f"{partner_text}\n"
        f"{improvements_text}"
        f"INPUT: 8 competitors, viAct sitemap, 5 regulatory sources, Reference Library\n"
        f"OUTPUT: 1 pillar + 3 blogs + SEO meta + internal links → auto-pushed to Sheets\n\n"
        f"LATEST TOPICS:\n{topic_rows_text}\n"
        f"Last run: {last_run} | Next Monday run: {next_monday} 9:30 AM IST\n\n"
        f"Sheet: {sheet_url}\nDashboard: {dashboard_url}\n"
    )

    return html_body, text_body


# ── 4. Send via Resend ────────────────────────────────────────────────────────
def send_daily_report() -> bool:
    api_key = _env("RESEND_API_KEY")
    if not api_key:
        log("RESEND_API_KEY not set — add to GitHub Secrets.")
        return False

    today_str = datetime.date.today().strftime("%d %b %Y")
    subject   = f"viAct Automation Daily Report — {today_str}"

    log("Reading Sheets data...")
    data = _get_sheets_data() or {}
    log(f"  Total: {data.get('total_pages', 0)} pages | This week: {data.get('this_week_pages', 0)}")

    log("Reading Partner Outreach data (Agent 11)...")
    partner_stats = _get_partner_outreach_stats() or {}
    log(f"  Partners: {partner_stats.get('total_partners', 0)} | Emails: {partner_stats.get('total_emails', 0)}")

    log("Reading today's git commits...")
    commits = _get_todays_commits()
    log(f"  {len(commits)} commit(s) today")

    html_body, text_body = _build_email(data, commits, partner_stats)

    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "from":    RESEND_FROM,
                "to":      [SHOYAB_EMAIL],  # TEST — switch to [GARY_EMAIL, SURENDRA_EMAIL] after approval
                "cc":      [ADITYA_EMAIL],
                "subject": subject,
                "html":    html_body,
                "text":    text_body,
            },
            timeout=15,
        )
        resp.raise_for_status()
        log(f"Test report sent → Shoyab ({SHOYAB_EMAIL}), CC: Aditya (Gary/Surendra pending approval)")
        log(f"Resend ID: {resp.json().get('id', '?')}")
        return True
    except Exception as exc:
        log(f"Send failed: {exc}")
        return False


if __name__ == "__main__":
    log("=== viAct Daily Automation Report ===")
    ok = send_daily_report()
    sys.exit(0 if ok else 1)
