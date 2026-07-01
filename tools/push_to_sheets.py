"""Append generated content rows to a Google Sheet.

Authentication priority:
  1. Service Account via GCP_SERVICE_ACCOUNT env var (JSON string) — used on Streamlit Cloud + GitHub Actions
  2. OAuth token.json — used for local development only

To set up service account (one-time):
  - Google Cloud Console → IAM → Service Accounts → Create → Download JSON key
  - Share your Google Sheet with the service account's client_email (Editor role)
  - Add the full JSON as GCP_SERVICE_ACCOUNT in st.secrets / GitHub Secrets
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

def _service_account_creds():
    """Build service account credentials from GCP_SERVICE_ACCOUNT env var (JSON string or dict)."""
    from google.oauth2 import service_account

    raw = os.getenv("GCP_SERVICE_ACCOUNT", "")
    if not raw:
        return None
    try:
        sa_info = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    return service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)


def get_sheets_service():
    """Return an authenticated Google Sheets API service object.

    Prefers service account (headless). Falls back to OAuth token for local dev.
    """
    from googleapiclient.discovery import build

    # ── Service account (Streamlit Cloud / GitHub Actions) ────────────────────
    creds = _service_account_creds()
    if creds:
        return build("sheets", "v4", credentials=creds)

    # ── OAuth fallback (local development only) ───────────────────────────────
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    oauth_creds = None
    if os.path.exists(TOKEN_PATH):
        oauth_creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not oauth_creds or not oauth_creds.valid:
        if oauth_creds and oauth_creds.expired and oauth_creds.refresh_token:
            oauth_creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            oauth_creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(oauth_creds.to_json())

    return build("sheets", "v4", credentials=oauth_creds)


# ---------------------------------------------------------------------------
# Webpage Content pipeline — separate tab, separate schema
# ---------------------------------------------------------------------------

WEBPAGE_TAB = "Webpage Content"
WEBPAGE_COLUMNS = [
    "Date",               # A
    "Autorun#",           # B
    "Topic",              # C
    "Decision Logic",     # D — copy to Gary/Surendra's email
    "Webpage Body",       # E — full Markdown
    "SEO Suite (JSON)",   # F — meta title, desc, keywords
    "Schema FAQs (JSON)", # G — 5-item JSON array
    "Schema JSON-LD",     # H — paste into <head>
    "Extended FAQs (JSON)",  # I — 2 on-page only
    "GEO Package (JSON)", # J — opening 200 words + tips
    "Visual Strategy (JSON)", # K — Nano Banana prompts
    "Internal Links (JSON)",  # L
    "Competitor URLs",    # M
    "Input Source",       # N
    "Unverified",         # O — "Yes" if no reference provided
    "Status",             # P
]


def ensure_webpage_tab(service, sheet_id: str):
    """Create the 'Webpage Content' tab if absent and write the header row."""
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

    if WEBPAGE_TAB not in existing_titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": WEBPAGE_TAB}}}]},
        ).execute()

    # Write header row (overwrite if different)
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{WEBPAGE_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [WEBPAGE_COLUMNS]},
    ).execute()


def push_webpage(
    content: dict,
    decision_logic: str = "",
    input_source: str = "",
    competitor_urls: list[str] | None = None,
    autorun_num: int | None = None,
    unverified: bool = False,
) -> int:
    """
    Append one row to the 'Webpage Content' tab.
    Returns 1 if successful.
    """
    sheet_id = get_env("SHEET_ID")
    service = get_sheets_service()
    ensure_webpage_tab(service, sheet_id)

    # Auto-increment autorun# if not passed
    if autorun_num is None:
        existing = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{WEBPAGE_TAB}!A:A",
        ).execute()
        autorun_num = max(len(existing.get("values", [])), 1)

    seo = content.get("seo_suite", {})
    row = [
        date.today().isoformat(),
        str(autorun_num),
        content.get("topic", ""),
        decision_logic or content.get("decision_logic", ""),
        content.get("webpage_body", ""),
        json.dumps(seo, ensure_ascii=False),
        json.dumps(content.get("schema_faqs", []), ensure_ascii=False),
        content.get("schema_json_ld", "") if isinstance(content.get("schema_json_ld", ""), str) else json.dumps(content.get("schema_json_ld", {}), ensure_ascii=False),
        json.dumps(content.get("extended_faqs", []), ensure_ascii=False),
        json.dumps(content.get("geo_package", {}), ensure_ascii=False),
        json.dumps(content.get("nano_banana_prompts", content.get("visual_strategy", [])), ensure_ascii=False),
        json.dumps(content.get("internal_links", []), ensure_ascii=False),
        ", ".join(competitor_urls or []),
        input_source,
        "Yes" if unverified else "No",
        "Draft",
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{WEBPAGE_TAB}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    return 1


# ── Industry Pages — one dedicated tab per industry ──────────────────────────
INDUSTRY_PAGE_COLUMNS = [
    "Date",                    # A
    "Hero Subheadline",        # B
    "Hero Body Copy",          # C
    "Impact Section Title",    # D
    "Impact Subtitle",         # E
    "Metric 1 Label",          # F
    "Metric 1 Description",    # G
    "Metric 2 Label",          # H
    "Metric 2 Description",    # I
    "Metric 3 Label",          # J
    "Metric 3 Description",    # K
    "Use Cases Section Title",  # L
    "UC1 Title",               # M
    "UC1 Description",         # N
    "UC2 Title",               # O
    "UC2 Description",         # P
    "UC3 Title",               # Q
    "UC3 Description",         # R
    "UC4 Title",               # S
    "UC4 Description",         # T
    "UC5 Title",               # U
    "UC5 Description",         # V
    "UC6 Title",               # W
    "UC6 Description",         # X
    "Solutions Description",   # Y
    "viGent Description",      # Z
    "T1 Quote",                # AA
    "T1 Source",               # AB
    "T2 Quote",                # AC
    "T2 Source",               # AD
    "T3 Quote",                # AE
    "T3 Source",               # AF
    "T4 Quote",                # AG
    "T4 Source",               # AH
    "T5 Quote",                # AI
    "T5 Source",               # AJ
    "CTA Headline",            # AK
    "CTA Description",         # AL
    "Meta Title",              # AM
    "Meta Description",        # AN
    "Canonical Slug",          # AO
    "Webpage Body",            # AP
    "Image Prompts (JSON)",    # AQ
    "Status",                  # AR
]


def _ensure_industry_tab(service, sheet_id: str, tab_name: str) -> None:
    """Create the industry-specific tab if it doesn't exist and write the header."""
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [INDUSTRY_PAGE_COLUMNS]},
    ).execute()


def push_industry_page(content: dict, industry_name: str) -> int:
    """
    Append one row to a dedicated industry tab (created if absent).
    Tab name = industry_name, e.g. "Mining Safety", "Oil & Gas Safety".
    Each CMS field gets its own column for easy copy-paste.
    Returns 1 on success.
    """
    sheet_id = get_env("SHEET_ID")
    service = get_sheets_service()
    tab_name = industry_name.strip()
    _ensure_industry_tab(service, sheet_id, tab_name)

    cms = content.get("industry_cms_fields", {})
    metrics = cms.get("metrics", [{}, {}, {}])
    use_cases = cms.get("use_cases", [{} for _ in range(6)])
    testimonials = cms.get("testimonials", [{} for _ in range(5)])
    seo = content.get("seo_suite", {})

    def _m(lst, i, key):
        try:
            return lst[i].get(key, "")
        except IndexError:
            return ""

    row = [
        date.today().isoformat(),
        cms.get("hero_subheadline", ""),
        cms.get("hero_body_copy", ""),
        cms.get("impact_section_title", ""),
        cms.get("impact_subtitle", ""),
        _m(metrics, 0, "label"),
        _m(metrics, 0, "description"),
        _m(metrics, 1, "label"),
        _m(metrics, 1, "description"),
        _m(metrics, 2, "label"),
        _m(metrics, 2, "description"),
        cms.get("use_cases_section_title", ""),
        _m(use_cases, 0, "title"), _m(use_cases, 0, "description"),
        _m(use_cases, 1, "title"), _m(use_cases, 1, "description"),
        _m(use_cases, 2, "title"), _m(use_cases, 2, "description"),
        _m(use_cases, 3, "title"), _m(use_cases, 3, "description"),
        _m(use_cases, 4, "title"), _m(use_cases, 4, "description"),
        _m(use_cases, 5, "title"), _m(use_cases, 5, "description"),
        cms.get("solutions_description", ""),
        cms.get("vigent_description", ""),
        _m(testimonials, 0, "quote"), _m(testimonials, 0, "source"),
        _m(testimonials, 1, "quote"), _m(testimonials, 1, "source"),
        _m(testimonials, 2, "quote"), _m(testimonials, 2, "source"),
        _m(testimonials, 3, "quote"), _m(testimonials, 3, "source"),
        _m(testimonials, 4, "quote"), _m(testimonials, 4, "source"),
        cms.get("cta_headline", ""),
        cms.get("cta_description", ""),
        seo.get("meta_title", ""),
        seo.get("meta_description", ""),
        seo.get("canonical_url_slug", ""),
        content.get("webpage_body", ""),
        json.dumps(content.get("nano_banana_prompts", []), ensure_ascii=False),
        "Draft",
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    return 1


# ── Webpage Content — VERTICAL format ────────────────────────────────────────────
WEBPAGE_VERTICAL_TAB = "Webpage Content"   # fixed tab for all market radar pushes

def push_webpage_vertical(
    content: dict,
    decision_logic: str = "",
    input_source: str = "",
    competitor_urls: list | None = None,
    unverified: bool = False,
    tab_name: str | None = None,
) -> int:
    """
    Append one content block vertically to a named tab.
    tab_name defaults to WEBPAGE_VERTICAL_TAB ("Webpage Content").
    Pass tab_name=date.today().isoformat() for date-based tabs.
    Field name in col A, value in col B. Section headers = blue background.
    Multiple topics pushed on the same day are stacked in the same tab with a spacer.
    Returns 1 on success.
    """
    sheet_id = get_env("SHEET_ID")
    service = get_sheets_service()
    tab_name = tab_name or WEBPAGE_VERTICAL_TAB

    # Create tab if it doesn't exist yet
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()

    # Find the next empty row (so multiple topics stack in the same day-tab)
    existing_vals = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab_name}'!A:A"
    ).execute()
    start_row = len(existing_vals.get("values", [])) + 1   # 1-based

    seo   = content.get("seo_suite", {}) or {}
    hero  = content.get("hero_section", {}) or {}
    faqs  = content.get("schema_faqs", []) or []
    efaqs = content.get("extended_faqs", []) or []
    geo   = content.get("geo_package", {}) or {}
    nano  = content.get("nano_banana_prompts", content.get("visual_strategy", [])) or []
    links = content.get("internal_links", []) or []

    rows = []
    section_rows  = []   # 0-based within this block (for blue formatting)
    topic_rows    = []   # topic header row index (for orange formatting)

    def sec(title):
        section_rows.append(len(rows))
        rows.append([title, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # ── Topic header ─────────────────────────────────────────────────────────────
    topic_rows.append(len(rows))
    rows.append([f"TOPIC: {content.get('topic', input_source)}", ""])
    f("Input Source",  input_source or "Manual")
    f("Date",          date.today().isoformat())
    f("Unverified",    "Yes" if unverified else "No")
    f("Competitor URLs", ", ".join(competitor_urls or []))
    blank()

    # ── SEO & Meta ───────────────────────────────────────────────────────────────
    sec("SEO & META")
    f("Meta Title",         seo.get("meta_title", ""))
    f("Meta Description",   seo.get("meta_description", ""))
    f("Primary Keyword",    seo.get("primary_keyword", ""))
    f("Secondary Keywords", ", ".join(seo.get("secondary_keywords", [])))
    f("LSI Keywords",       ", ".join(seo.get("lsi_keywords", [])))
    f("Canonical Slug",     seo.get("canonical_url_slug", ""))
    blank()

    # ── Hero Section ─────────────────────────────────────────────────────────────
    sec("HERO SECTION")
    f("H1",           hero.get("h1", ""))
    f("Subheadline",  hero.get("subheadline", ""))
    f("CTA Text",     hero.get("cta_text", ""))
    f("CTA URL",      hero.get("cta_url", ""))
    blank()

    # ── Problem Statement ────────────────────────────────────────────────────────
    sec("PROBLEM STATEMENT")
    f("Problem Statement", content.get("problem_statement", ""))
    blank()

    # ── Webpage Body ─────────────────────────────────────────────────────────────
    sec("WEBPAGE BODY (H-tagged Markdown)")
    f("Webpage Body", content.get("webpage_body", ""))
    blank()

    # ── Schema FAQs ──────────────────────────────────────────────────────────────
    sec("SCHEMA FAQs (5 items — paste into FAQ schema)")
    for i, faq in enumerate(faqs[:5], 1):
        f(f"FAQ {i} Question", faq.get("question", "") if isinstance(faq, dict) else "")
        f(f"FAQ {i} Answer",   faq.get("answer", "")   if isinstance(faq, dict) else str(faq))
    blank()

    # ── Extended FAQs ────────────────────────────────────────────────────────────
    sec("EXTENDED FAQs (on-page only)")
    for i, faq in enumerate(efaqs[:3], 1):
        f(f"Extended FAQ {i} Question", faq.get("question", "") if isinstance(faq, dict) else "")
        f(f"Extended FAQ {i} Answer",   faq.get("answer", "")   if isinstance(faq, dict) else str(faq))
    blank()

    # ── Schema JSON-LD ───────────────────────────────────────────────────────────
    sec("SCHEMA JSON-LD (paste into <head>)")
    jld = content.get("schema_json_ld", "")
    f("Schema JSON-LD", jld if isinstance(jld, str) else json.dumps(jld, ensure_ascii=False))
    blank()

    # ── GEO Package ──────────────────────────────────────────────────────────────
    sec("GEO PACKAGE")
    f("Opening 200 Words",     geo.get("opening_200_words", ""))
    for i, tip in enumerate(geo.get("citation_framing_tips", [])[:3], 1):
        f(f"Citation Tip {i}", tip)
    blank()

    # ── Image Prompts ────────────────────────────────────────────────────────────
    sec("IMAGE PROMPTS (Nano Banana)")
    for i, img in enumerate(nano, 1):
        if isinstance(img, dict):
            f(f"Image {i} Placement", img.get("placement", ""))
            f(f"Image {i} Prompt",    img.get("prompt", ""))
            f(f"Image {i} Alt Text",  img.get("alt_text", ""))
        else:
            f(f"Image {i}", str(img))
    blank()

    # ── Internal Links ───────────────────────────────────────────────────────────
    sec("INTERNAL LINKS")
    for i, lnk in enumerate(links[:10], 1):
        if isinstance(lnk, dict):
            f(f"Link {i} Anchor",  lnk.get("anchor_text", ""))
            f(f"Link {i} URL",     lnk.get("url", ""))
            f(f"Link {i} Context", lnk.get("context", ""))
    blank()

    # ── Decision Logic ───────────────────────────────────────────────────────────
    sec("DECISION LOGIC (for email to Gary / Surendra)")
    f("Decision Logic", decision_logic or content.get("decision_logic", ""))

    # Fetch sheet metadata (needed for gid + row count check)
    meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )
    current_rows = next(
        s["properties"]["gridProperties"]["rowCount"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )
    # Expand sheet rows if needed before writing
    end_row_needed = start_row + len(rows)
    if end_row_needed > current_rows:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"appendDimension": {
                "sheetId": sheet_gid,
                "dimension": "ROWS",
                "length": end_row_needed - current_rows + 1000,
            }}]},
        ).execute()

    # Write rows
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A{start_row}",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Apply formatting (sheet_gid already fetched above)

    offset = start_row - 1   # convert to 0-based
    fmt_reqs = []

    # Blue section headers
    for ri in section_rows:
        fmt_reqs.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_gid,
                    "startRowIndex": offset + ri,
                    "endRowIndex":   offset + ri + 1,
                    "startColumnIndex": 0, "endColumnIndex": 2,
                },
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.643, "green": 0.761, "blue": 0.957},
                    "textFormat": {"bold": True, "fontSize": 10},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

    # Orange topic header
    for ri in topic_rows:
        fmt_reqs.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_gid,
                    "startRowIndex": offset + ri,
                    "endRowIndex":   offset + ri + 1,
                    "startColumnIndex": 0, "endColumnIndex": 2,
                },
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 1.0, "green": 0.6, "blue": 0.2},
                    "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

    # Column widths (only set on first topic in tab — start_row == 1)
    if start_row == 1:
        fmt_reqs += [
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 240},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                    "properties": {"pixelSize": 700},
                    "fields": "pixelSize",
                }
            },
        ]

    if fmt_reqs:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": fmt_reqs},
        ).execute()

    return 1


# ── Industry Pages — VERTICAL format (field: value rows, green section headers) ─
def push_industry_page_vertical(content: dict, industry_name: str, sheet_id: str = "") -> int:
    """sheet_id defaults to INDUSTRY_SHEET_ID env var, falls back to SHEET_ID."""
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")
    """
    Write industry page content vertically: field name in col A, value in col B.
    Section headers get green background (#b7e1cc) and bold text.
    Each run clears and rewrites the tab so it stays fresh.
    Returns 1 on success.
    """
    service = get_sheets_service()
    tab_name = industry_name.strip()

    # Create tab or clear existing
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
    else:
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A:B",
        ).execute()

    cms = content.get("industry_cms_fields", {})
    metrics    = cms.get("metrics",     [{}, {}, {}])
    use_cases  = cms.get("use_cases",   [{} for _ in range(6)])
    testimonials = cms.get("testimonials", [{} for _ in range(5)])
    seo  = content.get("seo_suite", {})
    nano = content.get("nano_banana_prompts", [])

    def _g(lst, i, key):
        try:
            return str(lst[i].get(key, "") or "")
        except IndexError:
            return ""

    rows = []          # list of [col_A, col_B]
    section_rows = []  # 0-based row indices that are section headers

    def sec(title):
        section_rows.append(len(rows))
        rows.append([title, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # ── SEO & Meta ──────────────────────────────────────────────────────────────
    sec("SEO & META")
    f("Meta Title",          seo.get("meta_title", ""))
    f("Meta Description",    seo.get("meta_description", ""))
    f("Primary Keyword",     seo.get("primary_keyword", ""))
    f("Secondary Keywords",  ", ".join(seo.get("secondary_keywords", [])))
    f("Canonical URL Slug",  seo.get("canonical_url_slug", ""))
    blank()

    # ── Hero Section ─────────────────────────────────────────────────────────────
    sec("1st Section - Hero")
    f("H1 Eyebrow",               f"AI for Safety & Productivity in {industry_name}")
    f("Hero Subheadline [H2]",    cms.get("hero_subheadline", ""))
    f("Hero Body Copy [H3]",      cms.get("hero_body_copy", ""))
    blank()

    # ── Proven Impact ────────────────────────────────────────────────────────────
    sec("2nd Section - Proven Impact")
    f("Impact Section Title",  cms.get("impact_section_title", ""))
    f("Impact Subtitle",       cms.get("impact_subtitle", ""))
    for i in range(3):
        f(f"Metric {i+1} Label",       _g(metrics, i, "label"))
        f(f"Metric {i+1} Description", _g(metrics, i, "description"))
    blank()

    # ── AI CCTV Use Cases ────────────────────────────────────────────────────────
    sec("3rd Section - AI CCTV Use Cases")
    f("Use Cases Section Title",  cms.get("use_cases_section_title", ""))
    for i in range(6):
        f(f"Use Case {i+1} Title [H3]", _g(use_cases, i, "title"))
        f(f"Use Case {i+1} Description", _g(use_cases, i, "description"))
        f(f"Use Case {i+1} Image Prompt", _g(nano, i, "prompt"))
        f(f"Use Case {i+1} Alt Text",    _g(nano, i, "alt_text"))
    blank()

    # ── Pre-Built Solutions ───────────────────────────────────────────────────────
    sec("4th Section - Pre-Built Solutions")
    f("Solutions Description", cms.get("solutions_description", ""))
    blank()

    # ── viGent (nano index 6) ────────────────────────────────────────────────────
    sec("5th Section - viGent AI Agent")
    f("viGent Description",   cms.get("vigent_description", ""))
    f("viGent Image Prompt",  _g(nano, 6, "prompt"))
    f("viGent Image Alt Text", _g(nano, 6, "alt_text"))
    blank()

    # ── Voices from the Field — Testimonials (nano headshots: indices 7-10) ──────
    sec("6th Section - Voices from the Field")
    for i in range(5):
        f(f"Testimonial {i+1} Quote",  _g(testimonials, i, "quote"))
        f(f"Testimonial {i+1} Source", _g(testimonials, i, "source"))
        if i < 4:
            f(f"Reviewer {i+1} Image Prompt",  _g(nano, 7 + i, "prompt"))
            f(f"Reviewer {i+1} Alt Text",       _g(nano, 7 + i, "alt_text"))
        blank()

    # ── CTA ───────────────────────────────────────────────────────────────────────
    sec("7th Section - CTA")
    f("CTA Headline",     cms.get("cta_headline", ""))
    f("CTA Description",  cms.get("cta_description", ""))
    blank()

    # ── Full Webpage Body ──────────────────────────────────────────────────────────
    sec("Full Webpage Body (H-tagged Markdown)")
    f("Webpage Body", content.get("webpage_body", ""))

    # Write all rows in one call
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Get the numeric sheetId for formatting
    meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )

    fmt_requests = []
    # Green background + bold for section header rows
    for row_idx in section_rows:
        fmt_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_gid,
                    "startRowIndex": row_idx,
                    "endRowIndex": row_idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.718, "green": 0.882, "blue": 0.804},
                        "textFormat": {"bold": True, "fontSize": 10},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })
    # Column widths: A=260px, B=650px
    fmt_requests += [
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 260},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 650},
                "fields": "pixelSize",
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": fmt_requests},
    ).execute()
    return 1


# ── Universal Builder — dynamic push, one tab per page type ──────────────────

def push_dynamic_page(result: dict, sheet_id: str = "") -> int:
    """
    Push Universal Builder output to a tab named after result["page_type"].
    - Creates tab if missing.
    - Appends a new block of rows per run (INSERT_ROWS) — all topics accumulate.
    - Separator row between pages.
    - Metadata header rows (Topic, Generated, Status) get blue-grey background.
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service  = get_sheets_service()
    tab_name = result.get("page_type", "Dynamic Pages").strip()
    topic    = result.get("page_topic", "")
    ts       = result.get("generation_meta", {}).get("timestamp", "")[:19].replace("T", " ")
    cms      = result.get("cms_fields", {})
    errors   = result.get("quality_gate_errors", [])

    # Create tab if missing
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()

    rows = []
    header_rows = []  # row indices (0-based within this batch) that get colored

    def sec(label):
        header_rows.append(len(rows))
        rows.append([label, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # Separator between pages (skip on very first append — handled by empty tab)
    rows.append(["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""])

    # ── Page metadata ─────────────────────────────────────────────────────────
    sec(f"📄 {topic}")
    f("Topic",     topic)
    f("Generated", ts + " UTC")
    f("Status",    "Draft")
    blank()

    # ── CMS fields ───────────────────────────────────────────────────────────
    sec("CMS Fields")
    _skip = {"data_sources_used", "access_denied_urls"}
    for key, val in cms.items():
        if key in _skip:
            continue
        if isinstance(val, list):
            if val and isinstance(val[0], dict):
                for i, item in enumerate(val, 1):
                    for sub_k, sub_v in item.items():
                        f(f"{key}[{i}].{sub_k}", sub_v)
            else:
                f(key, " | ".join(str(v) for v in val))
        else:
            f(key, val)
    blank()

    # ── SEO ───────────────────────────────────────────────────────────────────
    if cms.get("meta_title") or cms.get("meta_description"):
        sec("SEO")
        if cms.get("meta_title"):
            f("Meta Title",       cms["meta_title"])
        if cms.get("meta_description"):
            f("Meta Description", cms["meta_description"])
        blank()

    # ── Sources ───────────────────────────────────────────────────────────────
    sources = cms.get("data_sources_used", [])
    if sources:
        sec("Sources Used")
        for s in sources:
            f("Source", s)
        blank()

    # ── Quality gate errors (if any) ─────────────────────────────────────────
    if errors:
        sec("⚠️ Quality Gate Warnings")
        for e in errors:
            f("Warning", e)
        blank()

    # Append rows
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    # Get current row count to calculate absolute row indices for formatting
    sheet_data = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A:A",
    ).execute()
    total_rows = len(sheet_data.get("values", []))
    batch_start = total_rows - len(rows)  # first row of this batch (0-based)

    # Get numeric sheetId for formatting
    meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )

    fmt_requests = []
    # Blue-grey (#cfe2f3) + bold for section header rows
    for local_idx in header_rows:
        abs_idx = batch_start + local_idx
        fmt_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_gid,
                    "startRowIndex": abs_idx,
                    "endRowIndex": abs_idx + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.812, "green": 0.886, "blue": 0.953},
                        "textFormat": {"bold": True, "fontSize": 10},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

    # Column widths (only set once — repeated calls are idempotent)
    fmt_requests += [
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 260},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 650},
                "fields": "pixelSize",
            }
        },
    ]

    if fmt_requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": fmt_requests},
        ).execute()

    return 1


# ── Case Study Builder — vertical field:value rows, one tab per company ──────

def push_case_study(result: dict, sheet_id: str = "") -> int:
    """
    Push case study content to a tab named after the company in INDUSTRY_SHEET_ID.
    Layout: field name in col A, value in col B (same pattern as industry pages).
    Creates tab if missing; clears and rewrites on each run (latest version always fresh).
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service  = get_sheets_service()
    cms      = result.get("cms_fields", {})
    meta     = result.get("generation_meta", {})
    errors   = result.get("quality_gate_errors", [])
    company  = cms.get("company_name", meta.get("company", "Case Study")).strip()
    tab_name = f"CS — {company}"[:100]   # tab name prefix so it's easy to spot

    # Create tab or clear existing
    sheet_meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing   = [s["properties"]["title"] for s in sheet_meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
    else:
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range=f"'{tab_name}'!A:B",
        ).execute()

    rows: list[list] = []
    section_rows: list[int] = []

    def sec(title):
        section_rows.append(len(rows))
        rows.append([title, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # ── Meta ─────────────────────────────────────────────────────────────────
    sec("META")
    f("Generated",    meta.get("timestamp", "")[:19].replace("T", " ") + " UTC")
    f("Status",       "Draft")
    f("Model",        meta.get("model_used", ""))
    f("Retry Count",  str(meta.get("retry_count", 0)))
    blank()

    # ── Company Info ─────────────────────────────────────────────────────────
    sec("COMPANY INFO")
    f("Company Name",     cms.get("company_name", ""))
    f("Industry",         cms.get("industry", ""))
    f("Location",         cms.get("location", ""))
    f("Company Size",     cms.get("company_size", ""))
    f("Company Type",     cms.get("company_type", ""))
    f("Products Used",    ", ".join(cms.get("products_used", [])) if isinstance(cms.get("products_used"), list) else str(cms.get("products_used", "")))
    f("Company Overview", cms.get("company_overview", ""))
    f("Story Snapshot",   cms.get("story_snapshot", ""))
    f("Use Case",         cms.get("use_case", ""))
    blank()

    # ── Hero ─────────────────────────────────────────────────────────────────
    sec("HERO")
    f("h1",               cms.get("hero_h1", ""))
    f("h2",               cms.get("h2", ""))
    f("h3 Intro",         cms.get("h3", ""))
    f("Hero Image Brief",     cms.get("hero_image_brief", ""))
    f("Hero Alt Text",        cms.get("hero_alt_text", ""))
    f("Overview Image Brief", cms.get("overview_image_brief", ""))
    blank()

    # ── Key Metrics ──────────────────────────────────────────────────────────
    sec("KEY METRICS")
    for i in (1, 2, 3):
        f(f"Metric {i} Value",       cms.get(f"metric_{i}_value", ""))
        f(f"Metric {i} Label",       cms.get(f"metric_{i}_label", ""))
        f(f"Metric {i} Description", cms.get(f"metric_{i}_description", ""))
        f(f"Metric {i} Alt Text",    cms.get(f"metric_{i}_alt_text", ""))
    blank()

    # ── Challenge ────────────────────────────────────────────────────────────
    sec("THE CHALLENGE")
    f("Challenge Title", cms.get("challenge_title", ""))
    f("Challenge Body",  cms.get("challenge_body", ""))
    blank()

    # ── Solution ─────────────────────────────────────────────────────────────
    sec("THE SOLUTION")
    f("Solution Title",     cms.get("solution_title", ""))
    f("Solution Body",      cms.get("solution_body", ""))
    f("Sub1 Title",          cms.get("solution_sub1_title", ""))
    f("Sub1 Body",           cms.get("solution_sub1_body", ""))
    f("Sub1 Image Brief",    cms.get("solution_1_image_brief", ""))
    f("Sub1 Alt Text",       cms.get("solution_1_alt_text", ""))
    f("Sub2 Title",          cms.get("solution_sub2_title", ""))
    f("Sub2 Body",           cms.get("solution_sub2_body", ""))
    f("Sub2 Image Brief",    cms.get("solution_2_image_brief", ""))
    f("Sub2 Alt Text",       cms.get("solution_2_alt_text", ""))
    blank()

    # ── Impact ───────────────────────────────────────────────────────────────
    sec("THE IMPACT")
    f("Impact Title", cms.get("impact_title", ""))
    f("Impact Body",  cms.get("impact_body", ""))
    blank()

    # ── Testimonials ─────────────────────────────────────────────────────────
    sec("TESTIMONIALS")
    for i in (1, 2):
        f(f"Testimonial {i} Quote",   cms.get(f"testimonial_{i}_quote", ""))
        f(f"Testimonial {i} Role",    cms.get(f"testimonial_{i}_role", ""))
        f(f"Testimonial {i} Company", cms.get(f"testimonial_{i}_company", ""))
    f("Testimonial Image Brief",  cms.get("testimonial_image_brief", ""))
    f("Company Logo Alt Text",    cms.get("company_logo_alt_text", ""))
    f("Profile Image Alt Text",   cms.get("profile_image_alt_text", ""))
    blank()

    # ── CTA & SEO ────────────────────────────────────────────────────────────
    sec("CTA & SEO")
    f("CTA Headline",          cms.get("cta_headline", ""))
    f("Meta Title",            cms.get("meta_title", ""))
    f("Meta Description",      cms.get("meta_description", ""))
    f("URL Slug",              cms.get("slug", ""))
    f("URL (Full)",            cms.get("url", ""))
    f("Tags",                  ", ".join(cms.get("tags", [])) if isinstance(cms.get("tags"), list) else str(cms.get("tags", "")))
    f("Filter Tag",            cms.get("filter_tag", ""))
    f("Keywords",              cms.get("keywords", ""))
    f("List Page Description", cms.get("list_page_description", ""))
    blank()

    # ── Alt Texts ────────────────────────────────────────────────────────────
    sec("ALT TEXTS")
    f("Company Overview Alt Text", cms.get("section_alt_text", ""))
    f("Industry Alt Text",         cms.get("industry_alt_text", ""))
    f("Location Alt Text",         cms.get("location_alt_text", ""))
    f("Use Case Alt Text",         cms.get("use_case_alt_text", ""))
    blank()

    # ── Quality Gate ─────────────────────────────────────────────────────────
    if errors:
        sec("⚠️ QUALITY GATE WARNINGS")
        for e in errors:
            f("Warning", e)
        blank()

    # Write rows
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Format: green section headers + column widths
    meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )
    fmt_requests = []
    for row_idx in section_rows:
        fmt_requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_gid, "startRowIndex": row_idx,
                           "endRowIndex": row_idx + 1, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.718, "green": 0.882, "blue": 0.804},
                    "textFormat": {"bold": True, "fontSize": 10},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })
    fmt_requests += [
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 220}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 700}, "fields": "pixelSize",
        }},
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": fmt_requests},
    ).execute()
    return 1


# ── Opportunity Scanner — horizontal rows in "Opportunities" tab ──────────────

def push_opportunities(opportunities: list[dict], sheet_id: str = "") -> int:
    """
    Append ranked opportunities to "Opportunities" tab in INDUSTRY_SHEET_ID.
    Creates the tab + header row on first call.
    Each opportunity = 1 row: Date | Page Type | Topic | Score | Gap Type | Why Build | Evidence | Status
    Returns count of rows appended.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    if not opportunities:
        return 0

    service  = get_sheets_service()
    tab_name = "Opportunities"
    header   = ["Date", "Page Type", "Topic", "Score", "Gap Type", "Why Build",
                "Competitor Evidence", "Status"]

    # Create tab if missing; write header row on first create
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [header]},
        ).execute()

        # Bold + blue-grey header
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        tab_gid = next(
            s["properties"]["sheetId"]
            for s in meta2["sheets"]
            if s["properties"]["title"] == tab_name
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": tab_gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(header)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.812, "green": 0.886, "blue": 0.953},
                        "textFormat": {"bold": True, "fontSize": 10},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()

    # Build rows from opportunities
    rows = []
    for opp in opportunities:
        evidence_str = "; ".join(
            f"{e['name']}: {e['url']}" for e in opp.get("competitor_evidence", [])
        )
        rows.append([
            opp.get("scan_date", ""),
            opp.get("page_type", ""),
            opp.get("topic", ""),
            str(opp.get("score", 0)),
            opp.get("gap_type", "MISSING"),
            opp.get("why_build", ""),
            evidence_str,
            "New",
        ])

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)


# ── Reference Library tab — persistent user-provided reference material ──────
REFERENCE_TAB = "Reference_Library"
REF_COLUMNS = ["Type", "Topic Filter", "Reference Text", "Added At"]


def ensure_reference_tab(service, sheet_id: str) -> None:
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if REFERENCE_TAB not in existing_titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": REFERENCE_TAB}}}]},
        ).execute()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{REFERENCE_TAB}!A1:D1"
    ).execute()
    if not result.get("values"):
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{REFERENCE_TAB}!A1",
            valueInputOption="RAW",
            body={"values": [REF_COLUMNS]},
        ).execute()


def read_reference_library(service, sheet_id: str, topic: str = "") -> str:
    """
    Load reference material from the Reference_Library tab.

    Returns combined text of:
      - All rows where Type == 'global' (always included)
      - All rows where Type == 'topic' AND Topic Filter keyword appears in topic name

    Combined result stripped to 4000 chars for Agent 3 prompt.
    Returns "" if tab is empty or unavailable.
    """
    try:
        ensure_reference_tab(service, sheet_id)
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=f"{REFERENCE_TAB}!A:D"
        ).execute()
        rows = result.get("values", [])[1:]  # skip header
        topic_lower = topic.lower()
        parts: list[str] = []
        for row in rows:
            if len(row) < 3:
                continue
            ref_type = row[0].strip().lower()
            topic_filter = row[1].strip().lower() if len(row) > 1 else ""
            ref_text = row[2].strip() if len(row) > 2 else ""
            if not ref_text:
                continue
            if ref_type == "global":
                parts.append(ref_text)
            elif ref_type == "topic" and topic_filter and topic_filter in topic_lower:
                parts.append(ref_text)
        combined = "\n".join(parts)
        return combined[:4000]
    except Exception:
        return ""


def add_reference(service, sheet_id: str, ref_type: str, topic_filter: str, ref_text: str) -> None:
    """Append one row to the Reference_Library tab."""
    from datetime import date as _date
    try:
        ensure_reference_tab(service, sheet_id)
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{REFERENCE_TAB}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[ref_type, topic_filter, ref_text, _date.today().isoformat()]]},
        ).execute()
    except Exception as exc:
        print(f"[ref_lib] add_reference failed: {exc}", flush=True)


# ── Dedup Log tab — persists seen_topics across GitHub Actions runs ──────────
DEDUP_TAB = "Dedup_Log"


def ensure_dedup_tab(service, sheet_id: str) -> None:
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if DEDUP_TAB not in existing_titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": DEDUP_TAB}}}]},
        ).execute()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"{DEDUP_TAB}!A1:B1"
    ).execute()
    if not result.get("values"):
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{DEDUP_TAB}!A1",
            valueInputOption="RAW",
            body={"values": [["topic_slug", "added_at"]]},
        ).execute()


def read_dedup_log(service, sheet_id: str) -> dict:
    """Return {topic_slug: added_at_iso} from Dedup_Log tab. {} on first run."""
    try:
        ensure_dedup_tab(service, sheet_id)
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=f"{DEDUP_TAB}!A:B"
        ).execute()
        seen = {}
        for row in result.get("values", [])[1:]:
            if len(row) >= 2:
                seen[row[0]] = row[1]
        return seen
    except Exception:
        return {}


def write_dedup_log(service, sheet_id: str, seen: dict) -> None:
    """Overwrite Dedup_Log tab with the current seen_topics dict."""
    try:
        ensure_dedup_tab(service, sheet_id)
        rows = [["topic_slug", "added_at"]]
        rows.extend([slug, str(added_at)] for slug, added_at in seen.items())
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{DEDUP_TAB}!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
    except Exception as exc:
        print(f"[dedup] Sheets write failed: {exc}", flush=True)


# ── Competitor Intel tab — daily news + trend monitor results ─────────────────
COMPETITOR_INTEL_TAB = "Competitor Intel"
COMPETITOR_INTEL_HEADER = [
    "Date", "Urgency", "Executive Summary", "Top Competitor Move",
    "Trending Topic", "viAct Opportunity",
    "Competitor News Count", "Trends Count", "Opportunities Count",
    "Top 3 Competitor News", "Top 3 Trends", "Top 3 Opportunities",
]


def push_competitor_intel(intel: dict, sheet_id: str = "") -> int:
    """
    Append today's competitor intelligence to 'Competitor Intel' tab.
    Creates tab + header on first call.
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service = get_sheets_service()

    # Create tab if missing
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if COMPETITOR_INTEL_TAB not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": COMPETITOR_INTEL_TAB}}}]},
        ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{COMPETITOR_INTEL_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [COMPETITOR_INTEL_HEADER]},
        ).execute()
        # Format header row
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        gid = next(s["properties"]["sheetId"] for s in meta2["sheets"]
                   if s["properties"]["title"] == COMPETITOR_INTEL_TAB)
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(COMPETITOR_INTEL_HEADER)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.051, "green": 0.278, "blue": 0.631},
                        "textFormat": {"bold": True, "fontSize": 10, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()

    # Build summary strings
    top_news = " | ".join(
        f"[{n['competitor']}] {n['title'][:60]}"
        for n in intel.get("competitor_news", [])[:3]
    )
    top_trends = " | ".join(
        t["title"][:60] for t in intel.get("industry_trends", [])[:3]
    )
    top_opps = " | ".join(
        o["title"][:60] for o in intel.get("marketing_opportunities", [])[:3]
    )
    counts = intel.get("counts", {})

    row = [
        intel.get("date", ""),
        intel.get("urgency", "medium").upper(),
        intel.get("executive_summary", ""),
        intel.get("top_competitor_move", ""),
        intel.get("trending_topic", ""),
        intel.get("viact_opportunity", ""),
        str(counts.get("competitor_news", 0)),
        str(counts.get("trends", 0)),
        str(counts.get("opportunities", 0)),
        top_news,
        top_trends,
        top_opps,
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{COMPETITOR_INTEL_TAB}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    return 1


# ── Daily Topics — one row per day, cumulative history ───────────────────────

DAILY_TOPICS_TAB = "Daily Topics"
DAILY_TOPICS_HEADER = [
    "Date",
    "Industry Topic", "Industry", "Industry Why",
    "CS Company Type", "CS Industry", "CS Location", "CS Detection Focus", "CS Why",
    "VA Detection", "VA Why",
    "Urgency",
    "Pillar Topic", "Pillar Keyword", "Pillar Why",
    "Blog Topic", "Blog Keyword", "Blog Why",
    "Solutions Name", "Solutions Why",
]


def push_daily_topics(intel: dict, sheet_id: str = "") -> int:
    """
    Append one row to 'Daily Topics' tab with today's 3 suggested content topics.
    Creates tab + header on first call. Appends (never overwrites) for history.
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service = get_sheets_service()

    # Create tab + header if missing
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if DAILY_TOPICS_TAB not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": DAILY_TOPICS_TAB}}}]},
        ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{DAILY_TOPICS_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [DAILY_TOPICS_HEADER]},
        ).execute()
        # Bold blue header
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        gid = next(s["properties"]["sheetId"] for s in meta2["sheets"]
                   if s["properties"]["title"] == DAILY_TOPICS_TAB)
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(DAILY_TOPICS_HEADER)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.051, "green": 0.278, "blue": 0.631},
                        "textFormat": {"bold": True, "fontSize": 10,
                                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()

    topics    = intel.get("daily_topics", {})
    ind       = topics.get("industry_topic", {})
    cs        = topics.get("case_study_topic", {})
    va        = topics.get("va_topic", {})
    pillar    = topics.get("pillar_topic", {})
    blog      = topics.get("blog_topic", {})
    solutions = topics.get("solutions_topic", {})

    row = [
        intel.get("date", ""),
        ind.get("topic", ""),
        ind.get("industry", ""),
        ind.get("why", ""),
        cs.get("company_type", ""),
        cs.get("industry", ""),
        cs.get("location", ""),
        cs.get("detection_focus", ""),
        cs.get("why", ""),
        va.get("detection_name", ""),
        va.get("why", ""),
        intel.get("urgency", "medium").upper(),
        pillar.get("topic", ""),
        pillar.get("primary_keyword", ""),
        pillar.get("why", ""),
        blog.get("topic", ""),
        blog.get("primary_keyword", ""),
        blog.get("why", ""),
        solutions.get("solution_name", ""),
        solutions.get("why", ""),
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{DAILY_TOPICS_TAB}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    return 1


# ── Product Launches — competitor product/feature launch tracker ──────────────

PRODUCT_LAUNCHES_TAB = "Product Launches"
PRODUCT_LAUNCHES_HEADER = [
    "Date", "Competitor", "Product / Feature Name", "URL", "Snippet", "Status",
]


def push_product_launches(intel: dict, sheet_id: str = "") -> int:
    """
    Append today's detected competitor product launches to 'Product Launches' tab.
    Creates tab + dark-blue header on first call. Appends — never overwrites.
    Returns number of rows written.
    """
    launches = intel.get("product_launches", [])
    if not launches:
        return 0

    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service = get_sheets_service()

    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if PRODUCT_LAUNCHES_TAB not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": PRODUCT_LAUNCHES_TAB}}}]},
        ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{PRODUCT_LAUNCHES_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [PRODUCT_LAUNCHES_HEADER]},
        ).execute()
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        gid = next(s["properties"]["sheetId"] for s in meta2["sheets"]
                   if s["properties"]["title"] == PRODUCT_LAUNCHES_TAB)
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(PRODUCT_LAUNCHES_HEADER)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.051, "green": 0.110, "blue": 0.310},
                        "textFormat": {"bold": True, "fontSize": 10,
                                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()

    rows = [
        [
            launch.get("date", ""),
            launch.get("competitor", ""),
            launch.get("product_name", ""),
            launch.get("url", ""),
            launch.get("snippet", "")[:200],
            "New",
        ]
        for launch in launches
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{PRODUCT_LAUNCHES_TAB}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


# ── Competitor Site Changes — website page change tracker ─────────────────────

COMPETITOR_SITE_CHANGES_TAB = "Competitor Site Changes"
COMPETITOR_SITE_CHANGES_HEADER = [
    "Date", "Competitor", "Change Type", "URL",
    "Page Title", "Content Snippet", "Marketing Response", "Status",
]


def push_competitor_site_changes(intel: dict, sheet_id: str = "") -> int:
    """
    Append today's detected competitor website changes to 'Competitor Site Changes' tab.
    Creates tab + teal header on first call. Appends — never overwrites.
    Returns number of rows written.
    """
    changes = intel.get("website_changes", [])
    if not changes:
        return 0

    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service = get_sheets_service()

    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if COMPETITOR_SITE_CHANGES_TAB not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": COMPETITOR_SITE_CHANGES_TAB}}}]},
        ).execute()
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{COMPETITOR_SITE_CHANGES_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [COMPETITOR_SITE_CHANGES_HEADER]},
        ).execute()
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        gid = next(s["properties"]["sheetId"] for s in meta2["sheets"]
                   if s["properties"]["title"] == COMPETITOR_SITE_CHANGES_TAB)
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(COMPETITOR_SITE_CHANGES_HEADER)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.0, "green": 0.412, "blue": 0.361},
                        "textFormat": {"bold": True, "fontSize": 10,
                                       "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()

    rows = [
        [
            ch.get("date", ""),
            ch.get("competitor", ""),
            ch.get("change_type", "").replace("_", " ").title(),
            ch.get("url", ""),
            ch.get("title", ""),
            ch.get("content_snippet", "")[:200],
            ch.get("marketing_response", ""),
            "New",
        ]
        for ch in changes
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{COMPETITOR_SITE_CHANGES_TAB}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    return len(rows)


# ── Video Analytics Item Pages — one tab per detection type ──────────────────

def push_video_analytics_page(result: dict, sheet_id: str = "") -> int:
    """
    Push video analytics item page content to a tab named "VA — {detection_name}".
    Layout: field name in col A, value in col B (vertical, same as push_case_study).
    Creates tab if missing; clears and rewrites on each run (fresh, not appended).
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service       = get_sheets_service()
    cms           = result.get("cms_fields", {})
    meta          = result.get("generation_meta", {})
    errors        = result.get("quality_gate_errors", [])
    detection     = cms.get("title", meta.get("detection_name", "VA Page")).strip()
    tab_name      = f"VA — {detection}"[:100]

    # Create tab or clear existing
    sheet_meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing   = [s["properties"]["title"] for s in sheet_meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
    else:
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range=f"'{tab_name}'!A:B",
        ).execute()

    rows: list[list] = []
    section_rows: list[int] = []

    def sec(title):
        section_rows.append(len(rows))
        rows.append([title, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # ── META ─────────────────────────────────────────────────────────────────
    sec("META")
    f("Date",         meta.get("timestamp", "")[:10])  # yyyy-MM-dd for GAS isToday check
    f("Generated",    meta.get("timestamp", "")[:19].replace("T", " ") + " UTC")
    f("Status",       "Draft")
    f("Model",        meta.get("model_used", ""))
    f("Retry Count",  str(meta.get("retry_count", 0)))
    blank()

    # ── SEO & META ────────────────────────────────────────────────────────────
    sec("SEO & META")
    f("Meta Title",        cms.get("meta_title", ""))
    f("Meta Description",  cms.get("meta_descriptions", ""))
    f("Keywords",          cms.get("keywords", ""))
    blank()

    # ── HERO ─────────────────────────────────────────────────────────────────
    sec("HERO SECTION")
    f("Title",           cms.get("title", ""))
    f("H1",              cms.get("h1", ""))
    f("H2",              cms.get("h2", ""))
    f("H3",              cms.get("h3", ""))
    f("First Paragraph", cms.get("first_paragraph", ""))
    blank()

    # ── CHALLENGES ───────────────────────────────────────────────────────────
    sec("CHALLENGES (t1 block)")
    f("Section Title [t1]", cms.get("t1", ""))
    f("Body [td]",          cms.get("td", ""))
    blank()

    # ── HOW IT WORKS ─────────────────────────────────────────────────────────
    sec("HOW COMPUTER VISION WORKS (t2 block)")
    f("Section Title [t2]",         cms.get("t2", ""))
    f("Step 1 Title [t2_ct2]",      cms.get("t2_ct2", ""))
    f("Step 1 Description",         cms.get("t2_cdesc2", ""))
    f("Step 2 Title [t2_t1]",       cms.get("t2_t1", ""))
    f("Step 2 Description",         cms.get("t2_1d", ""))
    f("Step 3 Title [t3_1t]",       cms.get("t3_1t", ""))
    f("Step 3 Description",         cms.get("t3_1d", ""))
    f("Step 4 Title [t4_t1]",       cms.get("t4_t1", ""))
    f("Step 4 Description",         cms.get("t4_td", ""))
    blank()

    # ── WHERE NEEDED MOST (s6) ────────────────────────────────────────────────
    sec("WHERE NEEDED MOST (s6)")
    f("Section Title [s6_title]",   cms.get("s6_title", ""))
    f("Intro [s6_descriptions]",    cms.get("s6_descriptions", ""))
    for i in range(1, 6):
        f(f"Use Case {i} Title [s6_t{i}]",   cms.get(f"s6_t{i}", ""))
        f(f"Use Case {i} Desc [s6_desc{i}]", cms.get(f"s6_desc{i}", ""))
    blank()

    # ── CASE STUDY SNAPSHOT (s7) ──────────────────────────────────────────────
    sec("CASE STUDY SNAPSHOT (s7)")
    f("Headline [s7_title]",              cms.get("s7_title", ""))
    f("Industry Label",                   cms.get("construction", ""))
    f("Location Label",                   cms.get("singapore", ""))
    f("Module Label",                     cms.get("open_edge_detection", ""))
    f("The Problem",                      cms.get("problem_description", ""))
    f("The Solution",                     cms.get("solution_description", ""))
    f("The viAct impAct",                 cms.get("viact_impact_descriptions", ""))
    blank()

    # ── WHY VIACT (s8) ────────────────────────────────────────────────────────
    sec("WHY VIACT (s8)")
    f("Section Title [s8_title]",   cms.get("s8_title", ""))
    f("Intro Line [s8_description]", cms.get("s8_description", ""))
    for i in range(1, 8):
        f(f"Bullet {i} [s8_{i}]", cms.get(f"s8_{i}", ""))
    blank()

    # ── ALT TEXTS ────────────────────────────────────────────────────────────
    sec("ALT TEXTS")
    f("Hero Image Alt Text",   cms.get("hero_image_alt_text", ""))
    f("Image Alt Text 1",      cms.get("image_alt_text_1", ""))
    f("Image Alt Text 2",      cms.get("image_alt_text_2", ""))
    f("Image Alt Text 3",      cms.get("image_alt_text_3", ""))
    f("Image Alt Text 4",      cms.get("image_alt_text_4", ""))
    f("S7 Image Alt Text",     cms.get("s7_image_alt_text", ""))
    blank()

    # ── QUALITY GATE ─────────────────────────────────────────────────────────
    if errors:
        sec("⚠️ QUALITY GATE WARNINGS")
        for e in errors:
            f("Warning", e)
        blank()

    # Write rows
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Format: green section headers + column widths
    meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )
    fmt_requests = []
    for row_idx in section_rows:
        fmt_requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_gid, "startRowIndex": row_idx,
                           "endRowIndex": row_idx + 1, "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.718, "green": 0.882, "blue": 0.804},
                    "textFormat": {"bold": True, "fontSize": 10},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })
    fmt_requests += [
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 220}, "fields": "pixelSize",
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            "properties": {"pixelSize": 700}, "fields": "pixelSize",
        }},
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": fmt_requests},
    ).execute()
    return 1


def push_solutions_page(result: dict, sheet_id: str = "") -> int:
    """
    Push solutions item page content to a tab named "Sol — {solution_name}".
    Vertical layout: field name in col A, value in col B.
    Creates tab if missing; clears and rewrites on each run.
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service  = get_sheets_service()
    cms      = result.get("cms_fields", {})
    meta     = result.get("generation_meta", {})
    errors   = result.get("quality_gate_errors", [])
    sol_name = cms.get("solution_name", meta.get("solution_name", "Solution")).strip()
    tab_name = f"Sol — {sol_name}"[:100]

    sheet_meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing   = [s["properties"]["title"] for s in sheet_meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
    else:
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range=f"'{tab_name}'!A:B",
        ).execute()

    rows: list[list] = []
    section_rows: list[int] = []

    def sec(title):
        section_rows.append(len(rows))
        rows.append([title, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # META
    sec("META")
    f("Date",          meta.get("timestamp", "")[:10])
    f("Solution Name", sol_name)
    f("Slug",          cms.get("slug", ""))
    f("Status",        "Draft")
    f("Retry Count",   str(meta.get("retry_count", 0)))
    f("Quality Errors", "; ".join(errors) if errors else "None")
    blank()

    # SEO
    sec("SEO")
    f("Meta Title",       cms.get("seo_meta_title", ""))
    f("Meta Description", cms.get("seo_meta_description", ""))
    f("Keywords",         cms.get("seo_keywords", ""))
    blank()

    # HERO
    sec("HERO")
    f("Tagline",           cms.get("tagline", ""))
    f("Short Description", cms.get("short_description", ""))
    f("Long Description",  cms.get("long_description", ""))
    f("Testimonial Quote", cms.get("testimonial_quote", ""))
    f("Attribution",       cms.get("testimonial_attribution", ""))
    blank()

    # DIFFERENCE SECTION
    sec("DIFFERENCE SECTION (Trends / Stats / Outcome)")
    f("Section Title",    cms.get("diff_section_title", ""))
    f("Trend Title",      cms.get("trend_title", ""))
    f("Trend Desc",       cms.get("trend_description", ""))
    f("Stats Title",      cms.get("stats_title", ""))
    f("Stats Desc",       cms.get("stats_description", ""))
    f("Outcome Title",    cms.get("outcome_title", ""))
    f("Outcome Desc",     cms.get("outcome_description", ""))
    blank()

    # CTA
    sec("CTA")
    f("CTA Text",    cms.get("cta_text", ""))
    f("CTA Button",  cms.get("cta_button", ""))
    f("New CTA Text (bottom page)", cms.get("new_cta_text", ""))
    blank()

    # FEATURES
    sec("FEATURES")
    f("Features Title", cms.get("features_title", ""))
    for i in range(1, 6):
        f(f"Feature Tab {i}", cms.get(f"feature_tab_{i}", ""))
    blank()
    for i in range(1, 15):
        f(f"Bullet {i}", cms.get(f"bullet_{i}", ""))
    blank()

    # PERFORMANCE METRICS
    sec("POST-DEPLOYMENT METRICS")
    for i in range(1, 4):
        f(f"Metric {i} Value", cms.get(f"metric_{i}_value", ""))
        f(f"Metric {i} Desc",  cms.get(f"metric_{i}_desc", ""))
    blank()

    # UVPs
    sec("UNIQUE VALUE PROPOSITIONS")
    for i in range(1, 6):
        f(f"UVP {i} Title", cms.get(f"uvp_{i}_title", ""))
        f(f"UVP {i} Desc",  cms.get(f"uvp_{i}_desc", ""))
    blank()

    # IMAGE ALT TEXTS
    sec("IMAGE ALT TEXTS (SEO)")
    f("hero image",         cms.get("hero_image_alt", ""))
    f("Trends img",         cms.get("trends_image_alt", ""))
    f("STATISTICS img",     cms.get("stats_image_alt", ""))
    f("OUTCOME img",        cms.get("outcome_image_alt", ""))
    f("dashboard img",      cms.get("dashboard_image_alt", ""))
    f("Solution list image",cms.get("list_image_alt", ""))
    for i in range(1, 6):
        f(f"{i} Key features", cms.get(f"feature_{i}_img_alt", ""))
    for i in range(1, 6):
        f(f"{i} Unique Value", cms.get(f"uvp_{i}_img_alt", ""))
    f("1 check",            cms.get("check_img_alt", ""))
    blank()

    # OUR TECHNOLOGIES (static, same across all solutions pages)
    _OT = [
        ("Computer Vision",   "Transforms video feeds into actionable safety insights by detecting unsafe behaviors, PPE violations, and environmental hazards in real-time."),
        ("AI CCTV Cameras",   "Enhance traditional surveillance with AI-powered analytics to monitor compliance, detect intrusions, and automate safety alerts across dynamic jobsites."),
        ("Edge Devices",      "Enable real-time data processing on-site, minimizing latency and ensuring faster safety responses without relying on constant cloud connectivity."),
        ("IoT & Wearables",   "Integrates smart helmets, locks and sensors for seamless monitoring of workers' vitals, movement, equipment status, and environmental conditions."),
        ("Drones",            "Deploy low-altitude drones for autonomous site surveillance, thermal scanning, and hazard detection in hard-to-reach or high-risk work zones."),
        ("Co-pilot / AI Agents", "Acts as digital assistants offering voice/text-based safety guidance, process automation, and instant access to documentation for frontline teams."),
    ]
    sec("OUR TECHNOLOGIES (static)")
    for ot_title, ot_desc in _OT:
        f(f"ot: {ot_title}", ot_desc)
    blank()

    # FAQs — combined Q+A per field (Wix format: "Question?\n\nAnswer.")
    sec("FAQs (Wix: Q+A combined per field)")
    for i in range(1, 6):
        q = cms.get(f"faq_{i}_q", "")
        a = cms.get(f"faq_{i}_a", "")
        if q or a:
            f(f"faq{i}", f"{q}\n\n{a}" if q and a else (q or a))
    blank()

    # IMAGE PROMPTS (Nano Banana)
    image_prompts = result.get("image_prompts", [])
    if image_prompts:
        sec("IMAGE PROMPTS (Nano Banana)")
        for img in image_prompts:
            placement = img.get("placement", "")
            prompt    = img.get("prompt", "")
            alt_text  = img.get("alt_text", "")
            f(f"[{placement}] prompt", prompt)
            f(f"[{placement}] alt_text", alt_text)
        blank()

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Format: bold section headers, wide col B
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in service.spreadsheets().get(spreadsheetId=sheet_id).execute().get("sheets", [])
        if s["properties"]["title"] == tab_name
    )
    fmt_requests = [
        {"repeatCell": {
            "range": {"sheetId": sheet_gid, "startRowIndex": r, "endRowIndex": r + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                           "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.24}}},
            "fields": "userEnteredFormat(textFormat,backgroundColor)",
        }} for r in section_rows
    ] + [{"updateDimensionProperties": {
        "range": {"sheetId": sheet_gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
        "properties": {"pixelSize": 700}, "fields": "pixelSize",
    }}]
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": fmt_requests},
    ).execute()
    return 1


def push_blog_post(result: dict, sheet_id: str = "") -> int:
    """
    Push blog post CMS fields to a tab named "Blog — {title}".
    Vertical layout: field name in col A, value in col B.
    Creates tab if missing; clears and rewrites on each run.
    Returns 1 on success.
    """
    if not sheet_id:
        sheet_id = os.getenv("INDUSTRY_SHEET_ID") or get_env("SHEET_ID")

    service  = get_sheets_service()
    cms      = result.get("cms_fields", {})
    seo      = result.get("seo", {})
    meta     = result.get("generation_meta", {})
    title    = cms.get("blog_title", meta.get("topic", "Blog")).strip()
    tab_name = f"Blog — {title}"[:100]

    sheet_meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing   = [s["properties"]["title"] for s in sheet_meta.get("sheets", [])]
    if tab_name not in existing:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()
    else:
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range=f"'{tab_name}'!A:B",
        ).execute()

    rows: list[list] = []
    section_rows: list[int] = []

    def sec(t):
        section_rows.append(len(rows))
        rows.append([t, ""])

    def f(label, value):
        rows.append([label, str(value) if value is not None else ""])

    def blank():
        rows.append(["", ""])

    # META
    sec("META")
    f("Date",          meta.get("generated_at", "")[:10])
    f("Blog Title",    title)
    f("Slug",          cms.get("slug", ""))
    f("Category",      cms.get("category", ""))
    f("Tags",          ", ".join(cms.get("tags", [])))
    f("Reading Time",  cms.get("reading_time", ""))
    f("Author",        cms.get("author", "viAct Editorial Team"))
    f("Publish Date",  cms.get("publish_date", ""))
    f("Status",        "Draft")
    blank()

    # SEO
    sec("SEO")
    f("Meta Title",         cms.get("meta_title", ""))
    f("Meta Description",   cms.get("meta_description", ""))
    f("Focus Keyword",      seo.get("focus_keyword", ""))
    f("Secondary Keywords", ", ".join(seo.get("secondary_keywords", [])))
    f("Est. Word Count",    str(seo.get("estimated_word_count", "")))
    f("Keyword in Title",   "Yes" if seo.get("keyword_in_title") else "No")
    f("Keyword in Desc",    "Yes" if seo.get("keyword_in_desc") else "No")
    blank()

    # BODY
    sec("BODY")
    f("Excerpt",      cms.get("excerpt", ""))
    f("Introduction", cms.get("introduction", ""))
    tldr = cms.get("tldr", [])
    if tldr:
        f("TLDR", "\n".join([f"{i}. {p}" for i, p in enumerate(tldr, 1)]))
    toc = cms.get("table_of_contents", [])
    if toc:
        f("Table of Contents", "\n".join([f"{i}. {h}" for i, h in enumerate(toc, 1)]))
    for i, sec_data in enumerate(cms.get("body_sections", []), 1):
        f(f"Section {i} H2", sec_data.get("heading", ""))
        if sec_data.get("content"):
            f(f"Section {i} Intro", sec_data.get("content", ""))
        for j, sub in enumerate(sec_data.get("subsections", []), 1):
            f(f"Section {i}.{j} H3", sub.get("subheading", ""))
            f(f"Section {i}.{j} Content", sub.get("content", ""))
    cs = cms.get("case_study", {})
    if cs:
        sec("CASE STUDY")
        f("Section Heading", cs.get("heading", ""))
        f("Client",    cs.get("client", ""))
        f("Challenge", cs.get("challenge", ""))
        f("Solution",  cs.get("solution", ""))
        f("Outcome",   cs.get("outcome", ""))
    f("Conclusion", cms.get("conclusion", ""))
    kt = cms.get("key_takeaways", [])
    if kt:
        f("Key Takeaways", "\n".join([f"• {t}" for t in kt]))
    faqs = cms.get("faqs", [])
    if faqs:
        sec("FAQs")
        for i, faq in enumerate(faqs, 1):
            f(f"FAQ {i} Q", faq.get("question", ""))
            f(f"FAQ {i} A", faq.get("answer", ""))
    blank()

    # CTA
    sec("CTA")
    f("CTA Heading",     cms.get("cta_heading", ""))
    f("CTA Body",        cms.get("cta_body", ""))
    f("CTA Button Text", cms.get("cta_button_text", ""))
    f("CTA URL",         cms.get("cta_url", ""))
    blank()

    # IMAGE
    sec("IMAGE")
    f("Hero Image Alt Text",    cms.get("image_alt_main", ""))
    f("Hero Image Prompt",      cms.get("image_prompt_main", ""))
    blank()

    # INTERNAL LINKS
    sec("INTERNAL LINKS")
    for lnk in cms.get("internal_links", []):
        f(lnk.get("anchor", ""), lnk.get("suggested_page", ""))

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    fmt_requests = []
    for r in section_rows:
        fmt_requests.append({
            "repeatCell": {
                "range": {"sheetId": _get_sheet_id(service, sheet_id, tab_name),
                           "startRowIndex": r, "endRowIndex": r + 1,
                           "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.93, "green": 0.47, "blue": 0.24},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        })

    if fmt_requests:
        sheet_meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        tab_gid = next(
            s["properties"]["sheetId"]
            for s in sheet_meta2["sheets"]
            if s["properties"]["title"] == tab_name
        )
        for req in fmt_requests:
            req["repeatCell"]["range"]["sheetId"] = tab_gid
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id, body={"requests": fmt_requests},
        ).execute()
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Partner Outreach (Agent 11) — one tab per competitor in PARTNER_SHEET_ID
# ─────────────────────────────────────────────────────────────────────────────

# Existing user-maintained columns (A–H) preserved verbatim.
# 3 agent-managed columns added (I–K).
# Phone Number (D) kept in schema but left blank — agent does not fill it.
PARTNER_COLUMNS = [
    "Company Name",      # A
    "Description",       # B
    "Website",           # C
    "Phone Number",      # D — left blank (user's manual column)
    "Email",             # E — scraped or verified email
    "Address",           # F — scraped from partner website
    "Country",           # G — scraped or inferred
    "Status",            # H — user sets "Shortlist" / "Done" manually
    "Email Source",      # I — scraped | tavily | pattern_verified | whois
    "Discovered Via",    # J — A1:sitemap | A2:homepage | A3:patterns | A4:site-search | A5:news | A6:customers
    "Discovered At",     # K — YYYY-MM-DD
]


def _norm_domain_for_dedup(website: str) -> str:
    """Strip protocol/www/path — same logic as discover_partners._norm_domain."""
    import re as _re
    if not website:
        return ""
    w = website.lower().strip()
    w = _re.sub(r"^https?://", "", w)
    w = _re.sub(r"^www\.", "", w)
    w = w.split("/")[0].strip()
    return w


def _norm_name_for_dedup(name: str) -> str:
    """Lowercase + strip suffixes — same logic as discover_partners._norm_name."""
    import re as _re
    n = name.lower().strip()
    n = _re.sub(r"[,\.]", "", n)
    n = _re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|pvt|private)\b", "", n)
    n = _re.sub(r"\s+", " ", n).strip()
    return n


def _ensure_partner_columns(service, sheet_id: str, tab_name: str) -> None:
    """Make sure header row has the 5 agent-managed columns (I-M). Idempotent."""
    range_ = f"'{tab_name}'!1:1"
    resp = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_).execute()
    header = resp.get("values", [[]])
    header = header[0] if header else []

    # Header is correct if all 13 cols match
    if header[:len(PARTNER_COLUMNS)] == PARTNER_COLUMNS:
        return

    # Otherwise overwrite row 1 with the canonical header
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [PARTNER_COLUMNS]},
    ).execute()


def _read_existing_partners(service, sheet_id: str, tab_name: str) -> tuple[set, set]:
    """
    Return (existing_domains, existing_names_normalized) from the tab.
    Used to dedup before appending.
    """
    try:
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{tab_name}'!A2:C",
        ).execute()
    except Exception:
        return set(), set()

    rows = resp.get("values", [])
    domains: set = set()
    names: set = set()
    for row in rows:
        name = row[0] if len(row) >= 1 else ""
        website = row[2] if len(row) >= 3 else ""
        if website:
            d = _norm_domain_for_dedup(website)
            if d:
                domains.add(d)
        if name:
            names.add(_norm_name_for_dedup(name))
    return domains, names


def push_partners(competitor_tab: str, partners: list[dict], sheet_id: str = "") -> int:
    """
    Append new partner rows to the competitor's tab. Dedup against existing
    rows by Website domain first, then by normalized Company Name.

    Args:
        competitor_tab: Exact tab name in PARTNER_SHEET_ID (e.g., "Openspace").
        partners: List of dicts from discover_partners() — fields:
            name, description, website, country, discovered_via
        sheet_id: Override PARTNER_SHEET_ID (optional).

    Returns:
        Count of rows actually appended (after dedup).

    Raises:
        EnvironmentError if PARTNER_SHEET_ID is not set.
        ValueError if the tab doesn't exist (we do NOT auto-create — user
        controls which competitors are tracked).
    """
    if not sheet_id:
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        raise EnvironmentError(
            "PARTNER_SHEET_ID not set. Add to .env: "
            "PARTNER_SHEET_ID=1Q2XJZ2STaCN94DK4JEnS1mHkrgILfFljjNCc1dy_5qw"
        )

    if not partners:
        return 0

    service = get_sheets_service()

    # Auto-create the tab if missing (v2: Competitors tab drives which tabs exist,
    # so any Track-marked new competitor without a pre-existing tab gets one now)
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if competitor_tab not in existing_tabs:
        # Create the tab
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": competitor_tab}}}]},
        ).execute()
        # Write header row
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{competitor_tab}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [PARTNER_COLUMNS]},
        ).execute()
        # Style header row
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        tab_gid = next(
            s["properties"]["sheetId"]
            for s in meta2["sheets"]
            if s["properties"]["title"] == competitor_tab
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": tab_gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(PARTNER_COLUMNS)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.812, "green": 0.886, "blue": 0.953},
                        "textFormat": {"bold": True, "fontSize": 10},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()

    _ensure_partner_columns(service, sheet_id, competitor_tab)
    existing_domains, existing_names = _read_existing_partners(service, sheet_id, competitor_tab)

    today_str = date.today().isoformat()
    new_rows: list[list[str]] = []

    for p in partners:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        website = (p.get("website") or "").strip()
        norm_d = _norm_domain_for_dedup(website)
        norm_n = _norm_name_for_dedup(name)

        # Dedup: domain first (stronger signal), then name
        if norm_d and norm_d in existing_domains:
            continue
        if norm_n in existing_names:
            continue

        new_rows.append([
            name,
            (p.get("description") or "").strip(),
            website,
            (p.get("phone") or "").strip(),              # Phone — v3.1: extracted from partner website
            (p.get("email") or "").strip(),              # Email
            (p.get("address") or "").strip(),            # Address
            (p.get("country") or "").strip(),
            "",                                          # Status — user fills manually
            (p.get("email_source") or "").strip(),       # Email Source
            p.get("discovered_via", ""),
            today_str,
        ])

        # Update local sets so duplicates within the same batch get dropped too
        if norm_d:
            existing_domains.add(norm_d)
        existing_names.add(norm_n)

    if not new_rows:
        return 0

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{competitor_tab}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows},
    ).execute()

    return len(new_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Competitors tab (Agent 1) — auto-discovered competitors go here
# ─────────────────────────────────────────────────────────────────────────────

COMPETITORS_TAB = "Competitors"
COMPETITORS_COLUMNS = [
    "Name",             # A
    "Website",          # B
    "Category",         # C — ai_vision | wearables_iot | site_documentation | compliance_checklist | project_management
    "Description",      # D
    "Discovered At",    # E — YYYY-MM-DD
    "Discovered Via",   # F — tavily+g2+capterra
    "Status",           # G — user marks Track / Skip
]


def _ensure_competitors_tab(service, sheet_id: str) -> None:
    """Create Competitors tab if missing, write header, apply header formatting."""
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

    if COMPETITORS_TAB not in existing_titles:
        # Create tab
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": COMPETITORS_TAB}}}]},
        ).execute()

        # Write header
        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{COMPETITORS_TAB}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [COMPETITORS_COLUMNS]},
        ).execute()

        # Style header
        meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        tab_gid = next(
            s["properties"]["sheetId"]
            for s in meta2["sheets"]
            if s["properties"]["title"] == COMPETITORS_TAB
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "repeatCell": {
                    "range": {"sheetId": tab_gid, "startRowIndex": 0, "endRowIndex": 1,
                              "startColumnIndex": 0, "endColumnIndex": len(COMPETITORS_COLUMNS)},
                    "cell": {"userEnteredFormat": {
                        "backgroundColor": {"red": 0.812, "green": 0.886, "blue": 0.953},
                        "textFormat": {"bold": True, "fontSize": 10},
                    }},
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }]},
        ).execute()
        return

    # Tab exists — check header row is correct
    resp = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{COMPETITORS_TAB}'!1:1",
    ).execute()
    header = resp.get("values", [[]])
    header = header[0] if header else []
    if header[:len(COMPETITORS_COLUMNS)] != COMPETITORS_COLUMNS:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{COMPETITORS_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [COMPETITORS_COLUMNS]},
        ).execute()


def _read_existing_competitors(service, sheet_id: str) -> tuple[set[str], set[str]]:
    """Return (existing_names, existing_domains) from the Competitors tab."""
    try:
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{COMPETITORS_TAB}'!A2:B",
        ).execute()
    except Exception:
        return set(), set()

    rows = resp.get("values", [])
    names: set[str] = set()
    domains: set[str] = set()
    for row in rows:
        if len(row) >= 1 and row[0]:
            names.add(_norm_name_for_dedup(row[0]))
        if len(row) >= 2 and row[1]:
            domains.add(_norm_domain_for_dedup(row[1]))
    return names, domains


def push_competitors(competitors: list[dict], sheet_id: str = "") -> int:
    """
    Append newly-discovered competitors to the Competitors tab. Dedup by
    normalized name and domain.

    Args:
        competitors: List of dicts from discover_competitors() — fields:
            name, website, category, description, discovered_at, discovered_via
        sheet_id: Override PARTNER_SHEET_ID (optional).

    Returns:
        Count of rows actually appended after dedup.
    """
    if not sheet_id:
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        raise EnvironmentError(
            "PARTNER_SHEET_ID not set. Add to .env: "
            "PARTNER_SHEET_ID=1Q2XJZ2STaCN94DK4JEnS1mHkrgILfFljjNCc1dy_5qw"
        )

    if not competitors:
        return 0

    service = get_sheets_service()
    _ensure_competitors_tab(service, sheet_id)

    existing_names, existing_domains = _read_existing_competitors(service, sheet_id)

    new_rows: list[list[str]] = []
    for c in competitors:
        name = (c.get("name") or "").strip()
        website = (c.get("website") or "").strip()
        if not name or not website:
            continue

        n_name = _norm_name_for_dedup(name)
        n_domain = _norm_domain_for_dedup(website)

        if n_name in existing_names or (n_domain and n_domain in existing_domains):
            continue

        new_rows.append([
            name,
            website,
            (c.get("category") or "").strip(),
            (c.get("description") or "").strip(),
            (c.get("discovered_at") or "").strip(),
            (c.get("discovered_via") or "").strip(),
            (c.get("status") or "").strip(),  # Optional pre-set (e.g., "Track" for seeded existing competitors)
        ])

        existing_names.add(n_name)
        if n_domain:
            existing_domains.add(n_domain)

    if not new_rows:
        return 0

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{COMPETITORS_TAB}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows},
    ).execute()

    return len(new_rows)


def read_tracked_competitors(sheet_id: str = "") -> list[dict]:
    """
    Return competitors from the Competitors tab where Status = "Track"
    (case-insensitive). Used by Agent 2 to know which new competitors to
    process. Format: [{name, website, category}].
    """
    if not sheet_id:
        sheet_id = os.getenv("PARTNER_SHEET_ID", "")
    if not sheet_id:
        return []
    try:
        service = get_sheets_service()
        resp = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{COMPETITORS_TAB}'!A2:G",
        ).execute()
    except Exception:
        return []

    out = []
    for row in resp.get("values", []):
        # Row layout: [name, website, category, description, discovered_at, discovered_via, status]
        if len(row) < 7:
            continue
        status = (row[6] or "").strip().lower()
        if status != "track":
            continue
        out.append({
            "name": row[0],
            "website": row[1],
            "category": row[2] if len(row) > 2 else "",
        })
    return out


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Push content rows to Google Sheets")
    parser.add_argument("--source", default="", help="Input source label (url/topic/file)")
    args = parser.parse_args()

    try:
        content = json.load(sys.stdin)
        count = push_webpage(content, input_source=args.source)
        print(json.dumps({"rows_written": count}))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
