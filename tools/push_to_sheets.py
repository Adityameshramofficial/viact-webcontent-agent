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

COLUMNS = ["Date", "Platform", "Post Copy", "Hashtags", "Image URL", "Input Source", "Status"]


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


def ensure_header(service, sheet_id: str):
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Sheet1!A1:G1"
    ).execute()
    existing = result.get("values", [])
    if not existing or existing[0] != COLUMNS:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": [COLUMNS]},
        ).execute()


def content_to_rows(content: dict, input_source: str, image_url: str) -> list:
    today = date.today().isoformat()
    rows = []

    for platform in ["linkedin", "twitter", "instagram"]:
        p = content.get(platform, {})
        copy = p.get("copy", "")
        hashtags = " ".join(f"#{h.lstrip('#')}" for h in p.get("hashtags", []))
        rows.append([today, platform.capitalize(), copy, hashtags, image_url, input_source, "Draft"])

    blog = content.get("blog", {})
    blog_copy = f"{blog.get('title', '')}\n\n{blog.get('copy', '')}"
    rows.append([today, "Blog", blog_copy, "", image_url, input_source, "Draft"])

    return rows


def push(content: dict, input_source: str = "", image_url: str = "") -> int:
    sheet_id = get_env("SHEET_ID")
    service = get_sheets_service()
    ensure_header(service, sheet_id)

    rows = content_to_rows(content, input_source, image_url)

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)


# ---------------------------------------------------------------------------
# Webpage Content pipeline — separate tab, separate schema
# All additions below are additive — existing push() is unchanged.
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

    # Write rows
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A{start_row}",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    # Apply formatting
    meta2 = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_gid = next(
        s["properties"]["sheetId"]
        for s in meta2["sheets"]
        if s["properties"]["title"] == tab_name
    )

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
def push_industry_page_vertical(content: dict, industry_name: str, sheet_id: str) -> int:
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Push content rows to Google Sheets")
    parser.add_argument("--source", default="", help="Input source label (url/topic/file)")
    parser.add_argument("--image-url", default="", help="Image URL to attach to rows")
    parser.add_argument("--mode", choices=["social", "webpage"], default="social")
    args = parser.parse_args()

    try:
        content = json.load(sys.stdin)
        if args.mode == "webpage":
            count = push_webpage(content, input_source=args.source)
        else:
            count = push(content, input_source=args.source, image_url=args.image_url)
        print(json.dumps({"rows_written": count}))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
