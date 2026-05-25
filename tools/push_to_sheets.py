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
        content.get("schema_json_ld", ""),
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
